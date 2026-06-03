#!/usr/bin/env python3
"""Catch up QuestDB utxo_lifecycle directly from Bitcoin Core RPC.

spec-061 elegant alternative to the DuckDB-intermediate catchup
(2026-06-03): bypass the DuckDB write lock entirely by reading new
blocks from Bitcoin Core and streaming creation rows into QuestDB via
ILP. Spent updates come later through the existing
``historical_spent_backfill.py --target-backend questdb`` path, so this
script handles only the CREATION side.

Why this exists:
    The original ``catchup_utxo_lifecycle_to_tip.py`` writes new blocks
    into DuckDB and then mirrors that delta into QuestDB. That requires
    a DuckDB write lock, which the production wave1 materializer holds
    continuously. This script removes the DuckDB dependency entirely so
    spec-061's freshness gate can flip to OK without disturbing the
    materializer.

Usage:
    uv run python -m scripts.bootstrap.tip_catchup_lifecycle_via_rpc

    # Custom range
    uv run python -m scripts.bootstrap.tip_catchup_lifecycle_via_rpc \\
        --start-block 927968 --end-block 952000

Performance: ~50 ms / block RPC + ~10 us / row ILP. Expected ~25 min for
24k blocks (~4M rows) on the production host.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Iterator

logger = logging.getLogger(__name__)

# Skip OP_RETURN outputs — provably unspendable, never appear in utxo_lifecycle_full
# in DuckDB either. Filtering reduces ILP traffic by ~30% on recent blocks.
_UNSPENDABLE_SCRIPT_TYPES = {"nulldata"}
_THREAD_STATE = threading.local()

# Outpoint format reuses what `utxo_lifecycle_full` already uses:
# `<txid>:<vout_index>` (no length restriction beyond the txid hex shape).


def _resolve_log_level(raw_level: str | None) -> int:
    if (
        not raw_level
        or raw_level.startswith("ENC[")
        or raw_level.startswith("encrypted:")
    ):
        return logging.INFO
    level = getattr(logging, raw_level.upper(), None)
    return level if isinstance(level, int) else logging.INFO


def _resolve_tip() -> int:
    """Resolve current Bitcoin tip via bitcoin-cli, fallback to BitcoinRPC."""
    try:
        result = subprocess.run(
            ["bitcoin-cli", "getblockcount"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return int(result.stdout.strip())
    except Exception as exc:
        logger.warning("bitcoin-cli failed (%s); falling back to Python RPC", exc)
        from scripts.sync_utxo_lifecycle import BitcoinRPC

        return int(BitcoinRPC().getblockcount())


def _resolve_questdb_max_creation() -> int:
    """Find the highest creation_block already in QuestDB utxo_lifecycle."""
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
            cur.execute("SELECT max(creation_block) FROM utxo_lifecycle")
            row = cur.fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def _thread_rpc_client():
    """Return one BitcoinRPC client per worker thread."""
    rpc = getattr(_THREAD_STATE, "rpc", None)
    if rpc is None:
        from scripts.sync_utxo_lifecycle import BitcoinRPC

        rpc = BitcoinRPC()
        _THREAD_STATE.rpc = rpc
    return rpc


def _fetch_block_via_rpc(height: int) -> tuple[int, datetime, dict]:
    """Fetch one block via Bitcoin Core RPC verbosity=3."""
    rpc = _thread_rpc_client()
    block_hash = rpc.getblockhash(height)
    block = rpc.getblock(block_hash, 3)
    block_time = datetime.fromtimestamp(int(block["time"]), tz=timezone.utc)
    return height, block_time, block


def _iter_block_outputs(
    start_block: int, end_block: int, workers: int = 8
) -> Iterator[tuple[int, datetime, dict]]:
    """Yield (block_height, block_time_utc, block_data) in monotonic order.

    Uses a thread pool to overlap RPC latency. Workers fetch eagerly but
    we re-order results so consumers see strictly ascending heights.
    """
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending: dict[int, tuple[int, datetime, dict]] = {}
        futures = {}
        next_submit = start_block
        next_height = start_block

        def submit_until_full() -> None:
            nonlocal next_submit
            max_in_flight = max(1, workers * 2)
            while next_submit <= end_block and len(futures) < max_in_flight:
                futures[pool.submit(_fetch_block_via_rpc, next_submit)] = next_submit
                next_submit += 1

        submit_until_full()
        while futures:
            done, _not_done = wait(futures, return_when=FIRST_COMPLETED)
            for fut in done:
                expected_height = futures.pop(fut)
                try:
                    h, ts, b = fut.result()
                    pending[h] = (h, ts, b)
                except Exception as exc:
                    raise RuntimeError(
                        f"RPC fetch failed for block {expected_height}: {exc}"
                    ) from exc

            while next_height in pending:
                yield pending.pop(next_height)
                next_height += 1
            submit_until_full()

        while pending:
            try:
                yield pending.pop(next_height)
                next_height += 1
            except KeyError as exc:
                raise RuntimeError(f"missing fetched block {next_height}") from exc


def _ilp_sender():
    """Open a QuestDB ILP Sender using the project's existing config."""
    from questdb.ingress import Sender

    host = os.getenv("QUESTDB_ILP_HOST", "localhost")
    port = int(os.getenv("QUESTDB_ILP_PORT", "9009"))
    # Project pattern: TCP without auth on localhost.
    return Sender.from_conf(f"tcp::addr={host}:{port};")


