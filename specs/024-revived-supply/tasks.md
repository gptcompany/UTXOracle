# Tasks: Revived Supply (spec-024)

**Input**: Design documents from `/specs/024-revived-supply/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Tests**: TDD required per plan.md - tests written before implementation.

**Organization**: Single user story feature (Calculate Revived Supply Metrics).

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - complex algorithmic tasks
- **[US1]**: User Story 1 - Revived Supply Calculation

### Marker Analysis

| File | Tasks | [P] Eligible |
|------|-------|--------------|
| `scripts/models/metrics_models.py` | T002, T003 | ❌ Same file |
| `tests/test_revived_supply.py` | T004, T005 | ❌ Same file |
| `scripts/metrics/revived_supply.py` | T006, T007 | ❌ Same file |
| `api/main.py` | T008 | ❌ Depends on T007 |

**[E] Analysis**: No complex algorithms requiring multi-implementation exploration. Zone classification is simple conditionals; query is standard SQL aggregate.

---

## Phase 1: Setup

**Purpose**: Project structure verification (existing project)

- [X] T001 Verify utxo_lifecycle_full VIEW exists with required columns (btc_value, age_days, is_spent, spent_timestamp)

---

## Phase 2: Foundational - Data Models

**Purpose**: Create data structures required by all subsequent tasks

**⚠️ CRITICAL**: Calculator and API depend on these models

- [X] T002 Add RevivedZone enum to scripts/models/metrics_models.py
- [X] T003 Add RevivedSupplyResult dataclass to scripts/models/metrics_models.py

**Checkpoint**: Data models ready - TDD test phase can begin

---

## Phase 3: User Story 1 - Revived Supply Calculation (Priority: P1) 🎯 MVP

**Goal**: Track dormant coins being spent to signal long-term holder behavior changes

**Independent Test**: `curl http://localhost:8000/api/metrics/revived-supply` returns valid JSON with revived_1y, zone, confidence fields

### Tests for User Story 1 (TDD - RED Phase)

**NOTE**: Write these tests FIRST, ensure they FAIL before implementation

- [X] T004 [US1] Write unit tests for zone classification in tests/test_revived_supply.py (test_classify_revived_zone_dormant, test_classify_revived_zone_normal, test_classify_revived_zone_elevated, test_classify_revived_zone_spike)
- [X] T005 [US1] Write unit tests for calculator in tests/test_revived_supply.py (test_calculate_revived_supply_basic, test_revived_supply_with_thresholds, test_empty_window_handling)

**Checkpoint (RED)**: All tests written and failing - implementation can begin

### Implementation for User Story 1 (GREEN Phase)

- [X] T006 [US1] Implement classify_revived_zone function in scripts/metrics/revived_supply.py
- [X] T007 [US1] Implement calculate_revived_supply_signal function in scripts/metrics/revived_supply.py
- [X] T008 [US1] Add GET /api/metrics/revived-supply endpoint to api/main.py with threshold and window query parameters

**Checkpoint (GREEN)**: All unit tests passing - User Story 1 complete

---

## Phase 4: Polish & Validation

**Purpose**: Final verification and documentation

- [X] T009 Write API integration test in tests/test_revived_supply.py (test_revived_supply_api_endpoint)
- [X] T010 Run quickstart.md validation scenarios
- [X] T011 Run full test suite with coverage (target: 80%+)
- [X] T012 Validate performance requirement: revived supply calculation <100ms (achieved: 7.07ms)

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup
    │
    ▼
Phase 2: Foundational (T002 → T003)
    │
    ▼
Phase 3: US1 Tests (T004 → T005) ─ RED Phase
    │
    ▼
Phase 3: US1 Implementation (T006 → T007 → T008) ─ GREEN Phase
    │
    ▼
Phase 4: Polish (T009 → T010 → T011 → T012)
```

### Task Dependencies

| Task | Depends On | Reason |
|------|------------|--------|
| T002 | T001 | VIEW must exist |
| T003 | T002 | Dataclass uses RevivedZone enum |
| T004 | T003 | Tests import RevivedZone |
| T005 | T003 | Tests import RevivedSupplyResult |
| T006 | T004 | TDD: zone tests must exist first |
| T007 | T005, T006 | TDD: calculator tests must exist; depends on zone function |
| T008 | T007 | Endpoint calls calculate_revived_supply_signal |
| T009 | T008 | API test requires endpoint |
| T010 | T008 | Quickstart requires working API |
| T011 | T009 | Full suite after API test added |
| T012 | T011 | Performance validation after tests pass |

### Parallel Opportunities

**Limited parallelization** due to single-file task groupings:

- T004 and T005: Same file (test_revived_supply.py) - **Sequential**
- T006 and T007: Same file (revived_supply.py) - **Sequential**

**No [P] markers assigned** - all tasks within each file must run sequentially.

---

## Parallel Example: This Feature

```bash
# No parallel execution available for this feature
# All tasks target overlapping files

# Execution order (strictly sequential):
T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008 → T009 → T010 → T011 → T012
```

---

## Implementation Strategy

### MVP Delivery (User Story 1)

1. ✅ Phase 1: Verify VIEW exists
2. ✅ Phase 2: Create RevivedZone enum + RevivedSupplyResult dataclass
3. ✅ Phase 3 Tests: Write failing tests (RED)
4. ✅ Phase 3 Impl: Implement calculator + API (GREEN)
5. **STOP and VALIDATE**: Test via curl/pytest
6. Deploy/demo if ready

### TDD Cycle Per Task

```bash
# T004-T005: RED Phase
uv run pytest tests/test_revived_supply.py -v  # Must FAIL

# T006-T007: GREEN Phase
uv run pytest tests/test_revived_supply.py -v  # Must PASS

# T008: Extend GREEN
uv run pytest tests/test_revived_supply.py -v  # All PASS
```

---

## Notes

- **No [P] markers**: All task groups edit single files
- **No [E] markers**: No complex algorithms (zone classification is simple conditionals)
- **TDD enforced**: Tests (T004-T005) must fail before implementation (T006-T007)
- **Single user story**: Entire feature is one atomic deliverable
- Commit after each task
- Verify tests fail before implementing
- Target: 80%+ coverage, <100ms query latency (validated by T012)
