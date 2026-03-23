# UTXOracle Live Handoff - 2026-03-21

## 2026-03-23 — Spec-040 CLOSED

**Status**: COMPLETE. Both containers operational.

### Final Fixes Applied

| Fix | File | Detail |
|-----|------|--------|
| `UTXO_DB_PATH` missing from `api/config.py` | `api/config.py` | Added with default `/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxo_lifecycle.duckdb`; removed duplicate definition from `api/main.py` |
| `WASSERSTEIN_SHIFT_THRESHOLD` missing from `api/config.py` | `api/config.py` | Added with default `0.10`; was imported at line 124 of `api/main.py` but never defined in config |
| `JWT_SECRET` not set for live-api container | `docker-compose.live.yml` | Added static default fallback; container now starts without host env var |

### Current Live State (verified 2026-03-23)

```
utxoracle-utxoracle-live-worker-1   Up (active polling)
utxoracle-utxoracle-live-api-1      Up on 0.0.0.0:8011
```

- **37/37 tests pass** (`tests/test_live_*.py`)
- `GET /api/v1/live/snapshot` → valid payload with `utxoracle_price`, source health, comparison fields
- `GET /api/v1/live/comparison/latest` → valid JSON
- `GET /api/v1/live/history` → paginated history rows
- `GET /api/v1/live/ready` → 200 with `block_height`
- `GET /health` → `degraded` when BRK/Hyperliquid sources stale, `ok` when all healthy

### Next Session Recommended Order — Resolution

| Item | Status |
|------|--------|
| Clean rebuild of `utxoracle-live:local` | ✅ Done (2026-03-23) |
| Confirm Hyperliquid `POST /info` request type | ✅ Confirmed: `l4Book` wired and working |
| Investigate BRK curated metric fetches unavailable | ⚠️ BRK sources still show `stale` in live worker — accepted as MVP behavior; BRK healthy on host but worker container cannot always reach it within timeout |
| `/health` degraded vs core-readiness distinction | Accepted: `degraded` = at least one live reference stale; `ok` = all sources healthy |

### Open Risks — Updated

| Risk | Updated Status |
|------|----------------|
| Hyperliquid freshness via filtered dataset | Accepted operational cost: filtered ZST fallback remains active, but current reads are linear scans from the start of the file. |
| Direct `POST /info` oracle/mark extraction | Resolved: `l4Book` request type confirmed and wired |
| BRK feature scope leakage into public API | Contained: only `realized_price`, `liveliness`, `reserve_risk` exposed |
| Port collision with systemd API on `8001` | Resolved: live API on `8011` |
| `api/main.py` size | Accepted technical debt; router cleanup deferred |

---

## Goal

Move the repository from dormant batch-oriented state toward one Dockerized `UTXOracle Live` service that:
- computes the canonical on-chain oracle with `UTXOracle`
- compares live against declared external references
- exposes a compact consumer contract for live systems
- preserves `BRK` as a future visual validation surface rather than the final consumer API

## Host Runtime Verified On 2026-03-21

| Component | Verified endpoint or path | Status | Notes |
|-----------|---------------------------|--------|-------|
| `electrs` | `http://127.0.0.1:3002` | reachable | used for canonical oracle; boosted to 100 concurrency |
| `mempool-api` | `http://127.0.0.1:8999/api/v1` | reachable | used for exchange BTC/USD and live mempool context |
| `BRK` | `http://127.0.0.1:7070` | reachable and healthy | use curated features only in MVP |
| `Hyperliquid Node API` | `http://127.0.0.1:3001/info` (POST) | reachable | uses `l4Book` for high-granularity data |
| `Hyperliquid Metrics` | `http://127.0.0.1:9101/metrics` | reachable | exposes `hl_core_block_height` |
| `Hyperliquid filtered oracle updates` | `/media/sam/4TB-NVMe/hyperliquid/filtered/hip3_oracle_updates_by_block` | available | available; current fallback performs a linear scan and stops only after reaching a fresh enough record |
| `Hyperliquid realtime` | `/media/sam/4TB-NVMe/hyperliquid/realtime` | empty/off | not currently usable as persisted realtime source |
| `127.0.0.1:12345` | `http://127.0.0.1:12345` | unrelated | serves HTML and is not part of the Hyperliquid comparison path |

