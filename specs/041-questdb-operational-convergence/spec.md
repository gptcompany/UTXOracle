# spec-041: QuestDB Operational Convergence & API Boundary

> **Status**: COMPLETE
> **Priority**: CRITICAL
> **Effort**: High
> **Created**: 2026-03-31

## Problem Statement

The repository currently runs one healthy live service on `8011`, but the operational surface is still split across incompatible storage and API models:

1. `live_snapshots` is actively populated in QuestDB and backs the current live contract.
2. legacy REST endpoints under `api.main` still expose routes that read QuestDB tables with zero rows.
3. other exposed routes still read DuckDB directly and can fail when the expected research datasets are missing or locked.
4. the Docker live API on `8011` and the legacy systemd API on `8001` both boot the same `api.main:app`, so production and legacy surfaces are mixed together.
5. placeholder and partially implemented routes remain visible on the live service even when they are not operationally supported.

The result is architecture drift: the live runtime is QuestDB-first, but the publicly exposed API is not yet QuestDB-only or production-scoped.

An additional migration risk exists: moving production reads to QuestDB before proving parity against the previous DuckDB-backed research outputs could silently operationalize incorrect data.

## Decision

The operational stack MUST converge fully to QuestDB for all API-served and continuously updated data in order to remove DuckDB lock contention from the served path.

After this spec:

- `QuestDB` is the only authoritative operational store for live and API-served datasets.
- `DuckDB` remains allowed only for offline research, local experimentation, and backtests that are explicitly marked non-operational.
- `8011` is the only production API surface.
- `8001` is either retired or reduced to an explicitly manual legacy/research mode.

## Goals

1. **Single operational store**: all production-served datasets come from QuestDB.
2. **Clean API boundary**: the live API exposes only supported, QuestDB-backed endpoints.
3. **No DuckDB in served path**: live consumers do not depend on local DuckDB files.
4. **Remove API ambiguity**: `8011` becomes the canonical API; `8001` is demoted or removed.
5. **De-risk charting and trading follow-ups**: later specs can build on one stable storage and schema model.

## Non-Goals

- rewriting the core UTXOracle algorithm
- migrating every research notebook or one-off bootstrap script away from DuckDB immediately
- replacing BRK, mempool, electrs, or Hyperliquid
- defining chart UX or Nautilus integration details beyond their storage dependencies

## Current Facts Verified On 2026-03-31

- `127.0.0.1:8011` now boots `api.apps.live:app`, not the mixed `api.main:app`.
- `127.0.0.1:8011` now exposes only `/health` and `/api/v1/live/*`; legacy families such as `/api/prices/*` return `404`.
- `127.0.0.1:8001` remains the explicit legacy systemd surface via `api.apps.legacy:app`.
- the retained live family on `8011` now reads and serves directly from QuestDB `live_snapshots`.
- `/api/prices/historical` has a first real parity slice and dual-read logging path, but the parity gate is not complete for all retained route families.
- some legacy routes still read DuckDB directly, but they are not admitted to `8011`.

## Design

### 1. App Split

Create an explicit split between:

- **live production app**: QuestDB-only, served on `8011`
- **legacy/research app**: optional, not part of the default production runtime

Recommended shape:

- `api/apps/live.py` or equivalent for the production app
- `api/apps/legacy.py` or equivalent for the old surface
- `api.main` becomes a thin compatibility shim or is retired entirely

### 2. Production Endpoint Policy

No endpoint may remain exposed on the production app unless one of the following is true:

1. it is fully backed by QuestDB and has an active writer/backfill path
2. it is a stateless upstream proxy with clear degraded behavior
3. it is explicitly marked read-only metadata and does not depend on local storage

Routes that are placeholder, partially migrated, or DuckDB-backed MUST be:

- removed from the production app, or
- moved behind a legacy/research app, or
- hidden until their QuestDB pipeline exists

### 3. Operational Dataset Classes

QuestDB becomes authoritative for these dataset classes:

- live snapshots and live comparisons
- historical price comparison series
- whale transactions and whale aggregates
- general on-chain metric snapshots used by served APIs
- chart-ready historical series produced for visualization
- operational health, freshness, and alert-event series

DuckDB remains acceptable only for:

- offline research pipelines
- historical backtest preparation
- ad hoc experimental metrics
- local validation work that is not served from the production API

### 4. Migration Rule

Every production API route MUST map to:

- a QuestDB table or materialized query
- a named ingestion job or backfill process
- freshness expectations
- degraded behavior when data is missing or stale

If one of these is missing, the route is not production-ready and does not belong on `8011`.

### 5. Data Parity Gate

Before any retained production route cuts over from DuckDB-backed or mixed behavior to QuestDB-only reads, the repository MUST prove numerical parity over a bounded lookback window.

Minimum parity gate:

- compare QuestDB outputs against DuckDB baselines for at least the previous 7 days
- define per-route tolerances
- start with concrete defaults unless a stricter route-specific tolerance is justified:
  - `<0.1%` for price series and direct price-comparison fields
  - `<2%` for complex derived metrics
