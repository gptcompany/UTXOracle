# Tasks: PRO Risk Metric (spec-033)

**Input**: Design documents from `/specs/033-pro-risk-metric/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi.yaml

**Tests**: The spec mentions "Unit tests" in implementation files. TDD workflow per Constitution II.

**Organization**: Tasks grouped by user story for independent implementation.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - complex algorithmic tasks
- **[Story]**: Which user story (US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and database schema

- [X] T001 Create DuckDB schema for risk_percentiles table in scripts/metrics/init_risk_db.py
- [X] T002 Create DuckDB schema for pro_risk_daily table in scripts/metrics/init_risk_db.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core components that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [P] Implement Puell Multiple calculation in scripts/metrics/puell_multiple.py (requires fee data from electrs)
- [X] T004 [P] Implement percentile normalization helper with winsorization in scripts/metrics/pro_risk.py
- [X] T005 [P] Define component weights and zone thresholds constants in scripts/metrics/pro_risk.py
- [X] T006 Generate 4-year historical percentile bootstrap data for all 6 metrics in scripts/metrics/bootstrap_percentiles.py

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Core PRO Risk Calculation (Priority: P1) 🎯 MVP

**Goal**: Calculate composite 0-1 PRO Risk metric from 6 on-chain signals

**Independent Test**: `python -m scripts.metrics.pro_risk -d 2025/12/25` outputs valid JSON with value, zone, components

### Tests for User Story 1

- [X] T007 [P] [US1] Write failing test for normalize_to_percentile function in tests/test_pro_risk.py
- [X] T008 [P] [US1] Write failing test for classify_zone function in tests/test_pro_risk.py
- [X] T009 [P] [US1] Write failing test for calculate_pro_risk function in tests/test_pro_risk.py
- [X] T010 [P] [US1] Write failing test for calculate_confidence function in tests/test_pro_risk.py

### Implementation for User Story 1

- [X] T011 [P] [US1] Create ProRiskResult dataclass in scripts/metrics/pro_risk.py
- [X] T012 [P] [US1] Create ComponentScore dataclass in scripts/metrics/pro_risk.py
- [X] T013 [E] [US1] Implement normalize_to_percentile with 4-year window and 2% winsorization in scripts/metrics/pro_risk.py
- [X] T014 [US1] Implement classify_zone function (extreme_fear → extreme_greed) in scripts/metrics/pro_risk.py
- [X] T015 [US1] Implement calculate_confidence function in scripts/metrics/pro_risk.py
- [X] T016 [E] [US1] Implement calculate_pro_risk main aggregation function in scripts/metrics/pro_risk.py
- [X] T017 [US1] Add component metric fetchers (fetch MVRV-Z, SOPR, NUPL, Reserve Risk, HODL Waves from existing modules) in scripts/metrics/pro_risk.py
- [X] T018 [US1] Add CLI interface with -d flag and --json output in scripts/metrics/pro_risk.py
- [X] T019 [US1] Run tests and verify all US1 tests pass

**Checkpoint**: User Story 1 complete - PRO Risk can be calculated via CLI

---

## Phase 4: User Story 2 - REST API Access (Priority: P2)

**Goal**: Expose PRO Risk via REST API endpoints (/api/v1/risk/pro, /risk/pro/zones)

**Independent Test**: `curl http://localhost:8000/api/v1/risk/pro` returns valid ProRiskResponse JSON

### Tests for User Story 2

- [X] T020 [P] [US2] Write failing test for GET /api/v1/risk/pro endpoint in tests/test_api_risk.py
- [X] T021 [P] [US2] Write failing test for GET /api/v1/risk/pro/zones endpoint in tests/test_api_risk.py

### Implementation for User Story 2

- [X] T022 [P] [US2] Create ProRiskResponseAPI Pydantic model in api/models/risk_models.py
- [X] T023 [P] [US2] Create ProRiskComponentAPI Pydantic model in api/models/risk_models.py
- [X] T024 [US2] Create risk router with GET /risk/pro endpoint in api/routes/risk.py
- [X] T025 [US2] Add GET /risk/pro/zones endpoint returning zone definitions in api/routes/risk.py
- [X] T026 [US2] Register risk router in api/main.py
- [X] T027 [US2] Run tests and verify all US2 tests pass

**Checkpoint**: User Story 2 complete - PRO Risk accessible via REST API

---

## Phase 5: User Story 3 - Historical Analysis (Priority: P3)

**Goal**: View PRO Risk history for date ranges and analyze zone trends

**Independent Test**: `curl "http://localhost:8000/api/v1/risk/pro/history?start_date=2025-01-01&end_date=2025-12-25"` returns array of historical values

