# Spec-034: Bitcoin Price Power Law Model

## Overview

Implement the Bitcoin Power Law price model: a mathematical relationship between Bitcoin's price and time since genesis block. This is **distinct** from UTXO distribution power law - it models price evolution over time.

## Mathematical Foundation

### Core Formula

```
Price(t) = 10^(α + β * log10(days_since_genesis))
```

Where:
- `t` = days since Bitcoin genesis (2009-01-03)
- `α` = intercept coefficient (~-17.01)
- `β` = slope coefficient (~5.82)

### Derivation

Log-log linear regression on historical BTC/USD prices yields:
```
log10(Price) = α + β * log10(days)
```

This implies price grows as a power of time: `Price ∝ days^β`

## Technical Design

### Data Model

```python
@dataclass
class PowerLawModel:
    alpha: float           # Intercept
    beta: float            # Slope (power exponent)
    r_squared: float       # Fit quality
    std_error: float       # Prediction std deviation
    fitted_on: date        # Last calibration date
    sample_size: int       # Days of data used

@dataclass
class PowerLawPrediction:
    date: date
    fair_value: float      # Model predicted price
    lower_band: float      # -1 std dev (support)
    upper_band: float      # +1 std dev (resistance)
    current_price: float   # Actual price
    deviation_pct: float   # % above/below fair value
    zone: str              # "undervalued", "fair", "overvalued"
```

### Implementation

```python
from datetime import date
import numpy as np

GENESIS_DATE = date(2009, 1, 3)

def days_since_genesis(target_date: date) -> int:
    return (target_date - GENESIS_DATE).days

def fit_power_law(
    dates: list[date],
    prices: list[float]
) -> PowerLawModel:
    """Fit power law model using log-log linear regression."""
    days = np.array([days_since_genesis(d) for d in dates])
    log_days = np.log10(days)
    log_prices = np.log10(prices)

    # Linear regression: log_price = alpha + beta * log_days
    beta, alpha = np.polyfit(log_days, log_prices, 1)

    # Calculate R² and std error
    predictions = alpha + beta * log_days
    ss_res = np.sum((log_prices - predictions) ** 2)
    ss_tot = np.sum((log_prices - np.mean(log_prices)) ** 2)
    r_squared = 1 - (ss_res / ss_tot)
    std_error = np.sqrt(ss_res / (len(dates) - 2))

    return PowerLawModel(
        alpha=alpha,
        beta=beta,
        r_squared=r_squared,
        std_error=std_error,
        fitted_on=dates[-1],
        sample_size=len(dates)
    )

def predict_price(
    model: PowerLawModel,
    target_date: date,
    current_price: float | None = None
) -> PowerLawPrediction:
    """Predict fair value and bands for target date."""
    days = days_since_genesis(target_date)
    log_fair = model.alpha + model.beta * np.log10(days)
    fair_value = 10 ** log_fair

    # Bands at ±1 std dev in log space
    lower_band = 10 ** (log_fair - model.std_error)
    upper_band = 10 ** (log_fair + model.std_error)

    deviation_pct = None
    zone = "unknown"
    if current_price:
        deviation_pct = ((current_price - fair_value) / fair_value) * 100
        if deviation_pct < -20:
            zone = "undervalued"
        elif deviation_pct > 50:
            zone = "overvalued"
        else:
            zone = "fair"

    return PowerLawPrediction(
        date=target_date,
        fair_value=fair_value,
        lower_band=lower_band,
        upper_band=upper_band,
        current_price=current_price,
        deviation_pct=deviation_pct,
        zone=zone
    )
```

### Pre-Computed Coefficients

Based on RBN and community research:
```python
# Default model (as of 2025)
DEFAULT_MODEL = PowerLawModel(
    alpha=-17.01,
    beta=5.82,
    r_squared=0.95,
    std_error=0.32,
    fitted_on=date(2025, 1, 1),
    sample_size=5800
)
```

## API Endpoint

```
GET /api/v1/models/power-law
GET /api/v1/models/power-law/predict?date=2025-12-25

Response:
{
    "model": {
        "alpha": -17.01,
        "beta": 5.82,
        "r_squared": 0.95,
        "last_calibrated": "2025-01-01"
    },
    "prediction": {
        "date": "2025-12-25",
        "fair_value": 89234.56,
        "lower_band": 42567.89,
        "upper_band": 187012.34,
        "current_price": 98500.00,
        "deviation_pct": 10.4,
        "zone": "fair"
    }
}
```

## Visualization

Frontend chart showing:
1. Historical log-log price chart
2. Regression line (fair value)
3. ±1σ bands (support/resistance corridors)
4. Current price position

## Data Requirements

1. **Historical prices**: Daily BTC/USD since 2010 (via mempool.space or similar)
2. **Model refresh**: Re-fit monthly or quarterly
3. **Prediction range**: Up to 10 years forward

## Implementation Files

```
scripts/models/power_law.py          # Core model
api/routes/models.py                 # API endpoint
frontend/charts/power_law.js         # Visualization
tests/test_power_law.py              # Unit tests
```

## Validation Criteria

1. **R² > 0.93**: Model explains >93% of price variance in log-log space
2. **Historical accuracy**: Price stays within ±1σ bands >68% of time
3. **No lookahead bias**: Model only uses data prior to prediction date
   - Test: `fit_power_law(dates[:N], prices[:N])` must produce identical results regardless of data after index N
   - Test: Prediction for date D must not change when prices after D are added to training set

## Status

**Draft** - Awaiting implementation approval
