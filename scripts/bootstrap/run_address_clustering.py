#!/usr/bin/env python3
"""Bootstrap Script: Run Address Clustering on Historical Blockchain.

This script scans blocks to extract transaction input addresses and runs
the multi-input clustering heuristic to group addresses by entity/wallet.

Architecture (spec-013):
- Uses Bitcoin Core RPC verbosity=3 for efficient prevout data
- Applies multi-input heuristic: addresses that spend together belong to same entity
- Updates address_clusters table with cluster assignments

Usage:
    python -m scripts.bootstrap.run_address_clustering --start-block 0 --end-block 928000
    python -m scripts.bootstrap.run_address_clustering --resume

Performance:
    - ~1000 blocks/minute with rpc-v3
    - Full blockchain (928k blocks): ~15 hours
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
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
UTXO_DB_PATH = os.getenv("UTXO_LIFECYCLE_DB_PATH", "data/utxo_lifecycle.duckdb")


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
                "id": "clustering",
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


def extract_input_addresses_from_block(block_data: dict) -> list[list[str]]:
    """Extract input address groups from block transactions.

    Returns list of address lists, where each inner list contains
    all input addresses for a single transaction.
    """
    tx_input_groups = []

    for tx in block_data.get("tx", []):
        input_addresses = []

        for vin in tx.get("vin", []):
            # Skip coinbase inputs
            if "coinbase" in vin:
                continue

            prevout = vin.get("prevout", {})
            spk = prevout.get("scriptPubKey", {})
            addr = spk.get("address")

            if addr:
                input_addresses.append(addr)

        # Only include transactions with 2+ inputs (clustering opportunity)
        if len(input_addresses) >= 2:
            tx_input_groups.append(input_addresses)

    return tx_input_groups


def get_clustering_state(conn: duckdb.DuckDBPyConnection) -> dict | None:
    """Get clustering sync state from database."""
    try:
        result = conn.execute("""
            SELECT last_block, total_clustered, last_sync_time
            FROM clustering_sync_state
            ORDER BY last_sync_time DESC
            LIMIT 1
        """).fetchone()

        if result:
            return {
                "last_block": result[0],
                "total_clustered": result[1],
                "last_sync_time": result[2],
            }
    except Exception:
        pass
    return None


def update_clustering_state(
    conn: duckdb.DuckDBPyConnection,
    last_block: int,
    total_clustered: int,
) -> None:
    """Update clustering sync state in database."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clustering_sync_state (
            last_block INTEGER,
            total_clustered INTEGER,
            last_sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "INSERT INTO clustering_sync_state (last_block, total_clustered) VALUES (?, ?)",
        [last_block, total_clustered],
    )


def save_clusters_to_db(
    uf: UnionFind,
    conn: duckdb.DuckDBPyConnection,
    batch_size: int = 100000,
) -> int:
    """Save all clusters to database efficiently."""
    from datetime import datetime

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


