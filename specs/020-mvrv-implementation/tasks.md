# Tasks: MVRV-Z Score + STH/LTH Variants

**Input**: Design documents from `/specs/020-mvrv-implementation/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: TDD approach per Constitution Principle II - tests are REQUIRED for all new functions.

**Organization**: Tasks are grouped by functional requirement (FR-001 through FR-005) to enable independent implementation and testing.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - use for complex algorithmic tasks
- **[Story]**: Which functional requirement this task belongs to (FR1, FR2, FR3, FR4, FR5)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add missing prerequisite models from spec-017

**TDD Note**: Dataclasses are type-only definitions validated by type checkers (mypy/pyright).
Per Constitution II exception: pure data containers without logic don't require RED phase tests.
However, `AgeCohortsConfig.classify()` contains logic and requires a test. T005 validates no regressions.

- [x] T001 Add `UTXOLifecycle` dataclass to `scripts/models/metrics_models.py`
- [x] T002 Add `UTXOSetSnapshot` dataclass to `scripts/models/metrics_models.py`
- [x] T003a [Setup] Write test `TestAgeCohortsConfig.test_classify_sth_lth_boundary` in `tests/test_metrics_models.py`
- [x] T003 Add `AgeCohortsConfig` dataclass to `scripts/models/metrics_models.py`
- [x] T004 Add `SyncState` dataclass to `scripts/models/metrics_models.py`
- [x] T005 Verify existing tests pass with new models: `uv run pytest tests/test_realized_metrics.py -v`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add new dataclass and verify infrastructure

**⚠️ CRITICAL**: FR-001 through FR-003 depend on this phase completion

- [x] T006 Add `MVRVExtendedSignal` dataclass to `scripts/models/metrics_models.py`
- [x] T007a [FR1] Write test `TestMarketCapHistory.test_get_history_365_days` in `tests/test_realized_metrics.py`
- [x] T007b [FR1] Write test `TestMarketCapHistory.test_insufficient_history_warning` in `tests/test_realized_metrics.py`
- [x] T007 Add `get_market_cap_history()` helper function to `scripts/metrics/realized_metrics.py`
- [x] T008 Verify database has `utxo_snapshots` table with `market_cap_usd` column

**Checkpoint**: Foundation ready - FR implementations can now begin

---

## Phase 3: FR-001 - MVRV-Z Score (Priority: P0) 🎯 MVP

**Goal**: Calculate MVRV-Z score using 365-day rolling market cap history

**Independent Test**: `calculate_mvrv_z()` returns valid Z-score for known inputs

### Tests for FR-001

- [x] T009 [FR1] Write test `TestMVRVZScore.test_basic_calculation` in `tests/test_realized_metrics.py`
- [x] T010 [FR1] Write test `TestMVRVZScore.test_insufficient_history` in `tests/test_realized_metrics.py`
- [x] T011 [FR1] Write test `TestMVRVZScore.test_zero_std_deviation` in `tests/test_realized_metrics.py`
- [x] T012 [FR1] Write test `TestMVRVZScore.test_typical_ranges` in `tests/test_realized_metrics.py`

### Implementation for FR-001

- [x] T013 [FR1] Implement `calculate_mvrv_z(market_cap, realized_cap, history)` in `scripts/metrics/realized_metrics.py`
- [x] T014 [FR1] Add logging for Z-score edge cases (insufficient data, zero std) in `scripts/metrics/realized_metrics.py`
- [x] T015 [FR1] Run tests to verify GREEN: `uv run pytest tests/test_realized_metrics.py::TestMVRVZScore -v`

**Checkpoint**: FR-001 complete - MVRV-Z Score functional

---

## Phase 4: FR-002 - Cohort Realized Cap (Priority: P0)

**Goal**: Calculate realized cap for STH and LTH cohorts

**Independent Test**: `calculate_cohort_realized_cap()` returns correct values for STH/LTH

### Tests for FR-002

- [ ] T016 [FR2] Write test `TestCohortRealizedCap.test_sth_realized_cap` in `tests/test_realized_metrics.py`
- [ ] T017 [FR2] Write test `TestCohortRealizedCap.test_lth_realized_cap` in `tests/test_realized_metrics.py`
- [ ] T018 [FR2] Write test `TestCohortRealizedCap.test_sth_plus_lth_equals_total` in `tests/test_realized_metrics.py`
- [ ] T019 [FR2] Write test `TestCohortRealizedCap.test_custom_threshold` in `tests/test_realized_metrics.py`

### Implementation for FR-002

- [ ] T020 [FR2] Implement `calculate_cohort_realized_cap(conn, current_block, cohort, threshold_days)` in `scripts/metrics/realized_metrics.py`
- [ ] T021 [FR2] Run tests to verify GREEN: `uv run pytest tests/test_realized_metrics.py::TestCohortRealizedCap -v`

**Checkpoint**: FR-002 complete - Cohort Realized Cap functional

---

## Phase 5: FR-003 - STH/LTH MVRV (Priority: P0)

**Goal**: Calculate MVRV ratios for STH and LTH cohorts

**Independent Test**: `calculate_cohort_mvrv()` returns correct ratios

### Tests for FR-003

- [ ] T022 [FR3] Write test `TestCohortMVRV.test_sth_mvrv_calculation` in `tests/test_realized_metrics.py`
- [ ] T023 [FR3] Write test `TestCohortMVRV.test_lth_mvrv_calculation` in `tests/test_realized_metrics.py`
- [ ] T024 [FR3] Write test `TestCohortMVRV.test_zero_realized_cap_handling` in `tests/test_realized_metrics.py`

### Implementation for FR-003

- [ ] T025 [FR3] Implement `calculate_cohort_mvrv(market_cap, cohort_realized_cap)` in `scripts/metrics/realized_metrics.py`
- [ ] T026 [FR3] Run tests to verify GREEN: `uv run pytest tests/test_realized_metrics.py::TestCohortMVRV -v`

**Checkpoint**: FR-003 complete - STH/LTH MVRV functional

---

## Phase 6: FR-004 - Signal Classification (Priority: P1)

**Goal**: Classify MVRV-Z into zones and generate confidence scores

**Independent Test**: Zone classification matches spec thresholds

### Tests for FR-004

- [ ] T027 [FR4] Write test `TestMVRVSignal.test_extreme_sell_zone` in `tests/test_realized_metrics.py`
- [ ] T028 [FR4] Write test `TestMVRVSignal.test_caution_zone` in `tests/test_realized_metrics.py`
- [ ] T029 [FR4] Write test `TestMVRVSignal.test_normal_zone` in `tests/test_realized_metrics.py`
- [ ] T030 [FR4] Write test `TestMVRVSignal.test_accumulation_zone` in `tests/test_realized_metrics.py`

### Implementation for FR-004

- [ ] T031 [FR4] Implement `classify_mvrv_zone(mvrv_z)` in `scripts/metrics/realized_metrics.py`
- [ ] T032a [FR4] Write test `TestMVRVSignal.test_confidence_extreme_zones` in `tests/test_realized_metrics.py`
- [ ] T032b [FR4] Write test `TestMVRVSignal.test_confidence_normal_zone` in `tests/test_realized_metrics.py`
- [ ] T032 [FR4] Implement `calculate_mvrv_confidence(mvrv_z, zone)` in `scripts/metrics/realized_metrics.py`
- [ ] T033 [FR4] Implement `get_mvrv_extended_signal(conn, current_block, current_price)` in `scripts/metrics/realized_metrics.py`
- [ ] T034 [FR4] Run tests to verify GREEN: `uv run pytest tests/test_realized_metrics.py::TestMVRVSignal -v`

**Checkpoint**: FR-004 complete - Signal classification functional

---

## Phase 7: FR-005 - Fusion Integration (Priority: P1)

**Goal**: Add MVRV-Z vote to enhanced_fusion() with proper weight allocation

**Independent Test**: Fusion with mvrv_z_vote produces valid signal

### Tests for FR-005

- [ ] T035 [FR5] Write test `TestMVRVFusion.test_weights_sum_to_one` in `tests/test_monte_carlo_fusion.py`
- [ ] T036 [FR5] Write test `TestMVRVFusion.test_mvrv_z_vote_integration` in `tests/test_monte_carlo_fusion.py`
- [ ] T037 [FR5] Write test `TestMVRVFusion.test_mvrv_z_optional` in `tests/test_monte_carlo_fusion.py`

### Implementation for FR-005

- [ ] T038 [FR5] Update `ENHANCED_WEIGHTS` in `scripts/metrics/monte_carlo_fusion.py`: reduce `power_law` 0.09→0.06, add `mvrv_z` 0.03
- [ ] T039 [FR5] Add `mvrv_z_vote` and `mvrv_z_conf` parameters to `enhanced_fusion()` in `scripts/metrics/monte_carlo_fusion.py`
- [ ] T040 [FR5] Update `EnhancedFusionResult` dataclass with `mvrv_z_vote` and `mvrv_z_weight` fields in `scripts/models/metrics_models.py`
- [ ] T041 [FR5] Run tests to verify GREEN: `uv run pytest tests/test_monte_carlo_fusion.py::TestMVRVFusion -v`

**Checkpoint**: FR-005 complete - Fusion integration functional

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Validation, documentation, and final verification

- [ ] T042 [P] Run all tests to verify no regressions: `uv run pytest tests/ -v`
- [ ] T043 [P] Validate quickstart.md examples work
- [ ] T044 [P] Run linting: `ruff check scripts/metrics/realized_metrics.py scripts/metrics/monte_carlo_fusion.py`
- [ ] T045 [P] Run formatter: `ruff format scripts/metrics/realized_metrics.py scripts/metrics/monte_carlo_fusion.py`
- [ ] T046 Verify STH + LTH realized cap ≈ Total realized cap invariant with real data
- [ ] T047 Update `docs/ARCHITECTURE.md` with spec-020 module documentation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - adds missing prerequisite models
- **Foundational (Phase 2)**: Depends on Setup - adds MVRVExtendedSignal model
- **FR-001 (Phase 3)**: Depends on Foundational - MVRV-Z Score
- **FR-002 (Phase 4)**: Depends on Foundational - Cohort Realized Cap
- **FR-003 (Phase 5)**: Depends on FR-002 - STH/LTH MVRV
- **FR-004 (Phase 6)**: Depends on FR-001, FR-002, FR-003 - Signal Classification
- **FR-005 (Phase 7)**: Depends on FR-004 - Fusion Integration
- **Polish (Phase 8)**: Depends on all FR phases complete

### Functional Requirement Dependencies

```
Phase 1: Setup
    │
    ▼
