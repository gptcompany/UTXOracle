#!/usr/bin/env python3
"""Memory-Optimized Clustering: Process 2B+ pairs with ~15GB RAM (spec-013).

This version uses integer IDs instead of string addresses to reduce memory
from ~100 bytes/address to ~20 bytes/address (5x reduction).

Strategy:
1. Phase 1: Build address→int mapping, save to disk
2. Phase 2: Run UnionFind on integers only (memory efficient)
3. Phase 3: Write results using int→address mapping

Usage:
    python -m scripts.bootstrap.complete_clustering_v2

Memory estimate: 500M addresses × 20 bytes = 10GB RAM (vs 50GB with strings)
"""

from __future__ import annotations

import csv
import gzip
import logging
import os
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

UTXO_DB_PATH = os.getenv("UTXO_DB_PATH", "data/utxo_lifecycle.duckdb")
OUTPUT_DIR = Path("data/clustering_temp")
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"


class IntUnionFind:
    """Memory-efficient UnionFind using integer IDs only.

    Uses numpy arrays for parent/rank storage - much more memory efficient
    than dict of strings.
    """

    def __init__(self, max_size: int = 600_000_000):
        """Initialize with pre-allocated arrays.

        Args:
            max_size: Maximum number of elements (addresses)
        """
        import numpy as np

        # Use int32 for parent (supports up to 2B elements)
        # Use int8 for rank (max tree height ~31)
        self.parent = np.arange(max_size, dtype=np.int32)  # self-parent initially
        self.rank = np.zeros(max_size, dtype=np.int8)
        self.size = 0  # Current number of elements
        self._max_size = max_size

    def find(self, x: int) -> int:
        """Find root with path compression."""
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        # Path compression
        while self.parent[x] != root:
            next_x = self.parent[x]
            self.parent[x] = root
            x = next_x
        return root

    def union(self, x: int, y: int) -> bool:
        """Union by rank. Returns True if merger happened."""
        root_x = self.find(x)
        root_y = self.find(y)

        if root_x == root_y:
            return False

        # Union by rank
        if self.rank[root_x] < self.rank[root_y]:
            self.parent[root_x] = root_y
        elif self.rank[root_x] > self.rank[root_y]:
            self.parent[root_y] = root_x
        else:
            self.parent[root_y] = root_x
            self.rank[root_x] += 1

        return True

    def memory_usage_gb(self) -> float:
        """Return current memory usage in GB."""
        # parent: 4 bytes * max_size
        # rank: 1 byte * max_size
        return (self.parent.nbytes + self.rank.nbytes) / (1024**3)


def build_address_mapping(pair_files: list[Path], output_file: Path) -> dict[str, int]:
    """Phase 1: Build address→int mapping from all pairs.

    Returns dict mapping address string to integer ID.
    Also saves mapping to disk for recovery.
    """
    logger.info("=== PHASE 1: Building address mapping ===")

    # Check for existing mapping (resume capability)
    if output_file.exists():
        logger.info(f"Loading existing mapping from {output_file}")
        with open(output_file, "rb") as f:
            return pickle.load(f)

    addr_to_int: dict[str, int] = {}
    next_id = 0
    total_pairs = 0
    start_time = time.time()

    for i, pair_file in enumerate(sorted(pair_files)):
        file_new = 0
        with gzip.open(pair_file, "rt") as f:
            reader = csv.reader(f)
            for addr1, addr2 in reader:
                if addr1 not in addr_to_int:
                    addr_to_int[addr1] = next_id
                    next_id += 1
                    file_new += 1
                if addr2 not in addr_to_int:
                    addr_to_int[addr2] = next_id
                    next_id += 1
                    file_new += 1
                total_pairs += 1

                if total_pairs % 50_000_000 == 0:
                    elapsed = time.time() - start_time
                    logger.info(
                        f"  {total_pairs / 1e6:.0f}M pairs, "
                        f"{len(addr_to_int):,} addresses, "
                        f"{total_pairs / elapsed / 1e6:.2f}M pairs/sec"
                    )

        logger.info(
            f"[{i + 1}/{len(pair_files)}] {pair_file.name}: "
            f"+{file_new:,} new addresses, total: {len(addr_to_int):,}"
        )

    elapsed = time.time() - start_time
    logger.info(
        f"Phase 1 complete: {len(addr_to_int):,} unique addresses "
        f"from {total_pairs:,} pairs in {elapsed:.1f}s"
    )

    # Save mapping to disk
    logger.info(f"Saving mapping to {output_file}...")
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    with open(output_file, "wb") as f:
        pickle.dump(addr_to_int, f, protocol=pickle.HIGHEST_PROTOCOL)

    mapping_size_gb = output_file.stat().st_size / (1024**3)
    logger.info(f"Mapping saved: {mapping_size_gb:.2f} GB")

    return addr_to_int


