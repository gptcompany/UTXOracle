# Implementation Plan: MVRV-Z Score + STH/LTH Variants

**Branch**: `020-mvrv-implementation` | **Date**: 2025-12-10 | **Spec**: [spec-020](spec.md)
**Input**: Feature specification from `/specs/020-mvrv-implementation/spec.md`

## Summary

Extend existing MVRV implementation with Z-score normalization and cohort-specific variants (STH-MVRV, LTH-MVRV). These additions enable cross-cycle comparison and cohort-level profit/loss analysis. Implementation extends `realized_metrics.py` with 3 new functions and integrates with `enhanced_fusion()` via a new `mvrv_z` signal component.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: DuckDB (existing), statistics (stdlib)
**Storage**: DuckDB `utxo_lifecycle` table (existing), `utxo_snapshots` table (existing)
**Testing**: pytest with existing fixtures from `test_realized_metrics.py`
**Target Platform**: Linux server
**Project Type**: Single Python package
**Performance Goals**: <5 seconds for cohort realized cap calculation
**Constraints**: <100ms for Z-score calculation
**Scale/Scope**: 365 days of market cap history for Z-score calculation

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. KISS/YAGNI | ✅ PASS | Extends existing module, no new files needed |
| II. TDD | ✅ PASS | Tests exist in `test_realized_metrics.py`, will add new tests |
| III. UX Consistency | ✅ PASS | No CLI/API changes, internal functions only |
| IV. Performance | ✅ PASS | SQL queries use existing indexes |
| V. Data Privacy | ✅ PASS | All data processed locally from blockchain |

**Pre-Design Gate**: PASS - All principles satisfied.

## Project Structure

### Documentation (this feature)

```
specs/020-mvrv-implementation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # N/A - no API changes
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```
scripts/
├── metrics/
│   ├── realized_metrics.py     # ADD: calculate_mvrv_z, calculate_cohort_realized_cap
│   └── monte_carlo_fusion.py   # MODIFY: add mvrv_z_vote to enhanced_fusion()
└── models/
    └── metrics_models.py       # ADD: MVRVExtendedSignal dataclass

tests/
└── test_realized_metrics.py    # ADD: TestMVRVZScore, TestCohortMVRV classes
```

**Structure Decision**: Single project structure. Extends existing `realized_metrics.py` module with 3 new functions. No new files created.

## Complexity Tracking

*No violations. Implementation extends existing patterns without new complexity.*

| Aspect | Complexity | Justification |
|--------|------------|---------------|
| New functions | 3 | Minimum needed: Z-score, cohort realized cap, cohort MVRV |
| Data model | 1 dataclass | MVRVExtendedSignal consolidates all MVRV variants |
| Fusion weight | Rebalance | Reduce power_law 0.09→0.06, add mvrv_z 0.03 |

---

## Dependencies Analysis

| Dependency | Status | Action |
|------------|--------|--------|
| `realized_metrics.py` | ✅ Has `calculate_mvrv()` | Base to extend |
| `utxo_lifecycle` table | ✅ Has `creation_price_usd` | Query for cohort data |
| Market cap history | ⚠️ Need 365 days | Use `utxo_snapshots.market_cap_usd` |
| `UTXOSetSnapshot` | ⚠️ Missing model | **PREREQUISITE**: Add to metrics_models.py |

### Critical Prerequisite

The `UTXOLifecycle`, `UTXOSetSnapshot`, `AgeCohortsConfig`, and `SyncState` dataclasses are **specified but not implemented** in `scripts/models/metrics_models.py`. These must be added before this spec can proceed.

**Action**: Add missing models from spec-017/data-model.md to `scripts/models/metrics_models.py`.

---

## Implementation Approach

### Phase 1: Add Missing Models (Prerequisite)

Add to `scripts/models/metrics_models.py`:
- `UTXOLifecycle` dataclass
- `UTXOSetSnapshot` dataclass
- `AgeCohortsConfig` dataclass
- `SyncState` dataclass

### Phase 2: MVRV-Z Score Implementation

```python
def calculate_mvrv_z(
    market_cap: float,
    realized_cap: float,
    market_cap_history: list[float],  # 365 days recommended
) -> float:
```

- Use `statistics.stdev()` for std calculation
- Return 0.0 for insufficient data (<30 days)
- Guard against zero std

### Phase 3: Cohort Realized Cap

```python
def calculate_cohort_realized_cap(
    conn: duckdb.DuckDBPyConnection,
    current_block: int,
    cohort: Literal["STH", "LTH"],
    threshold_days: int = 155,
) -> float:
```

- Query `utxo_lifecycle` with age filter
- STH: `creation_block > cutoff_block`
- LTH: `creation_block <= cutoff_block`
- Use existing index `idx_utxo_creation_block`

### Phase 4: Fusion Integration

Modify `ENHANCED_WEIGHTS` in `monte_carlo_fusion.py`:
- Reduce `power_law`: 0.09 → 0.06
- Add `mvrv_z`: 0.03
- Weights still sum to 1.0

Add `mvrv_z_vote` and `mvrv_z_conf` parameters to `enhanced_fusion()`.

---

## Signal Interpretation (from spec)

### MVRV-Z Score Zones

| MVRV-Z | Zone | Action |
|--------|------|--------|
| > 7 | Extreme | Strong sell signal |
| 3 - 7 | Caution | Reduce exposure |
| -0.5 - 3 | Normal | Hold |
| < -0.5 | Accumulation | Strong buy signal |

### STH-MVRV

| Value | Interpretation |
|-------|----------------|
| > 1.2 | New buyers in profit → distribution risk |
| 1.0 | Break-even |
| < 0.8 | New buyers underwater → capitulation |

### LTH-MVRV

| Value | Interpretation |
|-------|----------------|
| > 3.5 | LTH in massive profit → cycle top risk |
| 1.5 - 3.5 | Healthy profit |
| < 1.0 | LTH underwater → generational bottom |

---

## Validation Criteria

1. `calculate_mvrv_z()` returns valid Z-score with 365-day history
2. `calculate_cohort_realized_cap()` works for both STH and LTH
3. STH + LTH realized cap ≈ Total realized cap (validation invariant)
4. Signal classification zones implemented correctly
5. Fusion integration working with weights summing to 1.0
6. All existing tests pass
7. New tests achieve >80% coverage for new functions

---

## Post-Design Constitution Re-check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. KISS/YAGNI | ✅ PASS | No over-engineering, minimal new code |
| II. TDD | ✅ PASS | RED phase tests first |
| III. UX Consistency | ✅ PASS | Internal functions only |
| IV. Performance | ✅ PASS | Uses existing indexes |
| V. Data Privacy | ✅ PASS | Local blockchain data only |

**Post-Design Gate**: PASS - Ready for task generation.
