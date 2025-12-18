# Tasks: Wallet Waves & Absorption Rates (spec-025)

**Input**: Design documents from `/specs/025-wallet-waves/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Tests**: TDD required per plan.md - tests written before implementation.

**Organization**: Two user stories (Wallet Waves, Absorption Rates) that can be implemented independently.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - complex algorithmic tasks
- **[US1]**: User Story 1 - Wallet Waves Distribution
- **[US2]**: User Story 2 - Absorption Rates

### Marker Analysis

| File | Tasks | [P] Eligible |
|------|-------|--------------|
| `scripts/models/metrics_models.py` | T002, T003, T004, T005, T006 | ❌ Same file |
| `tests/test_wallet_waves.py` | T007, T008 | ❌ Same file |
| `scripts/metrics/wallet_waves.py` | T009, T010 | ❌ Same file |
| `api/main.py` | T011, T011b | ❌ Depends on T010 |
| `tests/test_absorption_rates.py` | T012, T013 | ❌ Same file |
| `scripts/metrics/absorption_rates.py` | T014, T015 | ❌ Same file |
| `api/main.py` | T016 | ❌ Depends on T015 |

**[P] Opportunities**: US1 and US2 test files can run in parallel (T007 || T012) after Phase 2.

**[E] Analysis**: No complex algorithms requiring multi-implementation exploration. SQL aggregation is straightforward.

---

## Phase 1: Setup

**Purpose**: Verify infrastructure exists (existing project)

- [x] T001 Verify utxo_lifecycle_full VIEW exists with address column

---

## Phase 2: Foundational - Data Models

**Purpose**: Create shared data structures required by both user stories

**⚠️ CRITICAL**: Both US1 and US2 depend on WalletBand enum

- [x] T002 Add WalletBand enum to scripts/models/metrics_models.py
- [x] T003 Add BAND_THRESHOLDS constant to scripts/models/metrics_models.py
- [x] T004 Add WalletBandMetrics dataclass to scripts/models/metrics_models.py
- [x] T005 Add WalletWavesResult dataclass to scripts/models/metrics_models.py
- [x] T006 Add AbsorptionRateMetrics and AbsorptionRatesResult dataclasses to scripts/models/metrics_models.py

**Checkpoint**: Data models ready - user story implementation can begin

---

## Phase 3: User Story 1 - Wallet Waves Distribution (Priority: P1) 🎯 MVP

**Goal**: Calculate supply distribution across 6 wallet size bands (shrimp to humpback)

**Independent Test**: `curl http://localhost:8000/api/metrics/wallet-waves` returns JSON with 6 bands, retail_supply_pct, institutional_supply_pct

### Tests for User Story 1 (TDD - RED Phase)

**NOTE**: Write these tests FIRST, ensure they FAIL before implementation

- [x] T007 [P] [US1] Write unit tests for classify_balance_to_band function in tests/test_wallet_waves.py (test_classify_shrimp, test_classify_crab, test_classify_fish, test_classify_shark, test_classify_whale, test_classify_humpback, test_classify_edge_cases)
- [x] T008 [US1] Write unit tests for calculate_wallet_waves function in tests/test_wallet_waves.py (test_basic_distribution, test_empty_database, test_percentage_sum_validation, test_retail_institutional_aggregates)

**Checkpoint (RED)**: All US1 tests written and failing - implementation can begin

### Implementation for User Story 1 (GREEN Phase)

- [x] T009 [US1] Implement classify_balance_to_band function in scripts/metrics/wallet_waves.py
- [x] T010 [US1] Implement calculate_wallet_waves function in scripts/metrics/wallet_waves.py
- [x] T011 [US1] Add GET /api/metrics/wallet-waves endpoint to api/main.py
- [x] T011b [US1] Add GET /api/metrics/wallet-waves/history endpoint to api/main.py with days query parameter

**Checkpoint (GREEN)**: All US1 tests passing - User Story 1 complete

---

## Phase 4: User Story 2 - Absorption Rates (Priority: P2)

**Goal**: Calculate rate at which each wallet band absorbs new mined supply

**Independent Test**: `curl "http://localhost:8000/api/metrics/absorption-rates?window=30d"` returns JSON with absorption rates per band, dominant_absorber

**Dependencies**: Requires WalletWavesResult from US1 (for snapshot comparison)

### Tests for User Story 2 (TDD - RED Phase)

**NOTE**: Write these tests FIRST, ensure they FAIL before implementation

- [x] T012 [P] [US2] Write unit tests for calculate_mined_supply function in tests/test_absorption_rates.py (test_mined_supply_7d, test_mined_supply_30d, test_mined_supply_90d)
- [x] T013 [US2] Write unit tests for calculate_absorption_rates function in tests/test_absorption_rates.py (test_basic_absorption, test_no_historical_data, test_dominant_absorber_selection, test_retail_vs_institutional)

**Checkpoint (RED)**: All US2 tests written and failing - implementation can begin

### Implementation for User Story 2 (GREEN Phase)

- [x] T014 [US2] Implement calculate_mined_supply helper function in scripts/metrics/absorption_rates.py
- [x] T015 [US2] Implement calculate_absorption_rates function in scripts/metrics/absorption_rates.py
- [x] T016 [US2] Add GET /api/metrics/absorption-rates endpoint to api/main.py with window query parameter

