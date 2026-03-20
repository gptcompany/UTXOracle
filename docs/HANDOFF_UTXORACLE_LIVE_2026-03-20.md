# UTXOracle Live Handoff - 2026-03-20

## Goal

Move the repository from dormant batch-oriented state toward one Dockerized `UTXOracle Live` service that:
- computes the canonical on-chain oracle with `UTXOracle`
- compares live against declared external references
- exposes a compact consumer contract for live systems
- preserves `BRK` as a future visual validation surface rather than the final consumer API

## Host Runtime Verified On 2026-03-20

| Component | Verified endpoint or path | Status | Notes |
|-----------|---------------------------|--------|-------|
| `electrs` | `http://127.0.0.1:3002` | reachable | `3001` is not available for this role |
| `mempool-api` | `http://127.0.0.1:8999/api/v1` | reachable | used for exchange BTC/USD and live mempool context |
| `BRK` | `http://127.0.0.1:7070` | reachable and healthy | use curated features only in MVP |
| `UTXOracle API` current | `http://127.0.0.1:8001` | existing baseline | current systemd FastAPI service |
| `Hyperliquid Node API` | `http://127.0.0.1:3001/info` (POST) | reachable | verified node API surface; `GET /info` returns `405` |
| `Hyperliquid Metrics` | `http://127.0.0.1:9101/metrics` | reachable | exposes `hl_core_block_height` |
| `Hyperliquid filtered oracle updates` | `/media/sam/4TB-NVMe/hyperliquid/filtered/hip3_oracle_updates_by_block` | available | contains `coin_to_oracle_px` and `coin_to_mark_px` for `cash:BTC` |
| `Hyperliquid realtime` | `/media/sam/4TB-NVMe/hyperliquid/realtime` | empty/off | not currently usable as persisted realtime source |
| `127.0.0.1:12345` | `http://127.0.0.1:12345` | unrelated | serves HTML and is not part of the Hyperliquid comparison path |

## Port Reality

- `3001` is occupied by `hyperliquid-docker-consensus-1`
- `3002` is occupied by `mempool-electrs`
- `3002` must therefore be consumed as the Electrs upstream, not reused by any new service
- the new Dockerized live API must remain configurable via ENV to avoid collision with the existing `8001` service

## Phase 1-4 Implementation Completed

### New live scaffolding

- `scripts/live/models.py`
- `scripts/live/comparison.py`
- `scripts/live/source_clients.py`
- `scripts/live/storage.py`
- `scripts/live/worker.py`
- `scripts/live/__init__.py`
- `api/routes/live.py`

### Tests added

- `tests/test_live_models.py`
- `tests/test_live_comparison.py`
- `tests/test_live_source_clients.py`
- `tests/test_live_storage.py`
- `tests/test_live_worker.py`
- `tests/test_live_api.py`

### Legacy defaults corrected

- `scripts/config/mempool_config.py`: `electrs` default aligned to `http://127.0.0.1:3002`
- `scripts/sync_utxo_lifecycle.py`: `electrs` default aligned to `http://127.0.0.1:3002`
- `scripts/utils/electrs_async.py`: `electrs` default aligned to `http://127.0.0.1:3002`
- `scripts/compare_brk_utxoracle.py`: `BRK` default aligned to `http://127.0.0.1:7070`
- `scripts/validate_brk_integration.py`: `BRK` default aligned to `http://127.0.0.1:7070`
- `api/config.py`: live ENV surface added for current upstreams and future Docker API port separation

## Implemented Behaviors

### `scripts/live/models.py`

Defines the normalized schema used by worker, API, and storage:
- `SourceHealth`
- `LiveFeatureSet`
- `LiveComparison`
- `LiveComparisonSnapshot`
- `HyperliquidPriceSnapshot`
- `OracleObservation`
- `LiveSnapshot`
- `LiveHistoryQuery`

### `scripts/live/comparison.py`

Implements basis-point comparison helpers:
- `compute_basis_points(...)`
- `build_live_comparison(...)`

### `scripts/live/source_clients.py`

Implements the upstream client layer:
- `ElectrsClient.fetch_tip_height()`
- `MempoolApiClient.fetch_exchange_price()`
- `BrkClient.fetch_curated_features()`
- `HyperliquidSnapshotClient.fetch_snapshot()`

`HyperliquidSnapshotClient` behavior is intentionally defensive:
1. try `HYPERLIQUID_NODE_API_URL`
2. require JSON content type and extract oracle and mark fields only when payload is valid
3. fall back to filesystem snapshots under `HYPERLIQUID_DATA_ROOT`

