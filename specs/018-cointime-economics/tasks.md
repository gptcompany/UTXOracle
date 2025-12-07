# Tasks: Cointime Economics Framework

**Input**: Design documents from `/specs/018-cointime-economics/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅

**Tests**: TDD required per Constitution Principle II.

**Organization**: Tasks grouped by user story.

## Format: `[ID] [Markers] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - complex algorithmic task

---

## Phase 1: Setup

- [ ] T001 Create feature branch `018-cointime-economics`
- [ ] T002 [P] Create `scripts/metrics/cointime.py` with docstring
- [ ] T003 [P] Create `tests/test_cointime.py` with imports
- [ ] T004 [P] Add Cointime configuration to `.env.example`

---

## Phase 2: Foundational

- [ ] T005 Add CoinblocksMetrics dataclass to `scripts/models/metrics_models.py`
- [ ] T006 Add CointimeSupply dataclass to `scripts/models/metrics_models.py`
- [ ] T007 Add CointimeValuation dataclass to `scripts/models/metrics_models.py`
- [ ] T008 Add CointimeSignal dataclass to `scripts/models/metrics_models.py`
- [ ] T009 Create DuckDB schema for `cointime_metrics` table

**Checkpoint**: Schema ready

---

## Phase 3: User Story 1 - Coinblocks Tracking (P1) 🎯 MVP

**Goal**: Calculate coinblocks created and destroyed per block

### Tests (RED)

- [ ] T010 [P] [US1] Test `test_coinblocks_destroyed()` in `tests/test_cointime.py`
- [ ] T011 [P] [US1] Test `test_coinblocks_created()` in `tests/test_cointime.py`
- [ ] T012 [P] [US1] Test `test_cumulative_tracking()` in `tests/test_cointime.py`

### Implementation (GREEN)

- [ ] T013 [E] [US1] Implement `calculate_coinblocks_destroyed()` in `scripts/metrics/cointime.py`
- [ ] T014 [E] [US1] Implement `calculate_coinblocks_created()` in `scripts/metrics/cointime.py`
- [ ] T015 [US1] Implement cumulative tracking functions
- [ ] T016 [US1] Run tests → GREEN

**Checkpoint**: Coinblocks working

---

## Phase 4: User Story 2 - Liveliness (P1)

**Goal**: Calculate Liveliness and Vaultedness ratios

### Tests (RED)

- [ ] T017 [P] [US2] Test `test_liveliness_calculation()` in `tests/test_cointime.py`
- [ ] T018 [P] [US2] Test `test_vaultedness_calculation()` in `tests/test_cointime.py`
- [ ] T019 [P] [US2] Test `test_liveliness_bounds()` in `tests/test_cointime.py`

### Implementation (GREEN)

- [ ] T020 [E] [US2] Implement `calculate_liveliness()` in `scripts/metrics/cointime.py`
- [ ] T021 [E] [US2] Implement `calculate_vaultedness()` in `scripts/metrics/cointime.py`
- [ ] T022 [US2] Add bounds validation (0-1)
- [ ] T023 [US2] Run tests → GREEN

**Checkpoint**: Liveliness working

---

## Phase 5: User Story 3 - Supply Split (P1)

**Goal**: Calculate Active and Vaulted Supply

### Tests (RED)

- [ ] T024 [P] [US3] Test `test_active_supply()` in `tests/test_cointime.py`
- [ ] T025 [P] [US3] Test `test_vaulted_supply()` in `tests/test_cointime.py`
- [ ] T026 [P] [US3] Test `test_supply_sum()` in `tests/test_cointime.py`

### Implementation (GREEN)

- [ ] T027 [E] [US3] Implement `calculate_active_supply()` in `scripts/metrics/cointime.py`
- [ ] T028 [E] [US3] Implement `calculate_vaulted_supply()` in `scripts/metrics/cointime.py`
- [ ] T029 [US3] Run tests → GREEN

**Checkpoint**: Supply split working

---

## Phase 6: User Story 4 - AVIV Ratio (P1)

**Goal**: Calculate True Market Mean and AVIV

### Tests (RED)

- [ ] T030 [P] [US4] Test `test_true_market_mean()` in `tests/test_cointime.py`
- [ ] T031 [P] [US4] Test `test_aviv_ratio()` in `tests/test_cointime.py`
- [ ] T032 [P] [US4] Test `test_aviv_zones()` in `tests/test_cointime.py`

### Implementation (GREEN)

- [ ] T033 [US4] Implement `calculate_true_market_mean()` in `scripts/metrics/cointime.py`
- [ ] T034 [US4] Implement `calculate_aviv()` in `scripts/metrics/cointime.py`
- [ ] T035 [US4] Implement `classify_valuation_zone()` in `scripts/metrics/cointime.py`
- [ ] T036 [US4] Run tests → GREEN

**Checkpoint**: AVIV working

---

## Phase 7: User Story 5 - Fusion Integration (P2)

**Goal**: Integrate Cointime into Monte Carlo fusion

### Tests (RED)

- [ ] T037 [P] [US5] Test `test_cointime_signal_generation()` in `tests/test_cointime.py`
- [ ] T038 [P] [US5] Test `test_fusion_with_cointime()` in `tests/test_monte_carlo_fusion.py`

### Implementation (GREEN)

- [ ] T039 [US5] Implement `generate_cointime_signal()` in `scripts/metrics/cointime.py`
- [ ] T040 [US5] Add `cointime` to `EVIDENCE_BASED_WEIGHTS` in fusion
- [ ] T041 [US5] Update `enhanced_monte_carlo_fusion()` for 10 components
- [ ] T042 [US5] Add `/api/metrics/cointime` endpoint in `api/main.py`
- [ ] T043 [US5] Run tests → GREEN

**Checkpoint**: Fusion integration complete

---

## Phase 8: Polish

- [ ] T044 [P] Update CLAUDE.md with spec-018 status
- [ ] T045 [P] Update `docs/ARCHITECTURE.md` with Cointime documentation
- [ ] T046 Run full test suite
- [ ] T047 Run linter
- [ ] T048 Validate quickstart.md
- [ ] T049 Create PR and merge

---

## Dependencies

```
spec-017 (UTXO Lifecycle) ──► spec-018 (Cointime)

US1 (Coinblocks) → US2 (Liveliness) → US3 (Supply) → US4 (AVIV) → US5 (Fusion)
```

---

## Summary

| Metric | Count |
|--------|-------|
| **Total Tasks** | 49 |
| **Setup** | 4 |
| **Foundational** | 5 |
| **US1** | 7 |
| **US2** | 7 |
| **US3** | 6 |
| **US4** | 7 |
| **US5** | 7 |
| **Polish** | 6 |
| **Parallel [P]** | 18 |

Estimated: 3-4 weeks after spec-017
