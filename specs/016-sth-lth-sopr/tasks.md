# Tasks: STH/LTH SOPR Implementation

**Input**: Design documents from `/specs/016-sth-lth-sopr/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: TDD approach required per Constitution Principle II. Tests written FIRST.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [Markers] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - complex algorithmic task requiring multi-implementation exploration
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions
- **Scripts**: `scripts/metrics/`, `scripts/models/`
- **Tests**: `tests/`
- **API**: `api/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and SOPR module structure

- [X] T001 Create feature branch `016-sth-lth-sopr` and verify checkout
- [ ] T002 [P] Create SOPR module file at `scripts/metrics/sopr.py` with docstring
- [X] T003 [P] Create test file at `tests/test_sopr.py` with imports
- [X] T004 [P] Add SOPR configuration to `.env.example` (SOPR_ENABLED, SOPR_STH_THRESHOLD_DAYS, etc.)
- [X] T005 [P] Create test fixtures file at `tests/fixtures/sopr_fixtures.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 Add SpentOutputSOPR dataclass to `scripts/models/metrics_models.py`
- [ ] T007 Add BlockSOPR dataclass to `scripts/models/metrics_models.py`
- [ ] T008 Add SOPRWindow dataclass to `scripts/models/metrics_models.py`
- [ ] T009 Add SOPRSignal dataclass to `scripts/models/metrics_models.py`
- [ ] T010 [P] Verify historical prices table exists in DuckDB with `utxoracle_prices`
- [ ] T011 [P] Create SOPR database schema (sopr_blocks, sopr_signals tables) in `scripts/metrics/sopr.py`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - SOPR Calculation (Priority: P1) 🎯 MVP

**Goal**: Calculate SOPR for individual spent outputs comparing spend price vs creation price

**Independent Test**: Given creation_price=$50K and spend_price=$100K, SOPR should equal 2.0

### Tests for User Story 1 (RED Phase)

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T012 [P] [US1] Unit test `test_sopr_calculation_profit()` in `tests/test_sopr.py`
- [ ] T013 [P] [US1] Unit test `test_sopr_calculation_loss()` in `tests/test_sopr.py`
- [ ] T014 [P] [US1] Unit test `test_sopr_calculation_breakeven()` in `tests/test_sopr.py`
- [ ] T015 [P] [US1] Unit test `test_sopr_invalid_prices()` in `tests/test_sopr.py`

**Run tests**: `uv run pytest tests/test_sopr.py -v -k "test_sopr_calculation"` → Must FAIL

### Implementation for User Story 1 (GREEN Phase)

- [ ] T016 [E] [US1] Implement `calculate_output_sopr()` function in `scripts/metrics/sopr.py`
- [ ] T017 [US1] Implement `get_historical_price()` for price lookup in `scripts/metrics/sopr.py`
- [ ] T018 [US1] Implement `get_utxo_creation_block()` for age calculation in `scripts/metrics/sopr.py`
- [ ] T019 [E] [US1] Add caching for creation block lookups in `scripts/metrics/sopr.py`
- [ ] T020 [US1] Run tests and verify all pass → GREEN

**Checkpoint**: Individual output SOPR calculation working and tested

---

## Phase 4: User Story 2 - STH/LTH Split (Priority: P1)

**Goal**: Split SOPR by holder duration (STH < 155 days, LTH >= 155 days)

**Independent Test**: Output held 30 days → STH cohort; Output held 200 days → LTH cohort

### Tests for User Story 2 (RED Phase)

- [ ] T021 [P] [US2] Unit test `test_sth_classification()` in `tests/test_sopr.py`
- [ ] T022 [P] [US2] Unit test `test_lth_classification()` in `tests/test_sopr.py`
- [ ] T023 [P] [US2] Unit test `test_block_sopr_aggregation()` in `tests/test_sopr.py`
- [ ] T024 [P] [US2] Unit test `test_block_sopr_sth_lth_split()` in `tests/test_sopr.py`

**Run tests**: `uv run pytest tests/test_sopr.py -v -k "test_sth or test_lth or test_block"` → Must FAIL

### Implementation for User Story 2 (GREEN Phase)

- [ ] T025 [US2] Implement cohort classification in `SpentOutputSOPR.__post_init__()` in `scripts/models/metrics_models.py`
- [ ] T026 [E] [US2] Implement `calculate_block_sopr()` function in `scripts/metrics/sopr.py`
- [ ] T027 [US2] Implement `BlockSOPR.from_outputs()` classmethod in `scripts/models/metrics_models.py`
- [ ] T028 [E] [US2] Add weighted average helper function in `scripts/metrics/sopr.py`
- [ ] T029 [US2] Run tests and verify all pass → GREEN

**Checkpoint**: Block SOPR with STH/LTH split working and tested

---

## Phase 5: User Story 3 - Trading Signals (Priority: P1)

**Goal**: Generate actionable signals from SOPR patterns (capitulation, break-even cross, distribution)

**Independent Test**: 3+ days of STH-SOPR < 1.0 → Capitulation signal with bullish sopr_vote

### Tests for User Story 3 (RED Phase)

- [ ] T030 [P] [US3] Unit test `test_detect_sth_capitulation()` in `tests/test_sopr.py`
- [ ] T031 [P] [US3] Unit test `test_detect_breakeven_cross()` in `tests/test_sopr.py`
- [ ] T032 [P] [US3] Unit test `test_detect_lth_distribution()` in `tests/test_sopr.py`
- [ ] T033 [P] [US3] Unit test `test_sopr_vote_generation()` in `tests/test_sopr.py`

**Run tests**: `uv run pytest tests/test_sopr.py -v -k "test_detect"` → Must FAIL

### Implementation for User Story 3 (GREEN Phase)

- [ ] T034 [E] [US3] Implement `detect_sopr_signals()` function in `scripts/metrics/sopr.py`
- [ ] T035 [US3] Implement `SOPRSignal.capitulation_signal()` classmethod in `scripts/models/metrics_models.py`
- [ ] T036 [US3] Implement `SOPRSignal.distribution_signal()` classmethod in `scripts/models/metrics_models.py`
- [ ] T037 [E] [US3] Implement rolling window analysis in `scripts/metrics/sopr.py`
- [ ] T038 [US3] Run tests and verify all pass → GREEN

**Checkpoint**: SOPR signal detection working and tested

---

## Phase 6: User Story 4 - Fusion Integration (Priority: P2)

**Goal**: Integrate SOPR signals into Monte Carlo fusion as 9th component

**Independent Test**: Enhanced fusion with sopr_vote contributes correctly weighted signal

### Tests for User Story 4 (RED Phase)

- [ ] T039 [P] [US4] Unit test `test_fusion_with_sopr_component()` in `tests/test_monte_carlo_fusion.py`
- [ ] T040 [P] [US4] Integration test `test_daily_analysis_with_sopr()` in `tests/test_sopr.py`

**Run tests**: `uv run pytest -v -k "test_fusion_with_sopr or test_daily_analysis_with_sopr"` → Must FAIL

### Implementation for User Story 4 (GREEN Phase)

- [ ] T041 [US4] Add `sopr` to `EVIDENCE_BASED_WEIGHTS` with weight 0.15 (FR-017) in `scripts/metrics/monte_carlo_fusion.py`
- [ ] T042 [US4] Update `enhanced_monte_carlo_fusion()` to accept sopr_vote as 9th component (FR-016) in `scripts/metrics/monte_carlo_fusion.py`
- [ ] T043 [US4] Add SOPR calculation to `scripts/daily_analysis.py` pipeline
- [ ] T044 [US4] Add `/api/metrics/sopr/current` endpoint in `api/main.py`
- [ ] T045 [US4] Add `/api/metrics/sopr/history` endpoint in `api/main.py`
- [ ] T046 [US4] Add `/api/metrics/sopr/signals` endpoint in `api/main.py`
- [ ] T047 [US4] Run tests and verify all pass → GREEN

**Checkpoint**: Full SOPR integration complete and tested

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, optimization, and validation

- [ ] T048 [P] Update CLAUDE.md with spec-016 completion status
- [ ] T049 [P] Update `docs/ARCHITECTURE.md` with SOPR module documentation
- [ ] T050 Run full test suite: `uv run pytest tests/ -v --tb=short`
- [ ] T051 Run linter: `ruff check scripts/metrics/sopr.py && ruff format scripts/metrics/sopr.py`
- [ ] T052 Validate quickstart.md scenarios work end-to-end
- [ ] T053 Run backtest to verify SOPR contribution to Sharpe ratio
- [ ] T054 Benchmark `calculate_block_sopr()` against NFR-001 target (<100ms per block with 3000 outputs)
- [ ] T055 Create PR with summary and merge

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 → US2 → US3 (sequential dependency chain: SpentOutputSOPR → BlockSOPR → Signals)
  - Within each user story, test tasks marked [P] can run in parallel
  - US4 depends on US1-US3 completion
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (SOPR Calc)**: Foundational complete → Can start
- **User Story 2 (STH/LTH Split)**: Depends on US1 (uses SpentOutputSOPR)
- **User Story 3 (Signals)**: Depends on US2 (uses BlockSOPR)
- **User Story 4 (Fusion)**: Depends on US1-US3 (integrates all)

### Within Each User Story

- Tests (RED) MUST be written and FAIL before implementation
- Implementation (GREEN) makes tests pass
- Refactor if needed while maintaining passing tests
- Story complete before moving to next

### Parallel Opportunities

- T002, T003, T004, T005 can run in parallel (Phase 1)
- T006-T009 are sequential (same file)
- T010, T011 can run in parallel
- All test tasks within a phase marked [P] can run in parallel
- User stories are sequential (US1 → US2 → US3), only [P] tasks within each story can parallel

---

## Parallel Example: User Story 1 Tests

```bash
# Launch all US1 tests together:
Task: "Unit test test_sopr_calculation_profit() in tests/test_sopr.py"
Task: "Unit test test_sopr_calculation_loss() in tests/test_sopr.py"
Task: "Unit test test_sopr_calculation_breakeven() in tests/test_sopr.py"
Task: "Unit test test_sopr_invalid_prices() in tests/test_sopr.py"
```

---

## Implementation Strategy

### MVP First (User Story 1-3)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL)
3. Complete Phase 3: User Story 1 (SOPR Calculation)
4. Complete Phase 4: User Story 2 (STH/LTH Split)
5. Complete Phase 5: User Story 3 (Signals)
6. **STOP and VALIDATE**: Test SOPR independently
7. Then add Phase 6: Fusion Integration

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 (SOPR Calc) → Can calculate individual output SOPR
3. US2 (STH/LTH) → Can aggregate and split by cohort
4. US3 (Signals) → Can detect trading patterns
5. US4 (Fusion) → Full integration with Monte Carlo
6. Each story adds value without breaking previous stories

---

## Summary

| Metric | Count |
|--------|-------|
| **Total Tasks** | 55 |
| **Setup Tasks** | 5 |
| **Foundational Tasks** | 6 |
| **US1 Tasks** | 9 |
| **US2 Tasks** | 9 |
| **US3 Tasks** | 9 |
| **US4 Tasks** | 9 |
| **Polish Tasks** | 8 |
| **Parallel Opportunities** | 24 tasks marked [P] |

---

## Notes

- TDD required: RED → GREEN → REFACTOR
- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Each user story independently testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
