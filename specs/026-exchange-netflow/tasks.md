# Tasks: Exchange Netflow (spec-026)

**Input**: Design documents from `/specs/026-exchange-netflow/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Tests**: TDD required per plan.md (Constitution Principle II) - tests written before implementation.

**Organization**: Two user stories organized by API endpoint functionality.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - complex algorithmic tasks
- **[US1]**: User Story 1 - Current Netflow Snapshot
- **[US2]**: User Story 2 - Historical Netflow Data

### Marker Analysis

| File | Tasks | [P] Eligible |
|------|-------|--------------|
| `scripts/models/metrics_models.py` | T003, T004 | ❌ Same file |
| `tests/test_exchange_netflow.py` | T005-T011 | ❌ Same file |
| `scripts/metrics/exchange_netflow.py` | T012-T017 | ❌ Same file |
| `api/main.py` | T018, T019 | ❌ Same file |

**[E] Analysis**: No complex algorithms requiring multi-implementation exploration. Zone classification is simple conditionals; queries are standard SQL aggregates with JOIN.

---

## Phase 1: Setup

**Purpose**: Project structure verification and data validation (existing project)

- [X] T001 Verify utxo_lifecycle_full VIEW exists with required columns (address, btc_value, creation_timestamp, is_spent, spent_timestamp)
- [X] T002 Verify data/exchange_addresses.csv exists with correct schema (exchange_name, address, type) and 10 exchange addresses

---

## Phase 2: Foundational - Data Models

**Purpose**: Create data structures required by all subsequent tasks

**⚠️ CRITICAL**: Calculator and API depend on these models

- [X] T003 Add NetflowZone enum to scripts/models/metrics_models.py (STRONG_OUTFLOW, WEAK_OUTFLOW, WEAK_INFLOW, STRONG_INFLOW)
- [X] T004 Add ExchangeNetflowResult dataclass to scripts/models/metrics_models.py with all fields from data-model.md

**Checkpoint**: Data models ready - TDD test phase can begin

---

## Phase 3: User Story 1 - Current Netflow Snapshot (Priority: P1) 🎯 MVP

**Goal**: Calculate real-time exchange netflow metrics for a given time window

**Independent Test**: `curl http://localhost:8000/api/metrics/exchange-netflow` returns valid JSON with exchange_inflow, exchange_outflow, netflow, zone, confidence fields

### Tests for User Story 1 (TDD - RED Phase)

**NOTE**: Write these tests FIRST, ensure they FAIL before implementation

- [X] T005 [US1] Write test for load_exchange_addresses in tests/test_exchange_netflow.py (test_load_exchange_addresses_from_csv, test_load_exchange_addresses_file_not_found)
- [X] T006 [US1] Write tests for zone classification in tests/test_exchange_netflow.py (test_classify_netflow_zone_strong_outflow, test_classify_netflow_zone_weak_outflow, test_classify_netflow_zone_weak_inflow, test_classify_netflow_zone_strong_inflow)
- [X] T007 [US1] Write tests for inflow/outflow calculation in tests/test_exchange_netflow.py (test_calculate_exchange_inflow, test_calculate_exchange_outflow, test_calculate_netflow_positive, test_calculate_netflow_negative)
- [X] T008 [US1] Write tests for edge cases in tests/test_exchange_netflow.py (test_empty_window_handling, test_no_matched_addresses)

**Checkpoint (RED)**: All US1 tests written and failing - implementation can begin

### Implementation for User Story 1 (GREEN Phase)

- [X] T009 [US1] Implement load_exchange_addresses function in scripts/metrics/exchange_netflow.py (CSV to DuckDB table)
- [X] T010 [US1] Implement classify_netflow_zone function in scripts/metrics/exchange_netflow.py
- [X] T011 [US1] Implement calculate_exchange_inflow and calculate_exchange_outflow functions in scripts/metrics/exchange_netflow.py
- [X] T012 [US1] Implement calculate_exchange_netflow main function in scripts/metrics/exchange_netflow.py (returns ExchangeNetflowResult)
- [X] T013 [US1] Add GET /api/metrics/exchange-netflow endpoint to api/main.py with window query parameter

**Checkpoint (GREEN)**: All US1 unit tests passing - User Story 1 MVP complete

---

## Phase 4: User Story 2 - Historical Netflow Data (Priority: P2)

**Goal**: Provide historical daily netflow data for charting and moving average calculations

**Independent Test**: `curl http://localhost:8000/api/metrics/exchange-netflow/history?days=30` returns array of daily netflow values

### Tests for User Story 2 (TDD - RED Phase)

- [X] T014 [US2] Write tests for moving average calculation in tests/test_exchange_netflow.py (test_calculate_moving_average_full_window, test_calculate_moving_average_partial_window, test_calculate_moving_average_empty)
- [X] T015 [US2] Write tests for daily aggregation in tests/test_exchange_netflow.py (test_get_daily_netflow_history)

**Checkpoint (RED)**: All US2 tests written and failing

### Implementation for User Story 2 (GREEN Phase)

