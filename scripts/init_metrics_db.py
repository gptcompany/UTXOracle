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
from scripts.config import UTXORACLE_DB_PATH

# Default database path (same as daily_analysis.py)
DEFAULT_DB_PATH = str(UTXORACLE_DB_PATH)

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

    -- Coinblocks (per-block) - must be non-negative
    coinblocks_created DOUBLE NOT NULL CHECK (coinblocks_created >= 0),
    coinblocks_destroyed DOUBLE NOT NULL CHECK (coinblocks_destroyed >= 0),

    -- Coinblocks (cumulative) - must be non-negative
    cumulative_created DOUBLE NOT NULL CHECK (cumulative_created >= 0),
    cumulative_destroyed DOUBLE NOT NULL CHECK (cumulative_destroyed >= 0),

    -- Liveliness/Vaultedness (derived)
    liveliness DOUBLE NOT NULL CHECK (liveliness >= 0 AND liveliness <= 1),
    vaultedness DOUBLE NOT NULL CHECK (vaultedness >= 0 AND vaultedness <= 1),

    -- Supply split - must be non-negative
    active_supply_btc DOUBLE NOT NULL CHECK (active_supply_btc >= 0),
    vaulted_supply_btc DOUBLE NOT NULL CHECK (vaulted_supply_btc >= 0),

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

# Schema for address_clusters table (spec-013)
ADDRESS_CLUSTERS_TABLE_SQL = """
-- Address Clusters table (spec-013)
-- Stores address-to-cluster mappings for entity identification

CREATE TABLE IF NOT EXISTS address_clusters (
    -- Address is the primary key
    address VARCHAR PRIMARY KEY,
    -- Cluster identifier (typically root address from Union-Find)
    cluster_id VARCHAR NOT NULL,
    -- Timestamps for tracking activity
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    -- Heuristic flags
    is_exchange_likely BOOLEAN DEFAULT FALSE,
    -- Optional label for known entities
    label VARCHAR
);
"""

ADDRESS_CLUSTERS_INDEXES_SQL = """
-- Index for cluster_id filtering (find all addresses in a cluster)
CREATE INDEX IF NOT EXISTS idx_cluster_id ON address_clusters(cluster_id);

-- Index for exchange detection
CREATE INDEX IF NOT EXISTS idx_exchange_likely ON address_clusters(is_exchange_likely);
"""

# Schema for coinjoin_cache table (spec-013)
COINJOIN_CACHE_TABLE_SQL = """
-- CoinJoin Cache table (spec-013)
-- Stores CoinJoin detection results to avoid re-analysis

CREATE TABLE IF NOT EXISTS coinjoin_cache (
    -- Transaction ID is the primary key
    txid VARCHAR PRIMARY KEY,
    -- Detection result
    is_coinjoin BOOLEAN NOT NULL,
    confidence DOUBLE,
    coinjoin_type VARCHAR CHECK (coinjoin_type IN ('wasabi', 'whirlpool', 'joinmarket', 'generic') OR coinjoin_type IS NULL),
    -- Transaction statistics
    equal_output_count INTEGER,
    total_inputs INTEGER,
    total_outputs INTEGER,
    -- Timestamp
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

COINJOIN_CACHE_INDEXES_SQL = """
-- Index for CoinJoin type filtering
CREATE INDEX IF NOT EXISTS idx_coinjoin_type ON coinjoin_cache(coinjoin_type);

-- Index for confidence filtering
CREATE INDEX IF NOT EXISTS idx_coinjoin_confidence ON coinjoin_cache(confidence);
"""

# Schema for wallet_cost_basis table (spec-013 Phase 9)
WALLET_COST_BASIS_TABLE_SQL = """
-- Wallet Cost Basis table (spec-013)
-- Tracks acquisition prices at wallet (cluster) level for accurate Realized Cap

CREATE TABLE IF NOT EXISTS wallet_cost_basis (
    -- Composite key: cluster + acquisition block
    cluster_id VARCHAR NOT NULL,
    acquisition_block INTEGER NOT NULL,
    -- BTC amount acquired at this block
    btc_amount DOUBLE NOT NULL CHECK (btc_amount > 0),
    -- Price at time of acquisition (USD)
    acquisition_price DOUBLE NOT NULL CHECK (acquisition_price >= 0),
    -- Timestamp
    acquisition_timestamp TIMESTAMP NOT NULL,
    -- Primary key is cluster + block combination
    PRIMARY KEY (cluster_id, acquisition_block)
);
"""

WALLET_COST_BASIS_INDEXES_SQL = """
-- Index for cluster lookup
CREATE INDEX IF NOT EXISTS idx_wcb_cluster ON wallet_cost_basis(cluster_id);

-- Index for block-based queries
CREATE INDEX IF NOT EXISTS idx_wcb_block ON wallet_cost_basis(acquisition_block);

