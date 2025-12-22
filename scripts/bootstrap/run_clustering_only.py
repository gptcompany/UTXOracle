#!/usr/bin/env python3
"""Clustering-Only Bootstrap: Extract Address Clusters from Blockchain (spec-013).

This script ONLY performs address clustering, without updating spent UTXOs.
This is faster because:
1. No database writes during block processing (pure in-memory UnionFind)
2. Single batch write at the end for clusters
3. Can run while index creation is in progress

The spent UTXO updates will be handled separately by run_combined_bootstrap.py
after the txid,vout index is created.

Architecture:
- Uses Bitcoin Core RPC verbosity=3 for efficient prevout data
- Multi-input heuristic: addresses spending together belong to same entity
- Parallel block fetching, sequential UnionFind operations (not thread-safe)
- Clusters saved to address_clusters table at checkpoints and end

Usage:
    # Full bootstrap from genesis
    python -m scripts.bootstrap.run_clustering_only --start-block 0

    # Resume from checkpoint
    python -m scripts.bootstrap.run_clustering_only --resume

    # Custom range with more workers
    python -m scripts.bootstrap.run_clustering_only --start-block 800000 --end-block 850000 --workers 8

Performance:
    - ~1500-2000 blocks/minute (faster than combined bootstrap)
    - Full blockchain (928k blocks): ~8-10 hours
"""

from __future__ import annotations

import argparse
import logging
import os
import pickle
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
CHECKPOINT_DIR = Path("data/clustering_checkpoints")


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


def extract_clustering_data(block_data: dict, uf: UnionFind) -> dict:
    """Extract clustering data from a block.

    Args:
        block_data: Block data from RPC v3
        uf: UnionFind structure for clustering

    Returns:
        Stats dict
    """
    stats = {
        "txs_clustered": 0,
        "addresses_clustered": 0,
    }

    for tx in block_data.get("tx", []):
        input_addresses = []

        for vin in tx.get("vin", []):
            # Skip coinbase inputs
            if "coinbase" in vin:
                continue

            # Get prevout address for clustering
            prevout = vin.get("prevout", {})
            spk = prevout.get("scriptPubKey", {})
            addr = spk.get("address")

            if addr:
                input_addresses.append(addr)

        # Cluster addresses with 2+ inputs
        if len(input_addresses) >= 2:
            cluster_addresses(uf, input_addresses)
            stats["txs_clustered"] += 1
            stats["addresses_clustered"] += len(input_addresses)

    return stats


