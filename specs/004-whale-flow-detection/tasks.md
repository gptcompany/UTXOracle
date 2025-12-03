# Tasks: Whale Flow Detection

**Input**: Design documents from `/specs/004-whale-flow-detection/`
**Prerequisites**: plan.md ✅, spec.md ✅, examples/whale-flow-references/ ✅

**Tests**: TDD approach - tests written BEFORE implementation (RED-GREEN-REFACTOR)

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- All file paths are absolute

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependencies, and directory structure

- [X] T001 Install bitcoinlib dependency in pyproject.toml (`bitcoinlib = "^0.6"`)
- [X] T002 [P] Create data/ directory for exchange addresses CSV
- [X] T003 [P] Create tests/fixtures/ directory for test data
- [X] T004 [P] Create docs/ directory (if not exists) for documentation
- [X] T005 [P] Verify electrs HTTP API connectivity: `curl localhost:3001/blocks/tip/height`
- [X] T006 [P] Verify mempool backend API connectivity: `curl localhost:8999/api/v1/prices`

**Checkpoint**: All services accessible, directories created, dependencies ready

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data and infrastructure that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T007 Download exchange addresses from GitHub Gist to `data/exchange_addresses.csv`
- [X] T008 Validate exchange address CSV format (columns: exchange_name, address, type)
- [X] T009 Extend DuckDB schema: `ALTER TABLE price_comparisons ADD COLUMN whale_net_flow REAL`
- [X] T010 Extend DuckDB schema: `ALTER TABLE price_comparisons ADD COLUMN whale_direction TEXT`
- [X] T011 Extend DuckDB schema: `ALTER TABLE price_comparisons ADD COLUMN action TEXT`
- [X] T012 Extend DuckDB schema: `ALTER TABLE price_comparisons ADD COLUMN combined_signal REAL`
- [X] T013 Create WhaleFlowSignal dataclass in `contracts/whale_flow_detector_interface.py`
- [X] T014 Create WhaleFlowDetector class interface in `contracts/whale_flow_detector_interface.py`
- [X] T015 Create test fixture: `tests/fixtures/whale_transactions_sample.json` (20 labeled transactions)

**Checkpoint**: Foundation ready - CSV downloaded, DB schema extended, contracts defined

---

## Phase 3: User Story 1 - Real-time Whale Flow Signal (Priority: P1) 🎯 MVP

**Goal**: Detect whale accumulation/distribution signals from latest Bitcoin block and display on dashboard

**Independent Test**: Run `python3 scripts/whale_flow_detector.py` standalone and verify WhaleFlowSignal output with net_flow_btc, direction, confidence

### Tests for User Story 1 (TDD - Write FIRST) ⚠️

**RED Phase**: Write failing tests, validate they FAIL before implementation

- [X] T016 [P] [US1] Unit test: `test_load_exchange_addresses_csv()` in tests/test_whale_flow_detector.py
- [X] T017 [P] [US1] Unit test: `test_parse_addresses_from_transaction()` in tests/test_whale_flow_detector.py
- [X] T018 [P] [US1] Unit test: `test_classify_transaction_inflow()` in tests/test_whale_flow_detector.py
- [X] T019 [P] [US1] Unit test: `test_classify_transaction_outflow()` in tests/test_whale_flow_detector.py
- [X] T020 [P] [US1] Unit test: `test_classify_transaction_internal()` in tests/test_whale_flow_detector.py
- [X] T021 [P] [US1] Unit test: `test_calculate_net_flow()` in tests/test_whale_flow_detector.py
- [X] T022 [P] [US1] Unit test: `test_determine_direction_accumulation()` in tests/test_whale_flow_detector.py
- [X] T023 [P] [US1] Unit test: `test_determine_direction_distribution()` in tests/test_whale_flow_detector.py
- [X] T024 [P] [US1] Unit test: `test_determine_direction_neutral()` in tests/test_whale_flow_detector.py
- [X] T025 [P] [US1] Unit test: `test_analyze_block_with_mock_data()` in tests/test_whale_flow_detector.py
- [X] T026 [P] [US1] Unit test: `test_whale_flow_signal_validation()` in tests/test_whale_flow_detector.py

