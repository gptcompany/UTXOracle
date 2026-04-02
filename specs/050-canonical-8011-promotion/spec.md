# spec-050: Canonical 8011 Promotion for QuestDB-Backed Families

> **Status**: COMPLETE
> **Priority**: HIGH
> **Effort**: Medium
> **Created**: 2026-04-02
> **Implemented**: 2026-04-02

## Problem Statement

The repository now has a clean production live boundary on `8011`, but several high-value route families remain on the explicit legacy app at `8001` even though they are already QuestDB-backed and admitted in the contract registry.

Current gap:

1. `/api/prices/*` is QuestDB-backed and `tier_1_production`, but still lives on `8001`
2. `/api/metrics/latest` is QuestDB-backed and `tier_1_production`, but still lives on `8001`
3. `/api/whale/{transactions,summary,transaction/{txid}}` is QuestDB-backed and canonical for forensics, but still lives on `8001`
4. downstream consumers still need to understand two app boundaries for operationally relevant route families
5. the production-serving story remains incomplete even though these families are already much closer to `8011` than the DuckDB research families

This spec promotes the already QuestDB-backed route families that deserve to join the canonical production app, without reopening DuckDB-heavy research surfaces or broadening the contract indiscriminately.

## Decision

The next production-boundary expansion MUST be limited to these three families:

- `/api/prices/*`
- `/api/metrics/latest`
- `/api/whale/{transactions,summary,transaction/{txid}}`

This spec does not promote DuckDB-backed metric families. It only moves already QuestDB-backed, operationally meaningful families into the canonical `8011` app once they satisfy route-level health, stale, and migration requirements.

## Goals

1. reduce practical production dependence on `8001`
2. give downstream consumers one canonical host for live, charts, prices, compact metrics, and whale forensics
3. keep DuckDB analytical families out of the `8011` serving path
4. formalize migration behavior for callers still using `8001`

## Non-Goals

- moving Wave 1 DuckDB analytics to `8011`
- reopening `reserve-risk`, `nupl`, or `cost-basis` promotion
- republishing broad `BRK` metric fanout
- turning `8001` off immediately

## Dependencies

- [specs/041-questdb-operational-convergence/spec.md](/media/sam/1TB/UTXOracle/specs/041-questdb-operational-convergence/spec.md)
- [specs/044-feature-service-contract-registry/spec.md](/media/sam/1TB/UTXOracle/specs/044-feature-service-contract-registry/spec.md)
- [specs/045-feature-dependency-provenance-manifest/spec.md](/media/sam/1TB/UTXOracle/specs/045-feature-dependency-provenance-manifest/spec.md)
- [specs/047-whale-entity-surface-unification/spec.md](/media/sam/1TB/UTXOracle/specs/047-whale-entity-surface-unification/spec.md)

## Design

### 1. Promotion Slice

The retained promotion slice is:

- `prices_surface`
- `metrics_latest_surface`
- `whale_query_surface`

No other family is part of this spec.

### 2. Host Policy

After this spec:

- `8011` becomes the canonical host for the promoted slice
- `8001` may continue to serve temporary compatibility access, but only as a documented legacy alias

### 3. Serving Rule

The promoted families MUST be served directly from production-app read paths on `8011`.

They MUST NOT:

- proxy through DuckDB calculators
- proxy through the live worker
- depend on request-time analytical reconstruction

They MUST read from their current QuestDB-backed serving tables and handlers, or equivalent production-app router modules derived from those handlers.

### 4. Route-Level Gates

Each promoted family MUST define:

- canonical read path owner
- freshness semantics
- empty-state behavior
- stale/degraded behavior
- migration behavior for `8001`

Minimum expectations:

- `/api/prices/*`: typed empty/stale semantics suitable for time-series serving
- `/api/metrics/latest`: explicit freshness policy for the compact metrics bundle
- whale canonical family: explicit stale semantics for `mempool_predictions` recency while preserving best-effort omission semantics for entity enrichment

### 5. Migration Behavior

`8001` should not silently remain equally canonical for these families.

Once a family is promoted:

- `8001` responses SHOULD include explicit migration/deprecation metadata or headers
- docs MUST describe `8011` as the canonical host for the promoted family
- the registry and provenance manifest MUST be updated in the same change set

### 6. Boundary Protection

This spec does not weaken the `8011` boundary.

DuckDB-backed and research-only families remain excluded until they have their own serving-grade path.

## Functional Requirements

### FR1: Canonical Host Promotion

The promoted slice MUST move its canonical host from `8001` to `8011`.

### FR2: QuestDB-Only Serving Path

No promoted route may introduce DuckDB reads into the `8011` request path.

### FR3: Whale Canonicality Preservation

Promotion of whale routes MUST preserve the canonical schema and omission semantics frozen by spec-047.

### FR4: Migration Notice

The legacy host MUST no longer appear equally canonical for the promoted slice.

### FR5: Contract Alignment

Registry, provenance manifest, architecture docs, and scope docs MUST reflect the same host policy in the same change set.

## Success Criteria

1. `8011` serves live, charts, prices, `metrics/latest`, and the canonical whale family
2. `8001` is clearly secondary for the promoted slice
3. no DuckDB-backed route enters the promoted production boundary through this work
4. downstream consumers can treat `8011` as the only serious host for the promoted slice

## Completion Notes

- `023e0a7` promoted `/api/prices/*`, `/api/metrics/latest`, and canonical whale routes to `8011`
- `8001` now serves the promoted slice as a documented secondary host with migration headers
- `26ae0cc` tightened the production boundary checks by closing the live QuestDB repository cleanly on shutdown, strengthening boundary tests, and removing a tracked runtime lockfile
