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
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import duckdb

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from api.questdb_repository import QuestDBRepository
from scripts.metrics.absorption_rates import calculate_absorption_rates
from scripts.metrics.wallet_waves import calculate_wallet_waves
from scripts.metrics.address_cohorts import calculate_address_cohorts
from scripts.metrics.cost_basis import calculate_cost_basis_signal
from scripts.metrics.urpd_features import calculate_urpd_features_signal

DUCKDB_PATH = os.getenv("DUCKDB_PATH") or os.getenv("UTXORACLE_DB_PATH") or "data/utxoracle.duckdb"


def _setup_script_logging(name: str) -> logging.Logger:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
    return logging.getLogger(name)


logger = _setup_script_logging("materialize_wave1")


async def _resolve_current_price(repo: QuestDBRepository) -> tuple[float, str]:
    price_row = await repo.get_latest_price_analysis()
    if price_row and price_row.get("utxoracle_price"):
        return float(price_row["utxoracle_price"]), "price_analysis"

    live_snapshot_row = await repo.get_latest_live_snapshot_row()
    if live_snapshot_row and live_snapshot_row.get("utxoracle_price"):
        return float(live_snapshot_row["utxoracle_price"]), "live_snapshots"

    if live_snapshot_row and live_snapshot_row.get("snapshot_json"):
        try:
            snapshot = json.loads(live_snapshot_row["snapshot_json"])
            price = snapshot.get("utxoracle_price")
            if price:
                return float(price), "live_snapshots.snapshot_json"
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning("Failed to parse live snapshot JSON while resolving Wave 1 price")

    return 0.0, "unavailable"


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
        
        current_price, price_source = await _resolve_current_price(repo)

        logger.info(
            "Materializing Wave 1 for height %s (target: %s), price: $%.2f via %s",
            latest_height,
            target_date.date(),
            current_price,
            price_source,
        )
        
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

        # 4.5. Calculate Cost Basis
        cost_basis = calculate_cost_basis_signal(
            conn=conn,
            current_block=latest_height,
            current_price_usd=current_price,
            timestamp=target_date
        )

        urpd_features = calculate_urpd_features_signal(
            conn=conn,
            current_price_usd=current_price,
            current_block=latest_height,
            timestamp=target_date,
        )
        
        # 5. Save to QuestDB
        wallet_waves_written = repo.save_wallet_waves(wallet_waves)
        if not wallet_waves_written:
            repo.abort_ingestion()
            logger.error("Wave 1 materialization write failure: wallet_waves=False")
            return False

        absorption_written = repo.save_absorption_rates(absorption)
        if not absorption_written:
            repo.abort_ingestion()
            logger.error(
                "Wave 1 materialization write failure: wallet_waves=True absorption_rates=False"
            )
            return False

        address_cohorts_written = repo.save_address_cohorts(address_cohorts)
        if not address_cohorts_written:
            repo.abort_ingestion()
            logger.error(
                "Wave 1 materialization write failure: wallet_waves=True absorption_rates=True address_cohorts=False"
            )
            return False

        cost_basis_written = repo.save_cost_basis(cost_basis)
        if not cost_basis_written:
            repo.abort_ingestion()
            logger.error(
                "Wave 1 materialization write failure: wallet_waves=True absorption_rates=True address_cohorts=True cost_basis=False"
            )
            return False

        urpd_features_written = repo.save_urpd_features(urpd_features)
        if not urpd_features_written:
            repo.abort_ingestion()
            logger.error(
                "Wave 1 materialization write failure: wallet_waves=True absorption_rates=True "
                "address_cohorts=True cost_basis=True urpd_features=False"
            )
            return False
        
        logger.info(f"✅ Successfully materialized Wave 1 for {target_date.date()}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to materialize Wave 1 for {target_date.date()}: {e}", exc_info=True)
        return False


async def run_materialization_pass(
    conn: duckdb.DuckDBPyConnection,
    target_date: datetime,
) -> bool:
    """
    Run one materialization pass with a fresh repository instance.

    A write failure aborts the current ILP sender; using a new repository for each
    pass keeps the optional backfill retry path isolated.
    """
    # Limit memory usage for large DuckDB scans on 57GB database
    conn.execute("SET max_memory='8GB'")
    
    repo = QuestDBRepository()
    await repo.initialize()

    try:
        success = await materialize_daily_snapshot(repo, conn, target_date)
        if not success:
            return False

        flush_ok = await repo.async_flush_ingestion()
        if not flush_ok:
            logger.error(
                "Wave 1 materialization flush failure after snapshot for %s",
                target_date.date(),
            )
            return False

        return True
    finally:
        await repo.close()


async def main():
    if not os.path.exists(DUCKDB_PATH):
        logger.error(f"DuckDB database not found at {DUCKDB_PATH}")
        return

    conn = duckdb.connect(DUCKDB_PATH, read_only=True)
    conn.execute("SET max_memory='8GB'")
    
    try:
        # Run for today
        await run_materialization_pass(conn, datetime.now(timezone.utc))
        
        # Optional backfill check
        if "--backfill" in sys.argv:
            # For now, just re-run for current state as a proxy
            logger.info("Backfill requested (placeholder logic executed)")
            await run_materialization_pass(conn, datetime.now(timezone.utc))
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