def run_int_clustering(
    pair_files: list[Path],
    addr_to_int: dict[str, int],
    checkpoint_file: Path | None = None,
) -> IntUnionFind:
    """Phase 2: Run UnionFind clustering using integer IDs only.

    This is the memory-efficient core - only integers in UnionFind.
    """
    logger.info("=== PHASE 2: Integer-based UnionFind clustering ===")

    num_addresses = len(addr_to_int)
    logger.info(f"Initializing IntUnionFind for {num_addresses:,} addresses...")

    uf = IntUnionFind(max_size=num_addresses + 1000)  # Small buffer
    uf.size = num_addresses

    logger.info(f"IntUnionFind memory: {uf.memory_usage_gb():.2f} GB")

    total_pairs = 0
    unions = 0
    start_time = time.time()

    for i, pair_file in enumerate(sorted(pair_files)):
        file_unions = 0
        with gzip.open(pair_file, "rt") as f:
            reader = csv.reader(f)
            for addr1, addr2 in reader:
                id1 = addr_to_int[addr1]
                id2 = addr_to_int[addr2]

                if uf.union(id1, id2):
                    unions += 1
                    file_unions += 1

                total_pairs += 1

                if total_pairs % 50_000_000 == 0:
                    elapsed = time.time() - start_time
                    logger.info(
                        f"  {total_pairs / 1e6:.0f}M pairs, "
                        f"{unions:,} unions, "
                        f"{total_pairs / elapsed / 1e6:.2f}M pairs/sec"
                    )

        logger.info(
            f"[{i + 1}/{len(pair_files)}] {pair_file.name}: "
            f"{file_unions:,} unions this file"
        )

        # Checkpoint after each file
        if checkpoint_file:
            save_uf_checkpoint(uf, checkpoint_file, i + 1, total_pairs, unions)

    elapsed = time.time() - start_time
    logger.info(
        f"Phase 2 complete: {total_pairs:,} pairs → {unions:,} unions "
        f"in {elapsed:.1f}s ({total_pairs / elapsed / 1e6:.2f}M pairs/sec)"
    )

    return uf


def save_uf_checkpoint(
    uf: IntUnionFind, path: Path, file_idx: int, pairs: int, unions: int
):
    """Save UnionFind state checkpoint (atomic write)."""

    checkpoint = {
        "file_idx": file_idx,
        "pairs_processed": pairs,
        "unions": unions,
        "parent": uf.parent[: uf.size],
        "rank": uf.rank[: uf.size],
        "size": uf.size,
    }

    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "wb") as f:
        pickle.dump(checkpoint, f, protocol=pickle.HIGHEST_PROTOCOL)
        f.flush()
        os.fsync(f.fileno())
    temp_path.rename(path)


def count_clusters(uf: IntUnionFind) -> int:
    """Count unique clusters (roots)."""
    import numpy as np

    # A root is where parent[i] == i
    roots = np.sum(uf.parent[: uf.size] == np.arange(uf.size, dtype=np.int32))
    return int(roots)


