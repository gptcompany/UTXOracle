# Tasks: spec-046 Calculator Surface Productization

**Input**: design documents from `/specs/046-calculator-surface-productization/`
**Prerequisites**: `spec.md`, `plan.md`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex integration or data-model task

---

## Phase 1: Prioritization

- [x] T001 Freeze Wave 1 route set: address cohorts, wallet waves, absorption rates
- [x] T002 Freeze Wave 2 route set: reserve-risk, NUPL, cost-basis
- [x] T003 Map backend and history requirements for each wave
- [x] T004 Publish promotion acceptance checklist

**Checkpoint**: promotion work is ordered and bounded.

---

## Phase 2: RED Tests for Wave 1

- [x] T005 Add failing tests for `/api/metrics/address-cohorts`
- [x] T006 Add failing tests for `/api/metrics/wallet-waves`
- [x] T007 Add failing tests for `/api/metrics/absorption-rates`
- [x] T008 Add degraded and missing-backend tests for Wave 1 routes
- [x] T009 Add insufficient-history tests for absorption rates and wallet-waves history behavior

**Checkpoint**: promotion behavior is defined by tests before wiring.

---

## Phase 3: Wave 1 Wiring

- [x] T010 [E] Wire `scripts/metrics/address_cohorts.py` into `/api/metrics/address-cohorts`
- [x] T011 [E] Wire `scripts/metrics/wallet_waves.py` into `/api/metrics/wallet-waves`
- [x] T012 [E] Wire `scripts/metrics/absorption_rates.py` into `/api/metrics/absorption-rates`
- [x] T013 Replace `501` responses with defined empty/stale/misconfigured behavior
- [x] T014 Add route-level caveats or confidence metadata where needed

**Checkpoint**: Wave 1 routes are callable and no longer placeholder APIs.

---

## Phase 4: History Materialization

- [ ] T015 Define persistent snapshot storage for wallet-wave baselines
- [ ] T016 Define writer/backfill workflow for absorption-rate inputs
- [x] T017 Implement `/api/metrics/wallet-waves/history` behavior or explicitly demote it to a later wave
- [x] T018 Document insufficient-history semantics for history-dependent routes

**Checkpoint**: history-dependent Wave 1 routes are operationally coherent.

---

## Phase 5: Registry Updates

- [x] T019 Update spec-044 contract registry entries for promoted routes
- [x] T020 Update spec-045 provenance manifest entries for promoted routes
- [x] T021 Document remaining `calculator only` families as later waves

Execution note:

- Wave 1 runtime promotion is complete for `/api/metrics/address-cohorts`, `/api/metrics/wallet-waves`, and `/api/metrics/absorption-rates`.
- `wallet-waves/history` was explicitly held out of the promoted slice and now returns an explicit `503` pending snapshot materialization.
- RED-only failing artifacts were not preserved separately once deterministic regression tests were added for the promoted routes.

**Checkpoint**: promotion is reflected outside the code path.

---

## Phase 6: Wave 2 Preparation

- [x] T022 Audit reserve-risk inputs and dependencies
- [x] T023 Audit NUPL inputs and dependencies
- [x] T024 Audit cost-basis inputs and dependencies
- [x] T025 Freeze Wave 2 execution plan based on actual blockers

**Checkpoint**: the second promotion wave is ready without re-auditing from scratch.

Execution note:

- Wave 2 is now explicitly selective rather than all-or-nothing.
- `/api/metrics/reserve-risk` remains held because the calculator still mixes real reads with placeholder/default analytical internals.
- `/api/metrics/nupl` is the first selective promotion candidate, subject to explicit policy for the estimated `pct_supply_in_profit` field.
- `/api/metrics/cost-basis` is the strongest selective promotion candidate, but still requires route wiring and route-level degraded semantics.

---

## Phase 7: Selective Wave 2 Follow-Up

- [ ] T026 Add RED tests for `/api/metrics/nupl` healthy and degraded serving paths
- [ ] T027 Add RED tests for `/api/metrics/cost-basis` healthy and degraded serving paths
- [ ] T028 Freeze field policy for NUPL `pct_supply_in_profit` before route admission
- [ ] T029 Keep `/api/metrics/reserve-risk` at `501` until placeholder/default internals are removed or separately re-spec the route

**Checkpoint**: the next implementation milestone is narrowed to the routes that are actually ready for productization work.
