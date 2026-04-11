# Decision Log: spec-057 Data Quality, Reconciliation, and Restatement

This file records the binding outputs of `Freeze` and `Decide` tasks from [tasks.md](/media/sam/1TB/UTXOracle/specs/057-data-quality-reconciliation-and-restatement/tasks.md).

Usage:

- fill one row when the referenced task is actually resolved
- keep `Decision` short and final; do not paste exploratory notes
- use `Binding For` to name the downstream tasks, phases, or artifacts that inherit the decision
- use `Source Ref` to point to the spec section, commit, or implementation artifact that made the decision effective

Expected coverage: 13 binding decision rows.

| Phase | Task | Topic | Decision | Binding For | Source Ref |
|-------|------|-------|----------|-------------|------------|
| Phase 1 | T001 | scope boundary | data quality, reconciliation, quarantine, and restatement for execution-relevant surfaces only | T002-T036, non-goal enforcement | spec.md#problem-statement |
| Phase 1 | T002 | quality vocabulary | exactly `valid`, `suspect`, `quarantined`, `restated`, with `restated` modeled as a correction overlay rather than a current runtime state | T003-T036, surface semantics, docs | spec.md#1-data-quality-states |
| Phase 1 | T003 | first-slice scope of quality state | live snapshot, bundles, signals, and execution-driving inputs | T007-T036, contract artifacts | spec.md#1-data-quality-states |
| Phase 1 | T004 | visibility versus execution eligibility | data may remain visible to operators without remaining execution-safe | T013-T036, operator docs, spec-055 coupling | spec.md#1-data-quality-states |
| Phase 1 | T005 | runtime quality state versus historical correction | `valid`/`suspect`/`quarantined` describe current evaluation state; `restated` is a correction overlay on previously published data | T006-T036, serving logic, docs | spec.md#1-data-quality-states |
| Phase 1 | T006 | restatement-worthy event definition | historical correction that changes previously published execution-relevant meaning must emit explicit restatement artifact | T018-T036, audit trail | spec.md#4-restatement-model |
| Phase 2 | T007 | ingest validation layer | tier-1 inputs require ingest validation before normal materialization trust is assumed | T008-T036, storage design | spec.md#2-validation-layers |
| Phase 2 | T012 | source-of-truth-aware reconciliation | upstream disagreement must be interpreted through the metric source-of-truth manifest rather than treated uniformly | T013-T036, telemetry and restatement design | spec.md#3-reconciliation-direction |
| Phase 3 | T014 | quarantine escalation rule | materially unsafe conditions escalate to `quarantined` and cannot coexist with execution-safe operation | T015-T036, spec-055 coupling | spec.md#1-data-quality-states |
| Phase 4 | T018 | minimum restatement artifact | restatement_id, issued_at, affected_surface, affected_time_range, severity, reason, supersedes_ref | T019-T036, audit and serving logic | spec.md#4-restatement-model |
| Phase 5 | T023 | execution consequence of `suspect` | suspect tier-1 data must downgrade execution explicitly or be allowlisted by written rule; it cannot silently remain equivalent to valid | T024-T036, execution-state logic | spec.md#5-execution-coupling |
| Phase 5 | T024 | execution consequence of `quarantined` | quarantined tier-1 data cannot coexist with `trade_enabled` | T025-T036, execution-state logic | spec.md#5-execution-coupling |
| Phase 5 | T025 | unresolved critical restatement rule | unresolved critical restatement on tier-1 data cannot coexist with `trade_enabled` | T026-T036, execution-state logic | spec.md#5-execution-coupling |
