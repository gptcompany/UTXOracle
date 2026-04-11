# Decision Log: spec-059 Observability and Incident Response

This file records the binding outputs of `Freeze` and `Decide` tasks from [tasks.md](/media/sam/1TB/UTXOracle/specs/059-observability-and-incident-response/tasks.md).

Usage:

- fill one row when the referenced task is actually resolved
- keep `Decision` short and final; do not paste exploratory notes
- use `Binding For` to name the downstream tasks, phases, or artifacts that inherit the decision
- use `Source Ref` to point to the spec section, commit, or implementation artifact that made the decision effective

Expected coverage: 12 binding decision rows.

| Phase | Task | Topic | Decision | Binding For | Source Ref |
|-------|------|-------|----------|-------------|------------|
| Phase 1 | T001 | scope boundary | tier-1 execution observability and incident handling only | T002-T029, non-goal enforcement | spec.md#problem-statement |
| Phase 1 | T002 | canonical metric families | latency, error rate, freshness, sequence integrity, upstream status, divergence/quarantine counts, restatement counts, and execution-state telemetry | T006-T029, telemetry wiring | spec.md#1-canonical-metric-families |
| Phase 1 | T003 | alert severity vocabulary | exactly `warning`, `critical`, `fatal` | T004-T029, alerting and runbooks | spec.md#2-alert-severity |
| Phase 1 | T004 | incident-qualifying failure modes | only `critical` and `fatal` alerts on tier-1 execution surfaces qualify as incidents requiring artifact generation; `warning` alerts are logged but do not require incident artifacts | T016-T029, incident governance | spec.md#2-alert-severity |
| Phase 1 | T005 | execution observability boundary | generic `/health` or app-level `/metrics` success is corroborative only and cannot alone clear an execution-affecting condition | T006-T029, operator docs, alert clearance logic | spec.md#1-canonical-metric-families |
| Phase 2 | T006 | latency and error alerts | tier-1 latency and error-rate conditions are canonical execution observability inputs | T007-T029, SLO coupling | spec.md#1-canonical-metric-families |
| Phase 2 | T007 | freshness alerts | stale or severely degraded tier-1 freshness is a canonical alert family | T008-T029, spec-056 coupling | spec.md#1-canonical-metric-families |
| Phase 2 | T008 | sequence integrity alerts | sequence_id non-monotonic or gap > 1 is a fatal alert | T011-T029, sequence wiring | spec.md#2-alert-severity |
| Phase 2 | T009 | data quality alerts | divergence spikes, quarantine events, and critical restatements are canonical alert families | T011-T029, spec-057 coupling | spec.md#2-alert-severity |
| Phase 2 | T010 | severity to execution coupling | `warning` → no mode change (investigate within 15min); `critical` → `manage_only` or `halted` per threshold table in spec.md§2; `fatal` → immediate `halted`; clearance requires triggering metric within healthy range for 2 consecutive intervals | T011-T029, spec-055 coupling | spec.md#2-alert-severity |
| Phase 3 | T011 | minimum runbook set | stale live snapshot, tier-1 endpoint failure, bundle/signal sequence gap, divergence spike, QuestDB unavailable, execution-affecting restatement, and execution-status unavailable or inconsistent | T012-T029, operator docs | spec.md#3-minimum-runbooks |
| Phase 4 | T016 | incident artifact minimum | incident start/end, triggering evidence, affected surfaces, execution consequence, operator action, recovery confirmation, follow-up fix or accepted risk | T017-T029, incident docs | spec.md#4-incident-evidence |
| Phase 5 | T021 | execution-state coupling | observability severity and evidence must justify `observe_only`, `manage_only`, or `halted` transitions in spec-055 and cannot override the execution state machine | T022-T029, execution-state implementation | spec.md#5-execution-coupling |
| Phase 5 | T023 | quality and restatement coupling | divergence, quarantine, and restatement events are canonical observability inputs and incident triggers | T024-T029, spec-057 coupling | spec.md#1-canonical-metric-families |
