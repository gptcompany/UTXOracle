# Tasks: Advanced On-Chain Analytics

**Feature**: 009-advanced-onchain-analytics
**Branch**: `009-advanced-onchain-analytics`
**Generated**: 2025-12-04
**Total Tasks**: 45
**Estimated LOC**: ~640 (including tests)

## User Story Summary

| Story | Priority | Description | Tasks | LOC |
|-------|----------|-------------|-------|-----|
| US1 | P1 | Power Law Regime Detection | 9 | ~120 |
| US2 | P1 | Symbolic Dynamics Pattern Detection | 9 | ~100 |
| US3 | P2 | Fractal Dimension Analysis | 9 | ~80 |
| US4 | P1 | Enhanced Monte Carlo Fusion | 8 | ~60 |
| - | - | Setup & Foundational | 6 | - |
| - | - | Polish & Integration | 4 | ~80 |

## Implementation Order (KISS)

Per spec recommendation, implement in order:
1. **US2: Symbolic Dynamics** (easiest, highest ROI +25%)
2. **US1: Power Law** (well-documented MLE)
3. **US3: Fractal Dimension** (straightforward box-counting)
4. **US4: Enhanced Fusion** (integration point)

---

## Phase 1: Setup

**Goal**: Verify prerequisites and prepare project structure.

- [x] T001 Verify spec-007 Monte Carlo fusion exists at `scripts/metrics/monte_carlo_fusion.py`
- [x] T002 [P] Verify DuckDB metrics table exists (run `scripts/init_metrics_db.py` if needed)
- [x] T003 [P] Create test file skeleton at `tests/test_advanced_metrics.py`
- [x] T004 [P] Add new dataclasses to `scripts/models/metrics_models.py` (PowerLawResult, SymbolicDynamicsResult, FractalDimensionResult)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before user story implementation.

- [x] T005 Copy canonical dataclass definitions from `specs/009-advanced-onchain-analytics/contracts/advanced_metrics_api.py` to `scripts/models/metrics_models.py`
- [x] T006 Verify existing `scripts/metrics/__init__.py` structure and add placeholder exports for new modules

**Checkpoint**: Foundation ready - user story implementation can begin

---

## Phase 3: User Story 2 - Symbolic Dynamics Pattern Detection (Priority: P1) - FIRST

**Goal**: Measure temporal complexity of UTXO flow patterns via permutation entropy.

**Independent Test**: Run `python -c "from scripts.metrics.symbolic_dynamics import analyze; print(analyze([1,2,3,4,5,6,7,8,9,10]))"` and verify `pattern_type="ACCUMULATION_TREND"` with H ≈ 0.

### Tests for User Story 2 (TDD RED)

- [x] T007 [P] [US2] Write test `test_permutation_entropy_monotonic()` - expects H ≈ 0.0 in `tests/test_advanced_metrics.py`
- [x] T008 [P] [US2] Write test `test_permutation_entropy_random()` - expects H ≈ 1.0 in `tests/test_advanced_metrics.py`
- [x] T009 [P] [US2] Write test `test_symbolic_dynamics_classification()` - verify pattern_type and vote in `tests/test_advanced_metrics.py`

### Implementation for User Story 2 (TDD GREEN)

- [x] T010 [US2] Create `scripts/metrics/symbolic_dynamics.py` with SymbolicDynamicsResult import
- [x] T011 [US2] Implement `permutation_entropy(series, order, delay)` function (~40 LOC)
- [x] T012 [US2] Implement `statistical_complexity(pattern_distribution)` function (~20 LOC)
- [x] T013 [US2] Implement `analyze(series, order)` main function with classification logic (~40 LOC)
- [x] T014 [US2] Verify all US2 tests pass with `uv run pytest tests/test_advanced_metrics.py -k symbolic -v`
- [x] T015 [US2] Add module export to `scripts/metrics/__init__.py`

**Checkpoint US2**: `from scripts.metrics.symbolic_dynamics import analyze` works and tests pass

---

## Phase 4: User Story 1 - Power Law Regime Detection (Priority: P1)

**Goal**: Detect when UTXO distributions deviate from typical power law behavior.

**Independent Test**: Run with synthetic data with known τ=2.0 and verify estimate within ±0.1.

### Tests for User Story 1 (TDD RED)

- [x] T016 [P] [US1] Write test `test_power_law_mle_estimation()` - verify τ ≈ 2.0 for synthetic data in `tests/test_advanced_metrics.py`
- [x] T017 [P] [US1] Write test `test_power_law_ks_validation()` - verify is_valid for good fit in `tests/test_advanced_metrics.py`
- [x] T018 [P] [US1] Write test `test_power_law_regime_classification()` - verify ACCUMULATION/NEUTRAL/DISTRIBUTION in `tests/test_advanced_metrics.py`

