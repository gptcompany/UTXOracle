# Tasks: Backtesting Framework

**Input**: Design documents from `/specs/012-backtesting-framework/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Tests**: TDD approach per UTXOracle constitution.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Create scripts/backtest/ directory structure
- [X] T002 [P] Add BacktestConfig dataclass to scripts/backtest/engine.py
- [X] T003 [P] Add Trade dataclass to scripts/backtest/engine.py
- [X] T004 [P] Add BacktestResult dataclass to scripts/backtest/engine.py
- [X] T005 [P] Create empty tests/test_backtest.py

---

## Phase 2: Foundational

- [X] T006 Implement DuckDB data loader in scripts/backtest/data_loader.py
- [X] T007 [P] Implement HTML fallback data loader in scripts/backtest/data_loader.py
- [X] T008 [P] Add timestamp alignment utility in scripts/backtest/data_loader.py

---

## Phase 3: User Story 1 - Single Signal Backtest (P1) 🎯 MVP

**Goal**: Backtest individual signals against historical price data

### Tests (TDD RED)
- [X] T009 [P] [US1] Write test_backtest_perfect_signal() in tests/test_backtest.py
- [X] T010 [P] [US1] Write test_backtest_random_signal() in tests/test_backtest.py
- [X] T011 [P] [US1] Write test_backtest_inverted_signal() in tests/test_backtest.py

### Implementation (TDD GREEN)
- [X] T012 [US1] Implement trade signal logic in scripts/backtest/engine.py
- [X] T013 [US1] Implement trade execution simulation in scripts/backtest/engine.py
- [X] T014 [US1] Implement P&L calculation in scripts/backtest/engine.py
- [X] T015 [US1] Implement `run_backtest()` in scripts/backtest/engine.py
- [X] T016 [US1] Run tests - verify T009-T011 pass

**Checkpoint**: Single signal backtest functional ✅

---

## Phase 4: User Story 2 - Performance Metrics (P1)

**Goal**: Calculate Sharpe, Sortino, win rate, max drawdown, profit factor

### Tests (TDD RED)
- [X] T017 [P] [US2] Write test_sharpe_ratio_calculation() in tests/test_backtest.py
- [X] T018 [P] [US2] Write test_sortino_ratio_calculation() in tests/test_backtest.py
- [X] T019 [P] [US2] Write test_max_drawdown_calculation() in tests/test_backtest.py
- [X] T020 [P] [US2] Write test_win_rate_calculation() in tests/test_backtest.py

### Implementation (TDD GREEN)
- [X] T021 [US2] Implement sharpe_ratio() in scripts/backtest/metrics.py
- [X] T022 [P] [US2] Implement sortino_ratio() in scripts/backtest/metrics.py
- [X] T023 [P] [US2] Implement max_drawdown() in scripts/backtest/metrics.py
- [X] T024 [P] [US2] Implement win_rate() in scripts/backtest/metrics.py
- [X] T025 [P] [US2] Implement profit_factor() in scripts/backtest/metrics.py
- [X] T026 [US2] Run tests - verify T017-T020 pass

**Checkpoint**: All performance metrics calculated correctly ✅

---

## Phase 5: User Story 3 - Multi-Signal Comparison (P1)

**Goal**: Compare multiple signals side-by-side, rank by Sharpe

### Tests (TDD RED)
- [X] T027 [P] [US3] Write test_compare_signals_ranking() in tests/test_backtest.py
- [X] T028 [P] [US3] Write test_compare_signals_consistency() in tests/test_backtest.py

### Implementation (TDD GREEN)
- [X] T029 [US3] Add ComparisonResult dataclass to scripts/backtest/engine.py
- [X] T030 [US3] Implement compare_signals() in scripts/backtest/engine.py
- [X] T031 [US3] Run tests - verify T027-T028 pass

**Checkpoint**: Multi-signal comparison working ✅

---

## Phase 6: User Story 4 - Weight Optimization (P2)

**Goal**: Optimize fusion weights based on backtest Sharpe

### Tests (TDD RED)
- [X] T032 [P] [US4] Write test_weight_optimization_improves() in tests/test_backtest.py
- [X] T033 [P] [US4] Write test_weights_sum_to_one() in tests/test_backtest.py
- [X] T034 [P] [US4] Write test_walk_forward_validation() in tests/test_backtest.py

### Implementation (TDD GREEN)
- [X] T035 [US4] Add OptimizationResult dataclass to scripts/backtest/optimizer.py
- [X] T036 [US4] Implement grid search in scripts/backtest/optimizer.py
- [X] T037 [US4] Implement walk-forward validation in scripts/backtest/optimizer.py
- [X] T038 [US4] Implement optimize_weights() in scripts/backtest/optimizer.py
- [X] T039 [US4] Run tests - verify T032-T034 pass

**Checkpoint**: Weight optimization complete ✅

---

## Phase 7: User Story 5 - Database Integration (P2)

**Goal**: Store and retrieve backtest results from DuckDB

### Implementation
- [X] T040 [US5] Add backtest_results table to scripts/init_metrics_db.py
- [X] T041 [US5] Implement save_backtest_result() in scripts/backtest/data_loader.py
- [X] T042 [US5] Implement load_backtest_history() in scripts/backtest/data_loader.py

**Checkpoint**: Backtest persistence working ✅

---

## Phase 8: Polish

- [X] T043 [P] Add module docstrings to all backtest modules
- [X] T044 [P] Create scripts/backtest/__init__.py with public API exports
- [X] T045 Run full test suite - verify ≥67% coverage (16 tests pass)
- [X] T046 Run quickstart.md validation (API matches spec)
- [X] T047 Create integration test in tests/integration/test_backtest_pipeline.py

---

## Dependencies

```
Phase 1 (Setup)        → No dependencies
Phase 2 (Foundation)   → Phase 1
Phase 3 (US1)         → Phase 2 🎯 MVP
Phase 4 (US2)         → Phase 3
Phase 5 (US3)         → Phase 3
Phase 6 (US4)         → Phase 3, Phase 4
Phase 7 (US5)         → Phase 3
Phase 8 (Polish)      → All previous
```

## Summary

| Phase | Tasks |
|-------|-------|
| Setup | 5 |
| Foundation | 3 |
| US1 | 8 |
| US2 | 10 |
| US3 | 5 |
| US4 | 8 |
| US5 | 3 |
| Polish | 5 |
| **Total** | **47** |
