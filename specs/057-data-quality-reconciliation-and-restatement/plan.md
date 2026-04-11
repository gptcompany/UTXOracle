# spec-057: Implementation Plan

## Execution Order

```
Phase 1: Quality-State Model Freeze
├── freeze the bounded quality vocabulary
├── freeze where quality state applies
├── separate visibility from execution eligibility
└── define what counts as a restatement-worthy event

Phase 2: Validation and Reconciliation Layers
├── define ingest validation
├── define materialization validation
├── define serve-time validation
└── define cross-source and continuity reconciliation

Phase 3: Quarantine and Restatement Rules
├── define suspect versus quarantined behavior
├── define restatement artifact shape
├── define historical supersession rules
└── define operator visibility and audit trail

Phase 4: Execution Coupling
├── map quality states into execution consequences
├── define unresolved-restatement behavior
├── define sequence and continuity escalation
└── keep the fail-closed rule simple

Phase 5: Storage, Serving, and Governance
├── decide where quality and restatement artifacts live
├── decide how they are referenced from tier-1 surfaces
├── align with provenance and contract artifacts
└── publish operator guidance
```

## Core Principle

For live trading, "data exists" is not enough. The service must distinguish valid, suspect, quarantined, and corrected data explicitly, and that distinction must have execution consequences.

## Decision Gates

### Gate A: Quality-State Simplicity

Before adding another quality label or status, confirm:

1. the existing bounded states are not enough
2. the new state changes an operator or execution action materially
3. the new state is maintainable across tier-1 surfaces
4. the new state is not just diagnostic noise

### Gate B: Quarantine Thresholds

Before moving a condition from `suspect` to `quarantined`, confirm:

1. the condition is materially unsafe for execution
2. the escalation is deterministic
3. the operator can see why the escalation happened
4. the consequence is compatible with spec-055 fail-closed behavior

### Gate C: Restatement Discipline

Before allowing any historical correction, confirm:

1. the correction is explicit, not silent
2. the affected surface and time range are recorded
3. the superseded artifact can be identified
4. execution consequences are defined

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| quality-state and validation design | 1-2 days | should stay narrow |
| reconciliation and quarantine rules | 1-2 days | execution-sensitive |
| restatement artifact design | 1-2 days | auditability matters |
| governance and coupling | 0.5-1.5 days | docs plus execution alignment |
| **Total** | **3.5-7.5 days** | best done before live-capital use |