Phase 2: Foundational
    │
    ├──────────────┬──────────────┐
    ▼              ▼              │
Phase 3: FR-001   Phase 4: FR-002 │
(MVRV-Z)          (Cohort Cap)   │
    │              │              │
    │              ▼              │
    │         Phase 5: FR-003 ◄───┘
    │         (Cohort MVRV)
    │              │
    ▼              ▼
    └──────┬───────┘
           ▼
    Phase 6: FR-004
    (Signal Classification)
           │
           ▼
    Phase 7: FR-005
    (Fusion Integration)
           │
           ▼
    Phase 8: Polish
```

### Within Each Functional Requirement

- Tests MUST be written and FAIL before implementation (TDD)
- Test verification after implementation (GREEN)
- Checkpoint validation before next FR

### Parallel Opportunities

**Phase 8 (Polish)** - only phase with true parallel opportunities:
- T042, T043, T044, T045 can run in parallel (independent commands, no file conflicts)

**Note**: Other phases have tasks that edit the same file, so they CANNOT run in parallel:
- Phase 1: T001-T004 all edit `metrics_models.py` → sequential
- FR-001 Tests: T009-T012 all edit `test_realized_metrics.py` → sequential
- FR-002 Tests: T016-T019 all edit `test_realized_metrics.py` → sequential
- FR-003 Tests: T022-T024 all edit `test_realized_metrics.py` → sequential
- FR-004 Tests: T027-T030 all edit `test_realized_metrics.py` → sequential
- FR-005 Tests: T035-T037 all edit `test_monte_carlo_fusion.py` → sequential

---

## Parallel Example: Polish Phase

```bash
# Only Polish phase has true parallel opportunities (different targets):
Task: "Run all tests to verify no regressions"        # pytest execution
Task: "Validate quickstart.md examples work"          # validation script
Task: "Run linting on metrics modules"                # ruff check
Task: "Run formatter on metrics modules"              # ruff format
```

**Why other phases are sequential**: Tasks that edit the same file (e.g., multiple test methods in `test_realized_metrics.py`) would conflict if run in parallel.

---

## Implementation Strategy

### MVP First (FR-001 Only)

1. Complete Phase 1: Setup (add missing models)
2. Complete Phase 2: Foundational (add MVRVExtendedSignal)
3. Complete Phase 3: FR-001 (MVRV-Z Score)
4. **STOP and VALIDATE**: Test `calculate_mvrv_z()` independently
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add FR-001 → Test independently → MVRV-Z available
3. Add FR-002 + FR-003 → Test independently → Cohort MVRV available
4. Add FR-004 → Test independently → Signal zones available
5. Add FR-005 → Test independently → Fusion complete
6. Each FR adds value without breaking previous FRs

### Estimated Effort (from spec)

| Phase | Tasks | Effort |
|-------|-------|--------|
| Setup | T001-T005 (+T003a) | 35min |
| Foundational | T006-T008 (+T007a,b) | 40min |
| FR-001 | T009-T015 | 1.5h |
| FR-002 | T016-T021 | 1h |
| FR-003 | T022-T026 | 30min |
| FR-004 | T027-T034 (+T032a,b) | 40min |
| FR-005 | T035-T041 | 1h |
| Polish | T042-T047 | 30min |
| **Total** | **52 tasks** | **~6 hours** |

---

## Notes

- [P] tasks = different files, no dependencies (processed by /speckit.implement)
- [FR] label maps task to specific functional requirement for traceability
- Each FR should be independently completable and testable
- TDD is REQUIRED (Constitution Principle II): verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate FR independently
- Invariant check: STH + LTH realized cap ≈ Total realized cap

---

## Files Modified

| File | Changes |
|------|---------|
| `scripts/models/metrics_models.py` | ADD: UTXOLifecycle, UTXOSetSnapshot, AgeCohortsConfig, SyncState, MVRVExtendedSignal |
| `scripts/metrics/realized_metrics.py` | ADD: calculate_mvrv_z, calculate_cohort_realized_cap, calculate_cohort_mvrv, classify_mvrv_zone, get_mvrv_extended_signal, get_market_cap_history |
| `scripts/metrics/monte_carlo_fusion.py` | MODIFY: ENHANCED_WEIGHTS, enhanced_fusion() |
| `tests/test_metrics_models.py` | ADD: TestAgeCohortsConfig (new file) |
| `tests/test_realized_metrics.py` | ADD: TestMarketCapHistory, TestMVRVZScore, TestCohortRealizedCap, TestCohortMVRV, TestMVRVSignal |
| `tests/test_monte_carlo_fusion.py` | ADD: TestMVRVFusion |
| `docs/ARCHITECTURE.md` | ADD: spec-020 documentation |
