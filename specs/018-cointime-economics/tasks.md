# Tasks: Cointime Economics Framework

**Input**: Design documents from `/specs/018-cointime-economics/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅

**Tests**: TDD required per Constitution Principle II.

**Organization**: Tasks grouped by user story.

## Format: `[ID] [Markers] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - complex algorithmic task

## Governance Note (2026-04-05)

- This spec is in maintenance mode, not active feature build-out.
- `scripts/metrics/cointime.py`, `api/main.py`, and `scripts/metrics/monte_carlo_fusion.py` already implement the calculator, route family, and fusion integration.
- Remaining open tasks are limited to validation evidence and performance benchmarking on the research surface.

## Implementer Handoff (2026-04-05)

- Primary files for any remaining work: `tests/test_cointime.py`, `tests/fixtures/glassnode_cointime_reference.csv`, `scripts/metrics/cointime.py`, and `api/main.py`.
- Do not reinterpret this spec as a request to redesign the API contract; `/api/metrics/cointime*` already exists on `:8001`.
- When in doubt, follow current code reality: `cointime` sits in the 11-component `ENHANCED_WEIGHTS` set with weight `0.14`.

---

## Phase 1: Setup

- [x] T001 Create feature branch `018-cointime-economics`
- [x] T002 [P] Create `scripts/metrics/cointime.py` with docstring
- [x] T003 [P] Create `tests/test_cointime.py` with imports
- [x] T004 [P] Add Cointime configuration to `.env.example`

---

## Phase 2: Foundational

- [x] T005 Add CoinblocksMetrics dataclass to `scripts/models/metrics_models.py`
- [x] T006 Add CointimeSupply dataclass to `scripts/models/metrics_models.py`
- [x] T007 Add CointimeValuation dataclass to `scripts/models/metrics_models.py`
- [x] T008 Add CointimeSignal dataclass to `scripts/models/metrics_models.py`
- [x] T009 Create DuckDB schema for `cointime_metrics` table

**Checkpoint**: Schema ready

---

## Phase 3: User Story 1 - Coinblocks Tracking (P1) 🎯 MVP

**Goal**: Calculate coinblocks created and destroyed per block

### Tests (RED)

- [x] T010 [US1] Test `test_coinblocks_destroyed()` in `tests/test_cointime.py`
- [x] T011 [US1] Test `test_coinblocks_created()` in `tests/test_cointime.py`
- [x] T012 [US1] Test `test_cumulative_tracking()` in `tests/test_cointime.py`

### Implementation (GREEN)

- [x] T013 [E] [US1] Implement `calculate_coinblocks_destroyed()` in `scripts/metrics/cointime.py`
- [x] T014 [E] [US1] Implement `calculate_coinblocks_created()` in `scripts/metrics/cointime.py`
- [x] T015 [US1] Implement cumulative tracking functions
- [x] T016 [US1] Run tests → GREEN

**Checkpoint**: Coinblocks working ✅

---

## Phase 4: User Story 2 - Liveliness (P1)

**Goal**: Calculate Liveliness and Vaultedness ratios

### Tests (RED)

- [x] T017 [US2] Test `test_liveliness_calculation()` in `tests/test_cointime.py`
- [x] T018 [US2] Test `test_vaultedness_calculation()` in `tests/test_cointime.py`
- [x] T019 [US2] Test `test_liveliness_bounds()` in `tests/test_cointime.py`

### Implementation (GREEN)

- [x] T020 [E] [US2] Implement `calculate_liveliness()` in `scripts/metrics/cointime.py`
- [x] T021 [E] [US2] Implement `calculate_vaultedness()` in `scripts/metrics/cointime.py`
- [x] T022 [US2] Add bounds validation (0-1)
- [x] T023 [US2] Run tests → GREEN

**Checkpoint**: Liveliness working ✅

---

## Phase 4b: Rolling Liveliness (FR-006)

**Goal**: Calculate 7d, 30d, 90d rolling liveliness windows

### Tests (RED)

- [x] T023a [US2] Test `test_rolling_liveliness_7d()` in `tests/test_cointime.py`
- [x] T023b [US2] Test `test_rolling_liveliness_30d()` in `tests/test_cointime.py`
- [x] T023c [US2] Test `test_rolling_liveliness_90d()` in `tests/test_cointime.py`

### Implementation (GREEN)

- [x] T023d [US2] Implement `calculate_rolling_liveliness(window_days: int)` in `scripts/metrics/cointime.py`
- [x] T023e [US2] Run tests → GREEN

