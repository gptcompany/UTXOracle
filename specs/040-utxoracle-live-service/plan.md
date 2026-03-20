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

Current repo and host state impose five immediate constraints:

1. several modules still default to `electrs` on `localhost:3001`, but live runtime is `127.0.0.1:3002`
2. BRK validation scripts still default to `localhost:3110`, but host runtime is `127.0.0.1:7070`
3. existing API docs and tests still mention `8000`, while the current systemd service runs on `8001`
4. the repo already exposes many historical metrics, but does not yet expose one clean live comparison surface
5. `127.0.0.1:12345` is reachable today but currently returns non-Hyperliquid content, so the live client must validate payload shape and fall back to filesystem data when needed

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
tests/test_live_api.py
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
- map upstream payloads into local models
- return source health metadata with latency and last success
- hide current endpoint drift behind env config

### 2. Model Layer

Create `scripts/live/models.py` with normalized models for:
- `SourceHealth`
- `LiveFeatureSet`
- `LiveComparison`
- `LiveSnapshot`
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

Proposed table:

```sql
CREATE TABLE IF NOT EXISTS live_snapshots (
  timestamp TIMESTAMP PRIMARY KEY,
  block_height BIGINT,
  utxoracle_price DOUBLE,
  utxoracle_confidence DOUBLE,
  mempool_exchange_price DOUBLE,
  hyperliquid_oracle_price DOUBLE,
  hyperliquid_mark_price DOUBLE,
  utxo_vs_mempool_bps DOUBLE,
  utxo_vs_hl_oracle_bps DOUBLE,
  utxo_vs_hl_mark_bps DOUBLE,
  brk_realized_price DOUBLE,
  brk_liveliness DOUBLE,
  brk_reserve_risk DOUBLE,
  source_health_json VARCHAR,
  source_timestamps_json VARCHAR,
  schema_version VARCHAR
)
```

### 5. Worker Layer

Create `scripts/live/worker.py`.

Worker loop design:
- poll market sources every configurable market interval
- refresh block-bound context when observed `electrs` tip height changes
- calculate comparison fields via `comparison.py`
- write a new snapshot row when enough upstream data is available
- preserve last good snapshot on degraded cycles

### 6. API Layer

Extend `api/main.py` with live endpoints first rather than creating a second FastAPI app.

Add endpoints:
- `GET /api/v1/live/snapshot`
- `GET /api/v1/live/history?minutes=...`
- `GET /api/v1/live/comparison/latest`
- enhance `GET /health` with live source health summary when `LIVE_ENABLED=true`
- add `GET /ready`

### 7. Deployment Layer

Create `Dockerfile.live` and `docker-compose.live.yml`.

Compose services:
- `utxoracle-live-worker`
- `utxoracle-live-api`

Runtime assumptions:
- host can reach `127.0.0.1:3002`, `127.0.0.1:8999`, and `127.0.0.1:7070`
- local bind mount for DuckDB and logs
- `network_mode: host` is acceptable for MVP on this node if it simplifies source access

## Configuration Plan

Add or align env vars:

```text
DUCKDB_PATH
FASTAPI_PORT
ELECTRS_HTTP_URL
MEMPOOL_API_URL
BRK_BASE_URL
HYPERLIQUID_DATA_ROOT
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

`HYPERLIQUID_NODE_API_URL` is configured as the intended primary live source, but the host endpoint on `12345` currently does not return the expected JSON payload. The implementation must validate the response at runtime, fall back to local files under `HYPERLIQUID_DATA_ROOT`, and define what counts as fresh enough for live comparison.

### Risk 3: API Surface Bloat

`api/main.py` is already large. The MVP should keep live code grouped and extract later only if needed.

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
