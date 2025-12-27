#!/usr/bin/env python3
"""
Database consolidation migration script.

Consolidates all UTXOracle databases into a single data/utxoracle.duckdb file.

Usage:
    python -m scripts.migrations.consolidate_databases --dry-run
    python -m scripts.migrations.consolidate_databases
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Source databases
UTXO_LIFECYCLE_PATH = Path("data/utxo_lifecycle.duckdb")
NVME_CACHE_PATH = Path(
    "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
)

# Target database
TARGET_PATH = Path("data/utxoracle.duckdb")

# Tables to migrate from NVMe cache
CACHE_TABLES = ["price_analysis", "alert_events", "metrics", "intraday_prices"]


def create_metric_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """
    Create empty metric tables for daily calculated values.

    Creates: sopr_daily, nupl_daily, mvrv_daily, realized_cap_daily, cointime_daily
    """
    logger.info("Creating metric tables...")

    # SOPR Daily - Spent Output Profit Ratio
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sopr_daily (
            date DATE PRIMARY KEY,
            sopr DOUBLE,
            sopr_adjusted DOUBLE,
            spent_volume DOUBLE,
            profit_volume DOUBLE,
            loss_volume DOUBLE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # NUPL Daily - Net Unrealized Profit/Loss
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nupl_daily (
            date DATE PRIMARY KEY,
            nupl DOUBLE,
            market_cap DOUBLE,
            realized_cap DOUBLE,
            unrealized_profit DOUBLE,
            unrealized_loss DOUBLE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # MVRV Daily - Market Value to Realized Value
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mvrv_daily (
            date DATE PRIMARY KEY,
            mvrv DOUBLE,
            mvrv_z DOUBLE,
            market_cap DOUBLE,
            realized_cap DOUBLE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Realized Cap Daily
    conn.execute("""
        CREATE TABLE IF NOT EXISTS realized_cap_daily (
            date DATE PRIMARY KEY,
            realized_cap DOUBLE,
            total_supply DOUBLE,
            average_cost_basis DOUBLE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Cointime Daily - Liveliness, Vaultedness, AVIV
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cointime_daily (
            date DATE PRIMARY KEY,
            liveliness DOUBLE,
            vaultedness DOUBLE,
            activity_to_vaultedness_ratio DOUBLE,
            coindays_created DOUBLE,
            coindays_destroyed DOUBLE,
            true_market_mean DOUBLE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    logger.info(
        "Created 5 metric tables: sopr_daily, nupl_daily, mvrv_daily, realized_cap_daily, cointime_daily"
    )


def migrate_cache_tables(
    source_path: str, target_conn: duckdb.DuckDBPyConnection
) -> None:
    """
    Migrate tables from cache database to target.

    Copies: price_analysis, alert_events, metrics, intraday_prices
    Skips tables that don't exist in source.
    """
    logger.info(f"Migrating cache tables from {source_path}...")

    # ATTACH source database (DuckDB format)
    target_conn.execute(f"ATTACH '{source_path}' AS source_db (READ_ONLY)")

    try:
        # Get list of tables in source using SHOW ALL TABLES
        all_tables = target_conn.execute("SHOW ALL TABLES").fetchall()
        # Filter for source_db tables (first column is database name)
        source_table_names = {t[2] for t in all_tables if t[0] == "source_db"}

        for table_name in CACHE_TABLES:
            if table_name not in source_table_names:
                logger.warning(f"  Skipping {table_name} - not found in source")
                continue

            # Check if table has any rows
            count = target_conn.execute(
                f"SELECT COUNT(*) FROM source_db.{table_name}"
            ).fetchone()[0]

            if count == 0:
                logger.info(f"  Skipping {table_name} - empty table")
                continue

            # Check if table already exists in target
            target_tables = target_conn.execute("SHOW TABLES").fetchall()
            target_table_names = {t[0] for t in target_tables}

            if table_name in target_table_names:
                # Drop and recreate
                target_conn.execute(f"DROP TABLE IF EXISTS {table_name}")

            # Copy table
            target_conn.execute(
                f"CREATE TABLE {table_name} AS SELECT * FROM source_db.{table_name}"
            )
            logger.info(f"  Migrated {table_name}: {count} rows")

    finally:
        target_conn.execute("DETACH source_db")


def migrate(dry_run: bool = False) -> dict:
    """
    Run the full database consolidation migration.

    Steps:
    1. Verify source databases exist
    2. Rename utxo_lifecycle.duckdb -> utxoracle.duckdb (or copy for safety)
    3. Create metric tables
    4. Migrate cache tables from NVMe
    5. Update symlinks

    Args:
        dry_run: If True, only report what would be done

    Returns:
        dict with migration results
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "steps": [],
    }

    logger.info("=" * 60)
    logger.info("UTXOracle Database Consolidation Migration")
    logger.info("=" * 60)

    # Step 1: Verify sources
    if not UTXO_LIFECYCLE_PATH.exists():
        raise FileNotFoundError(f"Source database not found: {UTXO_LIFECYCLE_PATH}")

    logger.info(
        f"Source: {UTXO_LIFECYCLE_PATH} ({UTXO_LIFECYCLE_PATH.stat().st_size / 1e9:.2f} GB)"
    )

    if NVME_CACHE_PATH.exists():
        logger.info(
            f"Cache: {NVME_CACHE_PATH} ({NVME_CACHE_PATH.stat().st_size / 1e6:.2f} MB)"
        )
    else:
        logger.warning(f"Cache not found: {NVME_CACHE_PATH}")

    # Step 2: Rename/copy main database
    if TARGET_PATH.exists() and TARGET_PATH != UTXO_LIFECYCLE_PATH:
        if dry_run:
            logger.info(f"WOULD REMOVE: orphaned {TARGET_PATH}")
        else:
            # Backup orphaned file first
            backup_path = TARGET_PATH.with_suffix(".duckdb.bak")
            shutil.move(TARGET_PATH, backup_path)
            logger.info(f"Moved orphaned {TARGET_PATH} to {backup_path}")

    if UTXO_LIFECYCLE_PATH != TARGET_PATH:
        if dry_run:
            logger.info(f"WOULD RENAME: {UTXO_LIFECYCLE_PATH} -> {TARGET_PATH}")
            results["steps"].append({"action": "rename", "dry_run": True})
        else:
            # Use rename (atomic on same filesystem)
            shutil.move(UTXO_LIFECYCLE_PATH, TARGET_PATH)
            logger.info(f"Renamed {UTXO_LIFECYCLE_PATH} -> {TARGET_PATH}")
            results["steps"].append(
                {
                    "action": "rename",
                    "from": str(UTXO_LIFECYCLE_PATH),
                    "to": str(TARGET_PATH),
                }
            )

    # Step 3 & 4: Open target and run migrations
    if dry_run:
        logger.info("WOULD CREATE: metric tables")
        logger.info("WOULD MIGRATE: cache tables from NVMe")
        results["steps"].append({"action": "create_metric_tables", "dry_run": True})
        results["steps"].append({"action": "migrate_cache_tables", "dry_run": True})
    else:
        conn = duckdb.connect(str(TARGET_PATH))
        try:
            create_metric_tables(conn)
            results["steps"].append({"action": "create_metric_tables", "success": True})

            if NVME_CACHE_PATH.exists():
                migrate_cache_tables(str(NVME_CACHE_PATH), conn)
                results["steps"].append(
                    {"action": "migrate_cache_tables", "success": True}
                )
            else:
                logger.warning("Skipping cache migration - source not found")
                results["steps"].append(
                    {"action": "migrate_cache_tables", "skipped": True}
                )

        finally:
            conn.close()

    # Step 5: Create backward-compatible symlink
    symlink_path = UTXO_LIFECYCLE_PATH
    if not symlink_path.exists() and not dry_run:
        symlink_path.symlink_to(TARGET_PATH.name)
        logger.info(f"Created symlink: {symlink_path} -> {TARGET_PATH.name}")
        results["steps"].append({"action": "create_symlink", "path": str(symlink_path)})

    logger.info("=" * 60)
    if dry_run:
        logger.info("DRY RUN COMPLETE - no changes made")
    else:
        logger.info("MIGRATION COMPLETE")
    logger.info("=" * 60)

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Consolidate UTXOracle databases")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done"
    )
    args = parser.parse_args()

    try:
        results = migrate(dry_run=args.dry_run)
        if not args.dry_run:
            logger.info(f"Migration completed with {len(results['steps'])} steps")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    main()
