# Decision Log: spec-055 NT Execution Safety Contract

This file records the binding outputs of `Freeze` and `Decide` tasks from [tasks.md](/media/sam/1TB/UTXOracle/specs/055-nt-execution-safety-contract/tasks.md).

Usage:

- fill one row when the referenced task is actually resolved
- keep `Decision` short and final; do not paste exploratory notes
- use `Binding For` to name the downstream tasks, phases, or artifacts that inherit the decision
- use `Source Ref` to point to the spec section, commit, or implementation artifact that made the decision effective

Expected coverage: >20 binding decision rows.

| Phase | Task | Topic | Decision | Binding For | Source Ref |
|-------|------|-------|----------|-------------|------------|
| Phase 1 | T001 | scope boundary | execution safety state only; excludes strategy alpha, sizing formulas, and exchange OMS details | T002-T039, non-goal enforcement | spec.md#problem-statement |
| Phase 1 | T002 | execution mode vocabulary | exactly `halted`, `warming_up`, `observe_only`, `manage_only`, `trade_enabled` | T005-T039, route payloads, NT docs | spec.md#1-execution-modes |
| Phase 1 | T003 | fail-closed rule | unknown or ambiguous safety state resolves to `halted` | T010-T039, startup and route logic | spec.md#2-fail-closed-rule |
| Phase 1 | T004 | execution input eligibility | only `tier_1_execution` inputs may influence `trade_enabled` | T006-T039, spec-054 dependency | spec.md#3-minimum-inputs |
| Phase 1 | T005 | new-risk vs risk-reduction separation | `manage_only` may reduce or neutralize risk but must not add new directional exposure | T010-T039, NT rulebook | spec.md#1-execution-modes |
| Phase 1 | T006 | legacy adapter compatibility | older `STATUS_OK` / `STATUS_LIQUIDATE_ONLY` / `STATUS_HALT` states remain compatibility aliases only; the new execution-mode surface is authoritative | T007-T039, NT transition docs | spec.md#current-baseline |
| Phase 2 | T007 | minimum execution input set | `/health`, `/api/v1/live/snapshot`, the four `/api/features/btc/*/latest`, and `/api/signals/btc/latest` | T008-T039, execution route implementation | spec.md#3-minimum-inputs |
| Phase 2 | T008 | `/health` role | `/health` is a blocking corroboration input only; healthy `/health` alone cannot promote `trade_enabled` | T009-T039, state derivation, tests | spec.md#3-minimum-inputs |
| Phase 2 | T009 | bundle and signal freshness | stale >= 30s for snapshot, >= 60s for bundle/signal downgrades execution | T010-T039, execution route logic | spec.md#2-fail-closed-rule |
| Phase 2 | T010 | monotonic sequence | violated sequence guarantee triggers downgrade or halt | T011-T039, execution route logic | spec.md#2-fail-closed-rule |
| Phase 2 | T011 | confidence and anomaly mapping | low-confidence and anomaly-bearing tier-1 inputs must downgrade execution explicitly rather than remaining implicit adapter-side concerns | T012-T039, execution route logic, NT transition docs | spec.md#3-minimum-inputs |
| Phase 3 | T012 | startup behavior | default to `warming_up` after process start until explicit warmup criteria pass | T013-T039, state-machine tests | spec.md#4-startup-and-recovery-rules |
| Phase 3 | T013 | restart behavior | default to `warming_up` or `observe_only` after process crash until explicit warmup criteria pass | T014-T039, state-machine tests | spec.md#4-startup-and-recovery-rules |
| Phase 3 | T014 | warmup criteria direction | require consecutive valid reads, sequence monotonicity confirmation, and freshness within SLO before `trade_enabled` | T015-T039, spec-056 dependency | spec.md#4-startup-and-recovery-rules |
| Phase 3 | T015 | history and replay continuity | inability to verify continuity during warmup keeps system in a safe non-trading mode | T016-T039, startup and recovery | spec.md#4-startup-and-recovery-rules |
| Phase 3 | T016 | stale and sequence gaps | unresolved stale or sequence gap conditions force `halted` | T017-T039, state-machine tests | spec.md#2-fail-closed-rule |
| Phase 4 | T017 | operator-stage vocabulary | exactly `shadow`, `paper_live`, `canary_capital`, `full_capital` | T018-T039, operator docs | spec.md#5-capital-rollout-stages |
| Phase 4 | T018 | allowed execution modes per stage | operator stage constrains maximum allowed mode (e.g., `shadow` limits to `observe_only`) | T019-T039, stage gating | spec.md#5-capital-rollout-stages |
| Phase 4 | T019 | stage transition rule | progression between operator stages requires explicit operator action and validation; never implicit | T020-T039, incident/runbook coupling | spec.md#5-capital-rollout-stages |
| Phase 4 | T020 | rollback behavior | rollback to a safer stage requires explicit action or fallback to safe non-trading mode | T021-T039, runbook | spec.md#5-capital-rollout-stages |
| Phase 4 | T021 | stage change artifact | explicit artifact/configuration update and validation checklist required | T022-T039, implementation | spec.md#5-capital-rollout-stages |
| Phase 5 | T022 | canonical execution-status route | `GET /api/execution/btc/status` in the first slice | T023-T039, NT integration docs | spec.md#6-preferred-contract-shape |
| Phase 5 | T023 | minimum execution-status payload | execution_mode, status_reason, compatibility_status, evaluated_at, input_refs, freshness_summary, sequence_summary, restatement_status, operator_stage | T024-T039, contract tests | spec.md#6-preferred-contract-shape |