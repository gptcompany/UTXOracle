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
from datetime import datetime

import duckdb

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
# B6 fix: Use .duckdb extension to match api/main.py UTXO_DB_PATH default
UTXO_DB_PATH = "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxo_lifecycle.duckdb"


def migrate_cost_basis(
    db_path: str = DEFAULT_DB_PATH,
    utxo_db_path: str = UTXO_DB_PATH,
    batch_size: int = 10000,
) -> dict:
    """Migrate UTXO cost basis data to wallet-level tracking.

    Args:
        db_path: Path to main DuckDB database with wallet_cost_basis table
        utxo_db_path: Path to UTXO lifecycle database
        batch_size: Number of records to process per batch

    Returns:
        Statistics dict with migration results
    """
    stats = {
        "clusters_processed": 0,
        "entries_created": 0,
        "errors": 0,
        "start_time": datetime.now().isoformat(),
    }

    try:
        # Connect to databases
        conn = duckdb.connect(db_path)
        utxo_conn = duckdb.connect(utxo_db_path, read_only=True)

        # Check if address_clusters table has data
        cluster_count = conn.execute(
            "SELECT COUNT(DISTINCT cluster_id) FROM address_clusters"
        ).fetchone()[0]

        if cluster_count == 0:
            logger.warning("No address clusters found. Run clustering first.")
            return stats

        logger.info(f"Found {cluster_count} address clusters to process")

        # Get all cluster IDs
        clusters = conn.execute(
            "SELECT DISTINCT cluster_id FROM address_clusters"
        ).fetchall()

        for (cluster_id,) in clusters:
            try:
                # Get all addresses in this cluster
                addresses = conn.execute(
                    "SELECT address FROM address_clusters WHERE cluster_id = ?",
                    [cluster_id],
                ).fetchall()

                address_list = [addr[0] for addr in addresses]

                if not address_list:
                    continue

                # For each cluster, find the earliest UTXO creations
                # (representing when BTC first entered this wallet)
                # This query finds acquisitions: UTXOs created by transactions
                # where the input addresses are NOT in the same cluster
                # (i.e., BTC came from outside this entity)

                # Simplified approach: Use UTXO creation events with their prices
                # A more sophisticated approach would track inter-cluster transfers

                # Query UTXOs created to addresses in this cluster
                placeholders = ",".join(["?" for _ in address_list])
                acquisition_query = f"""
                    SELECT
                        creation_block,
                        SUM(btc_value) as btc_amount,
                        AVG(creation_price_usd) as avg_price,
                        MIN(creation_timestamp) as earliest_timestamp
                    FROM utxo_lifecycle_full
                    WHERE address IN ({placeholders})
                      AND creation_price_usd > 0
                    GROUP BY creation_block
                    ORDER BY creation_block
                """

                try:
                    results = utxo_conn.execute(
                        acquisition_query, address_list
                    ).fetchall()

                    for block, btc_amount, avg_price, timestamp in results:
                        if btc_amount and avg_price:
                            try:
                                conn.execute(
                                    """
                                    INSERT INTO wallet_cost_basis (
                                        cluster_id, acquisition_block, btc_amount,
                                        acquisition_price, acquisition_timestamp
                                    )
                                    VALUES (?, ?, ?, ?, ?)
                                    ON CONFLICT (cluster_id, acquisition_block)
                                    DO UPDATE SET
                                        btc_amount = btc_amount + EXCLUDED.btc_amount
                                    """,
                                    [
                                        cluster_id,
                                        block,
                                        btc_amount,
                                        avg_price,
                                        timestamp or datetime.now(),
                                    ],
                                )
                                stats["entries_created"] += 1
                            except Exception as e:
                                logger.debug(f"Insert error: {e}")
                                stats["errors"] += 1

                except Exception as e:
                    logger.debug(f"Query error for cluster {cluster_id}: {e}")
                    stats["errors"] += 1

                stats["clusters_processed"] += 1

                if stats["clusters_processed"] % 1000 == 0:
                    logger.info(
                        f"Processed {stats['clusters_processed']}/{cluster_count} clusters"
                    )

            except Exception as e:
                logger.warning(f"Error processing cluster {cluster_id}: {e}")
                stats["errors"] += 1

        conn.close()
        utxo_conn.close()

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
            logger.info(f"Address clusters to process: {cluster_count}")

            existing = conn.execute(
                "SELECT COUNT(*) FROM wallet_cost_basis"
            ).fetchone()[0]
            logger.info(f"Existing wallet_cost_basis entries: {existing}")
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