### Implementation for User Story 1 (TDD GREEN)

- [x] T019 [US1] Create `scripts/metrics/power_law.py` with PowerLawResult import
- [x] T020 [US1] Implement `mle_estimate(values, xmin)` function - τ = 1 + n / Σ ln(x_i/x_min) (~30 LOC)
- [x] T021 [US1] Implement `ks_test(values, tau, xmin)` function - KS statistic and p-value (~40 LOC)
- [x] T022 [US1] Implement `fit(values, xmin)` main function with regime classification (~50 LOC)
- [x] T023 [US1] Verify all US1 tests pass with `uv run pytest tests/test_advanced_metrics.py -k power_law -v`
- [x] T024 [US1] Add module export to `scripts/metrics/__init__.py`

**Checkpoint US1**: `from scripts.metrics.power_law import fit` works and tests pass

---

## Phase 5: User Story 3 - Fractal Dimension Analysis (Priority: P2)

**Goal**: Measure fractal dimension of UTXO value distributions via box-counting.

**Independent Test**: Run with uniform distribution and verify D ≈ 1.0.

### Tests for User Story 3 (TDD RED)

- [x] T025 [P] [US3] Write test `test_fractal_dimension_uniform()` - expects D ≈ 1.0 in `tests/test_advanced_metrics.py`
- [x] T026 [P] [US3] Write test `test_fractal_dimension_clustered()` - expects D < 0.8 in `tests/test_advanced_metrics.py`
- [x] T027 [P] [US3] Write test `test_fractal_structure_classification()` - verify WHALE_DOMINATED/MIXED/RETAIL in `tests/test_advanced_metrics.py`

### Implementation for User Story 3 (TDD GREEN)

- [x] T028 [US3] Create `scripts/metrics/fractal_dimension.py` with FractalDimensionResult import
- [x] T029 [US3] Implement `box_count(values, epsilon)` function (~20 LOC)
- [x] T030 [US3] Implement `linear_regression(x, y)` helper for log-log fit (~15 LOC)
- [x] T031 [US3] Implement `analyze(values, min_scales)` main function with structure classification (~45 LOC)
- [x] T032 [US3] Verify all US3 tests pass with `uv run pytest tests/test_advanced_metrics.py -k fractal -v`
- [x] T033 [US3] Add module export to `scripts/metrics/__init__.py`

**Checkpoint US3**: `from scripts.metrics.fractal_dimension import analyze` works and tests pass

---

## Phase 6: User Story 4 - Enhanced Monte Carlo Fusion (Priority: P1)

**Goal**: Extend Monte Carlo fusion to support all 7 signal components.

**Independent Test**: Provide all 7 components and verify weighted fusion output.

### Tests for User Story 4 (TDD RED)

- [x] T034 [P] [US4] Write test `test_enhanced_fusion_all_components()` in `tests/test_advanced_metrics.py`
- [x] T035 [P] [US4] Write test `test_enhanced_fusion_missing_components()` - verify weight renormalization in `tests/test_advanced_metrics.py`
- [x] T036 [P] [US4] Write test `test_enhanced_fusion_backward_compatible()` - verify spec-007 behavior preserved in `tests/test_advanced_metrics.py`

### Implementation for User Story 4 (TDD GREEN)

- [x] T037 [US4] Add EnhancedFusionResult to `scripts/models/metrics_models.py`
- [x] T038 [US4] Modify `scripts/metrics/monte_carlo_fusion.py` to add `enhanced_fusion()` function (~60 LOC)
- [x] T039 [US4] Implement weight renormalization when components are None
- [x] T040 [US4] Verify all US4 tests pass with `uv run pytest tests/test_advanced_metrics.py -k fusion -v`
- [x] T041 [US4] Update module exports in `scripts/metrics/__init__.py`

**Checkpoint US4**: Enhanced fusion works with all 7 components and gracefully handles missing ones

---

## Phase 7: Polish & Cross-Cutting Concerns

**Goal**: Integration, API endpoint, documentation, and validation.

- [x] T042 Integrate advanced metrics into `scripts/daily_analysis.py` (call after existing metrics)
- [x] T043 Add `/api/metrics/advanced` endpoint to `api/main.py` using AdvancedMetricsResponse model
- [x] T044 [P] Run full test suite: `uv run pytest tests/test_advanced_metrics.py -v --cov=scripts/metrics`
- [x] T045 [P] Update CLAUDE.md with spec-009 documentation (add to On-Chain Metrics Module section)

**Final Checkpoint**: All tests pass, coverage ≥85%, API endpoint returns valid response

---

## Dependencies & Execution Order

### Critical Path (Sequential)

