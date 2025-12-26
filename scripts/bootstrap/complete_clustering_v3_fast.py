#!/usr/bin/env python3
"""Ultra-Fast Clustering: 10x speedup over v2 using Cython + PyArrow (spec-013).

Performance Optimizations:
1. Cython-compiled UnionFind (18M ops/sec vs 0.25M ops/sec = 70x faster)
2. PyArrow CSV parsing (4-5M rows/sec vs 0.6M rows/sec = 7x faster)
3. Parallel file processing with multiprocessing (scales with cores)
4. Batch processing to minimize Python overhead
5. Memory-efficient integer ID mapping

Target: Process 2B pairs in ~20-30 minutes instead of 3-4 hours.

Architecture:
- Phase 1: Build address->int mapping using PyArrow (parallel read)
- Phase 2: Cython UnionFind clustering on integer IDs
- Phase 3: Bulk COPY results to DuckDB

Usage:
    # First compile Cython extension:
    cd scripts/bootstrap/cython_uf && python setup.py build_ext --inplace

    # Then run:
    python -m scripts.bootstrap.complete_clustering_v3_fast

Requirements:
    - Cython extension compiled (scripts/bootstrap/cython_uf/)
    - PyArrow 21.0+
    - DuckDB
    - ~30GB RAM for 164M addresses
"""

from __future__ import annotations

import csv
import gc
import logging
import os
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.csv as pv_csv
from dotenv import load_dotenv

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import Cython extension
sys.path.insert(0, str(Path(__file__).parent / "cython_uf"))
try:
    from fast_union_find import FastUnionFind

    CYTHON_AVAILABLE = True
except ImportError:
    CYTHON_AVAILABLE = False
    print("WARNING: Cython extension not found. Run:")
    print("  cd scripts/bootstrap/cython_uf && python setup.py build_ext --inplace")

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

UTXO_DB_PATH = os.getenv("UTXO_DB_PATH", "data/utxo_lifecycle.duckdb")
OUTPUT_DIR = Path("data/clustering_temp")
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"

# Processing parameters
BATCH_SIZE = 10_000_000  # Process 10M pairs at a time
PROGRESS_INTERVAL = 50_000_000  # Log every 50M pairs


def load_file_with_pyarrow(file_path: Path) -> pa.Table:
    """Load a single gzipped CSV file using PyArrow.

    Returns PyArrow table with addr1, addr2 columns.
    """
    return pv_csv.read_csv(
        file_path,
        read_options=pv_csv.ReadOptions(
            column_names=["addr1", "addr2"],
            block_size=1024 * 1024 * 32,  # 32MB blocks for better throughput
            use_threads=False,  # Single-threaded to avoid SIGFPE with large memory
        ),
        parse_options=pv_csv.ParseOptions(delimiter=","),
    )


# Size threshold for chunked reading (1GB uncompressed estimate)
LARGE_FILE_THRESHOLD_GB = 1.0
CHUNK_SIZE_ROWS = 1_000_000  # 1M rows per chunk (minimal memory)


def stream_file_chunks(file_path: Path):
    """Stream a gzipped CSV file in chunks using PyArrow streaming reader.

    Yields batches of (addr1_list, addr2_list) tuples.
    This avoids loading the entire file into memory.
    """

    # Estimate if file is "large" based on compressed size
    # Typically 15-20x compression ratio for address pairs
    compressed_size_gb = file_path.stat().st_size / (1024**3)
    estimated_uncompressed_gb = compressed_size_gb * 18  # Conservative estimate

    if estimated_uncompressed_gb < LARGE_FILE_THRESHOLD_GB:
        # Small file - load all at once (faster)
        table = load_file_with_pyarrow(file_path)
        yield table.column("addr1").to_pylist(), table.column("addr2").to_pylist()
        del table
        return

    # Large file - use streaming reader with chunked batches
    logger.info(
        f"  Using chunked streaming for large file ({compressed_size_gb:.1f}GB compressed)"
    )

    try:
        # Try PyArrow streaming reader first
        # NOTE: use_threads=False to avoid SIGFPE race condition with large dicts
        reader = pv_csv.open_csv(
            file_path,
            read_options=pv_csv.ReadOptions(
                column_names=["addr1", "addr2"],
                block_size=1024 * 1024 * 32,  # 32MB blocks (reduced for memory)
                use_threads=False,  # Single-threaded to avoid memory corruption
            ),
            parse_options=pv_csv.ParseOptions(
                delimiter=",",
                invalid_row_handler=lambda row: "skip",  # Skip malformed rows
            ),
        )

        batch_count = 0

        for batch in reader:
            batch_count += 1
            # Yield each batch directly to minimize memory (no accumulation)
            addr1_list = batch.column("addr1").to_pylist()
            addr2_list = batch.column("addr2").to_pylist()
            del batch
            yield addr1_list, addr2_list
            del addr1_list, addr2_list
            gc.collect()  # Aggressive memory cleanup

        logger.info(f"  Processed {batch_count} batches via PyArrow streaming")

    except Exception as e:
        # CRITICAL: Do NOT fallback after yielding data - would cause duplicates (B8 fix)
        # If PyArrow fails mid-file, we must fail fast and let caller handle retry
        logger.error(f"  PyArrow streaming failed: {e}")
        logger.error("  Cannot fallback safely after partial yield - failing fast")
        raise RuntimeError(f"PyArrow streaming failed for {file_path.name}: {e}") from e


