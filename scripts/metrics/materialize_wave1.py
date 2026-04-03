#!/usr/bin/env python3
"""
Wave 1 Materialization Script (spec-046 Phase 4).

Daily snapshotting and backfilling for:
- Wallet Waves (spec-025)
- Absorption Rates (spec-025)
- Address Cohorts (spec-039)

Reads from DuckDB (utxo_lifecycle_full) and writes to QuestDB for persistent serving.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import duckdb

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from api.config import DUCKDB_PATH, setup_logging
from api.questdb_repository import QuestDBRepository
from scripts.metrics.absorption_rates import calculate_absorption_rates
from scripts.metrics.wallet_waves import calculate_wallet_waves
from scripts.metrics.address_cohorts import calculate_address_cohorts

logger = setup_logging("materialize_wave1")


async def materialize_daily_snapshot(
    repo: QuestDBRepository,
    conn: duckdb.DuckDBPyConnection,
    target_date: datetime,
    backfill: bool = False,
):
    """
    Calculate and save Wave 1 metrics for a specific date.
    """
    try:
        # 1. Get current state from database
        res = conn.execute("SELECT max(creation_block) FROM utxo_lifecycle_full").fetchone()
        latest_height = res[0] if res and res[0] else 0
        
        # Get latest price for MVRV calculations in address cohorts
        price_row = await repo.get_latest_price_analysis()
        current_price = price_row["utxoracle_price"] if price_row else 0.0
        
        logger.info(f"Materializing Wave 1 for height {latest_height} (target: {target_date.date()}), price: ${current_price:,.2f}")
        
        # 2. Calculate Wallet Waves
        wallet_waves = calculate_wallet_waves(conn, block_height=latest_height, timestamp=target_date)
        
        # 3. Calculate Absorption Rates (30d window)
        historical_height = latest_height - (144 * 30) # Approx 30 days
        historical_snapshot = None
        if historical_height > 0:
            try:
                # Note: as_of_block reconstructs the state at that height
                historical_snapshot = calculate_wallet_waves(
                    conn, as_of_block=historical_height, timestamp=target_date - timedelta(days=30)
                )
            except Exception as e:
                logger.warning(f"Could not calculate historical snapshot for absorption: {e}")

        absorption = calculate_absorption_rates(
            conn=conn,
            current_snapshot=wallet_waves,
            historical_snapshot=historical_snapshot,
            window_days=30,
            timestamp=target_date
        )
        
        # 4. Calculate Address Cohorts
        address_cohorts = calculate_address_cohorts(
            conn=conn,
            current_block=latest_height,
            current_price_usd=current_price
        )
        address_cohorts.timestamp = target_date # Override with target date
        
        # 5. Save to QuestDB
        writes = [
            repo.save_wallet_waves(wallet_waves),
            repo.save_absorption_rates(absorption),
            repo.save_address_cohorts(address_cohorts),
        ]
        if not all(writes):
            logger.error(
                "Wave 1 materialization write failure: wallet_waves=%s absorption_rates=%s address_cohorts=%s",
                writes[0],
                writes[1],
                writes[2],
            )
            return False
        
        logger.info(f"✅ Successfully materialized Wave 1 for {target_date.date()}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to materialize Wave 1 for {target_date.date()}: {e}", exc_info=True)
        return False


async def main():
    repo = QuestDBRepository()
    await repo.initialize()
    
    if not os.path.exists(DUCKDB_PATH):
        logger.error(f"DuckDB database not found at {DUCKDB_PATH}")
        return

    conn = duckdb.connect(DUCKDB_PATH, read_only=True)
    
    try:
        # Run for today
        await materialize_daily_snapshot(repo, conn, datetime.now(timezone.utc))
        
        # Optional backfill check
        if "--backfill" in sys.argv:
            # For now, just re-run for current state as a proxy
            logger.info("Backfill requested (placeholder logic executed)")
            await materialize_daily_snapshot(repo, conn, datetime.now(timezone.utc))
            
        await repo.async_flush_ingestion()
    finally:
        conn.close()
        await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
