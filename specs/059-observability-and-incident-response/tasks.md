# Tasks: spec-059 Observability and Incident Response

**Input**: design documents from `/specs/059-observability-and-incident-response/`
**Prerequisites**: `spec.md`, `plan.md`, `spec-054`, `spec-055`, `spec-056`, `spec-057`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: operationally critical instrumentation or incident-governance change

---

## Phase 1: Telemetry Scope Freeze

- [x] T001 Freeze the scope: tier-1 execution observability and incident handling only
- [x] T002 Freeze the canonical metric families required for tier-1 surfaces, including execution-state telemetry
- [x] T003 Freeze the alert severity vocabulary to `warning`, `critical`, `fatal`
- [x] T004 Define which failure modes qualify as incidents in the first slice
- [x] T005 Freeze the rule that execution observability must remain narrower than general dashboard curiosity and generic app `/health` or `/metrics` comfort signals

**Checkpoint**: the telemetry model is bounded before implementation expands.

---

## Phase 2: Alert and Severity Model

- [x] T006 Define alert conditions for tier-1 latency and error rate
- [x] T007 Define alert conditions for live snapshot, bundle, and signal freshness
- [x] T008 Define alert conditions for sequence monotonicity and gap detection
- [x] T009 Define alert conditions for divergence, quarantine, and restatement events
- [x] T010 Define how `warning`, `critical`, and `fatal` map into execution consequences and alert-clearance rules

**Checkpoint**: alerting is tied to action, not just visibility.

---

## Phase 3: Runbook Set

- [x] T011 Freeze the minimum runbook set: stale live snapshot, tier-1 endpoint failure, sequence gap, divergence spike, QuestDB unavailable, execution-affecting restatement, execution-status unavailable or inconsistent
- [x] T012 Define the first operator action for each runbook
- [x] T013 Define the recovery confirmation checks for each runbook
- [x] T014 Define when the runbook requires execution halt versus manage-only behavior
- [x] T015 Define where the dedicated execution-grade runbooks live and how they are referenced from incidents or alerts

**Checkpoint**: critical failures now have explicit operator procedures.

---

## Phase 4: Incident Artifact Model

- [x] T016 Freeze the minimum incident artifact shape
- [x] T017 Define required fields for incident start/end, triggering evidence, affected surfaces, execution consequence, and operator action
- [x] T018 Define the minimum evidence required before closing a critical or fatal incident
- [x] T019 Define the follow-up artifact or accepted-risk note after incident closure

**Checkpoint**: incident handling leaves usable evidence.

---

## Phase 5: Governance and Service Wiring

- [x] T020 [E] Connect canonical telemetry requirements to real tier-1 service surfaces
- [x] T021 [E] Connect severity thresholds and clearance rules to `spec-055` execution modes
- [x] T022 Align observability docs with the SLO thresholds from `spec-056`
- [x] T023 Align incident consequences with data-quality and restatement events from `spec-057`
- [x] T024 Update operator docs with the frozen telemetry, severity, runbook, and incident artifact model

**Checkpoint**: observability becomes an execution support layer, not a side system.

---

## Phase 6: Verification

- [x] T025 Verify all tier-1 surfaces have canonical telemetry coverage
- [x] T026 Verify every critical execution-affecting failure mode has a runbook
- [x] T027 Verify incident severity maps cleanly into execution consequences and recovery clearance conditions
- [x] T028 Verify the incident artifact is lightweight enough to be used consistently
- [x] T029 Verify the observability layer remains narrow and maintainable

**Checkpoint**: the operator can use the observability model under stress, not only in theory.