def catchup(start_block: int, end_block: int) -> int:
    """Run the tip catch-up. Returns the count of rows emitted to QuestDB."""
    rows_emitted = 0
    last_log = time.monotonic()
    sender = _ilp_sender()
    try:
        sender.establish()
        for height, block_time, block in _iter_block_outputs(start_block, end_block):
            for tx in block.get("tx", []):
                txid = tx["txid"]
                for vout in tx.get("vout", []):
                    # Filter OP_RETURN — provably unspendable, never appear
                    # in the historical DuckDB mirror either.
                    script_type = (
                        vout.get("scriptPubKey", {}).get("type") or ""
                    ).lower()
                    if script_type in _UNSPENDABLE_SCRIPT_TYPES:
                        continue
                    vout_index = int(vout["n"])
                    btc_value = float(vout["value"])
                    if btc_value <= 0:
                        continue
                    outpoint = f"{txid}:{vout_index}"
                    sender.row(
                        "utxo_lifecycle",
                        symbols={},
                        columns={
                            "outpoint": outpoint,
                            "txid": txid,
                            "vout_index": vout_index,
                            "creation_block": int(height),
                            "btc_value": float(btc_value),
                            "is_spent": False,
                        },
                        at=block_time,
                    )
                    rows_emitted += 1
            # Flush periodically — at 100-block boundaries.
            if height % 100 == 0:
                sender.flush()
                now = time.monotonic()
                if now - last_log >= 30:
                    logger.info(
                        "Catch-up progress: block %d/%d (%.1f%%); rows=%d",
                        height,
                        end_block,
                        100
                        * (height - start_block + 1)
                        / max(1, end_block - start_block + 1),
                        rows_emitted,
                    )
                    last_log = now
        sender.flush()
    finally:
        sender.close()
    return rows_emitted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-block", type=int, default=None)
    parser.add_argument("--end-block", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(
        level=_resolve_log_level(os.getenv("LOG_LEVEL", "INFO")),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    start = args.start_block
    if start is None:
        start = _resolve_questdb_max_creation() + 1
    end = args.end_block
    if end is None:
        end = _resolve_tip()

    if start > end:
        logger.info("Already at tip: max_creation=%d, tip=%d", start - 1, end)
        return 0

    logger.info(
        "Tip catch-up range: blocks %d..%d (%d blocks)",
        start,
        end,
        end - start + 1,
    )
    t0 = time.monotonic()
    rows = catchup(start, end)
    elapsed = time.monotonic() - t0
    logger.info(
        "Tip catch-up complete: %d rows in %.1fs (%.0f rows/s)",
        rows,
        elapsed,
        rows / max(0.001, elapsed),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