- [X] T016 [US2] Implement calculate_moving_average function in scripts/metrics/exchange_netflow.py
- [X] T017 [US2] Implement get_daily_netflow_history function in scripts/metrics/exchange_netflow.py
- [X] T018 [US2] Update calculate_exchange_netflow to include netflow_7d_ma and netflow_30d_ma fields
- [X] T019 [US2] Add GET /api/metrics/exchange-netflow/history endpoint to api/main.py with days query parameter

**Checkpoint (GREEN)**: All US2 tests passing - User Story 2 complete

---

## Phase 5: Polish & Validation

**Purpose**: Final verification, integration testing, and documentation

- [X] T020 Write API integration tests in tests/test_exchange_netflow.py (test_exchange_netflow_api_endpoint, test_exchange_netflow_history_api_endpoint)
- [X] T021 Run quickstart.md validation scenarios
- [X] T022 Run full test suite with coverage (target: 80%+)
- [X] T023 Validate performance requirement: netflow calculation <200ms

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup (T001 → T002)
    │
    ▼
Phase 2: Foundational (T003 → T004)
    │
    ▼
Phase 3: US1 Tests (T005 → T006 → T007 → T008) ─ RED Phase
    │
    ▼
Phase 3: US1 Implementation (T009 → T010 → T011 → T012 → T013) ─ GREEN Phase
    │
    ▼
Phase 4: US2 Tests (T014 → T015) ─ RED Phase
    │
    ▼
Phase 4: US2 Implementation (T016 → T017 → T018 → T019) ─ GREEN Phase
    │
    ▼
Phase 5: Polish (T020 → T021 → T022 → T023)
```

### Task Dependencies

| Task | Depends On | Reason |
|------|------------|--------|
| T001 | - | First task |
| T002 | T001 | Verify data source exists |
| T003 | T002 | Models after data verification |
| T004 | T003 | Dataclass uses NetflowZone enum |
| T005 | T004 | Tests import data models |
| T006-T008 | T005 | Tests in same file |
| T009 | T008 | TDD: tests must exist first |
| T010-T012 | T009 | Implementation in same file |
| T013 | T012 | Endpoint calls calculator function |
| T014-T015 | T013 | US2 tests after US1 complete |
| T016-T018 | T015 | US2 implementation |
| T019 | T018 | History endpoint after MA implemented |
| T020 | T019 | Integration tests after all endpoints |
| T021-T023 | T020 | Validation after integration tests |

### Parallel Opportunities

**Limited parallelization** due to single-file task groupings:

- T005-T008: Same file (test_exchange_netflow.py) - **Sequential**
- T009-T012: Same file (exchange_netflow.py) - **Sequential**
- T014-T015: Same file (test_exchange_netflow.py) - **Sequential**
- T016-T018: Same file (exchange_netflow.py) - **Sequential**

**No [P] markers assigned** - all tasks within each file must run sequentially.

---

## Parallel Example: This Feature

```bash
# No parallel execution available for this feature
# All tasks target overlapping files

# Execution order (strictly sequential):
T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008 → T009 → T010 →
T011 → T012 → T013 → T014 → T015 → T016 → T017 → T018 → T019 → T020 →
T021 → T022 → T023
```

---

## Implementation Strategy

### MVP Delivery (User Story 1 Only)

1. Phase 1: Verify VIEW and CSV exist
2. Phase 2: Create NetflowZone enum + ExchangeNetflowResult dataclass
3. Phase 3 Tests: Write failing tests (RED)
4. Phase 3 Impl: Implement loader, classifier, calculator, API (GREEN)
5. **STOP and VALIDATE**: Test via `curl http://localhost:8000/api/metrics/exchange-netflow`
6. Deploy/demo if ready - MVP complete with single endpoint

### Incremental Delivery

1. Setup + Foundational → Data models ready
2. User Story 1 (T005-T013) → Current netflow API → **MVP!**
3. User Story 2 (T014-T019) → Historical netflow + moving averages
4. Polish (T020-T023) → Full validation

### TDD Cycle Per Story

```bash
# US1 - RED Phase
uv run pytest tests/test_exchange_netflow.py -v  # Must FAIL

# US1 - GREEN Phase (after T009-T013)
uv run pytest tests/test_exchange_netflow.py -v  # Must PASS

# US2 - RED Phase (after T014-T015)
uv run pytest tests/test_exchange_netflow.py -v  # New tests FAIL

# US2 - GREEN Phase (after T016-T019)
uv run pytest tests/test_exchange_netflow.py -v  # All PASS
```

---

## Notes

- **No [P] markers**: All task groups edit single files
- **No [E] markers**: No complex algorithms (zone classification is simple conditionals)
- **TDD enforced**: Tests must fail before implementation (Constitution Principle II)
- **Two user stories**: US1 (current netflow) is MVP, US2 (history/MA) adds charting support
- Commit after each task
- Verify tests fail before implementing
- Target: 80%+ coverage, <200ms query latency (validated by T023)
- Exchange address list uses existing CSV at `data/exchange_addresses.csv`
