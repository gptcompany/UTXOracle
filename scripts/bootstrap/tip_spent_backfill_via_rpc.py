#!/usr/bin/env python3
"""Spent-block backfill for QuestDB utxo_lifecycle via Bitcoin Core RPC.

spec-061 Wave 6 closing path (2026-06-03). Companion to
``tip_catchup_lifecycle_via_rpc.py``: where that script writes new
creation rows for blocks N..tip, this one scans the same range for
spending inputs and UPDATEs ``spent_block`` on existing QuestDB rows.

Together the two scripts let utxo_lifecycle_full reach freshness
(creation tip + spent tip) without touching the live DuckDB writer
lock at all.

Why this exists alongside ``historical_spent_backfill.py``:
    The original spent backfill writes DuckDB first, then propagates
    to QuestDB. That requires the DuckDB write lock, which the live
    wave1 materializer holds for long periods. This RPC-only path
    bypasses DuckDB entirely.

Usage:
    uv run python -m scripts.bootstrap.tip_spent_backfill_via_rpc

    # Custom range
    uv run python -m scripts.bootstrap.tip_spent_backfill_via_rpc \\
        --start-block 927968 --end-block 952000 --workers 8

Performance: bounded by Bitcoin Core RPC. Each block yields roughly
``tx_count - 1`` inputs to inspect (coinbase has no real inputs). At 8
workers + verbosity=2, expect ~10-15 ms / block of RPC time plus the
QuestDB UPDATE round-trip (batched 1000 at a time via psycopg
executemany).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Iterator

logger = logging.getLogger(__name__)

_THREAD_STATE = threading.local()
_BATCH_SIZE = 1000


def _resolve_log_level(raw_level: str | None) -> int:
    if (
        not raw_level
        or raw_level.startswith("ENC[")
        or raw_level.startswith("encrypted:")
    ):
        return logging.INFO
    level = getattr(logging, raw_level.upper(), None)
    return level if isinstance(level, int) else logging.INFO


def _thread_rpc_client():
    rpc = getattr(_THREAD_STATE, "rpc", None)
    if rpc is None:
        from scripts.sync_utxo_lifecycle import BitcoinRPC

        rpc = BitcoinRPC()
        _THREAD_STATE.rpc = rpc
    return rpc


def _resolve_tip() -> int:
    import subprocess

    try:
        result = subprocess.run(
            ["bitcoin-cli", "getblockcount"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return int(result.stdout.strip())
    except Exception as exc:
        logger.warning("bitcoin-cli failed (%s); using Python RPC", exc)
        return int(_thread_rpc_client().getblockcount())


def _resolve_questdb_max_spent() -> int:
    """Highest spent_block currently in QuestDB utxo_lifecycle.

    A NULL result (no spent rows at all) returns 0 so the caller defaults
    to the catchup start.
    """
    import psycopg

    from api.questdb_repository import (
        QUESTDB_PG_DATABASE,
        QUESTDB_PG_HOST,
        QUESTDB_PG_PASSWORD,
        QUESTDB_PG_PORT,
        QUESTDB_PG_USER,
    )

    with psycopg.connect(
        host=QUESTDB_PG_HOST,
        port=QUESTDB_PG_PORT,
        user=QUESTDB_PG_USER,
        password=QUESTDB_PG_PASSWORD,
        dbname=QUESTDB_PG_DATABASE,
        autocommit=True,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT max(spent_block) FROM utxo_lifecycle "
                "WHERE spent_block IS NOT NULL"
            )
            row = cur.fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def _fetch_block_inputs(height: int) -> tuple[int, list[tuple[int, str, int]]]:
    """Yield (height, [(spent_block, txid, vout_index), ...]) for a block.

    Uses verbosity=2 which includes the ``vin.txid`` + ``vin.vout`` we
    need without the heavier prevout decoration of verbosity=3.
    Coinbase inputs (no ``txid``) are skipped — they don't spend anything.
    """
    rpc = _thread_rpc_client()
    block_hash = rpc.getblockhash(height)
    block = rpc.getblock(block_hash, 2)
    updates: list[tuple[int, str, int]] = []
    for tx in block.get("tx", []):
        for vin in tx.get("vin", []):
            prev_txid = vin.get("txid")
            if not prev_txid:
                continue  # coinbase
            try:
                prev_vout = int(vin["vout"])
            except (KeyError, ValueError, TypeError):
                continue
            updates.append((int(height), prev_txid, prev_vout))
    return height, updates


def _iter_block_updates(
    start_block: int, end_block: int, workers: int = 8
) -> Iterator[tuple[int, list[tuple[int, str, int]]]]:
    """Bounded-future block scan; yield in monotonic height order."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending: dict[int, tuple[int, list[tuple[int, str, int]]]] = {}
        futures: dict = {}
        next_submit = start_block
        next_height = start_block

        def submit_until_full() -> None:
            nonlocal next_submit
            max_in_flight = max(1, workers * 2)
            while next_submit <= end_block and len(futures) < max_in_flight:
                futures[pool.submit(_fetch_block_inputs, next_submit)] = next_submit
                next_submit += 1

        submit_until_full()
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for fut in done:
                expected = futures.pop(fut)
                try:
                    h, updates = fut.result()
                    pending[h] = (h, updates)
                except Exception as exc:
                    raise RuntimeError(
                        f"RPC fetch failed for block {expected}: {exc}"
                    ) from exc
            while next_height in pending:
                yield pending.pop(next_height)
                next_height += 1
            submit_until_full()
        while pending:
            yield pending.pop(next_height)
            next_height += 1


