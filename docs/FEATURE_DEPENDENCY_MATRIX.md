# UTXOracle Feature Dependency Matrix

Date: 2026-04-02

Status: Initial provenance and dependency matrix, updated through `M6` selective Wave 2 productization plus the metric source-of-truth manifest freeze

Machine-readable source of truth:

- [docs/contracts/feature_provenance_manifest.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_provenance_manifest.yaml)
- [docs/contracts/metric_source_of_truth_manifest.yaml](/media/sam/1TB/UTXOracle/docs/contracts/metric_source_of_truth_manifest.yaml) for metric-level `BRK` vs local ownership decisions

Scope note:

- this first-pass matrix covers the priority route families required by spec-045
- it is intentionally narrower than the full contract registry in spec-044
- it is a backend dependency view, not a complete metric-level ownership policy; overlapping `BRK` metrics must also follow [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)

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
| `live_snapshot_surface` | `/api/v1/live/*` | `hybrid` | `LiveSnapshotStore` snapshots | `electrs`, `mempool`, `BRK`, `Hyperliquid`, UTXOracle block oracle | `ELECTRS_HTTP_URL`, `MEMPOOL_API_URL` or `MEMPOOL_API_V1_URL`, `BRK_BASE_URL`, `HYPERLIQUID_NODE_API_URL`, `LIVE_RETENTION_HOURS`, `LIVE_SOURCE_TIMEOUT_SECONDS`, `LIVE_WORKER_LOCK_PATH`, `LIVE_ORACLE_TX_CONCURRENCY`, `LIVE_ORACLE_MIN_TX_COUNT` | `scripts.live.worker.LiveWorker` | `api.routes.live` | snapshot timestamp in `LiveSnapshotStore` | `503` when empty; stale at `>=30s`; degraded when sources are unhealthy |
| `live_chart_surface` | `/api/v1/charts/*` | `hybrid` | `LiveSnapshotStore` snapshots | same live upstreams as snapshot surface; BRK for realized-price chart | same as live snapshot surface | `scripts.live.worker.LiveWorker` | `api.routes.charts` | latest snapshot used in chart payload | `503` when no snapshots; stale/degraded encoded in payload metadata |
| `prices_surface` | `/api/prices/*` | `questdb` | `price_analysis` | UTXOracle calculator + mempool price feed via daily analysis pipeline | `QUESTDB_PG_HOST`, `QUESTDB_PG_PORT`, `QUESTDB_PG_USER`, `QUESTDB_PG_PASSWORD`, `QUESTDB_PG_DATABASE` | `scripts.daily_analysis.py` via `QuestDBRepository` | `api.main` | newest `price_analysis.ts` row | `404` when empty; `500` on QuestDB failure |
| `metrics_latest_surface` | `/api/metrics/latest` | `questdb` | `metrics` | `scripts.metrics` bundle produced by analysis pipeline | QuestDB PG env set above | `scripts.daily_analysis.py` + `scripts.metrics.save_metrics_to_db` | `api.main` | newest `metrics.ts` row | `404` when empty; `500` on QuestDB failure |
| `whale_query_surface` | `/api/whale/{transactions,summary,transaction/{txid}}` | `questdb` | `mempool_predictions`; optional `address_clusters` enrichment | mempool whale monitor / prediction writers; optional clustering bootstrap | QuestDB PG env set above | `scripts/mempool_whale_monitor.py`, clustering bootstrap, and related whale writers | `api.mempool_whale_endpoints` | newest `mempool_predictions.ts` row; optional enrichment reads current `address_clusters` rows | `404` for missing txid; `500` on base query failure; entity enrichment degrades to omission when `address_clusters` is absent or ambiguous |
| `exchange_netflow_surface` | `/api/metrics/exchange-netflow*` | `duckdb_utxo_lifecycle` | `utxo_lifecycle_full`, `exchange_addresses.csv` | none beyond local dataset | `UTXO_DB_PATH` or `DUCKDB_PATH`; `data/exchange_addresses.csv` must exist | UTXO lifecycle bootstrap/sync pipeline + exchange address scraper | `api.main` | latest available UTXO data and exchange address CSV mtime | `503` when DB missing; `404` when tables missing |
| `exchange_addresses_stats_surface` | `/api/exchange-addresses/stats` | `computed_inline` | `data/exchange_addresses.csv` | none | local CSV file must exist | exchange address scraper process | `api.main` | CSV file mtime | `404` when CSV missing; `500` on file read errors |
| `binary_cdd_surface` | `/api/metrics/binary-cdd` | `duckdb_utxo_lifecycle` | `utxo_lifecycle_full` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | UTXO lifecycle bootstrap/sync pipeline | `api.main` | latest available UTXO data | `503` when DB missing; `404` when tables missing |
| `net_realized_pnl_surface` | `/api/metrics/net-realized-pnl*` | `duckdb_utxo_lifecycle` | `utxo_lifecycle_full` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | UTXO lifecycle bootstrap/sync pipeline | `api.main` | latest spent UTXO coverage | `503` when DB missing; `404` when tables missing |
| `pl_ratio_surface` | `/api/metrics/pl-ratio*` | `duckdb_utxo_lifecycle` | `utxo_lifecycle_full` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | UTXO lifecycle bootstrap/sync pipeline | `api.main` | latest spent UTXO coverage | `503` when DB missing; `404` when tables missing |
| `sopr_surface` | `/api/metrics/sopr` | `duckdb_utxo_lifecycle` | `utxo_lifecycle`, `utxo_lifecycle_full` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | UTXO lifecycle bootstrap/sync pipeline | `api.main` | latest spent UTXO coverage | `503` when DB missing; `404` when tables missing |
| `nvt_surface` | `/api/metrics/nvt` | `duckdb_utxo_lifecycle` | `utxo_lifecycle_full`, `block_heights` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | UTXO lifecycle bootstrap/sync pipeline + `block_heights` build | `api.main` | latest UTXO coverage and `block_heights` tip | `503` on insufficient data or missing schema |
| `nupl_surface` | `/api/metrics/nupl` | `duckdb_utxo_lifecycle` | `utxo_lifecycle_full` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | UTXO lifecycle bootstrap/sync pipeline | `api.main` | latest visible `utxo_lifecycle_full` snapshot at request time | `503` when DB missing; `404` when schema or usable unspent snapshot is missing; `pct_supply_in_profit` is explicitly estimated |
| `cost_basis_surface` | `/api/metrics/cost-basis` | `duckdb_utxo_lifecycle` | `utxo_lifecycle_full` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | UTXO lifecycle bootstrap/sync pipeline | `api.main` | latest visible `utxo_lifecycle_full` snapshot at request time | `503` when DB missing; `404` when schema or usable cost-basis snapshot is missing |
| `volatility_surface` | `/api/metrics/volatility` | `duckdb_daily_prices` | `daily_prices` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | `scripts.bootstrap.build_price_table` | `api.main` | newest `daily_prices.date` | `503` on insufficient history or missing table |
| `wallet_and_cohort_surface` | `/api/metrics/{address-cohorts,wallet-waves,absorption-rates}` | `duckdb_utxo_lifecycle` | `utxo_lifecycle_full` | none | `UTXO_DB_PATH` or `DUCKDB_PATH` | UTXO lifecycle bootstrap/sync pipeline | `scripts.metrics.address_cohorts`, `scripts.metrics.wallet_waves`, `scripts.metrics.absorption_rates`, `api.main` | latest visible `creation_block`; absorption baseline reconstructed from `current_block - window_days*144` | `503` when DB missing; `404` on missing schema; address cohorts can return zeroed cohorts, wallet waves returns `404` when no addressable balances exist, absorption rates can return `200` with `has_historical_data=false` when baseline is unavailable |
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
- Wave 1 wallet/cohort routes are now live on DuckDB:
  - `address-cohorts` is current-state only
  - `wallet-waves` is current-state only
  - `absorption-rates` reconstructs its historical baseline on demand from `spent_block` semantics and may respond with `has_historical_data=false`
- Selective Wave 2 DuckDB routes are now live as research surfaces:
  - `nupl` serves explicit estimate metadata for `pct_supply_in_profit`
  - `cost-basis` serves current-state STH/LTH cost basis with route-level `404` on unusable snapshots
- Whale canonicalization is now explicit:
  - `/api/whale/{transactions,summary,transaction/{txid}}` is the only canonical whale query family
  - `/api/whale/{latest,historical,history}` remains outside the canonical surface and now returns `410 Gone` deprecation metadata
- Whale entity foundations are additive:
  - base whale events come from `mempool_predictions`
  - optional enrichment reads `address_clusters` only when exchange addresses exist
  - missing or conflicting enrichment must not fail the base whale event response
- `computed_inline` does not mean “safe.” It only means the core value is produced inline without a persistent backend. `PRO Risk` and `Puell Multiple` remain contract-caveated or excluded for exactly this reason.
- `duckdb_utxo_lifecycle` also does not imply “preferred source of truth.” Some overlapping macro metrics may remain local research routes while `BRK` is still the preferred shared production source.