**Checkpoint**: Rolling liveliness working ✅

---

## Phase 5: User Story 3 - Supply Split (P1)

**Goal**: Calculate Active and Vaulted Supply

### Tests (RED)

- [x] T024 [US3] Test `test_active_supply()` in `tests/test_cointime.py`
- [x] T025 [US3] Test `test_vaulted_supply()` in `tests/test_cointime.py`
- [x] T026 [US3] Test `test_supply_sum()` in `tests/test_cointime.py`

### Implementation (GREEN)

- [x] T027 [E] [US3] Implement `calculate_active_supply()` in `scripts/metrics/cointime.py`
- [x] T028 [E] [US3] Implement `calculate_vaulted_supply()` in `scripts/metrics/cointime.py`
- [x] T029 [US3] Run tests → GREEN

**Checkpoint**: Supply split working ✅

---

## Phase 6: User Story 4 - AVIV Ratio (P1)

**Goal**: Calculate True Market Mean and AVIV

### Tests (RED)

- [x] T030 [US4] Test `test_true_market_mean()` in `tests/test_cointime.py`
- [x] T031 [US4] Test `test_aviv_ratio()` in `tests/test_cointime.py`
- [x] T032 [US4] Test `test_aviv_zones()` in `tests/test_cointime.py`

### Implementation (GREEN)

- [x] T033 [US4] Implement `calculate_true_market_mean()` in `scripts/metrics/cointime.py`
- [x] T034 [US4] Implement `calculate_aviv()` in `scripts/metrics/cointime.py`
- [x] T035 [US4] Implement `classify_valuation_zone()` in `scripts/metrics/cointime.py`
- [x] T036 [US4] Run tests → GREEN

**Checkpoint**: AVIV working ✅

---

## Phase 7: User Story 5 - Fusion Integration (P2)

**Goal**: Integrate Cointime into Monte Carlo fusion

### Tests (RED)

- [x] T037 [P] [US5] Test `test_cointime_signal_generation()` in `tests/test_cointime.py`
- [x] T038 [P] [US5] Test `test_fusion_with_cointime()` in `tests/test_cointime.py`

### Implementation (GREEN)

- [x] T039 [US5] Implement `generate_cointime_signal()` in `scripts/metrics/cointime.py`
- [x] T040 [US5] Add `cointime` to `ENHANCED_WEIGHTS` in fusion (current 11-component set)
- [x] T040a [US5] Rebalance `ENHANCED_WEIGHTS` to the current 1.0-summing mix (`whale 0.24`, `utxo 0.12`, `funding 0.05`, `oi 0.05`, `power_law 0.06`, `symbolic 0.12`, `fractal 0.09`, `wasserstein 0.08`, `cointime 0.14`, `sopr 0.02`, `mvrv_z 0.03`)
- [x] T041 [US5] Update `enhanced_fusion()` for the current 11-component set
- [x] T042 [US5] Add `/api/metrics/cointime` endpoints in `api/main.py` (latest, history, signal)
- [x] T043 [US5] Run tests → GREEN (96 passed)

**Checkpoint**: Fusion integration complete ✅

---

## Phase 8: Polish

- [x] T044 [P] Update CLAUDE.md with spec-018 status
- [x] T045 [P] Update `docs/ARCHITECTURE.md` with Cointime documentation
- [ ] T045a [P] Create `tests/fixtures/glassnode_cointime_reference.csv` with sampled reference values for `liveliness` and `aviv_ratio`
- [ ] T045b Add `test_glassnode_comparison()` to `tests/test_cointime.py` comparing local outputs against `tests/fixtures/glassnode_cointime_reference.csv` for `SC-001`/`SC-002`
- [ ] T045c Add a performance benchmark test to `tests/test_cointime.py` asserting the `<1s/block` requirement for `SC-003`
- [x] T046 Run full test suite (96 passed)
- [x] T047 Run linter (all checks passed)
- [x] T048 Validate quickstart.md (N/A - no quickstart for spec-018)
- [x] T049 Create PR → https://github.com/gptprojectmanager/UTXOracle/pull/6

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
| **Total Tasks** | 58 |
| **Setup** | 4 |
| **Foundational** | 5 |
| **US1** | 7 |
| **US2 + Rolling** | 12 |
| **US3** | 6 |
| **US4** | 7 |
| **US5** | 8 |
| **Polish** | 9 |
| **Parallel [P]** | 8 |

Estimated: 3-4 weeks after spec-017
