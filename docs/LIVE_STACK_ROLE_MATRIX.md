# Live Stack Role Matrix

**Status**: Active reference for the live production direction
**Updated**: 2026-04-02 (post-`M7` governance plus metric source-of-truth freeze)

This document defines the correct role of `UTXOracle`, `BRK`, `electrs`, `mempool`, and `Hyperliquid` in the current live-first architecture.

Metric-level source-of-truth decisions for overlapping analytics now live in:

- [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)

## Current Runtime on Host

| Component | Runtime endpoint or path | Role |
|-----------|--------------------------|------|
| `UTXOracle Live API` | `http://127.0.0.1:8011` | **Primary live consumer API** — `api.apps.live:app`, production-scoped `GET /api/v1/live/*` + `/health` (Docker, `LIVE_ENABLED=true`; served snapshot source is QuestDB `live_snapshots`) |
| `UTXOracle Live Worker` | Docker container (no port) | Polling worker — writes live snapshots to `utxoracle_live.sqlite3` |
| `UTXOracle API` | `http://127.0.0.1:8001` | Explicit legacy FastAPI surface via `api.apps.legacy:app` (systemd, batch-oriented, non-canonical) |
| `BRK` | `http://127.0.0.1:7070` | Query surface + computed on-chain metrics |
| `electrs` | `http://127.0.0.1:3002` | Confirmed chain index and raw lookup |
| `mempool-api` | `http://127.0.0.1:8999/api/v1` | Live mempool, fees, mining stats, exchange price |
| `mempool-web` | `http://127.0.0.1:8080` | Explorer UI |
| `hyperliquid-node /info` | `http://127.0.0.1:3001/info` (POST) | Verified node metadata surface and future direct market query surface |
| `hyperliquid-node metrics` | `http://127.0.0.1:9101/metrics` | Hyperliquid node health and block-height metrics |
| `hyperliquid-node filtered oracle updates` | `/media/sam/4TB-NVMe/hyperliquid/filtered/hip3_oracle_updates_by_block` | Current verified oracle and mark comparison source |
| `hyperliquid-node realtime` | `/media/sam/4TB-NVMe/hyperliquid/realtime` | Optional low-latency persistence path; currently empty/off |

## Correct Component Roles

### UTXOracle

`UTXOracle` remains the canonical on-chain oracle engine.

Primary responsibilities:
- compute the Bitcoin price directly from confirmed on-chain activity
- expose the consumer-facing API contract for trading, research, and backtests
- persist local research datasets and custom metrics in DuckDB
- host repo-specific analytics not covered cleanly by upstream infrastructure

Important distinction:
- `UTXOracle` is the final product surface for downstream consumers
- it should not expose raw upstream complexity to trading engines
- on the current host, only `8011` is admitted as the production consumer contract

### BRK

`BRK` is the broad on-chain query and feature engine.

Primary responsibilities:
- provide block, transaction, address, and mempool-compatible query endpoints
- provide 1000+ computed on-chain metrics via REST and MCP
- act as the main feature provider for overlapping on-chain analytics such as realized price, MVRV, SOPR, NUPL, liveliness, and cohort metrics
- support visual validation and research workflows

Important distinction:
- `BRK` is not the final consumer contract for live trading systems
- `BRK` is an upstream feature provider and validation surface
- `BRK` does not replace external market or derivatives data sources

### electrs

`electrs` is the low-level confirmed-chain index and lookup layer.

Primary responsibilities:
- confirmed block and transaction lookup
- address and prevout access patterns needed by bootstrap and lifecycle sync flows
- stable raw chain data service for components that need indexed Bitcoin data but not a full analytics layer

Important distinction:
- `electrs` is not a broad feature engine
- `electrs` is infra, not a final analytics surface

### mempool-api

`mempool-api` is the live market and mempool context layer.

Primary responsibilities:
- exchange BTC/USD price updater
- mempool state and fee estimation
- mining statistics
- WebSocket and live transaction flows used by the whale pipeline

Important distinction:
- `mempool-api` is not a substitute for broad historical on-chain analytics
- in this repo it is a live feed and market context dependency, not the canonical oracle

### Hyperliquid

`Hyperliquid` is an external market reference delivered locally through the `hyperliquid-node` stack.

Primary responsibilities:
- oracle price reference
- mark price reference
- funding and open interest context for fusion or comparison
- node metadata and health visibility through `/info` and exporter metrics

Important distinction:
- `Hyperliquid` is never the canonical Bitcoin on-chain oracle source
- the currently verified comparison source is the filtered oracle-update dataset on `4TB-NVMe`
- `POST /info` is a real node API surface, but direct oracle and mark extraction remains optional until its supported request type is confirmed on this host
- `127.0.0.1:12345` is not part of the canonical Hyperliquid comparison path

## Feature Matrix

