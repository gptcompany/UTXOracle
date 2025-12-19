"""
P/L Ratio (Dominance) Module (spec-029)

Derives P/L ratio and normalized dominance metrics from spec-028 Net Realized P/L
to provide market regime identification.

Metrics:
- pl_ratio: Profit / Loss ratio (> 1 = profit dominant)
- pl_dominance: (Profit - Loss) / (Profit + Loss), normalized -1 to +1
- dominance_zone: Market regime classification (EXTREME_PROFIT to EXTREME_LOSS)

Dependencies:
- spec-028 (Net Realized P/L) - provides realized_profit_usd and realized_loss_usd
- utxo_lifecycle_full VIEW with columns:
  - creation_price_usd, spent_price_usd, btc_value, is_spent, spent_timestamp

Usage:
    from scripts.metrics.pl_ratio import (
        calculate_pl_ratio,
        get_pl_ratio_history,
    )

    # Calculate current window
    result = calculate_pl_ratio(conn, window_hours=24)
    print(f"P/L Ratio: {result.pl_ratio:.2f}")
    print(f"Zone: {result.dominance_zone.value}")

    # Get historical data
    history = get_pl_ratio_history(conn, days=30)
    for day in history:
        print(f"{day.date}: {day.dominance_zone.value}")

Spec: spec-029
Created: 2025-12-19
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import duckdb

from scripts.models.metrics_models import (
    PLRatioResult,
    PLRatioHistoryPoint,
    PLDominanceZone,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Zone Classification Thresholds (from data-model.md)
# =============================================================================

EXTREME_PROFIT_THRESHOLD = 5.0  # ratio > 5.0
PROFIT_THRESHOLD = 1.5  # ratio > 1.5
NEUTRAL_LOW_THRESHOLD = 0.67  # ratio > 0.67
LOSS_THRESHOLD = 0.2  # ratio > 0.2
# Below 0.2 = EXTREME_LOSS


# =============================================================================
# Helper Functions (T007, T008)
# =============================================================================


def _determine_zone(pl_ratio: float) -> PLDominanceZone:
    """
    Determine market regime zone from P/L ratio.

    Thresholds (from spec):
        EXTREME_PROFIT: ratio > 5.0
        PROFIT: ratio > 1.5
        NEUTRAL: ratio > 0.67
        LOSS: ratio > 0.2
        EXTREME_LOSS: ratio <= 0.2

    Args:
        pl_ratio: Profit / Loss ratio (>= 0)

    Returns:
        PLDominanceZone classification
    """
    if pl_ratio > EXTREME_PROFIT_THRESHOLD:
        return PLDominanceZone.EXTREME_PROFIT
    elif pl_ratio > PROFIT_THRESHOLD:
        return PLDominanceZone.PROFIT
    elif pl_ratio >= NEUTRAL_LOW_THRESHOLD:
        return PLDominanceZone.NEUTRAL
    elif pl_ratio >= LOSS_THRESHOLD:
        return PLDominanceZone.LOSS
    else:
        return PLDominanceZone.EXTREME_LOSS


def _calculate_pl_dominance(
    realized_profit_usd: float,
    realized_loss_usd: float,
) -> float:
    """
    Calculate normalized P/L dominance.

    Formula: (Profit - Loss) / (Profit + Loss)

    Range: -1.0 to +1.0
        +1.0 = 100% profit (no loss)
        0.0 = neutral (equal profit/loss)
        -1.0 = 100% loss (no profit)

    Args:
        realized_profit_usd: Total profit realized
        realized_loss_usd: Total loss realized

    Returns:
        Dominance value in range [-1.0, 1.0]
        Returns 0.0 when both are zero (no activity)
    """
    total = realized_profit_usd + realized_loss_usd
    if total == 0:
        return 0.0
    return (realized_profit_usd - realized_loss_usd) / total


def _calculate_pl_ratio_value(
    realized_profit_usd: float,
    realized_loss_usd: float,
) -> float:
    """
    Calculate P/L ratio with division-by-zero handling.

    Args:
        realized_profit_usd: Total profit realized
        realized_loss_usd: Total loss realized

    Returns:
        Ratio (profit / loss):
        - If both are zero: returns 0.0
        - If only loss is zero: returns 1e9 (JSON-safe "infinity")
        - Otherwise: returns profit / loss
    """
    if realized_loss_usd == 0:
        if realized_profit_usd == 0:
            return 0.0
        else:
            return 1e9  # JSON-safe infinity
    return realized_profit_usd / realized_loss_usd


# =============================================================================
# Core Calculation (T009)
# =============================================================================


def calculate_pl_ratio(
    conn: duckdb.DuckDBPyConnection,
    window_hours: int = 24,
) -> PLRatioResult:
    """
    Calculate P/L Ratio and Dominance for spent UTXOs within time window.

    Derives ratio and normalized dominance from realized profit/loss to
    identify market regime (euphoria vs capitulation).

    Args:
        conn: DuckDB connection
        window_hours: Time window in hours (1-720, default 24)

    Returns:
        PLRatioResult with all metrics

    Raises:
        ValueError: If window_hours out of range
    """
    if window_hours < 1 or window_hours > 720:
        raise ValueError(f"window_hours must be between 1 and 720, got {window_hours}")

    window_start = datetime.now() - timedelta(hours=window_hours)

    # Query for profit/loss aggregation (same as spec-028)
    query = """
        SELECT
            COALESCE(SUM(CASE WHEN spent_price_usd > creation_price_usd
                THEN (spent_price_usd - creation_price_usd) * btc_value ELSE 0 END), 0) AS realized_profit_usd,
            COALESCE(SUM(CASE WHEN spent_price_usd < creation_price_usd
                THEN (creation_price_usd - spent_price_usd) * btc_value ELSE 0 END), 0) AS realized_loss_usd
        FROM utxo_lifecycle_full
        WHERE is_spent = TRUE
          AND spent_timestamp >= ?
          AND creation_price_usd > 0
          AND spent_price_usd > 0
    """

    result = conn.execute(query, [window_start]).fetchone()

    realized_profit_usd = float(result[0])
    realized_loss_usd = float(result[1])

    # Calculate derived metrics
    pl_ratio = _calculate_pl_ratio_value(realized_profit_usd, realized_loss_usd)
    pl_dominance = _calculate_pl_dominance(realized_profit_usd, realized_loss_usd)
    profit_dominant = pl_ratio > 1.0
    dominance_zone = _determine_zone(pl_ratio)

    return PLRatioResult(
        pl_ratio=pl_ratio,
        pl_dominance=pl_dominance,
        profit_dominant=profit_dominant,
        dominance_zone=dominance_zone,
        realized_profit_usd=realized_profit_usd,
        realized_loss_usd=realized_loss_usd,
        window_hours=window_hours,
        timestamp=datetime.now(),
    )


# =============================================================================
# Historical Data (T013)
# =============================================================================


def get_pl_ratio_history(
    conn: duckdb.DuckDBPyConnection,
    days: int = 30,
) -> list[PLRatioHistoryPoint]:
    """
    Get daily P/L Ratio history for trend analysis.

    Returns one data point per day with aggregated profit/loss and derived
    ratio/dominance metrics.

    Args:
        conn: DuckDB connection
        days: Number of days of history (1-365, default 30)

    Returns:
        List of PLRatioHistoryPoint sorted by date (oldest first)

    Raises:
        ValueError: If days out of range
    """
    if days < 1 or days > 365:
        raise ValueError(f"days must be between 1 and 365, got {days}")

    start_date = datetime.now() - timedelta(days=days)

    query = """
        SELECT
            DATE(spent_timestamp) AS date,
            COALESCE(SUM(CASE WHEN spent_price_usd > creation_price_usd
                THEN (spent_price_usd - creation_price_usd) * btc_value ELSE 0 END), 0) AS realized_profit_usd,
            COALESCE(SUM(CASE WHEN spent_price_usd < creation_price_usd
                THEN (creation_price_usd - spent_price_usd) * btc_value ELSE 0 END), 0) AS realized_loss_usd
        FROM utxo_lifecycle_full
        WHERE is_spent = TRUE
          AND spent_timestamp >= ?
          AND creation_price_usd > 0
          AND spent_price_usd > 0
        GROUP BY DATE(spent_timestamp)
        ORDER BY date ASC
    """

    results = conn.execute(query, [start_date]).fetchall()

    history = []
    for row in results:
        row_date = row[0]
        if isinstance(row_date, str):
            row_date = datetime.strptime(row_date, "%Y-%m-%d").date()
        elif isinstance(row_date, datetime):
            row_date = row_date.date()

        realized_profit = float(row[1])
        realized_loss = float(row[2])

        pl_ratio = _calculate_pl_ratio_value(realized_profit, realized_loss)
        pl_dominance = _calculate_pl_dominance(realized_profit, realized_loss)
        dominance_zone = _determine_zone(pl_ratio)

        history.append(
            PLRatioHistoryPoint(
                date=row_date,
                pl_ratio=pl_ratio,
                pl_dominance=pl_dominance,
                dominance_zone=dominance_zone,
                realized_profit_usd=realized_profit,
                realized_loss_usd=realized_loss,
            )
        )

    return history
