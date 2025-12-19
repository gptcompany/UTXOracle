# Tasks: Net Realized Profit/Loss (spec-028)

**Input**: Design documents from `/specs/028-net-realized-pnl/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: TDD tests are included as specified in spec.md (Files section mentions `tests/test_net_realized_pnl.py`).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - use for complex algorithmic tasks
- **[Story]**: Which user story this task belongs to (US1, US2)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify existing infrastructure and create module structure

- [x] T001 Verify `utxo_lifecycle_full` VIEW exists with required columns (creation_price_usd, spent_price_usd, btc_value, is_spent, spent_timestamp) in DuckDB
- [x] T002 Create empty module file scripts/metrics/net_realized_pnl.py with module docstring

---

## Phase 2: Foundational (Data Models)

**Purpose**: Create data models that BOTH user stories depend on

**⚠️ CRITICAL**: No user story work can begin until data models are complete

- [x] T003 Add NetRealizedPnLResult dataclass to scripts/models/metrics_models.py per data-model.md specification
- [x] T004 Add NetRealizedPnLHistoryPoint dataclass to scripts/models/metrics_models.py per data-model.md specification
- [x] T005 Add NetRealizedPnLResponse Pydantic model to api/main.py imports section
- [x] T006 Add NetRealizedPnLHistoryResponse Pydantic model to api/main.py imports section

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Calculate Net Realized P/L (Priority: P1) 🎯 MVP

**Goal**: Calculate Net Realized P/L for spent UTXOs within a configurable time window

**Independent Test**: `curl "http://localhost:8000/api/metrics/net-realized-pnl?window=24"` returns valid JSON with all required fields

### Tests for User Story 1 ⚠️

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T007 [US1] Write test_calculate_net_realized_pnl_basic in tests/test_net_realized_pnl.py - tests profit/loss calculation with mock data
- [x] T008 [US1] Write test_calculate_net_realized_pnl_edge_cases in tests/test_net_realized_pnl.py - tests zero values, missing prices, empty results
- [x] T009 [US1] Write test_signal_interpretation in tests/test_net_realized_pnl.py - tests PROFIT_DOMINANT, LOSS_DOMINANT, NEUTRAL signals

### Implementation for User Story 1

- [x] T010 [US1] Implement calculate_net_realized_pnl() function in scripts/metrics/net_realized_pnl.py with SQL query from data-model.md
- [x] T011 [US1] Implement _determine_signal() helper function in scripts/metrics/net_realized_pnl.py for interpreting net P/L
- [x] T012 [US1] Implement _calculate_profit_loss_ratio() helper in scripts/metrics/net_realized_pnl.py with division-by-zero handling
- [x] T013 [US1] Add GET /api/metrics/net-realized-pnl endpoint to api/main.py following existing patterns (window parameter 1-720 hours, default 24)
- [x] T014 [US1] Add input validation for window parameter (1-720 range) in api/main.py endpoint
- [x] T015 [US1] Add error handling for database connection failures in api/main.py endpoint

**Checkpoint**: User Story 1 (MVP) should be fully functional - run `uv run pytest tests/test_net_realized_pnl.py -v` to verify

---

## Phase 4: User Story 2 - Historical P/L Data (Priority: P2)

**Goal**: Provide daily Net Realized P/L history for trend analysis

**Independent Test**: `curl "http://localhost:8000/api/metrics/net-realized-pnl/history?days=7"` returns valid JSON with history array

### Tests for User Story 2 ⚠️

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T016 [US2] Write test_get_net_realized_pnl_history in tests/test_net_realized_pnl.py - tests history retrieval with mock data
- [x] T017 [US2] Write test_history_date_range in tests/test_net_realized_pnl.py - tests correct start_date/end_date calculation

### Implementation for User Story 2

- [x] T018 [US2] Implement get_net_realized_pnl_history() function in scripts/metrics/net_realized_pnl.py with GROUP BY DATE(spent_timestamp) query
- [x] T019 [US2] Add GET /api/metrics/net-realized-pnl/history endpoint to api/main.py (days parameter 1-365, default 30)
- [x] T020 [US2] Add input validation for days parameter (1-365 range) in api/main.py endpoint

**Checkpoint**: Both user stories should be independently functional

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [x] T021 [P] Run full test suite: `uv run pytest tests/test_net_realized_pnl.py -v --cov=scripts/metrics/net_realized_pnl`
- [x] T022 [P] Validate API with quickstart.md examples - both endpoints should return expected response format
- [x] T023 Run linter/formatter: `ruff check scripts/metrics/net_realized_pnl.py && ruff format scripts/metrics/net_realized_pnl.py`
- [x] T024 Validate performance: Query 24h window must complete in <100ms (use `time` or add timing to test)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - verify existing infrastructure
- **Foundational (Phase 2)**: Depends on Setup - creates data models
- **User Story 1 (Phase 3)**: Depends on Foundational - MVP implementation
- **User Story 2 (Phase 4)**: Depends on Foundational - extends with history
- **Polish (Phase 5)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on US2
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Shares module with US1 but independently testable

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Core calculation before API endpoint
- Validation and error handling last

### Parallel Opportunities

- T005 and T006 can run in parallel (different models in api/main.py imports)
- T021, T022, T023 can run in parallel (final validation)
- User Story 1 and User Story 2 implementation could be done in parallel by different developers (after Foundational phase)

---

## Parallel Example: User Story 1 Tests

```bash
# All US1 tests go in the same file, so run sequentially within tests phase:
# T007 → T008 → T009 (same file: tests/test_net_realized_pnl.py)

# However, test writing and implementation are separate phases
# Implementation T010-T015 happens AFTER tests T007-T009 fail
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T006)
3. Complete Phase 3: User Story 1 (T007-T015)
4. **STOP and VALIDATE**: Test US1 independently with `curl` command
5. API endpoint `/api/metrics/net-realized-pnl` is functional

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test → MVP deployed!
3. Add User Story 2 → Test → Full feature deployed!
4. Each story adds value without breaking previous stories

### Estimated Effort

| Phase | Tasks | Estimated Time |
|-------|-------|----------------|
| Setup | 2 | 10 min |
| Foundational | 4 | 20 min |
| User Story 1 | 9 | 60 min |
| User Story 2 | 5 | 30 min |
| Polish | 4 | 20 min |
| **Total** | **24** | **~2-3 hours** |

---

## Notes

- All tasks follow existing patterns in `scripts/metrics/` modules
- No new dependencies required - uses existing DuckDB, FastAPI, Pydantic
- Tests use existing pytest fixtures pattern
- API follows existing `/api/metrics/*` endpoint patterns
- Constitution Principle II (TDD) enforced: tests written before implementation
