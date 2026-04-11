# Decision Log: spec-058 Schema Evolution and Deprecation Policy

This file records the binding outputs of `Freeze` and `Decide` tasks from [tasks.md](/media/sam/1TB/UTXOracle/specs/058-schema-evolution-and-deprecation-policy/tasks.md).

Usage:

- fill one row when the referenced task is actually resolved
- keep `Decision` short and final; do not paste exploratory notes
- use `Binding For` to name the downstream tasks, phases, or artifacts that inherit the decision
- use `Source Ref` to point to the spec section, commit, or implementation artifact that made the decision effective

Expected coverage: 12 binding decision rows.

| Phase | Task | Topic | Decision | Binding For | Source Ref |
|-------|------|-------|----------|-------------|------------|
| Phase 1 | T001 | scope boundary | execution-grade contract evolution only; not every internal model in the repo | T002-T024, non-goal enforcement | spec.md#problem-statement |
| Phase 1 | T002 | change-class vocabulary | exactly `docs_only`, `additive_non_breaking`, `behavioral_tightening`, `breaking`; map execution-grade `behavioral_tightening` to the older repo-wide `caveat change` term and treat deprecation as a lifecycle overlay | T003-T024, review checklist, docs | spec.md#1-change-classes |
| Phase 1 | T003 | breaking shape rule | removal, rename, required-field incompatibility, or incompatible contract split counts as breaking | T004-T024, version policy | spec.md#1-change-classes |
| Phase 1 | T004 | breaking semantic rule | silent semantic repurposing of an existing field counts as breaking | T005-T024, compatibility gate | spec.md#1-change-classes |
| Phase 1 | T005 | current major-version rule | execution-grade `v1` surfaces are additive-only by default | T006-T024, registry alignment | spec.md#2-major-version-rule |
| Phase 2 | T006 | major-version requirement | breaking changes require a new major version | T007-T024, migration policy | spec.md#2-major-version-rule |
| Phase 2 | T007 | deprecation window | minimum `30 day` deprecation window for execution-grade breaking replacement unless emergency override is recorded | T008-T024, rollout docs | spec.md#3-deprecation-window |
| Phase 2 | T008 | parallel overlap | parallel overlap is expected for all execution-grade breaking replacements where practical; skipping overlap must be justified and recorded | T009-T024, rollout strategy | spec.md#2-major-version-rule |
| Phase 2 | T009 | emergency override | emergency overrides require recording: reason, affected surfaces, operator name, and expiration date in the decision log | T010-T024, operator safety | spec.md#3-deprecation-window |
| Phase 2 | T010 | migration note | breaking replacements require a migration note covering: compatibility impact, rationale, and explicit transition steps | T011-T024, consumer guidance | spec.md#2-major-version-rule |
| Phase 3 | T011 | route-contract compatibility gate | schema-affecting or `behavioral_tightening` promotions require route contract validation | T012-T024, change-control workflow | spec.md#4-nt-compatibility-gate |
| Phase 3 | T012 | replay compatibility gate | schema-affecting or `behavioral_tightening` promotions require replay compatibility verification | T013-T024, promotion workflow | spec.md#4-nt-compatibility-gate |
| Phase 3 | T013 | NT compatibility gate | schema-affecting or `behavioral_tightening` promotions require NT adapter compatibility verification | T014-T024, promotion workflow | spec.md#4-nt-compatibility-gate |
| Phase 3 | T014 | explicit signoff threshold | `behavioral_tightening` and `breaking` changes require explicit compatibility signoff; purely additive changes still require registry and contract updates but not full replay/NT signoff by default | T015-T024, promotion workflow | spec.md#4-nt-compatibility-gate |
| Phase 3 | T015 | compatibility evidence location | compatibility evidence is recorded in the decision log of the owning spec and cross-referenced from the feature contract registry entry; no separate compatibility store in the first slice | T016-T024, registry alignment | spec.md#4-nt-compatibility-gate |
