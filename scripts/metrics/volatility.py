"""
Bitcoin Price Volatility Calculator.

Calculates historical volatility using log returns standard deviation.
Annualized volatility is the standard metric for comparing across assets.

Formula:
    Daily Return = ln(Price_t / Price_t-1)
    Volatility = StdDev(Daily Returns) × sqrt(365)

Interpretation:
- < 30%: Low volatility (rare for BTC)
- 30-60%: Normal BTC volatility
- 60-100%: High volatility (common in bull/bear markets)
- > 100%: Extreme volatility (major events)

Usage:
    from scripts.metrics.volatility import calculate_volatility, VolatilityResult

    result = calculate_volatility(
        prices=[95000, 96000, 94500, 97000, 96500],
        window_days=30,
    )
    print(f"Annualized Volatility: {result.annualized_pct:.1f}%")
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import duckdb


@dataclass
class VolatilityResult:
    """Volatility calculation result."""

    daily_volatility: float  # Standard deviation of daily returns
    annualized_pct: float  # Annualized volatility as percentage
    window_days: int  # Number of days in calculation window
    regime: str  # "low", "normal", "high", "extreme"
    date: date
    timestamp: datetime

    @property
    def is_extreme(self) -> bool:
        return self.annualized_pct > 100


# Volatility regime thresholds (annualized %)
VOL_LOW = 30
VOL_HIGH = 60
VOL_EXTREME = 100

# Trading days per year for annualization
TRADING_DAYS_YEAR = 365


def calculate_volatility(
    prices: list[float],
    window_days: Optional[int] = None,
    target_date: Optional[date] = None,
) -> VolatilityResult:
    """Calculate price volatility from a series of prices.

    Args:
        prices: List of prices (oldest first)
        window_days: Window size (defaults to len(prices))
        target_date: Date for the metric (defaults to today)

    Returns:
        VolatilityResult with daily and annualized volatility

    Raises:
        ValueError: If fewer than 3 prices provided (need 2+ log returns for variance)
    """
    # B1 fix: Require 3 prices for meaningful volatility (2 log returns for variance)
    # With only 2 prices we get 1 log return, and variance of single value is always 0
    if len(prices) < 3:
        raise ValueError("At least 3 prices required for volatility calculation")

    # Use all prices if window not specified
    if window_days is None:
        window_days = len(prices)

    # Take last N prices based on window
    prices = prices[-window_days:]

    # Calculate log returns
    log_returns = []
    for i in range(1, len(prices)):
        if prices[i - 1] > 0 and prices[i] > 0:
            log_return = math.log(prices[i] / prices[i - 1])
            log_returns.append(log_return)

    if len(log_returns) < 1:
        raise ValueError("Not enough valid prices for volatility calculation")

    # Calculate standard deviation of returns
    mean_return = sum(log_returns) / len(log_returns)
    variance = sum((r - mean_return) ** 2 for r in log_returns) / len(log_returns)
    daily_vol = math.sqrt(variance)

    # Annualize: multiply by sqrt(trading days per year)
    annualized_vol = daily_vol * math.sqrt(TRADING_DAYS_YEAR)
    annualized_pct = annualized_vol * 100

    # Determine regime
    if annualized_pct < VOL_LOW:
        regime = "low"
    elif annualized_pct < VOL_HIGH:
        regime = "normal"
    elif annualized_pct < VOL_EXTREME:
        regime = "high"
    else:
        regime = "extreme"

    return VolatilityResult(
        daily_volatility=daily_vol,
        annualized_pct=annualized_pct,
        window_days=len(prices),
        regime=regime,
        date=target_date or date.today(),
        timestamp=datetime.now(),
    )


def calculate_volatility_from_db(
    conn: duckdb.DuckDBPyConnection,
    window_days: int = 30,
    target_date: Optional[date] = None,
) -> Optional[VolatilityResult]:
    """Calculate volatility from DuckDB price history.

    Args:
        conn: DuckDB connection with daily_prices table
        window_days: Rolling window in days
        target_date: End date for calculation (defaults to latest)

    Returns:
        VolatilityResult or None if insufficient data
    """
    # Query price history
    query = """
        SELECT price_usd
        FROM daily_prices
        WHERE price_usd > 0
        ORDER BY date DESC
        LIMIT ?
    """

    result = conn.execute(query, [window_days + 1]).fetchall()

    if len(result) < 2:
        return None

    # Prices are in DESC order, reverse to get oldest first
    prices = [row[0] for row in reversed(result)]

    return calculate_volatility(prices, window_days, target_date)
