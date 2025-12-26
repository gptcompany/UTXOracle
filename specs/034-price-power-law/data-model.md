# Data Model: Bitcoin Price Power Law

**Feature**: spec-034 | **Date**: 2025-12-26

## Entities

### 1. PowerLawModel

Stores fitted model parameters from log-log linear regression.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| alpha | float | Intercept coefficient | Required, typically ~-17 |
| beta | float | Slope coefficient (power exponent) | Required, typically ~5.8 |
| r_squared | float | Model fit quality (0-1) | 0.0 ≤ x ≤ 1.0 |
| std_error | float | Prediction standard deviation in log10 space | > 0 |
| fitted_on | date | Last calibration date | Required |
| sample_size | int | Number of data points used | > 0 |

**Constraints**:
- `alpha` typically range: [-18, -16]
- `beta` typically range: [5.5, 6.0]
- `r_squared` should be > 0.90 for valid fit

**Pydantic Model**:
```python
from datetime import date
from pydantic import BaseModel, Field

class PowerLawModel(BaseModel):
    """Fitted power law model parameters."""
    alpha: float = Field(description="Intercept coefficient")
    beta: float = Field(description="Slope coefficient (power exponent)")
    r_squared: float = Field(ge=0.0, le=1.0, description="Model fit R²")
    std_error: float = Field(gt=0, description="Standard error in log10 space")
    fitted_on: date = Field(description="Date model was calibrated")
    sample_size: int = Field(gt=0, description="Data points used for fit")
```

### 2. PowerLawPrediction

Represents a price prediction for a specific date.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| date | date | Prediction target date | Required |
| days_since_genesis | int | Days from 2009-01-03 | > 0, computed |
| fair_value | float | Model predicted price (USD) | > 0 |
| lower_band | float | -1σ support level (USD) | > 0 |
| upper_band | float | +1σ resistance level (USD) | > 0 |
| current_price | float | None | Actual market price if available | Optional |
| deviation_pct | float | None | % above/below fair value | Optional |
| zone | str | Valuation zone classification | "undervalued", "fair", "overvalued", "unknown" |

**Pydantic Model**:
```python
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field

class PowerLawPrediction(BaseModel):
    """Price prediction for a specific date."""
    date: date
    days_since_genesis: int = Field(gt=0)
    fair_value: float = Field(gt=0, description="Model predicted price USD")
    lower_band: float = Field(gt=0, description="-1σ support level")
    upper_band: float = Field(gt=0, description="+1σ resistance level")
    current_price: float | None = Field(default=None, description="Actual market price")
    deviation_pct: float | None = Field(default=None, description="% deviation from fair value")
    zone: Literal["undervalued", "fair", "overvalued", "unknown"] = "unknown"
```

### 3. PowerLawResponse

API response combining model info and prediction.

| Field | Type | Description |
|-------|------|-------------|
| model | PowerLawModel | Current model parameters |
| prediction | PowerLawPrediction | None | Prediction for requested date |

**Pydantic Model**:
```python
class PowerLawResponse(BaseModel):
    """API response with model and optional prediction."""
    model: PowerLawModel
    prediction: PowerLawPrediction | None = None
```

### 4. PowerLawHistoryPoint

Single data point for historical chart data.

| Field | Type | Description |
|-------|------|-------------|
| date | date | Historical date |
| price | float | Actual BTC/USD price |
| fair_value | float | Model fair value at that date |
| zone | str | Zone classification at that date |

**Pydantic Model**:
```python
class PowerLawHistoryPoint(BaseModel):
    """Historical data point for charting."""
    date: date
    price: float
    fair_value: float
    zone: Literal["undervalued", "fair", "overvalued"]
```

## Relationships

```
PowerLawModel 1:N PowerLawPrediction
  - One model can generate many predictions
  - Predictions reference model.std_error for band calculation

daily_prices (existing) → PowerLawModel
  - daily_prices table is DATA SOURCE for model fitting
  - SELECT date, price_usd FROM daily_prices WHERE price_usd > 0
```

## State Transitions

### Model Lifecycle

```
[UNINITIALIZED] → fit_power_law() → [FITTED]
                                        ↓
[FITTED] → recalibrate() → [FITTED] (updated)
                                        ↓
[FITTED] → predict_price() → PowerLawPrediction
```

### Zone Classification

```
deviation_pct = (current_price - fair_value) / fair_value * 100

if deviation_pct < -20%:
    zone = "undervalued"    # Buy opportunity
elif deviation_pct > +50%:
    zone = "overvalued"     # Caution/distribution
else:
    zone = "fair"           # Neutral/hold
```

## Database Schema

### No New Tables Required

The power law model uses existing infrastructure:
- **Read**: `daily_prices` table for historical prices
- **Memory**: Model coefficients stored in-memory (6 floats)
- **No writes**: Model is computed on-demand or cached in memory

### Existing Table Used

```sql
-- From scripts/bootstrap/build_price_table.py
CREATE TABLE IF NOT EXISTS daily_prices (
    date DATE PRIMARY KEY,
    price_usd DOUBLE NOT NULL,
    block_height INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Constants

```python
# Genesis date for days calculation
GENESIS_DATE = date(2009, 1, 3)

# Default model coefficients (RBN research, 2025)
DEFAULT_ALPHA = -17.01
DEFAULT_BETA = 5.82
DEFAULT_R_SQUARED = 0.95
DEFAULT_STD_ERROR = 0.32

# Zone classification thresholds
ZONE_UNDERVALUED_THRESHOLD = -0.20  # -20%
ZONE_OVERVALUED_THRESHOLD = 0.50    # +50%

# Minimum data points for valid fit
MIN_SAMPLES_FOR_FIT = 365  # At least 1 year of data
```

## File Location

```
api/models/power_law_models.py  # Pydantic models
scripts/models/price_power_law.py  # Core calculation logic
```
