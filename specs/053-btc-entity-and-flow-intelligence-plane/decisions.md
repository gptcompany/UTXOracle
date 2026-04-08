# Decision Log: spec-053 BTC Entity and Flow Intelligence Plane

This file records the binding outputs of `Freeze` and `Decide` tasks from [tasks.md](/media/sam/1TB/UTXOracle/specs/053-btc-entity-and-flow-intelligence-plane/tasks.md).

Usage:

- fill one row when the referenced task is actually resolved
- keep `Decision` short and final; do not paste exploratory notes
- use `Binding For` to name the downstream tasks, phases, or artifacts that inherit the decision
- use `Source Ref` to point to the spec section, commit, or implementation file that made the decision effective

Expected coverage: 19 binding decision rows.

| Phase | Task | Topic | Decision | Binding For | Source Ref |
|-------|------|-------|----------|-------------|------------|
| Phase 1 | T001 | intelligence-plane boundary | Entity identity, provenance, and flow-of-funds forensics; excluding trading/execution logic and AML/sanctions products | T002-T064, non-goal enforcement, implementation scope | spec.md#problem-statement |
| Phase 1 | T002 | base vocabulary freeze | address, cluster_id, entity_id, entity_label, mapping_confidence, label_confidence, confidence_overall | T006-T064, serialization, API payloads, docs | spec.md#1-identity-model |
| Phase 1 | T003 | canonical `entity_id` format and namespace | btc:entity:<namespace>:<stable_id>; namespaces: cluster, curated, external; compatible with cluster:{id} alias | T006-T020, T039-T061, whale compatibility, registry serialization | spec.md#1-identity-model |
| Phase 1 | T004 | deep API namespace | /api/entities/* (research-first); later projection to btc_entity.v1 | T039-T064, route docs, admission/gov artifacts | spec.md#8-api-namespace |
| Phase 1 | T005 | baseline heuristics inventory | Union-find MIH, CAH, CoinJoin detection, change filtering, DuckDB sync to QuestDB address_clusters | T016-T017 (must not reinvent existing clustering) | spec.md#existing-heuristics-and-infrastructure |
| Phase 2 | T010 | local-authoritative vs QuestDB artifacts | Authoritative registry & provenance in local DuckDB/curated files; materialized serving copies in QuestDB | T028-T038, T051-T064, serving architecture | spec.md#7-serving-architecture |
| Phase 2 | T011 | registry and label status vocabulary | Registry: active, candidate, deprecated; Label: verified, provisional, stale | T034-T038, T045-T047, T060-T063 | spec.md#2-registry-model |
| Phase 3 | T012 | separate confidence fields | cluster_confidence, mapping_confidence, label_confidence, confidence_overall | T014-T015, T045, T048, T060-T061 | spec.md#3-confidence-model |
| Phase 3 | T013 | provenance vocabulary | source_kind: heuristic, curated_csv, manual, external, inherited; review_status: unreviewed, provisional, reviewed, deprecated | T018-T020, T045-T047, T060-T063 | spec.md#4-provenance-model |
| Phase 5 | T026 | movement classification vocabulary | exchange_inflow, exchange_outflow, entity_to_entity, entity_to_unlabeled, unlabeled_to_entity, internal_entity_reshuffle, ambiguous | T027, T036, T041, T047, T050, T053, T061 | spec.md#6-movement-classification |
| Phase 6 | T028 | QuestDB materialization scope | Materialize registry, daily flows, and balance snapshots; raw movement events remain local/research only | T029-T038, T051-T064 | design_materialization.md#1-materialization-scope-questdb |
| Phase 6 | T032 | first-slice host boundary (`:8001` vs serving-grade) | Materialized registry and flows admitted to `:8011`; raw forensics remain on `:8001` | T033, T039-T064, exposure decisions, docs | design_materialization.md#41-host-policy |
| Phase 6 | T033 | entity and flow API security posture | `:8011` inherits whale GET policy (no auth, standard rate limit); `:8001` requires internal auth | T039-T064, route exposure, input validation, cross-spec security sync | design_materialization.md#42-auth-and-rate-limiting |
| Phase 7 | T039 | entity metadata route family |  | T045, T048, T051, T058, contract tests |  |
| Phase 7 | T040 | entity history route family |  | T046, T049, T052, contract tests |  |
| Phase 7 | T041 | movement and flow route family |  | T047, T049-T050, T053, T061 |  |
| Phase 7 | T045 | entity metadata response shape |  | T048, T051, T060 |  |
| Phase 7 | T046 | entity history response shape |  | T049, T052, T060 |  |
| Phase 7 | T047 | movement and flow response shape |  | T049-T050, T053, T061 |  |