### Tests for User Story 3

- [X] T028 [P] [US3] Write failing test for GET /api/v1/risk/pro/history endpoint in tests/test_api_risk.py
- [X] T029 [P] [US3] Write failing test for historical percentile context (30d/1y) in tests/test_pro_risk.py

### Implementation for User Story 3

- [X] T030 [US3] Add calculate_historical_context function (30d/1y percentiles) in scripts/metrics/pro_risk.py
- [X] T031 [US3] Add GET /risk/pro/history endpoint with start_date, end_date, granularity params in api/routes/risk.py
- [X] T032 [US3] Add storage/retrieval for pro_risk_daily table in scripts/metrics/pro_risk.py
- [X] T033 [US3] Run tests and verify all US3 tests pass

**Checkpoint**: User Story 3 complete - historical analysis available

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validation, documentation, cleanup

- [X] T034 [P] Run full test suite: `uv run pytest tests/test_pro_risk.py tests/test_api_risk.py -v`
- [X] T035 [P] Run linting: `ruff check scripts/metrics/pro_risk.py scripts/metrics/puell_multiple.py api/routes/risk.py`
- [X] T036 [P] Update docs/ARCHITECTURE.md with spec-033 documentation
- [ ] T037 Validate quickstart.md examples work end-to-end
- [ ] T038 Backtest validation against 2017, 2021, 2022 cycle tops/bottoms

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Phase 2 completion
  - US1 → US2 → US3 (sequential priority order)
- **Polish (Phase 6)**: Depends on US1, optionally US2/US3

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 - No dependencies on other stories
- **User Story 2 (P2)**: Depends on US1 (needs calculate_pro_risk function)
- **User Story 3 (P3)**: Depends on US1 (needs core calculation), independent of US2

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Dataclasses before functions
- Core implementation before CLI/API
- Story complete before moving to next priority

### Parallel Opportunities

- T003, T004, T005 can run in parallel (Phase 2 - different files)
- T007, T008, T009, T010 can run in parallel (US1 tests)
- T011, T012 can run in parallel (US1 dataclasses)
- T020, T021 can run in parallel (US2 tests)
- T022, T023 can run in parallel (US2 models)
- T028, T029 can run in parallel (US3 tests)
- T034, T035, T036 can run in parallel (Phase 6)

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests together (TDD Red phase) - T007-T010:
Task: "Write failing test for normalize_to_percentile function in tests/test_pro_risk.py"
Task: "Write failing test for classify_zone function in tests/test_pro_risk.py"
Task: "Write failing test for calculate_pro_risk function in tests/test_pro_risk.py"
Task: "Write failing test for calculate_confidence function in tests/test_pro_risk.py"

# Launch US1 dataclasses together - T011-T012:
Task: "Create ProRiskResult dataclass in scripts/metrics/pro_risk.py"
Task: "Create ComponentScore dataclass in scripts/metrics/pro_risk.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T006)
3. Complete Phase 3: User Story 1 (T007-T019)
4. **STOP and VALIDATE**: `python -m scripts.metrics.pro_risk -d 2025/12/25`
5. Deploy/demo CLI tool

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test via CLI → MVP ready!
3. Add User Story 2 → Test via API → REST access ready
4. Add User Story 3 → Test history endpoint → Full feature complete
5. Each story adds value without breaking previous stories

### [E] Tasks (Alpha-Evolve)

- **T013**: normalize_to_percentile - Complex statistical operation with winsorization
- **T016**: calculate_pro_risk - Core aggregation algorithm with weighted components

---

## Notes

- [P] tasks = different files, no dependencies
- [E] tasks = complex algorithms triggering alpha-evolve
- [Story] label maps task to specific user story
- TDD: Tests (RED) → Implementation (GREEN) → Refactor
- Commit after each logical group
- Constitution II requires test-first discipline
- All 6 component metrics already exist in spec-007/016/017/018

---

## Summary

| Phase | Tasks | Purpose |
|-------|-------|---------|
| Phase 1: Setup | T001-T002 | Database schema |
| Phase 2: Foundational | T003-T006 | Puell Multiple, normalization, bootstrap data |
| Phase 3: US1 - Core Calculation | T007-T019 | MVP: CLI PRO Risk calculation |
| Phase 4: US2 - REST API | T020-T027 | API endpoints |
| Phase 5: US3 - Historical | T028-T033 | History and trends |
| Phase 6: Polish | T034-T038 | Tests, docs, validation |

**Total Tasks**: 38
**MVP Scope**: T001-T019 (19 tasks)
**Parallel Opportunities**: 7 groups identified
