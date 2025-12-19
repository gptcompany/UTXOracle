"""
Net Realized Profit/Loss Module (spec-028)

Calculates realized gains/losses from spent UTXOs to show actual capital flows.
When coins move at a profit/loss, this metric captures the aggregate flow direction.

Metrics:
- realized_profit_usd/btc: Total profit realized from profitable UTXOs
- realized_loss_usd/btc: Total loss realized from unprofitable UTXOs
- net_realized_pnl: Net P/L (profit - loss)
- profit_loss_ratio: Profit/Loss ratio (> 1 = profit dominant)
- signal: PROFIT_DOMINANT, LOSS_DOMINANT, or NEUTRAL

Dependencies:
- spec-017 (UTXO Lifecycle Engine) - provides UTXO creation/spent prices
- utxo_lifecycle_full VIEW with columns:
  - creation_price_usd, spent_price_usd, btc_value, is_spent, spent_timestamp

Usage:
    from scripts.metrics.net_realized_pnl import (
        calculate_net_realized_pnl,
        get_net_realized_pnl_history,
    )

    # Calculate current window
    result = calculate_net_realized_pnl(conn, window_hours=24)
    print(f"Net P/L: ${result.net_realized_pnl_usd:,.2f}")
    print(f"Signal: {result.signal}")

    # Get historical data
    history = get_net_realized_pnl_history(conn, days=30)
    for day in history:
        print(f"{day.date}: ${day.net_realized_pnl_usd:,.2f}")

Spec: spec-028
Created: 2025-12-19
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Literal

import duckdb

from scripts.models.metrics_models import (
    NetRealizedPnLResult,
    NetRealizedPnLHistoryPoint,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Signal Interpretation (T011, T012)
# =============================================================================


def _determine_signal(
    net_pnl_usd: float,
    profit_loss_ratio: float,
) -> Literal["PROFIT_DOMINANT", "LOSS_DOMINANT", "NEUTRAL"]:
    """
    Determine market signal from Net Realized P/L.

    Args:
        net_pnl_usd: Net P/L value (positive = profit dominant)
        profit_loss_ratio: Ratio of profit to loss (> 1 = profit dominant)

    Returns:
        Signal interpretation based on net P/L direction
    """
    if net_pnl_usd > 0:
        return "PROFIT_DOMINANT"
    elif net_pnl_usd < 0:
        return "LOSS_DOMINANT"
    else:
        return "NEUTRAL"


def _calculate_profit_loss_ratio(
    realized_profit_usd: float,
    realized_loss_usd: float,
) -> float:
    """
    Calculate profit/loss ratio with division-by-zero handling.

    Args:
        realized_profit_usd: Total profit realized
        realized_loss_usd: Total loss realized

    Returns:
        Ratio (profit / loss):
        - If both are zero: returns 0.0
        - If only loss is zero: returns 1e9 (represents "effectively infinite")
        - Otherwise: returns profit / loss

    Note:
        Returns 1e9 instead of float('inf') for JSON serialization compatibility.
        Pydantic/FastAPI serializes infinity as null, which is semantically wrong.
    """
    if realized_loss_usd == 0:
        if realized_profit_usd == 0:
            return 0.0
        else:
            # Return large finite number instead of infinity for JSON compatibility
            return 1e9
    return realized_profit_usd / realized_loss_usd


# =============================================================================
# Core Calculation (T010)
# =============================================================================


def calculate_net_realized_pnl(
    conn: duckdb.DuckDBPyConnection,
    window_hours: int = 24,
) -> NetRealizedPnLResult:
    """
    Calculate Net Realized P/L for spent UTXOs within time window.

    Aggregates realized gains/losses from all UTXOs spent within the window
    where both creation_price_usd and spent_price_usd are valid (> 0).

    Args:
        conn: DuckDB connection
        window_hours: Time window in hours (1-720, default 24)

    Returns:
        NetRealizedPnLResult with all metrics

    Raises:
        ValueError: If window_hours out of range
    """
    # Validate window_hours
    if window_hours < 1 or window_hours > 720:
        raise ValueError(f"window_hours must be between 1 and 720, got {window_hours}")

    # Calculate window start time
    window_start = datetime.now() - timedelta(hours=window_hours)

    # Query from data-model.md
    query = """
        SELECT
            -- USD metrics
            COALESCE(SUM(CASE WHEN spent_price_usd > creation_price_usd
                THEN (spent_price_usd - creation_price_usd) * btc_value ELSE 0 END), 0) AS realized_profit_usd,
            COALESCE(SUM(CASE WHEN spent_price_usd < creation_price_usd
                THEN (creation_price_usd - spent_price_usd) * btc_value ELSE 0 END), 0) AS realized_loss_usd,

            -- BTC metrics (volume of profitable/unprofitable UTXOs)
            COALESCE(SUM(CASE WHEN spent_price_usd > creation_price_usd
                THEN btc_value ELSE 0 END), 0) AS profit_btc_volume,
            COALESCE(SUM(CASE WHEN spent_price_usd < creation_price_usd
                THEN btc_value ELSE 0 END), 0) AS loss_btc_volume,

            -- Counts
            COUNT(CASE WHEN spent_price_usd > creation_price_usd THEN 1 END) AS profit_count,
            COUNT(CASE WHEN spent_price_usd < creation_price_usd THEN 1 END) AS loss_count

        FROM utxo_lifecycle_full
        WHERE is_spent = TRUE
          AND spent_timestamp >= ?
          AND creation_price_usd > 0
          AND spent_price_usd > 0
    """

    result = conn.execute(query, [window_start]).fetchone()

    # Unpack results
    realized_profit_usd = float(result[0])
    realized_loss_usd = float(result[1])
    profit_btc_volume = float(result[2])
    loss_btc_volume = float(result[3])
    profit_count = int(result[4]) if result[4] else 0
    loss_count = int(result[5]) if result[5] else 0

    # Calculate derived metrics
    net_realized_pnl_usd = realized_profit_usd - realized_loss_usd
    net_realized_pnl_btc = profit_btc_volume - loss_btc_volume
    profit_loss_ratio = _calculate_profit_loss_ratio(
        realized_profit_usd, realized_loss_usd
    )
    signal = _determine_signal(net_realized_pnl_usd, profit_loss_ratio)

    return NetRealizedPnLResult(
        realized_profit_usd=realized_profit_usd,
        realized_loss_usd=realized_loss_usd,
        net_realized_pnl_usd=net_realized_pnl_usd,
        realized_profit_btc=profit_btc_volume,
        realized_loss_btc=loss_btc_volume,
        net_realized_pnl_btc=net_realized_pnl_btc,
        profit_utxo_count=profit_count,
        loss_utxo_count=loss_count,
        profit_loss_ratio=profit_loss_ratio,
        signal=signal,
        window_hours=window_hours,
        timestamp=datetime.now(),
    )


# =============================================================================
# Historical Data (T018)
# =============================================================================


def get_net_realized_pnl_history(
    conn: duckdb.DuckDBPyConnection,
    days: int = 30,
) -> list[NetRealizedPnLHistoryPoint]:
    """
    Get daily Net Realized P/L history for trend analysis.

    Returns one data point per day with aggregated profit/loss metrics.

    Args:
        conn: DuckDB connection
        days: Number of days of history (1-365, default 30)

    Returns:
        List of NetRealizedPnLHistoryPoint sorted by date (oldest first)

    Raises:
        ValueError: If days out of range
    """
    # Validate days parameter
    if days < 1 or days > 365:
        raise ValueError(f"days must be between 1 and 365, got {days}")

    # Calculate start date
    start_date = datetime.now() - timedelta(days=days)

    # Query with GROUP BY date
    query = """
        SELECT
            DATE(spent_timestamp) AS date,
            COALESCE(SUM(CASE WHEN spent_price_usd > creation_price_usd
                THEN (spent_price_usd - creation_price_usd) * btc_value ELSE 0 END), 0) AS realized_profit_usd,
            COALESCE(SUM(CASE WHEN spent_price_usd < creation_price_usd
                THEN (creation_price_usd - spent_price_usd) * btc_value ELSE 0 END), 0) AS realized_loss_usd,
            COUNT(CASE WHEN spent_price_usd > creation_price_usd THEN 1 END) AS profit_count,
            COUNT(CASE WHEN spent_price_usd < creation_price_usd THEN 1 END) AS loss_count
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
        # Handle both date objects and strings
        if isinstance(row_date, str):
            row_date = datetime.strptime(row_date, "%Y-%m-%d").date()
        elif isinstance(row_date, datetime):
            row_date = row_date.date()

        realized_profit = float(row[1])
        realized_loss = float(row[2])
        profit_count = int(row[3]) if row[3] else 0
        loss_count = int(row[4]) if row[4] else 0

        history.append(
            NetRealizedPnLHistoryPoint(
                date=row_date,
                realized_profit_usd=realized_profit,
                realized_loss_usd=realized_loss,
                net_realized_pnl_usd=realized_profit - realized_loss,
                profit_utxo_count=profit_count,
                loss_utxo_count=loss_count,
            )
        )

    return history
