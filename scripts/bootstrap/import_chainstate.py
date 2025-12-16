"""Import chainstate CSV dump into DuckDB using COPY.

Uses bitcoin-utxo-dump CSV output for fast UTXO lifecycle bootstrap.
DuckDB COPY is ~2,970x faster than INSERT (712K vs 240 rows/sec).

Prerequisites:
    go install github.com/in3rsha/bitcoin-utxo-dump@latest
    bitcoin-utxo-dump -db ~/.bitcoin/chainstate -o utxos.csv -f txid,vout,height,coinbase,amount,type,address

Usage:
    python -m scripts.bootstrap.import_chainstate --csv-path utxos.csv --db-path data/utxo_lifecycle.duckdb

CSV Format (from bitcoin-utxo-dump):
    txid,vout,height,coinbase,amount,type,address
    abc123...,0,800000,0,100000000,p2wpkh,bc1q...
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

# Expected CSV columns from bitcoin-utxo-dump (using -f txid,vout,height,coinbase,amount,type,address)
# Note: The tool outputs 'type' not 'script_type' for the output type field
EXPECTED_COLUMNS = [
    "txid",
    "vout",
    "height",
    "coinbase",
    "amount",
    "type",  # bitcoin-utxo-dump uses 'type', mapped to 'script_type' in our schema
    "address",
]


def create_utxo_lifecycle_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create UNIFIED utxo_lifecycle table schema.

    This is the CANONICAL schema used by ALL specs (017, 018, 020, 021).
    Design principles:
    - Store ONLY raw data from chainstate + Tier 2 spent metadata
    - Compute derived fields at query time (btc_value, realized_value, age_days, cohort)
    - Use VIEWs for backward compatibility with metrics expecting computed columns

    Schema evolution:
    - Tier 1: Chainstate import (txid, vout, creation_block, amount, is_coinbase)
    - Tier 2: Spent UTXO sync (is_spent, spent_block, spent_timestamp, spent_price_usd)

    Args:
        conn: DuckDB connection
    """
    # Core table: minimal storage, raw data only
    conn.execute("""
        CREATE TABLE IF NOT EXISTS utxo_lifecycle (
            -- Primary key (composite, natural from chainstate)
            txid VARCHAR NOT NULL,
            vout INTEGER NOT NULL,

            -- Tier 1: Creation data (from chainstate dump)
            creation_block INTEGER NOT NULL,      -- Block height when UTXO was created
            amount BIGINT NOT NULL,               -- Value in satoshis
            is_coinbase BOOLEAN DEFAULT FALSE,    -- Coinbase transaction output
            script_type VARCHAR,                  -- p2pkh, p2wpkh, p2sh, p2wsh, etc.
            address VARCHAR,                      -- Decoded address (if available)

            -- Tier 2: Spent data (from rpc-v3 sync)
            is_spent BOOLEAN DEFAULT FALSE,
            spent_block INTEGER,                  -- Block height when spent
            spent_timestamp BIGINT,               -- Unix timestamp when spent
            spent_price_usd DOUBLE,               -- BTC/USD price when spent

            -- Metadata
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (txid, vout)
        )
    """)
    logger.info("Created utxo_lifecycle table (unified schema)")


def create_utxo_lifecycle_view(conn: duckdb.DuckDBPyConnection) -> None:
    """Create VIEW with computed columns for metric queries.

    This VIEW provides backward compatibility with spec-017 metrics that
    expect columns like btc_value, creation_price_usd, realized_value_usd,
    age_days, cohort, sopr, outpoint.

    All computed at query time - no storage overhead.

    Requires:
        - daily_prices table (from build_price_table.py)
        - block_heights table (from build_block_heights.py)

    Args:
        conn: DuckDB connection
    """
    conn.execute("""
        CREATE OR REPLACE VIEW utxo_lifecycle_full AS
        SELECT
            -- Raw columns
            u.txid,
            u.vout,
            u.creation_block,
            u.amount,
            u.is_coinbase,
            u.script_type,
            u.address,
            u.is_spent,
            u.spent_block,
            u.spent_timestamp,
            u.spent_price_usd,
            u.created_at,

            -- Computed: outpoint (for spec-017 compatibility)
            u.txid || ':' || CAST(u.vout AS VARCHAR) AS outpoint,

            -- Computed: BTC value from satoshis
            CAST(u.amount AS DOUBLE) / 100000000.0 AS btc_value,

            -- Computed: Creation timestamp (from block_heights table)
            COALESCE(bh.timestamp, 0) AS creation_timestamp,

            -- Computed: Creation price (from daily_prices table)
            COALESCE(dp.price_usd, 0.0) AS creation_price_usd,

            -- Computed: Realized value at creation
            (CAST(u.amount AS DOUBLE) / 100000000.0) * COALESCE(dp.price_usd, 0.0) AS realized_value_usd,

            -- Computed: Age in blocks (requires current_block parameter - use NULL)
            NULL AS age_blocks,

            -- Computed: Age in days (approximate: blocks / 144)
            NULL AS age_days,

            -- Computed: Cohort (STH/LTH based on 155-day threshold)
            NULL AS cohort,

            -- Computed: SOPR (Spent Output Profit Ratio)
            CASE
                WHEN u.is_spent AND u.spent_price_usd > 0 AND COALESCE(dp.price_usd, 0) > 0
                THEN u.spent_price_usd / dp.price_usd
                ELSE NULL
            END AS sopr,

            -- Alias for spec-017 compatibility
            u.vout AS vout_index

        FROM utxo_lifecycle u
        LEFT JOIN block_heights bh ON u.creation_block = bh.height
        LEFT JOIN daily_prices dp ON CAST(to_timestamp(bh.timestamp) AS DATE) = dp.date
    """)
    logger.info("Created utxo_lifecycle_full VIEW (computed columns)")


