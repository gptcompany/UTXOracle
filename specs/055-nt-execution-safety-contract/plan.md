# spec-055: Implementation Plan

## Execution Order

```
Phase 1: Execution-State Vocabulary Freeze
├── freeze execution modes
├── freeze fail-closed rule
├── freeze which inputs are eligible to influence execution
└── freeze the separation between trade, manage-only, and halt

Phase 2: Startup and Recovery Semantics
├── define warmup rules
├── define restart behavior
├── define sequence-integrity preconditions
└── define stale-input consequences

Phase 3: Operator Stage and Capital Rollout
├── freeze operator stages
├── define stage transitions
├── define which stages block real capital
└── define how manual approval is recorded

Phase 4: Execution Status Surface
├── freeze the execution-status route
├── freeze payload shape
├── decide how input refs are represented
└── wire state derivation from tier-1 inputs only

Phase 5: NT Integration Discipline
├── define the minimum NT consumer contract
├── define fallback behavior on status uncertainty
├── define replay/live expectations
└── publish operator guidance
```

## Core Principle

The system should never require `NT` to reverse-engineer trading safety from many route-specific payloads. It should expose one bounded execution decision surface that fails closed.

## Decision Gates

### Gate A: Execution Input Discipline

Before any input can influence `trade_enabled`, confirm:

1. the input is in `tier_1_execution`
2. the input has explicit freshness semantics
3. the input has a deterministic failure mode
4. the input adds real safety value

### Gate B: Fail-Closed Behavior

Before allowing any non-halt state under degraded conditions, confirm:

1. the degraded condition is understood
2. the safe allowed action is explicit
3. no ambiguous state can accidentally become `trade_enabled`
4. the outcome is compatible with NT risk policy

### Gate C: Capital Rollout

Before allowing progression to a higher capital stage, confirm:

1. the required checks are explicit
2. the transition is manual or explicitly authorized
3. no automatic capital escalation exists
4. rollback to a safer stage is possible

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| state machine freeze | 1-2 days | highest leverage |
| startup/restart rules | 1-2 days | subtle failure cases |
| status route and payload | 1-2 days | bounded if kept narrow |
| NT alignment and docs | 0.5-1.5 days | should stay simple |
| **Total** | **3.5-7.5 days** | should start immediately after spec-054 |

