# Data Model: PRO Risk Metric (spec-033)

**Date**: 2025-12-25 | **Version**: 1.0

## Entities

### 1. ProRiskResult

Primary output entity for PRO Risk calculations.

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal

RiskZone = Literal["extreme_fear", "fear", "neutral", "greed", "extreme_greed"]

@dataclass
class ProRiskResult:
    """Composite risk metric result for a specific date."""

    # Core fields
    date: datetime
    value: float                    # 0.0 - 1.0 composite score
    zone: RiskZone                  # Classification string

    # Component scores (normalized 0-1)
    components: dict[str, float] = field(default_factory=dict)

    # Metadata
    confidence: float = 1.0         # Data availability (0.0-1.0)
    block_height: Optional[int] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"value must be in [0, 1], got {self.value}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
```

**Validation Rules**:
- `value` must be in [0.0, 1.0]
- `zone` must be one of 5 valid zones
- `confidence` must be in [0.0, 1.0]
- `components` must have 6 keys when fully populated

### 2. ComponentScore

Individual metric score before aggregation.

```python
@dataclass
class ComponentScore:
    """Single component metric normalized score."""

    metric_name: str                # e.g., "mvrv_z", "sopr"
    raw_value: float                # Original metric value
    percentile: float               # Normalized 0-1 score
    weight: float                   # Weight in composite (0.05-0.30)
    history_days: int               # Days of data available
    is_valid: bool = True           # Whether sufficient history exists

    @property
    def weighted_contribution(self) -> float:
        return self.percentile * self.weight if self.is_valid else 0.0
```

**Validation Rules**:
- `percentile` must be in [0.0, 1.0]
- `weight` must be in [0.0, 1.0]
- `history_days` >= 1460 for `is_valid = True`

### 3. PercentileData

Pre-computed percentile thresholds for normalization.

```python
@dataclass
class PercentileData:
    """Cached percentile distribution for a metric."""

    metric_name: str
    as_of_date: datetime
    history_days: int               # Total days of history used

    # Key percentile thresholds (for quick lookup)
    p02: float                      # 2nd percentile (winsorization floor)
    p25: float                      # Q1
    p50: float                      # Median
    p75: float                      # Q3
    p98: float                      # 98th percentile (winsorization ceiling)

    def normalize(self, value: float) -> float:
        """Normalize value to 0-1 using stored percentiles."""
        capped = max(self.p02, min(self.p98, value))
        # Linear interpolation within percentile range
        if capped <= self.p02:
            return 0.02
        elif capped >= self.p98:
            return 0.98
        else:
            # Use pre-computed lookup or calculate from full history
            pass
```

---

## Relationships

```
                    ┌─────────────────────┐
                    │   ProRiskResult     │
                    │  (daily aggregate)  │
                    └──────────┬──────────┘
                               │ contains
           ┌───────────────────┼───────────────────┐
           │                   │                   │
    ┌──────▼──────┐     ┌──────▼──────┐     ┌──────▼──────┐
    │ComponentScore│     │ComponentScore│     │ComponentScore│
    │  (mvrv_z)    │     │   (sopr)    │     │    ...       │
    └──────┬──────┘     └──────┬──────┘     └──────────────┘
           │                   │
           │ normalized by     │ normalized by
           │                   │
    ┌──────▼──────┐     ┌──────▼──────┐
    │PercentileData│    │PercentileData│
    │  (mvrv_z)    │    │   (sopr)     │
    └─────────────┘    └──────────────┘
```

---

## Database Schema

### DuckDB Tables

```sql
-- Stores daily risk percentiles for each component metric
CREATE TABLE IF NOT EXISTS risk_percentiles (
    metric_name VARCHAR NOT NULL,
    date DATE NOT NULL,
    raw_value DOUBLE,
    percentile DOUBLE,              -- Normalized 0-1 score
    history_days INTEGER,
    PRIMARY KEY (metric_name, date)
);

-- Stores daily PRO Risk composite results
CREATE TABLE IF NOT EXISTS pro_risk_daily (
    date DATE PRIMARY KEY,
    value DOUBLE NOT NULL,          -- Composite 0-1 score
    zone VARCHAR NOT NULL,
    mvrv_z_score DOUBLE,            -- Individual components
    sopr_score DOUBLE,
    nupl_score DOUBLE,
    reserve_risk_score DOUBLE,
    puell_score DOUBLE,
    hodl_waves_score DOUBLE,
    confidence DOUBLE DEFAULT 1.0,
    block_height INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_risk_percentiles_date
    ON risk_percentiles(date);
CREATE INDEX IF NOT EXISTS idx_pro_risk_zone
    ON pro_risk_daily(zone);
```

---

## State Transitions

### Risk Zone Classification

```
Zone               Value Range      Interpretation
──────────────────────────────────────────────────
extreme_fear       [0.00, 0.20)     Strong buy signal
fear               [0.20, 0.40)     Accumulation zone
neutral            [0.40, 0.60)     Hold / DCA
greed              [0.60, 0.80)     Caution zone
extreme_greed      [0.80, 1.00]     Distribution zone
```

### Confidence States

| State | Confidence | Missing Data |
|-------|------------|--------------|
| FULL | 1.00 | None |
| HIGH | 0.85-0.99 | 1 Grade B metric |
| MEDIUM | 0.70-0.84 | 2 Grade B or 1 Grade A |
| LOW | <0.70 | Multiple Grade A metrics |

---

## Component Weights

```python
COMPONENT_WEIGHTS = {
    "mvrv_z": 0.30,         # Grade A - proven cycle indicator
    "sopr": 0.20,           # Grade A - directional accuracy 82%
    "nupl": 0.20,           # Grade A - direct P/L measure
    "reserve_risk": 0.15,   # Grade B - ARK framework
    "puell": 0.10,          # Grade B - miner-centric
    "hodl_waves": 0.05,     # Grade B - derivative metric
}

# Validation: weights must sum to 1.0
assert abs(sum(COMPONENT_WEIGHTS.values()) - 1.0) < 0.001
```

---

## Pydantic API Models

```python
from pydantic import BaseModel, Field
from datetime import date
from typing import Literal

class ProRiskComponentAPI(BaseModel):
    """API response for individual component."""
    metric: str
    raw_value: float
    normalized: float = Field(ge=0.0, le=1.0)
    weight: float
    weighted: float

class ProRiskResponseAPI(BaseModel):
    """API response for PRO Risk endpoint."""
    date: date
    value: float = Field(ge=0.0, le=1.0)
    zone: Literal["extreme_fear", "fear", "neutral", "greed", "extreme_greed"]
    components: list[ProRiskComponentAPI]
    confidence: float = Field(ge=0.0, le=1.0)
    historical_context: dict[str, float] | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2025-12-25",
                "value": 0.62,
                "zone": "greed",
                "components": [
                    {"metric": "mvrv_z", "raw_value": 2.1, "normalized": 0.71, "weight": 0.30, "weighted": 0.213},
                    {"metric": "sopr", "raw_value": 1.02, "normalized": 0.55, "weight": 0.20, "weighted": 0.110},
                ],
                "confidence": 0.95,
                "historical_context": {"percentile_30d": 0.78, "percentile_1y": 0.65}
            }
        }
```
