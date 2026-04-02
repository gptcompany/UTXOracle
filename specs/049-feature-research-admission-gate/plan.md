# spec-049: Implementation Plan

## Execution Order

```
Phase 1: Scope Freeze
├── freeze candidate routes for post-M6 admission review
├── explicitly exclude reserve-risk
└── publish the admission-governance baseline

Phase 2: Evidence Inventory
├── inventory runtime and degraded semantics for each candidate
├── inventory existing validation evidence
├── inventory field-level semantic risks
└── inventory consumer-use assumptions

Phase 3: Admission Gates
├── define route-specific go/no-go criteria for nupl
├── define route-specific go/no-go criteria for cost-basis
├── define estimated-field policy requirements
└── define reproducibility requirements where no external parity exists

Phase 4: Decision Publication
├── update roadmap milestone state
├── publish admission-gate document
├── link future contract triggers from consumer docs
└── keep registry/provenance references aligned

Phase 5: Follow-Up
├── either keep routes research-only with explicit blockers
├── or prepare a future contract-promotion change set
└── keep reserve-risk on a separate hardening path
```

## Core Principle

Live does not mean admitted. Consumer promotion requires explicit evidence, not inference from route availability.

## Decision Gates

### Gate A: Route Eligibility

Before considering any route for promotion, confirm:

1. it is already live and stable as a research route
2. its degraded semantics are frozen
3. it has no known placeholder/default analytical internals

### Gate B: Field Semantics

Before admitting any field into a consumer contract, confirm:

1. the field is direct or explicitly declared derived/estimated
2. the field meaning is stable across docs and runtime
3. the consumer impact of approximation is documented

### Gate C: Validation

Before promoting a route, confirm:

1. validation evidence exists, or the lack of external parity is explicitly accepted
2. operator reproducibility checks are named
3. admission does not rely on undocumented assumptions

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| scope freeze and evidence inventory | 0.5-1 day | mostly documentary |
| route-specific gate definition | 0.5-1 day | decision-heavy |
| publication and roadmap alignment | 0.5 day | high leverage |
| **Total** | **1.5-3 days** | no new serving code required |
