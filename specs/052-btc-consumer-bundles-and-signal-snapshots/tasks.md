# Tasks: spec-052 BTC Consumer Bundles and Signal Snapshots

**Input**: design documents from `/specs/052-btc-consumer-bundles-and-signal-snapshots/`
**Prerequisites**: `spec.md`, `plan.md`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex integration or boundary change

---

## Phase 1: Scope Freeze and Baseline Inventory

- [ ] T001 Freeze the new bundle plane to exactly `btc_core_live.v1`, `btc_flow.v1`, `btc_macro.v1`, and `btc_cohort.v1`
- [ ] T002 Freeze the signal plane to exactly `btc_signal_snapshot.v1`
- [ ] T003 Record the existing production-ready input families already available on `:8011`
- [ ] T004 Record which interesting families remain outside the first bundle plane by design: `RBN`, mixed advanced research, and local `NUPL`
- [ ] T005 Record the current `BRK` curated subset already consumed by the live worker

**Checkpoint**: the scope is narrow before any implementation starts.

---

## Phase 2: Bundle Contract Freeze

- [ ] T006 Define the exact route families for `latest` and `history` under `/api/features/btc/*`
- [ ] T007 Freeze the top-level metadata common to all bundles: `schema_version`, `bundle_id`, `sequence_id`, `produced_at`, `bundle_status`, `degraded_reasons`
- [ ] T008 Freeze the payload shape for `btc_core_live.v1`
- [ ] T009 Freeze the payload shape for `btc_flow.v1`
- [ ] T010 Freeze the payload shape for `btc_macro.v1`
- [ ] T011 Freeze the payload shape for `btc_cohort.v1`
- [ ] T012 Decide whether any currently existing route fields stay outside the first admitted bundle subset

**Checkpoint**: bundle names and schemas are frozen before wiring.

---

## Phase 3: Storage and Monotonicity

- [ ] T013 [E] Decide how `sequence_id` is generated and persisted for bundle rows
- [ ] T014 [E] Decide whether `sequence_id` is per-bundle only or part of a cross-bundle generation model
- [ ] T015 Define the QuestDB tables or serving artifacts for the four bundle families
- [ ] T016 Define the QuestDB table or serving artifact for `btc_signal_snapshot.v1`
- [ ] T017 Freeze history ordering semantics for all bundles and the signal plane

**Checkpoint**: replay and deduplication semantics are explicit.

---

## Phase 4: Cost Basis Promotion

- [ ] T018 Freeze the admitted `cost_basis` field subset for production consumption
- [ ] T019 Publish the consumer-use statement for promoted `cost_basis`
- [ ] T020 Publish reproducibility checks for `cost_basis`
- [ ] T021 [E] Decide whether the promoted `cost_basis` slice is served directly from DuckDB with caveats or materialized into QuestDB
- [ ] T022 Implement the chosen `cost_basis` serving-grade path
- [ ] T023 Add boundary and degraded-state tests for the promoted `cost_basis` slice

**Checkpoint**: `cost_basis` is no longer trapped as a research-only route if it belongs in the service.

---

## Phase 5: BRK Macro Normalization

- [ ] T024 Freeze the first admitted `BRK` macro subset for `btc_macro.v1`
- [ ] T025 Verify whether `BRK` exposes an exact `cost_basis` equivalent, a partial overlap only, or no usable equivalent
- [ ] T026 Record the `cost_basis` comparison outcome without changing local ownership unless equivalence is explicit
- [ ] T027 [E] Extend the current BRK curated subset beyond `realized_price_usd`, `liveliness`, and `reserve_risk` as needed for the macro bundle
- [ ] T028 Add missing-value and partial-degradation semantics for `btc_macro.v1`
- [ ] T029 Add tests proving the bundle does not proxy the full BRK universe

**Checkpoint**: the macro bundle is `BRK`-first, deliberate, and bounded.

---

## Phase 6: Bundle Serving and History

- [ ] T030 [E] Implement `/api/features/btc/core/latest`
- [ ] T031 [E] Implement `/api/features/btc/core/history`
- [ ] T032 [E] Implement `/api/features/btc/flow/latest`
- [ ] T033 [E] Implement `/api/features/btc/flow/history`
- [ ] T034 [E] Implement `/api/features/btc/macro/latest`
- [ ] T035 [E] Implement `/api/features/btc/macro/history`
- [ ] T036 [E] Implement `/api/features/btc/cohort/latest`
- [ ] T037 [E] Implement `/api/features/btc/cohort/history`
- [ ] T038 Freeze uniform `empty`, `stale`, `degraded`, and `misconfigured` behavior across all new bundle routes

**Checkpoint**: the new feature plane is consumable and replayable.

---

## Phase 7: Signal Snapshot Layer

- [ ] T039 Freeze the payload schema for `btc_signal_snapshot.v1`
- [ ] T040 Freeze the deterministic formulas and component normalization rules for:
  - `regime_score`
  - `flow_score`
  - `valuation_score`
  - `quality_score`
- [ ] T041 Decide the final `service_status` vocabulary for the signal plane
- [ ] T042 [E] Implement the signal snapshot writer using only admitted bundle inputs
- [ ] T043 [E] Implement `/api/signals/btc/latest`
- [ ] T044 [E] Implement `/api/signals/btc/history`
- [ ] T045 Add tests proving signal snapshots carry referenced input bundle sequence IDs
- [ ] T046 Add tests proving degraded bundle inputs degrade signal status deterministically

**Checkpoint**: the service exposes a real signal layer, not only raw features.

---

## Phase 8: Contract, Provenance, and Consumer Docs

- [ ] T047 Update the contract registry with the new bundle and signal surfaces
- [ ] T048 Update the provenance manifest with writer/read-path ownership for the new bundle and signal surfaces
- [ ] T049 Update the production consumer service profile to reflect the implemented state
- [ ] T050 Update the scope lock so the new service plane becomes the active boundary
- [ ] T051 Update consumer-facing docs describing the production-ready BTC service

**Checkpoint**: the implemented service and the docs match exactly.

---

## Phase 9: Verification

- [ ] T052 Run targeted tests for all new bundle routes
- [ ] T053 Run targeted tests for all new signal routes
- [ ] T054 Run replay-order verification using `sequence_id`
- [ ] T055 Run degradation verification with missing BRK data
- [ ] T056 Run degradation verification with stale or missing QuestDB rows
- [ ] T057 Verify that `RBN` is absent from the runtime dependency path of the new service plane

**Checkpoint**: the BTC bundle and signal service is production-consumable, not merely documented.