def save_clusters_bulk(
    uf: IntUnionFind, addr_to_int: dict[str, int], db_path: str
) -> int:
    """Phase 3: Write clusters to DuckDB using bulk COPY.

    Creates int→address mapping and writes CSV for bulk load.
    """
    logger.info("=== PHASE 3: Writing clusters to database ===")

    # Create reverse mapping
    logger.info("Building int→address reverse mapping...")
    int_to_addr = {v: k for k, v in addr_to_int.items()}

    # Count clusters
    num_clusters = count_clusters(uf)
    logger.info(f"Found {num_clusters:,} unique clusters")

    # Write to temp CSV
    temp_csv = OUTPUT_DIR / "clusters_final.csv"
    now = datetime.now().isoformat()

    logger.info(f"Writing {uf.size:,} addresses to {temp_csv}...")
    count = 0
    start_time = time.time()

    with open(temp_csv, "w", newline="") as f:
        writer = csv.writer(f)
        for int_id in range(uf.size):
            address = int_to_addr[int_id]
            root_id = uf.find(int_id)
            cluster_id = int_to_addr[root_id]  # Use root's address as cluster_id
            writer.writerow([address, cluster_id, now, now])
            count += 1

            if count % 50_000_000 == 0:
                elapsed = time.time() - start_time
                logger.info(
                    f"  Written {count / 1e6:.0f}M addresses ({count / elapsed / 1e6:.2f}M/sec)"
                )

    elapsed = time.time() - start_time
    logger.info(f"CSV written: {count:,} rows in {elapsed:.1f}s")

    # Bulk COPY into DuckDB
    logger.info("Bulk loading into DuckDB...")
    conn = None
    final_count = 0

    try:
        conn = duckdb.connect(db_path)

        # Transaction for DELETE + COPY
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

        # Stats
        stats = conn.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT cluster_id) as unique_clusters,
                COUNT(*) FILTER (WHERE cluster_id != address) as non_singleton
            FROM address_clusters
        """).fetchone()

        logger.info(f"Loaded {final_count:,} addresses")
        logger.info(f"  Unique clusters: {stats[1]:,}")
        logger.info(f"  Non-singleton addresses: {stats[2]:,}")

        conn.close()

    except Exception as e:
        logger.error(f"Database error: {e}")
        if conn:
            conn.close()
        raise

    # Cleanup temp file
    if temp_csv.exists():
        temp_csv.unlink()
        logger.info("Cleaned up temp CSV")

    return final_count


def main():
    """Run memory-optimized clustering pipeline."""
    print("\n" + "=" * 70)
    print("MEMORY-OPTIMIZED CLUSTERING (v2)")
    print("=" * 70)

    # Find pair files
    pair_files = sorted(OUTPUT_DIR.glob("pairs_*.csv.gz"))
    if not pair_files:
        logger.error(f"No pair files found in {OUTPUT_DIR}")
        sys.exit(1)

    total_size = sum(f.stat().st_size for f in pair_files)
    print(f"Pair files: {len(pair_files)} ({total_size / 1e9:.1f} GB compressed)")
    print(f"Database: {UTXO_DB_PATH}")
    print("=" * 70 + "\n")

    start_time = time.time()

    # Phase 1: Build address mapping
    mapping_file = CHECKPOINT_DIR / "address_mapping.pkl"
    addr_to_int = build_address_mapping(pair_files, mapping_file)

    # Phase 2: Integer-based clustering
    checkpoint_file = CHECKPOINT_DIR / "uf_checkpoint.pkl"
    uf = run_int_clustering(pair_files, addr_to_int, checkpoint_file)

    # Phase 3: Save to database
    saved = save_clusters_bulk(uf, addr_to_int, UTXO_DB_PATH)

    # Summary
    duration = time.time() - start_time
    print("\n" + "=" * 70)
    print("CLUSTERING COMPLETE")
    print("=" * 70)
    print(f"  Addresses: {len(addr_to_int):,}")
    print(f"  Clusters: {count_clusters(uf):,}")
    print(f"  Saved to DB: {saved:,}")
    print(f"  Duration: {duration:.1f}s ({duration / 60:.1f}m)")
    print(
        f"  Peak memory: ~{uf.memory_usage_gb() + len(addr_to_int) * 100 / 1e9:.1f} GB"
    )
    print("=" * 70)
    print("\nNext: Run migrate_cost_basis.py to populate wallet_cost_basis")


if __name__ == "__main__":
    main()
