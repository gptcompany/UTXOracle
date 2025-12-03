# Tasks: On-Chain Metrics Core

**Feature**: 007-onchain-metrics-core
**Branch**: `007-onchain-metrics-core`
**Generated**: 2025-12-03
**Total Tasks**: 36 ✅ (all complete)
**Estimated LOC**: ~330
**Coverage**: 87%

## User Story Summary

| Story | Priority | Description | Tasks | LOC |
|-------|----------|-------------|-------|-----|
| US1 | P1 | Monte Carlo Signal Fusion | 8 | ~150 |
| US2 | P1 | Active Addresses Metric | 6 | ~100 |
| US3 | P1 | TX Volume USD | 6 | ~80 |
| - | - | Setup & Integration | 12 | - |

## Implementation Order (KISS)

Per spec recommendation, implement in order of complexity:
1. **US3: TX Volume USD** (easiest) → validates integration pattern
2. **US2: Active Addresses** → builds on tx iteration
3. **US1: Monte Carlo Fusion** (most complex) → last

---

## Phase 1: Setup

**Goal**: Create project structure and shared infrastructure.

- [x] T001 Create metrics module directory at `scripts/metrics/__init__.py`
- [x] T002 Create data models file at `scripts/models/metrics_models.py` (copy from data-model.md)
- [x] T003 Create DuckDB migration script at `scripts/init_metrics_db.py`
- [x] T004 Run DuckDB migration to create `metrics` table
- [x] T005 Create test file at `tests/test_onchain_metrics.py` with imports and fixtures

---

## Phase 2: Foundational

**Goal**: Establish shared patterns before user story implementation.

- [x] T006 Add Pydantic API models to `api/models/` (copy from contracts/metrics_api.py)
- [x] T007 Add `save_metrics_to_db()` helper function in `scripts/metrics/__init__.py`
- [x] T008 Add `load_metrics_from_db()` helper function in `scripts/metrics/__init__.py`

---

## Phase 3: User Story 3 - TX Volume USD (P1) [FIRST - Easiest]

**Goal**: Calculate total transaction volume in USD using UTXOracle on-chain price.

**Independent Test Criteria**:
- Given 1000 transactions with total output of 5000 BTC and UTXOracle price $100,000
- When TX Volume USD is calculated
- Then result is $500,000,000 (±0.01% tolerance)

### Tests (TDD RED)

- [x] T009 [US3] Write test `test_tx_volume_basic_calculation()` in `tests/test_onchain_metrics.py`
- [x] T010 [US3] Write test `test_tx_volume_low_confidence_flag()` in `tests/test_onchain_metrics.py`
- [x] T011 [US3] Write test `test_tx_volume_change_output_heuristic()` in `tests/test_onchain_metrics.py`

### Implementation (TDD GREEN)

- [x] T012 [US3] Implement `estimate_real_volume(tx)` in `scripts/metrics/tx_volume.py`
- [x] T013 [US3] Implement `calculate_tx_volume(transactions, utxoracle_price, confidence)` in `scripts/metrics/tx_volume.py`
- [x] T014 [US3] Verify all US3 tests pass with `uv run pytest tests/test_onchain_metrics.py -k tx_volume -v`

---

## Phase 4: User Story 2 - Active Addresses (P1)

**Goal**: Count unique addresses per block/day from transaction inputs and outputs.

**Independent Test Criteria**:
- Given block 870000 with known transaction data
- When active addresses are calculated
- Then count matches block explorer (±10% tolerance)

### Tests (TDD RED)

- [x] T015 [US2] Write test `test_active_addresses_single_block()` in `tests/test_onchain_metrics.py`
- [x] T016 [US2] Write test `test_active_addresses_deduplication()` in `tests/test_onchain_metrics.py`
- [x] T017 [US2] Write test `test_active_addresses_anomaly_detection()` in `tests/test_onchain_metrics.py`

### Implementation (TDD GREEN)

- [x] T018 [US2] Implement `count_active_addresses(transactions)` in `scripts/metrics/active_addresses.py`
- [x] T019 [US2] Implement `detect_anomaly(current_count, historical_counts)` in `scripts/metrics/active_addresses.py`
- [x] T020 [US2] Verify all US2 tests pass with `uv run pytest tests/test_onchain_metrics.py -k active_address -v`

---

## Phase 5: User Story 1 - Monte Carlo Signal Fusion (P1) [Most Complex]

**Goal**: Upgrade linear fusion to bootstrap sampling with 95% confidence intervals.

**Independent Test Criteria**:
- Given whale signal ACCUMULATION (confidence 0.8) and UTXOracle confidence 0.85
- When Monte Carlo fusion runs with 1000 bootstrap samples
- Then output includes signal_mean, signal_std, and 95% CI

### Tests (TDD RED)

