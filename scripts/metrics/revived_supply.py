"""
Revived Supply Module (spec-024).

Tracks dormant coins being spent to signal long-term holder behavior changes.
When old coins suddenly move, it often indicates a shift in market sentiment.

Key Signals:
- Rising revived supply during rally: LTH distributing to late buyers (bearish)
- Low revived supply during dip: LTH holding strong (bullish conviction)
- 5Y+ coins moving: Extremely rare, significant holder behavior shift
- Sustained elevated zone: Distribution phase, potential trend reversal

Usage:
    from scripts.metrics.revived_supply import (
        calculate_revived_supply_signal,
        classify_revived_zone,
    )

    result = calculate_revived_supply_signal(conn, block, price, timestamp)
    print(f"Revived 1Y: {result.revived_1y:.2f} BTC, Zone: {result.zone.value}")
"""

import logging
from datetime import datetime, timedelta

import duckdb

from scripts.models.metrics_models import RevivedZone, RevivedSupplyResult

logger = logging.getLogger(__name__)

# Age thresholds in days
THRESHOLD_1Y = 365
THRESHOLD_2Y = 730
THRESHOLD_5Y = 1825

# Zone thresholds in BTC/day
ZONE_THRESHOLD_NORMAL = 1000.0  # < 1000 = DORMANT
ZONE_THRESHOLD_ELEVATED = 5000.0  # < 5000 = NORMAL
ZONE_THRESHOLD_SPIKE = 10000.0  # < 10000 = ELEVATED, >= 10000 = SPIKE


def classify_revived_zone(revived_btc_per_day: float) -> RevivedZone:
    """Classify revived supply into behavioral zone.

    Zone boundaries based on historical Bitcoin on-chain data patterns:
    - DORMANT: < 1000 BTC/day (low LTH activity, stable holding)
    - NORMAL: 1000-5000 BTC/day (baseline movement)
    - ELEVATED: 5000-10000 BTC/day (increased LTH selling, watch closely)
    - SPIKE: >= 10000 BTC/day (major distribution event, potential top signal)

    Args:
        revived_btc_per_day: Daily average of revived BTC (1y+ dormant).
            Must be a finite non-negative number.

    Returns:
        RevivedZone enum member.

    Raises:
        ValueError: If revived_btc_per_day is NaN, infinite, or negative.
    """
    import math

    if math.isnan(revived_btc_per_day) or math.isinf(revived_btc_per_day):
        raise ValueError(
            f"revived_btc_per_day must be finite, got {revived_btc_per_day}"
        )
    if revived_btc_per_day < 0:
        raise ValueError(
            f"revived_btc_per_day must be non-negative, got {revived_btc_per_day}"
        )

    if revived_btc_per_day < ZONE_THRESHOLD_NORMAL:
        return RevivedZone.DORMANT
    elif revived_btc_per_day < ZONE_THRESHOLD_ELEVATED:
        return RevivedZone.NORMAL
    elif revived_btc_per_day < ZONE_THRESHOLD_SPIKE:
        return RevivedZone.ELEVATED
    else:
        return RevivedZone.SPIKE