-- Index for timestamp queries
CREATE INDEX IF NOT EXISTS idx_wcb_timestamp ON wallet_cost_basis(acquisition_timestamp);
"""

# Schema for risk_percentiles table (spec-033)
RISK_PERCENTILES_TABLE_SQL = """
-- Risk Percentiles table (spec-033)
-- Stores daily percentile-normalized values for each component metric

CREATE TABLE IF NOT EXISTS risk_percentiles (
    -- Composite primary key: metric + date
    metric_name VARCHAR NOT NULL,
    date DATE NOT NULL,
    -- Raw metric value from source module
    raw_value DOUBLE,
    -- Normalized 0-1 percentile score
    percentile DOUBLE CHECK (percentile >= 0 AND percentile <= 1 OR percentile IS NULL),
    -- Number of historical days used for percentile calculation
    history_days INTEGER CHECK (history_days >= 0 OR history_days IS NULL),
    -- Metadata
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (metric_name, date)
);
"""

RISK_PERCENTILES_INDEXES_SQL = """
-- Index for date filtering (get all metrics for a date)
CREATE INDEX IF NOT EXISTS idx_risk_percentiles_date ON risk_percentiles(date);

-- Index for metric filtering (get history of one metric)
CREATE INDEX IF NOT EXISTS idx_risk_percentiles_metric ON risk_percentiles(metric_name);
"""

# Schema for pro_risk_daily table (spec-033)
PRO_RISK_DAILY_TABLE_SQL = """
-- PRO Risk Daily table (spec-033)
-- Stores daily composite PRO Risk metric results

CREATE TABLE IF NOT EXISTS pro_risk_daily (
    -- Date is the primary key
    date DATE PRIMARY KEY,
    -- Composite 0-1 score (weighted average of components)
    value DOUBLE NOT NULL CHECK (value >= 0 AND value <= 1),
    -- Zone classification
    zone VARCHAR NOT NULL CHECK (zone IN ('extreme_fear', 'fear', 'neutral', 'greed', 'extreme_greed')),
    -- Individual component normalized scores (0-1)
    mvrv_z_score DOUBLE CHECK (mvrv_z_score >= 0 AND mvrv_z_score <= 1 OR mvrv_z_score IS NULL),
    sopr_score DOUBLE CHECK (sopr_score >= 0 AND sopr_score <= 1 OR sopr_score IS NULL),
    nupl_score DOUBLE CHECK (nupl_score >= 0 AND nupl_score <= 1 OR nupl_score IS NULL),
    reserve_risk_score DOUBLE CHECK (reserve_risk_score >= 0 AND reserve_risk_score <= 1 OR reserve_risk_score IS NULL),
    puell_score DOUBLE CHECK (puell_score >= 0 AND puell_score <= 1 OR puell_score IS NULL),
    hodl_waves_score DOUBLE CHECK (hodl_waves_score >= 0 AND hodl_waves_score <= 1 OR hodl_waves_score IS NULL),
    -- Data availability confidence (0-1)
    confidence DOUBLE DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    -- Block height at calculation time
    block_height INTEGER,
    -- Metadata
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

PRO_RISK_DAILY_INDEXES_SQL = """
-- Index for zone filtering (find all extreme_fear days)
CREATE INDEX IF NOT EXISTS idx_pro_risk_zone ON pro_risk_daily(zone);

-- Index for value range queries
CREATE INDEX IF NOT EXISTS idx_pro_risk_value ON pro_risk_daily(value);
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

        # Create address_clusters table (spec-013)
        conn.execute(ADDRESS_CLUSTERS_TABLE_SQL)
        print("Created/verified address_clusters table")

        # Create address_clusters indexes
        conn.execute(ADDRESS_CLUSTERS_INDEXES_SQL)
        print("Created/verified address_clusters indexes")

        # Create coinjoin_cache table (spec-013)
        conn.execute(COINJOIN_CACHE_TABLE_SQL)
        print("Created/verified coinjoin_cache table")

        # Create coinjoin_cache indexes
        conn.execute(COINJOIN_CACHE_INDEXES_SQL)
        print("Created/verified coinjoin_cache indexes")

        # Create wallet_cost_basis table (spec-013)
        conn.execute(WALLET_COST_BASIS_TABLE_SQL)
        print("Created/verified wallet_cost_basis table")

        # Create wallet_cost_basis indexes
        conn.execute(WALLET_COST_BASIS_INDEXES_SQL)
        print("Created/verified wallet_cost_basis indexes")

        # Create risk_percentiles table (spec-033)
        conn.execute(RISK_PERCENTILES_TABLE_SQL)
        print("Created/verified risk_percentiles table")

        # Create risk_percentiles indexes
        conn.execute(RISK_PERCENTILES_INDEXES_SQL)
        print("Created/verified risk_percentiles indexes")

        # Create pro_risk_daily table (spec-033)
        conn.execute(PRO_RISK_DAILY_TABLE_SQL)
        print("Created/verified pro_risk_daily table")

        # Create pro_risk_daily indexes
        conn.execute(PRO_RISK_DAILY_INDEXES_SQL)
        print("Created/verified pro_risk_daily indexes")

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
