# Tasks: Binary CDD Indicator

**Input**: Design documents from `/specs/027-binary-cdd/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.yaml, quickstart.md

**Tests**: TDD tests are included as specified in spec.md and plan.md (Constitution Principle II: Test-First Discipline)

**Organization**: Single user story feature - delivers statistical significance flag for CDD events.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - use for complex algorithmic tasks
- **[Story]**: Which user story this task belongs to (e.g., US1)

---

## Phase 1: Setup

**Purpose**: Project structure verification and TDD test file creation

- [X] T001 Verify spec-021 dependency available (cdd_vdd.py exists in scripts/metrics/)
- [X] T002 Verify DuckDB utxo_lifecycle_full table schema accessible

---

## Phase 2: Foundational (TDD - RED Phase)

**Purpose**: Write failing tests BEFORE implementation (Constitution Principle II)

**⚠️ CRITICAL**: Tests MUST fail before proceeding to implementation

- [X] T003 Create test file tests/test_binary_cdd.py with test fixtures
- [X] T004 Write test_calculate_binary_cdd_normal_case in tests/test_binary_cdd.py
- [X] T005 Write test_calculate_binary_cdd_significant_event in tests/test_binary_cdd.py
- [X] T006 Write test_calculate_binary_cdd_insufficient_data in tests/test_binary_cdd.py
- [X] T007 Write test_calculate_binary_cdd_zero_std_deviation in tests/test_binary_cdd.py
- [X] T008 Write test_binary_cdd_api_endpoint in tests/test_binary_cdd.py
- [X] T009 Run tests and verify all FAIL (RED phase complete)

**Checkpoint**: All tests written and failing - ready for implementation ✅

---

## Phase 3: User Story 1 - Binary CDD API (Priority: P1) 🎯 MVP

**Goal**: Expose Binary CDD indicator via GET /api/metrics/binary-cdd endpoint

**Independent Test**: `curl http://localhost:8000/api/metrics/binary-cdd` returns valid JSON with binary_cdd field

### Implementation for User Story 1

- [X] T010 [P] [US1] Add BinaryCDDResult dataclass to scripts/models/metrics_models.py
- [X] T011 [US1] Create calculate_binary_cdd() function in scripts/metrics/binary_cdd.py
- [X] T012 [US1] Add BinaryCDDResponse Pydantic model to api/main.py
- [X] T013 [US1] Implement GET /api/metrics/binary-cdd endpoint in api/main.py
- [X] T014 [US1] Run tests and verify all PASS (GREEN phase complete)

**Checkpoint**: Binary CDD endpoint functional and all tests passing ✅

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and validation

- [X] T015 Run quickstart.md validation (curl commands from quickstart.md)
- [X] T016 Run ruff check and ruff format on new/modified files
- [X] T017 Verify API matches contracts/api.yaml specification

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - verification only
- **Foundational (Phase 2)**: Depends on Setup - writes all tests first (TDD RED)
- **User Story 1 (Phase 3)**: Depends on Foundational - implements to pass tests (TDD GREEN)
- **Polish (Phase 4)**: Depends on User Story 1 completion

### Task Dependencies Within Phases

**Phase 2 (Tests)**:
- T003 → T004, T005, T006, T007, T008 (test file must exist first)
- T004-T008 sequential (same file - no [P] marker)
- T009 depends on T004-T008

**Phase 3 (Implementation)**:
- T010 can run in parallel (different file) - [P] marker
- T011 depends on T010 (uses BinaryCDDResult)
- T012 depends on T010 (uses BinaryCDDResult)
- T013 depends on T011, T012 (uses both)
- T014 depends on T013

### File Edit Constraints (No [P] for same file)

| File | Tasks |
|------|-------|
| tests/test_binary_cdd.py | T003, T004, T005, T006, T007, T008 (sequential) |
| scripts/models/metrics_models.py | T010 |
| scripts/metrics/binary_cdd.py | T011 |
| api/main.py | T012, T013 (sequential) |

---

## Parallel Example: Phase 3 Start

```bash
# After T009 (tests failing), T010 can run in parallel with waiting for nothing
Task: "Add BinaryCDDResult dataclass to scripts/models/metrics_models.py" [P]

# Then T011 and T012 can potentially overlap (different files):
# But T012 depends on T010 completing, so limited parallelism
```

---

## Implementation Strategy

### TDD Flow (RED → GREEN)

1. **Phase 1**: Verify dependencies exist
2. **Phase 2**: Write all tests (T003-T008), verify they FAIL (T009)
3. **Phase 3**: Implement minimal code to pass tests (T010-T013), verify PASS (T014)
4. **Phase 4**: Polish and validate

### MVP Definition

**MVP = Phase 1 + Phase 2 + Phase 3**

Delivers:
- `GET /api/metrics/binary-cdd?threshold=2.0&window=365`
- Returns: cdd_today, cdd_mean, cdd_std, cdd_zscore, cdd_percentile, binary_cdd, etc.
- All tests passing

### Estimated Effort

| Phase | Tasks | Estimate |
|-------|-------|----------|
| Setup | T001-T002 | 5 min |
| Foundational (TDD) | T003-T009 | 30 min |
| Implementation | T010-T014 | 45 min |
| Polish | T015-T017 | 10 min |
| **Total** | 17 tasks | ~90 min |

---

## Notes

- Single user story feature - simple linear execution
- TDD discipline enforced (Constitution Principle II)
- No [P] markers on same-file tasks to prevent conflicts
- T010 is the only parallelizable implementation task (different file)
- Formula: `z = (cdd_today - mean) / std`, `binary = 1 if z >= threshold else 0`
- Default threshold: 2.0 sigma, window: 365 days
- Edge cases: insufficient_data=true when < 30 days history, zscore=null when std=0
