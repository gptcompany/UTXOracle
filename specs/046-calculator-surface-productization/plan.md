# spec-046: Implementation Plan

## Execution Order

```
Phase 1: Prioritization
├── confirm wave ordering
├── verify calculators exist and are in-scope
├── identify history/materialization requirements
└── define acceptance rules for promotion

Phase 2: RED Tests for Wave 1
├── add failing API tests for address cohorts
├── add failing API tests for wallet waves
├── add failing API tests for absorption rates
└── add degraded and empty-state tests

Phase 3: Wave 1 Wiring
├── connect calculators to API handlers
├── define dependency and failure semantics
├── add optional snapshot persistence support
└── remove `501` responses from promoted routes

Phase 4: History Materialization
├── define snapshot tables for wallet waves
├── define writer/backfill path for absorption rates baseline
├── add history endpoint behavior
└── document baseline-unavailable semantics

Phase 5: Contract and Provenance Update
├── update contract registry
├── update dependency manifest
├── mark remaining `501` routes as future waves
└── publish route support notes

Phase 6: Wave 2 Preparation
├── inventory reserve-risk, NUPL, and cost-basis prerequisites
├── identify missing historical inputs
└── freeze the next promotion plan
```

## Core Principle

Promotion is not wiring alone. A route is productized only when runtime behavior, history requirements, and failure semantics are explicit.

## Decision Gates

### Gate A: Wave Admission

Before including a route in a wave, confirm:

1. the calculator exists
2. the response model is already defined or can be finalized
3. dependencies are known
4. history requirements are understood

### Gate B: History Requirement

Before promoting a route with lookback semantics, confirm:

1. baseline storage exists or is created
2. insufficient-history behavior is defined
3. backfill policy is documented

### Gate C: Contract Promotion

Before marking a route as supported, confirm:

1. `501` is removed
2. tests pass
3. spec-044 and spec-045 are updated

## Estimated Effort

| Wave | Effort | Notes |
|------|--------|-------|
| Wave 1 | 3-5 days | highest leverage and clearest calculators |
| Wave 2 | 2-4 days | depends on history and confidence semantics |
| Wave 3 | 4-8 days | broader and more heterogeneous |
| **Total** | **9-17 days** | can be split across milestones |

