#!/usr/bin/env python3
"""
Production Database Initialization Script
Unifies all database schemas for UTXOracle production deployment

Creates:
- price_analysis table (for daily_analysis.py integration service)
- mempool_predictions table (for whale detection system)
- prediction_outcomes table (for correlation tracking)
"""

import duckdb
import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def initialize_production_database(db_path: str = "utxoracle.db"):
    """
    Initialize complete production database schema

    Args:
        db_path: Path to DuckDB file

    Returns:
        bool: True if successful, False otherwise
    """

    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("🚀 PRODUCTION DATABASE INITIALIZATION")
    logger.info("=" * 60)
    logger.info(f"Database: {db_path}")
    logger.info("")

    try:
        conn = duckdb.connect(db_path)

        # =====================================================================
        # Table 1: price_analysis (T042 - Integration Service)
        # =====================================================================
        logger.info("Creating table: price_analysis")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_analysis (
                date DATE PRIMARY KEY,
                exchange_price DECIMAL(12, 2),
                utxoracle_price DECIMAL(12, 2),
                price_difference DECIMAL(12, 2),
                avg_pct_diff DECIMAL(6, 2),
                confidence DECIMAL(5, 4),
                tx_count INTEGER,
                is_valid BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("  ✅ price_analysis table created")

        # =====================================================================
        # Table 2: mempool_predictions (T016 - Whale Detection)
        # =====================================================================
        logger.info("Creating table: mempool_predictions")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mempool_predictions (
                prediction_id TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL,
                flow_type TEXT NOT NULL,
                btc_value REAL NOT NULL CHECK (btc_value > 100),
                fee_rate REAL NOT NULL CHECK (fee_rate > 0),
                urgency_score REAL NOT NULL CHECK (urgency_score >= 0 AND urgency_score <= 1),
                rbf_enabled BOOLEAN NOT NULL,
                detection_timestamp TIMESTAMP NOT NULL,
                predicted_confirmation_block INTEGER,
                exchange_addresses TEXT,
                confidence_score REAL,
                was_modified BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("  ✅ mempool_predictions table created")

        # =====================================================================
        # Table 3: prediction_outcomes (T042 - Correlation Tracking)
        # =====================================================================
        logger.info("Creating table: prediction_outcomes")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prediction_outcomes (
                outcome_id TEXT PRIMARY KEY,
                prediction_id TEXT NOT NULL,
                transaction_id TEXT NOT NULL,
                predicted_flow TEXT NOT NULL,
                actual_outcome TEXT,
                confirmation_time TIMESTAMP,
                confirmation_block INTEGER,
                accuracy_score REAL,
                time_to_confirmation INTEGER,
                final_fee_rate REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (prediction_id) REFERENCES mempool_predictions(prediction_id)
            )
        """)
        logger.info("  ✅ prediction_outcomes table created")

        # =====================================================================
        # Performance Indexes
        # =====================================================================
        logger.info("Creating indexes for performance...")

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_txid
            ON mempool_predictions(transaction_id)
        """)
        logger.info("  ✅ idx_predictions_txid")

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_timestamp
            ON mempool_predictions(detection_timestamp)
        """)
        logger.info("  ✅ idx_predictions_timestamp")

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_outcomes_predid
            ON prediction_outcomes(prediction_id)
        """)
        logger.info("  ✅ idx_outcomes_predid")

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_analysis_date
            ON price_analysis(date)
        """)
        logger.info("  ✅ idx_price_analysis_date")

        # =====================================================================
        # Verification
        # =====================================================================
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 DATABASE VERIFICATION")
        logger.info("=" * 60)

        # List tables
        tables = conn.execute("SHOW TABLES").fetchall()
        logger.info(f"Tables created: {len(tables)}")
        for table in tables:
            table_name = table[0]
            count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            logger.info(f"  - {table_name}: {count} rows")

        # Show schema
        logger.info("")
        logger.info("Full schema:")
        schema = conn.execute("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'main'
            ORDER BY table_name, ordinal_position
        """).fetchall()

        current_table = None
        for table, column, dtype in schema:
            if table != current_table:
                logger.info(f"\n  📋 {table}:")
                current_table = table
            logger.info(f"     - {column}: {dtype}")

        conn.close()

        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ DATABASE INITIALIZATION COMPLETE!")
        logger.info("=" * 60)
        logger.info(f"Database ready at: {db_path}")
        logger.info(f"Tables: {len(tables)}")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Configure JWT in .env")
        logger.info("  2. Start WebSocket server")
        logger.info("  3. Run integration service")
        logger.info("")

        return True

    except Exception as e:
        logger.error(f"❌ Database initialization FAILED: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    # Get database path from command line or use default
    db_path = sys.argv[1] if len(sys.argv) > 1 else "utxoracle.db"

    # Initialize database
    success = initialize_production_database(db_path)

    # Exit with appropriate code
    sys.exit(0 if success else 1)