**Checkpoint (GREEN)**: All US2 tests passing - User Story 2 complete

---

## Phase 5: Polish & Validation

**Purpose**: Final verification and cross-cutting concerns

- [x] T017 Write API integration tests in tests/test_wallet_waves.py (test_wallet_waves_api_endpoint, test_wallet_waves_history_endpoint, test_wallet_waves_api_response_schema)
- [x] T018 Write API integration tests in tests/test_absorption_rates.py (test_absorption_rates_api_endpoint, test_absorption_rates_window_parameter)
- [x] T019 Run quickstart.md validation scenarios (20/20 unit tests pass)
- [x] T020 Run full test suite with coverage (target: 80%+) → **93% achieved**
- [ ] T021 Validate performance requirement: wallet waves calculation <5s (requires populated DB)

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup (T001)
    │
    ▼
Phase 2: Foundational (T002 → T003 → T004 → T005 → T006)
    │
    ├──────────────────────────────┐
    ▼                              ▼
Phase 3: US1 (T007-T011)     Phase 4: US2 (T012-T016)
    │                              │
    └──────────────────────────────┘
                   │
                   ▼
         Phase 5: Polish (T017-T021)
```

### User Story Dependencies

| Story | Depends On | Reason |
|-------|------------|--------|
| US1 (Wallet Waves) | Phase 2 | Needs WalletBand enum, WalletWavesResult |
| US2 (Absorption Rates) | Phase 2, US1 partial | Needs WalletWavesResult; uses calculate_wallet_waves internally |

### Task Dependencies

| Task | Depends On | Reason |
|------|------------|--------|
| T003 | T002 | Thresholds reference WalletBand enum |
| T004 | T002 | WalletBandMetrics uses WalletBand |
| T005 | T004 | WalletWavesResult contains list[WalletBandMetrics] |
| T006 | T002, T004 | AbsorptionRateMetrics uses WalletBand |
| T007 | T002, T003 | Tests import WalletBand, BAND_THRESHOLDS |
| T008 | T005 | Tests import WalletWavesResult |
| T009 | T007 | TDD: classify tests must fail first |
| T010 | T008, T009 | TDD: calculator tests must fail first; depends on classify |
| T011 | T010 | Endpoint calls calculate_wallet_waves |
| T011b | T010 | History endpoint calls calculate_wallet_waves |
| T012 | T006 | Tests import AbsorptionRatesResult |
| T013 | T006, T010 | Tests need absorption result; may mock wallet_waves |
| T014 | T012 | TDD: mined_supply tests must fail first |
| T015 | T013, T014, T010 | TDD: absorption tests must fail; depends on wallet_waves |
| T016 | T015 | Endpoint calls calculate_absorption_rates |
| T017 | T011, T011b | API tests require endpoints |
| T018 | T016 | API tests require endpoint |
| T019 | T011, T011b, T016 | Quickstart requires working API |
| T020 | T017, T018 | Full suite after API tests |
| T021 | T020 | Performance after tests pass |

### Parallel Opportunities

**Limited parallelization** due to single-file task groupings and TDD dependencies:

**After Phase 2 completes**, US1 and US2 test files can start in parallel:
```bash
# Can run in parallel (different files):
T007 (tests/test_wallet_waves.py) || T012 (tests/test_absorption_rates.py)
```

**Within each user story**: Sequential execution required (TDD + same file)

---

## Parallel Example: After Phase 2

```bash
# Launch US1 and US2 test writing in parallel (different files):
Task: "Write unit tests for classify_balance_to_band in tests/test_wallet_waves.py"
Task: "Write unit tests for calculate_mined_supply in tests/test_absorption_rates.py"

# Note: Implementation tasks remain sequential within each story
```

---

## Implementation Strategy

### MVP Delivery (User Story 1 Only)

1. ✅ Phase 1: Verify VIEW exists
2. Complete Phase 2: Create all data models (T002-T006)
3. Complete Phase 3: US1 Tests (T007-T008) → Implementation (T009-T011)
4. **STOP and VALIDATE**: Test via curl/pytest
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Data models ready
2. Add US1 (Wallet Waves) → Test independently → Demo (MVP!)
3. Add US2 (Absorption Rates) → Test independently → Demo
4. Polish → Full test suite, performance validation

### TDD Cycle Per User Story

```bash
# US1: RED Phase
uv run pytest tests/test_wallet_waves.py -v  # Must FAIL

# US1: GREEN Phase
uv run pytest tests/test_wallet_waves.py -v  # Must PASS

# US2: RED Phase
uv run pytest tests/test_absorption_rates.py -v  # Must FAIL

# US2: GREEN Phase
uv run pytest tests/test_absorption_rates.py -v  # Must PASS
```

---

## Notes

- **No [E] markers**: SQL aggregation is straightforward, no complex algorithms
- **Limited [P] markers**: Most tasks edit same files within each phase
- **TDD enforced**: Tests (T007-T008, T012-T013) must fail before implementation
- **US2 depends on US1**: calculate_absorption_rates uses calculate_wallet_waves internally
- Commit after each task
- Verify tests fail before implementing
- Target: 80%+ coverage, <5s query latency
