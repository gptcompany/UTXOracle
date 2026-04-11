# Tasks: spec-055 NT Execution Safety Contract

**Input**: design documents from `/specs/055-nt-execution-safety-contract/`
**Prerequisites**: `spec.md`, `plan.md`, `spec-054`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: execution-critical integration or boundary task

---

## Phase 1: Execution-State Vocabulary Freeze

- [x] T001 Freeze the scope: this spec governs execution safety state, not alpha or exchange execution details
- [x] T002 Freeze the execution mode vocabulary to exactly `halted`, `warming_up`, `observe_only`, `manage_only`, `trade_enabled`
- [x] T003 Freeze the fail-closed rule for unknown or ambiguous safety state
- [x] T004 Freeze the rule that only `tier_1_execution` inputs may influence `trade_enabled`
- [x] T005 Freeze the difference between new-risk permission and risk-reduction permission
- [x] T006 Define the compatibility relationship between the older `spec-043` adapter statuses and the new service-side execution modes

**Checkpoint**: the state machine boundary is explicit before any endpoint is designed.

---

## Phase 2: Input and Gating Model

- [x] T007 Freeze the minimum execution input set from `tier_1_execution`
- [x] T008 Define how `/health` participates in the execution decision versus pure liveness only
- [x] T009 Define how bundle and signal freshness affect the execution state
- [x] T010 Define how monotonic `sequence_id` behavior affects the execution state
- [x] T011 Define how misconfigured, empty, degraded, stale, low-confidence, and anomaly-bearing tier-1 inputs map into execution modes

**Checkpoint**: the gating model is deterministic and bounded.

---

## Phase 3: Startup, Restart, and Recovery

- [x] T012 Freeze warmup behavior on cold start
- [x] T013 Freeze restart behavior after process crash or service restart
- [x] T014 Freeze minimum consecutive-valid-read criteria before `trade_enabled`
- [x] T015 Freeze the behavior when history or replay continuity cannot be verified
- [x] T016 Freeze the consequence of unresolved stale or sequence-gap conditions during runtime

**Checkpoint**: startup and recovery no longer rely on operator intuition.

---

## Phase 4: Operator Stage and Capital Rollout

- [x] T017 Freeze the operator-stage vocabulary to exactly `shadow`, `paper_live`, `canary_capital`, `full_capital`
- [x] T018 Define the allowed execution modes under each operator stage
- [x] T019 Define the promotion criteria between operator stages
- [x] T020 Define rollback behavior to a safer operator stage
- [x] T021 Define the minimum artifact or acknowledgment needed for a stage change

**Checkpoint**: capital rollout is explicit and non-automatic.

---

## Phase 5: Execution Status Surface

- [x] T022 Freeze the first route family for execution status, likely `GET /api/execution/btc/status`
- [x] T023 Freeze the minimum response payload shape, including compatibility mapping fields if retained
- [x] T024 Freeze how `input_refs`, freshness summary, and sequence summary are represented
- [ ] T025 Write RED tests for execution status: response shape, mode transitions, fail-closed behavior
- [x] T026 [E] Implement execution-state derivation using only tier-1 inputs
- [x] T027 [E] Implement the execution status route
- [ ] T028 Verify RED tests from T025 now pass GREEN

**Checkpoint**: NT can read one canonical safety surface.

---

## Phase 6: NT Alignment and Governance

- [ ] T029 Define the minimum NT consumer rulebook for interpreting the execution surface
- [ ] T030 Define the fallback behavior if the execution endpoint itself is unavailable
- [ ] T031 Define replay/live parity expectations for the execution state
- [ ] T032 Define the explicit compatibility mapping if an older adapter still uses `STATUS_OK`, `STATUS_LIQUIDATE_ONLY`, `STATUS_HALT`
- [ ] T033 Update service docs and consumer docs to reference the execution status route as the only execution safety source
- [ ] T034 Record the dependency this spec has on `spec-056`, `spec-057`, `spec-058`, and `spec-059`

**Checkpoint**: the execution contract is operationally usable, not just implemented.

---

## Phase 7: Verification

- [ ] T035 Verify no `tier_2_operator` or `tier_3_research` route is required for `trade_enabled`
- [ ] T036 Verify ambiguous conditions always downgrade to a safe non-trading mode
- [ ] T037 Verify startup and restart transitions are deterministic
- [ ] T038 Verify operator-stage changes do not happen implicitly
- [ ] T039 Verify the execution safety contract is narrow enough for long-term maintenance

**Checkpoint**: the execution state machine is safe enough to become a hard dependency for NT.
