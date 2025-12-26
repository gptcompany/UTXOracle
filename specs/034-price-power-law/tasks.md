# Tasks: Bitcoin Price Power Law Model

**Input**: Design documents from `/specs/034-price-power-law/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi.yaml

**Tests**: Required per constitution (Principle II: Test-First Discipline)

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - use for complex algorithmic tasks
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create file structure and shared dependencies

- [X] T001 Create api/models/ directory if not exists
- [X] T002 Create frontend/charts/ directory if not exists

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pydantic models and core algorithm that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Create Pydantic models in api/models/power_law_models.py (PowerLawModel, PowerLawPrediction, PowerLawResponse, PowerLawHistoryPoint, PowerLawHistoryResponse)
- [X] T004 Implement core algorithm in scripts/models/price_power_law.py (days_since_genesis, fit_power_law, predict_price, DEFAULT_MODEL, constants)

**Checkpoint**: Foundation ready - user story implementation can now begin ✅

---

## Phase 3: User Story 1 - Core Model & Prediction API (Priority: P1) 🎯 MVP

**Goal**: User can get fair value prediction for any date via API

**Independent Test**: `curl http://localhost:8000/api/v1/models/power-law/predict?date=2025-12-25&current_price=98500` returns prediction with zone classification

### Tests for User Story 1 ⚠️ TDD Required

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T005 [US1] Unit tests for core functions in tests/test_price_power_law.py (days_since_genesis, fit_power_law, predict_price, zone classification)
- [X] T006 [US1] API tests for GET /api/v1/models/power-law in tests/test_api_power_law.py
- [X] T007 [US1] API tests for GET /api/v1/models/power-law/predict in tests/test_api_power_law.py

### Implementation for User Story 1

- [X] T008 [US1] Implement GET /api/v1/models/power-law endpoint in api/main.py (returns current model parameters)
- [X] T009 [US1] Implement GET /api/v1/models/power-law/predict endpoint in api/main.py (returns prediction with bands and zone)
- [X] T010 [US1] Add input validation for date parameter (400 error on invalid format)
- [X] T011 [US1] Add 503 error handling when database unavailable

**Checkpoint**: User Story 1 complete - API returns model and predictions. Run: `uv run pytest tests/test_price_power_law.py tests/test_api_power_law.py -v` ✅

---

## Phase 4: User Story 2 - Historical Data & Recalibration (Priority: P2)

**Goal**: User can view historical prices with model values and trigger recalibration

**Independent Test**:
- `curl http://localhost:8000/api/v1/models/power-law/history?days=30` returns 30 data points
- `curl -X POST http://localhost:8000/api/v1/models/power-law/recalibrate` returns updated model

### Tests for User Story 2 ⚠️ TDD Required

- [X] T012 [US2] API tests for GET /api/v1/models/power-law/history in tests/test_api_power_law.py
- [X] T013 [US2] API tests for POST /api/v1/models/power-law/recalibrate in tests/test_api_power_law.py
- [X] T014 [US2] Unit test for model fitting from DuckDB data in tests/test_price_power_law.py

### Implementation for User Story 2

- [X] T015 [US2] Implement GET /api/v1/models/power-law/history endpoint in api/main.py (query daily_prices, compute fair values)
- [X] T016 [US2] Implement POST /api/v1/models/power-law/recalibrate endpoint in api/main.py (fit model from database)
- [X] T017 [US2] Add model caching with stale check (30 days) in api/main.py
- [X] T018 [US2] Add parameter validation for days query param (7-5000 range)

**Checkpoint**: User Story 2 complete - Historical data and recalibration working. All API endpoints functional. ✅

---

## Phase 5: User Story 3 - Frontend Visualization (Priority: P3)

**Goal**: User can view interactive log-log chart with power law regression

**Independent Test**: Open http://localhost:8000/power_law.html - displays chart with:
- Historical prices (scatter)
- Regression line (fair value)
- ±1σ bands
- Current zone indication

### Implementation for User Story 3

- [X] T019 [P] [US3] Create power_law_chart.js in frontend/charts/ (Plotly.js log-log chart)
- [X] T020 [P] [US3] Create power_law.html in frontend/ (standalone page with chart)
- [X] T021 [US3] Add API fetch logic to load history data in frontend/charts/power_law_chart.js
- [X] T022 [US3] Add zone coloring (green=undervalued, orange=fair, red=overvalued) in frontend/charts/power_law_chart.js
- [X] T023 [US3] Add static file serving for power_law.html in api/main.py

**Checkpoint**: User Story 3 complete - Full visualization available in browser. ✅

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [X] T024 Run full test suite and verify 80% coverage: `uv run pytest --cov=scripts/models/price_power_law --cov=api/main --cov-report=term-missing` (50 tests pass, 96% coverage)
- [X] T025 Validate quickstart.md examples work as documented (API endpoints verified via tests)
- [X] T026 Update docs/ARCHITECTURE.md with spec-034 section

**Checkpoint**: All tasks complete! ✅

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - creates directories
- **Foundational (Phase 2)**: Depends on Setup - creates shared models and core algorithm
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - US1 (Core API) → US2 (History/Recalibrate) → US3 (Visualization)
  - US2 uses endpoints from US1
  - US3 consumes history endpoint from US2
- **Polish (Phase 6)**: Depends on all user stories being complete

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD)
- Endpoints depend on core algorithm from Phase 2
- Validation/error handling after basic endpoint works
- Story complete before moving to next priority

### Parallel Opportunities

- T001 and T002 can run in parallel (different directories)
- T005, T006, T007 are in same file - must be sequential
- T019 and T020 can run in parallel (different files)

---

## Parallel Example: Phase 2 Foundational

```bash
# These CANNOT run in parallel - T004 depends on models from T003
# Run sequentially:
Task T003: "Create Pydantic models in api/models/power_law_models.py"
# Then:
Task T004: "Implement core algorithm in scripts/models/price_power_law.py"
```

## Parallel Example: User Story 3

```bash
# Launch frontend files together (different files):
Task T019: "Create power_law_chart.js in frontend/charts/"
Task T020: "Create power_law.html in frontend/"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (2 tasks)
2. Complete Phase 2: Foundational (2 tasks) - CRITICAL
3. Complete Phase 3: User Story 1 (7 tasks)
4. **STOP and VALIDATE**: Test with curl commands
5. Deploy/demo if ready - API is functional!

### Full Implementation

1. Setup + Foundational → Core infrastructure (4 tasks)
2. User Story 1 → API basics (7 tasks) → MVP deployed
3. User Story 2 → History & recalibration (7 tasks)
4. User Story 3 → Visualization (5 tasks)
5. Polish → Documentation & validation (3 tasks)

---

## Summary

| Phase | Tasks | Cumulative |
|-------|-------|------------|
| Phase 1: Setup | 2 | 2 |
| Phase 2: Foundational | 2 | 4 |
| Phase 3: US1 (MVP) | 7 | 11 |
| Phase 4: US2 | 7 | 18 |
| Phase 5: US3 | 5 | 23 |
| Phase 6: Polish | 3 | 26 |

**Total Tasks**: 26

---

## Notes

- [P] tasks = different files, no dependencies
- [E] not used - no complex algorithms requiring multi-implementation exploration (log-log regression is straightforward)
- TDD required per constitution Principle II
- Each user story independently testable via curl commands
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