def calculate_revived_supply_signal(
    conn: duckdb.DuckDBPyConnection,
    current_block: int,
    current_price_usd: float,
    timestamp: datetime | None = None,
    window_days: int = 30,
) -> RevivedSupplyResult:
    """Calculate revived supply metrics for dormant coin movement tracking.

    Queries spent UTXOs within the lookback window and calculates:
    - revived_1y: BTC revived after 1+ year dormancy
    - revived_2y: BTC revived after 2+ year dormancy
    - revived_5y: BTC revived after 5+ year dormancy
    - revived_total_usd: USD value of 1y revived supply
    - revived_avg_age: Weighted average age of revived UTXOs

    Args:
        conn: DuckDB connection with utxo_lifecycle_full VIEW.
        current_block: Current block height.
        current_price_usd: Current BTC price in USD.
        timestamp: Optional timestamp (defaults to now).
        window_days: Lookback window in days (default 30).

    Returns:
        RevivedSupplyResult with zone classification.
    """
    if timestamp is None:
        timestamp = datetime.utcnow()

    logger.debug(
        "Calculating revived supply for block %d, window %d days",
        current_block,
        window_days,
    )

    # Calculate window start timestamp
    window_start = timestamp - timedelta(days=window_days)
    # Convert to Unix epoch (spent_timestamp is stored as BIGINT seconds)
    window_start_epoch = int(window_start.timestamp())

    # Query revived UTXOs: spent within window, age >= 1 year at time of spending
    # Note: spent_timestamp is BIGINT (Unix epoch), not TIMESTAMP
    # Note: btc_value IS NOT NULL ensures we only count UTXOs with valid BTC values
    result = conn.execute(
        """
        SELECT
            SUM(CASE WHEN age_days >= ? THEN btc_value ELSE 0 END) AS revived_1y,
            SUM(CASE WHEN age_days >= ? THEN btc_value ELSE 0 END) AS revived_2y,
            SUM(CASE WHEN age_days >= ? THEN btc_value ELSE 0 END) AS revived_5y,
            SUM(CASE WHEN age_days >= ? THEN btc_value * age_days ELSE 0 END) AS weighted_age_sum,
            COUNT(CASE WHEN age_days >= ? AND btc_value IS NOT NULL THEN 1 END) AS utxo_count
        FROM utxo_lifecycle_full
        WHERE is_spent = TRUE
          AND age_days >= ?
          AND btc_value IS NOT NULL
          AND spent_timestamp IS NOT NULL
          AND spent_timestamp >= ?
        """,
        [
            THRESHOLD_1Y,  # revived_1y threshold
            THRESHOLD_2Y,  # revived_2y threshold
            THRESHOLD_5Y,  # revived_5y threshold
            THRESHOLD_1Y,  # for weighted age (only 1y+ UTXOs)
            THRESHOLD_1Y,  # utxo_count threshold
            THRESHOLD_1Y,  # minimum age filter
            window_start_epoch,  # Unix epoch comparison
        ],
    ).fetchone()

    # Extract results with null handling
    revived_1y = float(result[0] or 0.0)
    revived_2y = float(result[1] or 0.0)
    revived_5y = float(result[2] or 0.0)
    weighted_age_sum = float(result[3] or 0.0)
    utxo_count = int(result[4] or 0)

    logger.debug(
        "Raw revived supply: 1y=%.2f, 2y=%.2f, 5y=%.2f, count=%d",
        revived_1y,
        revived_2y,
        revived_5y,
        utxo_count,
    )

    # Calculate derived metrics
    revived_total_usd = revived_1y * current_price_usd

    # Calculate weighted average age (only for 1y+ UTXOs)
    if revived_1y > 0:
        revived_avg_age = weighted_age_sum / revived_1y
    else:
        revived_avg_age = 0.0

    # Calculate daily rate for zone classification
    revived_per_day = revived_1y / window_days if window_days > 0 else 0.0
    zone = classify_revived_zone(revived_per_day)

    # Determine confidence based on data quality
    if utxo_count == 0:
        confidence = 0.0  # No data
    elif utxo_count < 100:
        confidence = 0.5  # Low sample size
    else:
        confidence = 0.85  # Default high confidence for Tier A metric

    result_obj = RevivedSupplyResult(
        revived_1y=revived_1y,
        revived_2y=revived_2y,
        revived_5y=revived_5y,
        revived_total_usd=revived_total_usd,
        revived_avg_age=revived_avg_age,
        zone=zone,
        utxo_count=utxo_count,
        window_days=window_days,
        current_price_usd=current_price_usd,
        block_height=current_block,
        timestamp=timestamp,
        confidence=confidence,
    )

    logger.info(
        "Revived supply: 1y=%.2f BTC, 2y=%.2f BTC, 5y=%.2f BTC, "
        "zone=%s, count=%d, confidence=%.2f",
        revived_1y,
        revived_2y,
        revived_5y,
        zone.value,
        utxo_count,
        confidence,
    )

    return result_obj
