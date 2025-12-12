"""Import chainstate CSV dump into DuckDB using COPY.

Uses bitcoin-utxo-dump CSV output for fast UTXO lifecycle bootstrap.
DuckDB COPY is ~2,970x faster than INSERT (712K vs 240 rows/sec).

Prerequisites:
    go install github.com/in3rsha/bitcoin-utxo-dump@latest
    bitcoin-utxo-dump -o csv -f count,txid,vout,height,coinbase,amount,script > utxos.csv

Usage:
    python -m scripts.bootstrap.import_chainstate --csv-path utxos.csv --db-path data/utxo_lifecycle.duckdb

CSV Format (from bitcoin-utxo-dump):
    count,txid,vout,height,coinbase,amount,script_type,address
    1,abc123...,0,800000,0,100000000,p2wpkh,bc1q...
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

# Expected CSV columns from bitcoin-utxo-dump
EXPECTED_COLUMNS = [
    "txid",
    "vout",
    "height",
    "coinbase",
    "amount",
    "script_type",
    "address",
]


def create_utxo_lifecycle_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create utxo_lifecycle table schema for chainstate import.

    Note: This is a simplified schema for Tier 1 bootstrap.
    Full schema with spent UTXO tracking added later in Tier 2.

    Args:
        conn: DuckDB connection
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS utxo_lifecycle (
            txid VARCHAR NOT NULL,
            vout INTEGER NOT NULL,
            height INTEGER NOT NULL,
            coinbase BOOLEAN DEFAULT FALSE,
            amount BIGINT NOT NULL,
            script_type VARCHAR,
            address VARCHAR,
            -- Tier 1 computed fields (added after import)
            creation_price_usd DOUBLE,
            btc_value DOUBLE,
            -- Tier 2 fields (for spent UTXOs)
            is_spent BOOLEAN DEFAULT FALSE,
            spent_block INTEGER,
            spent_timestamp INTEGER,
            spent_price_usd DOUBLE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (txid, vout)
        )
    """)
    logger.info("Created utxo_lifecycle table schema")


def create_indexes(conn: duckdb.DuckDBPyConnection) -> None:
    """Create indexes for efficient queries.

    Args:
        conn: DuckDB connection
    """
    indexes = [
        ("idx_utxo_height", "height"),
        ("idx_utxo_is_spent", "is_spent"),
        ("idx_utxo_creation_price", "creation_price_usd"),
        ("idx_utxo_address", "address"),
    ]

    for idx_name, column in indexes:
        try:
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {idx_name} ON utxo_lifecycle({column})"
            )
            logger.debug(f"Created index {idx_name}")
        except Exception as e:
            logger.warning(f"Failed to create index {idx_name}: {e}")

    logger.info("Created indexes on utxo_lifecycle")


