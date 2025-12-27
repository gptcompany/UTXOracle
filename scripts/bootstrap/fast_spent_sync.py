#!/usr/bin/env python3
"""Fast spent UTXO sync using DuckDB staging table.

Two modes:
1. --fast-mode: Skip UTXO key loading, collect ALL inputs, filter during UPDATE
2. Default: Load UTXO keys into memory for pre-filtering (uses more RAM but less disk I/O)

Usage:
    # Fast mode (recommended for large block ranges)
    python -m scripts.bootstrap.fast_spent_sync --start-block 925405 --end-block 929725 --fast-mode

    # Memory mode (for smaller ranges)
    python -m scripts.bootstrap.fast_spent_sync --start-block 929715 --end-block 929725
"""

import argparse

from scripts.config import UTXORACLE_DB_PATH
import http.client
import base64
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BitcoinRPC:
    """Thread-safe Bitcoin Core RPC client (creates new connection per call)."""

    def __init__(self, datadir: str = None):
        datadir = datadir or os.getenv("BITCOIN_DATADIR", "/media/sam/3TB-WDC/Bitcoin")
        cookie_path = Path(datadir) / ".cookie"

        with open(cookie_path) as f:
            cookie = f.read().strip()
        user, pw = cookie.split(":")

        self.auth = base64.b64encode(f"{user}:{pw}".encode()).decode()

    def call(self, method: str, *params):
        """Thread-safe RPC call - creates new connection per request."""
        payload = json.dumps({"method": method, "params": list(params), "id": 1})
        conn = http.client.HTTPConnection("localhost", 8332, timeout=120)
        try:
            conn.request(
                "POST",
                "/",
                payload,
                {
                    "Authorization": f"Basic {self.auth}",
                    "Content-Type": "application/json",
                },
            )
            resp = conn.getresponse()
            data = json.loads(resp.read())
            if data.get("error"):
                raise Exception(data["error"])
            return data["result"]
        finally:
            conn.close()

    def getblockhash(self, height: int) -> str:
        return self.call("getblockhash", height)

    def getblock(self, blockhash: str, verbosity: int = 3) -> dict:
        return self.call("getblock", blockhash, verbosity)


def load_utxo_keys(db_path: str) -> set:
    """Load all unspent UTXO keys into memory for O(1) lookup.

    Returns:
        Set of (txid, vout) tuples
    """
    logger.info("Loading UTXO keys into memory...")
    start = time.time()

    conn = duckdb.connect(db_path, read_only=True)

    # Count first
    count = conn.execute(
        "SELECT COUNT(*) FROM utxo_lifecycle WHERE is_spent = FALSE OR is_spent IS NULL"
    ).fetchone()[0]
    logger.info(f"  Loading {count:,} unspent UTXOs...")

    # Load in batches to show progress
    utxo_keys = set()
    batch_size = 10_000_000
    offset = 0

    while True:
        result = conn.execute(f"""
            SELECT txid, vout FROM utxo_lifecycle
            WHERE is_spent = FALSE OR is_spent IS NULL
            LIMIT {batch_size} OFFSET {offset}
        """).fetchall()

        if not result:
            break

        for row in result:
            utxo_keys.add((row[0], row[1]))

        offset += len(result)
        logger.info(
            f"  Loaded {len(utxo_keys):,} / {count:,} ({100 * len(utxo_keys) / count:.1f}%)"
        )

    conn.close()

    elapsed = time.time() - start
    logger.info(f"Loaded {len(utxo_keys):,} UTXO keys in {elapsed:.1f}s")

    return utxo_keys


def process_blocks(
    rpc: BitcoinRPC,
    start_block: int,
    end_block: int,
    utxo_keys: set,
    workers: int = 10,
) -> list:
    """Process blocks and collect spent UTXOs (memory mode with pre-filtering).

    Returns:
        List of (txid, vout, spent_block, spent_timestamp) tuples
    """
    logger.info(f"Processing blocks {start_block} to {end_block}...")

    spent_utxos = []
    heights = list(range(start_block, end_block + 1))
    total_blocks = len(heights)

    def fetch_block(height: int):
        try:
            block_hash = rpc.getblockhash(height)
            return rpc.getblock(block_hash, 3)
        except Exception as e:
            logger.error(f"Error fetching block {height}: {e}")
            return None

    start_time = time.time()
    processed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for i in range(0, len(heights), workers * 2):
            chunk = heights[i : i + workers * 2]
            blocks = list(executor.map(fetch_block, chunk))

            for block_data in blocks:
                if not block_data:
                    continue

                block_height = block_data["height"]
                block_time = block_data["time"]

                for tx in block_data.get("tx", []):
                    for vin in tx.get("vin", []):
                        if "coinbase" in vin:
                            continue

                        spent_txid = vin.get("txid", "")
                        spent_vout = vin.get("vout", 0)

                        if spent_txid and (spent_txid, spent_vout) in utxo_keys:
                            spent_utxos.append(
                                (
                                    spent_txid,
                                    spent_vout,
                                    block_height,
                                    block_time,
                                )
                            )

                processed += 1

            # Progress every 100 blocks
            if processed % 100 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = total_blocks - processed
                eta = remaining / rate if rate > 0 else 0
                logger.info(
                    f"Block {block_height}: {processed}/{total_blocks} "
                    f"({100 * processed / total_blocks:.1f}%), "
                    f"spent={len(spent_utxos):,}, "
                    f"{rate:.1f} blk/s, ETA: {eta / 60:.1f}m"
                )

    logger.info(f"Found {len(spent_utxos):,} spent UTXOs in {total_blocks} blocks")
    return spent_utxos


