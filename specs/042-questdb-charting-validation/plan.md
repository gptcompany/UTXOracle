# spec-042: Implementation Plan

## Execution Order

```
Phase 0: RED Contract Tests
├── add failing tests for chart catalog and normalized schema
├── add failing tests for compare-mode payloads and parity metadata
└── add failing tests for downsampling and overlay degradation behavior

Phase 1: Chart Contract
├── define chart catalog
├── define normalized series schema and metadata fields
├── define parity score and compare payloads
└── choose initial chart families supported by QuestDB data

Phase 2: QuestDB Queries
├── build chart query layer
├── add downsampling strategy by series type
└── expose latest/history/compare endpoints

Phase 3: Validation Track
├── add BRK overlay mapping
├── add tolerance and freshness metadata
├── build numeric parity workflow first
└── add visual rendering on top of parity outputs

Phase 4: Frontend
├── create one canonical chart dashboard
├── add live comparison view
├── add overlay toggles and status display
└── remove ambiguity around older chart pages
```

## Operating Principle

Execution MUST follow RED -> GREEN -> REFACTOR for chart contracts, query behavior, and overlay degradation semantics.

## Entry Criteria

Do not start this spec until spec-041 is complete enough that:

1. the production app boundary is stable
2. the intended chart datasets are actually QuestDB-backed
3. `8011` is the canonical chart API host

## Initial Chart Family Recommendation

Build in this order:

1. live oracle vs mempool vs Hyperliquid comparison
2. deviation bps history
3. ingestion latency/freshness chart
4. curated BRK feature overlays from live snapshots
5. whale/netflow charts once QuestDB ingestion is confirmed

## Frozen First Slice

Do the first pass in this order only:

1. freeze `live-price-comparison` as the only admitted `chart_id`
2. implement `catalog`, `latest`, and `history`
3. read only from QuestDB `live_snapshots`
4. expose freshness and degraded-state metadata
5. defer BRK compare mode, overlays, and downsampling until the base contract is stable

## Frozen External Validation Direction

Do not force `live-price-comparison` against CheckOnChain-style structural metrics.

Use this order for the first external validation slice:

1. keep `live-price-comparison` on internal market-reference compare only
2. map `brk_realized_price` as the first credible BRK / CheckOnChain-style external validation candidate
3. add numeric compare first
4. add visual review only after the numeric contract is stable

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| chart schema and API design | 0.5 day | mostly contract work |
| QuestDB query layer and downsampling | 1-2 days | depends on desired windows |
| validation overlay and numerical parity workflow | 1-1.5 days | narrower if only 1-2 charts initially |
| frontend dashboard | 1-2 days | depends on scope and polish |
| **Total** | **4-6 days** | can be reduced by limiting initial chart set |
