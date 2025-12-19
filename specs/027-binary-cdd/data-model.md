# Data Model: Binary CDD Indicator

**Date**: 2025-12-18 | **Spec**: 027-binary-cdd

## Entities

### BinaryCDDResult (Dataclass)

Primary output entity for Binary CDD calculations.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cdd_today` | `float` | Yes | Today's total Coin Days Destroyed |
| `cdd_mean` | `float` | Yes | Mean CDD over lookback window |
| `cdd_std` | `float` | Yes | Standard deviation of CDD over window |
| `cdd_zscore` | `Optional[float]` | No | Z-score (null if insufficient data) |
| `cdd_percentile` | `Optional[float]` | No | Percentile rank (0-100) |
| `binary_cdd` | `int` | Yes | Binary flag (0 or 1) |
| `threshold_used` | `float` | Yes | Sigma threshold applied |
| `window_days` | `int` | Yes | Lookback window size |
| `data_points` | `int` | Yes | Actual data points available |
| `insufficient_data` | `bool` | Yes | True if < 30 days history |
| `block_height` | `int` | Yes | Block height at calculation |
| `timestamp` | `datetime` | Yes | Calculation timestamp |

### Validation Rules

1. **cdd_today**: Must be >= 0 (CDD cannot be negative)
2. **cdd_mean**: Must be >= 0
3. **cdd_std**: Must be >= 0
4. **cdd_zscore**: Can be negative (below-average CDD is meaningful)
5. **cdd_percentile**: Must be in range [0, 100] if present
6. **binary_cdd**: Must be 0 or 1
7. **threshold_used**: Must be in range [1.0, 4.0]
8. **window_days**: Must be in range [30, 730] (30 days min, 2 years max)
9. **data_points**: Must be > 0

### State Transitions

Binary CDD is stateless - no state transitions. Each calculation is independent based on current blockchain data.

## Data Sources

### Input: utxo_lifecycle_full (DuckDB Table)

Existing table from spec-017/021 containing UTXO lifecycle data.

| Column | Type | Used For |
|--------|------|----------|
| `spent_timestamp` | `TIMESTAMP` | Date grouping |
| `age_days` | `INTEGER` | Coin age at spend |
| `btc_value` | `FLOAT` | BTC amount |
| `is_spent` | `BOOLEAN` | Filter spent UTXOs |

### Query: Daily CDD Aggregation

```sql
SELECT
    DATE(spent_timestamp) AS spend_date,
    SUM(COALESCE(age_days, 0) * btc_value) AS daily_cdd
FROM utxo_lifecycle_full
WHERE is_spent = TRUE
  AND spent_timestamp >= CURRENT_DATE - INTERVAL {window_days} DAY
GROUP BY DATE(spent_timestamp)
ORDER BY spend_date
```

## Relationships

```
utxo_lifecycle_full (source)
         │
         ▼
   [Aggregation]
         │
         ▼
   daily_cdd[]
         │
         ▼
   [Z-Score Calc]
         │
         ▼
  BinaryCDDResult
```

## Python Dataclass Definition

```python
@dataclass
class BinaryCDDResult:
    """Binary CDD statistical significance result.

    Converts raw CDD into actionable binary signal based on
    z-score threshold exceeding N-sigma.

    Spec: spec-027
    """
    cdd_today: float
    cdd_mean: float
    cdd_std: float
    cdd_zscore: Optional[float]
    cdd_percentile: Optional[float]
    binary_cdd: int  # 0 or 1
    threshold_used: float
    window_days: int
    data_points: int
    insufficient_data: bool
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate Binary CDD fields."""
        if self.cdd_today < 0:
            raise ValueError(f"cdd_today must be >= 0: {self.cdd_today}")
        if self.cdd_mean < 0:
            raise ValueError(f"cdd_mean must be >= 0: {self.cdd_mean}")
        if self.cdd_std < 0:
            raise ValueError(f"cdd_std must be >= 0: {self.cdd_std}")
        if self.cdd_percentile is not None and not 0 <= self.cdd_percentile <= 100:
            raise ValueError(f"cdd_percentile must be in [0, 100]: {self.cdd_percentile}")
        if self.binary_cdd not in (0, 1):
            raise ValueError(f"binary_cdd must be 0 or 1: {self.binary_cdd}")
        if not 1.0 <= self.threshold_used <= 4.0:
            raise ValueError(f"threshold_used must be in [1.0, 4.0]: {self.threshold_used}")
        if not 30 <= self.window_days <= 730:
            raise ValueError(f"window_days must be in [30, 730]: {self.window_days}")
        if self.data_points < 1:
            raise ValueError(f"data_points must be > 0: {self.data_points}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "cdd_today": self.cdd_today,
            "cdd_mean": self.cdd_mean,
            "cdd_std": self.cdd_std,
            "cdd_zscore": self.cdd_zscore,
            "cdd_percentile": self.cdd_percentile,
            "binary_cdd": self.binary_cdd,
            "threshold_used": self.threshold_used,
            "window_days": self.window_days,
            "data_points": self.data_points,
            "insufficient_data": self.insufficient_data,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
        }
```

## Pydantic Response Model

```python
class BinaryCDDResponse(BaseModel):
    """Binary CDD API response."""

    cdd_today: float = Field(..., description="Today's CDD value")
    cdd_mean: float = Field(..., description="Mean CDD over lookback window")
    cdd_std: float = Field(..., description="Std dev of CDD over window")
    cdd_zscore: Optional[float] = Field(None, description="Z-score (null if insufficient data)")
    cdd_percentile: Optional[float] = Field(None, description="Percentile rank (0-100)")
    binary_cdd: int = Field(..., ge=0, le=1, description="Binary flag (0=noise, 1=significant)")
    threshold_used: float = Field(..., ge=1.0, le=4.0, description="Sigma threshold applied")
    window_days: int = Field(..., ge=30, le=730, description="Lookback window size")
    data_points: int = Field(..., gt=0, description="Available data points")
    insufficient_data: bool = Field(..., description="True if < 30 days history")
    block_height: int = Field(..., description="Block height at calculation")
    timestamp: str = Field(..., description="ISO timestamp of calculation")
```
