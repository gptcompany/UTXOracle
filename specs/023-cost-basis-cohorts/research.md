# Research: STH/LTH Cost Basis (spec-023)

**Date**: 2025-12-16
**Status**: Complete

## Research Summary

All technical unknowns resolved. Implementation approach validated against existing codebase patterns.

---

## 1. Cost Basis Formula Validation

### Decision
Use weighted average formula:
```
Cost Basis (cohort) = SUM(creation_price_usd × btc_value) / SUM(btc_value)
```

### Rationale
- Standard industry formula used by Glassnode, CheckOnChain, and CryptoQuant
- Direct mapping to existing `utxo_lifecycle_full` VIEW columns
- `realized_value_usd` column already stores `creation_price_usd × btc_value`, simplifying query

### Alternatives Considered
1. **Simple Average**: `AVG(creation_price_usd)` - Rejected: ignores UTXO value weighting
2. **Median Cost Basis**: More robust to outliers - Rejected: not standard metric, harder to compute efficiently in DuckDB

---

## 2. Cohort Boundary Definition

### Decision
Use 155-day threshold for STH/LTH boundary (industry standard).

### Rationale
- Consistent with existing `AgeCohortsConfig.sth_threshold_days = 155` in `metrics_models.py`
- Glassnode, CheckOnChain use same boundary
- Conversion: 155 days × 144 blocks/day = 22,320 blocks

### Alternatives Considered
1. **90-day boundary**: Used by some analysts - Rejected: inconsistent with existing cohort logic
2. **Configurable boundary**: Runtime parameter - Rejected: YAGNI, can add later if needed

---

## 3. Query Pattern for utxo_lifecycle_full VIEW

### Decision
Follow existing `calculate_cohort_realized_cap()` pattern from `realized_metrics.py`:

```sql
-- STH Cost Basis
SELECT SUM(realized_value_usd) / SUM(btc_value) AS sth_cost_basis
FROM utxo_lifecycle_full
WHERE is_spent = FALSE
  AND creation_block > (current_block - 22320)  -- 155 days
  AND creation_price_usd IS NOT NULL
  AND btc_value > 0

-- LTH Cost Basis
SELECT SUM(realized_value_usd) / SUM(btc_value) AS lth_cost_basis
FROM utxo_lifecycle_full
WHERE is_spent = FALSE
  AND creation_block <= (current_block - 22320)  -- 155 days
  AND creation_price_usd IS NOT NULL
  AND btc_value > 0
```

### Rationale
- Reuses existing cohort filtering logic
- `realized_value_usd = creation_price_usd × btc_value` already computed
- Single aggregate query per cohort (no complex JOINs)
- Filter `creation_price_usd IS NOT NULL` handles UTXOs with missing price data

### Alternatives Considered
1. **Combined query with CASE**: Single query for both cohorts - Acceptable alternative, similar performance
2. **Pre-aggregated table**: Store cost basis snapshots - Rejected: adds complexity, not needed for MVP

---

## 4. MVRV Calculation for Cohorts

### Decision
Compute cohort-specific MVRV as additional signal:
```python
sth_mvrv = current_price_usd / sth_cost_basis  # Price relative to STH cost
lth_mvrv = current_price_usd / lth_cost_basis  # Price relative to LTH cost
```

### Rationale
- Extends value of cost basis metric with actionable signal
- When `sth_mvrv < 1`: STH underwater (capitulation signal)
- When `lth_mvrv > 1`: LTH in profit (distribution risk signal)
- Complements existing `MVRVExtendedSignal` which uses realized cap (different calculation)

### Alternatives Considered
1. **Only return cost basis**: Simpler output - Rejected: MVRV adds minimal code, high value
2. **Use existing cohort MVRV**: From `MVRVExtendedSignal` - Rejected: different formula (uses cohort realized cap, not weighted average cost)

---

## 5. Dataclass Design

### Decision
Create `CostBasisResult` dataclass following existing patterns:

