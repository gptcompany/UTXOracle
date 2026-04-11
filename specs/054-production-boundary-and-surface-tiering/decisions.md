# Decision Log: spec-054 Production Boundary and Surface Tiering

This file records the binding outputs of `Freeze` and `Decide` tasks from [tasks.md](/media/sam/1TB/UTXOracle/specs/054-production-boundary-and-surface-tiering/tasks.md).

Usage:

- fill one row when the referenced task is actually resolved
- keep `Decision` short and final; do not paste discussion transcripts
- use `Binding For` to name the downstream tasks, phases, or artifacts that inherit the decision
- use `Source Ref` to point to the spec section, commit, or implementation artifact that made the decision effective

Expected coverage: 13 binding decision rows.

| Phase | Task | Topic | Decision | Binding For | Source Ref |
|-------|------|-------|----------|-------------|------------|
| Phase 1 | T001 | scope boundary | production boundary and execution eligibility only; excludes strategy logic, broad auth redesign, and feature expansion | T002-T033, non-goal enforcement | spec.md#problem-statement |
| Phase 2 | T006 | tier vocabulary | exactly `tier_1_execution`, `tier_2_operator`, `tier_3_research` | T007-T033, docs, boundary artifact | spec.md#1-service-tier-model |
| Phase 2 | T007 | tier semantics | tier 1 may drive NT; tier 2 is non-execution operator/validation/forensics; tier 3 is research-only and non-execution | T008-T033, service profile, runtime guidance | spec.md#1-service-tier-model |
| Phase 2 | T008 | canonical NT consumer rule | NT may consume only `tier_1_execution` surfaces | T018-T033, spec-055 dependency | spec.md#3-canonical-consumer-rule |
| Phase 2 | T009 | `:8001` classification | `:8001` remains `tier_3_research` / transition by default | T018-T033, boundary docs | spec.md#2-proposed-initial-tiering |
| Phase 2 | T010 | transitional `:8011` non-execution exposure | `tier_2_operator` and narrowly scoped `tier_3_research` families may remain exposed on `:8011` only if explicitly marked non-execution | T017-T033, runtime/docs alignment | spec.md#4-runtime-exposure-policy |
| Phase 3 | T012 | live family classification | `/health` and `/api/v1/live/*` are `tier_1_execution` | T018-T033, NT guidance | spec.md#2-proposed-initial-tiering |
| Phase 3 | T013 | bundle and signal classification | `/api/features/btc/*` and `/api/signals/btc/*` are `tier_1_execution` | T018-T033, spec-055 inputs | spec.md#2-proposed-initial-tiering |
| Phase 3 | T014 | prices and compact metrics classification | `/api/prices/*` and `/api/metrics/latest` are `tier_2_operator` in the first execution slice (conservative: not required by NT for execution gating); promotion to `tier_1_execution` available via T027 change-control rule | T018-T033, service profile | spec.md#2-proposed-initial-tiering |
| Phase 3 | T015 | materialized cohort and cost-basis classification | `/api/metrics/address-cohorts`, `/api/metrics/cost-basis`, `/api/metrics/wallet-waves`, and `/api/metrics/absorption-rates` are `tier_2_operator` in the first slice | T018-T033, service profile, non-execution docs | spec.md#2-proposed-initial-tiering |
| Phase 3 | T016 | whale and entity classification | `/api/whale/*` and `/api/entities/*` are `tier_2_operator` in the first slice | T018-T033, operator-only guidance | spec.md#2-proposed-initial-tiering |
| Phase 3 | T017 | chart, meta, and research classification | `/api/v1/charts/*`, `/charts/*`, and `/api/meta/features` are `tier_2_operator`; `/api/research/tier-stats` is `tier_3_research` even if still exposed on `:8011` | T018-T033, boundary docs, transition policy | spec.md#2-proposed-initial-tiering |
| Phase 4 | T019 | canonical boundary artifact | one boundary artifact must list route family, host, tier, allowed consumers, source of truth, fail mode, execution eligibility | T020-T033, future boundary changes | spec.md#5-boundary-artifact |
