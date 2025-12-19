# Research: Binary CDD Indicator

**Date**: 2025-12-18 | **Spec**: 027-binary-cdd

## Overview

Research findings for implementing Binary CDD - a statistical significance flag that transforms noisy CDD data into actionable binary signals.

## Decision 1: Data Source for Historical CDD

**Decision**: Query daily aggregated CDD from `utxo_lifecycle_full` table

**Rationale**:
- Spec-021's `cdd_vdd.py` already queries this table for CDD calculations
- Table contains `is_spent`, `spent_timestamp`, `age_days`, and `btc_value` fields
- Daily aggregation: `SUM(age_days * btc_value) GROUP BY DATE(spent_timestamp)`
- 365-day rolling window provides sufficient sample size for robust z-score

**Alternatives Considered**:
1. **Pre-aggregated cdd_metrics table**: Not implemented - would require new ETL
2. **Real-time calculation from raw UTXOs**: Too slow for 365-day lookback
3. **Separate time-series store**: Over-engineered for this use case

## Decision 2: Z-Score Calculation Method

**Decision**: Use numpy for rolling mean/std calculation on daily CDD values

**Rationale**:
- Formula: `z = (cdd_today - mean_365d) / std_365d`
- numpy provides vectorized operations for efficient statistics
- Already a dependency in the project (used by other metrics)
- Simple, well-tested implementation

**Alternatives Considered**:
1. **DuckDB window functions**: Possible but less readable, harder to test
2. **scipy.stats.zscore**: Overkill, adds unnecessary dependency
3. **Manual Python calculation**: Reinventing the wheel

## Decision 3: Threshold Configuration

**Decision**: Default threshold = 2.0 sigma, configurable via API parameter

**Rationale**:
- 2-sigma captures ~5% of extreme events (95th percentile)
- Configurable allows users to adjust sensitivity
- API parameter: `threshold=2.0` (default), range: 1.0-4.0

**Signal Interpretation**:
| Z-Score | Percentile | Binary CDD | Meaning |
|---------|------------|------------|---------|
| < 2σ | < 97.5% | 0 | Normal noise |
| >= 2σ | >= 97.5% | 1 | Significant event |
| >= 3σ | >= 99.9% | 1 | Extreme event |

## Decision 4: Handling Insufficient History

**Decision**: Return null z-score with `insufficient_data: true` flag when < 30 days history

**Rationale**:
- Z-score is meaningless without sufficient baseline data
- 30 days minimum provides basic statistical validity
- Clear flag allows frontend to display appropriate message
- Graceful degradation without errors

## Decision 5: API Endpoint Design

**Decision**: `GET /api/metrics/binary-cdd?threshold=2.0&window=365`

**Rationale**:
- Follows existing `/api/metrics/*` patterns (see cdd-vdd, nupl, etc.)
- Query parameters for configurable threshold and lookback window
- Returns both raw z-score and binary flag for flexibility

**Response Fields**:
```json
{
  "cdd_today": 12500.5,
  "cdd_mean_365d": 8234.2,
  "cdd_std_365d": 2156.7,
  "cdd_zscore": 1.98,
  "cdd_percentile": 97.3,
  "binary_cdd": 0,
  "threshold_used": 2.0,
  "window_days": 365,
  "data_points": 365,
  "insufficient_data": false,
  "block_height": 875000,
  "timestamp": "2025-12-18T10:30:00Z"
}
```

## Decision 6: Calculator Module Design

**Decision**: New `scripts/metrics/binary_cdd.py` with single `calculate_binary_cdd()` function

**Rationale**:
- Follows existing pattern (cdd_vdd.py, nupl.py, etc.)
- Single responsibility: one module, one metric
- Takes DuckDB connection, returns dataclass result
- Easy to test in isolation

**Function Signature**:
```python
def calculate_binary_cdd(
    conn: duckdb.DuckDBPyConnection,
    block_height: int,
    threshold: float = 2.0,
    window_days: int = 365,
) -> BinaryCDDResult:
```

## Implementation Notes

### Query Strategy

```sql
-- Step 1: Get daily CDD values for window
WITH daily_cdd AS (
    SELECT
        DATE(spent_timestamp) AS date,
        SUM(COALESCE(age_days, 0) * btc_value) AS cdd
    FROM utxo_lifecycle_full
    WHERE is_spent = TRUE
      AND spent_timestamp >= NOW() - INTERVAL ? DAY
    GROUP BY DATE(spent_timestamp)
    ORDER BY date
)
SELECT * FROM daily_cdd;
```

```python
# Step 2: Calculate statistics in Python
import numpy as np

daily_values = [row['cdd'] for row in daily_cdd]
today_cdd = daily_values[-1]  # Most recent
mean_cdd = np.mean(daily_values)
std_cdd = np.std(daily_values, ddof=1)  # Sample std (N-1)
zscore = (today_cdd - mean_cdd) / std_cdd if std_cdd > 0 else 0.0
binary = 1 if zscore >= threshold else 0
```

### Edge Cases

1. **Zero standard deviation**: If all daily CDD values identical, z-score = 0
2. **Missing days**: Use only available data points (some days may have no spends)
3. **Very low CDD**: Still calculate z-score, low baseline is meaningful
4. **Negative z-score**: Valid - indicates unusually low CDD (accumulation)

## References

- [Glassnode: Binary CDD](https://academy.glassnode.com/indicators/coin-days-destroyed/binary-cdd) - Industry standard
- spec-021: CDD/VDD implementation in this codebase
- `scripts/metrics/cdd_vdd.py` - Existing CDD calculation patterns
