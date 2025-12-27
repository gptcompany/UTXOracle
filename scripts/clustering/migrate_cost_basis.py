#!/usr/bin/env python3
"""Migration Script for Wallet-Level Cost Basis (spec-013).

Populates the wallet_cost_basis table from existing UTXO lifecycle data,
using address clustering to identify wallet entities.

This script:
1. Loads existing address clusters
2. For each cluster, finds the original acquisition transactions
3. Records the acquisition price at the time BTC entered the cluster
4. Saves to wallet_cost_basis table

Usage:
    python scripts/clustering/migrate_cost_basis.py [--db-path PATH]

Prerequisites:
- Address clustering must be populated (address_clusters table)
- UTXO lifecycle data with price history

Note: This is a one-time migration. Subsequent updates are handled by
the daily processing pipeline.
"""

import argparse
import logging
import os
from datetime import datetime

import duckdb

from scripts.config import UTXORACLE_DB_PATH

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Use environment variable or default to local dev path
DEFAULT_DB_PATH = str(UTXORACLE_DB_PATH)
# For now, both tables are in the same database
UTXO_DB_PATH = DEFAULT_DB_PATH


def migrate_cost_basis(
    db_path: str = DEFAULT_DB_PATH,
    utxo_db_path: str = UTXO_DB_PATH,
    batch_size: int = 10000,
) -> dict:
    """Migrate UTXO cost basis data to wallet-level tracking.

    Uses BULK SQL approach instead of cluster-by-cluster iteration.
    Much faster for large datasets (29M+ clusters).

    Args:
        db_path: Path to main DuckDB database with wallet_cost_basis table
        utxo_db_path: Path to UTXO lifecycle database
        batch_size: Number of records to process per batch

    Returns:
        Statistics dict with migration results
    """
    import time

    stats = {
        "clusters_processed": 0,
        "entries_created": 0,
        "errors": 0,
        "start_time": datetime.now().isoformat(),
    }

    try:
        # Connect to database (both tables in same DB now)
        conn = duckdb.connect(db_path)

        # Check if address_clusters table has data
        cluster_count = conn.execute(
            "SELECT COUNT(DISTINCT cluster_id) FROM address_clusters"
        ).fetchone()[0]

        if cluster_count == 0:
            logger.warning("No address clusters found. Run clustering first.")
            conn.close()
            return stats

        logger.info(f"Found {cluster_count:,} address clusters to process")

        # CRITICAL: Wrap DELETE + INSERT in transaction for atomicity
        # If INSERT fails after DELETE, we'd lose all data without transaction
        logger.info("Running bulk migration (DELETE + INSERT in transaction)...")
        start_time = time.time()

        conn.execute("BEGIN TRANSACTION")
        try:
            # Clear existing data
            conn.execute("DELETE FROM wallet_cost_basis")

            # BULK approach: Join address_clusters with utxo_lifecycle_full
            # and aggregate by cluster_id and creation_block in a single query
            # This query:
            # 1. Joins addresses to their clusters
            # 2. Groups UTXOs by cluster and creation block
            # 3. Aggregates BTC amount and WEIGHTED average price
            #    (BUG FIX: Simple AVG was wrong, must weight by BTC amount)
            conn.execute("""
                INSERT INTO wallet_cost_basis (
                    cluster_id,
                    acquisition_block,
                    btc_amount,
                    acquisition_price,
                    acquisition_timestamp
                )
                SELECT
                    ac.cluster_id,
                    u.creation_block,
                    SUM(u.btc_value) as btc_amount,
                    SUM(u.btc_value * u.creation_price_usd) / SUM(u.btc_value) as weighted_avg_price,
                    to_timestamp(MIN(u.creation_timestamp)) as earliest_timestamp
                FROM utxo_lifecycle_full u
                JOIN address_clusters ac ON u.address = ac.address
                WHERE u.creation_price_usd > 0
                  AND u.btc_value > 0
                GROUP BY ac.cluster_id, u.creation_block
                HAVING SUM(u.btc_value) > 0
            """)
            conn.execute("COMMIT")
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"Migration transaction failed, rolled back: {e}")
            raise

        elapsed = time.time() - start_time
        logger.info(f"Bulk migration completed in {elapsed:.1f}s")

        # Get statistics
        result = conn.execute("""
            SELECT
                COUNT(*) as entries,
                COUNT(DISTINCT cluster_id) as clusters
            FROM wallet_cost_basis
        """).fetchone()

        stats["entries_created"] = result[0]
        stats["clusters_processed"] = result[1]

        conn.close()

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        stats["error_message"] = str(e)

    stats["end_time"] = datetime.now().isoformat()
    return stats


