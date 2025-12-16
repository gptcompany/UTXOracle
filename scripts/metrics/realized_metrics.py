"""Realized Metrics Module.

This module calculates realized-value based metrics from UTXO lifecycle data:
- Realized Cap: Sum of UTXO values at creation price
- MVRV: Market Value to Realized Value ratio
- NUPL: Net Unrealized Profit/Loss

These are Tier A metrics with high predictive value for market analysis.

Spec: spec-017
Created: 2025-12-09
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

import duckdb

if TYPE_CHECKING:
    from scripts.models.metrics_models import MVRVExtendedSignal, UTXOSetSnapshot

logger = logging.getLogger(__name__)

# =============================================================================
# TTL Cache for API Performance (T063)
# =============================================================================

# Cache TTL in seconds (5 minutes - shorter than 10-min cron interval)
CACHE_TTL_SECONDS = 300

# Simple module-level cache for frequently accessed data
_snapshot_cache: dict[str, tuple[float, Any]] = {}


def _get_cached(key: str) -> Any | None:
    """Get value from cache if not expired."""
    if key in _snapshot_cache:
        timestamp, value = _snapshot_cache[key]
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            return value
        # Expired, remove from cache
        del _snapshot_cache[key]
    return None


def _set_cached(key: str, value: Any) -> None:
    """Set value in cache with current timestamp."""
    _snapshot_cache[key] = (time.time(), value)


def clear_cache() -> None:
    """Clear all cached data. Call after sync operations."""
    _snapshot_cache.clear()
    logger.debug("Realized metrics cache cleared")


def calculate_realized_cap(conn: duckdb.DuckDBPyConnection) -> float:
    """Calculate Realized Cap from unspent UTXOs.

    Realized Cap = Sum of (UTXO_value × creation_price) for all unspent UTXOs.

    Args:
        conn: DuckDB connection.

    Returns:
        Realized Cap in USD.
    """
    result = conn.execute(
        """
        SELECT COALESCE(SUM(realized_value_usd), 0)
        FROM utxo_lifecycle_full
        WHERE is_spent = FALSE
        """,
    ).fetchone()

    return result[0] if result else 0.0


def calculate_market_cap(total_supply_btc: float, current_price_usd: float) -> float:
    """Calculate Market Cap.

    Market Cap = Total Supply × Current Price.

    Args:
        total_supply_btc: Total BTC supply.
        current_price_usd: Current BTC price in USD.

    Returns:
        Market Cap in USD.

    Raises:
        ValueError: If price is negative.
    """
    # B7 fix: Guard against negative price values
    if current_price_usd < 0:
        raise ValueError(f"Invalid negative price: {current_price_usd}")
    return total_supply_btc * current_price_usd


def calculate_mvrv(market_cap_usd: float, realized_cap_usd: float) -> float:
    """Calculate MVRV ratio.

    MVRV = Market Cap / Realized Cap

    Interpretation:
    - MVRV > 3.7: Historically indicates market tops
    - MVRV < 1.0: Market trading below aggregate cost basis (capitulation)
    - MVRV = 1.0: Market at cost basis

    Args:
        market_cap_usd: Market Cap in USD.
        realized_cap_usd: Realized Cap in USD.

    Returns:
        MVRV ratio.
    """
    if realized_cap_usd <= 0:
        return 0.0
    return market_cap_usd / realized_cap_usd


def calculate_nupl(market_cap_usd: float, realized_cap_usd: float) -> float:
    """Calculate NUPL (Net Unrealized Profit/Loss).

    NUPL = (Market Cap - Realized Cap) / Market Cap

    Interpretation:
    - NUPL > 0.75: Euphoria/Greed (historically indicates tops)
    - NUPL 0.5-0.75: Belief/Denial
    - NUPL 0.25-0.5: Optimism/Anxiety
    - NUPL 0-0.25: Hope/Fear
    - NUPL < 0: Capitulation (historically indicates bottoms)

    Args:
        market_cap_usd: Market Cap in USD.
        realized_cap_usd: Realized Cap in USD.

    Returns:
        NUPL value (-1 to 1 range typically).
    """
    if market_cap_usd <= 0:
        return 0.0
    return (market_cap_usd - realized_cap_usd) / market_cap_usd


def get_total_unspent_supply(conn: duckdb.DuckDBPyConnection) -> float:
    """Get total BTC supply in unspent UTXOs.

    Args:
        conn: DuckDB connection.

    Returns:
        Total BTC in unspent UTXOs.
    """
    result = conn.execute(
        """
        SELECT COALESCE(SUM(btc_value), 0)
        FROM utxo_lifecycle_full
        WHERE is_spent = FALSE
        """,
    ).fetchone()

    return result[0] if result else 0.0


def create_snapshot(
    conn: duckdb.DuckDBPyConnection,
    block_height: int,
    timestamp: datetime,
    current_price_usd: float,
    hodl_waves: dict[str, float] | None = None,
) -> UTXOSetSnapshot:
    """Create a point-in-time snapshot of UTXO set metrics.

    Args:
        conn: DuckDB connection.
        block_height: Current block height.
        timestamp: Current block timestamp.
        current_price_usd: Current BTC price in USD.
        hodl_waves: Optional pre-calculated HODL waves.

    Returns:
        UTXOSetSnapshot with all metrics.
    """
    from scripts.metrics.utxo_lifecycle import get_sth_lth_supply, get_supply_by_cohort
    from scripts.models.metrics_models import AgeCohortsConfig, UTXOSetSnapshot

    # Calculate supply metrics
    total_supply = get_total_unspent_supply(conn)
    sth_supply, lth_supply = get_sth_lth_supply(conn, block_height)

    # Calculate supply by cohort
    config = AgeCohortsConfig()
    supply_by_cohort = get_supply_by_cohort(conn, block_height, config)

    # Calculate realized metrics
    realized_cap = calculate_realized_cap(conn)
    market_cap = calculate_market_cap(total_supply, current_price_usd)
    mvrv = calculate_mvrv(market_cap, realized_cap)
    nupl = calculate_nupl(market_cap, realized_cap)

    # Calculate HODL waves if not provided
    if hodl_waves is None:
        hodl_waves = {}
        if total_supply > 0:
            for cohort, btc in supply_by_cohort.items():
                hodl_waves[cohort] = (btc / total_supply) * 100

    snapshot = UTXOSetSnapshot(
        block_height=block_height,
        timestamp=timestamp,
        total_supply_btc=total_supply,
        sth_supply_btc=sth_supply,
        lth_supply_btc=lth_supply,
        supply_by_cohort=supply_by_cohort,
        realized_cap_usd=realized_cap,
        market_cap_usd=market_cap,
        mvrv=mvrv,
        nupl=nupl,
        hodl_waves=hodl_waves,
    )

    # Save snapshot to database
    save_snapshot(conn, snapshot)

    return snapshot


def save_snapshot(conn: duckdb.DuckDBPyConnection, snapshot: UTXOSetSnapshot) -> None:
    """Save a snapshot to the database.

    Automatically clears the snapshot cache to ensure fresh data.

    Args:
        conn: DuckDB connection.
        snapshot: UTXOSetSnapshot to save.
    """
    # Clear cache to ensure fresh data on next read
    clear_cache()

    conn.execute(
        """
        INSERT INTO utxo_snapshots (
            block_height, timestamp,
            total_supply_btc, sth_supply_btc, lth_supply_btc,
            realized_cap_usd, market_cap_usd, mvrv, nupl,
            hodl_waves_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (block_height) DO UPDATE SET
            timestamp = EXCLUDED.timestamp,
            total_supply_btc = EXCLUDED.total_supply_btc,
            sth_supply_btc = EXCLUDED.sth_supply_btc,
            lth_supply_btc = EXCLUDED.lth_supply_btc,
            realized_cap_usd = EXCLUDED.realized_cap_usd,
            market_cap_usd = EXCLUDED.market_cap_usd,
            mvrv = EXCLUDED.mvrv,
            nupl = EXCLUDED.nupl,
            hodl_waves_json = EXCLUDED.hodl_waves_json
        """,
        [
            snapshot.block_height,
            snapshot.timestamp,
            snapshot.total_supply_btc,
            snapshot.sth_supply_btc,
            snapshot.lth_supply_btc,
            snapshot.realized_cap_usd,
            snapshot.market_cap_usd,
            snapshot.mvrv,
            snapshot.nupl,
            json.dumps(snapshot.hodl_waves),
        ],
    )


def load_snapshot(
    conn: duckdb.DuckDBPyConnection, block_height: int
) -> UTXOSetSnapshot | None:
    """Load a snapshot from the database.

    Args:
        conn: DuckDB connection.
        block_height: Block height of the snapshot.

    Returns:
        UTXOSetSnapshot or None if not found.
    """
    from scripts.models.metrics_models import UTXOSetSnapshot

    result = conn.execute(
        """
        SELECT block_height, timestamp,
               total_supply_btc, sth_supply_btc, lth_supply_btc,
               realized_cap_usd, market_cap_usd, mvrv, nupl,
               hodl_waves_json
        FROM utxo_snapshots
        WHERE block_height = ?
        """,
        [block_height],
    ).fetchone()

    if result is None:
        return None

    hodl_waves = json.loads(result[9]) if result[9] else {}

    return UTXOSetSnapshot(
        block_height=result[0],
        timestamp=result[1],
        total_supply_btc=result[2],
        sth_supply_btc=result[3],
        lth_supply_btc=result[4],
        supply_by_cohort={},  # Not stored in DB, calculate if needed
        realized_cap_usd=result[5],
        market_cap_usd=result[6],
        mvrv=result[7],
        nupl=result[8],
        hodl_waves=hodl_waves,
    )


def get_latest_snapshot(conn: duckdb.DuckDBPyConnection) -> UTXOSetSnapshot | None:
    """Get the most recent snapshot (with TTL caching).

    Uses a 5-minute cache to reduce database queries for API requests.
    Cache is automatically invalidated after TTL expires.

    Args:
        conn: DuckDB connection.

    Returns:
        Most recent UTXOSetSnapshot or None.
    """
    # Check cache first
    cached = _get_cached("latest_snapshot")
    if cached is not None:
        logger.debug("Cache hit for latest_snapshot")
        return cached

    # Cache miss - query database
    result = conn.execute(
        """
        SELECT block_height FROM utxo_snapshots
        ORDER BY block_height DESC LIMIT 1
        """,
    ).fetchone()

    if result is None:
        return None

    snapshot = load_snapshot(conn, result[0])

    # Cache the result
    if snapshot is not None:
        _set_cached("latest_snapshot", snapshot)
        logger.debug(f"Cached latest_snapshot (block {snapshot.block_height})")

    return snapshot


def get_market_cap_history(
    conn: duckdb.DuckDBPyConnection,
    days: int = 365,
) -> list[float]:
    """Get historical market cap values for MVRV-Z calculation.

    Retrieves market cap values from utxo_snapshots table for the specified
    number of days. Used for calculating standard deviation in MVRV-Z score.

    Args:
        conn: DuckDB connection.
        days: Number of days of history to retrieve (default 365).

    Returns:
        List of market cap values (most recent first). Empty list if no data.

    Note:
        For valid MVRV-Z calculation, at least 30 days of history is recommended.
        If insufficient data exists, returns available data (may be empty).
    """
    # Query market cap history from snapshots, ordered by block height descending
    # We select all available snapshots and limit by the most recent 'days' worth
    # This approach works better for testing than NOW()-based queries
    result = conn.execute(
        """
        SELECT market_cap_usd
        FROM utxo_snapshots
        ORDER BY block_height DESC
        LIMIT ?
        """,
        [days],
    ).fetchall()

    history = [row[0] for row in result if row[0] is not None]

    if len(history) < 30:
        logger.warning(
            f"Insufficient market cap history: {len(history)} entries "
            f"(recommended: 30+)"
        )

    return history


def calculate_mvrv_z(
    market_cap: float,
    realized_cap: float,
    market_cap_history: list[float],
) -> float:
    """Calculate MVRV-Z Score for cross-cycle comparison.

    MVRV-Z = (Market Cap - Realized Cap) / StdDev(Market Cap History)

    The Z-score normalizes MVRV by historical volatility, enabling:
    - Cross-cycle comparison (MVRV of 3.0 in 2017 ≠ 3.0 in 2024)
    - Statistical extreme detection (Z > 7 = historically extreme)

    Args:
        market_cap: Current market cap in USD.
        realized_cap: Current realized cap in USD.
        market_cap_history: List of historical market cap values (365 days recommended).

    Returns:
        MVRV-Z score. Returns 0.0 if:
        - History has fewer than 30 values
        - Standard deviation is 0 (all values identical)

    Signal Interpretation:
        > 7: EXTREME_SELL - Historically extreme overvaluation
        3 to 7: CAUTION - Elevated valuation
        -0.5 to 3: NORMAL - Fair value range
        < -0.5: ACCUMULATION - Historically extreme undervaluation
    """
    import statistics

    # Guard: Insufficient history
    if len(market_cap_history) < 30:
        logger.warning(
            f"MVRV-Z: Insufficient history ({len(market_cap_history)} values, need 30+). "
            "Returning 0.0"
        )
        return 0.0

    # Calculate standard deviation
    try:
        std = statistics.stdev(market_cap_history)
    except statistics.StatisticsError:
        logger.warning("MVRV-Z: Failed to calculate stdev. Returning 0.0")
        return 0.0

    # Guard: Zero standard deviation
    if std == 0:
        logger.warning(
            "MVRV-Z: Zero standard deviation (all history values identical). "
            "Returning 0.0"
        )
        return 0.0

    # Calculate Z-score
    mvrv_z = (market_cap - realized_cap) / std

    logger.debug(
        f"MVRV-Z: market_cap={market_cap:.0f}, realized_cap={realized_cap:.0f}, "
        f"std={std:.0f}, z={mvrv_z:.2f}"
    )

    return mvrv_z


def calculate_cohort_realized_cap(
    conn: duckdb.DuckDBPyConnection,
    current_block: int,
    cohort: str,
    threshold_days: int = 155,
) -> float:
    """Calculate Realized Cap for a specific age cohort (STH or LTH).

    STH (Short-Term Holders): UTXOs created within threshold_days
    LTH (Long-Term Holders): UTXOs created before threshold_days

    Args:
        conn: DuckDB connection.
        current_block: Current block height for age calculation.
        cohort: "STH" or "LTH".
        threshold_days: Days threshold for STH/LTH boundary (default 155).

    Returns:
        Realized Cap in USD for the specified cohort.

    Raises:
        ValueError: If cohort is not "STH" or "LTH".
    """
    if cohort not in ("STH", "LTH"):
        raise ValueError(f"Invalid cohort: {cohort}. Must be 'STH' or 'LTH'.")

    # Convert days to blocks (144 blocks per day)
    threshold_blocks = threshold_days * 144
    cutoff_block = current_block - threshold_blocks

    if cohort == "STH":
        # STH: UTXOs created after cutoff (younger than threshold)
        result = conn.execute(
            """
            SELECT COALESCE(SUM(realized_value_usd), 0)
            FROM utxo_lifecycle_full
            WHERE is_spent = FALSE
              AND creation_block > ?
            """,
            [cutoff_block],
        ).fetchone()
    else:
        # LTH: UTXOs created at or before cutoff (older than threshold)
        result = conn.execute(
            """
            SELECT COALESCE(SUM(realized_value_usd), 0)
            FROM utxo_lifecycle_full
            WHERE is_spent = FALSE
              AND creation_block <= ?
            """,
            [cutoff_block],
        ).fetchone()

    return result[0] if result else 0.0


def calculate_cohort_mvrv(
    market_cap_usd: float, cohort_realized_cap_usd: float
) -> float:
    """Calculate MVRV for a specific cohort (STH or LTH).

    Cohort-MVRV = Market Cap / Cohort Realized Cap

    This metric helps identify whether short-term or long-term holders
    are in profit or loss, which has different market implications:
    - STH-MVRV > 1: Short-term holders in profit (potential distribution)
    - STH-MVRV < 1: Short-term holders in loss (potential accumulation)
    - LTH-MVRV > 1: Long-term holders in profit (patient holders)
    - LTH-MVRV < 1: Long-term holders in loss (extremely rare)

    Args:
        market_cap_usd: Total market cap in USD.
        cohort_realized_cap_usd: Realized cap for the cohort (STH or LTH).

    Returns:
        MVRV ratio for the cohort. Returns 0.0 if cohort realized cap is 0.
    """
    if cohort_realized_cap_usd <= 0:
        return 0.0
    return market_cap_usd / cohort_realized_cap_usd


def classify_mvrv_z_zone(mvrv_z: float) -> str:
    """Classify MVRV-Z score into market zones.

    Zone thresholds based on historical analysis:
    - EXTREME_SELL: Z > 7.0 (historically extreme overvaluation)
    - CAUTION: 3.0 <= Z <= 7.0 (elevated valuation)
    - NORMAL: -0.5 <= Z < 3.0 (fair value range)
    - ACCUMULATION: Z < -0.5 (historically extreme undervaluation)

    Args:
        mvrv_z: MVRV-Z score.

    Returns:
        Zone classification string.

    Raises:
        ValueError: If mvrv_z is NaN.
    """
    import math

    # B6 fix: Handle NaN input
    if math.isnan(mvrv_z):
        raise ValueError("mvrv_z cannot be NaN")

    if mvrv_z > 7.0:
        return "EXTREME_SELL"
    elif mvrv_z >= 3.0:
        return "CAUTION"
    elif mvrv_z >= -0.5:
        return "NORMAL"
    else:
        return "ACCUMULATION"


def calculate_mvrv_confidence(mvrv_z: float, history_days: int) -> float:
    """Calculate confidence score for MVRV-Z signal.

    Confidence is based on:
    1. History length (more data = higher confidence)
    2. Distance from zone thresholds (clearer signal = higher confidence)

    Args:
        mvrv_z: Current MVRV-Z score.
        history_days: Number of days of market cap history used.

    Returns:
        Confidence score from 0.0 to 1.0.

    Raises:
        ValueError: If history_days is negative.
    """
    # B2 fix: Validate history_days
    if history_days < 0:
        raise ValueError(f"history_days must be non-negative, got {history_days}")

    # Base confidence from history length
    # 0 days -> 0.0, 30 days -> 0.4, 180 days -> 0.7, 365+ days -> 0.9
    if history_days < 30:
        history_confidence = history_days / 100.0  # Max 0.3 for < 30 days
    elif history_days < 180:
        history_confidence = 0.4 + (history_days - 30) / 500.0  # 0.4 to 0.7
    else:
        history_confidence = min(0.7 + (history_days - 180) / 600.0, 0.9)  # Up to 0.9

    # Zone thresholds
    thresholds = [-0.5, 3.0, 7.0]

    # Distance to nearest threshold
    min_distance = min(abs(mvrv_z - t) for t in thresholds)

    # Threshold confidence: closer = lower confidence
    # Distance 0 -> 0.5, Distance 2+ -> 1.0
    threshold_confidence = min(0.5 + min_distance / 4.0, 1.0)

    # Combined confidence (weighted average)
    confidence = history_confidence * 0.6 + threshold_confidence * 0.4

    return min(max(confidence, 0.0), 1.0)


def create_mvrv_extended_signal(
    conn: duckdb.DuckDBPyConnection,
    current_block: int,
    current_price_usd: float,
    timestamp: datetime,
    threshold_days: int = 155,
) -> "MVRVExtendedSignal":
    """Create a complete MVRVExtendedSignal with all metrics.

    Calculates all MVRV variants, Z-score, zone classification, and confidence.

    Args:
        conn: DuckDB connection.
        current_block: Current block height.
        current_price_usd: Current BTC price in USD.
        timestamp: Current timestamp.
        threshold_days: STH/LTH threshold in days (default 155).

    Returns:
        MVRVExtendedSignal with all metrics populated.
    """
    from scripts.models.metrics_models import MVRVExtendedSignal

    # Get total supply and calculate market cap
    total_supply = get_total_unspent_supply(conn)
    market_cap = calculate_market_cap(total_supply, current_price_usd)

    # Get realized caps
    realized_cap = calculate_realized_cap(conn)
    sth_realized = calculate_cohort_realized_cap(
        conn, current_block, "STH", threshold_days
    )
    lth_realized = calculate_cohort_realized_cap(
        conn, current_block, "LTH", threshold_days
    )

    # Calculate base MVRV
    mvrv = calculate_mvrv(market_cap, realized_cap)

    # Calculate cohort MVRVs
    sth_mvrv = calculate_cohort_mvrv(market_cap, sth_realized)
    lth_mvrv = calculate_cohort_mvrv(market_cap, lth_realized)

    # Get market cap history for Z-score
    history = get_market_cap_history(conn)
    history_days = len(history)

    # Calculate MVRV-Z
    mvrv_z = calculate_mvrv_z(market_cap, realized_cap, history)

    # Classify zone and calculate confidence
    zone = classify_mvrv_z_zone(mvrv_z)
    confidence = calculate_mvrv_confidence(mvrv_z, history_days)

    return MVRVExtendedSignal(
        mvrv=mvrv,
        market_cap_usd=market_cap,
        realized_cap_usd=realized_cap,
        mvrv_z=mvrv_z,
        z_history_days=history_days,
        sth_mvrv=sth_mvrv,
        sth_realized_cap_usd=sth_realized,
        lth_mvrv=lth_mvrv,
        lth_realized_cap_usd=lth_realized,
        zone=zone,
        confidence=confidence,
        timestamp=timestamp,
        block_height=current_block,
        threshold_days=threshold_days,
    )
