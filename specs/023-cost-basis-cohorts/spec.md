# spec-023: STH/LTH Cost Basis

## Overview
Weighted average cost basis per holder cohort - key support/resistance levels.

## Formula
```
Cost Basis (cohort) = SUM(creation_price_usd × btc_value) / SUM(btc_value)
                    WHERE cohort = 'STH' or 'LTH'
```

## Metrics
| Metric | Description |
|--------|-------------|
| `sth_cost_basis` | Average acquisition price for STH (<155 days) |
| `lth_cost_basis` | Average acquisition price for LTH (>=155 days) |
| `total_cost_basis` | Overall realized price (all UTXOs) |
| `sth_mvrv` | Price / STH Cost Basis |
| `lth_mvrv` | Price / LTH Cost Basis |

## Signal Logic
- Price < STH Cost Basis → STH underwater → Capitulation risk
- Price > LTH Cost Basis → LTH in profit → Distribution risk
- STH Cost Basis = key support level
- LTH Cost Basis = macro support level

## Implementation

### Data Source
- `utxo_lifecycle_full` VIEW (creation_price_usd, btc_value, cohort)

### Query
```sql
SELECT
    cohort,
    SUM(creation_price_usd * btc_value) / SUM(btc_value) AS cost_basis,
    SUM(btc_value) AS total_btc
FROM utxo_lifecycle_full
WHERE is_spent = FALSE AND creation_price_usd IS NOT NULL
GROUP BY cohort
```

### Files
- `scripts/metrics/cost_basis.py` - Calculator
- `tests/test_cost_basis.py` - TDD tests
- `scripts/models/metrics_models.py` - Add CostBasisResult dataclass

### API
- `GET /api/metrics/cost-basis` - Returns STH/LTH cost basis with MVRV

## Effort: 2-3 hours
## Evidence Grade: A (CheckOnChain core metric)
## ROI: Very High - identifies key support/resistance