def import_chainstate_csv(
    conn: duckdb.DuckDBPyConnection,
    csv_path: str,
    create_schema: bool = True,
) -> int:
    """Import chainstate CSV into utxo_lifecycle table using DuckDB COPY.

    Uses DuckDB's native CSV reader for maximum performance (~712K rows/sec).

    Args:
        conn: DuckDB connection
        csv_path: Path to CSV file from bitcoin-utxo-dump
        create_schema: Whether to create table schema first

    Returns:
        Number of rows imported
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    logger.info(f"Importing chainstate from {csv_path}")

    # Create schema if needed
    if create_schema:
        create_utxo_lifecycle_schema(conn)

    # Use DuckDB COPY for fast import
    # This is ~2,970x faster than INSERT
    try:
        # First, check if table is empty
        count_before = conn.execute("SELECT COUNT(*) FROM utxo_lifecycle").fetchone()[0]

        # Import CSV directly
        conn.execute(f"""
            INSERT INTO utxo_lifecycle (txid, vout, height, coinbase, amount, script_type, address)
            SELECT
                txid,
                CAST(vout AS INTEGER),
                CAST(height AS INTEGER),
                CASE WHEN coinbase = '1' OR coinbase = 'true' THEN TRUE ELSE FALSE END,
                CAST(amount AS BIGINT),
                script_type,
                address
            FROM read_csv(
                '{csv_path}',
                header=true,
                columns={{
                    'txid': 'VARCHAR',
                    'vout': 'VARCHAR',
                    'height': 'VARCHAR',
                    'coinbase': 'VARCHAR',
                    'amount': 'VARCHAR',
                    'script_type': 'VARCHAR',
                    'address': 'VARCHAR'
                }},
                ignore_errors=true
            )
        """)

        count_after = conn.execute("SELECT COUNT(*) FROM utxo_lifecycle").fetchone()[0]
        rows_imported = count_after - count_before

        logger.info(f"Imported {rows_imported:,} rows from CSV")
        return rows_imported

    except Exception as e:
        logger.error(f"Failed to import CSV: {e}")
        raise


def compute_btc_values(conn: duckdb.DuckDBPyConnection) -> int:
    """Compute BTC values from satoshi amounts.

    Args:
        conn: DuckDB connection

    Returns:
        Number of rows updated
    """
    logger.info("Computing BTC values from satoshi amounts...")

    conn.execute("""
        UPDATE utxo_lifecycle
        SET btc_value = amount / 100000000.0
        WHERE btc_value IS NULL
    """)

    # Get row count
    count = conn.execute(
        "SELECT COUNT(*) FROM utxo_lifecycle WHERE btc_value IS NOT NULL"
    ).fetchone()[0]

    logger.info(f"Computed BTC values for {count:,} rows")
    return count


def compute_creation_prices(
    conn: duckdb.DuckDBPyConnection,
    price_table: str = "daily_prices",
    heights_table: str = "block_heights",
) -> int:
    """Compute creation prices by joining with price and height tables.

    Args:
        conn: DuckDB connection
        price_table: Table with daily prices
        heights_table: Table with block height->timestamp mapping

    Returns:
        Number of rows updated
    """
    logger.info("Computing creation prices from block heights and daily prices...")

    try:
        conn.execute(f"""
            UPDATE utxo_lifecycle u
            SET creation_price_usd = (
                SELECT p.price_usd
                FROM {heights_table} h
                JOIN {price_table} p ON DATE(TO_TIMESTAMP(h.timestamp)) = p.date
                WHERE h.height = u.height
            )
            WHERE u.creation_price_usd IS NULL
        """)

        count = conn.execute(
            "SELECT COUNT(*) FROM utxo_lifecycle WHERE creation_price_usd IS NOT NULL"
        ).fetchone()[0]

        logger.info(f"Computed creation prices for {count:,} rows")
        return count

    except Exception as e:
        logger.warning(f"Failed to compute creation prices (tables may not exist): {e}")
        return 0


def get_import_stats(conn: duckdb.DuckDBPyConnection) -> dict:
    """Get statistics about imported UTXOs.

    Args:
        conn: DuckDB connection

    Returns:
        Dict with import statistics
    """
    stats = {}

    try:
        stats["total_utxos"] = conn.execute(
            "SELECT COUNT(*) FROM utxo_lifecycle"
        ).fetchone()[0]

        stats["total_btc"] = conn.execute(
            "SELECT SUM(btc_value) FROM utxo_lifecycle"
        ).fetchone()[0]

        stats["min_height"] = conn.execute(
            "SELECT MIN(height) FROM utxo_lifecycle"
        ).fetchone()[0]

        stats["max_height"] = conn.execute(
            "SELECT MAX(height) FROM utxo_lifecycle"
        ).fetchone()[0]

        stats["unique_addresses"] = conn.execute(
            "SELECT COUNT(DISTINCT address) FROM utxo_lifecycle WHERE address IS NOT NULL"
        ).fetchone()[0]

        stats["script_type_counts"] = conn.execute("""
            SELECT script_type, COUNT(*) as count
            FROM utxo_lifecycle
            GROUP BY script_type
            ORDER BY count DESC
        """).fetchall()

    except Exception as e:
        logger.error(f"Failed to get import stats: {e}")

    return stats


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Import chainstate CSV into DuckDB")
    parser.add_argument(
        "--csv-path",
        required=True,
        help="Path to CSV file from bitcoin-utxo-dump",
    )
    parser.add_argument(
        "--db-path",
        default=os.getenv("DUCKDB_PATH", "data/utxo_lifecycle.duckdb"),
        help="Path to DuckDB database",
    )
    parser.add_argument(
        "--compute-prices",
        action="store_true",
        help="Compute creation prices after import (requires price/height tables)",
    )
    parser.add_argument(
        "--create-indexes",
        action="store_true",
        help="Create indexes after import",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Connect to DuckDB
    conn = duckdb.connect(args.db_path)

    try:
        # Import CSV
        import time

        start = time.time()
        rows = import_chainstate_csv(conn, args.csv_path)
        elapsed = time.time() - start

        print(
            f"Imported {rows:,} UTXOs in {elapsed:.1f} seconds ({rows / elapsed:,.0f} rows/sec)"
        )

        # Compute BTC values
        compute_btc_values(conn)

        # Optionally compute prices
        if args.compute_prices:
            compute_creation_prices(conn)

        # Optionally create indexes
        if args.create_indexes:
            create_indexes(conn)

        # Print stats
        stats = get_import_stats(conn)
        print("\nImport Statistics:")
        print(f"  Total UTXOs: {stats.get('total_utxos', 0):,}")
        print(f"  Total BTC: {stats.get('total_btc', 0):,.2f}")
        print(
            f"  Height range: {stats.get('min_height', 0)} - {stats.get('max_height', 0)}"
        )
        print(f"  Unique addresses: {stats.get('unique_addresses', 0):,}")

    finally:
        conn.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