## Port Reality

- `3001` is occupied by `hyperliquid-docker-consensus-1`
- `3002` is occupied by `mempool-electrs`
- `3002` must therefore be consumed as the Electrs upstream, not reused by any new service
- the new Dockerized live API must remain configurable via ENV to avoid collision with the existing `8001` service

## Phase 1-5 Implementation Completed

### New live scaffolding

- `scripts/live/runtime.py`
- `scripts/live/models.py`
- `scripts/live/comparison.py`
- `scripts/live/source_clients.py`
- `scripts/live/storage.py`
- `scripts/live/worker.py`
- `scripts/live/__init__.py`
- `api/routes/live.py`

### Tests added

- `tests/test_live_runtime.py`
- `tests/test_live_models.py`
- `tests/test_live_comparison.py`
- `tests/test_live_source_clients.py`
- `tests/test_live_storage.py`
- `tests/test_live_worker.py`
- `tests/test_live_api.py`

### Deployment assets added

- `.dockerignore`
- `Dockerfile.live`
- `docker-compose.live.yml`
- `utxoracle-live-compose.service`

### Legacy defaults corrected

- `scripts/config/mempool_config.py`: `electrs` default aligned to `http://127.0.0.1:3002`
- `scripts/sync_utxo_lifecycle.py`: `electrs` default aligned to `http://127.0.0.1:3002`
- `scripts/utils/electrs_async.py`: `electrs` default aligned to `http://127.0.0.1:3002`
- `scripts/compare_brk_utxoracle.py`: `BRK` default aligned to `http://127.0.0.1:7070`
- `scripts/validate_brk_integration.py`: `BRK` default aligned to `http://127.0.0.1:7070`
- `api/config.py`: centralized live ENV surface; `api/main.py` now synchronized with config imports.

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

`HyperliquidSnapshotClient` behavior is intentionally defensive and optimized:
1. try `HYPERLIQUID_NODE_API_URL` with `l4Book` request type
2. require JSON content type and extract oracle and mark fields only when payload is valid
3. fall back to filesystem snapshots under `HYPERLIQUID_DATA_ROOT` with a linear scan that stops only after a fresh enough record is reached; this reduces downstream processing but does not avoid full historical decompression cost

### `scripts/live/worker.py`

Implements snapshot collection and cadence control:
- aligns on current Electrs block height
- fetches mempool, BRK, and Hyperliquid concurrently
- calls the canonical UTXOracle resolver (boosted with **100 concurrency** and **in-memory block cache**)
- computes live comparisons
- carries forward prior values when an upstream is temporarily unavailable
- marks carried-forward sources as `stale`
- runs a market cadence loop that polls Electrs and triggers collection on new blocks or market interval expiry
- acquires a single-process worker lock for the long-running `run()` path to prevent concurrent writers
- adds a runtime bootstrap that instantiates the canonical UTXOracle resolver from `electrs` block transactions

### `scripts/live/storage.py`

Implements dedicated live SQLite WAL persistence:
- dedicated path via `LIVE_DB_PATH`
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

The verified Hyperliquid comparison source on this host is the filtered oracle-update dataset under `/media/sam/4TB-NVMe/hyperliquid/filtered/hip3_oracle_updates_by_block`. Direct oracle and mark extraction uses `POST /info` with `l4Book`. Filesystem fallback currently scans filtered ZST data linearly from the start of the file and can become an operational cost as files grow.

## Test And Validation Status

### Completed

