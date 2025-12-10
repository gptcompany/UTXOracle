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

    -- Wasserstein Distance (spec-010)
    wasserstein_distance DOUBLE,
    wasserstein_normalized DOUBLE,
    wasserstein_shift_direction VARCHAR(20) CHECK (wasserstein_shift_direction IN ('CONCENTRATION', 'DISPERSION', 'NONE') OR wasserstein_shift_direction IS NULL),
    wasserstein_regime_status VARCHAR(20) CHECK (wasserstein_regime_status IN ('STABLE', 'TRANSITIONING', 'SHIFTED') OR wasserstein_regime_status IS NULL),
    wasserstein_vote DOUBLE,
    wasserstein_is_valid BOOLEAN DEFAULT FALSE,

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

# Migration SQL for Wasserstein columns (spec-010) - for existing databases
WASSERSTEIN_MIGRATION_SQL = """
-- Add Wasserstein columns if they don't exist (spec-010)
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS wasserstein_distance DOUBLE;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS wasserstein_normalized DOUBLE;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS wasserstein_shift_direction VARCHAR(20);
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS wasserstein_regime_status VARCHAR(20);
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS wasserstein_vote DOUBLE;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS wasserstein_is_valid BOOLEAN DEFAULT FALSE;
"""

# Schema for alert_events table (spec-011)
ALERT_EVENTS_TABLE_SQL = """
-- Alert Events table (spec-011)
-- Stores webhook alert events for audit and replay

CREATE TABLE IF NOT EXISTS alert_events (
    event_id VARCHAR PRIMARY KEY,
    event_type VARCHAR NOT NULL CHECK (event_type IN ('whale', 'signal', 'regime', 'price')),
    timestamp TIMESTAMP NOT NULL,
    severity VARCHAR NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    payload JSON NOT NULL,
    webhook_status VARCHAR DEFAULT 'pending' CHECK (webhook_status IN ('pending', 'sent', 'failed')),
    webhook_attempts INTEGER DEFAULT 0,
    webhook_response_code INTEGER,
    webhook_error VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP
);
"""

ALERT_EVENTS_INDEXES_SQL = """
-- Index for event type filtering
CREATE INDEX IF NOT EXISTS idx_alert_type ON alert_events(event_type);

-- Index for severity filtering
CREATE INDEX IF NOT EXISTS idx_alert_severity ON alert_events(severity);

-- Index for timestamp ordering
CREATE INDEX IF NOT EXISTS idx_alert_timestamp ON alert_events(timestamp);

-- Index for webhook status (for replay queries)
CREATE INDEX IF NOT EXISTS idx_alert_status ON alert_events(webhook_status);
"""

# Schema for backtest_results table (spec-012)
BACKTEST_RESULTS_TABLE_SQL = """
-- Backtest Results table (spec-012)
-- Stores historical backtest runs for performance tracking

CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY,
    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    signal_source VARCHAR NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    total_return DOUBLE,
    sharpe_ratio DOUBLE,
    sortino_ratio DOUBLE,
    win_rate DOUBLE,
    max_drawdown DOUBLE,
    profit_factor DOUBLE,
    num_trades INTEGER,
    config_json VARCHAR,
    trades_json VARCHAR
);
"""

BACKTEST_RESULTS_INDEXES_SQL = """
-- Index for signal source filtering
CREATE INDEX IF NOT EXISTS idx_backtest_signal ON backtest_results(signal_source);

-- Index for date range queries
CREATE INDEX IF NOT EXISTS idx_backtest_dates ON backtest_results(start_date, end_date);

-- Index for run timestamp (most recent)
CREATE INDEX IF NOT EXISTS idx_backtest_run ON backtest_results(run_timestamp);
"""

# Schema for cointime_metrics table (spec-018)
COINTIME_METRICS_TABLE_SQL = """
-- Cointime Metrics table (spec-018)
-- Stores Cointime Economics metrics: coinblocks, liveliness, supply split, AVIV

CREATE TABLE IF NOT EXISTS cointime_metrics (
    -- Block height is the primary key
    block_height INTEGER PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,

    -- Coinblocks (per-block)
    coinblocks_created DOUBLE NOT NULL,
    coinblocks_destroyed DOUBLE NOT NULL,

    -- Coinblocks (cumulative)
    cumulative_created DOUBLE NOT NULL,
    cumulative_destroyed DOUBLE NOT NULL,

    -- Liveliness/Vaultedness (derived)
    liveliness DOUBLE NOT NULL CHECK (liveliness >= 0 AND liveliness <= 1),
    vaultedness DOUBLE NOT NULL CHECK (vaultedness >= 0 AND vaultedness <= 1),

    -- Supply split
    active_supply_btc DOUBLE NOT NULL,
    vaulted_supply_btc DOUBLE NOT NULL,

    -- Valuation (optional - requires price data)
    true_market_mean_usd DOUBLE,
    aviv_ratio DOUBLE,
    aviv_percentile DOUBLE CHECK (aviv_percentile >= 0 AND aviv_percentile <= 100 OR aviv_percentile IS NULL),

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

COINTIME_METRICS_INDEXES_SQL = """
-- Index for timestamp queries
CREATE INDEX IF NOT EXISTS idx_cointime_timestamp ON cointime_metrics(timestamp);

-- Index for AVIV ratio filtering (find undervalued/overvalued periods)
CREATE INDEX IF NOT EXISTS idx_cointime_aviv ON cointime_metrics(aviv_ratio);

-- Index for liveliness queries
CREATE INDEX IF NOT EXISTS idx_cointime_liveliness ON cointime_metrics(liveliness);
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

        # Create metrics table
        conn.execute(METRICS_TABLE_SQL)
        print(f"Created/verified metrics table in {db_path}")

        # Create metrics indexes
        conn.execute(INDEXES_SQL)
        print("Created/verified metrics indexes")

        # Run Wasserstein migration (spec-010) - adds columns if they don't exist
        for stmt in WASSERSTEIN_MIGRATION_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt and not stmt.startswith("--"):
                try:
                    conn.execute(stmt)
                except Exception as e:
                    # Column might already exist, ignore
                    if "already exists" not in str(e).lower():
                        print(f"Warning: Wasserstein migration: {e}")
        print("Created/verified Wasserstein columns (spec-010)")

        # Create alert_events table (spec-011)
        conn.execute(ALERT_EVENTS_TABLE_SQL)
        print("Created/verified alert_events table")

        # Create alert_events indexes
        conn.execute(ALERT_EVENTS_INDEXES_SQL)
        print("Created/verified alert_events indexes")

        # Create backtest_results table (spec-012)
        conn.execute(BACKTEST_RESULTS_TABLE_SQL)
        print("Created/verified backtest_results table")

        # Create backtest_results indexes
        conn.execute(BACKTEST_RESULTS_INDEXES_SQL)
        print("Created/verified backtest_results indexes")

        # Create cointime_metrics table (spec-018)
        conn.execute(COINTIME_METRICS_TABLE_SQL)
        print("Created/verified cointime_metrics table")

        # Create cointime_metrics indexes
        conn.execute(COINTIME_METRICS_INDEXES_SQL)
        print("Created/verified cointime_metrics indexes")

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