```python
@dataclass
class CostBasisResult:
    """Cost basis metrics for STH/LTH cohorts."""

    sth_cost_basis: float        # Weighted avg acquisition price for STH
    lth_cost_basis: float        # Weighted avg acquisition price for LTH
    total_cost_basis: float      # All UTXOs (realized price equivalent)

    sth_mvrv: float              # current_price / sth_cost_basis
    lth_mvrv: float              # current_price / lth_cost_basis

    sth_supply_btc: float        # BTC held by STH
    lth_supply_btc: float        # BTC held by LTH

    current_price_usd: float     # Price used for MVRV calculation
    block_height: int
    timestamp: datetime
    confidence: float = 0.85     # High confidence for Tier A metric
```

### Rationale
- Follows `NUPLResult`, `MVRVExtendedSignal` patterns
- Includes `to_dict()` for JSON serialization
- Field validation in `__post_init__`
- Stores context (price, block, timestamp) for API response

### Alternatives Considered
1. **Return dict**: No type safety - Rejected: inconsistent with codebase
2. **Pydantic model**: More validation - Rejected: existing code uses dataclasses

---

## 6. API Endpoint Design

### Decision
Add REST endpoint following existing pattern in `api/main.py`:

```
GET /api/metrics/cost-basis
```

Response:
```json
{
    "sth_cost_basis": 65432.10,
    "lth_cost_basis": 28500.00,
    "total_cost_basis": 42150.75,
    "sth_mvrv": 1.45,
    "lth_mvrv": 3.32,
    "sth_supply_btc": 2500000.0,
    "lth_supply_btc": 17000000.0,
    "current_price_usd": 95000.0,
    "block_height": 875000,
    "timestamp": "2025-12-16T10:00:00Z",
    "confidence": 0.85
}
```

### Rationale
- Consistent with existing `/api/metrics/*` endpoints
- Single endpoint returns complete cost basis view
- JSON response matches dataclass `to_dict()` output

### Alternatives Considered
1. **WebSocket streaming**: Real-time updates - Rejected: YAGNI, cost basis changes slowly
2. **Separate endpoints per cohort**: `/api/metrics/cost-basis/sth` - Rejected: unnecessary complexity

---

## 7. Error Handling

### Decision
Handle edge cases gracefully:

| Scenario | Handling |
|----------|----------|
| Zero BTC in cohort | Return `cost_basis = 0.0`, `mvrv = 0.0` |
| No UTXOs with price data | Return `confidence = 0.0` (insufficient data) |
| Division by zero (supply = 0) | Guard check, return neutral values |

### Rationale
- Follows existing patterns in `calculate_nupl_signal()` (see `nupl.py:106-118`)
- Never raise exceptions for edge cases in metrics calculations
- Use confidence field to indicate data quality

---

## 8. Test Strategy

### Decision
TDD approach with fixture-based testing:

1. **Unit tests** (`tests/test_cost_basis.py`):
   - `test_calculate_sth_cost_basis_basic`
   - `test_calculate_lth_cost_basis_basic`
   - `test_calculate_cost_basis_signal_full`
   - `test_cost_basis_mvrv_calculation`
   - `test_empty_cohort_handling`
   - `test_confidence_calculation`

2. **Integration test**: API endpoint response validation

### Rationale
- Follow existing test patterns in `tests/test_realized_metrics.py`
- Use DuckDB in-memory for fast tests
- Create sample UTXOs with known prices for deterministic validation

---

## Dependencies Summary

| Dependency | Version | Purpose |
|------------|---------|---------|
| DuckDB | existing | SQL query engine |
| FastAPI | existing | REST API framework |
| Pydantic | existing | Response validation |
| pytest | existing | Test framework |

**No new dependencies required.**

---

## Implementation Order

1. Add `CostBasisResult` dataclass to `metrics_models.py`
2. Create `scripts/metrics/cost_basis.py` with calculation functions
3. Add tests (`tests/test_cost_basis.py`)
4. Add API endpoint to `api/main.py`
5. Run full test suite

**Estimated Effort**: 2-3 hours (as specified in spec)