### `scripts/live/worker.py`

Implements one-cycle snapshot collection:
- aligns on current Electrs block height
- fetches mempool, BRK, and Hyperliquid concurrently
- calls the canonical UTXOracle resolver
- computes live comparisons
- carries forward prior values when an upstream is temporarily unavailable
- marks carried-forward sources as `stale`

### `scripts/live/storage.py`

Implements dedicated live DuckDB persistence:
- dedicated path via `LIVE_DUCKDB_PATH`
- worker-only write path with short-lived write connections
- API read path with short-lived `read_only` connections
- latest snapshot reads plus short-horizon history queries

### `api/routes/live.py`

Implements the initial consumer surface:
- `GET /api/v1/live/snapshot`
- `GET /api/v1/live/history`
- `GET /api/v1/live/comparison/latest`
- `GET /api/v1/live/ready`

## Current Architectural Boundary

### Canonical outputs

The public live contract should be owned by `UTXOracle Live`, not by `BRK`.

### BRK usage in MVP

`BRK` is treated as:
- curated feature provider
- source of selected on-chain reference metrics such as realized price and liveliness
- future visual validation backend for chart parity work against external providers

`BRK` is explicitly not the final consumer contract for trading or backtest engines.

### Hyperliquid usage in MVP

The verified Hyperliquid comparison source on this host is the filtered oracle-update dataset under `/media/sam/4TB-NVMe/hyperliquid/filtered/hip3_oracle_updates_by_block`. `POST /info` on `3001` is a real node API surface, but direct oracle and mark extraction is still treated as optional until the supported request type is confirmed on this node. `12345` is explicitly out of scope for the live comparison path.

## Test And Validation Status

### Completed

- Python syntax compilation succeeded for the new live modules and tests
- targeted unit suite is green through storage and API: `23 passed in 3.25s`
- live runtime endpoints and port collisions were manually verified on host

### Concrete smoke results

- `curl -fsS http://127.0.0.1:3002/blocks/tip/height` -> `941456`
- `curl -fsS http://127.0.0.1:8999/api/v1/prices` returned BTC/USD payload with `USD: 69834`
- `curl -fsS http://127.0.0.1:7070/health` returned `status: healthy` and `blocks_behind: 0`
- `curl -i -sS --max-time 2 http://127.0.0.1:3001/info` returned `405 Method Not Allowed`, confirming the verified node surface is `POST /info`
- `curl -sS -X POST http://127.0.0.1:3001/info -H "Content-Type: application/json" -d "{\"type\":\"meta\"}"` returned JSON, confirming the node stack is reachable
- `curl -sS http://127.0.0.1:9101/metrics | rg hl_core_block_height` returned the block-height gauge
- the latest verified filtered oracle-update file on `4TB-NVMe` contained both `coin_to_oracle_px` and `coin_to_mark_px` for `cash:BTC`
- `curl http://127.0.0.1:12345` returned `Content-Type: text/html; charset=utf-8`, confirming it is not part of the Hyperliquid comparison path

### Required after further edits

Rerun the targeted unit suite:

```bash
pytest tests/test_live_models.py tests/test_live_comparison.py tests/test_live_source_clients.py tests/test_live_storage.py tests/test_live_worker.py tests/test_live_api.py -q
```

If green, proceed to deployment and service-lifecycle phases.

## Next Session Recommended Order

1. implement the long-running worker loop and market cadence scheduling
2. extend host-level `/health` with live source summary when `LIVE_ENABLED=true`
3. create `Dockerfile.live` and `docker-compose.live.yml`
4. bind `LIVE_DUCKDB_PATH` and service ports in deployment assets
5. perform live smoke tests against the verified upstreams and the new `/api/v1/live/*` routes

## Open Risks

1. Hyperliquid oracle and mark comparison currently depends on the filtered dataset under `4TB-NVMe`, so freshness must be enforced explicitly
2. direct `POST /info` extraction for oracle and mark is still optional until the supported request type is confirmed on this node
3. `api/main.py` is already large, so live endpoints should be integrated carefully and kept isolated by helper modules
4. `BRK` feature scope must remain curated; do not leak raw metric fanout into the public live API
5. the existing systemd API on `8001` means Docker port selection must stay explicit to avoid accidental overlap
6. live history now depends on the dedicated `LIVE_DUCKDB_PATH`, so deployment assets must mount it explicitly