| Capability | UTXOracle | BRK | electrs | mempool-api | Hyperliquid | Recommended production source |
|-----------|-----------|-----|---------|-------------|-------------|-------------------------------|
| On-chain BTC price oracle | `YES` canonical | `PARTIAL` price metrics exist but different role | `NO` | `NO` | `NO` | `UTXOracle` |
| Confirmed block and tx lookup | `PARTIAL` through repo workflows | `YES` | `YES` | `PARTIAL` explorer style access | `NO` | `electrs` for raw sync, `BRK` for higher-level query and validation |
| Address and UTXO lookup | `PARTIAL` via sync pipeline | `YES` | `YES` | `PARTIAL` | `NO` | `electrs` and `BRK` |
| Live mempool feed | `NO` | `PARTIAL` internal mempool support exists | `NO` | `YES` | `NO` | `mempool-api` |
| Exchange BTC/USD price | `NO` | `NO` | `NO` | `YES` | `NO` | `mempool-api` |
| MVRV, NUPL, SOPR, liveliness, cohort metrics | `PARTIAL` repo implements many | `YES` broad surface | `NO` | `NO` | `NO` | `BRK` primary feature source, `UTXOracle` for validation and custom variants |
| UTXO lifecycle and DuckDB research tables | `YES` | `NO` direct repo-local workflow | `NO` | `NO` | `NO` | `UTXOracle` |
| Whale flow and exchange netflow analytics | `YES` repo-specific | `PARTIAL` mempool/address support only | `PARTIAL` raw input only | `YES` live input | `NO` | `UTXOracle` built on `mempool-api` plus `electrs` |
| Fee estimation and mining stats | `NO` | `PARTIAL` mempool endpoints | `NO` | `YES` | `NO` | `mempool-api` |
| Derivatives, oracle mark compare, funding, OI | `PARTIAL` consumer side only | `NO` | `NO` | `NO` | `YES` | `Hyperliquid` |
| Stable consumer API for trading engines | `TARGET` | `NO` | `NO` | `NO` | `NO` | `UTXOracle Live API` |
| Human visual validation dashboard | `PARTIAL` current repo dashboards | `YES` excellent upstream candidate | `NO` | `PARTIAL` explorer UI | `NO` | `BRK` plus UTXOracle overlays |

## What Is Unique to UTXOracle

These should remain first-class repo responsibilities even when BRK is available:
- canonical on-chain oracle price methodology
- custom DuckDB-backed research workflows
- UTXO lifecycle based analytics and experimental metrics
- consumer-facing normalized API for Nautilus Trader and backtest engines
- fusion of on-chain, mempool, and derivatives reference data into one live snapshot

## What BRK Does Better

These are the areas where BRK should be preferred as an upstream:
- breadth of precomputed on-chain metrics
- consistent feature discovery via REST and MCP
- large cohort surface and vector queries
- query ergonomics for blocks, addresses, txs, and metrics
- future visual metric exploration and CheckOnChain-style validation

Metric governance note:

- if `BRK` already owns the shared metric semantics, the repo should not productize a duplicate local route by default
- current metric-level decisions are frozen in [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)

## What mempool plus electrs Still Own

These remain shared infrastructure responsibilities:
- live mempool state
- exchange price updater
- fee and mining context
- low-level confirmed chain indexing
- whale pipeline input feeds already wired into this repo

## Recommended Production Topology

Use the following division of responsibility:

1. `bitcoind` as root truth
2. `electrs` as confirmed-chain raw index
3. `mempool-api` as live mempool and exchange-price context
4. `BRK` as the primary on-chain feature provider and validation surface
5. `Hyperliquid` as external oracle and derivatives comparator
6. `UTXOracle Live API` as the only downstream consumer contract

## Documentation Drift to Fix

The repo still contains legacy references that should not be treated as current truth:
- `electrs` on `localhost:3001`
- `BRK` on `localhost:3110`
- FastAPI on `localhost:8000`
- architecture text that assumes `mempool+electrs` are the whole live stack

Current host reality is:
- `electrs` on `3002`
- `BRK` on `7070`
- `hyperliquid-node /info` on `3001` via `POST`
- `hyperliquid-node metrics` on `9101`
- filtered oracle updates on `/media/sam/4TB-NVMe/hyperliquid/filtered/hip3_oracle_updates_by_block`
- current systemd FastAPI on `8001` is explicit legacy
- production-scoped FastAPI on `8011` boots through `api.apps.live:app`
- `127.0.0.1:12345` is not the canonical Hyperliquid source for this stack

## Immediate Live Direction (spec-040 COMPLETE — 2026-03-23)

1. ✅ `UTXOracle Live API` on `8011` is operational — primary consumer contract
2. ✅ curated `BRK` features consumed via `BrkClient.fetch_curated_features()` (stale when BRK is down, gracefully degraded)
3. ✅ `mempool-api` live exchange price and mempool context wired into worker
4. ✅ `electrs` block tip polling drives the block-cadence refresh loop
5. deferred: BRK visual validation dashboard for CheckOnChain-style chart parity
