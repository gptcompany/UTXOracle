#!/usr/bin/env python3
"""
Initialize DuckDB database for mempool whale predictions
Task T003: Database schema initialization
"""

import duckdb
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_database(db_path: str = "data/mempool_predictions.db"):
    """Initialize the DuckDB database with required schema"""

    # Ensure data directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initializing database at {db_path}")

    try:
        conn = duckdb.connect(db_path)

        # Create mempool_predictions table
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
        logger.info("✅ Created mempool_predictions table")

        # Create prediction_outcomes table
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
        logger.info("✅ Created prediction_outcomes table")

        # Create indexes for performance
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_txid
            ON mempool_predictions(transaction_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_timestamp
            ON mempool_predictions(detection_timestamp)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_outcomes_predid
            ON prediction_outcomes(prediction_id)
        """)

        logger.info("✅ Created indexes")

        # Verify table structure
        result = conn.execute("SHOW TABLES").fetchall()
        logger.info(f"Database tables: {result}")

        # Show schema
        schema = conn.execute("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'main'
            ORDER BY table_name, ordinal_position
        """).fetchall()

        logger.info("\nDatabase schema:")
        current_table = None
        for table, column, dtype in schema:
            if table != current_table:
                logger.info(f"\n📊 Table: {table}")
                current_table = table
            logger.info(f"  - {column}: {dtype}")

        conn.close()
        logger.info("\n✅ Database initialization complete!")

        return True

    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return False


if __name__ == "__main__":
    import sys

    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/mempool_predictions.db"
    success = init_database(db_path)
    sys.exit(0 if success else 1)
