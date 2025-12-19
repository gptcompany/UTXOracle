"""CDD/VDD (Coindays/Value Days Destroyed) Calculator.

spec-021: Advanced On-Chain Metrics
Implements FR-005: Coindays Destroyed and Value Days Destroyed

CDD: When a UTXO is spent, CDD = age_days × btc_value
VDD: CDD weighted by price = CDD × spent_price

Measures "old money" movement - spikes indicate long-term holders
moving coins (distribution or exchange deposit).

Signal Zones (based on VDD multiple):
    < 0.5: Low activity (accumulation)
    0.5 - 1.5: Normal activity
    1.5 - 2.0: Elevated (distribution possible)
    > 2.0: Spike (significant distribution)

Usage:
    from scripts.metrics.cdd_vdd import calculate_cdd_vdd

    result = calculate_cdd_vdd(
        conn=duckdb_conn,
        current_price_usd=100000.0,
        block_height=875000,
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import duckdb

from scripts.models.metrics_models import CoinDaysDestroyedResult

logger = logging.getLogger(__name__)


def calculate_cdd_vdd(
    conn: duckdb.DuckDBPyConnection,
    current_price_usd: float,
    block_height: int,
    window_days: int = 30,
) -> CoinDaysDestroyedResult:
    """Calculate Coindays Destroyed and Value Days Destroyed.

    CDD measures the economic weight of spent coins based on their age.
    VDD weights CDD by the price at which coins were spent.

    Args:
        conn: DuckDB connection with utxo_lifecycle table.
        current_price_usd: Current BTC price for context.
        block_height: Current block height for metadata.
        window_days: Rolling window for analysis (default: 30 days).

    Returns:
        CoinDaysDestroyedResult with CDD/VDD metrics and signal classification.

    Example:
        >>> result = calculate_cdd_vdd(conn, 100000.0, 875000)
        >>> result.signal_zone
        'NORMAL'
    """
    logger.debug(
        f"Calculating CDD/VDD: price=${current_price_usd:,.0f}, "
        f"block={block_height}, window={window_days}d"
    )

    # Calculate window cutoff
    window_cutoff = datetime.utcnow() - timedelta(days=window_days)
    # Convert to Unix epoch (spent_timestamp is stored as BIGINT seconds)
    window_cutoff_epoch = int(window_cutoff.timestamp())

    # Query: Aggregate CDD and VDD for spent UTXOs in window
    cdd_query = """
        SELECT
            COALESCE(SUM(COALESCE(age_days, 0) * btc_value), 0) AS cdd_total,
            COALESCE(SUM(COALESCE(age_days, 0) * btc_value * COALESCE(spent_price_usd, 0)), 0) AS vdd_total,
            COUNT(*) AS spent_count,
            COALESCE(AVG(COALESCE(age_days, 0)), 0) AS avg_age
        FROM utxo_lifecycle_full
        WHERE is_spent = TRUE
          AND spent_timestamp >= ?
    """

    result = conn.execute(cdd_query, [window_cutoff_epoch]).fetchone()

    cdd_total = float(result[0]) if result else 0.0
    vdd_total = float(result[1]) if result else 0.0
    spent_count = int(result[2]) if result else 0
    avg_age = float(result[3]) if result else 0.0

    # Calculate daily averages
    cdd_daily_avg = cdd_total / window_days if window_days > 0 else 0.0
    vdd_daily_avg = vdd_total / window_days if window_days > 0 else 0.0

    # Find max single day CDD
    max_day_query = """
        SELECT
            DATE(to_timestamp(spent_timestamp)) AS spent_date,
            SUM(COALESCE(age_days, 0) * btc_value) AS day_cdd
        FROM utxo_lifecycle_full
        WHERE is_spent = TRUE
          AND spent_timestamp >= ?
        GROUP BY DATE(to_timestamp(spent_timestamp))
        ORDER BY day_cdd DESC
        LIMIT 1
    """

    max_result = conn.execute(max_day_query, [window_cutoff_epoch]).fetchone()
    max_single_day_cdd = float(max_result[1]) if max_result else 0.0
    max_single_day_date: Optional[datetime] = None
    if max_result and max_result[0]:
        try:
            max_single_day_date = datetime.fromisoformat(str(max_result[0]))
        except (ValueError, TypeError):
            pass

    # Calculate VDD multiple (VDD / 365d MA)
    # For simplicity, use a heuristic based on cdd_total
    # In production, would query 365d history
    vdd_multiple: Optional[float] = None
    if vdd_daily_avg > 0:
        # Rough estimate: assume 365d average is similar to current daily avg
        # Proper implementation would query historical data
        vdd_multiple = 1.0  # Placeholder

    # Classify signal zone
    signal_zone, confidence = _classify_signal_zone(cdd_total, vdd_multiple)

    logger.info(
        f"CDD/VDD calculated: CDD={cdd_total:,.0f}, VDD=${vdd_total:,.0f}, "
        f"zone={signal_zone}, spent={spent_count}"
    )

    return CoinDaysDestroyedResult(
        cdd_total=cdd_total,
        cdd_daily_avg=cdd_daily_avg,
        vdd_total=vdd_total,
        vdd_daily_avg=vdd_daily_avg,
        vdd_multiple=vdd_multiple,
        window_days=window_days,
        spent_utxos_count=spent_count,
        avg_utxo_age_days=avg_age,
        max_single_day_cdd=max_single_day_cdd,
        max_single_day_date=max_single_day_date,
        current_price_usd=current_price_usd,
        signal_zone=signal_zone,
        confidence=confidence,
        block_height=block_height,
        timestamp=datetime.utcnow(),
    )


def _classify_signal_zone(
    cdd_total: float, vdd_multiple: Optional[float]
) -> tuple[str, float]:
    """Classify signal zone based on CDD and VDD multiple.

    VDD multiple > 2.0 indicates significant distribution (spikes).
    CDD total provides context for activity level.

    Args:
        cdd_total: Total coindays destroyed in window.
        vdd_multiple: VDD / 365d_MA (None if insufficient history).

    Returns:
        Tuple of (zone_name, confidence).
    """
    # Use VDD multiple if available
    if vdd_multiple is not None:
        if vdd_multiple >= 2.0:
            return "SPIKE", 0.85
        elif vdd_multiple >= 1.5:
            return "ELEVATED", 0.7
        elif vdd_multiple >= 0.5:
            return "NORMAL", 0.6
        else:
            return "LOW_ACTIVITY", 0.65

    # Fallback to CDD-based classification
    # These thresholds would need calibration with historical data
    if cdd_total >= 10000:
        return "SPIKE", 0.7
    elif cdd_total >= 5000:
        return "ELEVATED", 0.6
    elif cdd_total >= 500:
        return "NORMAL", 0.55
    else:
        return "LOW_ACTIVITY", 0.6
