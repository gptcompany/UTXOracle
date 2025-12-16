# Tasks: STH/LTH Cost Basis (spec-023)

**Input**: Design documents from `/specs/023-cost-basis-cohorts/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: TDD approach specified in plan.md - tests MUST be written first and fail before implementation.

**Organization**: Single user story (Cost Basis Calculation) - straightforward feature with clear implementation path.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - use for complex algorithmic tasks
- **[Story]**: Which user story this task belongs to (US1 = Cost Basis Metrics)

---

## Phase 1: Setup

**Purpose**: Verify existing infrastructure is ready for new metric

- [x] T001 Verify `utxo_lifecycle_full` VIEW exists and has required columns in DuckDB database

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add data model that all subsequent tasks depend on

**⚠️ CRITICAL**: The `CostBasisResult` dataclass must be created before tests or implementation can proceed.

- [x] T002 Add `CostBasisResult` dataclass to scripts/models/metrics_models.py following NUPLResult pattern

**Checkpoint**: Foundation ready - User Story 1 implementation can now begin

---

## Phase 3: User Story 1 - Cost Basis Metrics (Priority: P1) 🎯 MVP

**Goal**: Calculate weighted average cost basis for STH/LTH cohorts and expose via API

**Independent Test**:
- `uv run pytest tests/test_cost_basis.py -v` passes
- `curl http://localhost:8000/api/metrics/cost-basis` returns valid JSON with all fields

### Tests for User Story 1 (TDD - Write FIRST, Ensure They FAIL)

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T003 [US1] Write test_calculate_sth_cost_basis_basic in tests/test_cost_basis.py
- [x] T004 [US1] Write test_calculate_lth_cost_basis_basic in tests/test_cost_basis.py
- [x] T005 [US1] Write test_calculate_total_cost_basis in tests/test_cost_basis.py
- [x] T006 [US1] Write test_cost_basis_mvrv_calculation in tests/test_cost_basis.py
- [x] T007 [US1] Write test_zero_cost_basis_mvrv_returns_zero in tests/test_cost_basis.py
- [x] T008 [US1] Write test_empty_cohort_handling in tests/test_cost_basis.py
- [x] T009 [US1] Write test_calculate_cost_basis_signal_full in tests/test_cost_basis.py
- [x] T010 [US1] Write test_cost_basis_api_endpoint in tests/test_cost_basis.py

**Checkpoint**: All tests written and failing (RED phase complete)

### Implementation for User Story 1 (Make Tests Pass - GREEN)

- [x] T011 [US1] Create scripts/metrics/cost_basis.py with module docstring and imports
- [x] T012 [US1] Implement calculate_sth_cost_basis() function in scripts/metrics/cost_basis.py
- [x] T013 [US1] Implement calculate_lth_cost_basis() function in scripts/metrics/cost_basis.py
- [x] T014 [US1] Implement calculate_total_cost_basis() function in scripts/metrics/cost_basis.py
- [x] T015 [US1] Implement calculate_cost_basis_mvrv() helper function in scripts/metrics/cost_basis.py
- [x] T016 [US1] Implement calculate_cost_basis_signal() orchestrator function in scripts/metrics/cost_basis.py
- [x] T017 [US1] Add GET /api/metrics/cost-basis endpoint to api/main.py

**Checkpoint**: All tests passing (GREEN phase complete) ✅

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Verify integration and documentation

- [x] T018 [P] Run full test suite: `uv run pytest tests/test_cost_basis.py -v --cov=scripts/metrics/cost_basis --cov-report=term-missing` (88% coverage)
- [x] T019 [P] Run linter and formatter: `ruff check scripts/metrics/cost_basis.py && ruff format scripts/metrics/cost_basis.py`
- [x] T020 Validate quickstart.md examples work correctly
- [x] T021 Verify API endpoint matches contracts/api.yaml schema

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - verify existing infrastructure
- **Foundational (Phase 2)**: Depends on Phase 1 - BLOCKS User Story 1
- **User Story 1 (Phase 3)**: Depends on Phase 2 completion
- **Polish (Phase 4)**: Depends on Phase 3 completion

### Within User Story 1

**TDD Sequence (MUST follow order):**
1. T003-T010: Write ALL tests FIRST (ensure they FAIL)
2. T011: Create module file
3. T012-T015: Implement calculation functions (make tests pass incrementally)
4. T016: Implement orchestrator function
5. T017: Add API endpoint
6. T018-T021: Polish and verify

### Parallel Opportunities

- T003-T010: All test functions written in single file (sequential within same file)
- T018, T019: Can run in parallel (different operations)
- T012, T013, T014: Technically parallelizable but same file - write sequentially

---

## Parallel Example: Phase 4

```bash
# Launch polish tasks in parallel:
Task: "Run full test suite with coverage"
Task: "Run linter and formatter"
```

---

## Implementation Strategy

### MVP (All-in-One for This Feature)

1. Complete Phase 1: Setup (verify VIEW)
2. Complete Phase 2: Foundational (add dataclass)
3. Complete Phase 3: User Story 1 (TDD tests → implementation → API)
4. **STOP and VALIDATE**: All tests pass, API returns correct data
5. Complete Phase 4: Polish

### Estimated Effort

Per spec-023: 2-3 hours total

| Phase | Est. Time |
|-------|-----------|
| Setup | 5 min |
| Foundational | 15 min |
| US1 Tests | 30 min |
| US1 Implementation | 60 min |
| US1 API | 15 min |
| Polish | 15 min |
| **Total** | ~2.5 hours |

---

## Notes

- [P] tasks = different files, no dependencies
- [US1] = Cost Basis Metrics user story (only story for this feature)
- TDD is mandatory per Constitution Principle II
- Follow existing patterns from `scripts/metrics/nupl.py` and `scripts/metrics/realized_metrics.py`
- All tests must FAIL before implementation begins
- Commit after each phase or logical group
- 80%+ test coverage required per plan.md constraints