```
Phase 1 (Setup)
    │
    ▼
Phase 2 (Foundational)
    │
    ├──────────────────┬──────────────────┬──────────────────┐
    ▼                  ▼                  ▼                  ▼
Phase 3 (US2)     Phase 4 (US1)     Phase 5 (US3)     [Can parallelize]
Symbolic          Power Law          Fractal
[FIRST - easiest] [Second]          [Third]
    │                  │                  │
    └──────────────────┴──────────────────┘
                       │
                       ▼
              Phase 6 (US4)
              Enhanced Fusion
              [Depends on US1-3]
                       │
                       ▼
              Phase 7 (Polish)
```

### User Story Dependencies

- **US2 (Symbolic)**: Independent - can start after Phase 2
- **US1 (Power Law)**: Independent - can start after Phase 2
- **US3 (Fractal)**: Independent - can start after Phase 2
- **US4 (Enhanced Fusion)**: Depends on US1, US2, US3 completion

### Parallel Opportunities

**Within Phase 1** (all parallel):
```
T001, T002, T003, T004 [P]
```

**Within Each User Story Tests** (parallel):
```
US2: T007, T008, T009 [P]
US1: T016, T017, T018 [P]
US3: T025, T026, T027 [P]
US4: T034, T035, T036 [P]
```

**Cross-Story Parallelism** (after Phase 2):
```
US2, US1, US3 can run in parallel if multiple developers
```

---

## MVP Scope

**Recommended MVP**: Complete through Phase 4 (US2 + US1)

- Symbolic Dynamics implemented (+25% accuracy)
- Power Law implemented (+5% accuracy)
- Tests passing
- Total: ~220 LOC, ~30 tasks

**Defer to V1.1**:
- Fractal Dimension (Phase 5)
- Enhanced Fusion (Phase 6)
- Full Integration (Phase 7)

---

## File Checklist

After all tasks complete, verify:

```
✅ scripts/metrics/symbolic_dynamics.py (NEW)
✅ scripts/metrics/power_law.py (NEW)
✅ scripts/metrics/fractal_dimension.py (NEW)
✅ scripts/metrics/monte_carlo_fusion.py (MODIFIED - enhanced_fusion())
✅ scripts/metrics/__init__.py (MODIFIED - exports)
✅ scripts/models/metrics_models.py (MODIFIED - 4 new dataclasses)
✅ scripts/daily_analysis.py (MODIFIED - advanced metrics integration)
✅ api/main.py (MODIFIED - /api/metrics/advanced endpoint)
✅ tests/test_advanced_metrics.py (NEW)
✅ CLAUDE.md (MODIFIED - spec-009 docs)
```

---

## Validation Commands

```bash
# Run all advanced metrics tests
uv run pytest tests/test_advanced_metrics.py -v

# Check coverage
uv run pytest tests/test_advanced_metrics.py --cov=scripts/metrics --cov-report=term-missing

# Test individual modules
python -c "
from scripts.metrics.symbolic_dynamics import analyze as sym_analyze
from scripts.metrics.power_law import fit as pl_fit
from scripts.metrics.fractal_dimension import analyze as frac_analyze

# Symbolic test
result = sym_analyze([1,2,3,4,5,6,7,8,9,10])
print(f'Symbolic: H={result.permutation_entropy:.3f}, pattern={result.pattern_type}')

# Power law test (generate synthetic power law data)
import random
data = [random.paretovariate(2.0) for _ in range(500)]
result = pl_fit(data)
print(f'Power Law: tau={result.tau:.2f}, regime={result.regime}')

# Fractal test
data = [random.random() for _ in range(500)]
result = frac_analyze(data)
print(f'Fractal: D={result.dimension:.2f}, structure={result.structure}')
"

# Test API endpoint (after integration)
curl http://localhost:8001/api/metrics/advanced | jq

# Performance benchmark
python -c "
import time
import random
from scripts.metrics.symbolic_dynamics import analyze as sym
from scripts.metrics.power_law import fit as pl
from scripts.metrics.fractal_dimension import analyze as frac

data = [random.random() * 1000 for _ in range(1000)]
start = time.time()
for _ in range(100):
    sym(data)
    pl(data)
    frac(data)
elapsed = (time.time() - start) / 100 * 1000
print(f'Average time: {elapsed:.1f}ms (target: <100ms)')
"
```

---

**Document Status**: Ready for implementation
**Next Step**: Run `/speckit.implement` or implement tasks manually with TDD
**Estimated Timeline**: MVP (US2 + US1) in ~2 hours; Full spec in ~4 hours

**Generated by**: SpecKit `/speckit.tasks` command
**Date**: 2025-12-04
**Feature**: Advanced On-Chain Analytics (spec-009)
