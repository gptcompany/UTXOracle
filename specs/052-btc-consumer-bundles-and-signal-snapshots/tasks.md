# Tasks: spec-052 BTC Consumer Bundles and Signal Snapshots

**Input**: design documents from `/specs/052-btc-consumer-bundles-and-signal-snapshots/`
**Prerequisites**: `spec.md`, `plan.md`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex integration or boundary change

---

## Phase 1: Scope Freeze and Baseline Inventory

- [x] T001 Freeze the new bundle plane to exactly `btc_core_live.v1`, `btc_flow.v1`, `btc_macro.v1`, and `btc_cohort.v1`
- [x] T002 Freeze the signal plane to exactly `btc_signal_snapshot.v1`
- [x] T003 Record the existing production-ready input families already available on `:8011`
- [x] T004 Record which interesting families remain outside the first bundle plane by design: `RBN`, mixed advanced research, and local `NUPL`
- [x] T005 Record the current `BRK` curated subset already consumed by the live worker

**Checkpoint**: the scope is narrow before any implementation starts.

---

## Phase 2: Bundle Contract Freeze

- [x] T006 Define the exact route families for `latest` and `history` under `/api/features/btc/*`
- [x] T007 Freeze the top-level metadata common to all bundles: `schema_version`, `bundle_id`, `sequence_id`, `produced_at`, `bundle_status`, `degraded_reasons`
- [x] T008 Freeze the payload shape for `btc_core_live.v1`
- [x] T009 Freeze the payload shape for `btc_flow.v1`
- [x] T010 Freeze the payload shape for `btc_macro.v1`
- [x] T011 Freeze the payload shape for `btc_cohort.v1`
- [x] T012 Decide whether any currently existing route fields stay outside the first admitted bundle subset

**Checkpoint**: bundle names and schemas are frozen before wiring.

---

## Phase 3: Storage and Monotonicity

- [x] T013 [E] Decide how `sequence_id` is generated and persisted for bundle rows
- [x] T014 [E] Decide whether `sequence_id` is per-bundle only or part of a cross-bundle generation model
- [x] T015 Define the QuestDB tables or serving artifacts for the four bundle families
- [x] T016 Define the QuestDB table or serving artifact for `btc_signal_snapshot.v1`
- [x] T017 Freeze history ordering semantics for all bundles and the signal plane

**Checkpoint**: replay and deduplication semantics are explicit.

---

## Phase 4: Cost Basis Promotion

- [x] T018 Freeze the admitted `cost_basis` field subset for production consumption
- [x] T019 Publish the consumer-use statement for promoted `cost_basis`
- [x] T020 Publish reproducibility checks for `cost_basis`
- [x] T021 [E] Decide whether the promoted `cost_basis` slice is served directly from DuckDB with caveats or materialized into QuestDB
- [x] T022 Implement the chosen `cost_basis` serving-grade path
- [x] T023 Add boundary and degraded-state tests for the promoted `cost_basis` slice

**Checkpoint**: `cost_basis` is no longer trapped as a research-only route if it belongs in the service.

---

## Phase 5: BRK Macro Normalization

- [x] T024 Freeze the first admitted `BRK` macro subset for `btc_macro.v1`
- [x] T025 Verify whether `BRK` exposes an exact `cost_basis` equivalent, a partial overlap only, or no usable equivalent
- [x] T026 Record the `cost_basis` comparison outcome without changing local ownership unless equivalence is explicit
- [x] T027 [E] Extend the current BRK curated subset beyond `realized_price_usd`, `liveliness`, and `reserve_risk` as needed for the macro bundle
- [x] T028 Add missing-value and partial-degradation semantics for `btc_macro.v1`
- [x] T029 Add tests proving the bundle does not proxy the full BRK universe

**Checkpoint**: the macro bundle is `BRK`-first, deliberate, and bounded.

---

## Phase 6: Bundle Serving and History

- [x] T030 Freeze uniform `empty`, `stale`, `degraded`, and `misconfigured` behavior across all new bundle routes
- [x] T031 Write RED tests for all four bundle `latest` routes: expected response shape, `sequence_id` presence, `bundle_status` vocabulary, and degraded behavior
- [x] T032 Write RED tests for all four bundle `history` routes: ordering by `sequence_id`, pagination, and empty-state behavior
- [x] T033 [E] Implement `/api/features/btc/core/latest`
- [x] T034 [E] Implement `/api/features/btc/core/history`
- [x] T035 [E] Implement `/api/features/btc/flow/latest`
- [x] T036 [E] Implement `/api/features/btc/flow/history`
- [x] T037 [E] Implement `/api/features/btc/macro/latest`
- [x] T038 [E] Implement `/api/features/btc/macro/history`
- [x] T039 [E] Implement `/api/features/btc/cohort/latest`
- [x] T040 [E] Implement `/api/features/btc/cohort/history`
- [x] T041 Verify all RED tests from T031-T032 now pass GREEN

**Checkpoint**: the new feature plane is consumable and replayable.

---

## Phase 7: Signal Snapshot Layer

- [ ] T042 Freeze the payload schema for `btc_signal_snapshot.v1`
- [ ] T043 Freeze the deterministic formulas and component normalization rules for:
  - `regime_score`
  - `flow_score`
  - `valuation_score`
  - `quality_score`
- [ ] T044 Decide the final `service_status` vocabulary for the signal plane
- [ ] T045 Write RED tests for signal snapshot routes: response shape, `input_refs` presence, `sequence_id` monotonicity, and degraded-input propagation
- [ ] T046 [E] Implement the signal snapshot writer using only admitted bundle inputs
- [ ] T047 [E] Implement `/api/signals/btc/latest`
- [ ] T048 [E] Implement `/api/signals/btc/history`
- [ ] T049 Verify RED tests from T045 now pass GREEN

**Checkpoint**: the service exposes a real signal layer, not only raw features.

---

## Phase 8: Contract, Provenance, and Consumer Docs

- [ ] T050 Update the contract registry with the new bundle and signal surfaces
- [ ] T051 Update the provenance manifest with writer/read-path ownership for the new bundle and signal surfaces
- [ ] T052 Update the production consumer service profile to reflect the implemented state
- [ ] T053 Update the scope lock so the new service plane becomes the active boundary
- [ ] T054 Update consumer-facing docs describing the production-ready BTC service

**Checkpoint**: the implemented service and the docs match exactly.

---

## Phase 9: Verification

- [ ] T055 Run full integration suite across all bundle and signal routes
- [ ] T056 Run replay-order verification using `sequence_id`
- [ ] T057 Run degradation verification with missing BRK data
- [ ] T058 Run degradation verification with stale or missing QuestDB rows
- [ ] T059 Verify that `RBN` is absent from the runtime dependency path of the new service plane
- [ ] T060 Verify security posture decision from Gate E has been applied

**Checkpoint**: the BTC bundle and signal service is production-consumable, not merely documented.