- fail the cutover if parity falls outside those tolerances

This gate is required even when the old path is not production-worthy, because it is still the best available research baseline for many series.

### 6. Dual-Read Monitoring Period

For retained route families that previously depended on DuckDB, there MUST be a temporary dual-read or dual-compute period before final cutover:

- QuestDB result is returned or staged as the candidate result
- DuckDB or research baseline is computed in parallel or asynchronously
- differences are logged with route id, dataset id, timestamp window, and tolerance outcome

The purpose is to catch silent divergence before DuckDB is fully removed from the served path.

### 7. Historical Gap and Backfill Policy

Empty QuestDB tables are not considered a completed migration.

For each retained production route family, the implementation MUST define:

- whether historical data is required
- how much historical backfill is required before the route can be considered production-ready
- whether the route may temporarily return 404/empty while historical backfill is incomplete

### 8. Freshness and Health Model

Freshness MUST be explicit per dataset family, not inferred ad hoc.

Each retained production dataset MUST define:

- `max_staleness`
- whether stale data is still serveable
- whether the correct response is `200 degraded`, `404 empty`, or `503 unavailable`

### 9. Port and Service Policy

After convergence:

- `8011` = canonical production API
- `8001` = disabled by default, or renamed as a clearly non-production legacy service

Repo documentation MUST stop describing `8001` as the default API path.

## Functional Requirements

### FR1: QuestDB-Only Production Reads

The production API on `8011` MUST not read DuckDB for request handling.

### FR2: App Boundary

The live production service MUST not boot the mixed legacy app surface.

### FR3: Endpoint Inventory

The repository MUST maintain an explicit inventory of:

- production endpoints
- legacy/research endpoints
- deprecated endpoints

### FR4: Route Admission Gate

Every production endpoint MUST identify:

- QuestDB source table(s)
- ingestion/backfill owner
- freshness class
- degraded or empty-state semantics

### FR5: Placeholder Removal

Routes returning placeholder data, `501`, or mock calculations MUST not remain exposed on the production app.

### FR6: Legacy Retirement

The systemd `8001` service MUST be retired, renamed, or documented as non-production-only.

### FR7: Documentation Alignment

`README`, `ARCHITECTURE`, runbooks, service docs, and deployment docs MUST describe the same runtime truth.

### FR8: Migration Safety

No production route removal may happen without an explicit replacement, deprecation note, or legacy fallback plan.

### FR9: Numerical Parity Gate

No retained production route may cut over to QuestDB-only reads without a documented parity pass against the prior research baseline over a minimum 7-day lookback window.

### FR10: Dual-Read Monitoring

Retained route families migrating off DuckDB MUST support a temporary dual-read or dual-compute monitoring mode before final cutover.

### FR11: Historical Backfill Requirement

Every retained production route family MUST declare whether a historical backfill is required and what minimum backfill window is needed for production readiness.

### FR12: Freshness Registry

Every retained production route family MUST define a route-level freshness threshold and stale-data response policy.

### FR13: QuestDB Operational Tuning

The production app MUST define QuestDB connection-pool sizing, concurrency expectations, and failure behavior appropriate for concurrent API, charting, and trading reads.

## Success Criteria

| Criterion | Target |
|----------|--------|
| Production storage path | `8011` uses QuestDB only |
| Production app surface | no placeholder or DuckDB-backed routes on `8011` |
| Legacy ambiguity | `8001` no longer described as the main API |
| Endpoint clarity | all production routes mapped to QuestDB datasets and writers |
| Numerical correctness | retained routes pass parity checks against prior research baselines |
| Migration safety | dual-read monitoring shows no unresolved high-severity divergences before cutover |
| Runtime reliability | no DuckDB lock contention in served API path |
| Follow-up readiness | chart and trading specs can depend on one storage model |

## Closure Notes

1. `8011` is now a narrow QuestDB-backed production surface: `/health` plus `/api/v1/live/*`
2. legacy families such as `/api/prices/*`, `/api/metrics/*`, `/api/whale/*`, `/api/v1/models/*`, and `/api/v1/validation/*` remain outside `8011` by design
3. `/api/prices/historical` parity and dual-read work remains available for future legacy-family migration work, but it is no longer a blocker for the `8011` boundary closure

## Risks

| Risk | Mitigation |
|------|------------|
| Breaking existing callers of legacy routes | maintain a documented legacy app or deprecation period |
| Metric families not yet ingested into QuestDB | remove from production app until ingestion exists |
| Documentation drift persists | make docs update a mandatory completion gate |
| Mixed app boot remains by convenience | enforce app split in compose and service units |

## Dependencies

- builds on spec-040 live service as the current operational baseline
- supersedes the assumption that `api.main` can remain the permanent mixed production app
- unblocks spec-042 charting and spec-043 Nautilus integration
