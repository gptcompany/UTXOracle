# spec-041: Implementation Plan

## Execution Order

```
Phase 1: Inventory and Boundary
├── enumerate all routes currently exposed on 8011
├── classify each route as production, legacy, or research
├── identify every route still reading DuckDB or returning placeholder data
├── define the retained production route set
└── publish the initial PROD_ROUTE_REGISTRY

Phase 2: RED Boundary Tests
├── add failing tests for production app route exposure and health behavior
├── add failing tests proving placeholder and DuckDB-backed routes are excluded
└── add failing tests for parity and dual-read harness behavior

Phase 3: App Split
├── create dedicated live production app
├── move QuestDB-backed live routes and health into production app
├── isolate legacy/research routes into separate app or router tree
└── update compose/systemd entrypoints

Phase 4: Parity and Dual-Read
├── define route-level tolerances and freshness thresholds
├── build parity CLI for QuestDB vs DuckDB research baselines
├── run dual-read monitoring for migrating route families
└── resolve divergences before final cutover

Phase 5: QuestDB Convergence
├── map every retained production route to QuestDB tables
├── implement missing QuestDB writers or backfills
├── tune QuestDB read-path connection limits for API/chart/trading consumers
├── remove production dependence on DuckDB
└── define empty/stale/degraded semantics for each retained dataset

Phase 6: Deprecation and Docs
├── retire or demote 8001
├── remove unsupported routes from 8011
├── align README, ARCHITECTURE, runbook, and services
└── publish endpoint inventory and migration notes
```

## Core Principle

Production simplicity beats endpoint breadth.

If a route is not QuestDB-backed and operationally owned, it does not belong on the production app.

Execution MUST follow RED -> GREEN -> REFACTOR for production app, parity, and route-boundary changes.

## Decision Gates

### Gate A: Production Route Admission

Before a route remains on `8011`, confirm:

1. what QuestDB table backs it
2. what process writes that table
3. what freshness target it has
4. what the response is when the dataset is empty or stale

### Gate B: Legacy Surface Retention

Before keeping `8001`, confirm:

1. who still needs it
2. whether it can be renamed as legacy/research
3. whether it should be disabled by default

### Gate C: Numerical Parity

Before final cutover of any retained route family, confirm:

1. parity lookback window has been run
2. defined tolerances have passed
3. dual-read monitoring shows no unresolved severe divergence

### Gate D: DuckDB Exceptions

DuckDB exceptions are allowed only for:

- offline backfills
- backtests
- research and validation tools

No exception is allowed for synchronous request handling on the production app.

## Dependencies

```
Route Inventory ──▶ App Split ──▶ QuestDB Writers/Backfills ──▶ Docs + Port Retirement
```

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| Route inventory and classification | 0.5-1 day | mostly analysis and decisions |
| App split and boot changes | 1 day | high leverage, low algorithmic risk |
| Parity and dual-read harness | 1-2 days | required before cutover |
| QuestDB convergence for retained routes | 2-4 days | depends on number of routes kept |
| Legacy retirement and docs | 0.5-1 day | must be treated as a release gate |
| **Total** | **5-9 days** | depends on how much legacy surface is preserved |