- [x] T021 [US1] Write test `test_monte_carlo_basic_fusion()` in `tests/test_onchain_metrics.py`
- [x] T022 [US1] Write test `test_monte_carlo_confidence_intervals()` in `tests/test_onchain_metrics.py`
- [x] T023 [US1] Write test `test_monte_carlo_bimodal_detection()` in `tests/test_onchain_metrics.py`
- [x] T024 [US1] Write test `test_monte_carlo_performance_under_100ms()` in `tests/test_onchain_metrics.py`

### Implementation (TDD GREEN)

- [x] T025 [US1] Implement `monte_carlo_fusion(whale_vote, whale_conf, utxo_vote, utxo_conf, n_samples)` in `scripts/metrics/monte_carlo_fusion.py`
- [x] T026 [US1] Implement `detect_bimodal(samples)` in `scripts/metrics/monte_carlo_fusion.py`
- [x] T027 [US1] Implement `determine_action(signal_mean, ci_lower, ci_upper)` in `scripts/metrics/monte_carlo_fusion.py`
- [x] T028 [US1] Verify all US1 tests pass with `uv run pytest tests/test_onchain_metrics.py -k monte_carlo -v`

---

## Phase 6: Integration

**Goal**: Integrate all metrics into daily_analysis.py and expose via API.

- [x] T029 Integrate metrics calculation into `scripts/daily_analysis.py` main() flow
- [x] T030 Add `/api/metrics/latest` endpoint in `api/main.py`
- [x] T031 Create integration test at `tests/integration/test_metrics_integration.py`
- [x] T032 Verify full test suite passes with `uv run pytest tests/ -v --cov=scripts/metrics`

---

## Phase 7: Polish & Cross-Cutting

**Goal**: Documentation, performance validation, and cleanup.

- [x] T033 Validate Monte Carlo performance <100ms with benchmark script (2.8ms)
- [x] T034 Validate TX Volume adds <50ms overhead (0.9ms)
- [x] T035 Update CLAUDE.md with new metrics module documentation
- [x] T036 Verify code coverage ≥80% for `scripts/metrics/` (87% achieved)

---

## Dependency Graph

```
Phase 1 (Setup)
    │
    ▼
Phase 2 (Foundational)
    │
    ├──────────────────┬──────────────────┐
    ▼                  ▼                  ▼
Phase 3 (US3)     Phase 4 (US2)     Phase 5 (US1)
TX Volume USD    Active Addresses   Monte Carlo
[Independent]    [Independent]      [Independent]
    │                  │                  │
    └──────────────────┴──────────────────┘
                       │
                       ▼
              Phase 6 (Integration)
                       │
                       ▼
              Phase 7 (Polish)
```

**Note**: User Stories (US1, US2, US3) are **independent** and can be implemented in parallel after Phase 2. However, KISS recommendation is sequential: US3 → US2 → US1.

---

## Parallel Execution Opportunities

### Within Phase 3 (US3)
```
T009, T010, T011 [P] - Tests can be written in parallel
```

### Within Phase 4 (US2)
```
T015, T016, T017 [P] - Tests can be written in parallel
```

### Within Phase 5 (US1)
```
T021, T022, T023, T024 [P] - Tests can be written in parallel
```

### Cross-Story Parallelism (after Phase 2)
```
Phase 3, Phase 4, Phase 5 can run in parallel if multiple developers available
```

---

## MVP Scope

**Recommended MVP**: Complete through Phase 6 (Integration)

- All 3 metrics implemented
- API endpoint functional
- Tests passing

**Defer to future iteration**:
- Performance optimization (Phase 7)
- Historical backfill
- Dashboard visualization

---

## File Checklist

After all tasks complete, verify:

```
✅ scripts/metrics/__init__.py
✅ scripts/metrics/tx_volume.py
✅ scripts/metrics/active_addresses.py
✅ scripts/metrics/monte_carlo_fusion.py
✅ scripts/models/metrics_models.py
✅ scripts/init_metrics_db.py
✅ api/main.py (modified - /api/metrics/latest)
✅ scripts/daily_analysis.py (modified - metrics integration)
✅ tests/test_onchain_metrics.py
✅ tests/integration/test_metrics_integration.py
```

---

## Validation Commands

```bash
# Run all tests
uv run pytest tests/test_onchain_metrics.py -v

# Check coverage
uv run pytest tests/test_onchain_metrics.py --cov=scripts/metrics --cov-report=term-missing

# Test API endpoint
curl http://localhost:8000/api/metrics/latest | jq

# Performance benchmark
uv run python -c "
from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion
import time
start = time.time()
for _ in range(100):
    monte_carlo_fusion(0.8, 0.9, 0.7, 0.85)
print(f'Monte Carlo: {(time.time()-start)/100*1000:.1f}ms (target: <100ms)')
"
```
