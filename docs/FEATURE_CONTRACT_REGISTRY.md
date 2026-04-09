# UTXOracle Feature Contract Registry

Date: 2026-04-08

Status: Current registry view, updated through `M7`, Wave 1 QuestDB promotion, the 2026-04-05 service-profile classification, and spec-053 entity route registration

Machine-readable source of truth:

- [docs/contracts/feature_contract_registry.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_contract_registry.yaml)

Primary inputs:

- [docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md)
- [docs/FEATURE_SERVICE_ROADMAP_2026-04-01.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ROADMAP_2026-04-01.md)
- [docs/FEATURE_SERVICE_WAVE2_DECISION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_WAVE2_DECISION_2026-04-02.md)
- [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)
- [specs/044-feature-service-contract-registry/spec.md](/media/sam/1TB/UTXOracle/specs/044-feature-service-contract-registry/spec.md)

## 1. Purpose

This registry is the contract layer on top of the audited route inventory.

If a route family is not present in the registry, it is not part of the supported consumer surface.

The registry separates:

- audit reality: `runtime verified`, `code implemented`, `calculator only`, `placeholder`
- consumer admission: `tier_1_production`, `tier_2_production_with_caveats`, `tier_3_research`, `tier_4_not_admitted`

## 2. Required Entry Fields

Every registry entry carries:

- `surface_id`
- `route_family`
- `consumer`
- `current_label`
- `admission_tier`
- `source_of_truth`
- `backend_class`
- `freshness_target`
- `empty_state_policy`
- `stale_state_policy`
- `known_caveats`
- `owner`
- `version`
- `deprecation_status`

## 3. Tier Definitions

### `tier_1_production`

Stable for production consumption under the declared host policy, backend dependency, and freshness rules.

### `tier_2_production_with_caveats`

Admitted for production use only when the operator understands and accepts the declared caveats and dependency footprint.

### `tier_3_research`

Available for exploration, validation, or internal tooling, but not admitted as part of the production feature contract for `nautilus_dev`.

### `tier_4_not_admitted`

Explicitly excluded from the supported contract because they are placeholder, shadowed, mocked, or otherwise materially misleading today.

## 4. Deprecation Status Vocabulary

- `none`: no deprecation is currently declared
- `duplicate_alias_present`: duplicate exposure exists outside the canonical host policy
- `deprecated_alias_active`: legacy compatibility route remains exposed only to advertise migration
- `secondary_on_8001`: canonical host moved to `:8011`, but `:8001` still serves the route as a documented secondary legacy path
- `legacy_placeholder_candidate`: legacy surface should be removed, deprecated, or reimplemented
- `candidate_for_demotion_or_reimplementation`: exposed route should not remain admitted in current form
- `blocked_pending_route_fix`: route family is blocked by a routing or serving defect

## 5. Contract Summary

