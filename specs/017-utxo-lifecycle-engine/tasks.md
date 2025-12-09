# Tasks: UTXO Lifecycle Engine

**Input**: Design documents from `/specs/017-utxo-lifecycle-engine/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅

**Tests**: TDD approach required per Constitution Principle II.

**Organization**: Tasks grouped by user story for independent implementation.

## Format: `[ID] [Markers] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - complex algorithmic task

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and module structure

- [x] T001 Create feature branch `017-utxo-lifecycle-engine`
- [x] T002 [P] Create `scripts/metrics/utxo_lifecycle.py` with docstring (alpha-evolve: Approach C)
- [x] T003 [P] Create `scripts/metrics/realized_metrics.py` with docstring
- [x] T004 [P] Create `scripts/metrics/hodl_waves.py` with docstring (alpha-evolve: Approach C)
- [x] T005 [P] Create `tests/test_utxo_lifecycle.py` with imports
- [x] T006 [P] Create `tests/test_realized_metrics.py` with imports
- [x] T007 [P] Add UTXO configuration to `.env.example`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schema and core dataclasses

- [x] T008 Add UTXOLifecycle dataclass to `scripts/models/metrics_models.py`
- [x] T009 Add UTXOSetSnapshot dataclass to `scripts/models/metrics_models.py`
- [x] T010 Add AgeCohortsConfig dataclass to `scripts/models/metrics_models.py`
- [x] T011 Add SyncState dataclass to `scripts/models/metrics_models.py`
- [x] T012 Create DuckDB schema for `utxo_lifecycle` table
- [x] T013 Create DuckDB schema for `utxo_snapshots` table
- [x] T014 Create DuckDB schema for `utxo_sync_state` table
- [x] T015 [P] Add indexes for performance

### Storage Operation Tests (RED Phase) - A1 Remediation

- [x] T015a [P] Test `test_utxo_save_and_load()` in `tests/test_utxo_lifecycle.py`
- [x] T015b [P] Test `test_utxo_index_lookup_performance()` in `tests/test_utxo_lifecycle.py`
- [x] T015c [P] Test `test_utxo_pruning_removes_old_spent()` in `tests/test_utxo_lifecycle.py`

**Checkpoint**: Database ready for UTXO tracking

---

## Phase 3: User Story 1 - UTXO Creation Tracking (Priority: P1) 🎯 MVP

**Goal**: Track when each UTXO is created with block/price data

**Independent Test**: New UTXO has creation_block, creation_price, realized_value

### Tests for User Story 1 (RED Phase)

- [x] T016 [P] [US1] Test `test_utxo_creation_tracking()` in `tests/test_utxo_lifecycle.py`
- [x] T017 [P] [US1] Test `test_utxo_realized_value_calculation()` in `tests/test_utxo_lifecycle.py`
- [x] T018 [P] [US1] Test `test_process_block_outputs()` in `tests/test_utxo_lifecycle.py`

### Edge Case Tests (RED Phase) - A2 Remediation

- [x] T018a [P] [EC] Test `test_unknown_creation_price_fallback()` - mempool.space fallback
- [x] T018b [P] [EC] Test `test_coinbase_utxo_handling()` - is_coinbase=True, subsidy value
- [x] T018c [P] [EC] Test `test_reorg_invalidation()` - reorg_invalidated=True flow
- [x] T018d [P] [EC] Test `test_storage_limit_exceeded_triggers_prune()` - retention enforcement

### Implementation for User Story 1 (GREEN Phase)

- [x] T019 [US1] Implement `UTXOLifecycle.__post_init__()` in `scripts/models/metrics_models.py`
- [x] T020 [US1] Implement `save_utxo()` function in `scripts/metrics/utxo_lifecycle.py`
- [x] T021 [E] [US1] Implement `process_block_outputs()` in `scripts/metrics/utxo_lifecycle.py`
- [x] T022 [US1] Add price lookup integration in `scripts/metrics/utxo_lifecycle.py`
- [x] T023 [US1] Run tests → GREEN

**Checkpoint**: Can track new UTXO creation

---

## Phase 4: User Story 2 - UTXO Spending Tracking (Priority: P1)

