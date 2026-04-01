# spec-045: Implementation Plan

## Execution Order

```
Phase 1: Manifest Schema
├── define backend classes
├── define provenance fields
├── define failure mode vocabulary
└── create manifest skeleton

Phase 2: Priority Surface Mapping
├── map all first-pass route families
├── attach tables/views/upstreams/env vars
├── attach writer/read owners
└── capture current caveats

Phase 3: Documentation
├── generate readable dependency matrix
├── align terminology with contract registry
└── publish operator-facing provenance notes

Phase 4: Optional Metadata Endpoint
├── define metadata response schema
├── expose filtered manifest summaries
├── keep data plane and metadata plane separate
└── add tests for metadata parity

Phase 5: Validation
├── add CI checks for missing provenance fields
├── detect drift between docs and YAML
└── detect route families present in docs but missing from manifest
```

## Core Principle

Dependency ambiguity is operational debt. If a consumer cannot tell what backs a route and what breaks it, the route is not fully productized.

## Decision Gates

### Gate A: Coverage

Before publishing the first manifest, confirm every priority route family has:

1. backend class
2. upstream or table list
3. required env or credentials
4. failure mode semantics

### Gate B: Naming

Before introducing new backend classes, confirm existing classes cannot express the dependency cleanly.

### Gate C: Metadata Endpoint

Before adding `/api/meta/features`, confirm:

1. the YAML manifest already exists
2. the endpoint is derived from the manifest, not hand-maintained separately
3. the endpoint does not leak secrets or internal-only values

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| schema and vocabulary | 0.5 day | mostly alignment work |
| mapping priority surfaces | 1 day | route-by-route but mechanical |
| docs and metadata exposure | 0.5-1 day | depends on whether endpoint is added |
| validation automation | 0.5 day | high leverage |
| **Total** | **2.5-3 days** | moderate documentation and metadata work |

