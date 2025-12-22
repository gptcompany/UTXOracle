#!/usr/bin/env python3
"""Combined Bootstrap: Address Clustering + Spent UTXO Sync (spec-013).

This script efficiently processes the blockchain in a SINGLE PASS to:
1. Extract multi-input clustering data (addresses that spend together)
2. Mark UTXOs as spent with spent_block, spent_timestamp, spent_price_usd

This is ~50% faster than running both operations separately since they
both require the same RPC v3 block data.

Architecture:
- Uses Bitcoin Core RPC verbosity=3 for efficient prevout data
- Multi-input heuristic: addresses spending together belong to same entity
- Parallel block fetching, sequential UnionFind operations (not thread-safe)
- BULK staging table for spent UTXO updates (DuckDB OLAP optimization)

Performance Optimization:
- DuckDB is OLAP-optimized: bulk INSERT + UPDATE FROM staging is fast
- Individual UPDATE queries are slow (full table scan per update)
- We collect spent UTXOs in batches and apply them with staging table

Usage:
    # Full bootstrap from genesis
    python -m scripts.bootstrap.run_combined_bootstrap --start-block 0

    # Resume from checkpoint
    python -m scripts.bootstrap.run_combined_bootstrap --resume

    # Custom range with more workers
    python -m scripts.bootstrap.run_combined_bootstrap --start-block 800000 --end-block 850000 --workers 8

Performance:
    - ~800-1000 blocks/minute with rpc-v3 (10 workers)
    - Full blockchain (928k blocks): ~15 hours (vs 30h for separate runs)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.clustering.union_find import UnionFind
from scripts.clustering.address_clustering import cluster_addresses

# Load environment
load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Database paths
UTXO_DB_PATH = os.getenv("UTXO_DB_PATH", "data/utxo_lifecycle.duckdb")
CACHE_DB_PATH = os.getenv("DUCKDB_PATH", "data/utxoracle_cache.db")

# Batch size for staging table operations
SPENT_BATCH_SIZE = 10000


class BitcoinRPC:
    """Pure Python Bitcoin Core RPC client with cookie auth."""

    def __init__(self):
        import http.client
        import base64
        import json as json_module

        self._http = http.client
        self._base64 = base64
        self._json = json_module

        rpc_url = os.getenv("BITCOIN_RPC_URL", "http://127.0.0.1:8332")
        self.rpc_user = os.getenv("BITCOIN_RPC_USER", "")
        self.rpc_pass = os.getenv("BITCOIN_RPC_PASSWORD", "")

        # Parse host/port
        url_parts = rpc_url.replace("http://", "").replace("https://", "")
        if ":" in url_parts:
            self.host, port_str = url_parts.split(":")
            self.port = int(port_str)
        else:
            self.host = url_parts
            self.port = 8332

        # Fallback to cookie auth
        if not self.rpc_user or not self.rpc_pass:
            datadir = os.getenv("BITCOIN_DATADIR", os.path.expanduser("~/.bitcoin"))
            cookie_path = Path(datadir) / ".cookie"
            if cookie_path.exists():
                cookie = cookie_path.read_text().strip()
                self.rpc_user, self.rpc_pass = cookie.split(":", 1)
            else:
                raise RuntimeError(
                    f"No RPC credentials and cookie not found at {cookie_path}"
                )

    def _call(self, method: str, *params) -> Any:
        payload = self._json.dumps(
            {
                "jsonrpc": "1.0",
                "id": "bootstrap",
                "method": method,
                "params": list(params),
            }
        )

        auth = self._base64.b64encode(
            f"{self.rpc_user}:{self.rpc_pass}".encode()
        ).decode()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}",
        }

        conn = self._http.HTTPConnection(self.host, self.port, timeout=120)
        try:
            conn.request("POST", "/", payload, headers)
            response = conn.getresponse()

            if response.status != 200:
                raise Exception(f"RPC error: HTTP {response.status} {response.reason}")

            data = self._json.loads(response.read())
            if data.get("error"):
                raise Exception(f"RPC error: {data['error']}")

            return data["result"]
        finally:
            conn.close()

    def getblockcount(self) -> int:
        return self._call("getblockcount")

    def getblockhash(self, height: int) -> str:
        return self._call("getblockhash", height)

    def getblock(self, blockhash: str, verbosity: int = 3) -> dict:
        return self._call("getblock", blockhash, verbosity)


def get_price_for_block(
    cache_conn: duckdb.DuckDBPyConnection, block_height: int
) -> float:
    """Get BTC price for a block from price table.

    Falls back to approximation if exact block not found.
    """
    try:
        # Try exact block match first
        result = cache_conn.execute(
            "SELECT price_usd FROM block_prices WHERE block_height = ?",
            [block_height],
        ).fetchone()
        if result:
            return result[0]

        # Fallback: find closest block
        result = cache_conn.execute(
            """
            SELECT price_usd FROM block_prices
            WHERE block_height <= ?
            ORDER BY block_height DESC
            LIMIT 1
            """,
            [block_height],
        ).fetchone()
        if result:
            return result[0]

    except Exception:
        pass

    # Default fallback for early blocks
    return 0.0


def extract_block_data(
    block_data: dict,
    uf: UnionFind,
    block_price: float,
) -> tuple[dict, list[tuple]]:
    """Extract clustering and spent UTXO data from a block.

    Args:
        block_data: Block data from RPC v3
        uf: UnionFind structure for clustering
        block_price: BTC/USD price for this block

    Returns:
        Tuple of (stats dict, list of spent UTXO tuples)
    """
    block_height = block_data["height"]
    block_time = block_data["time"]

    stats = {
        "txs_clustered": 0,
        "addresses_clustered": 0,
        "utxos_to_mark": 0,
    }

    spent_utxos = []

    for tx in block_data.get("tx", []):
        input_addresses = []

        for vin in tx.get("vin", []):
            # Skip coinbase inputs
            if "coinbase" in vin:
                continue

            spent_txid = vin.get("txid", "")
            spent_vout = vin.get("vout", 0)

            # Get prevout address for clustering
            prevout = vin.get("prevout", {})
            spk = prevout.get("scriptPubKey", {})
            addr = spk.get("address")

            if addr:
                input_addresses.append(addr)

            # Collect spent UTXO data
            if spent_txid:
                spent_utxos.append(
                    (
                        spent_txid,
                        spent_vout,
                        block_height,
                        block_time,
                        block_price,
                    )
                )
                stats["utxos_to_mark"] += 1

        # Cluster addresses with 2+ inputs
        if len(input_addresses) >= 2:
            cluster_addresses(uf, input_addresses)
            stats["txs_clustered"] += 1
            stats["addresses_clustered"] += len(input_addresses)

    return stats, spent_utxos


def apply_spent_batch(
    conn: duckdb.DuckDBPyConnection,
    spent_batch: list[tuple],
) -> int:
    """Apply spent UTXO updates using staging table pattern.

    This is MUCH faster than individual UPDATEs for DuckDB.

    Args:
        conn: DuckDB connection
        spent_batch: List of (txid, vout, spent_block, spent_time, spent_price)

    Returns:
        Number of UTXOs actually updated
    """
    if not spent_batch:
        return 0

    # Create staging table
    conn.execute("""
        CREATE TEMP TABLE IF NOT EXISTS spent_staging (
            txid VARCHAR,
            vout INTEGER,
            spent_block INTEGER,
            spent_timestamp BIGINT,
            spent_price_usd DOUBLE
        )
    """)

    # Clear and populate staging table
    conn.execute("DELETE FROM spent_staging")
    conn.executemany(
        "INSERT INTO spent_staging VALUES (?, ?, ?, ?, ?)",
        spent_batch,
    )

    # Bulk UPDATE using staging table
    conn.execute("""
        UPDATE utxo_lifecycle
        SET is_spent = TRUE,
            spent_block = s.spent_block,
            spent_timestamp = s.spent_timestamp,
            spent_price_usd = s.spent_price_usd
        FROM spent_staging s
        WHERE utxo_lifecycle.txid = s.txid
          AND utxo_lifecycle.vout = s.vout
          AND (utxo_lifecycle.is_spent = FALSE OR utxo_lifecycle.is_spent IS NULL)
    """)

    # Note: DuckDB rowcount returns -1 for UPDATE statements
    # Return batch size as approximation (actual count may differ due to WHERE clause)
    return len(spent_batch)


def get_combined_sync_state(conn: duckdb.DuckDBPyConnection) -> dict | None:
    """Get combined sync state from database."""
    try:
        result = conn.execute("""
            SELECT last_block, total_clustered, total_spent, last_sync_time
            FROM combined_sync_state
            ORDER BY last_sync_time DESC
            LIMIT 1
        """).fetchone()

        if result:
            return {
                "last_block": result[0],
                "total_clustered": result[1],
                "total_spent": result[2],
                "last_sync_time": result[3],
            }
    except Exception:
        pass
    return None


def update_combined_sync_state(
    conn: duckdb.DuckDBPyConnection,
    last_block: int,
    total_clustered: int,
    total_spent: int,
) -> None:
    """Update combined sync state in database."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS combined_sync_state (
            last_block INTEGER,
            total_clustered INTEGER,
            total_spent INTEGER,
            last_sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "INSERT INTO combined_sync_state (last_block, total_clustered, total_spent) VALUES (?, ?, ?)",
        [last_block, total_clustered, total_spent],
    )