**Goal**: Track when each UTXO is spent and calculate SOPR

**Independent Test**: Spent UTXO has spent_block, SOPR calculated

### Tests for User Story 2 (RED Phase)

- [x] T024 [P] [US2] Test `test_utxo_spending_tracking()` in `tests/test_utxo_lifecycle.py`
- [x] T025 [P] [US2] Test `test_sopr_calculation_on_spend()` in `tests/test_utxo_lifecycle.py`
- [x] T026 [P] [US2] Test `test_process_block_inputs()` in `tests/test_utxo_lifecycle.py`

### Implementation for User Story 2 (GREEN Phase)

- [x] T027 [US2] Implement `UTXOLifecycle.mark_spent()` method
- [x] T028 [US2] Implement `mark_utxo_spent()` function in `scripts/metrics/utxo_lifecycle.py`
- [x] T029 [E] [US2] Implement `process_block_inputs()` in `scripts/metrics/utxo_lifecycle.py`
- [x] T030 [E] [US2] Implement `process_block_utxos()` combining inputs/outputs
- [x] T031 [US2] Run tests → GREEN

**Checkpoint**: Can track UTXO lifecycle (create + spend)

---

## Phase 5: User Story 3 - Age Cohort Analysis (Priority: P1)

**Goal**: Classify UTXOs by age and calculate supply distribution

**Independent Test**: 30-day UTXO → STH + "1w-1m" sub-cohort

### Tests for User Story 3 (RED Phase)

- [x] T032 [P] [US3] Test `test_age_cohort_classification()` in `tests/test_utxo_lifecycle.py`
- [x] T033 [P] [US3] Test `test_sth_lth_split()` in `tests/test_utxo_lifecycle.py`
- [x] T034 [P] [US3] Test `test_supply_by_cohort()` in `tests/test_utxo_lifecycle.py`

### Implementation for User Story 3 (GREEN Phase)

- [x] T035 [US3] Implement `AgeCohortsConfig.classify()` method
- [x] T036 [US3] Implement `calculate_age_days()` function
- [x] T037 [US3] Implement `get_supply_by_cohort()` in `scripts/metrics/utxo_lifecycle.py`
- [x] T038 [US3] Implement `get_sth_lth_supply()` in `scripts/metrics/utxo_lifecycle.py`
- [x] T039 [US3] Run tests → GREEN

**Checkpoint**: Age cohort classification working

---

## Phase 6: User Story 4 - Realized Metrics (Priority: P2)

**Goal**: Calculate Realized Cap, MVRV, NUPL

**Independent Test**: Realized Cap = sum of realized values for unspent UTXOs

### Tests for User Story 4 (RED Phase)

- [x] T040 [P] [US4] Test `test_realized_cap_calculation()` in `tests/test_realized_metrics.py`
- [x] T041 [P] [US4] Test `test_mvrv_calculation()` in `tests/test_realized_metrics.py`
- [x] T042 [P] [US4] Test `test_nupl_calculation()` in `tests/test_realized_metrics.py`

### Implementation for User Story 4 (GREEN Phase)

- [x] T043 [US4] Implement `calculate_realized_cap()` in `scripts/metrics/realized_metrics.py`
- [x] T044 [US4] Implement `calculate_mvrv()` in `scripts/metrics/realized_metrics.py`
- [x] T045 [US4] Implement `calculate_nupl()` in `scripts/metrics/realized_metrics.py`
- [x] T046 [US4] Implement `create_snapshot()` for point-in-time metrics
- [x] T047 [US4] Run tests → GREEN

**Checkpoint**: Realized metrics working

---

## Phase 7: User Story 5 - HODL Waves (Priority: P2)

**Goal**: Calculate supply distribution by age cohort (HODL Waves)

**Independent Test**: HODL waves sum to 100% of supply

### Tests for User Story 5 (RED Phase)

- [x] T048 [P] [US5] Test `test_hodl_waves_calculation()` in `tests/test_utxo_lifecycle.py`
- [x] T049 [P] [US5] Test `test_hodl_waves_sum_to_100()` in `tests/test_utxo_lifecycle.py`

