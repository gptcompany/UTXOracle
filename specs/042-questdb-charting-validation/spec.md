# spec-042: QuestDB Charting & Visual Validation

> **Status**: DRAFT
> **Priority**: HIGH
> **Effort**: Medium
> **Created**: 2026-03-31

## Problem Statement

The repository has multiple frontend experiments and chart assets, but no single charting surface that is both operationally trustworthy and aligned with the current live stack.

Current issues:

1. chart pages are fragmented across older frontends and dashboards
2. many metric routes are not production-backed yet
3. visual validation against BRK or CheckOnChain-style references is documented as a future direction, not an implemented workflow
4. there is no chart API contract built on the live QuestDB-first storage model

After spec-041, the repository will have one operational storage boundary. This spec turns that boundary into a chart-ready data and validation surface.

## Goals

1. build a chart-ready API on top of QuestDB-backed datasets
2. deliver a single dashboard surface for live comparison and historical validation
3. support overlays from BRK and external references where applicable
4. make chart parity measurable instead of anecdotal

## Non-Goals

- implementing live trading execution
- exposing the full raw BRK metric fanout
- cloning CheckOnChain exactly
- migrating every historical research visualization in one pass

## Dependencies

- requires spec-041 to be completed first
- assumes `8011` exposes only production-backed routes

## Design

### 1. Chart API Contract

Introduce a versioned chart API family, for example:

- `GET /api/v1/charts/catalog`
- `GET /api/v1/charts/{chart_id}/latest`
- `GET /api/v1/charts/{chart_id}/history`
- `GET /api/v1/charts/{chart_id}/compare`

Each chart response MUST include:

- schema version
- chart id
- source metadata
- freshness
- timestamps
- one or more normalized series
- optional overlay/reference series

Minimum normalized response shape:

```json
{
  "schema_version": "v1",
  "chart_id": "live-price-comparison",
  "window": "1h",
  "is_downsampled": false,
  "source_health_summary": "QuestDB:healthy | BRK:healthy",
  "metadata": {
    "freshness_seconds": 4.0,
    "parity_score": null
  },
  "ts": ["2026-03-31T11:00:00Z", "2026-03-31T11:00:05Z"],
  "series": [
    {"id": "utxoracle_price", "label": "UTXOracle", "unit": "usd", "data": [66274.1, 66280.3]},
    {"id": "mempool_exchange_price", "label": "Mempool", "unit": "usd", "data": [66303.0, 66301.5]}
  ],
  "overlays": [
    {"id": "brk_realized_price", "label": "BRK Realized Price", "unit": "usd", "data": [54130.9, 54130.9]}
  ]
}
```

### 2. QuestDB-First Series Model

Chart data MUST come from QuestDB-backed production datasets. Initial chart families should only cover data that is operationally available after spec-041.

Initial chart set:

- UTXOracle vs mempool vs Hyperliquid live comparison
- live deviation bps history
- curated BRK overlays already present in live snapshots
- ingestion latency and freshness chart

Deferred until QuestDB ingestion is verified:

- whale activity and net flow charts

### 3. Visual Validation Track

Validation MUST be numerical-first and visual-second.

The system MUST support a validation mode that shows:

- local UTXOracle series
- BRK overlay where overlapping metrics exist
- optional external reference overlay for manual parity review

Validation is both:

- **numeric**: tolerance checks, MAE/relative error/parity score on sampled series
- **visual**: side-by-side chart parity workflow that renders the numeric outcome instead of replacing it

### 4. Frontend Scope

Provide one intentional dashboard surface rather than many partial HTML pages.

The dashboard should:

- render live and historical chart families
- expose freshness and source health clearly
- allow overlay toggles
- support downsampled queries for longer windows
- make degraded/stale upstream states visible

### 5. Performance

Downsampling and windowing should happen server-side for large time ranges.

Default strategy:

- LTTB for continuous line series
- time-bucket aggregation for stepwise or already-aggregated metric series

The API should support at least:

- raw short windows
- downsampled medium windows
- aggressively downsampled long windows

BRK or external overlays MUST NOT block chart responses indefinitely. Overlay retrieval should be cached, materialized, or downgraded explicitly when unavailable.

## Functional Requirements

### FR1: Chart Catalog

The API MUST expose a discoverable catalog of available chart ids, labels, supported windows, and overlays.

### FR2: Normalized Series Schema

All chart endpoints MUST return a normalized multi-series schema instead of bespoke per-page JSON.

### FR3: QuestDB Source of Truth

All production chart series MUST be served from QuestDB-backed data or from declared upstream overlays with explicit freshness.

### FR4: Validation Mode

The dashboard MUST support a chart validation mode against BRK or other declared references, and that mode MUST compute numerical parity metrics before rendering the chart.

### FR5: Freshness Visibility

Each chart payload MUST include freshness and degraded-state metadata.

### FR6: Downsampling

Long-window chart requests MUST support server-side downsampling.

### FR7: Downsampling Metadata

Chart payloads MUST indicate whether they are downsampled and which strategy was used.

### FR8: Live Comparison Chart

The initial release MUST include a first-class chart for live oracle vs reference price comparison and deviation.

### FR9: Ingestion Latency Chart

The initial release MUST include an operational chart showing event-time vs write-time or equivalent ingestion freshness/latency behavior for trust monitoring.

### FR10: Overlay Failure Isolation

Slow or unavailable BRK/external overlays MUST degrade gracefully and MUST NOT prevent local QuestDB-backed chart data from being served.

For synchronous overlay fetches, the production chart API MUST enforce a hard timeout of `2s` before degrading the overlay.

## Success Criteria

| Criterion | Target |
|----------|--------|
| Chart API | one versioned chart endpoint family is live |
| Data trust | all production chart series are QuestDB-backed |
| Validation | at least one overlapping chart supports numerical BRK parity mode |
| UX coherence | one main dashboard replaces scattered chart entry points |
| Performance | long-window queries are downsampled server-side |

## Risks

| Risk | Mitigation |
|------|------------|
| Trying to chart unsupported metrics too early | only admit QuestDB-backed chart families |
| BRK normalization mismatch | keep overlay metadata and tolerance notes explicit |
| Frontend sprawl continues | define one canonical chart dashboard and route |
| Query cost grows too quickly | add window classes and downsampling policies |
