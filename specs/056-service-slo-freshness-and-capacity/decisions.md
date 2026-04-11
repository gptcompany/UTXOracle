# Decision Log: spec-056 Service SLO, Freshness, and Capacity

This file records the binding outputs of `Freeze` and `Decide` tasks from [tasks.md](/media/sam/1TB/UTXOracle/specs/056-service-slo-freshness-and-capacity/tasks.md).

Usage:

- fill one row when the referenced task is actually resolved
- keep `Decision` short and final; do not paste exploratory notes
- use `Binding For` to name the downstream tasks, phases, or artifacts that inherit the decision
- use `Source Ref` to point to the spec section, commit, or implementation artifact that made the decision effective

Expected coverage: 20 binding decision rows.

| Phase | Task | Topic | Decision | Binding For | Source Ref |
|-------|------|-------|----------|-------------|------------|
| Phase 1 | T001 | scope boundary | execution-grade internal SLOs only; not public commercial SLA commitments | T002-T029, docs, runbooks | spec.md#problem-statement |
| Phase 1 | T002 | strict SLO scope | strict SLOs apply only to `tier_1_execution` surfaces in the first slice | T004-T029, spec-055 coupling | spec.md#1-slo-scope |
| Phase 1 | T003 | deployment assumption | local single-host deployment with one serious automated consumer, future local execution-status reads, and light operator usage | T017-T029, capacity docs | spec.md#4-capacity-assumption |
| Phase 1 | T004 | tier-1 route targets | `latest` live snapshots, feature bundles, signal snapshots, and the future `spec-055` execution-status route require explicit latency, freshness, and availability targets | T012-T029, capacity docs | spec.md#1-slo-scope |
| Phase 1 | T005 | best-effort routes | `tier_2_operator` surfaces, historical research routes, and public API endpoints remain best-effort | T012-T029, docs, alerting | spec.md#1-slo-scope |
| Phase 2 | T006 | freshness vocabulary | exactly `healthy`, `degraded`, `stale` for tier-1 data | T007-T029, route semantics, spec-055 coupling | spec.md#3-freshness-classes |
| Phase 2 | T007 | live snapshot healthy freshness target | `<= 15s` | T010-T029, execution-state thresholds | spec.md#2-first-slice-service-targets |
| Phase 2 | T008 | bundle healthy freshness target | `<= 30s` | T010-T029, execution-state thresholds | spec.md#2-first-slice-service-targets |
| Phase 2 | T009 | signal healthy freshness target | `<= 30s` | T010-T029, execution-state thresholds | spec.md#2-first-slice-service-targets |
| Phase 2 | T010 | maximum stale thresholds | live snapshot becomes `stale` at `>= 30s`; bundles and signals become `stale` at `>= 60s` (boundary-inclusive; freshness measured as `now() - latest_block_or_capture_timestamp`) | T011-T029, execution-state thresholds, alerts | spec.md#2-first-slice-service-targets |
| Phase 2 | T011 | freshness alignment | freshness classes (`healthy`, `degraded`, `stale`) mean the same thing and dictate the same trading behavior across all tier-1 surfaces | T012-T029, spec-055 coupling | spec.md#3-freshness-classes |
| Phase 3 | T012 | `/health` p95 target | `<= 100ms` local p95 | T013-T029, telemetry and ops docs | spec.md#2-first-slice-service-targets |
| Phase 3 | T013 | tier-1 latest-read p95 target | `<= 250ms` local p95 | T014-T029, capacity and alerting | spec.md#2-first-slice-service-targets |
| Phase 3 | T014 | bounded history p95 target | `<= 1000ms` local p95 | T015-T029, capacity and alerting | spec.md#2-first-slice-service-targets |
| Phase 3 | T015 | monthly availability target | `99.5%` for `tier_1_execution` read availability | T016-T029, ops docs, incident severity | spec.md#2-first-slice-service-targets |
| Phase 3 | T016 | target violation severity | `degraded` freshness or latency warnings are operator-visible; `stale` data or availability failures block trading execution | T021-T029, alerting | spec.md#5-execution-coupling |
| Phase 4 | T017 | intended consumer model | one serious NT consumer plus light operator load | T018-T029, capacity verification | spec.md#4-capacity-assumption |
| Phase 4 | T018 | polling-cadence assumption | steady-state tier-1 latest polling assumption is up to every `5s` for the first slice | T019-T029, capacity verification, ops docs | spec.md#4-capacity-assumption |
| Phase 4 | T019 | out-of-scope load | multi-region availability, internet-scale public API load, commercial customer SLA credits, benchmarking historical routes | T020-T029, architecture | spec.md#non-goals |
| Phase 4 | T020 | capacity verification | burst tolerance for retries/dashboards and steady-state local p95 latency under `5s` polling | T021-T029, capacity docs | spec.md#4-capacity-assumption |