def compute_wallet_realized_cap_from_db(
    db_path: str = DEFAULT_DB_PATH,
) -> float:
    """Compute total Realized Cap from wallet_cost_basis table.

    This is the production method for calculating Realized Cap,
    using wallet-level cost basis instead of UTXO-level.

    Args:
        db_path: Path to DuckDB database

    Returns:
        Total Realized Cap in USD
    """
    try:
        conn = duckdb.connect(db_path, read_only=True)

        # Sum (btc_amount * acquisition_price) for all entries
        result = conn.execute("""
            SELECT COALESCE(
                SUM(btc_amount * acquisition_price),
                0
            ) as realized_cap
            FROM wallet_cost_basis
        """).fetchone()

        conn.close()
        return result[0] if result else 0.0

    except Exception as e:
        logger.error(f"Failed to compute wallet realized cap: {e}")
        return 0.0


def get_cluster_realized_value_from_db(
    cluster_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> float:
    """Get realized value for a specific cluster from database.

    Args:
        cluster_id: Cluster identifier
        db_path: Path to DuckDB database

    Returns:
        Realized value for this cluster in USD
    """
    try:
        conn = duckdb.connect(db_path, read_only=True)

        result = conn.execute(
            """
            SELECT COALESCE(
                SUM(btc_amount * acquisition_price),
                0
            ) as realized_value
            FROM wallet_cost_basis
            WHERE cluster_id = ?
            """,
            [cluster_id],
        ).fetchone()

        conn.close()
        return result[0] if result else 0.0

    except Exception as e:
        logger.error(f"Failed to get cluster realized value: {e}")
        return 0.0


def main():
    """Run cost basis migration."""
    parser = argparse.ArgumentParser(
        description="Migrate UTXO cost basis to wallet-level tracking (spec-013)"
    )
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to main DuckDB database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--utxo-db-path",
        default=UTXO_DB_PATH,
        help=f"Path to UTXO lifecycle database (default: {UTXO_DB_PATH})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="Batch size for processing (default: 10000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show statistics without migrating",
    )

    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN: Would migrate cost basis from UTXO data")

        # Show current state
        try:
            conn = duckdb.connect(args.db_path, read_only=True)

            cluster_count = conn.execute(
                "SELECT COUNT(DISTINCT cluster_id) FROM address_clusters"
            ).fetchone()[0]
            non_singleton = conn.execute(
                "SELECT COUNT(*) FROM address_clusters WHERE cluster_id != address"
            ).fetchone()[0]
            logger.info(
                f"Address clusters: {cluster_count:,} ({non_singleton:,} non-singletons)"
            )

            utxo_count = conn.execute(
                "SELECT COUNT(*) FROM utxo_lifecycle_full WHERE creation_price_usd > 0"
            ).fetchone()[0]
            logger.info(f"UTXOs with price data: {utxo_count:,}")

            existing = conn.execute(
                "SELECT COUNT(*) FROM wallet_cost_basis"
            ).fetchone()[0]
            logger.info(f"Existing wallet_cost_basis entries: {existing:,}")
            conn.close()
        except Exception as e:
            logger.warning(f"Could not read database: {e}")
        return

    logger.info("Starting wallet cost basis migration...")

    stats = migrate_cost_basis(
        db_path=args.db_path,
        utxo_db_path=args.utxo_db_path,
        batch_size=args.batch_size,
    )

    logger.info("Migration complete!")
    logger.info(f"  Clusters processed: {stats['clusters_processed']}")
    logger.info(f"  Entries created: {stats['entries_created']}")
    logger.info(f"  Errors: {stats['errors']}")

    # Show realized cap
    realized_cap = compute_wallet_realized_cap_from_db(args.db_path)
    logger.info(f"  Wallet Realized Cap: ${realized_cap:,.2f}")


if __name__ == "__main__":
    main()