**Checkpoint RED**: All tests written and FAILING (verify with `pytest tests/test_whale_flow_detector.py`)

### Implementation for User Story 1 (GREEN Phase) 🟢

**CRITICAL**: Implement MINIMAL code to pass each test, one at a time (baby steps)

- [X] T027 [US1] Create `scripts/whale_flow_detector.py` with WhaleFlowDetector class stub
- [X] T028 [US1] Implement `_load_exchange_addresses()` method (load CSV into set for O(1) lookup)
- [X] T029 [US1] Implement `_parse_addresses()` helper method (extract vin/vout addresses)
- [X] T030 [US1] Implement `_classify_transaction()` method (inflow/outflow/internal/unrelated logic)
- [X] T031 [US1] Implement `_calculate_net_flow()` method (sum inflow - outflow per block)
- [X] T032 [US1] Implement `_determine_direction()` method (threshold: 100 BTC for ACCUMULATION/DISTRIBUTION)
- [X] T033 [US1] Implement `_fetch_transactions_from_electrs()` method (GET localhost:3001/block/{hash}/txids)
- [X] T034 [US1] Implement `analyze_block(block_height)` method (main orchestration logic)
- [X] T035 [US1] Implement `analyze_latest_block()` convenience method
- [X] T036 [US1] Add error handling for electrs API failures (retry 3x with exponential backoff)
- [X] T037 [US1] Add logging: execution time, tx count, net flow, direction

**Checkpoint GREEN**: All US1 tests pass (verify with `pytest tests/test_whale_flow_detector.py`)

### Integration for User Story 1

- [ ] T038 [US1] Integration test: `test_whale_detector_with_real_electrs_api()` in tests/integration/test_whale_integration.py (DEFERRED to Phase 6)
- [ ] T039 [US1] Integration test: `test_fetch_latest_block_and_analyze()` in tests/integration/test_whale_integration.py (DEFERRED to Phase 6)
- [ ] T040 [US1] Integration test: `test_whale_flow_signal_consistency()` in tests/integration/test_whale_integration.py (DEFERRED to Phase 6)
- [X] T041 [US1] Add whale detector import to `scripts/daily_analysis.py` (line ~15: `from whale_flow_detector import WhaleFlowDetector`)
- [X] T042 [US1] Initialize WhaleFlowDetector in `scripts/daily_analysis.py` (load exchange addresses once at startup)
- [X] T043 [US1] Call `whale_detector.analyze_latest_block()` in main loop of daily_analysis.py (after UTXOracle calculation)
- [X] T044 [US1] Log whale signal output in daily_analysis.py (net_flow, direction, confidence)

**Checkpoint US1 Complete**: Run `python3 scripts/daily_analysis.py --dry-run --verbose` and verify whale signal logged

---

## Phase 4: User Story 2 - Combined Trading Signal Fusion (Priority: P2)

**Goal**: Combine whale flow signal (70%) with UTXOracle confidence (30%) into actionable BUY/SELL/HOLD recommendation

**Independent Test**: Provide mock whale signal + UTXOracle result, verify combined_signal calculation and action persistence in DuckDB

### Tests for User Story 2 (TDD - Write FIRST) ⚠️

- [x] T045 [P] [US2] Unit test: `test_signal_fusion_buy_scenario()` in tests/test_whale_flow_detector.py
- [x] T046 [P] [US2] Unit test: `test_signal_fusion_sell_scenario()` in tests/test_whale_flow_detector.py
- [x] T047 [P] [US2] Unit test: `test_signal_fusion_hold_scenario()` in tests/test_whale_flow_detector.py
- [x] T048 [P] [US2] Unit test: `test_signal_fusion_conflict_scenario()` in tests/test_whale_flow_detector.py (whale bullish + utxo bearish = HOLD)
- [ ] T049 [P] [US2] Integration test: `test_duckdb_persistence_with_whale_data()` in tests/integration/test_whale_integration.py

**Checkpoint RED**: All US2 tests written and FAILING

### Implementation for User Story 2 (GREEN Phase) 🟢

