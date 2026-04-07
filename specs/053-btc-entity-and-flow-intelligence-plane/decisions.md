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
| Phase 1 | T001 | intelligence-plane boundary |  | T002-T064, non-goal enforcement, implementation scope |  |
| Phase 1 | T002 | base vocabulary freeze |  | T006-T064, serialization, API payloads, docs |  |
| Phase 1 | T003 | canonical `entity_id` format and namespace |  | T006-T020, T039-T061, whale compatibility, registry serialization |  |
| Phase 1 | T004 | deep API namespace |  | T039-T064, route docs, admission/gov artifacts |  |
| Phase 1 | T005 | baseline heuristics inventory |  | T016-T017 (must not reinvent existing clustering) |  |
| Phase 2 | T010 | local-authoritative vs QuestDB artifacts |  | T028-T038, T051-T064, serving architecture |  |
| Phase 2 | T011 | registry and label status vocabulary |  | T034-T038, T045-T047, T060-T063 |  |
| Phase 3 | T012 | separate confidence fields |  | T014-T015, T045, T048, T060-T061 |  |
| Phase 3 | T013 | provenance vocabulary |  | T018-T020, T045-T047, T060-T063 |  |
| Phase 5 | T026 | movement classification vocabulary |  | T027, T036, T041, T047, T050, T053, T061 |  |
| Phase 6 | T028 | QuestDB materialization scope |  | T029-T038, T051-T064 |  |
| Phase 6 | T032 | first-slice host boundary (`:8001` vs serving-grade) |  | T033, T039-T064, exposure decisions, docs |  |
| Phase 6 | T033 | entity and flow API security posture |  | T039-T064, route exposure, input validation, cross-spec security sync |  |
| Phase 7 | T039 | entity metadata route family |  | T045, T048, T051, T058, contract tests |  |
| Phase 7 | T040 | entity history route family |  | T046, T049, T052, contract tests |  |
| Phase 7 | T041 | movement and flow route family |  | T047, T049-T050, T053, T061 |  |
| Phase 7 | T045 | entity metadata response shape |  | T048, T051, T060 |  |
| Phase 7 | T046 | entity history response shape |  | T049, T052, T060 |  |
| Phase 7 | T047 | movement and flow response shape |  | T049-T050, T053, T061 |  |
