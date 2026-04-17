from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, List, Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from api.models.questdb import (
    PriceEntry,
    ComparisonStats,
    MetricsLatestResponse,
    MonteCarloFusionResponse,
    ActiveAddressesResponse,
    TxVolumeResponse,
    AddressCohortsResponse,
    CostBasisResponse,
    URPDFeaturesResponse,
    CohortMetricsResponse,
    WalletWavesResponse,
    WalletBandMetricsResponse,
    AbsorptionRatesResponse,
    AbsorptionRateMetricsResponse,
    TierObservabilityResponse,
    TierStats,
)
from api.questdb_repository import QuestDBRepository

router = APIRouter(tags=["questdb-metrics"])


def get_questdb_repo(request: Request) -> QuestDBRepository:
    repo = getattr(request.app.state, "questdb_repo", None)
    if repo is None:
        raise HTTPException(
            status_code=503,
            detail="QuestDB repository unavailable. API startup may be incomplete.",
        )
    return repo


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _raise_http_exception(
    status_code: int,
    public_detail: str,
    log_message: str,
    exc: Exception,
) -> None:
    logging.exception("%s: %s", log_message, exc)
    raise HTTPException(status_code=status_code, detail=public_detail) from exc


# =============================================================================
# Dual Read Logging Helpers (from main.py)
# =============================================================================

def _prices_historical_dual_read_enabled() -> bool:
    return os.getenv("PRICES_HISTORICAL_DUAL_READ_ENABLED", "false").lower() == "true"


def _serialize_price_entries_for_dual_read(
    payload: list[PriceEntry] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, PriceEntry):
            serialized.append(item.model_dump(mode="json"))
        else:
            serialized.append(dict(item))
    return serialized


def _log_prices_historical_dual_read(
    payload: list[PriceEntry] | list[dict[str, Any]],
    *,
    days: int,
) -> dict[str, Any]:
    from scripts.config import UTXORACLE_DB_PATH
    from scripts.validation.route_parity import run_prices_historical_dual_read

    report = run_prices_historical_dual_read(
        questdb_payload=_serialize_price_entries_for_dual_read(payload),
        duckdb_path=os.getenv(
            "PRICES_HISTORICAL_DUAL_READ_DUCKDB_PATH",
            str(UTXORACLE_DB_PATH),
        ),
        lookback_days=days,
        dataset_id=f"prices-historical:{days}d",
        divergence_log=os.getenv("PRICES_HISTORICAL_DUAL_READ_LOG_PATH"),
    )
    logging.info(
        "prices-historical dual-read completed: status=%s sample_count=%s failing_fields=%s notes=%s",
        report.get("status"),
        report.get("sample_count"),
        report.get("failing_fields"),
        report.get("notes"),
    )
    return report


def _safe_log_prices_historical_dual_read(
    payload: list[PriceEntry] | list[dict[str, Any]],
    *,
    days: int,
) -> None:
    try:
        _log_prices_historical_dual_read(payload, days=days)
    except Exception as exc:
        logging.warning("prices-historical dual-read logging failed: %s", exc)


# =============================================================================
# Routes
# =============================================================================

@router.get("/api/prices/latest", response_model=PriceEntry)
async def get_latest_price(
    repo: Annotated[QuestDBRepository, Depends(get_questdb_repo)],
):
    """
    Get the most recent price comparison entry.
    """
    try:
        row = await repo.get_latest_price_analysis()
        if not row:
            raise HTTPException(status_code=404, detail="No price data available")

        return PriceEntry(
            timestamp=row["ts"].isoformat(),
            utxoracle_price=row["utxoracle_price"],
            mempool_price=row["exchange_price"],
            confidence=row["confidence"],
            tx_count=row["tx_count"],
            fetch_tier=row.get("fetch_tier"),
            diff_amount=row["price_difference"],
            diff_percent=row["avg_pct_diff"],
            is_valid=row["is_valid"],
        )
    except HTTPException:
        raise
    except Exception as e:
        _raise_http_exception(
            status_code=500,
            public_detail="Failed to fetch latest price data",
            log_message="Error getting latest price",
            exc=e,
        )


@router.get("/api/prices/historical", response_model=List[PriceEntry])
async def get_historical_prices(
    background_tasks: BackgroundTasks,
    repo: Annotated[QuestDBRepository, Depends(get_questdb_repo)],
    days: int = Query(
        default=7,
        ge=1,
        le=365,
        description="Number of days of historical data to retrieve",
    ),
):
    """
    Get historical price comparison data.
    """
    try:
        rows = await repo.get_historical_price_analysis(days)
        response_items = [
            PriceEntry(
                timestamp=row["ts"].isoformat(),
                utxoracle_price=row["utxoracle_price"],
                mempool_price=row["exchange_price"],
                confidence=row["confidence"],
                tx_count=row["tx_count"],
                fetch_tier=row.get("fetch_tier"),
                diff_amount=row["price_difference"],
                diff_percent=row["avg_pct_diff"],
                is_valid=row["is_valid"],
            )
            for row in rows
        ]

        if _prices_historical_dual_read_enabled():
            background_tasks.add_task(
                _safe_log_prices_historical_dual_read,
                response_items,
                days=days,
            )

        return response_items
    except Exception as e:
        _raise_http_exception(
            status_code=500,
            public_detail="Failed to fetch historical price data",
            log_message="Error getting historical prices",
            exc=e,
        )