### Implementation for User Story 5 (GREEN Phase)

- [x] T050 [E] [US5] Implement `calculate_hodl_waves()` in `scripts/metrics/hodl_waves.py`
- [x] T051 [US5] Add HODL waves to snapshot creation
- [x] T052 [US5] Run tests → GREEN

**Checkpoint**: HODL Waves working

---

## Phase 8: User Story 6 - Sync & API (Priority: P2)

**Goal**: Incremental sync and API endpoints

**Independent Test**: Sync resumes from last checkpoint

### Tests for User Story 6 (RED Phase)

- [x] T053 [P] [US6] Test `test_sync_state_tracking()` in `tests/test_utxo_lifecycle.py`
- [x] T054 [P] [US6] Test `test_incremental_sync()` in `tests/test_utxo_lifecycle.py`

### Implementation for User Story 6 (GREEN Phase)

- [x] T055 [US6] Implement `get_sync_state()` function
- [x] T056 [US6] Implement `update_sync_state()` function
- [x] T057 [US6] Create `scripts/sync_utxo_lifecycle.py` sync script
- [x] T058 [US6] Add `/api/metrics/utxo-lifecycle` endpoint in `api/main.py`
- [x] T059 [US6] Add `/api/metrics/realized` endpoint in `api/main.py`
- [x] T060 [US6] Add `/api/metrics/hodl-waves` endpoint in `api/main.py`
- [x] T061 [US6] Run tests → GREEN
- [x] T061a [US6] Integrate lifecycle tracking into `scripts/daily_analysis.py`

**Checkpoint**: Full lifecycle engine operational

---

## Phase 9: Polish & Optimization

**Purpose**: Pruning, caching, documentation

- [x] T062 [P] Implement `prune_old_utxos()` function
- [ ] T063 [P] Add caching for frequently accessed data
- [ ] T064 [P] Update CLAUDE.md with spec-017 status
- [ ] T065 [P] Update `docs/ARCHITECTURE.md` with lifecycle documentation

### NFR Validation Tests - A4/A5 Remediation

- [x] T065a [NFR] Test `test_block_processing_under_5_seconds()` - benchmark (NFR-001) ✅ PASS
- [x] T065b [NFR] Test `test_100k_utxos_per_block()` - stress test (NFR-004) ✅ PASS (443s)

- [x] T066 Run full test suite: `uv run pytest tests/ -v` ✅ 38/38 PASS
- [x] T067 Run linter on all new files ✅ All checks passed
- [ ] T068 Validate quickstart.md scenarios
- [ ] T069 Create PR and merge

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (1)**: No dependencies
- **Foundational (2)**: Depends on Setup
- **US1-US3 (3-5)**: Depend on Foundational, can run in sequence
- **US4-US5 (6-7)**: Depend on US1-US3
- **US6 (8)**: Depends on US4-US5
- **Polish (9)**: Depends on all user stories

### User Story Dependencies

```
US1 (Creation) → US2 (Spending) → US3 (Cohorts)
                                        ↓
                          US4 (Realized) → US5 (HODL)
                                               ↓
                                          US6 (Sync/API)
```

---

## Summary

| Metric | Count |
|--------|-------|
| **Total Tasks** | 79 |
| **Setup Tasks** | 7 |
| **Foundational Tasks** | 11 (+3 storage tests) |
| **US1 Tasks** | 12 (+4 edge case tests) |
| **US2 Tasks** | 8 |
| **US3 Tasks** | 8 |
| **US4 Tasks** | 8 |
| **US5 Tasks** | 5 |
| **US6 Tasks** | 10 (+1 integration) |
| **Polish Tasks** | 10 (+2 NFR tests) |
| **Parallel Opportunities** | 35 tasks marked [P] |

---

## Implementation Strategy

### MVP First (US1-US3)

1. Setup + Foundational
2. US1: Creation tracking
3. US2: Spending tracking
4. US3: Age cohorts
5. **STOP**: Basic lifecycle working

### Full Implementation

6. US4: Realized metrics
7. US5: HODL Waves
8. US6: Sync & API
9. Polish

Estimated: 4-6 weeks total
