# spec-027: Binary CDD Indicator

## Overview
Statistical significance flag when Coin Days Destroyed (CDD) exceeds N-sigma threshold.
Filters noise from raw CDD, highlights meaningful long-term holder activity events.

**Evidence Grade**: A (derivative of spec-021 CDD)
**Priority**: Quick Win (very low complexity, high signal value)

## Formula
```
CDD_zscore = (CDD_today - CDD_mean_365d) / CDD_std_365d
Binary_CDD = 1 if CDD_zscore >= threshold else 0
```

## Metrics
| Metric | Description |
|--------|-------------|
| `cdd_zscore` | Z-score of current CDD vs 365-day baseline |
| `binary_cdd` | Boolean flag (1 = significant event, 0 = noise) |
| `cdd_percentile` | Percentile rank of current CDD |
| `threshold_used` | Sigma threshold applied (default: 2.0) |

## Signal Interpretation
| Binary CDD | Z-Score | Interpretation |
|------------|---------|----------------|
| 0 | < 2σ | Normal LTH activity (noise) |
| 1 | >= 2σ | Significant LTH movement event |
| 1 | >= 3σ | Extreme event (rare, high conviction) |

## Implementation

### Data Source
- `utxo_lifecycle_full` table from spec-017/021 (UTXO lifecycle data)
- Historical CDD values for rolling statistics

### Files
- `scripts/metrics/binary_cdd.py` - Calculator
- `tests/test_binary_cdd.py` - TDD tests
- `scripts/models/metrics_models.py` - Add BinaryCDDResult dataclass

### API
- `GET /api/metrics/binary-cdd?threshold=2.0&window=365`

### Query (Illustrative)
```sql
-- Daily CDD aggregation from utxo_lifecycle_full
SELECT
    DATE(spent_timestamp) AS spend_date,
    SUM(COALESCE(age_days, 0) * btc_value) AS daily_cdd
FROM utxo_lifecycle_full
WHERE is_spent = TRUE
  AND spent_timestamp >= CURRENT_DATE - INTERVAL ? DAY
GROUP BY DATE(spent_timestamp)
ORDER BY spend_date
```

Z-score calculation performed in Python using numpy (see research.md Decision 2).

## Dependencies
- spec-021 (CDD/VDD module) - provides raw CDD data

## Effort: 1-2 hours (very low complexity)
## ROI: High - converts noisy CDD into actionable signal