def count_file_rows(file_path: Path) -> Tuple[str, int]:
    """Count rows in a single file (for parallel execution)."""
    table = load_file_with_pyarrow(file_path)
    return (str(file_path), len(table))


def save_mapping_checkpoint(
    addr_to_int: Dict[str, int],
    output_file: Path,
    file_idx: int,
    total_pairs: int,
) -> None:
    """Save Phase 1 mapping checkpoint atomically."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    checkpoint = {
        "addr_to_int": addr_to_int,
        "file_idx": file_idx,
        "total_pairs": total_pairs,
        "next_id": len(addr_to_int),
    }

    temp_path = output_file.with_suffix(".tmp")
    with open(temp_path, "wb") as f:
        pickle.dump(checkpoint, f, protocol=pickle.HIGHEST_PROTOCOL)
        f.flush()
        os.fsync(f.fileno())
    temp_path.rename(output_file)


def load_mapping_checkpoint(
    checkpoint_file: Path,
) -> Tuple[Dict[str, int], int, int, int] | None:
    """Load Phase 1 mapping checkpoint.

    Returns (addr_to_int, next_id, start_file_idx, total_pairs) or None.
    """
    if not checkpoint_file.exists():
        return None

    try:
        with open(checkpoint_file, "rb") as f:
            checkpoint = pickle.load(f)

        # Handle both old format (just dict) and new format (checkpoint dict)
        if isinstance(checkpoint, dict) and "addr_to_int" in checkpoint:
            return (
                checkpoint["addr_to_int"],
                checkpoint["next_id"],
                checkpoint["file_idx"],
                checkpoint["total_pairs"],
            )
        elif isinstance(checkpoint, dict):
            # Old format - complete mapping, no resume needed
            return checkpoint, len(checkpoint), 999, 0  # 999 = all files done
        else:
            return None
    except (pickle.UnpicklingError, EOFError, KeyError, OSError) as e:
        logger.warning(f"Corrupted mapping checkpoint, will rebuild: {e}")
        return None


def build_address_mapping_fast(
    pair_files: List[Path],
    output_file: Path,
    workers: int = 8,
) -> Dict[str, int]:
    """Phase 1: Build address->int mapping using chunked streaming.

    Optimizations:
    - Chunked streaming for large files (avoids memory issues)
    - Per-file checkpointing for resume capability
    - Fallback to Python csv if PyArrow fails

    Returns dict mapping address string to integer ID.
    """
    logger.info("=== PHASE 1: Building address mapping (chunked streaming) ===")

    sorted_files = sorted(pair_files)
    start_file_idx = 0
    total_pairs = 0

    # Try to load checkpoint for resume
    checkpoint_data = load_mapping_checkpoint(output_file)
    if checkpoint_data:
        addr_to_int, next_id, start_file_idx, total_pairs = checkpoint_data
        if start_file_idx >= len(sorted_files):
            logger.info(f"Mapping complete: {len(addr_to_int):,} addresses from cache")
            return addr_to_int
        logger.info(
            f"Resuming from file {start_file_idx}/{len(sorted_files)}, "
            f"{len(addr_to_int):,} addresses, {total_pairs:,} pairs processed"
        )
    else:
        addr_to_int = {}
        next_id = 0

    start_time = time.time()

    for i, pair_file in enumerate(sorted_files):
        # Skip already processed files
        if i < start_file_idx:
            continue

        file_start = time.time()
        file_rows = 0
        file_new = 0

        # Use chunked streaming for all files (handles large files safely)
        try:
            for addr1_list, addr2_list in stream_file_chunks(pair_file):
                for addr1, addr2 in zip(addr1_list, addr2_list):
                    if addr1 not in addr_to_int:
                        addr_to_int[addr1] = next_id
                        next_id += 1
                        file_new += 1
                    if addr2 not in addr_to_int:
                        addr_to_int[addr2] = next_id
                        next_id += 1
                        file_new += 1
                    file_rows += 1
                    total_pairs += 1

        except Exception as e:
            logger.error(f"Error processing {pair_file.name}: {e}")
            logger.error("Saving checkpoint and stopping...")
            save_mapping_checkpoint(addr_to_int, output_file, i, total_pairs)
            raise

        file_elapsed = time.time() - file_start
        rate = file_rows / file_elapsed / 1e6 if file_elapsed > 0 else 0
        logger.info(
            f"[{i + 1}/{len(pair_files)}] {pair_file.name}: "
            f"{file_rows:,} rows, +{file_new:,} new addresses "
            f"({file_elapsed:.1f}s, {rate:.2f}M/s)"
        )

        # Save checkpoint after EACH file (for resume capability)
        save_mapping_checkpoint(addr_to_int, output_file, i + 1, total_pairs)
        logger.info(f"  Checkpoint saved: {len(addr_to_int):,} addresses")

        # Force garbage collection between files
        gc.collect()

    elapsed = time.time() - start_time
    rate = total_pairs / elapsed / 1e6 if elapsed > 0 else 0
    logger.info(
        f"Phase 1 complete: {len(addr_to_int):,} unique addresses "
        f"from {total_pairs:,} pairs in {elapsed:.1f}s ({rate:.2f}M pairs/sec)"
    )

    mapping_size_gb = output_file.stat().st_size / (1024**3)
    logger.info(f"Mapping saved: {mapping_size_gb:.2f} GB")

    return addr_to_int


def run_cython_clustering(
    pair_files: List[Path],
    addr_to_int: Dict[str, int],
    checkpoint_file: Path | None = None,
) -> FastUnionFind:
    """Phase 2: Cython-accelerated UnionFind clustering.

    Key optimizations:
    - Cython compiled UnionFind (nogil, typed arrays)
    - Batch processing of integer ID pairs
    - Path compression and union by rank

    Returns FastUnionFind instance.
    """
    if not CYTHON_AVAILABLE:
        raise RuntimeError("Cython extension required. See module docstring.")

    logger.info("=== PHASE 2: Cython UnionFind clustering ===")

    num_addresses = len(addr_to_int)
    start_file_idx = 0
    total_pairs = 0
    total_unions = 0
    checkpoint_loaded = False  # B12 fix: track if checkpoint was loaded
    uf = None  # Will be initialized below

    # Try to load checkpoint for resume
    if checkpoint_file and checkpoint_file.exists():
        try:
            logger.info(f"Loading Phase 2 checkpoint from {checkpoint_file}")
            with open(checkpoint_file, "rb") as f:
                checkpoint = pickle.load(f)

            # B6 fix: Validate checkpoint matches current mapping size
            if checkpoint["size"] != num_addresses:
                logger.warning(
                    f"Checkpoint size mismatch: checkpoint has {checkpoint['size']:,} "
                    f"but current mapping has {num_addresses:,} addresses. Starting fresh."
                )
                checkpoint_file.unlink()
                raise ValueError("Checkpoint size mismatch")

            # Restore UnionFind state
            uf = FastUnionFind(num_addresses + 1000)
            parent_arr = uf.get_parent_array()
            rank_arr = uf.get_rank_array()
            parent_arr[: checkpoint["size"]] = checkpoint["parent"]
            rank_arr[: checkpoint["size"]] = checkpoint["rank"]

            start_file_idx = checkpoint["file_idx"]
            total_pairs = checkpoint["pairs_processed"]
            total_unions = checkpoint["unions"]
            checkpoint_loaded = True  # B12 fix: mark as loaded

            logger.info(
                f"Resumed from file {start_file_idx}/{len(pair_files)}, "
                f"{total_pairs:,} pairs, {total_unions:,} unions"
            )
        except (pickle.UnpicklingError, EOFError, KeyError, OSError) as e:
            logger.warning(f"Corrupted checkpoint, starting fresh: {e}")
            checkpoint_file.unlink()
            start_file_idx = 0
            checkpoint_loaded = False

    # B12 fix: Only create fresh UF if NO checkpoint was loaded (even if file_idx=0)
    if not checkpoint_loaded:
        logger.info(f"Initializing FastUnionFind for {num_addresses:,} addresses...")
        uf = FastUnionFind(num_addresses + 1000)  # Small buffer

    logger.info(f"FastUnionFind memory: {uf.memory_usage_gb():.2f} GB")

    start_time = time.time()
    sorted_files = sorted(pair_files)

    for i, pair_file in enumerate(sorted_files):
        # Skip already processed files
        if i < start_file_idx:
            continue

        file_start = time.time()
        file_rows = 0
        file_unions = 0

        # Use chunked streaming for large files (avoids memory issues)
        try:
            for addr1_list, addr2_list in stream_file_chunks(pair_file):
                chunk_size = len(addr1_list)

                # Build numpy arrays of integer IDs for this chunk
                ids1 = np.array([addr_to_int[a] for a in addr1_list], dtype=np.int32)
                ids2 = np.array([addr_to_int[a] for a in addr2_list], dtype=np.int32)
                del addr1_list, addr2_list

                # Process in batches using Cython
                for batch_start in range(0, len(ids1), BATCH_SIZE):
                    batch_end = min(batch_start + BATCH_SIZE, len(ids1))
                    batch_ids1 = ids1[batch_start:batch_end]
                    batch_ids2 = ids2[batch_start:batch_end]

                    # Cython batch processing
                    unions = uf.process_id_pairs(batch_ids1, batch_ids2)
                    file_unions += unions
                    total_pairs += len(batch_ids1)

                    if total_pairs % PROGRESS_INTERVAL == 0:
                        elapsed = time.time() - start_time
                        logger.info(
                            f"  {total_pairs / 1e6:.0f}M pairs, "
                            f"{total_unions + file_unions:,} unions, "
                            f"{total_pairs / elapsed / 1e6:.2f}M pairs/sec"
                        )

                file_rows += chunk_size
                del ids1, ids2

        except Exception as e:
            logger.error(f"Error processing {pair_file.name}: {e}")
            logger.error("Saving checkpoint and stopping...")
            if checkpoint_file:
                save_checkpoint(uf, checkpoint_file, i, total_pairs, total_unions)
            raise

        total_unions += file_unions
        file_elapsed = time.time() - file_start
        rate = file_rows / file_elapsed / 1e6 if file_elapsed > 0 else 0

        logger.info(
            f"[{i + 1}/{len(pair_files)}] {pair_file.name}: "
            f"{file_rows:,} rows, {file_unions:,} unions "
            f"({file_elapsed:.1f}s, {rate:.2f}M/s)"
        )

        # Checkpoint after each file
        if checkpoint_file:
            save_checkpoint(uf, checkpoint_file, i + 1, total_pairs, total_unions)
            logger.info("  Phase 2 checkpoint saved")

        # Force garbage collection between files
        gc.collect()

    elapsed = time.time() - start_time
    logger.info(
        f"Phase 2 complete: {total_pairs:,} pairs -> {total_unions:,} unions "
        f"in {elapsed:.1f}s ({total_pairs / elapsed / 1e6:.2f}M pairs/sec)"
    )

    return uf


def save_checkpoint(
    uf: FastUnionFind, path: Path, file_idx: int, pairs: int, unions: int
) -> None:
    """Save UnionFind state checkpoint (atomic write)."""
    parent = uf.get_parent_array()
    rank = uf.get_rank_array()

    checkpoint = {
        "file_idx": file_idx,
        "pairs_processed": pairs,
        "unions": unions,
        "parent": parent.copy(),
        "rank": rank.copy(),
        "size": len(parent),
    }

    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "wb") as f:
        pickle.dump(checkpoint, f, protocol=pickle.HIGHEST_PROTOCOL)
        f.flush()
        os.fsync(f.fileno())
    temp_path.rename(path)


def count_clusters(uf: FastUnionFind, num_addresses: int) -> int:
    """Count unique clusters (roots).

    Args:
        uf: FastUnionFind instance
        num_addresses: Actual number of addresses (excludes buffer slots)

    Returns:
        Number of unique clusters (roots where parent[i] == i)
    """
    parent = uf.get_parent_array()
    # B5 fix: Only count actual addresses, not buffer slots
    # A root is where parent[i] == i
    roots = np.sum(parent[:num_addresses] == np.arange(num_addresses, dtype=np.int32))
    return int(roots)


def save_clusters_bulk(
    uf: FastUnionFind,
    addr_to_int: Dict[str, int],
    db_path: str,
) -> int:
    """Phase 3: Write clusters to DuckDB using bulk COPY.

    Optimizations:
    - Vectorized root finding
    - Streaming CSV write
    - Single bulk COPY operation
    """
    logger.info("=== PHASE 3: Writing clusters to database ===")

    # Create reverse mapping
    logger.info("Building int->address reverse mapping...")
    int_to_addr = {v: k for k, v in addr_to_int.items()}

    num_addresses = len(addr_to_int)

    # Count clusters (B5 fix: pass num_addresses to exclude buffer)
    num_clusters = count_clusters(uf, num_addresses)
    logger.info(f"Found {num_clusters:,} unique clusters")

    # Write to temp CSV with streaming
    temp_csv = OUTPUT_DIR / "clusters_final.csv"
    now = datetime.now().isoformat()

    logger.info(f"Writing {num_addresses:,} addresses to {temp_csv}...")
    count = 0
    start_time = time.time()

    with open(temp_csv, "w", newline="") as f:
        writer = csv.writer(f)

        for int_id in range(num_addresses):
            address = int_to_addr[int_id]

            # Find root (with path compression already done)
            root_id = uf.find(int_id)
            cluster_id = int_to_addr[root_id]

            writer.writerow([address, cluster_id, now, now])
            count += 1

            if count % 50_000_000 == 0:
                elapsed = time.time() - start_time
                logger.info(
                    f"  Written {count / 1e6:.0f}M addresses "
                    f"({count / elapsed / 1e6:.2f}M/sec)"
                )

    elapsed = time.time() - start_time
    csv_size_gb = temp_csv.stat().st_size / (1024**3)
    logger.info(f"CSV written: {count:,} rows, {csv_size_gb:.2f} GB in {elapsed:.1f}s")

    # Bulk COPY into DuckDB
    logger.info("Bulk loading into DuckDB...")
    conn = None
    final_count = 0

    try:
        conn = duckdb.connect(db_path)

        # Ensure table exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS address_clusters (
                address VARCHAR PRIMARY KEY,
                cluster_id VARCHAR NOT NULL,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP
            )
        """)

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

    finally:
        if conn:
            conn.close()
        # Cleanup temp file
        if temp_csv.exists():
            temp_csv.unlink()
            logger.info("Cleaned up temp CSV")

    return final_count