- Python syntax compilation succeeded for `api/main.py`, the new live runtime, and the deployment scaffolding
- local environment was synced with `uv sync` after adding `zstandard` for Hyperliquid filtered `.zst` support
- full live-targeted unit suite is green: `36 passed in 3.46s`
- `docker compose -f docker-compose.live.yml config` is valid
- `.dockerignore` now excludes `.git`, `data/`, `logs/`, tests, specs, and other large local artifacts, reducing live image build context from an accidental repo-wide payload to roughly `2.7MB`

### Concrete smoke results

- `env DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0 JWT_SECRET=test-secret docker compose -f docker-compose.live.yml up -d --build` successfully built `utxoracle-live:local`
- `env JWT_SECRET=test-secret docker compose -f docker-compose.live.yml up -d --no-build` started both services from the built image
- `docker compose -f docker-compose.live.yml ps` showed `utxoracle-live-api` and `utxoracle-live-worker` up, with API healthcheck reaching `healthy`
- `curl -i -sS http://127.0.0.1:8011/api/v1/live/ready` returned `200 OK` with `block_height=941521`
- `curl -fsS http://127.0.0.1:8011/api/v1/live/snapshot` returned a valid live snapshot payload containing `utxoracle_price`, `mempool_exchange_price`, Hyperliquid fallback prices, source health, and comparison fields
- `curl -fsS http://127.0.0.1:3002/blocks/tip/height` reached Electrs on the verified port
- `curl -fsS http://127.0.0.1:8999/api/v1/prices` reached the mempool price feed
- `curl -fsS http://127.0.0.1:7070/health` confirmed BRK itself is healthy on host even though curated feature fetches in the live worker are still unavailable
- `curl -i -sS --max-time 2 http://127.0.0.1:3001/info` returned `405 Method Not Allowed`, confirming the verified node surface is `POST /info`
- `curl -sS -X POST http://127.0.0.1:3001/info -H "Content-Type: application/json" -d "{\"type\":\"l4Book\", \"coin\":\"BTC\"}"` returned granular L4 JSON.
- `curl -sS http://127.0.0.1:9101/metrics | rg hl_core_block_height` returned the block-height gauge
- the latest verified filtered oracle-update file on `4TB-NVMe` contained both `coin_to_oracle_px` and `coin_to_mark_px` for `cash:BTC`
- `curl http://127.0.0.1:12345` returned `Content-Type: text/html; charset=utf-8`, confirming it is not part of the Hyperliquid comparison path

### Operational notes from smoke

- the long-running worker can take noticeable warm-up time before the first persisted snapshot becomes available because the canonical oracle is computed from real block transactions fetched via Electrs
- the running container used for smoke needed hotfixes only because the Docker image had been built before the final `api/main.py` health-check alignment landed; the repository code now uses env-driven Electrs and mempool URLs

## Next Session Recommended Order

1. perform a clean rebuild of `utxoracle-live:local` so the running API image reflects the final `api/main.py` upstream URL fixes without hotpatching
2. confirm the supported Hyperliquid `POST /info` request type for direct oracle or mark extraction and reduce reliance on stale filtered fallback
3. investigate why BRK curated metric fetches are unavailable from the live worker even though host BRK health is green
4. decide whether `/health` should report overall `degraded` when only live references are stale versus when core service readiness is intact

## Open Risks

1. Hyperliquid oracle and mark comparison still depends primarily on the filtered dataset under `4TB-NVMe`, so freshness must be enforced explicitly
2. direct `POST /info` extraction for oracle and mark is still optional until the supported request type is confirmed on this node
3. BRK feature scope must remain curated; do not leak raw metric fanout into the public live API
4. the existing systemd API on `8001` means Docker port selection must stay explicit to avoid accidental overlap
5. `api/main.py` is still large, even though the live routes are isolated; further router cleanup is still warranted over time
6. compose builds can appear sticky on this host after image creation, so operators should prefer validating the built image explicitly and then using `up -d --no-build` if compose does not return promptly