def create_indexes(conn: duckdb.DuckDBPyConnection) -> None:
    """Create indexes for efficient metric queries.

    Indexes are optimized for the most common query patterns:
    - Filter by is_spent (URPD, Supply P/L)
    - Filter by creation_block (time-based metrics)
    - Filter by spent_block (SOPR, CDD, VDD)
    - Group by address (clustering metrics)

    Args:
        conn: DuckDB connection
    """
    indexes = [
        ("idx_utxo_creation_block", "creation_block"),
        ("idx_utxo_is_spent", "is_spent"),
        ("idx_utxo_spent_block", "spent_block"),
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

    CSV format from bitcoin-utxo-dump:
        txid,vout,height,coinbase,amount,script_type,address

    Column mapping (CSV -> unified schema):
        height -> creation_block
        coinbase -> is_coinbase

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

    # Use DuckDB COPY for fast import (~712K rows/sec)
    try:
        # Check row count before import
        count_before = conn.execute("SELECT COUNT(*) FROM utxo_lifecycle").fetchone()[0]

        # First, count rows in CSV to detect corruption later
        # Using DuckDB to count is fast even for large files
        csv_row_count = conn.execute(f"""
            SELECT COUNT(*) FROM read_csv(
                '{csv_path}',
                header=true,
                columns={{
                    'txid': 'VARCHAR',
                    'vout': 'VARCHAR',
                    'height': 'VARCHAR',
                    'coinbase': 'VARCHAR',
                    'amount': 'VARCHAR',
                    'type': 'VARCHAR',
                    'address': 'VARCHAR'
                }},
                ignore_errors=true
            )
        """).fetchone()[0]
        logger.info(f"CSV contains {csv_row_count:,} rows (excluding header)")

        # Import CSV with column mapping to unified schema
        # CSV columns from bitcoin-utxo-dump: txid, vout, height, coinbase, amount, type, address
        # Table columns: txid, vout, creation_block, is_coinbase, amount, script_type, address
        # Note: bitcoin-utxo-dump uses 'type' not 'script_type' for the output type field
        conn.execute(f"""
            INSERT INTO utxo_lifecycle (txid, vout, creation_block, is_coinbase, amount, script_type, address)
            SELECT
                txid,
                CAST(vout AS INTEGER),
                CAST(height AS INTEGER) AS creation_block,
                CASE WHEN coinbase = '1' OR LOWER(coinbase) = 'true' THEN TRUE ELSE FALSE END AS is_coinbase,
                CAST(amount AS BIGINT),
                type AS script_type,
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
                    'type': 'VARCHAR',
                    'address': 'VARCHAR'
                }},
                ignore_errors=true
            )
        """)

        count_after = conn.execute("SELECT COUNT(*) FROM utxo_lifecycle").fetchone()[0]
        rows_imported = count_after - count_before

        # CORRUPTION DETECTION: Check if imported rows match CSV row count
        # A significant mismatch indicates corrupted CSV (from bad chainstate read)
        if csv_row_count > 0 and rows_imported < csv_row_count:
            skipped_rows = csv_row_count - rows_imported
            skip_percentage = (skipped_rows / csv_row_count) * 100
            if skip_percentage > 1.0:  # More than 1% data loss is suspicious
                logger.error(
                    f"CORRUPTION WARNING: {skipped_rows:,} rows ({skip_percentage:.2f}%) "
                    f"were skipped during import!"
                )
                logger.error(
                    "This may indicate corrupted CSV from reading locked chainstate. "
                    "Verify bitcoin-utxo-dump ran with chainstate UNLOCKED."
                )
            else:
                logger.warning(
                    f"Minor data loss: {skipped_rows:,} rows ({skip_percentage:.2f}%) skipped"
                )

        logger.info(f"Imported {rows_imported:,} rows from CSV")
        return rows_imported

    except Exception as e:
        logger.error(f"Failed to import CSV: {e}")
        raise


def verify_supporting_tables(conn: duckdb.DuckDBPyConnection) -> dict:
    """Verify supporting tables exist AND have data for VIEW.

    The utxo_lifecycle_full VIEW requires:
    - block_heights: Maps block height to timestamp (should have ~900K+ rows)
    - daily_prices: Maps date to BTC/USD price (should have ~5K+ rows)

    Args:
        conn: DuckDB connection

    Returns:
        Dict with table existence and row count status
    """
    status = {
        "block_heights": False,
        "block_heights_count": 0,
        "daily_prices": False,
        "daily_prices_count": 0,
        "view_functional": False,
    }

    try:
        # Check block_heights table exists and has data
        result = conn.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'block_heights'
        """).fetchone()[0]
        if result > 0:
            count = conn.execute("SELECT COUNT(*) FROM block_heights").fetchone()[0]
            status["block_heights"] = count > 0
            status["block_heights_count"] = count

        # Check daily_prices table exists and has data
        result = conn.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'daily_prices'
        """).fetchone()[0]
        if result > 0:
            count = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
            status["daily_prices"] = count > 0
            status["daily_prices_count"] = count

        # Both required for VIEW to be functional (with data)
        status["view_functional"] = status["block_heights"] and status["daily_prices"]

        if status["view_functional"]:
            logger.info(
                f"Supporting tables verified - VIEW will compute derived columns "
                f"(block_heights: {status['block_heights_count']:,}, "
                f"daily_prices: {status['daily_prices_count']:,})"
            )
        else:
            missing = []
            if not status["block_heights"]:
                missing.append(
                    f"block_heights ({status['block_heights_count']:,} rows)"
                )
            if not status["daily_prices"]:
                missing.append(f"daily_prices ({status['daily_prices_count']:,} rows)")
            logger.warning(
                f"Missing/empty tables for VIEW: {missing}. "
                f"Run build_block_heights.py and build_price_table.py first."
            )

    except Exception as e:
        logger.error(f"Failed to verify supporting tables: {e}")

    return status


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

        # Compute BTC from satoshis (amount / 1e8)
        stats["total_btc"] = conn.execute(
            "SELECT SUM(CAST(amount AS DOUBLE) / 100000000.0) FROM utxo_lifecycle"
        ).fetchone()[0]

        stats["min_block"] = conn.execute(
            "SELECT MIN(creation_block) FROM utxo_lifecycle"
        ).fetchone()[0]

        stats["max_block"] = conn.execute(
            "SELECT MAX(creation_block) FROM utxo_lifecycle"
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
        "--create-view",
        action="store_true",
        help="Create utxo_lifecycle_full VIEW (requires price/height tables)",
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

        rows_per_sec = rows / elapsed if elapsed > 0 else 0
        print(
            f"Imported {rows:,} UTXOs in {elapsed:.1f}s ({rows_per_sec:,.0f} rows/sec)"
        )

        # Optionally create indexes
        if args.create_indexes:
            create_indexes(conn)

        # Optionally create VIEW with computed columns
        if args.create_view:
            table_status = verify_supporting_tables(conn)
            if table_status["view_functional"]:
                create_utxo_lifecycle_view(conn)
                print("Created utxo_lifecycle_full VIEW for metrics queries")
            else:
                print(
                    "WARNING: Cannot create VIEW - missing supporting tables. "
                    "Run build_price_table.py and build_block_heights.py first."
                )

        # Print stats
        stats = get_import_stats(conn)
        print("\nImport Statistics:")
        print(f"  Total UTXOs: {stats.get('total_utxos', 0):,}")
        print(f"  Total BTC: {stats.get('total_btc', 0):,.2f}")
        print(
            f"  Block range: {stats.get('min_block', 0):,} - {stats.get('max_block', 0):,}"
        )
        print(f"  Unique addresses: {stats.get('unique_addresses', 0):,}")

    finally:
        conn.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
