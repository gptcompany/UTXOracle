"""
Bitcoin Price Power Law Model (spec-034)

Implements the mathematical relationship between Bitcoin's price and time since genesis.
Uses log-log linear regression: log10(Price) = alpha + beta * log10(days_since_genesis)

Core functions:
- days_since_genesis: Calculate days from Bitcoin genesis date
- fit_power_law: Fit model parameters from historical data
- predict_price: Generate prediction with bands and zone classification
"""

from datetime import date
from typing import Literal

import numpy as np

from api.models.power_law_models import (
    PowerLawModel,
    PowerLawPrediction,
)

# Genesis date for days calculation
GENESIS_DATE = date(2009, 1, 3)

# Default model coefficients (RBN research, 2025)
DEFAULT_ALPHA = -17.01
DEFAULT_BETA = 5.82
DEFAULT_R_SQUARED = 0.95
DEFAULT_STD_ERROR = 0.32

# Zone classification thresholds
ZONE_UNDERVALUED_THRESHOLD = -0.20  # -20%
ZONE_OVERVALUED_THRESHOLD = 0.50  # +50%

# Minimum data points for valid fit
MIN_SAMPLES_FOR_FIT = 365  # At least 1 year of data

# Default model instance
DEFAULT_MODEL = PowerLawModel(
    alpha=DEFAULT_ALPHA,
    beta=DEFAULT_BETA,
    r_squared=DEFAULT_R_SQUARED,
    std_error=DEFAULT_STD_ERROR,
    fitted_on=date(2025, 1, 1),
    sample_size=5800,
)


def days_since_genesis(target_date: date) -> int:
    """
    Calculate days since Bitcoin genesis block (2009-01-03).

    Args:
        target_date: The date to calculate days for

    Returns:
        Number of days since genesis

    Raises:
        ValueError: If target_date is before genesis
    """
    delta = target_date - GENESIS_DATE
    if delta.days <= 0:
        raise ValueError(
            f"Date {target_date} is before or on genesis date {GENESIS_DATE}"
        )
    return delta.days


def fit_power_law(
    dates: list[date],
    prices: list[float],
) -> PowerLawModel:
    """
    Fit power law model from historical price data.

    Uses log-log linear regression: log10(price) = alpha + beta * log10(days)

    Args:
        dates: List of dates
        prices: List of corresponding prices in USD

    Returns:
        Fitted PowerLawModel with coefficients and fit statistics

    Raises:
        ValueError: If insufficient data points or mismatched lengths
    """
    if len(dates) != len(prices):
        raise ValueError(f"Length mismatch: {len(dates)} dates vs {len(prices)} prices")

    if len(dates) < MIN_SAMPLES_FOR_FIT:
        raise ValueError(
            f"Insufficient data: {len(dates)} < {MIN_SAMPLES_FOR_FIT} required"
        )

    # Filter valid data points (positive prices, after genesis)
    valid_days = []
    valid_log_prices = []

    for d, p in zip(dates, prices):
        if p > 0:
            try:
                days = days_since_genesis(d)
                valid_days.append(days)
                valid_log_prices.append(np.log10(p))
            except ValueError:
                continue

    if len(valid_days) < MIN_SAMPLES_FOR_FIT:
        raise ValueError(
            f"Insufficient valid data: {len(valid_days)} < {MIN_SAMPLES_FOR_FIT}"
        )

    # Log-transform days
    log_days = np.log10(valid_days)

    # Linear regression: log10(price) = alpha + beta * log10(days)
    n = len(log_days)
    sum_x = np.sum(log_days)
    sum_y = np.sum(valid_log_prices)
    sum_xy = np.sum(log_days * valid_log_prices)
    sum_x2 = np.sum(log_days**2)
    sum_y2 = np.sum(np.array(valid_log_prices) ** 2)

    # Calculate slope (beta) and intercept (alpha)
    denominator = n * sum_x2 - sum_x**2
    beta = (n * sum_xy - sum_x * sum_y) / denominator
    alpha = (sum_y - beta * sum_x) / n

    # Calculate R-squared
    ss_tot = sum_y2 - (sum_y**2) / n
    ss_res = sum_y2 - alpha * sum_y - beta * sum_xy
    r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

    # Calculate standard error of residuals
    predictions = alpha + beta * log_days
    residuals = np.array(valid_log_prices) - predictions
    std_error = float(np.std(residuals))

    return PowerLawModel(
        alpha=float(alpha),
        beta=float(beta),
        r_squared=float(max(0.0, min(1.0, r_squared))),
        std_error=max(0.001, std_error),  # Ensure positive
        fitted_on=max(dates),  # Last date in dataset
        sample_size=len(valid_days),
    )


def classify_zone(
    deviation_pct: float,
) -> Literal["undervalued", "fair", "overvalued"]:
    """
    Classify price zone based on deviation from fair value.

    Args:
        deviation_pct: Percentage deviation from fair value (e.g., 0.10 = 10%)

    Returns:
        Zone classification
    """
    if deviation_pct < ZONE_UNDERVALUED_THRESHOLD:
        return "undervalued"
    elif deviation_pct > ZONE_OVERVALUED_THRESHOLD:
        return "overvalued"
    else:
        return "fair"


def predict_price(
    model: PowerLawModel,
    target_date: date,
    current_price: float | None = None,
) -> PowerLawPrediction:
    """
    Generate price prediction for a specific date.

    Args:
        model: Power law model with fitted parameters
        target_date: Date to predict for
        current_price: Optional current market price for deviation calculation

    Returns:
        PowerLawPrediction with fair value, bands, and zone
    """
    days = days_since_genesis(target_date)
    log_days = np.log10(days)

    # Fair value: 10^(alpha + beta * log10(days))
    log_fair_value = model.alpha + model.beta * log_days
    fair_value = float(10**log_fair_value)

    # Bands: +/- 1 standard deviation in log space
    lower_band = float(10 ** (log_fair_value - model.std_error))
    upper_band = float(10 ** (log_fair_value + model.std_error))

    # Calculate deviation and zone if current price provided
    deviation_pct: float | None = None
    zone: Literal["undervalued", "fair", "overvalued", "unknown"] = "unknown"

    if current_price is not None and current_price > 0:
        deviation_pct = (current_price - fair_value) / fair_value
        zone = classify_zone(deviation_pct)

    return PowerLawPrediction(
        date=target_date,
        days_since_genesis=days,
        fair_value=fair_value,
        lower_band=lower_band,
        upper_band=upper_band,
        current_price=current_price,
        deviation_pct=deviation_pct,
        zone=zone,
    )
