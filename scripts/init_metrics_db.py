#!/usr/bin/env python3
"""
DuckDB Migration Script for On-Chain Metrics (spec-007).

Creates the `metrics` table for storing:
- Monte Carlo Signal Fusion results
- Active Addresses counts
- TX Volume in BTC and USD

Usage:
    python scripts/init_metrics_db.py [--db-path PATH]

The script is idempotent - safe to run multiple times.
"""

import argparse
import duckdb
from pathlib import Path

# Default database path (same as daily_analysis.py)
DEFAULT_DB_PATH = "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"

# Schema for metrics table
METRICS_TABLE_SQL = """
-- On-Chain Metrics table (spec-007)
-- Stores Monte Carlo fusion, Active Addresses, and TX Volume metrics

CREATE TABLE IF NOT EXISTS metrics (
    -- Timestamp is the primary key (unique per metrics calculation)
    timestamp TIMESTAMP NOT NULL PRIMARY KEY,

    -- Monte Carlo Fusion (FR-001, FR-002)
    signal_mean DOUBLE,
    signal_std DOUBLE,
    ci_lower DOUBLE,
    ci_upper DOUBLE,
    action VARCHAR(10) CHECK (action IN ('BUY', 'SELL', 'HOLD')),
    action_confidence DOUBLE CHECK (action_confidence >= 0 AND action_confidence <= 1),
    n_samples INTEGER DEFAULT 1000,
    distribution_type VARCHAR(20) CHECK (distribution_type IN ('unimodal', 'bimodal', 'insufficient_data')),

    -- Active Addresses (FR-003, FR-004)
    block_height INTEGER,
    active_addresses_block INTEGER CHECK (active_addresses_block >= 0),
    active_addresses_24h INTEGER CHECK (active_addresses_24h >= 0),
    unique_senders INTEGER CHECK (unique_senders >= 0),
    unique_receivers INTEGER CHECK (unique_receivers >= 0),
    is_anomaly BOOLEAN DEFAULT FALSE,

    -- TX Volume (FR-005, FR-006)
    tx_count INTEGER CHECK (tx_count >= 0),
    tx_volume_btc DOUBLE CHECK (tx_volume_btc >= 0),
    tx_volume_usd DOUBLE CHECK (tx_volume_usd >= 0 OR tx_volume_usd IS NULL),
    utxoracle_price_used DOUBLE,
    low_confidence BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Indexes for efficient queries
INDEXES_SQL = """
-- Index for action filtering (find all BUY signals)
CREATE INDEX IF NOT EXISTS idx_metrics_action ON metrics(action);

-- Index for anomaly detection queries (non-partial, DuckDB doesn't support partial indexes)
CREATE INDEX IF NOT EXISTS idx_metrics_anomaly ON metrics(is_anomaly);
"""


def init_metrics_db(db_path: str = DEFAULT_DB_PATH) -> bool:
    """
    Initialize the metrics table in DuckDB.

    Args:
        db_path: Path to DuckDB database file

    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure parent directory exists
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        # Connect to database
        conn = duckdb.connect(db_path)

        # Create table
        conn.execute(METRICS_TABLE_SQL)
        print(f"Created/verified metrics table in {db_path}")

        # Create indexes
        conn.execute(INDEXES_SQL)
        print("Created/verified indexes")

        # Verify table exists
        result = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'metrics'"
        ).fetchone()

        if result and result[0] > 0:
            print("Migration successful: metrics table ready")

            # Show table schema
            schema = conn.execute("DESCRIBE metrics").fetchall()
            print("\nTable schema:")
            for col in schema:
                print(f"  {col[0]}: {col[1]}")

            conn.close()
            return True
        else:
            print("ERROR: Table creation failed")
            conn.close()
            return False

    except Exception as e:
        print(f"ERROR: Migration failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Initialize DuckDB metrics table for spec-007"
    )
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show SQL without executing",
    )

    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN: SQL to be executed ===\n")
        print(METRICS_TABLE_SQL)
        print(INDEXES_SQL)
        return

    success = init_metrics_db(args.db_path)
    exit(0 if success else 1)


if __name__ == "__main__":
    main()
