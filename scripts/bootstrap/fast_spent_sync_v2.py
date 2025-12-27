#!/usr/bin/env python3
"""Ultra-fast spent UTXO sync using CSV COPY pattern (v2).

Key optimizations over v1:
1. Write inputs to CSV file (fast streaming write)
2. Use DuckDB COPY FROM for bulk staging (10-100x faster than executemany)
3. Single bulk UPDATE with hash index on staging table

Performance target: ~20 minutes for 30 days (4320 blocks)

Usage:
    BITCOIN_DATADIR=/media/sam/3TB-WDC/Bitcoin PYTHONPATH=/media/sam/1TB/UTXOracle \
    uv run python -m scripts.bootstrap.fast_spent_sync_v2 \
        --start-block 925405 --end-block 929725
"""

import argparse

from scripts.config import UTXORACLE_DB_PATH
import base64
import csv
import http.client
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

# Temp directory for CSV staging
TEMP_DIR = Path("/media/sam/1TB/UTXOracle/data/temp")


class BitcoinRPC:
    """Thread-safe Bitcoin Core RPC client."""

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


def process_blocks_to_csv(
    rpc: BitcoinRPC,
    start_block: int,
    end_block: int,
    csv_path: Path,
    workers: int = 10,
) -> int:
    """Process blocks and write inputs directly to CSV.

    Returns:
        Number of inputs written
    """
    logger.info(f"Processing blocks {start_block} to {end_block} -> {csv_path}")

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
    total_inputs = 0
    last_height = start_block

    # Open CSV for streaming write
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)

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
                                writer.writerow(
                                    [spent_txid, spent_vout, block_height, block_time]
                                )
                                total_inputs += 1

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
                        f"inputs={total_inputs:,}, "
                        f"{rate:.1f} blk/s, ETA: {eta / 60:.1f}m"
                    )

    elapsed = time.time() - start_time
    csv_size_mb = csv_path.stat().st_size / (1024 * 1024)
    logger.info(
        f"Wrote {total_inputs:,} inputs from {processed} blocks "
        f"to {csv_size_mb:.1f}MB CSV in {elapsed:.1f}s"
    )
    return total_inputs


def bulk_update_from_csv(db_path: str, csv_path: Path) -> int:
    """Bulk update spent UTXOs using CSV COPY + staging table.

    Returns:
        Number of rows updated
    """
    logger.info(f"Bulk updating from {csv_path}...")
    start = time.time()

    conn = duckdb.connect(db_path)

    # Create persistent staging table (temp tables can't use COPY FROM in some versions)
    conn.execute("DROP TABLE IF EXISTS spent_staging_v2")
    conn.execute("""
        CREATE TABLE spent_staging_v2 (
            txid VARCHAR,
            vout INTEGER,
            spent_block INTEGER,
            spent_timestamp BIGINT
        )
    """)

    # Bulk COPY from CSV (MUCH faster than executemany)
    logger.info("Loading CSV into staging table via COPY...")
    copy_start = time.time()
    conn.execute(f"""
        COPY spent_staging_v2 FROM '{csv_path}'
        (FORMAT CSV, HEADER FALSE)
    """)
    copy_elapsed = time.time() - copy_start

    staging_count = conn.execute("SELECT COUNT(*) FROM spent_staging_v2").fetchone()[0]
    logger.info(f"Staged {staging_count:,} rows in {copy_elapsed:.1f}s")

    # Create index on staging for faster JOIN
    logger.info("Creating index on staging table...")
    idx_start = time.time()
    conn.execute("CREATE INDEX idx_staging_txid_vout ON spent_staging_v2 (txid, vout)")
    idx_elapsed = time.time() - idx_start
    logger.info(f"Index created in {idx_elapsed:.1f}s")

    # Single bulk UPDATE
    logger.info("Executing bulk UPDATE...")
    update_start = time.time()
    conn.execute("""
        UPDATE utxo_lifecycle
        SET is_spent = TRUE,
            spent_block = s.spent_block,
            spent_timestamp = s.spent_timestamp
        FROM spent_staging_v2 s
        WHERE utxo_lifecycle.txid = s.txid
          AND utxo_lifecycle.vout = s.vout
    """)
    update_elapsed = time.time() - update_start
    logger.info(f"UPDATE completed in {update_elapsed:.1f}s")

    # Get count of updated rows
    updated = conn.execute(
        "SELECT COUNT(*) FROM utxo_lifecycle WHERE is_spent = TRUE"
    ).fetchone()[0]

    # Cleanup staging table
    conn.execute("DROP TABLE spent_staging_v2")

    conn.close()

    elapsed = time.time() - start
    logger.info(f"Total: {updated:,} spent UTXOs in {elapsed:.1f}s")

    return updated


def main():
    parser = argparse.ArgumentParser(description="Ultra-fast spent UTXO sync (v2)")
    parser.add_argument("--start-block", type=int, required=True)
    parser.add_argument("--end-block", type=int, required=True)
    parser.add_argument("--db-path", default=str(UTXORACLE_DB_PATH))
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    total_start = time.time()
    rpc = BitcoinRPC()

    # Ensure temp directory exists
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = TEMP_DIR / f"spent_inputs_{args.start_block}_{args.end_block}.csv"

    # Phase 1: Process blocks and write to CSV
    logger.info("=== PHASE 1: Collecting inputs to CSV ===")
    total_inputs = process_blocks_to_csv(
        rpc, args.start_block, args.end_block, csv_path, args.workers
    )

    if total_inputs == 0:
        logger.info("No inputs found, nothing to update")
        return

    # Phase 2: Bulk update from CSV
    logger.info("=== PHASE 2: Bulk UPDATE from CSV ===")
    updated = bulk_update_from_csv(args.db_path, csv_path)

    # Cleanup CSV
    if csv_path.exists():
        csv_path.unlink()
        logger.info("Cleaned up temp CSV")

    total_elapsed = time.time() - total_start
    logger.info(
        f"=== COMPLETE: {updated:,} UTXOs marked spent in {total_elapsed / 60:.1f} minutes ==="
    )


if __name__ == "__main__":
    main()
