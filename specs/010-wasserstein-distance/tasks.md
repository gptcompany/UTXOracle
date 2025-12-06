# Tasks: Wasserstein Distance Calculator

**Input**: Design documents from `/specs/010-wasserstein-distance/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: TDD approach per UTXOracle constitution (Principle II). Tests written FIRST.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions (from plan.md)
- **Metrics module**: `scripts/metrics/`
- **Models**: `scripts/models/metrics_models.py`
- **Tests**: `tests/test_wasserstein.py`, `tests/integration/`
- **API**: `api/main.py`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project structure and model definitions

- [ ] T001 Add WassersteinResult dataclass to scripts/models/metrics_models.py
- [ ] T002 [P] Add RollingWassersteinResult dataclass to scripts/models/metrics_models.py
- [ ] T003 [P] Create empty scripts/metrics/wasserstein.py module with docstring
- [ ] T004 [P] Create empty tests/test_wasserstein.py with pytest imports

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core algorithm infrastructure that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T005 Implement `_interpolate_quantiles()` helper in scripts/metrics/wasserstein.py
- [ ] T006 [P] Add configuration constants (thresholds, defaults) in scripts/metrics/wasserstein.py
- [ ] T007 [P] Add type hints and imports for all metric models

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Distribution Shift Detection (Priority: P1) 🎯 MVP

**Goal**: Compare two UTXO distributions and detect if a significant shift occurred

**Independent Test**: Given two known distributions with analytically computed W distance, verify calculation within ±0.01

### Tests for User Story 1 (TDD RED phase)

- [ ] T008 [P] [US1] Write test_wasserstein_identical_distributions() in tests/test_wasserstein.py - expect W=0.0
- [ ] T009 [P] [US1] Write test_wasserstein_shifted_uniform() in tests/test_wasserstein.py - expect W=0.5 for shift
- [ ] T010 [P] [US1] Write test_wasserstein_direction_concentration() in tests/test_wasserstein.py
- [ ] T011 [P] [US1] Write test_wasserstein_direction_dispersion() in tests/test_wasserstein.py
- [ ] T012 [P] [US1] Write test_wasserstein_insufficient_samples() in tests/test_wasserstein.py - expect is_valid=False

### Implementation for User Story 1 (TDD GREEN phase)

- [ ] T013 [US1] Implement `wasserstein_1d()` core algorithm in scripts/metrics/wasserstein.py
- [ ] T014 [US1] Implement `_detect_shift_direction()` helper in scripts/metrics/wasserstein.py
- [ ] T015 [US1] Implement `_normalize_distance()` helper in scripts/metrics/wasserstein.py
- [ ] T016 [US1] Implement `calculate_wasserstein()` returning WassersteinResult in scripts/metrics/wasserstein.py
- [ ] T017 [US1] Run tests - verify all T008-T012 pass

**Checkpoint**: Single-pair Wasserstein calculation functional and tested

---

## Phase 4: User Story 2 - Rolling Window Analysis (Priority: P1)

**Goal**: Compute rolling Wasserstein distances over time series to detect regime transitions

**Independent Test**: Given series with synthetic regime change at t=500, verify W peaks at that point

### Tests for User Story 2 (TDD RED phase)

- [ ] T018 [P] [US2] Write test_rolling_wasserstein_stable() in tests/test_wasserstein.py - expect low variance
- [ ] T019 [P] [US2] Write test_rolling_wasserstein_regime_change() in tests/test_wasserstein.py - expect peak at change
- [ ] T020 [P] [US2] Write test_rolling_sustained_shift() in tests/test_wasserstein.py - 3+ consecutive detection
- [ ] T021 [P] [US2] Write test_rolling_regime_status_transitions() in tests/test_wasserstein.py

### Implementation for User Story 2 (TDD GREEN phase)

- [ ] T022 [US2] Implement `_create_windows()` helper in scripts/metrics/wasserstein.py
- [ ] T023 [US2] Implement `_detect_sustained_shift()` helper in scripts/metrics/wasserstein.py
- [ ] T024 [US2] Implement `_classify_regime_status()` helper in scripts/metrics/wasserstein.py
- [ ] T025 [US2] Implement `rolling_wasserstein()` returning RollingWassersteinResult in scripts/metrics/wasserstein.py
- [ ] T026 [US2] Implement `wasserstein_vote()` signal calculation in scripts/metrics/wasserstein.py
- [ ] T027 [US2] Run tests - verify all T018-T021 pass

**Checkpoint**: Rolling window analysis functional, regime detection working

---

## Phase 5: User Story 3 - Integration with Enhanced Fusion (Priority: P2)

**Goal**: Add Wasserstein as 8th component in Monte Carlo fusion, update weights

**Independent Test**: Run enhanced_fusion with wasserstein_vote, verify it affects signal_mean

### Tests for User Story 3 (TDD RED phase)

- [ ] T028 [P] [US3] Write test_enhanced_fusion_with_wasserstein() in tests/test_wasserstein.py
- [ ] T029 [P] [US3] Write test_fusion_weights_sum_to_one() in tests/test_wasserstein.py
- [ ] T030 [P] [US3] Write test_fusion_without_wasserstein_backward_compatible() in tests/test_wasserstein.py

### Implementation for User Story 3 (TDD GREEN phase)

- [ ] T031 [US3] Update EnhancedFusionResult in scripts/models/metrics_models.py - add wasserstein fields
- [ ] T032 [US3] Update ENHANCED_WEIGHTS in scripts/metrics/monte_carlo_fusion.py for 8 components
- [ ] T033 [US3] Update `enhanced_fusion()` in scripts/metrics/monte_carlo_fusion.py to accept wasserstein_vote
- [ ] T034 [US3] Run tests - verify all T028-T030 pass
- [ ] T035 [US3] Verify existing spec-009 tests still pass (no regression)

**Checkpoint**: Wasserstein integrated into fusion, backward compatible

---

## Phase 6: User Story 4 - API Endpoint (Priority: P2)

**Goal**: Expose Wasserstein metrics via REST API

**Independent Test**: curl /api/metrics/wasserstein returns valid JSON response

### Tests for User Story 4 (TDD RED phase)

- [ ] T036 [P] [US4] Write test_api_wasserstein_latest() in tests/test_api.py
- [ ] T037 [P] [US4] Write test_api_wasserstein_history() in tests/test_api.py
- [ ] T038 [P] [US4] Write test_api_wasserstein_404_when_no_data() in tests/test_api.py

### Implementation for User Story 4 (TDD GREEN phase)

- [ ] T039 [US4] Add `/api/metrics/wasserstein` endpoint in api/main.py
- [ ] T040 [US4] Add `/api/metrics/wasserstein/history` endpoint in api/main.py
- [ ] T041 [US4] Add `/api/metrics/wasserstein/regime` endpoint in api/main.py
- [ ] T042 [US4] Run tests - verify all T036-T038 pass

**Checkpoint**: API endpoints functional

---

## Phase 7: User Story 5 - Pipeline Integration (Priority: P1)

**Goal**: Add Wasserstein calculation to daily_analysis.py pipeline

**Independent Test**: Run daily_analysis.py, verify wasserstein fields in DuckDB metrics table

### Implementation for User Story 5

- [ ] T043 [US5] Add Wasserstein imports to scripts/daily_analysis.py
- [ ] T044 [US5] Add Wasserstein calculation call in daily_analysis.py after UTXO extraction
- [ ] T045 [US5] Update DuckDB metrics table schema in scripts/init_metrics_db.py
- [ ] T046 [US5] Add Wasserstein fields to metrics save function in scripts/daily_analysis.py
- [ ] T047 [US5] Pass wasserstein_vote to enhanced_fusion() call in scripts/daily_analysis.py

**Checkpoint**: Full pipeline integration complete

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, cleanup, and final validation

- [ ] T048 [P] Add module docstring and function docstrings in scripts/metrics/wasserstein.py
- [ ] T049 [P] Export Wasserstein functions from scripts/metrics/__init__.py
- [ ] T050 [P] Add WASSERSTEIN_* configuration to .env.example
- [ ] T051 Run full test suite - verify ≥85% coverage for wasserstein.py
- [ ] T052 Run quickstart.md validation - test all code examples
- [ ] T053 Update CLAUDE.md Architecture section with Wasserstein module
- [ ] T054 Create integration test in tests/integration/test_wasserstein_pipeline.py

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)           → No dependencies
Phase 2 (Foundational)    → Depends on Phase 1
Phase 3 (US1)            → Depends on Phase 2 ⚠️ MVP
Phase 4 (US2)            → Depends on Phase 3 (uses wasserstein_1d)
Phase 5 (US3)            → Depends on Phase 3 (uses calculate_wasserstein)
Phase 6 (US4)            → Depends on Phase 4 (exposes rolling results)
Phase 7 (US5)            → Depends on Phase 4, Phase 5
Phase 8 (Polish)         → Depends on all previous phases
```

