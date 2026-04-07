# Tasks: spec-053 BTC Entity and Flow Intelligence Plane

**Input**: design documents from `/specs/053-btc-entity-and-flow-intelligence-plane/`
**Prerequisites**: `spec.md`, `plan.md`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex integration or schema task

---

## Phase 1: Scope Freeze and Vocabulary

- [x] T001 Freeze the problem boundary: this spec is about entity identity, provenance, and flow-of-funds, not macro metrics or execution logic
- [x] T002 Freeze the base vocabulary: `address`, `cluster_id`, `entity_id`, `entity_label`, `mapping_confidence`, `label_confidence`
- [x] T003 Decide the canonical `entity_id` format, generation strategy, and namespace vocabulary; freeze compatibility rules with `cluster:{cluster_id}`
- [x] T004 Decide the API namespace for deep entity and movement APIs
- [x] T005 Record the baseline heuristics already implemented and explicitly list what this spec must not reinvent

**Checkpoint**: the spec is framed as a new intelligence plane, not a reimplementation of old clustering code.

---

## Phase 2: Registry and Schema Design

- [x] T006 Design `entity_registry`; freeze `entity_kind` vocabulary
- [x] T007 Design `cluster_entity_map`
- [x] T008 Design `entity_labels`
- [x] T009 Design `entity_label_provenance`
- [x] T010 Decide which registry artifacts are authoritative in local storage versus materialized into QuestDB
- [x] T011 Freeze the status vocabulary for registry rows and labels

**Checkpoint**: entity identity and label storage are explicit.

---

## Phase 3: Confidence and Provenance Model

- [x] T012 Freeze separate confidence fields for clustering, mapping, and labels
- [x] T013 Freeze provenance vocabulary: source kind, source name, source ref, review status, method version
- [x] T014 Design how confidence is computed and updated when evidence changes; freeze first-slice composition rule for `confidence_overall`
- [x] T015 Design downgrade behavior when evidence becomes ambiguous or stale

**Checkpoint**: entity confidence is no longer a single opaque number.

---

## Phase 4: Mapping Pipeline

- [x] T016 [E] Define how existing `address_clusters` rows become registry-grade cluster records
- [x] T017 [E] Define how cluster-to-entity mapping is generated or curated
- [x] T018 Define how exchange labels and known entity hints feed the registry
- [x] T019 Define how manual or curated overrides are represented without destroying provenance
- [x] T020 Define reconciliation rules when multiple evidence sources disagree

**Checkpoint**: the entity registry has a real ingestion and reconciliation model.

---

## Phase 5: Flow-of-Funds Model

- [x] T021 Design `entity_movement_events` (transaction-level movement records, event-centric)
- [x] T022 Design `entity_transfer_edges` (directional relationship records between entities derived from movement events, relationship-centric)
- [x] T023 Design `entity_flows_daily`
- [x] T024 Design `entity_balance_snapshots_daily`
- [x] T025 Design `entity_counterparty_edges_daily`
- [x] T026 Freeze the movement classification vocabulary:
  - `exchange_inflow`
  - `exchange_outflow`
  - `entity_to_entity`
  - `entity_to_unlabeled`
  - `unlabeled_to_entity`
  - `internal_entity_reshuffle`
  - `ambiguous`
- [x] T027 Define how internal reshuffles are distinguished from external directional flow

**Checkpoint**: the spec has a real flow plane, not only labels.

---

## Phase 6: Materialization and Serving

- [ ] T028 [E] Decide which entity/flow artifacts must be materialized into QuestDB for serving-grade APIs
- [ ] T029 [E] Define the writer/backfill jobs for registry and flow artifacts
- [ ] T030 Define freshness targets for registry and flow aggregates
- [ ] T031 Define stale, degraded, and ambiguous behavior for entity APIs
- [ ] T032 Decide whether any first slice remains research-only on `:8001` before later promotion
- [ ] T033 Record the security posture decision for entity and flow APIs: auth, rate limiting, input validation, and host exposure
- [ ] T034 [E] Implement local authoritative storage for `entity_registry`, `cluster_entity_map`, `entity_labels`, and `entity_label_provenance`
- [ ] T035 [E] Implement registry writer/backfill path from existing `address_clusters` and curated entity hints
- [ ] T036 [E] Implement movement artifacts for `entity_movement_events`, `entity_transfer_edges`, `entity_flows_daily`, `entity_balance_snapshots_daily`, and `entity_counterparty_edges_daily`
- [ ] T037 [E] Materialize serving-grade entity and flow artifacts into QuestDB with freshness metadata
- [ ] T038 [E] Implement reconciliation and update logic when mapping evidence or labels change

**Checkpoint**: the serving path is operationally plausible and has a real implementation path.

---

## Phase 7: API Surface

- [ ] T039 Freeze the first route family for entity metadata lookup
- [ ] T040 Freeze the first route family for entity history
- [ ] T041 Freeze the first route family for movement and flow queries
- [ ] T042 Define pagination, filtering, and time-window semantics
- [ ] T043 Define omission/degraded behavior for partially resolved counterparties
- [ ] T044 Define compatibility behavior for the canonical whale surface
- [ ] T045 Freeze minimum response shape for entity metadata routes
- [ ] T046 Freeze minimum response shape for entity history routes
- [ ] T047 Freeze minimum response shape for movement and flow routes
- [ ] T048 Write RED tests for entity metadata lookup routes: response shape, confidence fields, degraded/ambiguous behavior
- [ ] T049 Write RED tests for entity history and movement/flow query routes: ordering, pagination, empty-state
- [ ] T050 Write RED tests for internal-reshuffle vs external-flow classification edge cases
- [ ] T051 [E] Implement entity metadata lookup routes
- [ ] T052 [E] Implement entity history routes
- [ ] T053 [E] Implement movement and flow query routes

**Checkpoint**: the entity intelligence plane has a concrete consumer interface with frozen payloads and real implementation tasks.

---

## Phase 8: Whale and Bundle Integration

- [ ] T054 Define how richer registry-backed `entity_id` values appear in whale enrichment without breaking `whale_event.v1`
- [ ] T055 Define whether and when this spec should project into a future `btc_entity.v1` bundle
- [ ] T056 Define whether `btc_flow.v2` should later reference the entity flow plane
- [ ] T057 Keep the existing whale omission and ambiguity guarantees intact while adding richer entity resolution
- [ ] T058 [E] Implement whale surface enrichment upgrade using registry-backed entity objects without breaking `whale_event.v1`

**Checkpoint**: the entity plane integrates forward without breaking current contracts.

---

## Phase 9: Verification and Governance

- [ ] T059 Verify RED tests from T048-T050 now pass GREEN
- [ ] T060 Add contract tests for entity identity and provenance serialization
- [ ] T061 Add tests for ambiguous and unavailable attribution cases
- [ ] T062 Update the feature contract registry if any new route family is admitted
- [ ] T063 Update the provenance manifest for new registry and flow artifacts
- [ ] T064 Update the address-clusters adoption checklist if any BRK-based entity alternative is proposed

**Checkpoint**: the entity plane is explicit, testable, and governance-aligned.
