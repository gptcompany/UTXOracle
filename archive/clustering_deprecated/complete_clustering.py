#!/usr/bin/env python3
"""Complete Clustering: Run Phase 2 & 3 on extracted pairs (spec-013).

This script completes the clustering process when Phase 1 (pair extraction)
is already done. It loads the extracted pairs and runs UnionFind clustering,
then bulk saves to DuckDB.

Usage:
    python -m scripts.bootstrap.complete_clustering

The script expects pair files in data/clustering_temp/pairs_*.csv.gz
"""

from __future__ import annotations

import csv
import gzip
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.clustering.union_find import UnionFind
from scripts.clustering.address_clustering import cluster_addresses

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

UTXO_DB_PATH = os.getenv("UTXO_DB_PATH", "data/utxo_lifecycle.duckdb")
OUTPUT_DIR = Path("data/clustering_temp")


def merge_and_cluster(pair_files: list[Path]) -> UnionFind:
    """Load all pairs and run clustering."""
    logger.info(f"Loading pairs from {len(pair_files)} files...")
    uf = UnionFind()
    total_pairs = 0
    start_time = time.time()

    for i, pair_file in enumerate(sorted(pair_files)):
        file_pairs = 0
        with gzip.open(pair_file, "rt") as f:
            reader = csv.reader(f)
            for addr1, addr2 in reader:
                cluster_addresses(uf, [addr1, addr2])
                file_pairs += 1
                total_pairs += 1

                # Progress every 10M pairs
                # NOTE: Use len(uf) not get_clusters() - O(1) vs O(n)
                # get_clusters() was causing 10+ hours wasted on logging
                if total_pairs % 10_000_000 == 0:
                    elapsed = time.time() - start_time
                    rate = total_pairs / elapsed
                    logger.info(
                        f"  {total_pairs / 1e6:.1f}M pairs, "
                        f"{len(uf):,} addresses, "
                        f"{rate / 1e6:.2f}M pairs/sec"
                    )

        logger.info(
            f"[{i + 1}/{len(pair_files)}] {pair_file.name}: "
            f"{file_pairs:,} pairs, total: {total_pairs:,}"
        )

    elapsed = time.time() - start_time
    logger.info(
        f"Total pairs processed: {total_pairs:,} in {elapsed:.1f}s "
        f"({total_pairs / elapsed / 1e6:.2f}M pairs/sec)"
    )
    return uf


def save_clusters_bulk(uf: UnionFind, db_path: str) -> int:
    """Save clusters using bulk CSV COPY (fastest method)."""
    clusters = uf.get_clusters()
    if not clusters:
        return 0

    # Count total addresses
    total_addresses = sum(len(c) for c in clusters)
    logger.info(f"Saving {len(clusters):,} clusters ({total_addresses:,} addresses)...")

    # Write to temp CSV
    temp_csv = OUTPUT_DIR / "clusters_final.csv"
    now = datetime.now().isoformat()

    logger.info("Writing clusters to temp CSV...")
    with open(temp_csv, "w", newline="") as f:
        writer = csv.writer(f)
        count = 0
        for cluster_set in clusters:
            cluster_id = uf.find(next(iter(cluster_set)))
            for address in cluster_set:
                writer.writerow([address, cluster_id, now, now])
                count += 1
                if count % 10_000_000 == 0:
                    logger.info(f"  Written {count / 1e6:.1f}M addresses...")

    logger.info(f"Temp CSV ready: {temp_csv} ({count:,} rows)")

    # Bulk COPY into DuckDB
    logger.info("Bulk loading clusters into DuckDB...")
    conn = None
    final_count = 0
    try:
        conn = duckdb.connect(db_path)

        # CRITICAL: Wrap DELETE + COPY in transaction
        # If COPY fails after DELETE, we'd lose all data without transaction
        conn.execute("BEGIN TRANSACTION")
        try:
            conn.execute("DELETE FROM address_clusters")
            conn.execute(f"""
                COPY address_clusters (address, cluster_id, first_seen, last_seen)
                FROM '{temp_csv}'
                (FORMAT CSV, HEADER FALSE)
            """)
            conn.execute("COMMIT")
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"Transaction failed, rolled back: {e}")
            raise

        final_count = conn.execute("SELECT COUNT(*) FROM address_clusters").fetchone()[
            0
        ]

        # Check non-singleton clusters
        stats = conn.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT cluster_id) as unique_clusters,
                COUNT(*) FILTER (WHERE cluster_id != address) as non_singleton_addrs
            FROM address_clusters
        """).fetchone()

        logger.info(f"Loaded {final_count:,} addresses into address_clusters")
        logger.info(f"  Total addresses: {stats[0]:,}")
        logger.info(f"  Unique clusters: {stats[1]:,}")
        logger.info(f"  Non-singleton addresses: {stats[2]:,}")

    finally:
        if conn:
            conn.close()
        # Cleanup temp CSV (always, even on error)
        if temp_csv.exists():
            temp_csv.unlink()
            logger.info("Temp CSV cleaned up")

    return final_count


def main():
    """Complete clustering from extracted pairs."""
    start_time = time.time()

    # Find pair files
    pair_files = list(OUTPUT_DIR.glob("pairs_*.csv.gz"))
    if not pair_files:
        logger.error(f"No pair files found in {OUTPUT_DIR}")
        return 1

    logger.info("=" * 70)
    logger.info("COMPLETING CLUSTERING (Phase 2 & 3)")
    logger.info("=" * 70)
    logger.info(f"Pair files: {len(pair_files)}")
    logger.info(f"Database: {UTXO_DB_PATH}")
    logger.info("=" * 70)

    # Phase 2: Merge and cluster
    logger.info("\n--- PHASE 2: UnionFind Clustering ---")
    uf = merge_and_cluster(pair_files)

    clusters = uf.get_clusters()
    logger.info(f"Clustering complete: {len(clusters):,} clusters")

    # Phase 3: Bulk save
    logger.info("\n--- PHASE 3: Bulk Save to DuckDB ---")
    saved = save_clusters_bulk(uf, UTXO_DB_PATH)

    duration = time.time() - start_time

    print("\n" + "=" * 70)
    print("CLUSTERING COMPLETE")
    print("=" * 70)
    print(f"  Clusters created: {len(clusters):,}")
    print(f"  Addresses saved: {saved:,}")
    print(f"  Duration: {duration:.1f}s ({duration / 60:.1f}m)")
    print("=" * 70)
    print("\nNext: Run migrate_cost_basis.py to populate wallet_cost_basis")

    return 0


if __name__ == "__main__":
    sys.exit(main())
