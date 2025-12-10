# Research: MVRV-Z Score + STH/LTH Variants

**Spec**: spec-020
**Date**: 2025-12-10

---

## Research Tasks

### R1: MVRV-Z Score Formula Validation

**Question**: Is the MVRV-Z formula in the spec correct?

**Research**:
The spec defines MVRV-Z as:
```
MVRV-Z = (Market Cap - Realized Cap) / StdDev(Market Cap)
```

This matches the standard definition used by:
- Glassnode (industry standard)
- CoinMetrics (academic research)
- Willy Woo (original MVRV popularizer)

**Decision**: Use spec formula exactly.

**Rationale**: The formula is mathematically sound and matches industry standards. The numerator (Market Cap - Realized Cap) is the unrealized profit/loss, normalized by market volatility.

**Alternatives considered**:
- Using StdDev(MVRV) instead of StdDev(Market Cap) - rejected because this would compound volatility measurement
- Using median instead of mean for "typical" market cap - rejected because standard deviation is based on mean

---

### R2: Optimal Window Size for Z-Score

**Question**: How many days of market cap history should be used?

**Research**:
- 30 days: Too short, catches only short-term volatility
- 90 days: Captures quarterly cycles
- **365 days**: Industry standard (Glassnode), captures full yearly cycle
- 730 days: Too slow to react to regime changes

**Decision**: 365 days (recommended), minimum 30 days (fallback)

**Rationale**: 365 days captures a full market cycle including seasonal effects. Return 0.0 if <30 days (insufficient statistical significance).

**Alternatives considered**:
- Adaptive window based on volatility regime - rejected (YAGNI)
- Multiple windows (30/90/365) - rejected (adds complexity without clear benefit)

---

### R3: STH/LTH Threshold Standard

**Question**: Why 155 days as the STH/LTH boundary?

**Research**:
The 155-day threshold is derived from:
- Glassnode's analysis showing behavioral shift at ~5 months
- Aligns with "hodler" behavior patterns (coins held >155 days rarely move)
- Roughly corresponds to 22,320 blocks (155 × 144)

Already implemented in spec-017 as `STH_THRESHOLD_DAYS = 155`.

**Decision**: Use existing 155-day threshold from spec-017.

**Rationale**: Consistency with existing implementation and industry standard.

**Alternatives considered**:
- Configurable threshold - already supported via `threshold_days` parameter
- Multiple thresholds (90/180/365) - rejected (spec-017 already has sub-cohorts)

---

### R4: Market Cap History Source

**Question**: Where to get 365 days of market cap history?

**Research**:
Options analyzed:
1. **Query `utxo_snapshots` table**: ✅ Exists, has `market_cap_usd` column
2. Calculate from `(supply × price)`: Requires external price history
3. External API: Violates privacy principles (Constitution V)

Current `utxo_snapshots` schema:
```sql
CREATE TABLE utxo_snapshots (
    block_height INTEGER PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    ...
    market_cap_usd DOUBLE NOT NULL,
    ...
);
```

**Decision**: Query `utxo_snapshots.market_cap_usd` for 365-day history.

**Rationale**: Uses existing table, no external dependencies, maintains privacy.

**Alternatives considered**:
- Bootstrap from external source - rejected (violates privacy principles)
- Generate synthetic history - rejected (inaccurate)

---

### R5: Fusion Weight Allocation

**Question**: How to integrate MVRV-Z into enhanced_fusion() without breaking existing weights?

**Research**:
Current `ENHANCED_WEIGHTS` (sum = 1.0):
```python
{
    "whale": 0.24,
    "utxo": 0.12,
    "funding": 0.05,
    "oi": 0.05,
    "power_law": 0.09,  # Target for reduction
    "symbolic": 0.12,
    "fractal": 0.09,
    "wasserstein": 0.08,
    "cointime": 0.14,
    "sopr": 0.02,
}
```

MVRV-Z is similar to power_law (valuation metric), so reduce power_law weight.

**Decision**: Reduce `power_law` from 0.09 to 0.06, add `mvrv_z` at 0.03.

**Rationale**:
- MVRV-Z and power_law both measure "fair value" deviation
- Small weight (0.03) appropriate for new, unvalidated metric
- Can increase after backtesting proves value

**Alternatives considered**:
- Equal reduction from all metrics - rejected (disrupts existing balance)
- Higher initial weight (0.05) - rejected (YAGNI until backtested)
- Separate from fusion - rejected (fusion is the integration point)

---

### R6: Missing Model Classes

**Question**: Why are UTXOLifecycle, UTXOSetSnapshot, etc. imported but not defined?

**Research**:
Spec-017 data-model.md defines these classes, but they're not in `metrics_models.py`.
The imports in tests use `TYPE_CHECKING` guards, causing import errors at runtime.

Current state:
- `scripts/metrics/utxo_lifecycle.py`: References models via TYPE_CHECKING
- `scripts/metrics/realized_metrics.py`: References models via TYPE_CHECKING
- `tests/test_realized_metrics.py`: Direct imports (will fail)

**Decision**: Add missing models to `scripts/models/metrics_models.py` as prerequisite.

**Rationale**: Tests cannot run without these models. Must be added before spec-020 implementation.

**Alternatives considered**:
- Create separate `utxo_models.py` - rejected (violates single module pattern)
- Use dicts instead of dataclasses - rejected (loses type safety)

---

## Resolved Clarifications

| Item | Resolution |
|------|------------|
| MVRV-Z formula | Matches industry standard |
| Window size | 365 days (30 day minimum) |
| STH/LTH threshold | 155 days (existing) |
| History source | `utxo_snapshots` table |
| Fusion weight | 0.03 from power_law reduction |
| Missing models | Add to metrics_models.py |

---

## Implementation Risks

| Risk | Mitigation |
|------|------------|
| Insufficient history | Return 0.0 with log warning |
| Zero std deviation | Return 0.0 (all values identical) |
| Missing models | Prerequisite task before main impl |

---

## Best Practices Identified

### For MVRV-Z Implementation

1. **Guard insufficient data**: Check `len(history) >= 30` before calculation
2. **Guard zero std**: Check `std != 0` before division
3. **Use statistics.stdev**: Standard library, proven, tested
4. **Cache history query**: Avoid repeated 365-day queries

### For Cohort Realized Cap

1. **Use existing index**: `idx_utxo_creation_block` for age filtering
2. **Block-based threshold**: Convert days to blocks (days × 144)
3. **Validate invariant**: STH + LTH ≈ Total (within floating point tolerance)

---

## References

- Glassnode Academy: MVRV-Z Score methodology
- CoinMetrics: State of the Network reports
- spec-017: UTXO Lifecycle Engine (existing implementation)
- spec-019: Funding Weight Adjustment (weight rebalancing precedent)