@router.get("/api/prices/comparison", response_model=ComparisonStats)
async def get_comparison_stats(
    repo: Annotated[QuestDBRepository, Depends(get_questdb_repo)],
    days: int = Query(
        default=7, ge=1, le=365, description="Number of days for statistics calculation"
    ),
):
    """
    Get statistical comparison metrics between UTXOracle and exchange prices.
    """
    try:
        query = """
            SELECT
                avg(abs(price_difference)) as avg_diff,
                max(abs(price_difference)) as max_diff,
                min(abs(price_difference)) as min_diff,
                avg(abs(avg_pct_diff)) as avg_diff_percent,
                count(*) as total_entries,
                count(CASE WHEN is_valid = true THEN 1 END) as valid_entries
            FROM price_analysis
            WHERE ts > $1
        """
        cutoff_time = (_utc_now() - timedelta(days=days)).replace(tzinfo=None)
        row = await repo.fetchrow(query, cutoff_time)
        if not row:
            return ComparisonStats(total_entries=0, valid_entries=0, timeframe_days=days)

        return ComparisonStats(
            avg_diff=row["avg_diff"],
            max_diff=row["max_diff"],
            min_diff=row["min_diff"],
            avg_diff_percent=row["avg_diff_percent"],
            total_entries=row["total_entries"],
            valid_entries=row["valid_entries"],
            timeframe_days=days,
        )
    except Exception as e:
        _raise_http_exception(
            status_code=500,
            public_detail="Failed to fetch comparison statistics",
            log_message="Error getting comparison stats",
            exc=e,
        )


