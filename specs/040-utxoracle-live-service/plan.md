# Implementation Plan: UTXOracle Live Service

**Spec**: [spec.md](./spec.md) | **Date**: 2026-03-20

## Summary

Implement a Docker deployable UTXOracle live service that combines the canonical UTXOracle oracle engine with current host upstreams and exposes a stable consumer API with live comparison fields.

**Primary delivery**:
1. one Docker Compose stack with `worker` and `api`
2. one normalized live snapshot contract for consumers
3. explicit comparison or deviation fields against declared live references
4. curated BRK feature ingestion without exposing BRK raw metric fanout

## Repo Reality Check

Current repo and host state impose six immediate constraints:

1. several modules still default to `electrs` on `localhost:3001`, but live runtime is `127.0.0.1:3002`
2. BRK validation scripts still default to `localhost:3110`, but host runtime is `127.0.0.1:7070`
3. existing API docs and tests still mention `8000`, while the current systemd service runs on `8001`
4. the repo already exposes many historical metrics, but does not yet expose one clean live comparison surface
5. `127.0.0.1:12345` is not the correct Hyperliquid comparison endpoint on this host; it serves unrelated HTML content
6. the verified Hyperliquid stack is `POST http://127.0.0.1:3001/info`, `http://127.0.0.1:9101/metrics`, and filtered oracle updates on `/media/sam/4TB-NVMe/hyperliquid/filtered/hip3_oracle_updates_by_block`, but the filtered dataset must be freshness-checked because realtime persistence is currently off

## Files to Create

```text
scripts/live/__init__.py
scripts/live/models.py
scripts/live/source_clients.py
scripts/live/comparison.py
scripts/live/storage.py
scripts/live/worker.py
tests/test_live_models.py
tests/test_live_source_clients.py
tests/test_live_comparison.py
tests/test_live_worker.py
tests/test_live_storage.py
tests/test_live_api.py
api/routes/live.py
Dockerfile.live
docker-compose.live.yml
```

## Files to Modify

```text
api/main.py
api/config.py
scripts/config/mempool_config.py
scripts/daily_analysis.py
scripts/sync_utxo_lifecycle.py
scripts/compare_brk_utxoracle.py
scripts/validate_brk_integration.py
docs/ARCHITECTURE.md
utxoracle-api.service
```

## Architecture Design

### 1. Source Clients Layer

Create `scripts/live/source_clients.py` with focused clients:
- `ElectrsClient`
- `MempoolApiClient`
- `BrkClient`
- `HyperliquidSnapshotClient`

Responsibilities:
- isolate HTTP or file access
- parse Hyperliquid filtered `.zst` oracle updates from the verified 4TB path
- support `POST /info` parsing for future direct Hyperliquid price extraction when available
- return source health metadata with latency and last success
- hide current endpoint drift behind env config

### 2. Model Layer

Create `scripts/live/models.py` with normalized models for:
- `SourceHealth`
- `LiveFeatureSet`
- `LiveComparison`
- `LiveSnapshot`
- `LiveComparisonSnapshot`
- `LiveHistoryQuery`

These models define both the consumer contract and the storage contract.

### 3. Comparison Layer

Create `scripts/live/comparison.py`.

Responsibilities:
- compute basis-point deviations
- centralize comparison rules and null handling
- produce a compact comparison object for the API

Initial comparisons:
- UTXOracle vs mempool exchange price
- UTXOracle vs Hyperliquid oracle price
- UTXOracle vs Hyperliquid mark price

### 4. Storage Layer

Create `scripts/live/storage.py` backed by DuckDB.

Implemented storage model:
- dedicated live database path via `LIVE_DUCKDB_PATH`
- single writer from the worker
- short-lived `read_only` connections from API handlers
- indexed timestamp and block-height columns plus full normalized `snapshot_json` payload

Implemented table:

```sql
CREATE TABLE IF NOT EXISTS live_snapshots (
  snapshot_ts TIMESTAMPTZ PRIMARY KEY,
  schema_version VARCHAR NOT NULL,
  block_height BIGINT,
  utxoracle_price DOUBLE,
  utxoracle_confidence DOUBLE,
  mempool_exchange_price DOUBLE,
  hyperliquid_oracle_price DOUBLE,
  hyperliquid_mark_price DOUBLE,
  comparison_json TEXT NOT NULL,
  features_json TEXT NOT NULL,
  source_health_json TEXT NOT NULL,
  source_timestamps_json TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
)
```

### 5. Worker Layer

Create `scripts/live/worker.py`.