- [x] T050 [US2] Implement `_calculate_whale_vote()` helper in daily_analysis.py (net_flow → vote: 1.0/-1.0/0.0)
- [x] T051 [US2] Implement `_calculate_utxo_vote()` helper in daily_analysis.py (confidence → vote: 1.0/-1.0/0.0)
- [x] T052 [US2] Implement `_fuse_signals()` method in daily_analysis.py (weighted combination: whale 70%, utxo 30%)
- [x] T053 [US2] Implement `_determine_action()` method in daily_analysis.py (threshold: >0.5 = BUY, <-0.5 = SELL)
- [x] T054 [US2] Add signal fusion call in daily_analysis.py main loop (after whale signal, before DB save)
- [x] T055 [US2] Extend DuckDB INSERT statement to include whale_net_flow, whale_direction, action, combined_signal
- [x] T056 [US2] Add graceful degradation: if whale detector fails, continue with UTXOracle-only (set whale_vote=0)
- [x] T057 [US2] Add logging for signal fusion: whale_vote, utxo_vote, combined_signal, action

**Checkpoint GREEN**: All US2 tests pass, DuckDB contains whale data

### Dashboard Enhancement for User Story 2

- [X] T058 [US2] Add whale flow indicator HTML div to `frontend/comparison.html` (traffic light: green/red/yellow)
- [X] T059 [US2] Add JavaScript function to fetch whale data from DuckDB via API endpoint
- [X] T060 [US2] Add JavaScript function to update traffic light indicator (green = ACCUMULATION, red = DISTRIBUTION, yellow = NEUTRAL)
- [X] T061 [US2] Add whale net flow display: "ACCUMULATION: +1,250 BTC" or "DISTRIBUTION: -800 BTC"
- [X] T062 [US2] Add trading action display: "Action: BUY" with color coding (green/red/yellow)

**Checkpoint US2 Complete**: Open `http://localhost:8080`, verify whale flow indicator displays correctly

---

## Phase 5: User Story 3 - Historical Whale Flow Analysis (Priority: P3)

**Goal**: Backtest whale flow signals against historical price data (7+ days) to validate correlation and optimize threshold

**Independent Test**: Run backtest script on blocks 921000-922008 (7 days), verify correlation >0.6 and false positive rate <20%

### Tests for User Story 3 (TDD - Write FIRST) ⚠️

- [X] T063 [P] [US3] Unit test: `test_backtest_correlation_calculation()` in tests/test_whale_flow_detector.py
- [X] T064 [P] [US3] Unit test: `test_backtest_false_positive_rate()` in tests/test_whale_flow_detector.py
- [ ] T065 [P] [US3] Integration test: `test_backtest_7day_dataset()` in tests/integration/test_whale_integration.py (DEFERRED to Phase 6)

**Checkpoint RED**: All US3 tests written and FAILING

### Implementation for User Story 3 (GREEN Phase) 🟢

- [x] T066 [US3] Create `scripts/whale_flow_backtest.py` script with command-line interface
- [x] T067 [US3] Implement `--days` argument for backtest duration (default: 7)
- [x] T068 [US3] Implement `--start-block` argument for custom block range
- [x] T069 [US3] Implement block range calculation: `start_block` to `start_block + (days * 144)`
- [x] T070 [US3] Implement loop to call `whale_detector.analyze_block(height)` for each block in range
- [X] T071 [US3] Implement DuckDB storage for backtest results: table `backtest_whale_signals`
- [X] T072 [US3] Fetch BTC/USD price data for each block from `price_comparisons` table or mempool API
- [X] T073 [US3] Calculate price change 24h after each block (lag: 144 blocks)
- [x] T074 [US3] Implement correlation calculation: `CORR(whale_net_flow, price_change_24h)`
- [x] T075 [US3] Implement false positive rate calculation: % of signals with wrong direction
- [X] T076 [US3] Generate backtest report: `docs/WHALE_FLOW_BACKTEST_REPORT.md` with correlation, false positive rate, charts

**Checkpoint GREEN**: Run `python3 scripts/whale_flow_backtest.py --days 7`, verify correlation >0.6

**Checkpoint US3 Complete**: Backtest report shows validation metrics meet success criteria

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, error handling, performance optimization, production readiness

