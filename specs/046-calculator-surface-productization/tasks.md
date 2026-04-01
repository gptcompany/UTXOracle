# Tasks: spec-046 Calculator Surface Productization

**Input**: design documents from `/specs/046-calculator-surface-productization/`
**Prerequisites**: `spec.md`, `plan.md`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex integration or data-model task

---

## Phase 1: Prioritization

- [ ] T001 Freeze Wave 1 route set: address cohorts, wallet waves, absorption rates
- [ ] T002 Freeze Wave 2 route set: reserve-risk, NUPL, cost-basis
- [ ] T003 Map backend and history requirements for each wave
- [ ] T004 Publish promotion acceptance checklist

**Checkpoint**: promotion work is ordered and bounded.

---

## Phase 2: RED Tests for Wave 1

- [ ] T005 Add failing tests for `/api/metrics/address-cohorts`
- [ ] T006 Add failing tests for `/api/metrics/wallet-waves`
- [ ] T007 Add failing tests for `/api/metrics/absorption-rates`
- [ ] T008 Add degraded and missing-backend tests for Wave 1 routes
- [ ] T009 Add insufficient-history tests for absorption rates and wallet-waves history behavior

**Checkpoint**: promotion behavior is defined by tests before wiring.

---

## Phase 3: Wave 1 Wiring

- [ ] T010 [E] Wire `scripts/metrics/address_cohorts.py` into `/api/metrics/address-cohorts`
- [ ] T011 [E] Wire `scripts/metrics/wallet_waves.py` into `/api/metrics/wallet-waves`
- [ ] T012 [E] Wire `scripts/metrics/absorption_rates.py` into `/api/metrics/absorption-rates`
- [ ] T013 Replace `501` responses with defined empty/stale/misconfigured behavior
- [ ] T014 Add route-level caveats or confidence metadata where needed

**Checkpoint**: Wave 1 routes are callable and no longer placeholder APIs.

---

## Phase 4: History Materialization

- [ ] T015 Define persistent snapshot storage for wallet-wave baselines
- [ ] T016 Define writer/backfill workflow for absorption-rate inputs
- [ ] T017 Implement `/api/metrics/wallet-waves/history` behavior or explicitly demote it to a later wave
- [ ] T018 Document insufficient-history semantics for history-dependent routes

**Checkpoint**: history-dependent Wave 1 routes are operationally coherent.

---

## Phase 5: Registry Updates

- [ ] T019 Update spec-044 contract registry entries for promoted routes
- [ ] T020 Update spec-045 provenance manifest entries for promoted routes
- [ ] T021 Document remaining `calculator only` families as later waves

**Checkpoint**: promotion is reflected outside the code path.

---

## Phase 6: Wave 2 Preparation

- [ ] T022 Audit reserve-risk inputs and dependencies
- [ ] T023 Audit NUPL inputs and dependencies
- [ ] T024 Audit cost-basis inputs and dependencies
- [ ] T025 Freeze Wave 2 execution plan based on actual blockers

**Checkpoint**: the second promotion wave is ready without re-auditing from scratch.

