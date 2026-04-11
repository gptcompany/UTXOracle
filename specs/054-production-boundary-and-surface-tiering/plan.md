# spec-054: Implementation Plan

## Execution Order

```
Phase 1: Baseline and Drift Inventory
├── inventory actual :8011 route exposure
├── inventory documented production boundary
├── identify drift between runtime, docs, and registry
└── freeze what problem this spec does and does not solve

Phase 2: Tier Model Freeze
├── freeze exactly three tiers
├── freeze tier semantics
├── freeze execution eligibility rule
└── freeze transition rule for operator routes still exposed on :8011

Phase 3: Route-Family Assignment
├── classify every :8011 family into one tier
├── classify :8001 as research/transition explicitly
├── record allowed consumers for each family
└── freeze which families NT may consume

Phase 4: Boundary Artifact and Docs
├── publish one canonical boundary artifact
├── align README and service profile
├── align contract registry labels if needed
└── define one source of truth for future boundary changes

Phase 5: Runtime and Policy Alignment
├── decide which exposed operator routes may remain on :8011
├── mark non-execution families explicitly
├── define the approval path for future tier moves
└── verify fail-closed consumer guidance
```

## Core Principle

The point of this spec is not to hide every non-core route immediately. The point is to make the execution boundary explicit so `NT` can consume a small trusted contract and ignore everything else.

## Decision Gates

### Gate A: Tier Admission

Before any route family enters `tier_1_execution`, confirm:

1. the route is bounded and versioned or equivalent
2. failure semantics are explicit
3. freshness expectations are known
4. downstream execution value is real

### Gate B: Transitional Exposure

Before leaving a non-execution family exposed on `:8011`, confirm:

1. it has clear operator value
2. it is marked non-execution in docs and boundary artifacts
3. `NT` has no dependency on it
4. the exposure is deliberate rather than accidental

### Gate C: Boundary Source of Truth

Before updating any doc or runtime route map, confirm:

1. one canonical boundary artifact is being updated
2. README and service profile will match it
3. contract labels remain consistent
4. the change is reviewable as a boundary decision, not a side effect

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| route inventory and drift review | 0.5-1 day | mostly classification and cleanup |
| tier model freeze | 0.5-1 day | high leverage |
| boundary artifact + docs | 0.5-1 day | should remain small |
| runtime/policy alignment | 1-2 days | depends on how much exposure is changed immediately |
| **Total** | **2.5-5 days** | should be completed before execution-safety wiring |

