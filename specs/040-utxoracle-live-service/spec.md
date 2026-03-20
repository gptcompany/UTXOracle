# spec-040: UTXOracle Live Service

## Objective

Deliver one Docker-deployable UTXOracle live service that is up and running on the host, exposes a stable consumer API, and publishes live comparison fields against declared external tools. `UTXOracle` remains the canonical on-chain oracle. `BRK` is used as an upstream feature provider and reserved for future visual validation of our charts against other providers.

## MVP Outcome

The MVP is successful when all of the following are true:
1. a Docker Compose stack starts and stays healthy
2. the service exposes a live snapshot for downstream consumers
3. the snapshot contains explicit comparison or deviation fields against declared external references
4. the service persists recent history for query and monitoring
5. the service operates with env-driven configuration and current host endpoints

## Problem Statement

Current repo capabilities are split across batch jobs, historical APIs, and validation scripts:

1. `UTXOracle_library.py` is the correct oracle engine but is not exposed as a stable live contract.
2. `scripts/daily_analysis.py` is batch oriented and cron oriented, not a live service.
3. current API endpoints focus on historical DuckDB tables, not a unified live snapshot and live comparison surface.
4. several integrations still use legacy defaults such as `electrs:3001`, `BRK:3110`, and API port `8000`, while current runtime uses different ports.
5. BRK exposes a very large metric surface, but downstream trading and backtest consumers need a compact, versioned schema.
6. the repo lacks a formally defined boundary between live consumer API and future visual validation workflows.

## Scope

### In Scope

- Docker service for `UTXOracle Live`
- env-driven integration with `electrs`, `mempool-api`, `BRK`, and `Hyperliquid`
- live snapshot with comparison fields
- latest plus short-horizon history persistence
- consumer API for Nautilus Trader and backtest engines
- health and readiness endpoints

### Out of Scope for MVP

- full BRK metric fanout exposure
- rebuilding `bitcoind`, `electrs`, `mempool`, or `BRK`
- onboarding infra services into `progressive-deploy`
- BRK visual validation dashboard itself

## Upstreams and Declared Comparators

| Source | Runtime endpoint or path | Role in MVP |
|--------|---------------------------|-------------|
| `electrs` | `http://127.0.0.1:3002` | confirmed chain context and tip height |
| `mempool-api` | `http://127.0.0.1:8999/api/v1` | exchange BTC/USD price, mempool, fee context |
| `BRK` | `http://127.0.0.1:7070` | curated on-chain features only |
| `Hyperliquid Node API` | `http://127.0.0.1:12345` | Current MVP source for oracle and mark price |
| `Hyperliquid Websocket` | (Future Activation) | Upcoming real-time source for lowest latency |
| `hyperliquid-realtime-data` | `/media/sam/1TB/hyperliquid-realtime-data` | historical and fallback reference (files) |
| `UTXOracle API` today | systemd on `8001` | existing API baseline, not final MVP deployment |

Implementation note verified on `2026-03-20`:
- `12345` is listening on the host, but current responses do not match the expected Hyperliquid JSON payload.
- The MVP implementation must therefore validate the node response at runtime and fall back to `hyperliquid-realtime-data` when the node endpoint is invalid or unavailable.
- The architecture still preserves `Hyperliquid Node API` as the intended primary live comparison source once the endpoint is corrected.

## Primary Users

### User Story 1: Live Consumer

As a downstream trading or backtest engine,
I want one stable live snapshot endpoint,
so that I can consume canonical oracle data and comparison fields without embedding BRK, mempool, or Hyperliquid logic.

### User Story 2: Service Operator

As an operator,
I want a Docker deployed service with health, readiness, and persistence,
so that the system can run continuously on the current host.

### User Story 3: Research Operator

As a research operator,
I want to see live match or deviation against declared external references,
so that I can evaluate whether UTXOracle is aligned or diverging in real time.

### User Story 4: Future Chart Validator

As a chart developer,
I want BRK preserved as a future validation surface,
so that our charts can later be checked visually against BRK and external providers without changing the live consumer contract.

## Functional Requirements

### FR1: Canonical Oracle Engine

The live service MUST use the existing UTXOracle library algorithm as the source of truth for `utxoracle_price`.

### FR2: Dockerized Live Service

The MVP MUST run as a Docker Compose deployment with at least:
- `utxoracle-live-worker`
- `utxoracle-live-api`

