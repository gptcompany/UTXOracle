# Tasks: spec-043 Nautilus Trader Live Integration

**Input**: design documents from `/specs/043-nautilus-live-trading-integration/`
**Prerequisites**: `spec.md`, `plan.md`, spec-041 completion

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex integration task

---

## Phase 1: Contract and Safety Rules

- [x] T001 Define the minimal tradable field whitelist
- [x] T002 Define the field ownership map: live API-produced vs adapter-derived fields
- [x] T003 Decide whether missing admitted fields such as `sequence_id` and `source_spread_bps` are added to the live contract or derived deterministically in-adapter
- [x] T004 Define freshness thresholds for accepted snapshots
- [x] T005 Define monotonicity rules for timestamp, block height, and sequence id
- [x] T006 Define required source-health combinations for accepted snapshots
- [x] T007 Define anomaly thresholds and circuit breaker rules
- [x] T008 Define recovery rules for `STATUS_HALT` and `STATUS_LIQUIDATE_ONLY`

**Checkpoint**: the adapter knows exactly what is safe to consume.

---

## Phase 2: RED Safety Tests

- [x] T009 Add failing tests for contract normalization and field ownership rules
- [x] T010 Add failing tests for freshness, health, anomaly, and monotonicity gates
- [x] T011 Add failing tests for kill-switch, recovery, and fail-closed behavior

**Checkpoint**: safety behavior is test-defined before adapter implementation starts.

---

## Phase 3: Adapter Implementation

- [x] T012 Create Nautilus integration module or package scaffold
- [x] T013 Implement polling client for the production live snapshot endpoint
- [x] T014 Implement snapshot normalization into Nautilus-consumable objects
- [x] T015 Implement required live-contract extensions or adapter-side derivations for admitted fields such as `sequence_id` and `source_spread_bps`
- [x] T016 Implement last-seen monotonicity tracking and backward-move rejection under the explicit re-org policy
- [x] T017 Add accept/reject decision logging with explicit reasons

**Checkpoint**: Nautilus can ingest the production contract in a controlled way.

---

## Phase 4: Replay and Paper Trading

- [x] T018 Implement recent-history replay from QuestDB-backed live history
- [x] T019 Add paper trading mode
- [x] T020 Add shadow/live-read mode without order routing
- [x] T021 Implement operator kill-switch check and fail-closed behavior
- [x] T022 Verify deterministic behavior on stale, degraded, anomalous, and backward-moving snapshots

**Checkpoint**: the adapter is usable without taking live trading risk.

---

## Phase 5: Rollout

- [x] T023 Add tests for end-to-end adapter behavior across replay, paper, and shadow modes
- [x] T024 Document live rollout order and operational kill-switch behavior
- [x] T025 Add operator runbook for enabling Nautilus integration safely

**Checkpoint**: the adapter is ready for controlled rollout.
