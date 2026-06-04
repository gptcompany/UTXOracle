#!/usr/bin/env python3
"""Build QuestDB block_heights from Bitcoin Core RPC.

Production replacement for ``build_block_heights.py``. This module never
opens DuckDB: it reads the current QuestDB max(height), walks Bitcoin Core
RPC, and streams height -> timestamp rows to QuestDB via ILP.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Iterator

from api.questdb_repository import _open_pg_sync

logger = logging.getLogger(__name__)
_THREAD_STATE = threading.local()


def _resolve_log_level(raw_level: str | None) -> int:
    if (
        not raw_level
        or raw_level.startswith("ENC[")
        or raw_level.startswith("encrypted:")
    ):
        return logging.INFO
    level = getattr(logging, raw_level.upper(), None)
    return level if isinstance(level, int) else logging.INFO


def _open_sender():
    from questdb.ingress import Sender

    host = os.getenv("QUESTDB_ILP_HOST", "localhost")
    port = int(os.getenv("QUESTDB_ILP_PORT", "9009"))
    return Sender.from_conf(f"tcp::addr={host}:{port};")


def _thread_rpc_client():
    rpc = getattr(_THREAD_STATE, "rpc", None)
    if rpc is None:
        from scripts.sync_utxo_lifecycle import BitcoinRPC

        rpc = BitcoinRPC()
        _THREAD_STATE.rpc = rpc
    return rpc


def resolve_tip() -> int:
    """Resolve Bitcoin Core tip using bitcoin-cli, then Python RPC fallback."""
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
        logger.warning("bitcoin-cli getblockcount failed (%s); using Python RPC", exc)
        return int(_thread_rpc_client().getblockcount())


def resolve_questdb_start_block() -> int:
    """Return max(height)+1 from QuestDB block_heights, or 0 for an empty table."""
    with _open_pg_sync() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT max(height) FROM block_heights")
            row = cur.fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0]) + 1


def _fetch_block_timestamp(height: int) -> tuple[int, datetime]:
    rpc = _thread_rpc_client()
    block_hash = rpc.getblockhash(height)
    block = rpc.getblock(block_hash, 1)
    block_time = datetime.fromtimestamp(int(block["time"]), tz=timezone.utc)
    return height, block_time


def iter_block_timestamps(
    start_block: int,
    end_block: int,
    workers: int,
) -> Iterator[tuple[int, datetime]]:
    """Fetch block timestamps concurrently and yield them by ascending height."""
    if end_block < start_block:
        return

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        pending: dict[int, datetime] = {}
        futures = {}
        next_submit = start_block
        next_height = start_block

        def submit_until_full() -> None:
            nonlocal next_submit
            max_in_flight = max(1, workers * 2)
            while next_submit <= end_block and len(futures) < max_in_flight:
                futures[pool.submit(_fetch_block_timestamp, next_submit)] = next_submit
                next_submit += 1

        submit_until_full()
        while futures:
            done, _not_done = wait(futures, return_when=FIRST_COMPLETED)
            for fut in done:
                expected = futures.pop(fut)
                try:
                    height, block_time = fut.result()
                except Exception as exc:
                    raise RuntimeError(
                        f"RPC fetch failed for block {expected}: {exc}"
                    ) from exc
                pending[height] = block_time

            while next_height in pending:
                yield next_height, pending.pop(next_height)
                next_height += 1
            submit_until_full()

        while pending:
            if next_height not in pending:
                raise RuntimeError(f"missing fetched block {next_height}")
            yield next_height, pending.pop(next_height)
            next_height += 1


def build_block_heights(
    start_block: int,
    end_block: int,
    workers: int,
) -> int:
    """Stream block height records to QuestDB. Returns emitted row count."""
    if end_block < start_block:
        logger.info("Already at tip: start=%d end=%d", start_block, end_block)
        return 0

    sender = _open_sender()
    rows = 0
    last_log = time.monotonic()
    fetched_at = datetime.now(timezone.utc)

    try:
        sender.establish()
        for height, block_time in iter_block_timestamps(start_block, end_block, workers):
            sender.row(
                "block_heights",
                symbols={},
                columns={
                    "height": int(height),
                    "fetched_at": fetched_at,
                },
                at=block_time,
            )
            rows += 1

            if rows % 1000 == 0:
                sender.flush()
            now = time.monotonic()
            if now - last_log >= 30:
                logger.info(
                    "block_heights progress: height=%d/%d rows=%d",
                    height,
                    end_block,
                    rows,
                )
                last_log = now
        sender.flush()
    finally:
        try:
            sender.close()
        except Exception:
            pass

    logger.info("Inserted %d block_heights rows into QuestDB", rows)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-block", type=int, default=None)
    parser.add_argument("--end-block", type=int, default=None)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else _resolve_log_level(os.getenv("LOG_LEVEL")),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    start_block = (
        int(args.start_block)
        if args.start_block is not None
        else resolve_questdb_start_block()
    )
    end_block = int(args.end_block) if args.end_block is not None else resolve_tip()
    build_block_heights(start_block, end_block, max(1, args.workers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
