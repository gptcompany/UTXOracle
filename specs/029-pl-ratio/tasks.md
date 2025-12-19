# Tasks: P/L Ratio (Dominance)

**Input**: Design documents from `/specs/029-pl-ratio/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: REQUIRED (per constitution Principle II: Test-First Discipline)

**Organization**: Tasks are organized by functional area. This is a "Quick Win" feature with minimal phases due to low complexity.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - use for complex algorithmic tasks
- **[Story]**: Which user story this task belongs to (US1, US2)

### User Story Mapping
- **US1**: Calculate Current P/L Ratio (current window)
- **US2**: Get P/L Ratio History (daily aggregates)

---

## Phase 1: Setup (Data Models)

**Purpose**: Add data models to existing metrics_models.py

- [X] T001 Add PLDominanceZone enum to scripts/models/metrics_models.py
- [X] T002 Add PLRatioResult dataclass to scripts/models/metrics_models.py (depends on T001)
- [X] T003 Add PLRatioHistoryPoint dataclass to scripts/models/metrics_models.py (depends on T001)

**Note**: All three additions are to the same file, so they must be sequential (not parallel).

---

## Phase 2: User Story 1 - Calculate Current P/L Ratio (Priority: P1) 🎯 MVP

**Goal**: Calculate P/L ratio and dominance metrics for a configurable time window

**Independent Test**: `curl "http://localhost:8000/api/metrics/pl-ratio?window_hours=24"` returns valid JSON with pl_ratio, pl_dominance, dominance_zone

### Tests for User Story 1 ⚠️

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T004 [US1] Write TDD tests for zone classification in tests/test_pl_ratio.py (test_determine_zone_*)
- [X] T005 [US1] Write TDD tests for pl_ratio calculation in tests/test_pl_ratio.py (test_calculate_pl_ratio_*)
- [X] T006 [US1] Write TDD tests for edge cases (zero loss, zero profit+loss) in tests/test_pl_ratio.py

### Implementation for User Story 1

- [X] T007 [US1] Implement _determine_zone() helper in scripts/metrics/pl_ratio.py
- [X] T008 [US1] Implement _calculate_pl_dominance() helper in scripts/metrics/pl_ratio.py
- [X] T009 [US1] Implement calculate_pl_ratio() function in scripts/metrics/pl_ratio.py (depends on T007, T008)
- [X] T010 [US1] Add GET /api/metrics/pl-ratio endpoint to api/main.py
- [X] T011 [US1] Run tests and verify US1 passes: uv run pytest tests/test_pl_ratio.py -v

**Checkpoint**: Current P/L ratio calculation works end-to-end

---

## Phase 3: User Story 2 - Get P/L Ratio History (Priority: P2)

**Goal**: Retrieve daily P/L ratio history for trend analysis

**Independent Test**: `curl "http://localhost:8000/api/metrics/pl-ratio/history?days=30"` returns array of daily points

### Tests for User Story 2 ⚠️

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T012 [US2] Write TDD tests for history function in tests/test_pl_ratio.py (test_get_pl_ratio_history_*)

### Implementation for User Story 2

- [X] T013 [US2] Implement get_pl_ratio_history() function in scripts/metrics/pl_ratio.py
- [X] T014 [US2] Add GET /api/metrics/pl-ratio/history endpoint to api/main.py
- [X] T015 [US2] Run tests and verify US2 passes: uv run pytest tests/test_pl_ratio.py -v

**Checkpoint**: P/L ratio history retrieval works end-to-end

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

- [X] T016 Run full test suite: uv run pytest tests/test_pl_ratio.py -v --cov=scripts/metrics/pl_ratio
- [X] T017 Verify coverage >= 80%: uv run pytest --cov-report=term-missing (97% achieved)
- [X] T018 Run linter and formatter: ruff check scripts/metrics/pl_ratio.py && ruff format scripts/metrics/pl_ratio.py
- [ ] T019 Validate quickstart.md examples work manually

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies - start immediately
- **Phase 2 (US1)**: Depends on Phase 1 completion
- **Phase 3 (US2)**: Depends on Phase 1 completion (can run in parallel with US1 if desired)
- **Phase 4 (Polish)**: Depends on US1 and US2 completion

### User Story Dependencies

- **US1 (Current Ratio)**: Depends on data models (Phase 1)
- **US2 (History)**: Depends on data models (Phase 1), can run parallel to US1

### Within Each User Story

1. Tests MUST be written FIRST (RED phase)
2. Verify tests FAIL before implementation
3. Implement minimal code (GREEN phase)
4. Run tests to confirm pass
5. Refactor if needed

### Parallel Opportunities

Limited due to single-file additions, but:
- US1 and US2 tests can be written in parallel (different test functions)
- US1 and US2 API endpoints could be added in parallel (if using separate functions)

---

## Parallel Example: User Story Implementation

```bash
# After Phase 1 (Setup) completes, both user stories can proceed:

# US1 branch:
Task: "Write TDD tests for zone classification in tests/test_pl_ratio.py"
# verify tests fail
Task: "Implement _determine_zone() helper in scripts/metrics/pl_ratio.py"
# etc.

# US2 branch (if parallel):
Task: "Write TDD tests for history function in tests/test_pl_ratio.py"
# verify tests fail
Task: "Implement get_pl_ratio_history() function in scripts/metrics/pl_ratio.py"
# etc.
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (data models)
2. Complete Phase 2: US1 (current ratio calculation)
3. **STOP and VALIDATE**: Test P/L ratio endpoint independently
4. Deploy if ready - history can be added later

### Full Implementation

1. Phase 1: Setup → Data models ready
2. Phase 2: US1 → Current ratio works
3. Phase 3: US2 → History works
4. Phase 4: Polish → Tests pass, coverage verified

### Estimated Effort

- Phase 1: 15 minutes
- Phase 2 (US1): 30-45 minutes
- Phase 3 (US2): 20-30 minutes
- Phase 4: 10-15 minutes
- **Total**: 1-2 hours (matches spec estimate)

---

## Notes

- All tasks target existing files per plan.md structure
- Reuses spec-028 infrastructure (no new dependencies)
- TDD required per constitution Principle II
- Single module (scripts/metrics/pl_ratio.py) + model additions
- 2 API endpoints added to existing api/main.py
