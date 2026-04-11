# Escalation and Restatement Rules

This document defines the escalation paths, visibility requirements, and the formal restatement model as required by Phases 3 and 4 of spec-057.

## Phase 3: Suspect and Quarantine Rules

### Escalation: Valid to Suspect (T013)
Data transitions from `valid` to `suspect` when:
- It fails non-critical reconciliation checks (e.g., minor divergence from alternative upstream sources for a `local_canonical` metric).
- Non-critical continuity warnings are triggered (e.g., unexpected but technically possible gaps in non-tier-1 telemetry).

### Escalation: Suspect to Quarantined (T014)
Data transitions from `suspect` (or directly from `valid`) to `quarantined` when:
- Materially unsafe conditions are detected, such as missing required execution fields, impossible numeric bounds, or severe temporal regressions.
- Significant divergence from an `adopt_from_brk` upstream occurs, definitively proving local calculation corruption.
- Quarantine escalation is strictly deterministic and never silently ignored.

### Immediate Execution Blockers (T015)
Quarantined conditions immediately block execution for:
- Any tier-1 `latest` data required for execution logic.
- Corrupted `signal` materializations.
- This directly engages the fail-closed requirements of spec-055.

### Operator Visibility and Diagnostics (T016, T017)
- **Visibility**: Both `suspect` and `quarantined` states must explicitly surface their current status in operator dashboards, logging, and telemetry, indicating the reason for the downgrade.
- **Forensic Access**: Quarantined data remains fully persisted and readable through administrative or forensic queries (e.g., diagnostic history endpoints). It is completely masked or gracefully failed-closed in execution-grade APIs.

## Phase 4: Restatement Model

### Minimum Restatement Artifact Shape (T018)
Any historical correction to execution-relevant meaning must emit an explicit restatement artifact with the following required schema:
- `restatement_id`: Unique identifier.
- `issued_at`: Timestamp of the correction.
- `affected_surface`: The specific bundle, signal, or metric namespace.
- `affected_time_range`: Start and end boundaries of the corrected period.
- `severity`: The severity class of the correction.
- `reason`: Human-readable context for the correction.
- `supersedes_ref`: Identifier of the specific prior artifact or snapshot being replaced.

### Surface and Time Range References (T019, T020)
- **Time Ranges**: Must use strictly bounded, inclusive UNIX timestamps or ISO8601 segments to identify affected periods.
- **Superseded Reference**: The `supersedes_ref` must clearly point to the unique `sequence_id`, `bundle_id`, or `snapshot_id` being invalidated, explicitly linking the new correction to the broken historical baseline.

### Severity Classes (T021)
- `INFO`: Non-execution relevant telemetry or cosmetic metadata corrections.
- `MINOR`: Data changes within acceptable execution variance bounds (no retroactive trade impact).
- `CRITICAL`: Material data changes that would have caused a different execution decision during live trading.

### Propagation to Consumers (T022)
- **Latest Consumers**: Unresolved `CRITICAL` restatements must immediately force the tier-1 `latest` surface into a fail-closed/quarantined state until explicitly acknowledged by an operator.
- **History Consumers**: `history` API queries will automatically serve the updated/restated data while attaching the `restated` state overlay as metadata, preserving the audit trail without silently lying about the past.