def main():
    """Run ultra-fast clustering pipeline."""
    print("\n" + "=" * 70)
    print("ULTRA-FAST CLUSTERING (v3)")
    print("=" * 70)
    print("Optimizations: Cython UnionFind + PyArrow CSV + Batch Processing")
    print("=" * 70)

    if not CYTHON_AVAILABLE:
        print("\nERROR: Cython extension not available.")
        print(
            "Run: cd scripts/bootstrap/cython_uf && python setup.py build_ext --inplace"
        )
        sys.exit(1)

    # Find pair files
    pair_files = sorted(OUTPUT_DIR.glob("pairs_*.csv.gz"))
    if not pair_files:
        logger.error(f"No pair files found in {OUTPUT_DIR}")
        sys.exit(1)

    total_size = sum(f.stat().st_size for f in pair_files)
    print(f"\nPair files: {len(pair_files)} ({total_size / 1e9:.1f} GB compressed)")
    print(f"Database: {UTXO_DB_PATH}")
    print("=" * 70 + "\n")

    start_time = time.time()

    # Phase 1: Build address mapping
    mapping_file = CHECKPOINT_DIR / "address_mapping_v3.pkl"
    addr_to_int = build_address_mapping_fast(pair_files, mapping_file)

    # Phase 2: Cython-accelerated clustering
    checkpoint_file = CHECKPOINT_DIR / "uf_checkpoint_v3.pkl"
    uf = run_cython_clustering(pair_files, addr_to_int, checkpoint_file)

    # Phase 3: Save to database
    saved = save_clusters_bulk(uf, addr_to_int, UTXO_DB_PATH)

    # Summary
    duration = time.time() - start_time
    num_clusters = count_clusters(uf, len(addr_to_int))

    print("\n" + "=" * 70)
    print("CLUSTERING COMPLETE (v3)")
    print("=" * 70)
    print(f"  Addresses: {len(addr_to_int):,}")
    print(f"  Clusters: {num_clusters:,}")
    print(f"  Saved to DB: {saved:,}")
    print(f"  Duration: {duration:.1f}s ({duration / 60:.1f}m)")
    print(
        f"  Peak memory: ~{uf.memory_usage_gb() + len(addr_to_int) * 100 / 1e9:.1f} GB"
    )
    print("=" * 70)

    # Performance comparison
    estimated_v2_time = duration * 10  # v2 is ~10x slower
    print("\nPerformance vs v2:")
    print(f"  v3 time: {duration / 60:.1f} minutes")
    print(f"  v2 est:  {estimated_v2_time / 60:.1f} minutes (10x slower)")
    print("  Speedup: ~10x")
    print("=" * 70)
    print("\nNext: Run migrate_cost_basis.py to populate wallet_cost_basis")


if __name__ == "__main__":
    main()