def process_blocks_fast(
    rpc: BitcoinRPC,
    start_block: int,
    end_block: int,
    workers: int = 10,
) -> list:
    """Process blocks collecting ALL inputs (fast mode - no pre-filtering).

    Collects all transaction inputs without checking if they exist in our UTXO set.
    The filtering happens during the UPDATE phase via SQL JOIN.

    Returns:
        List of (txid, vout, spent_block, spent_timestamp) tuples
    """
    logger.info(f"[FAST MODE] Processing blocks {start_block} to {end_block}...")

    all_inputs = []
    heights = list(range(start_block, end_block + 1))
    total_blocks = len(heights)

    def fetch_block(height: int):
        try:
            block_hash = rpc.getblockhash(height)
            return rpc.getblock(block_hash, 3)
        except Exception as e:
            logger.error(f"Error fetching block {height}: {e}")
            return None

    start_time = time.time()
    processed = 0
    last_height = start_block

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for i in range(0, len(heights), workers * 2):
            chunk = heights[i : i + workers * 2]
            blocks = list(executor.map(fetch_block, chunk))

            for block_data in blocks:
                if not block_data:
                    continue

                block_height = block_data["height"]
                block_time = block_data["time"]
                last_height = block_height

                for tx in block_data.get("tx", []):
                    for vin in tx.get("vin", []):
                        if "coinbase" in vin:
                            continue

                        spent_txid = vin.get("txid", "")
                        spent_vout = vin.get("vout", 0)

                        if spent_txid:
                            all_inputs.append(
                                (
                                    spent_txid,
                                    spent_vout,
                                    block_height,
                                    block_time,
                                )
                            )

                processed += 1

            # Progress every 100 blocks
            if processed % 100 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = total_blocks - processed
                eta = remaining / rate if rate > 0 else 0
                logger.info(
                    f"Block {last_height}: {processed}/{total_blocks} "
                    f"({100 * processed / total_blocks:.1f}%), "
                    f"inputs={len(all_inputs):,}, "
                    f"{rate:.1f} blk/s, ETA: {eta / 60:.1f}m"
                )

    elapsed = time.time() - start_time
    logger.info(
        f"Collected {len(all_inputs):,} inputs from {processed} blocks in {elapsed:.1f}s"
    )
    return all_inputs


def bulk_update_spent(db_path: str, spent_utxos: list) -> int:
    """Bulk update spent UTXOs using staging table pattern.

    Returns:
        Number of rows updated
    """
    if not spent_utxos:
        return 0

    logger.info(f"Bulk updating {len(spent_utxos):,} spent UTXOs...")
    start = time.time()

    conn = duckdb.connect(db_path)

    # Create staging table
    conn.execute("""
        CREATE TEMP TABLE spent_staging (
            txid VARCHAR,
            vout INTEGER,
            spent_block INTEGER,
            spent_timestamp BIGINT
        )
    """)

    # Insert all spent UTXOs into staging (in batches)
    batch_size = 100_000
    for i in range(0, len(spent_utxos), batch_size):
        batch = spent_utxos[i : i + batch_size]
        conn.executemany(
            "INSERT INTO spent_staging VALUES (?, ?, ?, ?)",
            batch,
        )
        logger.info(
            f"  Staged {min(i + batch_size, len(spent_utxos)):,} / {len(spent_utxos):,}"
        )

    # Single bulk UPDATE
    logger.info("Executing bulk UPDATE...")
    result = conn.execute("""
        UPDATE utxo_lifecycle
        SET is_spent = TRUE,
            spent_block = s.spent_block,
            spent_timestamp = s.spent_timestamp
        FROM spent_staging s
        WHERE utxo_lifecycle.txid = s.txid
          AND utxo_lifecycle.vout = s.vout
    """)

    # Get count of updated rows
    updated = conn.execute(
        "SELECT COUNT(*) FROM utxo_lifecycle WHERE is_spent = TRUE"
    ).fetchone()[0]

    conn.close()

    elapsed = time.time() - start
    logger.info(f"Updated {updated:,} rows in {elapsed:.1f}s")

    return updated


def main():
    parser = argparse.ArgumentParser(description="Fast spent UTXO sync")
    parser.add_argument("--start-block", type=int, required=True)
    parser.add_argument("--end-block", type=int, required=True)
    parser.add_argument("--db-path", default=str(UTXORACLE_DB_PATH))
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument(
        "--fast-mode",
        action="store_true",
        help="Skip UTXO key loading, collect all inputs, filter during UPDATE (faster for large ranges)",
    )
    args = parser.parse_args()

    total_start = time.time()
    rpc = BitcoinRPC()

    if args.fast_mode:
        # Fast mode: Collect ALL inputs, filter during UPDATE
        logger.info("=== FAST MODE: Skipping UTXO key loading ===")
        all_inputs = process_blocks_fast(
            rpc, args.start_block, args.end_block, args.workers
        )
        updated = bulk_update_spent(args.db_path, all_inputs)
    else:
        # Memory mode: Pre-filter using in-memory UTXO keys
        logger.info("=== MEMORY MODE: Loading UTXO keys for pre-filtering ===")
        utxo_keys = load_utxo_keys(args.db_path)
        spent_utxos = process_blocks(
            rpc, args.start_block, args.end_block, utxo_keys, args.workers
        )
        del utxo_keys  # Free memory before bulk update
        updated = bulk_update_spent(args.db_path, spent_utxos)

    total_elapsed = time.time() - total_start
    logger.info(
        f"=== COMPLETE: {updated:,} UTXOs marked spent in {total_elapsed / 60:.1f} minutes ==="
    )


if __name__ == "__main__":
    main()
