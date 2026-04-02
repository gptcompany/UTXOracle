# Nautilus Feature Contract V1

Date: 2026-04-02

Status: Initial `v1` consumer contract for `nautilus_dev`, updated through `M6` selective Wave 2 productization

Contract registry source:

- [docs/FEATURE_CONTRACT_REGISTRY.md](/media/sam/1TB/UTXOracle/docs/FEATURE_CONTRACT_REGISTRY.md)
- [docs/contracts/feature_contract_registry.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_contract_registry.yaml)

## 1. Scope

This document freezes the first explicit `UTXOracle` feature contract intended for `nautilus_dev`.

If a route family is not listed in this document, it is not admitted as part of `v1`.

## 2. Canonical Host Policy

### Dedicated live host

Use `http://127.0.0.1:8011` for:

- `/health`
- `/api/v1/live/*`
- `/api/v1/charts/*`

`/api/v1/live/*` is served only by the dedicated live app. The main app `:8001` is not part of the live-plane contract.

### Main app host

Use `http://127.0.0.1:8001` for:

- `/api/prices/*`
- `/api/metrics/latest`
- admitted main-app analytics listed below
- canonical whale query routes

## 3. Tier 1 Production Slice

These surfaces are admitted for direct production consumption in `v1`.

| Surface ID | Route family | Why admitted | Freshness target | Empty/stale policy |
|------|------|------|------|------|
| `live_snapshot_surface` | `/api/v1/live/*` on `:8011` | strongest runtime-verified live surface | `<= 60s` | `503` when snapshot missing; stale after `60s`; `/ready` returns `503` when stale |
| `live_chart_surface` | `/api/v1/charts/*` on `:8011` | strongest runtime-verified chart surface | `<= 60s` | `503` when snapshot history unavailable; stale shown in chart metadata |
| `prices_surface` | `/api/prices/*` | canonical price comparison family for main app | newest `price_analysis` row | `404` when no rows; `500` on QuestDB failures |
| `metrics_latest_surface` | `/api/metrics/latest` | compact admitted bundle already exposed for downstream feature use | newest `metrics` row | `404` when no rows; `500` on QuestDB failures |

## 4. Tier 2 Production With Caveats

These surfaces are admitted only with the declared infrastructure and semantic caveats.

| Surface ID | Route family | Caveat |
|------|------|------|
| `whale_query_surface` | `/api/whale/{transactions,summary,transaction/{txid}}` | canonical whale query family is frozen with additive `whale_event.v1` fields; entity enrichment is best-effort and may be omitted while the base event remains valid |
| `exchange_netflow_surface` | `/api/metrics/exchange-netflow*` | requires populated DuckDB plus `exchange_addresses.csv` |
| `binary_cdd_surface` | `/api/metrics/binary-cdd` | requires populated DuckDB and sufficient lookback history |
| `net_realized_pnl_surface` | `/api/metrics/net-realized-pnl*` | requires populated spent UTXO history |
| `pl_ratio_surface` | `/api/metrics/pl-ratio*` | requires populated spent UTXO history |
| `sopr_surface` | `/api/metrics/sopr` | requires `utxo_lifecycle_full` and recent spent data |
| `nvt_surface` | `/api/metrics/nvt` | depends on `utxo_lifecycle_full`, `block_heights`, and a caller-supplied or default `current_price` |
| `volatility_surface` | `/api/metrics/volatility` | depends on populated `daily_prices` |
| `mining_pulse_surface` | `/api/metrics/mining-pulse` | hard dependency on Bitcoin Core RPC |
| `hash_ribbons_surface` | `/api/metrics/hash-ribbons` | hard dependency on external hashrate API |
| `mining_economics_surface` | `/api/metrics/mining-economics*` | mixed dependency family; history path hardcodes historical `pulse_zone` |

## 5. Explicitly Excluded From `v1`

These surfaces are intentionally not admitted.

| Surface ID | Route family | Reason |
|------|------|------|
| `pro_risk_surface` | `/api/risk/pro*` | runtime-demoted pending real component inputs and historical serving |
| `puell_multiple_surface` | `/api/metrics/puell-multiple` | runtime-demoted pending real 365-day miner revenue history |
| `power_law_surface` | `/api/v1/models/power-law*` | research model surface; handler is now deterministic, but it is still outside the first production bundle |
| `models_core_surface` | `/api/v1/models*` | research surface, not frozen for downstream production use |
| `rbn_validation_surface` | `/api/v1/validation/rbn/*` | useful for validation and ops, but not part of the first production feature bundle |
| `nupl_surface` | `/api/metrics/nupl` | implemented as a research route, but `pct_supply_in_profit` remains an explicitly estimated field and the surface is not admitted into `v1`; `M7` closed with no promotion |
| `cost_basis_surface` | `/api/metrics/cost-basis` | implemented as a research route, but not yet admitted into the first production bundle; `M7` closed with no promotion |
| `advanced_research_surface` | `/api/metrics/{advanced,wasserstein*,cointime*,urpd,supply-profit-loss,reserve-risk,sell-side-risk,cdd-vdd,revived-supply}` | analytical logic exists, API contract does not |
| `wallet_and_cohort_surface` | `/api/metrics/{address-cohorts,wallet-waves,absorption-rates}` | implemented as a research surface after Wave 1 productization, but still outside the first `v1` production bundle |
| `legacy_whale_placeholder_surface` | `/api/whale/{latest,historical,history}` | deprecated `410 Gone` compatibility stubs only; not part of the canonical whale contract |
| `wallet_waves_history_placeholder_surface` | `/api/metrics/wallet-waves/history` | history route remains unavailable until snapshot materialization exists |
| `main_operational_pages_surface` | `/{,health,metrics,whale,dashboard,monitor,power-law,power_law}` | operational UI surface, not a data contract |

## 6. Consumer Rules

`nautilus_dev` should assume:

- only the canonical host policy above is supported
- only `tier_1_production` and `tier_2_production_with_caveats` surfaces are in contract
- any excluded or research-only route may change without compatibility guarantees

`nautilus_dev` should not assume:

- that any non-canonical host or undocumented alias is supported
- that undocumented route families are stable enough for direct strategy use
- that placeholder or research-only routes will be preserved

## 7. Migration Notes For Future Versions

Future contract versions may:

- admit individual Wave 1 calculator routes only after an explicit contract decision beyond `v1`
- add entity foundation fields only after canonical whale routes and provenance rules are frozen
- keep whale entity enrichment additive; no future version should require `entity` to be present for base whale-event validity
- re-admit `PRO Risk` or `Puell Multiple` only after their hardcoded behavior is removed
- selectively admit `nupl` and `cost-basis` only after reopening the post-`M6` admission gate in [docs/FEATURE_SERVICE_ADMISSION_GATE_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ADMISSION_GATE_2026-04-02.md) and superseding the current no-promotion decision in [docs/FEATURE_SERVICE_M7_DECISION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_M7_DECISION_2026-04-02.md)
- no future contract should admit NUPL's estimated `pct_supply_in_profit` field without an explicit field-level declaration that the value is estimated
- keep `reserve-risk` excluded until placeholder/default internals are removed from the calculator itself
- admit `power_law_surface` only after an explicit contract decision and tier promotion

Any such change must update:

- [docs/contracts/feature_contract_registry.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_contract_registry.yaml)
- [docs/contracts/feature_provenance_manifest.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_provenance_manifest.yaml)
