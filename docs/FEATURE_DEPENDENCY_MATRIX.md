# UTXOracle Feature Dependency Matrix

Date: 2026-04-01

Status: Initial provenance and dependency matrix, updated through `M2` hardening

Machine-readable source of truth:

- [docs/contracts/feature_provenance_manifest.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_provenance_manifest.yaml)

Scope note:

- this first-pass matrix covers the priority route families required by spec-045
- it is intentionally narrower than the full contract registry in spec-044

## 1. Backend Class Vocabulary

- `questdb`: served from QuestDB tables via `QuestDBRepository`
- `duckdb_utxo_lifecycle`: served from DuckDB `utxo_lifecycle` / `utxo_lifecycle_full` and related tables
- `duckdb_daily_prices`: served from DuckDB `daily_prices`
- `bitcoin_core_rpc`: served directly from Bitcoin Core RPC-backed computations
- `external_api`: served from an upstream HTTP API outside the repo
- `computed_inline`: route computes inline without a persistent backend as its core source
- `hybrid`: route reads from more than one backend class or combines live storage with external sources

## 2. Failure Vocabulary

- `empty`: route is healthy but has no data to return yet
- `stale`: route returns old data beyond its freshness target
- `degraded`: route serves a partial or reduced answer
- `misconfigured`: required env, credentials, DB, or service bootstrap is missing
- `placeholder`: route is exposed but its logic is intentionally incomplete or mocked

## 3. Route Family Matrix

