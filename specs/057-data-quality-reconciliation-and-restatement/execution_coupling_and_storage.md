# Execution Coupling, Storage, and Governance

This document defines how data quality states map directly to spec-055 execution consequences, and where these states and restatement artifacts are persisted, fulfilling Phases 5 and 6 of spec-057.

## Phase 5: Execution Coupling

### Impact on spec-055 Execution Modes (T023, T024, T025)
The data quality model interfaces directly with the execution safety contract (spec-055).

- **Suspect State**: `suspect` tier-1 data immediately triggers `execution_degraded`. If a specific `suspect` condition lacks a written allowlist rule, it must default to forcing `fail_closed` to prioritize execution safety.
- **Quarantined State**: `quarantined` tier-1 data explicitly and unconditionally forces `fail_closed`. `quarantined` data cannot coexist with `trade_enabled`.
- **Restated State**: An unresolved `CRITICAL` restatement forces `fail_closed`. Execution cannot resume on the affected surface until the restatement is explicitly resolved by an operator.

### Continuity Escalation (T026)
- Broken continuity (e.g., missing sequence IDs or out-of-order timestamps) directly escalates the current tier-1 artifact to `suspect` or `quarantined`, depending on severity.
- A missed signal snapshot update extending beyond the maximum freshness SLO forces `quarantined` and triggers `fail_closed`.

### Operator Resolution Flow (T027)
Before `fail_closed` can transition back to `trade_enabled` following a quarantine or critical restatement:
1. The operator must review the diagnostic logs or the restatement artifact.
2. The operator must issue a manual or programmatic acknowledgment (via the management API or CLI) clearing the blocking state.
3. The next tier-1 artifact sequence must generate successfully with a `valid` state.

## Phase 6: Storage, Serving, and Governance

### Persistence Location (T028)
- **Quality States**: Real-time quality states (`valid`, `suspect`, `quarantined`) are embedded directly into the materialized bundles and signals within the `questdb-live` database as an explicit `quality_state` column.
- **Restatement Artifacts**: Restatement artifacts are persisted in a dedicated `data_governance_restatements` table within `questdb-live`, ensuring atomic availability with the time-series data they correct.

### Referencing in Tier-1 Surfaces (T029)
- Tier-1 bundles and signals must include `quality_state` and an optional `active_restatement_id` field in their schemas.
- Serving endpoints (like `/api/metrics/latest`) read these fields. If `quality_state` != `valid` or `active_restatement_id` points to a critical restatement, the endpoint handles the data accordingly, masking the data for execution-grade consumers while keeping it visible to diagnostic endpoints.

### Governance and Documentation (T030, T031)
- **Contract Artifacts**: The `feature_provenance_manifest.yaml` has been updated with the explicit quality-state vocabulary.
- **Operator Docs**: Operational documentation and runbooks must incorporate the four-state quality vocabulary and instruct operators on handling restatements.