Current worker implementation:
- one-cycle collection path is implemented
- block-bound refresh already keys off observed `electrs` tip height
- market cadence polling is implemented through `LiveWorker.run(...)`
- degraded carry-forward semantics are implemented
- optional snapshot persistence hook writes into DuckDB storage

Remaining worker work:
- service lifecycle wiring around the long-running loop
- shutdown and runner integration for the final Docker services

### 6. API Layer

Keep live API code isolated in `api/routes/live.py` and include that router from `api/main.py`.

Implemented endpoints:
- `GET /api/v1/live/snapshot`
- `GET /api/v1/live/history?minutes=...`
- `GET /api/v1/live/comparison/latest`
- `GET /api/v1/live/ready`

Current API status:
- `/api/v1/live/*` route family is implemented
- host-level `/health` includes a live summary when `LIVE_ENABLED=true`

Remaining API work before deployment:
- keep the `/health` payload stable as deployment assets and runner wiring are added

### 7. Deployment Layer

Create `Dockerfile.live` and `docker-compose.live.yml`.

Compose services:
- `utxoracle-live-worker`
- `utxoracle-live-api`

Runtime assumptions:
- host can reach `127.0.0.1:3002`, `127.0.0.1:8999`, `127.0.0.1:7070`, `127.0.0.1:3001/info`, and `127.0.0.1:9101/metrics`
- host has access to `/media/sam/4TB-NVMe/hyperliquid/filtered/hip3_oracle_updates_by_block`
- local bind mount for DuckDB and logs
- `network_mode: host` is acceptable for MVP on this node if it simplifies source access

## Configuration Plan

Add or align env vars:

```text
DUCKDB_PATH
LIVE_DUCKDB_PATH
FASTAPI_PORT
ELECTRS_HTTP_URL
MEMPOOL_API_URL
BRK_BASE_URL
HYPERLIQUID_NODE_API_URL
HYPERLIQUID_NODE_INFO_REQUEST_TYPE
HYPERLIQUID_METRICS_URL
HYPERLIQUID_DATA_ROOT
HYPERLIQUID_FILTERED_STREAM
HYPERLIQUID_MAX_AGE_SECONDS
LIVE_MARKET_INTERVAL_SECONDS
LIVE_BLOCK_POLL_INTERVAL_SECONDS
LIVE_RETENTION_HOURS
LIVE_ENABLED
```

Also update existing modules that still use wrong defaults:
- `scripts/config/mempool_config.py`
- `scripts/utils/electrs_async.py`
- `scripts/whale_flow_detector.py`
- `scripts/compare_brk_utxoracle.py`
- `scripts/validate_brk_integration.py`

## TDD Strategy

1. start with model tests for snapshot and comparison schema
2. add source client tests with mocked payloads and failure modes
3. add comparison tests for basis-point calculations and missing-source behavior
4. add worker tests for healthy and degraded cycles
5. add API tests for snapshot, history, and comparison endpoints
6. only then wire Docker deployment assets

## Risks

### Risk 1: Endpoint Drift

Host runtime differs from repo defaults. Configuration centralization is mandatory before implementation expands.

### Risk 2: Hyperliquid Freshness

The verified Hyperliquid comparison source on this host is the filtered oracle-update dataset under `HYPERLIQUID_DATA_ROOT`. It contains both `coin_to_oracle_px` and `coin_to_mark_px`, but it may lag when the realtime consumer is off. The implementation must classify this source as `healthy`, `stale`, or `unavailable` based on timestamp age, and it must treat `POST /info` support for direct oracle and mark queries as optional until the supported request type is confirmed on the node.

### Risk 3: API Surface Bloat

`api/main.py` is already large. The live implementation now keeps route logic in `api/routes/live.py`; future edits should preserve that separation rather than adding more live logic inline.

### Risk 4: BRK Scope Creep

There is pressure to expose many BRK combinations. The live API must remain a curated contract.

### Risk 5: Visual Validation Coupling

Future BRK chart validation is important, but must not block the MVP live service or leak into the consumer contract.

## Validation Plan

1. unit tests for models, source clients, comparison engine, worker, and API
2. local smoke test with mocked upstreams
3. host integration smoke test against live `electrs`, `mempool-api`, and `BRK`
4. Docker Compose boot verification
5. manual curl checks for snapshot, comparison, health, and ready endpoints

## Estimated Effort

| Phase | Task | Hours |
|------|------|------|
| 1 | Config alignment and models | 2-3h |
| 2 | Source clients and comparison engine | 3-5h |
| 3 | Worker and storage | 3-4h |
| 4 | API endpoints | 2-3h |
| 5 | Docker deployment and docs | 2-3h |
| 6 | Integration validation | 2-4h |
| **Total** | | **14-22h** |