- [X] T077 [P] Add comprehensive logging to whale_flow_detector.py (DEBUG level for transaction details) - COMPLETED 2025-11-06
- [X] T078 [P] Add retry logic with exponential backoff for electrs API failures (3 retries, 1s/2s/4s delays) - COMPLETED 2025-11-06
- [X] T079 [P] Add connection pooling for electrs HTTP requests (reuse aiohttp.ClientSession) - COMPLETED 2025-11-06
- [X] T079a [P] PERFORMANCE: Eliminate double address parsing (3x→1x per transaction) - COMPLETED 2025-11-06
- [X] T079b [P] PERFORMANCE: Reuse Semaphore across batches (avoid recreation overhead) - COMPLETED 2025-11-06
- [X] T080 [P] Add performance metrics: execution time per block, avg API latency, memory usage - COMPLETED 2025-11-06 (execution time tracking implemented; API latency/memory metrics optional for future)
- [X] T081 Create `docs/WHALE_FLOW_DETECTOR.md` documentation (usage guide, API reference, troubleshooting) - COMPLETED 2025-11-06
- [X] T082 Add README section to `examples/whale-flow-references/README.md` linking to production code - COMPLETED 2025-11-06
- [X] T083 Add error handling for malformed CSV (exchange addresses file) - COMPLETED 2025-11-06
- [X] T084 Add validation: Check exchange address count >100 at startup (warn if <100) - COMPLETED 2025-11-06
- [X] T085 Add fallback to Bitcoin Core RPC if electrs fails (Tier 3 cascade, reuse existing code) - COMPLETED 2025-11-06
- [X] T086 Add graceful shutdown: Save state before exit (if needed) - COMPLETED 2025-11-06 (no-op shutdown method added, detector is stateless)
- [ ] T087 [P] Run final integration test: `test_end_to_end_whale_flow_pipeline()` in tests/integration/test_whale_integration.py
- [ ] T088 [P] Run performance test: Measure time to process 1 block with 2,500 transactions (target: <5s)
- [ ] T089 [P] Run memory test: Measure memory usage with exchange address set loaded (target: <100MB)
- [ ] T090 Generate coverage report: `pytest --cov=scripts.whale_flow_detector tests/` (target: >80%)

**Checkpoint**: All polish tasks complete, documentation exists, performance targets met

---

## Dependencies & Execution Order

### Critical Path (Sequential - MUST run in order):

1. **Phase 1 (Setup)** → T001-T006
2. **Phase 2 (Foundation)** → T007-T015 *(blocking for all user stories)*
3. **Phase 3 (US1 - MVP)** → T016-T044 *(independent, can be first user story)*
4. **Phase 4 (US2)** → T045-T062 *(depends on US1 complete, whale_detector.py exists)*
5. **Phase 5 (US3)** → T063-T076 *(depends on US1 complete, can run parallel with US2)*
6. **Phase 6 (Polish)** → T077-T090 *(depends on all user stories complete)*

### User Story Dependencies:

```
Phase 1: Setup (T001-T006)
    ↓
Phase 2: Foundation (T007-T015) ← BLOCKING for ALL stories
    ↓
    ├──→ US1: Real-time Signal (T016-T044) ← MVP (Priority P1)
    │       ↓
    │       ├──→ US2: Signal Fusion (T045-T062) ← Depends on US1 (Priority P2)
    │       │
    │       └──→ US3: Backtest (T063-T076) ← Depends on US1 (Priority P3)
    │
    └──→ Phase 6: Polish (T077-T090) ← Depends on ALL stories
```

### Parallel Opportunities:

**Within Phase 1** (all tasks can run in parallel):
- T002, T003, T004, T005, T006

**Within Phase 2** (parallel after T007 completes):
- T008 (validation)
- T009-T012 (DB schema changes, run sequentially but grouped)
- T013-T014 (contracts)
- T015 (fixtures)

**Within Phase 3 - US1 Tests** (all test files can be written in parallel):
- T016-T026 (all unit tests, different test functions)

**Within Phase 3 - US1 Implementation** (some tasks parallelizable):
- T038-T040 (integration tests, different test files)

**Within Phase 6 - Polish** (all tasks can run in parallel):
- T077, T078, T079, T080, T082, T083, T084, T087, T088, T089