### FR3: Source Normalization

The worker MUST collect and normalize data from:
- `electrs` for confirmed Bitcoin data and block height context
- `mempool-api` for market reference price and mempool context
- `BRK` for a curated subset of on-chain features only
- `Hyperliquid Node API` for primary oracle and mark price comparison when valid
- `hyperliquid-realtime-data` as the required local fallback for external oracle and mark price comparison

### FR4: Declared Live Comparisons

The live snapshot MUST include explicit comparison fields against all declared live references that are available in the deployment.

Required MVP comparisons:
- `utxoracle_price` vs `mempool_exchange_price`
- `utxoracle_price` vs `hyperliquid_oracle_price`
- `utxoracle_price` vs `hyperliquid_mark_price`

The payload MUST expose both raw values and deviation fields in basis points.

### FR5: Curated BRK Feature Surface

The service MUST expose a compact, versioned payload. Raw BRK metric fanout MUST NOT be the public consumer contract.

Initial BRK feature set:
- `brk_realized_price`
- `brk_liveliness`
- `brk_reserve_risk`

### FR6: Consumer API Contract

The API MUST expose at least:
- `GET /api/v1/live/snapshot`
- `GET /api/v1/live/history`
- `GET /api/v1/live/comparison/latest`
- `GET /health`
- `GET /ready`

### FR7: History and Persistence

The system MUST persist normalized live snapshots into local storage suitable for latest reads and short-horizon history queries.

### FR8: Configurability

All source endpoints and ports MUST be configured through environment variables. New live components MUST NOT rely on hardcoded defaults such as `localhost:3001`, `localhost:3110`, or `8000`.

### FR9: Source Health Visibility

Health responses MUST include per-source status, last success timestamp, and last observed block height where relevant.

### FR10: Degraded Operation

If one or more upstreams fail temporarily, the service MUST continue serving the latest valid snapshot with a degraded status rather than returning no data.

### FR11: Future Visual Validation Boundary

The spec MUST explicitly reserve BRK visual validation as a follow-up track. The MVP live consumer API MUST NOT be coupled to the future chart validation dashboard.

## Live Snapshot Contract

Example response for `GET /api/v1/live/snapshot`:

```json
{
  "schema_version": "v1",
  "timestamp": "2026-03-20T11:45:00Z",
  "block_height": 941428,
  "utxoracle_price": 84211.52,
  "utxoracle_confidence": 0.82,
  "mempool_exchange_price": 84302.11,
  "hyperliquid_oracle_price": 84295.40,
  "hyperliquid_mark_price": 84310.80,
  "comparison": {
    "utxo_vs_mempool_bps": -10.75,
    "utxo_vs_hl_oracle_bps": -9.95,
    "utxo_vs_hl_mark_bps": -11.02
  },
  "features": {
    "brk_realized_price": 47102.33,
    "brk_liveliness": 0.618,
    "brk_reserve_risk": 0.0041
  },
  "source_health": {
    "electrs": "healthy",
    "mempool_api": "healthy",
    "brk": "healthy",
    "hyperliquid": "healthy"
  }
}
```

## Operational Constraints

1. `mempool` and `electrs` remain shared host infrastructure.
2. `BRK` remains a separate upstream service.
3. the live service must tolerate temporary upstream failures and continue serving the latest valid snapshot.
4. the public contract must stay stable even if internal BRK feature selection changes.
5. BRK visual chart validation is a separate future deliverable.

## Success Criteria

| Criterion | Target |
|----------|--------|
| Service availability | `docker compose -f docker-compose.live.yml up -d` results in healthy worker and API |
| Snapshot freshness | market fields newer than 5 seconds during healthy operation |
| Comparison surface | response always includes current raw reference values plus deviation fields when sources are healthy |
| Block alignment | reported `block_height` matches `electrs` tip when healthy |
| Consumer simplicity | Nautilus or a backtest engine can consume one endpoint without BRK-specific logic |
| Resilience | worker survives upstream timeout without losing last good snapshot |
| Config correctness | no live component depends on hardcoded `3001`, `3110`, or `8000` |

## Deferred Follow-up

After the MVP live service, define a separate spec for:
- BRK visual validation charts
- side-by-side chart parity vs external providers such as CheckOnChain-style references
- visual and numeric validation workflows for overlapping on-chain features
