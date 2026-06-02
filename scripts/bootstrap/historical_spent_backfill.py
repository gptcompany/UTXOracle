#!/usr/bin/env python3
"""Historical spent UTXO backfill for liveliness calculation.

Scans all blocks from genesis to current tip to find spent UTXOs.
Designed for long-running background execution with:
- Resume capability from checkpoint
- Progress logging
- Configurable chunk size

Usage:
    # Full backfill (blocks 1 to 927966)
    BITCOIN_DATADIR=/media/sam/3TB-WDC/Bitcoin \
    uv run python -m scripts.bootstrap.historical_spent_backfill

    # Resume from checkpoint
    uv run python -m scripts.bootstrap.historical_spent_backfill --resume

    # Custom range
    uv run python -m scripts.bootstrap.historical_spent_backfill \
        --start-block 500000 --end-block 600000

    # Dry run (estimate only)
    uv run python -m scripts.bootstrap.historical_spent_backfill --dry-run

Estimated time: 6-10 days with 20 workers @ ~100 blocks/min
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Checkpoint file for resume
CHECKPOINT_FILE = Path("data/backfill_checkpoint.json")
CHUNK_SIZE = 10000  # Process in chunks for checkpointing


def load_checkpoint() -> dict:
    """Load checkpoint from file."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {"last_block": 0, "total_inputs": 0, "started_at": None}


