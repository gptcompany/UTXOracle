# Tasks: NUPL Oscillator (spec-022)

**Input**: Design documents from `/specs/022-nupl-oscillator/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: TDD workflow requested in spec - tests written before implementation.

**Organization**: Single user story (API endpoint delivery) with TDD phases.

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger (not used - simple implementation)

---

## Phase 1: Setup (Data Models)

**Purpose**: Add data structures to existing models file

- [X] T001 Add NUPLZone enum to scripts/models/metrics_models.py
- [X] T002 Add NUPLResult dataclass to scripts/models/metrics_models.py (after NUPLZone)

**Checkpoint**: Data models ready for use ✅

---

## Phase 2: Tests (TDD RED)

**Purpose**: Write failing tests FIRST per TDD discipline

- [X] T003 Create tests/test_nupl.py with test_classify_nupl_zone_capitulation()
- [X] T004 Add test_classify_nupl_zone_hope_fear() to tests/test_nupl.py
- [X] T005 Add test_classify_nupl_zone_optimism() to tests/test_nupl.py
- [X] T006 Add test_classify_nupl_zone_belief() to tests/test_nupl.py
- [X] T007 Add test_classify_nupl_zone_euphoria() to tests/test_nupl.py
- [X] T008 Add test_nupl_result_validation() to tests/test_nupl.py
- [X] T009 Add test_calculate_nupl_signal_integration() to tests/test_nupl.py

**Checkpoint**: All 7 tests exist and FAIL (RED phase) ✅

---

## Phase 3: Implementation (TDD GREEN)

**Purpose**: Implement minimal code to pass tests

- [X] T010 Create scripts/metrics/nupl.py with classify_nupl_zone() function
- [X] T011 Add calculate_nupl_signal() orchestrator to scripts/metrics/nupl.py
- [X] T012 Add structured logging to scripts/metrics/nupl.py
- [X] T013 Run tests: `uv run pytest tests/test_nupl.py -v` (must pass)

**Checkpoint**: All tests pass (GREEN phase) ✅

---

## Phase 4: API Integration

**Purpose**: Expose NUPL via REST endpoint

- [X] T014 Add NUPLResponse Pydantic model to api/main.py
- [X] T015 Add GET /api/metrics/nupl endpoint to api/main.py
- [X] T016 Add test_api_nupl_endpoint() to tests/test_nupl.py
- [X] T017 Run full test suite: `uv run pytest tests/test_nupl.py -v`

**Checkpoint**: API endpoint functional ✅

---

## Phase 5: Polish & Validation

**Purpose**: Final verification and documentation

- [X] T018 Run quickstart.md validation (curl endpoint, verify response)
- [X] T019 Run ruff linting: `ruff check scripts/metrics/nupl.py`
- [X] T020 Update docs/ARCHITECTURE.md if needed (spec-022 status)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies - models added to existing file
- **Phase 2 (Tests)**: Depends on Phase 1 (models must exist for import)
- **Phase 3 (Implementation)**: Depends on Phase 2 (tests must exist to verify)
- **Phase 4 (API)**: Depends on Phase 3 (nupl module must exist)
- **Phase 5 (Polish)**: Depends on Phase 4 (endpoint must be functional)

### Task Dependencies Within Phases

- **T001 → T002**: NUPLZone enum must exist before NUPLResult uses it
- **T003-T009**: Sequential (same file, no [P] marker)
- **T010 → T011 → T012**: classify_nupl_zone before orchestrator
- **T014 → T015**: Response model before endpoint

### Parallel Opportunities

Limited parallelism due to TDD sequential nature:
- T003-T009 could be parallelized if split into separate test files (not recommended for this scope)

---

## Implementation Strategy

### TDD Workflow

1. **Phase 1**: Add models (15 min)
2. **Phase 2**: Write all tests - verify they FAIL (20 min)
3. **Phase 3**: Implement - verify tests PASS (25 min)
4. **Phase 4**: Add API endpoint and API test (15 min)
5. **Phase 5**: Validate and polish (10 min)

**Total**: ~1.5 hours

### Validation Commands

```bash
# After Phase 2 (tests should FAIL)
uv run pytest tests/test_nupl.py -v --tb=short
# Expected: 7 failures (ModuleNotFoundError or AssertionError)

# After Phase 3 (tests should PASS)
uv run pytest tests/test_nupl.py -v
# Expected: All pass

# After Phase 4 (full validation)
uv run pytest tests/test_nupl.py -v --cov=scripts/metrics/nupl

# API validation
curl http://localhost:8000/api/metrics/nupl | jq
```

---

## Notes

- T001, T002 edit same file (metrics_models.py) - must be sequential
- T003-T009 edit same file (test_nupl.py) - must be sequential
- T010-T012 edit same file (nupl.py) - must be sequential
- T014-T016 edit same file (main.py) - must be sequential
- No [E] markers needed - straightforward implementation
- Reuses existing realized_metrics.py infrastructure (no new dependencies)
