#!/usr/bin/env python3
"""
Initialize whale detection tables in DuckDB.
Task T005 & T007: Set up DuckDB database and initialization script.
"""

import duckdb
import os
import sys
from pathlib import Path


def init_whale_database(db_path: str):
    """Initialize whale detection tables in DuckDB."""

    print(f"Connecting to DuckDB at: {db_path}")
    conn = duckdb.connect(db_path)

    try:
        # Create whale_transactions table
        print("Creating whale_transactions table...")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whale_transactions (
                transaction_id VARCHAR PRIMARY KEY,
                block_height INTEGER,
                timestamp TIMESTAMP NOT NULL,
                amount_btc DECIMAL(18, 8) NOT NULL,
                amount_usd DECIMAL(18, 2) NOT NULL,
                direction VARCHAR NOT NULL CHECK (direction IN ('BUY', 'SELL', 'TRANSFER')),
                urgency_score INTEGER NOT NULL CHECK (urgency_score >= 0 AND urgency_score <= 100),
                fee_rate DOUBLE NOT NULL,
                confidence DOUBLE NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
                is_mempool BOOLEAN NOT NULL DEFAULT TRUE,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for whale_transactions
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_whale_tx_timestamp ON whale_transactions(timestamp DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_whale_tx_amount ON whale_transactions(amount_btc DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_whale_tx_urgency ON whale_transactions(urgency_score DESC)"
        )

        # Create net_flow_metrics table
        print("Creating net_flow_metrics table...")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS net_flow_metrics (
                period_start TIMESTAMP NOT NULL,
                period_end TIMESTAMP NOT NULL,
                interval VARCHAR NOT NULL CHECK (interval IN ('1m', '5m', '1h', '24h')),
                net_flow_btc DECIMAL(18, 8) NOT NULL,
                net_flow_usd DECIMAL(18, 2) NOT NULL,
                total_buy_btc DECIMAL(18, 8) NOT NULL,
                total_sell_btc DECIMAL(18, 8) NOT NULL,
                transaction_count INTEGER NOT NULL,
                direction VARCHAR NOT NULL CHECK (direction IN ('ACCUMULATION', 'DISTRIBUTION', 'NEUTRAL')),
                strength DOUBLE CHECK (strength >= 0 AND strength <= 1),
                largest_tx_btc DECIMAL(18, 8),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (period_start, interval)
            )
        """)

        # Create indexes for net_flow_metrics
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_netflow_period ON net_flow_metrics(period_start DESC, interval)"
        )

        # Create alerts table
        print("Creating alerts table...")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id VARCHAR PRIMARY KEY,
                transaction_id VARCHAR NOT NULL,
                severity VARCHAR NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
                trigger_type VARCHAR NOT NULL CHECK (trigger_type IN ('SIZE', 'URGENCY', 'PATTERN', 'THRESHOLD')),
                threshold_value DECIMAL(18, 8) NOT NULL,
                title VARCHAR NOT NULL,
                message TEXT NOT NULL,
                amount_btc DECIMAL(18, 8) NOT NULL,
                amount_usd DECIMAL(18, 2) NOT NULL,
                direction VARCHAR NOT NULL CHECK (direction IN ('BUY', 'SELL', 'TRANSFER')),
                acknowledged BOOLEAN DEFAULT FALSE,
                acknowledged_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create index for alerts
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity, created_at DESC)"
        )

        # Create urgency_scores table (for tracking urgency calculation metadata)
        print("Creating urgency_scores table...")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS urgency_scores (
                transaction_id VARCHAR PRIMARY KEY REFERENCES whale_transactions(transaction_id),
                urgency_score INTEGER NOT NULL CHECK (urgency_score >= 0 AND urgency_score <= 100),
                fee_rate DOUBLE NOT NULL,
                amount_btc DECIMAL(18, 8) NOT NULL,
                time_in_mempool INTEGER NOT NULL,
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Verify tables were created
        tables = conn.execute("SHOW TABLES").fetchall()
        print(f"\n✅ Database initialized with tables: {[t[0] for t in tables]}")

        # Show table schemas
        print("\n📊 Table schemas:")
        for table_name in [
            "whale_transactions",
            "net_flow_metrics",
            "alerts",
            "urgency_scores",
        ]:
            if any(t[0] == table_name for t in tables):
                schema = conn.execute(f"DESCRIBE {table_name}").fetchall()
                print(f"\n{table_name}:")
                for col in schema[:3]:  # Show first 3 columns as sample
                    print(f"  - {col[0]}: {col[1]}")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        conn.close()
        return False


if __name__ == "__main__":
    # Get database path from environment or use default
    db_path = os.getenv("DUCKDB_PATH", "/media/sam/1TB/UTXOracle/data/utxoracle.duckdb")

    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Initialize database
    if init_whale_database(db_path):
        print("\n✅ Whale detection database initialization complete!")
        sys.exit(0)
    else:
        print("\n❌ Database initialization failed!")
        sys.exit(1)
