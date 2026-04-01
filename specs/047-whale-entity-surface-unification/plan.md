# spec-047: Implementation Plan

## Execution Order

```
Phase 1: Surface Inventory
├── list all current whale routes and payloads
├── mark canonical vs placeholder vs legacy
├── identify naming and namespace conflicts
└── choose retained route family

Phase 2: Canonical Schema
├── define whale event schema
├── define summary schema
├── define transaction drill-down schema
└── define entity foundation fields

Phase 3: Route Unification
├── keep or rework the implemented query routes
├── remove or deprecate placeholder routes
├── align route semantics and response docs
└── add deprecation behavior where needed

Phase 4: Entity Foundations
├── define entity registry shape
├── define provenance and confidence rules
├── add optional enrichment path for whale events
└── document observed vs inferred fields

Phase 5: Contract and Provenance Update
├── update contract registry
├── update provenance manifest
└── publish whale surface guidance for downstream consumers
```

## Core Principle

One namespace must imply one product story. If `/api/whale` means multiple incompatible things, it is not a product surface.

## Decision Gates

### Gate A: Canonical Retention

Before keeping any whale route, confirm:

1. it has a backing dataset
2. its semantics are still desired
3. it belongs in the canonical namespace

### Gate B: Entity Enrichment

Before adding entity fields to whale responses, confirm:

1. the label has provenance
2. the label has confidence
3. the label can be omitted without breaking the base event contract

### Gate C: Deprecation

Before keeping any legacy placeholder route, confirm:

1. there is a migration reason
2. there is a documented sunset date or removal condition
3. deprecation is visible to operators and consumers

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| surface inventory and schema decisions | 1 day | requires product clarity |
| route cleanup and deprecation | 1-2 days | low algorithmic risk |
| entity foundation schema | 1 day | mostly modeling and docs |
| optional enrichment integration | 1-3 days | depends on desired first slice |
| **Total** | **4-7 days** | can be phased |