**Execution Groups** (can run in parallel):
```bash
# Group 1: Setup (Phase 1)
- Run T001-T006 in parallel (6 tasks)

# Group 2: Foundation (Phase 2)
- Run T007 first (download CSV)
- Then run T008-T015 in parallel (8 tasks)

# Group 3: US1 Tests (RED phase)
- Run T016-T026 in parallel (11 test tasks)

# Group 4: US1 Implementation (GREEN phase)
- Run T027-T037 sequentially (core logic, dependencies)
- Run T038-T044 for integration

# Group 5: US2 Tests (RED phase)
- Run T045-T049 in parallel (5 test tasks)

# Group 6: US2 Implementation (GREEN phase)
- Run T050-T062 sequentially (signal fusion logic)

# Group 7: US3 (can run PARALLEL with US2 after US1 complete)
- Run T063-T065 (tests) in parallel
- Run T066-T076 (implementation) sequentially

# Group 8: Polish (Phase 6)
- Run T077-T090 mostly in parallel (14 tasks, 10 parallel)
```

---

## Implementation Strategy

### MVP Scope (Minimum Viable Product):
**User Story 1 ONLY** (T001-T044)
- Delivers: Real-time whale flow signal from latest block
- Testable: Run `python3 scripts/daily_analysis.py --dry-run`, see whale signal logged
- Time estimate: 2-3 days
- Success criteria: SC-001, SC-004, SC-006, SC-007 from spec.md

### Incremental Delivery:
1. **MVP (US1)**: Whale detection core → Deliverable after T044
2. **V1.1 (US2)**: Signal fusion + dashboard → Deliverable after T062
3. **V1.2 (US3)**: Historical validation → Deliverable after T076
4. **V1.3 (Polish)**: Production-ready → Deliverable after T090

### Test Coverage Targets:
- **Unit tests**: 90% coverage for `scripts/whale_flow_detector.py`
- **Integration tests**: 80% coverage for signal fusion logic
- **End-to-end test**: 100% coverage for main workflow (daily_analysis.py with whale detector)

### Performance Targets (from spec.md):
- **SC-001**: Process 1 block (2,500 tx) in <5 seconds → Validate with T088
- **SC-002**: Correlation >0.6 on 7-day backtest → Validate with T075
- **SC-003**: False positive rate <20% → Validate with T076
- **SC-005**: Dashboard update within 10 seconds → Validate with T062

---

## Task Summary

### Total Tasks: 90
- **Phase 1 (Setup)**: 6 tasks
- **Phase 2 (Foundation)**: 9 tasks *(blocking)*
- **Phase 3 (US1 - MVP)**: 29 tasks (11 tests + 18 implementation)
- **Phase 4 (US2)**: 18 tasks (5 tests + 13 implementation)
- **Phase 5 (US3)**: 14 tasks (3 tests + 11 implementation)
- **Phase 6 (Polish)**: 14 tasks

### Parallel Opportunities: 35 tasks marked [P]
- Phase 1: 5 tasks
- Phase 2: 7 tasks
- Phase 3: 11 tests (US1)
- Phase 4: 4 tests (US2)
- Phase 5: 2 tests (US3)
- Phase 6: 10 tasks

### Independent Test Criteria per User Story:
- **US1**: Run whale detector standalone, verify WhaleFlowSignal output
- **US2**: Provide mock inputs, verify signal fusion math and DuckDB persistence
- **US3**: Run backtest on 7-day dataset, verify correlation calculation

### Suggested Implementation Order:
1. **Days 1-2**: Phase 1 + Phase 2 (Foundation) → T001-T015
2. **Days 3-4**: Phase 3 (US1 - MVP) → T016-T044
3. **Day 5**: Phase 4 (US2) → T045-T062
4. **Day 6** (optional): Phase 5 (US3) → T063-T076
5. **Day 7** (optional): Phase 6 (Polish) → T077-T090

---

**Document Status**: ✅ Ready for implementation
**Next Step**: Run `/speckit.implement` to begin task execution
**Estimated Timeline**: 5-7 days for full implementation (MVP in 3 days)

**Generated by**: SpecKit `/speckit.tasks` command
**Date**: 2025-11-04
**Feature**: Whale Flow Detection (spec-004)
