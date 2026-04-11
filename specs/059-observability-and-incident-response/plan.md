# spec-059: Implementation Plan

## Execution Order

```
Phase 1: Telemetry Scope Freeze
├── freeze which metrics matter for tier-1 execution
├── freeze alert severity vocabulary
├── freeze which incidents matter operationally
└── separate dashboards from execution evidence

Phase 2: Alert and Severity Model
├── define warning, critical, and fatal thresholds
├── map metric families to alert classes
├── define when execution must degrade or halt
└── avoid alert spam by keeping the model narrow

Phase 3: Runbook Set
├── define minimum runbooks
├── define first operator actions
├── define recovery confirmation checks
└── align runbooks with the execution-state machine

Phase 4: Incident Artifact Model
├── define the minimum incident record
├── define evidence required after recovery
├── define follow-up expectations
└── keep the artifact lightweight and repeatable

Phase 5: Governance and Service Wiring
├── connect telemetry to tier-1 surfaces
├── connect alerts to execution modes
├── publish operator docs
└── align with SLO and data-quality specs
```

## Core Principle

Observability is only useful here if it answers one operational question fast: should the service keep influencing live capital right now or not?

## Decision Gates

### Gate A: Metric Admission

Before adding a new canonical execution metric, confirm:

1. it informs an actual operator action
2. it supports a tier-1 surface or execution decision
3. it is cheap enough to maintain
4. it is not already implied by a simpler metric

### Gate B: Alert Severity

Before classifying an alert as `critical` or `fatal`, confirm:

1. the condition materially threatens execution trust
2. the operator action is explicit
3. the severity maps to execution-state consequences
4. the classification will not create noise without actionability

### Gate C: Runbook Coverage

Before declaring observability sufficient, confirm:

1. each critical failure mode has a runbook
2. first operator action is explicit
3. recovery confirmation is explicit
4. evidence collection is explicit

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| telemetry and alert model | 1-2 days | keep narrow |
| runbooks and incident artifact shape | 1-2 days | practical operator value |
| governance and service wiring | 0.5-1.5 days | connect to other specs |
| **Total** | **2.5-5.5 days** | best done after SLO and quality rules are frozen |