def _open_questdb_pg():
    import psycopg

    from api.questdb_repository import (
        QUESTDB_PG_DATABASE,
        QUESTDB_PG_HOST,
        QUESTDB_PG_PASSWORD,
        QUESTDB_PG_PORT,
        QUESTDB_PG_USER,
    )

    return psycopg.connect(
        host=QUESTDB_PG_HOST,
        port=QUESTDB_PG_PORT,
        user=QUESTDB_PG_USER,
        password=QUESTDB_PG_PASSWORD,
        dbname=QUESTDB_PG_DATABASE,
        autocommit=True,
    )


def backfill(start_block: int, end_block: int, workers: int = 8) -> int:
    """Run the spent backfill. Returns total UPDATE rows issued."""
    issued = 0
    batch: list[tuple[int, str, int]] = []
    last_log = time.monotonic()

    def flush(conn) -> None:
        nonlocal issued, batch
        if not batch:
            return
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE utxo_lifecycle "
                "SET spent_block = %s, is_spent = true "
                "WHERE txid = %s AND vout_index = %s",
                batch,
            )
        issued += len(batch)
        batch = []

    with _open_questdb_pg() as conn:
        for height, updates in _iter_block_updates(start_block, end_block, workers):
            batch.extend(updates)
            if len(batch) >= _BATCH_SIZE:
                flush(conn)
            if height % 100 == 0:
                now = time.monotonic()
                if now - last_log >= 30:
                    logger.info(
                        "Spent backfill progress: block %d/%d (%.1f%%); updates=%d",
                        height,
                        end_block,
                        100 * (height - start_block + 1)
                        / max(1, end_block - start_block + 1),
                        issued + len(batch),
                    )
                    last_log = now
        flush(conn)

    return issued


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-block", type=int, default=None)
    parser.add_argument("--end-block", type=int, default=None)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    logging.basicConfig(
        level=_resolve_log_level(os.getenv("LOG_LEVEL", "INFO")),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    start = args.start_block
    if start is None:
        start = _resolve_questdb_max_spent() + 1
    end = args.end_block
    if end is None:
        end = _resolve_tip()

    if start > end:
        logger.info("Already at tip: max_spent=%d, tip=%d", start - 1, end)
        return 0

    logger.info(
        "Spent backfill range: blocks %d..%d (%d blocks, %d workers)",
        start, end, end - start + 1, args.workers,
    )
    t0 = time.monotonic()
    rows = backfill(start, end, workers=args.workers)
    elapsed = time.monotonic() - t0
    logger.info(
        "Spent backfill complete: %d UPDATEs in %.1fs (%.0f upd/s)",
        rows, elapsed, rows / max(0.001, elapsed),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
