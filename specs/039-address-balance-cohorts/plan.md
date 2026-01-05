# Implementation Plan: Address Balance Cohorts Analysis

**Spec**: [spec.md](./spec.md) | **Date**: 2025-01-05

## Summary

Implement address balance-based cohort analysis (whale/mid-tier/retail) with
cost basis, MVRV, and cross-cohort signals. Extends spec-023's cost basis
pattern with balance segmentation inspired by spec-025's wallet bands.

**Technical Approach**: Two-stage SQL aggregation on `utxo_lifecycle_full` VIEW:
1. Group UTXOs by address to calculate per-address balance
2. Classify addresses into cohorts and aggregate cost basis

## Files to Create/Modify

### New Files

```
scripts/metrics/address_cohorts.py       # Core calculation module
tests/test_address_cohorts.py            # TDD tests
```

### Modified Files

```
scripts/models/metrics_models.py         # Add CohortMetrics, AddressCohortsResult
api/main.py                              # Add /api/metrics/address-cohorts endpoint
docs/ARCHITECTURE.md                     # Document new metric
```

## Algorithm Design

### Two-Stage Aggregation

**Stage 1: Address Balance Calculation**
```sql
SELECT address, SUM(btc_value) AS balance, ...
FROM utxo_lifecycle_full
WHERE is_spent = FALSE AND address IS NOT NULL
GROUP BY address
```

**Stage 2: Cohort Classification & Aggregation**
```sql
SELECT
    CASE WHEN balance < 1 THEN 'retail'
         WHEN balance < 100 THEN 'mid_tier'
         ELSE 'whale'
    END AS cohort,
    SUM(cost_numerator) / SUM(cost_denominator) AS cost_basis,
    ...
FROM stage1
GROUP BY cohort
```

### Cost Basis Formula

Same methodology as spec-023:
```
Cost Basis = SUM(creation_price_usd × btc_value) / SUM(btc_value)
```

### MVRV Calculation

```python
mvrv = current_price_usd / cost_basis if cost_basis > 0 else 0.0
```

### Cross-Cohort Signals

```python
whale_retail_spread = whale.cost_basis - retail.cost_basis
whale_retail_mvrv_ratio = whale.mvrv / retail.mvrv if retail.mvrv > 0 else 0.0
```

## Performance Optimization

1. **Index Usage**: Leverage existing `idx_utxo_is_spent` index
2. **Batch Processing**: Single query with CTEs (Common Table Expressions)
3. **Caching**: Cache results for 1 hour
4. **Null Handling**: Track UTXOs without address separately

## TDD Workflow

1. Write tests first in `tests/test_address_cohorts.py`
2. Run tests - verify they fail (RED)
3. Implement in `scripts/metrics/address_cohorts.py`
4. Run tests - verify they pass (GREEN)
5. Refactor if needed

## Critical Files Reference

- `scripts/metrics/cost_basis.py` - Pattern for weighted cost basis calculation
- `scripts/metrics/wallet_waves.py` - Address grouping pattern
- `tests/test_cost_basis.py` - Test structure template

## Estimated Effort

| Phase | Task | Hours |
|-------|------|-------|
| 1 | Write tests | 1-2h |
| 2 | Implement calculator | 2-3h |
| 3 | API endpoint | 1h |
| 4 | Documentation | 0.5h |
| **Total** | | **5-7h** |
