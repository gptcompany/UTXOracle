# Tasks: Address Balance Cohorts (spec-039)

**Input**: Design documents from `/specs/039-address-balance-cohorts/`
**Prerequisites**: plan.md (required), spec.md (required)

**Tests**: TDD approach specified in plan.md - tests MUST be written first and fail before implementation.

**Organization**: Two user stories - Core Calculation (MVP) and API Endpoint.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - use for complex algorithmic tasks
- **[Story]**: Which user story this task belongs to (US1 = Core Calculation, US2 = API)

---

## Phase 1: Setup

**Purpose**: Verify existing infrastructure is ready for new metric

- [ ] T001 Verify `utxo_lifecycle_full` VIEW exists and has required columns (address, btc_value, creation_price_usd, is_spent) in DuckDB database

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add data models that all subsequent tasks depend on

**⚠️ CRITICAL**: The dataclasses must be created before tests or implementation can proceed.

- [ ] T002 Add `AddressCohort` enum (RETAIL, MID_TIER, WHALE) to scripts/models/metrics_models.py
- [ ] T003 Add `CohortMetrics` dataclass to scripts/models/metrics_models.py following spec.md structure
- [ ] T004 Add `AddressCohortsResult` dataclass to scripts/models/metrics_models.py following spec.md structure

**Checkpoint**: Foundation ready - User Story 1 implementation can now begin

---

## Phase 3: User Story 1 - Core Cohort Calculation (Priority: P1) 🎯 MVP

**Goal**: Calculate cost basis, supply, and MVRV for each address balance cohort (whale/mid-tier/retail)

**Independent Test**:
- `uv run pytest tests/test_address_cohorts.py -v` passes
- Function returns valid `AddressCohortsResult` with all three cohorts

### Tests for User Story 1 (TDD - Write FIRST, Ensure They FAIL)

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T005 [US1] Write test_calculate_retail_cohort_basic in tests/test_address_cohorts.py
- [ ] T006 [US1] Write test_calculate_whale_cohort_basic in tests/test_address_cohorts.py
- [ ] T007 [US1] Write test_calculate_mid_tier_cohort_basic in tests/test_address_cohorts.py
- [ ] T008 [US1] Write test_cohort_mvrv_calculation in tests/test_address_cohorts.py
- [ ] T009 [US1] Write test_whale_retail_spread_calculation in tests/test_address_cohorts.py
- [ ] T010 [US1] Write test_empty_cohort_handling in tests/test_address_cohorts.py
- [ ] T011 [US1] Write test_null_address_excluded in tests/test_address_cohorts.py

**Checkpoint**: All tests written and failing (RED phase complete)

### Implementation for User Story 1

- [ ] T012 [US1] Create scripts/metrics/address_cohorts.py with module docstring and imports
- [ ] T013 [E] [US1] Implement `calculate_address_cohorts()` function with two-stage SQL aggregation in scripts/metrics/address_cohorts.py
- [ ] T014 [US1] Implement `_classify_cohort()` helper function for balance → cohort mapping in scripts/metrics/address_cohorts.py
- [ ] T015 [US1] Implement `_calculate_mvrv()` helper function in scripts/metrics/address_cohorts.py
- [ ] T016 [US1] Implement `_calculate_cross_cohort_signals()` function in scripts/metrics/address_cohorts.py
- [ ] T017 [US1] Run full test suite: `uv run pytest tests/test_address_cohorts.py -v --cov=scripts/metrics/address_cohorts --cov-report=term-missing`
- [ ] T018 [P] [US1] Run linter and formatter: `ruff check scripts/metrics/address_cohorts.py && ruff format scripts/metrics/address_cohorts.py`

**Checkpoint**: Core calculation complete - all tests passing (GREEN phase)

---

## Phase 4: User Story 2 - API Endpoint (Priority: P2)

**Goal**: Expose address cohorts metrics via REST API

**Independent Test**:
- `curl http://localhost:8000/api/metrics/address-cohorts?current_price=98500` returns valid JSON

### Tests for User Story 2 (TDD)

- [ ] T019 [US2] Write test_address_cohorts_api_endpoint_success in tests/test_address_cohorts.py
- [ ] T020 [US2] Write test_address_cohorts_api_endpoint_error_handling in tests/test_address_cohorts.py

### Implementation for User Story 2

- [ ] T021 [US2] Add `AddressCohortsResponse` Pydantic model to api/main.py
- [ ] T022 [US2] Add GET `/api/metrics/address-cohorts` endpoint to api/main.py
- [ ] T023 [US2] Add proper error handling and logging to endpoint in api/main.py
- [ ] T024 [P] [US2] Run API tests: `uv run pytest tests/test_address_cohorts.py::test_address_cohorts_api -v`

**Checkpoint**: API endpoint functional

---

## Phase 5: Polish & Documentation

**Purpose**: Documentation and final validation

- [ ] T025 [P] Update docs/ARCHITECTURE.md with Address Cohorts metric documentation
- [ ] T026 [P] Add usage examples to scripts/metrics/address_cohorts.py docstrings
- [ ] T027 Run full test suite with coverage: `uv run pytest tests/ -v --cov=scripts/metrics/address_cohorts --cov-fail-under=85`
- [ ] T028 Validate against success criteria from spec.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - verify infrastructure
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational - Core calculation
- **User Story 2 (Phase 4)**: Depends on User Story 1 - API wraps core function
- **Polish (Phase 5)**: Depends on User Story 2 completion

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2)
- **User Story 2 (P2)**: Depends on User Story 1 completion (uses `calculate_address_cohorts()`)

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD)
- Helper functions before main function
- Core implementation before integration
- Verify tests pass (GREEN) before moving to next phase

### Parallel Opportunities

- T002, T003, T004 (dataclasses) must be sequential (same file)
- T005-T011 (US1 tests) must be sequential (same file)
- T017 and T018 can run in parallel (different operations)
- T025 and T026 can run in parallel (different files)

---

## Parallel Example: User Story 1

```bash
# After tests pass, these can run in parallel:
Task: T017 "Run full test suite"
Task: T018 "Run linter and formatter"

# Documentation tasks in parallel:
Task: T025 "Update ARCHITECTURE.md"
Task: T026 "Add usage examples"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup verification
2. Complete Phase 2: Foundational (dataclasses)
3. Complete Phase 3: User Story 1 (core calculation)
4. **STOP and VALIDATE**: Run `uv run pytest tests/test_address_cohorts.py -v`
5. Core metric available via Python API

### Full Delivery

1. Setup → Foundational → US1 → US2 → Polish
2. Each phase builds on previous
3. API endpoint available after US2

---

## Notes

- [P] tasks = different files, no dependencies
- [E] tasks = complex SQL aggregation, may benefit from alpha-evolve exploration
- TDD mandatory per plan.md - write tests first
- Cohort thresholds: RETAIL < 1 BTC, MID_TIER 1-100 BTC, WHALE >= 100 BTC
- Reuse patterns from scripts/metrics/cost_basis.py
- Reference tests/test_cost_basis.py for test structure