def run_clustering(
    start_block: int,
    end_block: int,
    db_path: str,
    workers: int = 4,
    checkpoint_interval: int = 1000,
) -> dict:
    """Run address clustering on block range.

    Args:
        start_block: First block to process
        end_block: Last block to process (inclusive)
        db_path: Path to DuckDB database
        workers: Number of parallel block fetches
        checkpoint_interval: Save checkpoint every N blocks

    Returns:
        Statistics dict
    """
    stats = {
        "start_time": time.time(),
        "blocks_processed": 0,
        "transactions_clustered": 0,
        "addresses_clustered": 0,
        "start_block": start_block,
        "end_block": end_block,
    }

    rpc = BitcoinRPC()
    conn = duckdb.connect(db_path)
    uf = UnionFind()

    logger.info(f"Starting clustering: blocks {start_block}-{end_block}")

    # Process blocks in chunks
    chunk_size = workers * 2
    heights = list(range(start_block, end_block + 1))

    def fetch_block(height: int) -> tuple[int, list[list[str]]]:
        try:
            block_hash = rpc.getblockhash(height)
            block_data = rpc.getblock(block_hash, 3)
            groups = extract_input_addresses_from_block(block_data)
            return height, groups
        except Exception as e:
            logger.error(f"Error fetching block {height}: {e}")
            return height, []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for chunk_start in range(0, len(heights), chunk_size):
            chunk_heights = heights[chunk_start : chunk_start + chunk_size]

            # Fetch blocks in parallel
            results = list(executor.map(fetch_block, chunk_heights))

            # Process results sequentially (UnionFind not thread-safe)
            for height, input_groups in sorted(results, key=lambda x: x[0]):
                for addresses in input_groups:
                    cluster_addresses(uf, addresses)
                    stats["transactions_clustered"] += 1
                    stats["addresses_clustered"] += len(addresses)

                stats["blocks_processed"] += 1

            # Progress logging
            current_block = chunk_heights[-1]
            if stats["blocks_processed"] % 100 == 0:
                elapsed = time.time() - stats["start_time"]
                blocks_per_sec = (
                    stats["blocks_processed"] / elapsed if elapsed > 0 else 0
                )
                eta_seconds = (
                    (end_block - current_block) / blocks_per_sec
                    if blocks_per_sec > 0
                    else 0
                )
                logger.info(
                    f"Block {current_block:,}: "
                    f"{stats['transactions_clustered']:,} txs clustered, "
                    f"{blocks_per_sec:.1f} blocks/sec, "
                    f"ETA: {eta_seconds / 3600:.1f}h"
                )

            # Checkpoint
            if stats["blocks_processed"] % checkpoint_interval == 0:
                update_clustering_state(
                    conn, current_block, stats["addresses_clustered"]
                )
                logger.info(f"Checkpoint saved at block {current_block}")

    # Final save
    logger.info("Saving clusters to database...")
    saved = save_clusters_to_db(uf, conn)
    logger.info(f"Saved {saved:,} address-cluster mappings")

    update_clustering_state(conn, end_block, stats["addresses_clustered"])

    conn.close()
    stats["duration_seconds"] = time.time() - stats["start_time"]
    stats["clusters_created"] = len(uf.get_clusters())

    return stats


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run address clustering on historical blockchain (spec-013)"
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
        "--db-path",
        default=UTXO_DB_PATH,
        help=f"Path to UTXO lifecycle DuckDB database (default: {UTXO_DB_PATH})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel block fetches (default: 4)",
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
    conn = duckdb.connect(args.db_path)

    # Determine start block
    if args.resume:
        state = get_clustering_state(conn)
        if state:
            args.start_block = state["last_block"] + 1
            logger.info(f"Resuming from block {args.start_block}")
        else:
            logger.error("No clustering state found. Use --start-block instead.")
            return 1

    if args.start_block is None:
        args.start_block = 0
        logger.info("Starting from block 0 (genesis)")

    # Determine end block
    if args.end_block is None:
        rpc = BitcoinRPC()
        args.end_block = rpc.getblockcount()

    conn.close()

    if args.start_block > args.end_block:
        logger.info("Already at chain tip")
        return 0

    # Run clustering
    stats = run_clustering(
        start_block=args.start_block,
        end_block=args.end_block,
        db_path=args.db_path,
        workers=args.workers,
    )

    print("\n" + "=" * 60)
    print("ADDRESS CLUSTERING COMPLETE")
    print("=" * 60)
    print(f"  Blocks: {stats['start_block']:,} - {stats['end_block']:,}")
    print(f"  Processed: {stats['blocks_processed']:,} blocks")
    print(f"  Transactions clustered: {stats['transactions_clustered']:,}")
    print(f"  Addresses clustered: {stats['addresses_clustered']:,}")
    print(f"  Clusters created: {stats['clusters_created']:,}")
    print(
        f"  Duration: {stats['duration_seconds']:.1f}s ({stats['duration_seconds'] / 3600:.2f}h)"
    )
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
