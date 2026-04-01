# spec-044: Implementation Plan

## Execution Order

```
Phase 1: Contract Schema
├── define registry entry fields
├── define admission tiers
├── define versioning and deprecation semantics
└── publish YAML schema conventions

Phase 2: Baseline Population
├── map all current route families into the registry
├── preserve audit labels from the roadmap prep document
├── assign initial admission tiers
└── capture all known caveats

Phase 3: First Consumer Slice
├── freeze the first `nautilus_dev` contract
├── separate production, caveat, research, and non-admitted families
├── document migration assumptions
└── publish `NAUTILUS_FEATURE_CONTRACT_V1`

Phase 4: Validation
├── add validation rules for required registry fields
├── add consistency checks between YAML and markdown docs
├── reject missing owner/backend/freshness fields
└── verify all caveat routes are explicitly marked

Phase 5: Documentation
├── publish registry docs
├── link the registry from roadmap and integration docs
└── define how future specs modify contract state
```

## Core Principle

Consumer admission must be explicit. If a route is not in the contract registry, it is not part of the supported integration surface.

## Decision Gates

### Gate A: First-Slice Admission

Before admitting a surface to `tier_1_production` or `tier_2_production_with_caveats`, confirm:

1. route family and host are explicit
2. backend/source-of-truth is named
3. freshness target is named
4. current caveats are documented

### Gate B: Caveat Handling

Before marking a route as admitted with caveats, confirm:

1. the caveat is operationally understandable
2. the consumer impact is documented
3. the route is not silently overstated elsewhere

### Gate C: Registry Authority

Before publishing `v1`, confirm:

1. roadmap prep, contract doc, and YAML agree
2. all admitted surfaces have owners
3. deprecation state is explicit for every admitted family

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| schema and tier design | 0.5 day | mostly editorial and alignment work |
| baseline population | 0.5-1 day | driven by current inventory |
| first-slice contract freeze | 0.5 day | needs product decisions, not code complexity |
| validation and docs | 0.5 day | high leverage |
| **Total** | **2-3 days** | low algorithmic risk |