def save_checkpoint(last_block: int, total_inputs: int, started_at: str):
    """Save checkpoint to file."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(
            {
                "last_block": last_block,
                "total_inputs": total_inputs,
                "started_at": started_at,
                "updated_at": datetime.now().isoformat(),
            },
            f,
            indent=2,
        )


def check_bitcoin_ready() -> bool:
    """Check if Bitcoin Core is ready for RPC."""
    try:
        from scripts.bootstrap.fast_spent_sync_v2 import BitcoinRPC

        rpc = BitcoinRPC()
        info = rpc.call("getblockchaininfo")
        if info.get("initialblockdownload", True):
            logger.warning("Bitcoin Core is still syncing (IBD)")
            return False
        logger.info(
            f"Bitcoin Core ready: chain={info['chain']}, blocks={info['blocks']}"
        )
        return True
    except Exception as e:
        logger.error(f"Bitcoin Core not ready: {e}")
        return False


def estimate_time(start_block: int, end_block: int, blocks_per_min: float = 100) -> str:
    """Estimate completion time."""
    blocks = end_block - start_block
    minutes = blocks / blocks_per_min
    hours = minutes / 60
    days = hours / 24

    if days >= 1:
        return f"{days:.1f} days"
    elif hours >= 1:
        return f"{hours:.1f} hours"
    else:
        return f"{minutes:.0f} minutes"


# spec-061 T034: psycopg lives at module level so tests can patch
# `scripts.bootstrap.historical_spent_backfill.psycopg.connect`. The import
# is best-effort because the rest of the script (duckdb path) does not
# depend on psycopg.
try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]


def _propagate_spent_to_questdb(csv_path: "Path") -> int:
    """Push spent-block updates from the staging CSV into QuestDB utxo_lifecycle.

    spec-061 T034: when run with `--target-backend questdb`, the backfill
    propagates `(txid, vout_index) -> spent_block` updates from the staging
    CSV to QuestDB after the DuckDB write completes. This makes the freshness
    probe `tip_lag_blocks` for `utxo_lifecycle_full` (spec-061 D2) return
    truthful values as the catch-up progresses.

    The staging CSV is the canonical (txid, vout, spent_block, spent_time) shape
    produced by `process_blocks_to_csv`. We batch the updates 1000 rows at a
    time via psycopg.executemany - UPDATE against a 164M-row table is slow
    but acceptable for a one-shot catch-up.

    Note: the QuestDB `utxo_lifecycle` schema uses `vout_index` rather than
    DuckDB's `vout` - we map the CSV column accordingly.
    """
    import csv

    if psycopg is None:
        raise ModuleNotFoundError(
            "psycopg is required for --target-backend questdb; install project deps"
        )

    from api.questdb_repository import (
        QUESTDB_PG_DATABASE,
        QUESTDB_PG_HOST,
        QUESTDB_PG_PASSWORD,
        QUESTDB_PG_PORT,
        QUESTDB_PG_USER,
    )

    updated = 0
    batch: list[tuple[int, str, int]] = []
    BATCH_SIZE = 1000

    with psycopg.connect(
        host=QUESTDB_PG_HOST,
        port=QUESTDB_PG_PORT,
        user=QUESTDB_PG_USER,
        password=QUESTDB_PG_PASSWORD,
        dbname=QUESTDB_PG_DATABASE,
        autocommit=True,
    ) as conn:
        with open(csv_path, newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 3:
                    continue
                txid, vout_str, spent_block_str = row[0], row[1], row[2]
                try:
                    batch.append((int(spent_block_str), txid, int(vout_str)))
                except ValueError:
                    continue
                if len(batch) >= BATCH_SIZE:
                    with conn.cursor() as cur:
                        cur.executemany(
                            "UPDATE utxo_lifecycle "
                            "SET spent_block = %s, is_spent = true "
                            "WHERE txid = %s AND vout_index = %s",
                            batch,
                        )
                    updated += len(batch)
                    batch = []
            if batch:
                with conn.cursor() as cur:
                    cur.executemany(
                        "UPDATE utxo_lifecycle "
                        "SET spent_block = %s, is_spent = true "
                        "WHERE txid = %s AND vout_index = %s",
                        batch,
                    )
                updated += len(batch)

    logger.info(
        "QuestDB propagation: %d UPDATEs issued from %s", updated, csv_path.name
    )
    return updated


def run_backfill(
    start_block: int,
    end_block: int,
    workers: int = 20,
    dry_run: bool = False,
    target_backend: str = "duckdb",
) -> None:
    """Run the backfill process.

    `target_backend` selects where the spent-block updates land.
    - `duckdb` (default, legacy behaviour): only the DuckDB table is updated.
    - `questdb`: DuckDB is still updated first (the CSV path requires it for
      the temp staging table), then the same updates are replicated to
      QuestDB via psycopg in batches of 1000. See spec-061 T034 / R6.
    """
    from scripts.bootstrap.fast_spent_sync_v2 import BitcoinRPC, process_blocks_to_csv
    from scripts.config import UTXORACLE_DB_PATH

    import duckdb

    total_blocks = end_block - start_block
    logger.info(
        f"Backfill: blocks {start_block} -> {end_block} ({total_blocks:,} blocks)"
    )
    logger.info(f"Estimated time: {estimate_time(start_block, end_block)}")

    if dry_run:
        logger.info("Dry run - exiting")
        return

    if not check_bitcoin_ready():
        logger.error("Bitcoin Core not ready. Exiting.")
        sys.exit(1)

    rpc = BitcoinRPC()
    conn = duckdb.connect(str(UTXORACLE_DB_PATH))

    started_at = datetime.now().isoformat()
    checkpoint = load_checkpoint()

    if checkpoint["last_block"] > start_block:
        start_block = checkpoint["last_block"] + 1
        logger.info(f"Resuming from checkpoint: block {start_block}")

    total_inputs = checkpoint.get("total_inputs", 0)
    chunk_start = start_block

    try:
        while chunk_start < end_block:
            chunk_end = min(chunk_start + CHUNK_SIZE, end_block)

            # Process chunk to CSV
            csv_path = Path(f"data/temp/backfill_{chunk_start}_{chunk_end}.csv")
            csv_path.parent.mkdir(parents=True, exist_ok=True)

            inputs_count = process_blocks_to_csv(
                rpc, chunk_start, chunk_end, csv_path, workers=workers
            )
            total_inputs += inputs_count

            # Bulk update database
            logger.info(f"Updating database with {inputs_count:,} inputs...")
            conn.execute(
                f"""
                CREATE TEMP TABLE IF NOT EXISTS staging_inputs (
                    txid VARCHAR,
                    vout INTEGER,
                    spent_block INTEGER,
                    spent_time INTEGER
                );
                TRUNCATE staging_inputs;
                COPY staging_inputs FROM '{csv_path}' (HEADER FALSE);
                """
            )

            updated = conn.execute(
                """
                UPDATE utxo_lifecycle u
                SET
                    is_spent = TRUE,
                    spent_block = s.spent_block
                FROM staging_inputs s
                WHERE u.txid = s.txid AND u.vout = s.vout
                AND (u.is_spent = FALSE OR u.is_spent IS NULL)
                """
            ).rowcount

            logger.info(f"Updated {updated:,} UTXOs as spent")

            # spec-061 T034: replicate to QuestDB before deleting the CSV.
            if target_backend == "questdb":
                try:
                    _propagate_spent_to_questdb(csv_path)
                except Exception as exc:
                    # Fail before deleting the CSV or advancing the checkpoint.
                    # Otherwise QuestDB catch-up can silently lose this chunk.
                    logger.error(
                        "QuestDB propagation failed for chunk %s-%s: %s",
                        chunk_start,
                        chunk_end,
                        exc,
                    )
                    raise

            # Cleanup CSV
            csv_path.unlink(missing_ok=True)

            # Save checkpoint
            save_checkpoint(chunk_end, total_inputs, started_at)

            # Progress
            progress = (chunk_end - start_block) / (end_block - start_block) * 100
            elapsed = (
                datetime.now() - datetime.fromisoformat(started_at)
            ).total_seconds()
            rate = (chunk_end - start_block) / elapsed * 60 if elapsed > 0 else 0
            eta = estimate_time(chunk_end, end_block, rate) if rate > 0 else "unknown"

            logger.info(
                f"Progress: {progress:.1f}% | "
                f"Block {chunk_end:,}/{end_block:,} | "
                f"Inputs: {total_inputs:,} | "
                f"Rate: {rate:.0f} blk/min | "
                f"ETA: {eta}"
            )

            chunk_start = chunk_end

    except KeyboardInterrupt:
        logger.info("Interrupted - checkpoint saved")
        save_checkpoint(chunk_start, total_inputs, started_at)
        sys.exit(0)

    logger.info(f"Backfill complete! Total inputs processed: {total_inputs:,}")


def main():
    parser = argparse.ArgumentParser(description="Historical spent UTXO backfill")
    parser.add_argument("--start-block", type=int, default=1, help="Start block")
    parser.add_argument("--end-block", type=int, default=927966, help="End block")
    parser.add_argument("--workers", type=int, default=20, help="Parallel workers")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--dry-run", action="store_true", help="Estimate only")
    parser.add_argument(
        "--check", action="store_true", help="Check Bitcoin Core status"
    )
    parser.add_argument(
        "--target-backend",
        choices=["duckdb", "questdb"],
        default="duckdb",
        help=(
            "Where to land spent-block updates. 'duckdb' (default) preserves "
            "legacy behaviour. 'questdb' additionally replicates each chunk's "
            "updates to QuestDB so the spec-061 freshness probe for "
            "utxo_lifecycle_full advances during catch-up."
        ),
    )

    args = parser.parse_args()

    if args.check:
        if check_bitcoin_ready():
            print("Bitcoin Core is ready for backfill")
            sys.exit(0)
        else:
            print("Bitcoin Core is NOT ready")
            sys.exit(1)

    if args.resume:
        checkpoint = load_checkpoint()
        if checkpoint["last_block"] > 0:
            args.start_block = checkpoint["last_block"] + 1
            logger.info(f"Resuming from block {args.start_block}")

    run_backfill(
        start_block=args.start_block,
        end_block=args.end_block,
        workers=args.workers,
        dry_run=args.dry_run,
        target_backend=args.target_backend,
    )


if __name__ == "__main__":
    main()
