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
| `Hyperliquid Node API` target | `http://127.0.0.1:12345` | reachable but invalid payload | current response is not the expected Hyperliquid JSON contract |
| `Hyperliquid fallback` | `/media/sam/1TB/hyperliquid-realtime-data` | available | SQLite and CSV fallback for oracle and mark price |

## Port Reality

- `3001` is occupied by `hyperliquid-docker-consensus-1`
- `3002` is occupied by `mempool-electrs`
- `3002` must therefore be consumed as the Electrs upstream, not reused by any new service
- the new Dockerized live API must remain configurable via ENV to avoid collision with the existing `8001` service

## Phase 1-2 Implementation Completed

### New live scaffolding

- `scripts/live/models.py`
- `scripts/live/comparison.py`
- `scripts/live/source_clients.py`
- `scripts/live/worker.py`
- `scripts/live/__init__.py`

### Tests added

- `tests/test_live_models.py`
- `tests/test_live_comparison.py`
- `tests/test_live_source_clients.py`
- `tests/test_live_worker.py`

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

`Hyperliquid Node API` remains the intended primary live comparator, but the implementation now reflects verified host reality: local filesystem data is the required fallback until the node endpoint returns the expected JSON payload.

## Test And Validation Status

### Completed

- Python syntax compilation succeeded for the new live modules and tests
- targeted unit suite is green: `10 passed in 0.84s`
- live runtime endpoints and port collisions were manually verified on host

### Concrete smoke results

- `curl -fsS http://127.0.0.1:3002/blocks/tip/height` -> `941456`
- `curl -fsS http://127.0.0.1:8999/api/v1/prices` returned BTC/USD payload with `USD: 69834`
- `curl -fsS http://127.0.0.1:7070/health` returned `status: healthy` and `blocks_behind: 0`
- `curl http://127.0.0.1:12345` returned `Content-Type: text/html; charset=utf-8`, confirming the current endpoint is not the expected Hyperliquid JSON API

### Required after further edits

Rerun the targeted unit suite:

```bash
pytest tests/test_live_models.py tests/test_live_comparison.py tests/test_live_source_clients.py tests/test_live_worker.py -q
```

If green, proceed to storage and API phases.

## Next Session Recommended Order

1. run the targeted `pytest` suite for the new live modules
2. add `scripts/live/storage.py` with DuckDB persistence for latest and short-horizon history
3. wire live endpoints into `api/main.py`
4. add `tests/test_live_api.py`
5. create `Dockerfile.live` and `docker-compose.live.yml`
6. perform live smoke tests against the verified upstreams

## Open Risks

1. `HYPERLIQUID_NODE_API_URL` is configured correctly as architecture intent, but current host payloads are not the expected contract
2. `api/main.py` is already large, so live endpoints should be integrated carefully and kept isolated by helper modules
3. `BRK` feature scope must remain curated; do not leak raw metric fanout into the public live API
4. the existing systemd API on `8001` means Docker port selection must stay explicit to avoid accidental overlap