| Surface ID | Route family | Current label | Admission tier | Primary consumer | Canonical host | Backend class | Owner | Key caveats |
|------|------|------|------|------|------|------|------|------|
| `live_snapshot_surface` | `/api/v1/live/*` | `runtime verified` | `tier_1_production` | `nautilus_dev`, operators | `:8011` | `hybrid` | `scripts.live.worker` + `api.routes.live` | Dedicated live app is now the only served host for this surface |
| `live_chart_surface` | `/api/v1/charts/*` | `runtime verified` | `tier_1_production` | `nautilus_dev`, research | `:8011` | `hybrid` | `scripts.live.worker` + `api.routes.charts` | Depends on live snapshot store and upstream source health |
| `prices_surface` | `/api/prices/*` | `runtime verified` | `tier_1_production` | `nautilus_dev`, research | `:8011` | `questdb` | `scripts.daily_analysis.py` + `api.routes.questdb` | `:8001` remains active only as a secondary legacy path with migration hint header |
| `metrics_latest_surface` | `/api/metrics/latest` | `runtime verified` | `tier_1_production` | `nautilus_dev`, research | `:8011` | `questdb` | `scripts.daily_analysis.py` + `scripts.metrics.save_metrics_to_db` + `api.routes.questdb` | `:8001` remains active only as a secondary legacy path with migration hint header |
| `whale_query_surface` | `/api/whale/{transactions,summary,transaction/{txid}}` | `runtime verified` | `tier_2_production_with_caveats` | research, `nautilus_dev` future forensics | `:8011` | `questdb` | `mempool whale monitor` + `address cluster bootstrap` + `api.mempool_whale_endpoints` | Canonical whale query family now serves additive `whale_event.v1` fields; entity enrichment is best-effort and `:8001` remains secondary with migration hint header |
| `exchange_netflow_surface` | `/api/metrics/exchange-netflow*` | `code implemented` | `tier_2_production_with_caveats` | `nautilus_dev`, research | `:8001` | `duckdb_utxo_lifecycle` | `scripts.metrics.exchange_netflow` + `api.main` | Requires populated DuckDB and exchange address CSV |
| `binary_cdd_surface` | `/api/metrics/binary-cdd` | `code implemented` | `tier_2_production_with_caveats` | `nautilus_dev`, research | `:8001` | `duckdb_utxo_lifecycle` | `scripts.metrics.binary_cdd` + `api.main` | Returns `503`/`404` when DuckDB or tables are absent |
| `net_realized_pnl_surface` | `/api/metrics/net-realized-pnl*` | `code implemented` | `tier_2_production_with_caveats` | `nautilus_dev`, research | `:8001` | `duckdb_utxo_lifecycle` | `scripts.metrics.net_realized_pnl` + `api.main` | Requires populated spent UTXO history |
| `pl_ratio_surface` | `/api/metrics/pl-ratio*` | `code implemented` | `tier_2_production_with_caveats` | `nautilus_dev`, research | `:8001` | `duckdb_utxo_lifecycle` | `scripts.metrics.pl_ratio` + `api.main` | Requires populated spent UTXO history |
| `sopr_surface` | `/api/metrics/sopr` | `code implemented` | `tier_2_production_with_caveats` | `nautilus_dev`, research | `:8001` | `duckdb_utxo_lifecycle` | `scripts.metrics.utxo_lifecycle` + `api.main` | Requires `utxo_lifecycle_full` and current spent data |
| `nvt_surface` | `/api/metrics/nvt` | `code implemented` | `tier_2_production_with_caveats` | `nautilus_dev`, research | `:8001` | `duckdb_utxo_lifecycle` | `scripts.metrics.nvt` + `api.main` | Also depends on `block_heights`; default `current_price` query arg can alter outputs |
| `volatility_surface` | `/api/metrics/volatility` | `code implemented` | `tier_2_production_with_caveats` | `nautilus_dev`, research | `:8001` | `duckdb_daily_prices` | `scripts.bootstrap.build_price_table` + `api.main` | Requires populated `daily_prices` history |
| `mining_pulse_surface` | `/api/metrics/mining-pulse` | `code implemented` | `tier_2_production_with_caveats` | `nautilus_dev`, research | `:8001` | `bitcoin_core_rpc` | `scripts.metrics.mining_economics` + `api.main` | Hard dependency on Bitcoin Core RPC availability |
| `hash_ribbons_surface` | `/api/metrics/hash-ribbons` | `code implemented` | `tier_2_production_with_caveats` | `nautilus_dev`, research | `:8001` | `external_api` | `scripts.data.hashrate_fetcher` + `api.main` | Hard dependency on hashrate upstream availability |
| `mining_economics_surface` | `/api/metrics/mining-economics*` | `code implemented` | `tier_2_production_with_caveats` | `nautilus_dev`, research | `:8001` | `hybrid` | `scripts.metrics.mining_economics` + `api.main` | History path hardcodes `pulse_zone="NORMAL"` |
| `exchange_addresses_stats_surface` | `/api/exchange-addresses/stats` | `code implemented` | `tier_3_research` | operators, research | `:8001` | `computed_inline` | `api.main` | Reads local CSV metadata only; not admitted to `nautilus_dev` |
| `nupl_surface` | `/api/metrics/nupl` | `code implemented` | `tier_3_research` | research | `:8001` | `duckdb_utxo_lifecycle` | `scripts.metrics.nupl` + `scripts.metrics.realized_metrics` + `api.main` | `pct_supply_in_profit` remains an explicit estimate (`nupl_linear_proxy`), not a direct per-UTXO profit-state field |
| `cost_basis_surface` | `/api/metrics/cost-basis` | `runtime verified` | `tier_1_production` | research, `nautilus_dev` | `:8011` | `questdb` | `scripts.metrics.materialize_wave1` + `api.routes.questdb` | Latest snapshot is materialized and served on `:8011`; admitted field subset only |
| `models_core_surface` | `/api/v1/models`, `/api/v1/models/{name}/predict`, `/api/v1/models/backtest/{name}`, `/api/v1/models/compare`, `/api/v1/models/ensemble` | `code implemented` | `tier_3_research` | research | `:8001` | `computed_inline` | `api.routes.models` | Not part of first consumer slice |
| `rbn_validation_surface` | `/api/v1/validation/rbn/*` | `code implemented` | `tier_3_research` | operators, research | `:8001` | `external_api` | `scripts.integrations.rbn_fetcher` + `api.main` | Requires `RBN_API_TOKEN` and is quota-bound |
| `btc_feature_bundles_surface` | `/api/features/btc/*` | `runtime verified` | `tier_1_production` | `nautilus_dev` | `:8011` | `questdb` | `scripts.live.bundle_writer` + `api.routes.features` | Materialized asynchronously by the background bundle writer |
| `btc_signal_snapshot_surface` | `/api/signals/btc/*` | `runtime verified` | `tier_1_production` | `nautilus_dev` | `:8011` | `questdb` | `scripts.live.signal_writer` + `api.routes.signals` | Derived strictly from admitted feature bundles |
| `entity_intelligence_surface` | `/api/entities/*` | `code implemented` | `tier_3_research` | research | `:8011` | `questdb` | `scripts.clustering.backfill_entity_registry_sampled` + `scripts.live.flow_aggregator` + `scripts.bootstrap.sync_entities_to_questdb` + `api.routes.entities` | Research-only entity intelligence surface on `:8011`; accepts legacy `cluster:*` aliases read-only and depends on daily registry/flow materialization |
| `advanced_research_surface` | `/api/metrics/{advanced,wasserstein*,cointime*,urpd,supply-profit-loss,reserve-risk,sell-side-risk,cdd-vdd,revived-supply}` | `mixed research surface` | `tier_3_research` | research | `:8001` | `hybrid` | `scripts.metrics.*` + `api.main` | `cointime*` is code implemented on `:8001`, but the broader research bucket remains mixed and some members still return `501`; `reserve-risk` is additionally frozen by the metric source-of-truth manifest as a `BRK`-first overlapping metric rather than a default local productization target |
| `wallet_and_cohort_surface` | `/api/metrics/{address-cohorts,wallet-waves,absorption-rates}` | `runtime verified` | `tier_1_production` | research, `nautilus_dev` | `:8011` | `questdb` | `scripts.metrics.materialize_wave1` + `api.routes.questdb` | Latest snapshots are materialized and served on `:8011`; `wallet-waves/history` remains outside the admitted slice |
| `power_law_surface` | `/api/v1/models/power-law*` | `code implemented` | `tier_3_research` | research | `:8001` | `duckdb_daily_prices` | `api.main` + `scripts.metrics.power_law` | Dedicated handler now wins deterministically, but the surface remains outside the first `nautilus_dev` contract slice |
| `research_operations_surface` | `/api/research/tier-stats` | `code implemented` | `tier_3_research` | operators, research | `:8011` | `questdb` | `api.routes.questdb` | Monitoring for fetch tier fallbacks (T140) |
| `pro_risk_surface` | `/api/risk/pro*` | `placeholder` | `tier_4_not_admitted` | research only today | `:8001` | `computed_inline` | `api.main` + `scripts.metrics.pro_risk` | `/api/risk/pro` and `/history` are now runtime-demoted; only `/zones` remains usable static metadata |
| `puell_multiple_surface` | `/api/metrics/puell-multiple` | `placeholder` | `tier_4_not_admitted` | research only today | `:8001` | `computed_inline` | `api.main` | Runtime-demoted until real 365-day miner revenue history is wired |
| `legacy_whale_placeholder_surface` | `/api/whale/{latest,historical,history}` | `code implemented` | `tier_4_not_admitted` | none | `:8001` | `computed_inline` | `api.main` | Legacy whale aliases now return explicit `410 Gone` migration stubs and are outside the canonical whale surface |
| `wallet_waves_history_placeholder_surface` | `/api/metrics/wallet-waves/history` | `placeholder` | `tier_4_not_admitted` | none | `:8001` | `computed_inline` | `api.main` | Route now returns explicit `503` until historical wallet-wave snapshots are materialized |
| `main_operational_pages_surface` | `/{,health,metrics,whale,dashboard,monitor,power-law,power_law}` | `code implemented` | `tier_4_not_admitted` | operators | `:8001` | `computed_inline` | `api.main` | Useful operationally, but not part of the admitted feature API contract |

## 6. Governance Rules

Any change to an admitted route family must be classified as one of:

- additive, backward compatible
- caveat change, non-breaking but operationally relevant
- breaking contract change
- deprecation

Breaking changes require:

1. registry version update
2. migration note in the consumer-facing contract
3. explicit naming of the affected consumer

## 7. Workflow Rule

Future specs that change route behavior must update:

1. [docs/contracts/feature_contract_registry.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_contract_registry.yaml)
2. [docs/NAUTILUS_FEATURE_CONTRACT_V1.md](/media/sam/1TB/UTXOracle/docs/NAUTILUS_FEATURE_CONTRACT_V1.md), if `nautilus_dev` is affected
3. [docs/contracts/feature_provenance_manifest.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_provenance_manifest.yaml), if dependency or failure semantics changed

Whale-specific schema note:

- the canonical whale query family now serves additive `whale_event.v1` fields
- entity enrichment is optional and documented in [docs/WHALE_ENTITY_FOUNDATION.md](/media/sam/1TB/UTXOracle/docs/WHALE_ENTITY_FOUNDATION.md)