def save_clusters_to_db(
    uf: UnionFind,
    conn: duckdb.DuckDBPyConnection,
    batch_size: int = 100000,
) -> int:
    """Save all clusters to database efficiently."""
    clusters = uf.get_clusters()
    if not clusters:
        return 0

    now = datetime.now()
    count = 0
    batch = []

    for cluster_set in clusters:
        cluster_id = uf.find(next(iter(cluster_set)))

        for address in cluster_set:
            batch.append((address, cluster_id, now, now))

            if len(batch) >= batch_size:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO address_clusters
                    (address, cluster_id, first_seen, last_seen)
                    VALUES (?, ?, ?, ?)
                    """,
                    batch,
                )
                count += len(batch)
                batch = []

    # Insert remaining
    if batch:
        conn.executemany(
            """
            INSERT OR REPLACE INTO address_clusters
            (address, cluster_id, first_seen, last_seen)
            VALUES (?, ?, ?, ?)
            """,
            batch,
        )
        count += len(batch)

    return count


def run_combined_bootstrap(
    start_block: int,
    end_block: int,
    utxo_db_path: str,
    cache_db_path: str,
    workers: int = 10,
    checkpoint_interval: int = 1000,
) -> dict:
    """Run combined address clustering + spent UTXO sync.

    Args:
        start_block: First block to process
        end_block: Last block to process (inclusive)
        utxo_db_path: Path to UTXO lifecycle DuckDB database
        cache_db_path: Path to cache DB with block prices
        workers: Number of parallel block fetches
        checkpoint_interval: Save checkpoint every N blocks

    Returns:
        Statistics dict
    """
    stats = {
        "start_time": time.time(),
        "blocks_processed": 0,
        "txs_clustered": 0,
        "addresses_clustered": 0,
        "utxos_spent": 0,
        "start_block": start_block,
        "end_block": end_block,
    }

    rpc = BitcoinRPC()
    utxo_conn = duckdb.connect(utxo_db_path)
    cache_conn = duckdb.connect(cache_db_path, read_only=True)
    uf = UnionFind()

    logger.info(f"Starting combined bootstrap: blocks {start_block}-{end_block}")
    logger.info(f"  UTXO DB: {utxo_db_path}")
    logger.info(f"  Cache DB: {cache_db_path}")
    logger.info(f"  Workers: {workers}")
    logger.info(f"  Spent batch size: {SPENT_BATCH_SIZE}")

    # Accumulated spent UTXOs for batch processing
    spent_batch = []

    # Process blocks in chunks
    chunk_size = workers * 2
    heights = list(range(start_block, end_block + 1))

    def fetch_block(height: int) -> tuple[int, dict]:
        try:
            block_hash = rpc.getblockhash(height)
            block_data = rpc.getblock(block_hash, 3)
            return height, block_data
        except Exception as e:
            logger.error(f"Error fetching block {height}: {e}")
            return height, {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for chunk_start in range(0, len(heights), chunk_size):
            chunk_heights = heights[chunk_start : chunk_start + chunk_size]

            # Fetch blocks in parallel
            results = list(executor.map(fetch_block, chunk_heights))

            # Process results sequentially (UnionFind not thread-safe)
            for height, block_data in sorted(results, key=lambda x: x[0]):
                if not block_data:
                    continue

                block_price = get_price_for_block(cache_conn, height)

                block_stats, block_spent = extract_block_data(
                    block_data, uf, block_price
                )

                stats["blocks_processed"] += 1
                stats["txs_clustered"] += block_stats["txs_clustered"]
                stats["addresses_clustered"] += block_stats["addresses_clustered"]

                # Accumulate spent UTXOs
                spent_batch.extend(block_spent)

                # Apply batch when threshold reached
                if len(spent_batch) >= SPENT_BATCH_SIZE:
                    updated = apply_spent_batch(utxo_conn, spent_batch)
                    stats["utxos_spent"] += updated
                    spent_batch = []

            # Progress logging
            current_block = chunk_heights[-1]
            if stats["blocks_processed"] % 100 == 0:
                elapsed = time.time() - stats["start_time"]
                blocks_per_sec = (
                    stats["blocks_processed"] / elapsed if elapsed > 0 else 0
                )
                blocks_remaining = end_block - current_block
                eta_seconds = (
                    blocks_remaining / blocks_per_sec if blocks_per_sec > 0 else 0
                )
                logger.info(
                    f"Block {current_block:,}: "
                    f"clustered={stats['txs_clustered']:,} txs, "
                    f"spent={stats['utxos_spent']:,} UTXOs, "
                    f"{blocks_per_sec:.1f} blk/s, "
                    f"ETA: {eta_seconds / 3600:.1f}h"
                )

            # Checkpoint
            if stats["blocks_processed"] % checkpoint_interval == 0:
                # Flush remaining spent batch
                if spent_batch:
                    updated = apply_spent_batch(utxo_conn, spent_batch)
                    stats["utxos_spent"] += updated
                    spent_batch = []

                update_combined_sync_state(
                    utxo_conn,
                    current_block,
                    stats["addresses_clustered"],
                    stats["utxos_spent"],
                )
                logger.info(f"Checkpoint saved at block {current_block}")

    # Final batch flush
    if spent_batch:
        updated = apply_spent_batch(utxo_conn, spent_batch)
        stats["utxos_spent"] += updated

    # Final save of clusters
    logger.info("Saving clusters to database...")
    saved = save_clusters_to_db(uf, utxo_conn)
    logger.info(f"Saved {saved:,} address-cluster mappings")

    update_combined_sync_state(
        utxo_conn, end_block, stats["addresses_clustered"], stats["utxos_spent"]
    )

    cache_conn.close()
    utxo_conn.close()

    stats["duration_seconds"] = time.time() - stats["start_time"]
    stats["clusters_created"] = len(uf.get_clusters())

    return stats


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Combined bootstrap: clustering + spent UTXO sync (spec-013)"
    )
    parser.add_argument(
        "--start-block",
        type=int,
        help="First block to process",
    )
    parser.add_argument(
        "--end-block",
        type=int,
        help="Last block to process (default: chain tip)",
    )
    parser.add_argument(
        "--utxo-db-path",
        default=UTXO_DB_PATH,
        help=f"Path to UTXO lifecycle database (default: {UTXO_DB_PATH})",
    )
    parser.add_argument(
        "--cache-db-path",
        default=CACHE_DB_PATH,
        help=f"Path to cache database with prices (default: {CACHE_DB_PATH})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Number of parallel block fetches (default: 10)",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=1000,
        help="Save checkpoint every N blocks (default: 1000)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Connect to database
    utxo_conn = duckdb.connect(args.utxo_db_path)

    # Determine start block
    if args.resume:
        state = get_combined_sync_state(utxo_conn)
        if state:
            args.start_block = state["last_block"] + 1
            logger.info(f"Resuming from block {args.start_block}")
        else:
            logger.error("No sync state found. Use --start-block instead.")
            return 1

    if args.start_block is None:
        args.start_block = 0
        logger.info("Starting from block 0 (genesis)")

    # Determine end block
    if args.end_block is None:
        rpc = BitcoinRPC()
        args.end_block = rpc.getblockcount()

    utxo_conn.close()

    if args.start_block > args.end_block:
        logger.info("Already at chain tip")
        return 0

    # Run combined bootstrap
    stats = run_combined_bootstrap(
        start_block=args.start_block,
        end_block=args.end_block,
        utxo_db_path=args.utxo_db_path,
        cache_db_path=args.cache_db_path,
        workers=args.workers,
        checkpoint_interval=args.checkpoint_interval,
    )

    print("\n" + "=" * 70)
    print("COMBINED BOOTSTRAP COMPLETE")
    print("=" * 70)
    print(f"  Blocks: {stats['start_block']:,} - {stats['end_block']:,}")
    print(f"  Processed: {stats['blocks_processed']:,} blocks")
    print(f"  Transactions clustered: {stats['txs_clustered']:,}")
    print(f"  Addresses clustered: {stats['addresses_clustered']:,}")
    print(f"  Clusters created: {stats['clusters_created']:,}")
    print(f"  UTXOs marked spent: {stats['utxos_spent']:,}")
    print(
        f"  Duration: {stats['duration_seconds']:.1f}s ({stats['duration_seconds'] / 3600:.2f}h)"
    )
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
