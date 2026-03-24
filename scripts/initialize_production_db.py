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


import asyncio
import os
import sys
import logging
from api.questdb_repository import create_tables_if_not_exist

async def initialize_production_database():
    """
    Initializes all production database tables in QuestDB.
    This function is idempotent and can be run multiple times.
    """
    logging.info("=" * 60)
    logging.info("🚀 PRODUCTION DATABASE INITIALIZATION (QUESTDB)")
    logging.info("=" * 60)

    try:
        await create_tables_if_not_exist()
        
        logging.info("")
        logging.info("=" * 60)
        logging.info("✅ QUESTDB DATABASE INITIALIZATION COMPLETE!")
        logging.info("=" * 60)
        logging.info("Next steps:")
        logging.info("  1. Configure JWT in .env")
        logging.info("  2. Start WebSocket server")
        logging.info("  3. Run integration service")
        logging.info("")

        return True

    except Exception as e:
        logging.error(f"❌ Database initialization FAILED: {e}", exc_info=True)
        return False


async def main():
    """Main execution block."""
    # Setup logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )

    # Initialize database
    success = await initialize_production_database()

    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())