| Surface ID | Route family | Backend class | Primary tables / artifacts | Upstreams | Required env / config | Writer owner | Read path owner | Freshness source | Failure highlights |
|------|------|------|------|------|------|------|------|------|------|
| `live_snapshot_surface` | `/api/v1/live/*` | `hybrid` | `LiveSnapshotStore` snapshots | `electrs`, `mempool`, `BRK`, `Hyperliquid`, UTXOracle block oracle | `ELECTRS_HTTP_URL`, `MEMPOOL_API_URL` or `MEMPOOL_API_V1_URL`, `BRK_BASE_URL`, `HYPERLIQUID_NODE_API_URL`, `LIVE_RETENTION_HOURS`, `LIVE_SOURCE_TIMEOUT_SECONDS`, `LIVE_WORKER_LOCK_PATH`, `LIVE_ORACLE_TX_CONCURRENCY`, `LIVE_ORACLE_MIN_TX_COUNT` | `scripts.live.worker.LiveWorker` | `api.routes.live` | snapshot timestamp in `LiveSnapshotStore` | `503` when empty; stale after `60s`; degraded when sources are unhealthy |
| `live_chart_surface` | `/api/v1/charts/*` | `hybrid` | `LiveSnapshotStore` snapshots | same live upstreams as snapshot surface; BRK for realized-price chart | same as live snapshot surface | `scripts.live.worker.LiveWorker` | `api.routes.charts` | latest snapshot used in chart payload | `503` when no snapshots; stale/degraded encoded in payload metadata |
| `prices_surface` | `/api/prices/*` | `questdb` | `price_analysis` | UTXOracle calculator + mempool price feed via daily analysis pipeline | `QUESTDB_PG_HOST`, `QUESTDB_PG_PORT`, `QUESTDB_PG_USER`, `QUESTDB_PG_PASSWORD`, `QUESTDB_PG_DATABASE` | `scripts.daily_analysis.py` via `QuestDBRepository` | `api.main` | newest `price_analysis.ts` row | `404` when empty; `500` on QuestDB failure |
| `metrics_latest_surface` | `/api/metrics/latest` | `questdb` | `metrics` | `scripts.metrics` bundle produced by analysis pipeline | QuestDB PG env set above | `scripts.daily_analysis.py` + `scripts.metrics.save_metrics_to_db` | `api.main` | newest `metrics.ts` row | `404` when empty; `500` on QuestDB failure |
| `whale_query_surface` | `/api/whale/{transactions,summary,transaction/{txid}}` | `questdb` | `mempool_predictions` | mempool whale monitor / prediction writers | QuestDB PG env set above | `scripts/mempool_whale_monitor.py` and related whale writers | `api.mempool_whale_endpoints` | newest `mempool_predictions.ts` row | `404` for missing txid; `500` on DB query failure |
| `exchange_netflow_surface` | `/api/metrics/exchange-netflow*` | `duckdb_utxo_lifecycle` | `utxo_lifecycle_full`, `exchange_addresses.csv` | none beyond local dataset | `UTXO_DB_PATH` or `DUCKDB_PATH`; `data/exchange_addresses.csv` must exist | UTXO lifecycle bootstrap/sync pipeline + exchange address scraper | `api.main` | latest available UTXO data and exchange address CSV mtime | `503` when DB missing; `404` when tables missing |
| `exchange_addresses_stats_surface` | `/api/exchange-addresses/stats` | `computed_inline` | `data/exchange_addresses.csv` | none | local CSV file must exist | exchange address scraper process | `api.main` | CSV file mtime | `404` when CSV missing; `500` on file read errors |
| `binary_cdd_surface` | `/api/metrics/binary-cdd` | `duckdb_utxo_lifecycle` | `utxo_lifecycle_full` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | UTXO lifecycle bootstrap/sync pipeline | `api.main` | latest available UTXO data | `503` when DB missing; `404` when tables missing |
| `net_realized_pnl_surface` | `/api/metrics/net-realized-pnl*` | `duckdb_utxo_lifecycle` | `utxo_lifecycle_full` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | UTXO lifecycle bootstrap/sync pipeline | `api.main` | latest spent UTXO coverage | `503` when DB missing; `404` when tables missing |
| `pl_ratio_surface` | `/api/metrics/pl-ratio*` | `duckdb_utxo_lifecycle` | `utxo_lifecycle_full` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | UTXO lifecycle bootstrap/sync pipeline | `api.main` | latest spent UTXO coverage | `503` when DB missing; `404` when tables missing |
| `sopr_surface` | `/api/metrics/sopr` | `duckdb_utxo_lifecycle` | `utxo_lifecycle`, `utxo_lifecycle_full` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | UTXO lifecycle bootstrap/sync pipeline | `api.main` | latest spent UTXO coverage | `503` when DB missing; `404` when tables missing |
| `nvt_surface` | `/api/metrics/nvt` | `duckdb_utxo_lifecycle` | `utxo_lifecycle_full`, `block_heights` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | UTXO lifecycle bootstrap/sync pipeline + `block_heights` build | `api.main` | latest UTXO coverage and `block_heights` tip | `503` on insufficient data or missing schema |
| `volatility_surface` | `/api/metrics/volatility` | `duckdb_daily_prices` | `daily_prices` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | `scripts.bootstrap.build_price_table` | `api.main` | newest `daily_prices.date` | `503` on insufficient history or missing table |
| `puell_multiple_surface` | `/api/metrics/puell-multiple` | `computed_inline` | inline constants; optional read of `utxo_lifecycle` for block height only | none | none for runtime-demoted serving; `UTXO_DB_PATH` was only optional enrichment in the old path | none for core calculation | `api.main` | request-time demotion | route now returns `501` until the 365-day denominator is backed by real miner revenue history |
| `mining_pulse_surface` | `/api/metrics/mining-pulse` | `bitcoin_core_rpc` | live block interval observations from RPC | Bitcoin Core RPC | `BITCOIN_RPC_URL`, `BITCOIN_RPC_USER`, `BITCOIN_RPC_PASSWORD` or equivalent RPC config | Bitcoin Core node | `api.main` | live tip and recent block intervals | `503` when RPC unavailable |
| `hash_ribbons_surface` | `/api/metrics/hash-ribbons` | `external_api` | in-memory fetched hashrate series | mempool hashrate API | external hashrate API reachability; no repo-local persistence required | external hashrate upstream | `api.main` | upstream response timestamp | `503` when upstream unavailable |
| `mining_economics_surface` | `/api/metrics/mining-economics*` | `hybrid` | live RPC results plus upstream hashrate history | Bitcoin Core RPC + external hashrate API | RPC config plus hashrate upstream reachability | Bitcoin Core node + external hashrate upstream | `api.main` | realtime endpoint uses RPC tip; history endpoint uses cached upstream history | degraded realtime behavior allowed when ribbons missing; history endpoint currently carries placeholder `pulse_zone` |
| `pro_risk_surface` | `/api/risk/pro*` | `computed_inline` | inline composite logic; no real metric fetch wiring yet | none in current route path | none required for current runtime-demoted behavior | none in current serving path | `api.main` | request-time demotion | `/api/risk/pro` and `/history` now return `501`; `/zones` remains static metadata |
| `models_core_surface` | `/api/v1/models*` | `computed_inline` | in-process model registry / handlers | none | none beyond app bootstrap | none | `api.routes.models` + `api.main` | request-time computation | may return `404` per model name; not contract-admitted |
| `power_law_surface` | `/api/v1/models/power-law*` | `duckdb_daily_prices` | `daily_prices` | none | `UTXO_LIFECYCLE_DB` or default DuckDB path | `scripts.bootstrap.build_price_table` | `api.main` | newest `daily_prices.date` | explicit power-law handler now wins deterministically; route remains research-only by contract |
| `rbn_validation_surface` | `/api/v1/validation/rbn/*` | `external_api` | local cache under `cache/rbn` | ResearchBitcoin.net API | `RBN_API_TOKEN`, `RBN_TIER`, `RBN_CACHE_TTL_HOURS`, `RBN_TIMEOUT_SECONDS` | `scripts.integrations.rbn_fetcher` cache writer | `api.main` | cache TTL or latest successful upstream fetch | `503` when misconfigured; `429` when quota exceeded; `404` when no comparison data exists |

## 4. Operator Notes

- `:8011` live routes are the canonical and only served fast plane for `nautilus_dev`.
- QuestDB-backed routes depend on `QuestDBRepository` PG connectivity and the presence of the relevant tables.
- DuckDB-backed routes fail in two materially different ways:
  - `503` when the DB file is absent or insufficiently populated
  - `404` or schema-specific `503` when the expected tables or views do not exist
- `computed_inline` does not mean “safe.” It only means the core value is produced inline without a persistent backend. `PRO Risk` and `Puell Multiple` remain contract-caveated or excluded for exactly this reason.
