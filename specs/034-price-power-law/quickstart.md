# Quickstart: Bitcoin Price Power Law Model

## Overview

The Bitcoin Price Power Law model calculates fair value based on the mathematical relationship between price and time since genesis. Use it to assess whether Bitcoin is undervalued or overvalued relative to its long-term trend.

## Prerequisites

- UTXOracle API running (`api/main.py`)
- `daily_prices` table populated (from `scripts/bootstrap/build_price_table.py`)

## Quick API Usage

### Get Current Model

```bash
curl http://localhost:8000/api/v1/models/power-law
```

Response:
```json
{
  "model": {
    "alpha": -17.01,
    "beta": 5.82,
    "r_squared": 0.95,
    "std_error": 0.32,
    "fitted_on": "2025-01-01",
    "sample_size": 5800
  }
}
```

### Get Price Prediction

```bash
# For today
curl "http://localhost:8000/api/v1/models/power-law/predict"

# For specific date with current price
curl "http://localhost:8000/api/v1/models/power-law/predict?date=2025-12-25&current_price=98500"
```

Response:
```json
{
  "model": { ... },
  "prediction": {
    "date": "2025-12-25",
    "days_since_genesis": 6200,
    "fair_value": 89234.56,
    "lower_band": 42567.89,
    "upper_band": 187012.34,
    "current_price": 98500.00,
    "deviation_pct": 10.4,
    "zone": "fair"
  }
}
```

### Get Historical Data for Charting

```bash
curl "http://localhost:8000/api/v1/models/power-law/history?days=365"
```

## Python Library Usage

```python
from scripts.models.price_power_law import (
    days_since_genesis,
    fit_power_law,
    predict_price,
    DEFAULT_MODEL,
)
from datetime import date
import duckdb

# Using default model
prediction = predict_price(DEFAULT_MODEL, date.today(), current_price=98500)
print(f"Fair value: ${prediction.fair_value:,.2f}")
print(f"Zone: {prediction.zone}")
print(f"Deviation: {prediction.deviation_pct:.1f}%")

# Fit custom model from database
conn = duckdb.connect("/path/to/utxo_lifecycle.duckdb")
result = conn.execute("""
    SELECT date, price_usd
    FROM daily_prices
    WHERE price_usd > 0
    ORDER BY date
""").fetchall()
conn.close()

dates = [row[0] for row in result]
prices = [row[1] for row in result]

custom_model = fit_power_law(dates, prices)
print(f"Custom fit R²: {custom_model.r_squared:.3f}")
```

## Zone Interpretation

| Zone | Deviation | Interpretation | Action |
|------|-----------|----------------|--------|
| undervalued | < -20% | Below long-term trend | Accumulation opportunity |
| fair | -20% to +50% | At or near trend | Hold / DCA |
| overvalued | > +50% | Above long-term trend | Caution / Distribution |

## Model Formula

```
Price(t) = 10^(α + β × log10(days_since_genesis))
```

Where:
- α = -17.01 (intercept)
- β = 5.82 (slope/power exponent)
- days_since_genesis = days from 2009-01-03

Support/Resistance bands: ±1 standard deviation in log10 space.

## Frontend Visualization

Navigate to `http://localhost:8000/power_law.html` for the interactive chart showing:
- Historical prices (scatter)
- Fair value regression line
- ±1σ bands
- Current zone indication

## Recalibration

To update the model with latest price data:

```bash
curl -X POST http://localhost:8000/api/v1/models/power-law/recalibrate
```

The model auto-recalibrates monthly on API startup if stale.