def save_checkpoint(
    uf: UnionFind,
    last_block: int,
    stats: dict,
) -> None:
    """Save UnionFind state to checkpoint file atomically."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_file = CHECKPOINT_DIR / f"clustering_checkpoint_{last_block}.pkl"
    temp_file = checkpoint_file.with_suffix(".pkl.tmp")

    checkpoint_data = {
        "uf": uf,
        "last_block": last_block,
        "stats": stats,
        "timestamp": datetime.now().isoformat(),
    }

    # Atomic write: write to temp file, then rename
    with open(temp_file, "wb") as f:
        pickle.dump(checkpoint_data, f)
        f.flush()
        os.fsync(f.fileno())  # Ensure data is on disk

    temp_file.rename(checkpoint_file)  # Atomic on POSIX
    logger.info(f"Checkpoint saved: {checkpoint_file}")

    # Clean old checkpoints (keep last 3)
    # Sort numerically by block number, not lexicographically
    def _extract_block_num(p: Path) -> int:
        try:
            return int(p.stem.split("_")[-1])
        except (ValueError, IndexError):
            return 0

    checkpoints = sorted(
        CHECKPOINT_DIR.glob("clustering_checkpoint_*.pkl"),
        key=_extract_block_num,
    )
    for old_ckpt in checkpoints[:-3]:
        old_ckpt.unlink()


def load_latest_checkpoint() -> tuple[UnionFind, int, dict] | None:
    """Load the latest checkpoint if exists."""
    if not CHECKPOINT_DIR.exists():
        return None

    # Sort numerically by block number, not lexicographically
    def _extract_block_num(p: Path) -> int:
        try:
            return int(p.stem.split("_")[-1])
        except (ValueError, IndexError):
            return 0

    checkpoints = sorted(
        CHECKPOINT_DIR.glob("clustering_checkpoint_*.pkl"),
        key=_extract_block_num,
    )
    if not checkpoints:
        return None

    latest = checkpoints[-1]
    logger.info(f"Loading checkpoint: {latest}")

    with open(latest, "rb") as f:
        data = pickle.load(f)

    return data["uf"], data["last_block"], data["stats"]


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
                logger.info(f"Saved {count:,} cluster mappings...")
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


def run_clustering_only(
    start_block: int,
    end_block: int,
    db_path: str,
    workers: int = 10,
    checkpoint_interval: int = 5000,
    resume_uf: UnionFind | None = None,
    resume_stats: dict | None = None,
) -> dict:
    """Run address clustering on block range.

    Args:
        start_block: First block to process
        end_block: Last block to process (inclusive)
        db_path: Path to DuckDB database
        workers: Number of parallel block fetches
        checkpoint_interval: Save checkpoint every N blocks
        resume_uf: UnionFind to resume from (if resuming)
        resume_stats: Stats to resume from (if resuming)

    Returns:
        Statistics dict
    """
    stats = resume_stats or {
        "start_time": time.time(),
        "blocks_processed": 0,
        "blocks_failed": 0,
        "txs_clustered": 0,
        "addresses_clustered": 0,
        "start_block": start_block,
    }
    if "blocks_failed" not in stats:
        stats["blocks_failed"] = 0  # For resume compatibility
    stats["end_block"] = end_block
    if "start_time" not in stats:
        stats["start_time"] = time.time()

    rpc = BitcoinRPC()
    uf = resume_uf or UnionFind()

    logger.info(f"Starting clustering: blocks {start_block}-{end_block}")
    logger.info(f"  Workers: {workers}")
    logger.info(f"  Checkpoint interval: {checkpoint_interval} blocks")
    if resume_uf:
        logger.info(f"  Resuming with {len(uf.get_clusters())} existing clusters")

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
                    stats["blocks_failed"] += 1
                    continue

                block_stats = extract_clustering_data(block_data, uf)

                stats["blocks_processed"] += 1
                stats["txs_clustered"] += block_stats["txs_clustered"]
                stats["addresses_clustered"] += block_stats["addresses_clustered"]

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
                # Use len(uf) instead of len(get_clusters()) to avoid memory-expensive
                # cluster enumeration. len(uf) returns total addresses tracked.
                addr_count = len(uf)
                logger.info(
                    f"Block {current_block:,}: "
                    f"{stats['txs_clustered']:,} txs, {addr_count:,} addrs, "
                    f"{blocks_per_sec:.1f} blk/s, "
                    f"ETA: {eta_seconds / 3600:.1f}h"
                )

            # Checkpoint (in-memory + file)
            if stats["blocks_processed"] % checkpoint_interval == 0:
                save_checkpoint(uf, current_block, stats)

    # Final save to database
    logger.info("Saving clusters to database...")
    conn = duckdb.connect(db_path)
    try:
        saved = save_clusters_to_db(uf, conn)
        logger.info(f"Saved {saved:,} address-cluster mappings")
    finally:
        conn.close()

    stats["duration_seconds"] = time.time() - stats["start_time"]
    stats["clusters_created"] = len(uf.get_clusters())

    # Clean up checkpoints after successful completion
    for ckpt in CHECKPOINT_DIR.glob("clustering_checkpoint_*.pkl"):
        ckpt.unlink()

    return stats


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Clustering-only bootstrap: extract address clusters (spec-013)"
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
        help=f"Path to DuckDB database (default: {UTXO_DB_PATH})",
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
        default=5000,
        help="Save checkpoint every N blocks (default: 5000)",
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

    # Handle resume
    resume_uf = None
    resume_stats = None

    if args.resume:
        checkpoint = load_latest_checkpoint()
        if checkpoint:
            resume_uf, last_block, resume_stats = checkpoint
            args.start_block = last_block + 1
            logger.info(f"Resuming from block {args.start_block}")
        else:
            logger.error("No checkpoint found. Use --start-block instead.")
            return 1

    if args.start_block is None:
        args.start_block = 0
        logger.info("Starting from block 0 (genesis)")

    # Determine end block
    if args.end_block is None:
        rpc = BitcoinRPC()
        args.end_block = rpc.getblockcount()

    if args.start_block > args.end_block:
        logger.info("Already at chain tip")
        return 0

    # Run clustering
    stats = run_clustering_only(
        start_block=args.start_block,
        end_block=args.end_block,
        db_path=args.db_path,
        workers=args.workers,
        checkpoint_interval=args.checkpoint_interval,
        resume_uf=resume_uf,
        resume_stats=resume_stats,
    )

    print("\n" + "=" * 70)
    print("CLUSTERING BOOTSTRAP COMPLETE")
    print("=" * 70)
    print(f"  Blocks: {stats['start_block']:,} - {stats['end_block']:,}")
    print(f"  Processed: {stats['blocks_processed']:,} blocks")
    if stats.get("blocks_failed", 0) > 0:
        print(f"  Failed: {stats['blocks_failed']:,} blocks (WARNING)")
    print(f"  Transactions clustered: {stats['txs_clustered']:,}")
    print(f"  Addresses clustered: {stats['addresses_clustered']:,}")
    print(f"  Clusters created: {stats['clusters_created']:,}")
    print(
        f"  Duration: {stats['duration_seconds']:.1f}s ({stats['duration_seconds'] / 3600:.2f}h)"
    )
    print("=" * 70)
    print("\nNext step: Run migrate_cost_basis.py to populate wallet_cost_basis")

    # Return non-zero if blocks failed
    if stats.get("blocks_failed", 0) > 0:
        logger.warning(
            f"{stats['blocks_failed']} blocks failed to fetch. "
            "Consider re-running with --resume after checking Bitcoin Core."
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