@router.get("/api/metrics/latest", response_model=MetricsLatestResponse)
async def get_latest_metrics(
    repo: Annotated[QuestDBRepository, Depends(get_questdb_repo)],
):
    """
    Get the most recent on-chain metrics (spec-007).
    """
    try:
        row = await repo.get_latest_metrics()
        if not row:
            raise HTTPException(status_code=404, detail="No metrics found")

        return MetricsLatestResponse(
            timestamp=row["ts"],
            monte_carlo=MonteCarloFusionResponse(
                signal_mean=row["signal_mean"],
                signal_std=row["signal_std"],
                ci_lower=row["ci_lower"],
                ci_upper=row["ci_upper"],
                action=row["action"],
                action_confidence=row["action_confidence"],
                n_samples=row["n_samples"],
                distribution_type=row["distribution_type"],
            ),
            active_addresses=ActiveAddressesResponse(
                block_height=row["block_height"],
                active_addresses_block=row["active_addresses_block"],
                active_addresses_24h=row["active_addresses_24h"],
                unique_senders=row["unique_senders"],
                unique_receivers=row["unique_receivers"],
                is_anomaly=row["is_anomaly"],
            ),
            tx_volume=TxVolumeResponse(
                tx_count=row["tx_count"],
                tx_volume_btc=row["tx_volume_btc"],
                tx_volume_usd=row["tx_volume_usd"],
                utxoracle_price_used=row["utxoracle_price_used"],
                low_confidence=row["low_confidence"],
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        _raise_http_exception(
            status_code=500,
            public_detail="Failed to fetch latest metrics",
            log_message="Error getting latest metrics",
            exc=e,
        )


@router.get("/api/metrics/address-cohorts", response_model=AddressCohortsResponse)
async def get_address_cohorts(
    repo: Annotated[QuestDBRepository, Depends(get_questdb_repo)],
):
    """
    Get latest address balance cohorts (spec-039).
    Now served from QuestDB materialization with block-consistency check.
    """
    try:
        rows = await repo.get_address_cohorts_latest()
        if not rows:
            raise HTTPException(status_code=404, detail="No address cohort data found")

        # Hardening: Ensure all cohorts belong to the same block height (Atomicity)
        heights = {row["block_height"] for row in rows}
        if len(heights) > 1:
            # We have an inconsistent snapshot. 
            # Strategy: pick the max height and see if it's complete, 
            # otherwise fail to avoid serving Frankenstein data.
            max_height = max(heights)
            rows = [row for row in rows if row["block_height"] == max_height]
            
        # For address cohorts we expect exactly 3: retail, mid_tier, whale
        if len(rows) < 3:
            logging.error(f"Inconsistent address cohorts snapshot: expected 3 cohorts, got {len(rows)} at heights {heights}")
            raise HTTPException(
                status_code=503, 
                detail="Inconsistent snapshot detected. Materialization job may be partial."
            )

        # Map rows to response
        first = rows[0]
        cohorts = {}
        for row in rows:
            cohorts[row["cohort"]] = CohortMetricsResponse(
                cohort=row["cohort"],
                cost_basis=row["cost_basis"],
                supply_btc=row["supply_btc"],
                supply_pct=row["supply_pct"],
                mvrv=row["mvrv"],
                address_count=row["address_count"],
            )

        return AddressCohortsResponse(
            timestamp=first["ts"],
            block_height=first["block_height"],
            current_price_usd=first["current_price_usd"],
            cohorts=cohorts,
            whale_retail_spread=first["whale_retail_spread"],
            whale_retail_mvrv_ratio=first["whale_retail_mvrv_ratio"],
            total_supply_btc=first["total_supply_btc"],
            total_addresses=first["total_addresses"],
        )
    except HTTPException:
        raise
    except Exception as e:
        _raise_http_exception(
            status_code=500,
            public_detail="Failed to fetch address cohorts",
            log_message="Error getting address cohorts",
            exc=e,
        )


@router.get("/api/metrics/cost-basis", response_model=CostBasisResponse)
async def get_cost_basis(
    repo: Annotated[QuestDBRepository, Depends(get_questdb_repo)],
):
    """
    Get latest STH/LTH cost basis metrics (spec-023).
    Now served from QuestDB materialization.
    """
    try:
        row = await repo.get_cost_basis_latest()
        if not row:
            raise HTTPException(status_code=404, detail="No cost basis data found")

        return CostBasisResponse(
            timestamp=row["ts"],
            block_height=row["block_height"],
            current_price_usd=row["current_price_usd"],
            total_cost_basis=row["total_cost_basis"],
            sth_cost_basis=row["sth_cost_basis"],
            lth_cost_basis=row["lth_cost_basis"],
            sth_mvrv=row["sth_mvrv"],
            lth_mvrv=row["lth_mvrv"],
            sth_supply_btc=row["sth_supply_btc"],
            lth_supply_btc=row["lth_supply_btc"],
            confidence=row["confidence"],
        )
    except HTTPException:
        raise
    except Exception as e:
        _raise_http_exception(
            status_code=500,
            public_detail="Failed to fetch cost basis metrics",
            log_message="Error getting cost basis metrics",
            exc=e,
        )


@router.get("/api/metrics/urpd-features", response_model=URPDFeaturesResponse)
async def get_urpd_features(
    repo: Annotated[QuestDBRepository, Depends(get_questdb_repo)],
):
    """
    Get latest scalar features derived from the URPD / cost-basis distribution.
    """
    try:
        row = await repo.get_urpd_features_latest()
        if not row:
            raise HTTPException(status_code=404, detail="No URPD feature data found")

        return URPDFeaturesResponse(
            timestamp=row["ts"],
            block_height=row["block_height"],
            current_price_usd=row["current_price_usd"],
            bucket_size_usd=row["bucket_size_usd"],
            total_supply_btc=row["total_supply_btc"],
            supply_below_price_pct=row["supply_below_price_pct"],
            supply_above_price_pct=row["supply_above_price_pct"],
            top_bucket_concentration=row["top_bucket_concentration"],
            dominant_bucket_distance_pct=row["dominant_bucket_distance_pct"],
            distribution_entropy=row["distribution_entropy"],
            confidence=row["confidence"],
        )
    except HTTPException:
        raise
    except Exception as e:
        _raise_http_exception(
            status_code=500,
            public_detail="Failed to fetch URPD features",
            log_message="Error getting URPD features",
            exc=e,
        )


@router.get("/api/metrics/wallet-waves", response_model=WalletWavesResponse)
async def get_wallet_waves(
    repo: Annotated[QuestDBRepository, Depends(get_questdb_repo)],
):
    """
    Get latest wallet waves distribution (spec-025).
    Now served from QuestDB materialization with block-consistency check.
    """
    try:
        rows = await repo.get_wallet_waves_latest()
        if not rows:
            raise HTTPException(status_code=404, detail="No wallet waves data found")

        # Hardening: Atomicity check
        heights = {row["block_height"] for row in rows}
        if len(heights) > 1:
            max_height = max(heights)
            rows = [row for row in rows if row["block_height"] == max_height]

        if len(rows) < 6:
            logging.error(f"Inconsistent wallet waves snapshot: expected 6 bands, got {len(rows)} at heights {heights}")
            raise HTTPException(
                status_code=503,
                detail="Inconsistent snapshot detected. Materialization job may be partial."
            )

        first = rows[0]
        bands = [
            WalletBandMetricsResponse(
                band=row["band"],
                supply_btc=row["supply_btc"],
                supply_pct=row["supply_pct"],
                address_count=row["address_count"],
                avg_balance=row["avg_balance"],
            )
            for row in rows
        ]

        return WalletWavesResponse(
            timestamp=first["ts"],
            block_height=first["block_height"],
            total_supply_btc=first["total_supply_btc"],
            bands=bands,
            retail_supply_pct=first["retail_supply_pct"],
            institutional_supply_pct=first["institutional_supply_pct"],
            address_count_total=first["address_count_total"],
            null_address_btc=first["null_address_btc"],
            confidence=first["confidence"],
        )
    except HTTPException:
        raise
    except Exception as e:
        _raise_http_exception(
            status_code=500,
            public_detail="Failed to fetch wallet waves",
            log_message="Error getting wallet waves",
            exc=e,
        )


@router.get("/api/metrics/absorption-rates", response_model=AbsorptionRatesResponse)
async def get_absorption_rates(
    repo: Annotated[QuestDBRepository, Depends(get_questdb_repo)],
    window_days: int = Query(default=30, description="Window days for absorption calculation"),
):
    """
    Get latest absorption rates (spec-025).
    Now served from QuestDB materialization with block-consistency check.
    """
    try:
        rows = await repo.get_absorption_rates_latest(window_days)
        if not rows:
            raise HTTPException(status_code=404, detail="No absorption data found for window")

        # Hardening: Atomicity check
        heights = {row["block_height"] for row in rows}
        if len(heights) > 1:
            max_height = max(heights)
            rows = [row for row in rows if row["block_height"] == max_height]

        if len(rows) < 6:
            logging.error(f"Inconsistent absorption snapshot: expected 6 bands, got {len(rows)} at heights {heights}")
            raise HTTPException(
                status_code=503,
                detail="Inconsistent snapshot detected. Materialization job may be partial."
            )

        first = rows[0]
        bands = [
            AbsorptionRateMetricsResponse(
                band=row["band"],
                absorption_rate=row["absorption_rate"],
                supply_delta_btc=row["supply_delta_btc"],
                supply_start_btc=row["supply_start_btc"],
                supply_end_btc=row["supply_end_btc"],
            )
            for row in rows
        ]

        return AbsorptionRatesResponse(
            timestamp=first["ts"],
            block_height=first["block_height"],
            window_days=first["window_days"],
            mined_supply_btc=first["mined_supply_btc"],
            bands=bands,
            dominant_absorber=first["dominant_absorber"],
            retail_absorption=first["retail_absorption"],
            institutional_absorption=first["institutional_absorption"],
            confidence=first["confidence"],
            has_historical_data=first["has_historical_data"],
        )
    except HTTPException:
        raise
    except Exception as e:
        _raise_http_exception(
            status_code=500,
            public_detail="Failed to fetch absorption rates",
            log_message="Error getting absorption rates",
            exc=e,
        )


# =============================================================================
# Research & Operations (spec-003 Hardening)
# =============================================================================

@router.get("/api/research/tier-stats", response_model=TierObservabilityResponse)
async def get_tier_stats(
    repo: Annotated[QuestDBRepository, Depends(get_questdb_repo)],
    days: int = Query(default=30, ge=1, le=365),
):
    """
    Operator endpoint to monitor fetch tier fallbacks (T140).
    RESEARCH ONLY.
    """
    try:
        cutoff_time = (_utc_now() - timedelta(days=days)).replace(tzinfo=None)
        
        # 1. Get counts per tier
        query_counts = """
            SELECT fetch_tier, count(*) as cnt
            FROM price_analysis
            WHERE ts > $1 AND fetch_tier IS NOT NULL
            GROUP BY fetch_tier
        """
        rows = await repo.fetchall(query_counts, cutoff_time)
        
        total_samples = sum(row["cnt"] for row in rows)
        stats = []
        for row in rows:
            stats.append(TierStats(
                tier=row["fetch_tier"],
                count=row["cnt"],
                percentage=(row["cnt"] / total_samples * 100) if total_samples > 0 else 0
            ))
            
        # 2. Get last tier used
        last_row = await repo.fetchrow(
            "SELECT fetch_tier FROM price_analysis WHERE fetch_tier IS NOT NULL ORDER BY ts DESC LIMIT 1"
        )
        last_tier = last_row["fetch_tier"] if last_row else None
        
        return TierObservabilityResponse(
            timeframe_days=days,
            total_samples=total_samples,
            stats=stats,
            last_tier_used=last_tier
        )
    except Exception as e:
        _raise_http_exception(
            status_code=500,
            public_detail="Failed to fetch tier statistics",
            log_message="Error getting tier stats",
            exc=e,
        )