### User Story Dependencies

```
US1 (Single Distance)     → Foundation only (independent)
US2 (Rolling)            → US1 (uses core algorithm)
US3 (Fusion Integration) → US1 (uses WassersteinResult)
US4 (API)                → US2 (exposes rolling results)
US5 (Pipeline)           → US2, US3 (full integration)
```

### Parallel Opportunities

**Within Phase 1**:
- T002, T003, T004 can run in parallel

**Within Phase 3 (US1 Tests)**:
- T008, T009, T010, T011, T012 can ALL run in parallel

**Within Phase 4 (US2 Tests)**:
- T018, T019, T020, T021 can ALL run in parallel

**Across Stories** (if team capacity):
- US1 and US3 tests can be written in parallel (different focuses)
- After US1 complete: US2 and US3 implementations can proceed in parallel

---

## Parallel Example: User Story 1 Tests

```bash
# Launch all US1 tests in parallel (TDD RED phase):
pytest tests/test_wasserstein.py::test_wasserstein_identical_distributions -v &
pytest tests/test_wasserstein.py::test_wasserstein_shifted_uniform -v &
pytest tests/test_wasserstein.py::test_wasserstein_direction_concentration -v &
pytest tests/test_wasserstein.py::test_wasserstein_direction_dispersion -v &
pytest tests/test_wasserstein.py::test_wasserstein_insufficient_samples -v &
wait
# All should FAIL (RED) at this point
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational (T005-T007)
3. Complete Phase 3: User Story 1 (T008-T017)
4. **STOP and VALIDATE**: Single-pair Wasserstein working
5. Deliverable: Core `wasserstein_1d()` function

### Incremental Delivery

```
Setup → Foundational → US1 (MVP!)
                       ↓
                      US2 (Rolling) → US4 (API)
                       ↓              ↓
                      US3 (Fusion) → US5 (Pipeline)
                                     ↓
                                   Polish
```

### Estimated Task Counts

| Phase | Story | Task Count |
|-------|-------|------------|
| 1 | Setup | 4 |
| 2 | Foundational | 3 |
| 3 | US1 | 10 |
| 4 | US2 | 10 |
| 5 | US3 | 8 |
| 6 | US4 | 7 |
| 7 | US5 | 5 |
| 8 | Polish | 7 |
| **Total** | | **54** |

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [US#] label maps task to specific user story
- TDD: Tests MUST fail before implementation begins
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Target: ≥85% code coverage per constitution
