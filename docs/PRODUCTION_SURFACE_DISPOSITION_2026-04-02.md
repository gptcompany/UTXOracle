# Production Surface Disposition Matrix

Date: 2026-04-02

Status: Concrete route-family disposition after `spec-041`, `M7`, and the metric source-of-truth freeze

Purpose:

- state plainly what `8001` still contains
- define what should move to `8011` next
- separate DuckDB analytical surfaces from QuestDB serving surfaces
- stop treating every existing route as implicit promotion backlog

Primary references:

- [docs/contracts/feature_contract_registry.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_contract_registry.yaml)
- [docs/contracts/feature_provenance_manifest.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_provenance_manifest.yaml)
- [docs/SCOPE_LOCK_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/SCOPE_LOCK_2026-04-02.md)
- [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)

## 1. Storage Roles

This repo is still intentionally hybrid:

- `QuestDB` is the serving and operational time-series store
- `DuckDB` is the local analytical and research store built around `utxo_lifecycle`, cohorts, and custom metric workflows

Practical rule:

- if a route should become part of the canonical consumer contract on `:8011`, it should converge toward a QuestDB-backed, operationally owned serving path
- if a route remains research-only or calculator-heavy, it may stay DuckDB-backed on `:8001`

## 2. `8001` Target Meaning

`8001` is not the final product boundary.

It should retain only:

- research surfaces
- operator and admin surfaces
- transition families not yet ready for `:8011`

It should not be treated as the place where the product keeps expanding indefinitely.

## 3. Promoted To `8011` (spec-050 + Wave 1) — COMPLETE 2026-04-02

These families are now natively served by the dedicated live app on `:8011`:

| Route family | Status | Backend | 8001 behavior |
|---|---|---|---|
| `/api/prices/*` | **PROMOTED** | `QuestDB price_analysis` | Migration hint header |
| `/api/metrics/latest` | **PROMOTED** | `QuestDB metrics` | Migration hint header |
| `/api/whale/{transactions,summary,transaction/{txid}}` | **PROMOTED** | `QuestDB mempool_predictions` | Migration hint header |
| `/api/metrics/address-cohorts` | **PROMOTED** | `QuestDB address_cohorts_daily` | Migration hint header |
| `/api/metrics/wallet-waves` | **PROMOTED** | `QuestDB wallet_waves_daily` | Migration hint header |
| `/api/metrics/absorption-rates` | **PROMOTED** | `QuestDB absorption_rates_daily` | Migration hint header |

Port `8011` is the canonical production host for this slice.
`8001` remains secondary for these routes to allow transition.

## 4. Materialize In QuestDB Before Any `8011` Move

These families have real analytical value, but they are still bound to DuckDB/request-time computation and should not move to `:8011` in current form:

| Route family | Current backend | Why not move yet | Concrete requirement |
|---|---|---|---|
| `/api/metrics/exchange-netflow*` | DuckDB + CSV | local state and freshness are not operationally owned enough | writer/backfill and QuestDB materialization |
| `/api/metrics/binary-cdd` | DuckDB | request-time analytical read from `utxo_lifecycle_full` | materialized series with owned refresh path |
| `/api/metrics/net-realized-pnl*` | DuckDB | depends on spent-history availability | QuestDB historical table plus backfill owner |
| `/api/metrics/pl-ratio*` | DuckDB | same spent-history dependency | QuestDB historical table plus backfill owner |
| `/api/metrics/sopr` | DuckDB | same spent-history dependency | QuestDB serving table plus freshness policy |
| `/api/metrics/nvt` | DuckDB + block metadata | depends on mutable request-time inputs | freeze reproducible serving inputs and materialize |
| `/api/metrics/volatility` | DuckDB daily prices | local price table serving path only | QuestDB price-volatility materialization if it becomes consumer-grade |
| `/api/metrics/wallet-waves/history` | QuestDB | snapshots are now materialized | consolidate history read-path in api.routes.questdb |

This is where the repo should keep analytical ambition without pretending the routes are already production-boundary ready.

## 5. Keep On `8001` As Research Or Operator Surfaces

These families are legitimate to keep, but they should stay explicitly outside the canonical consumer contract for now:

| Route family | Why it stays on `8001` |
|---|---|
| `/api/metrics/nupl` | `M7` kept it at `tier_3_research`; future admission still needs an explicit reopened decision |
| `/api/metrics/cost-basis` | same `M7` no-go; strongest future candidate, but still research-only today |
| `/api/v1/models*` | research/modeling surface, not part of the consumer API |
| `/api/v1/models/power-law*` | research-only model family |
| `/api/v1/validation/rbn/*` | operator/research validation surface with external quota dependence |
| `/api/exchange-addresses/stats` | operator metadata surface, not a downstream feature contract |
| `/api/metrics/{advanced,wasserstein*,cointime*,urpd,supply-profit-loss,sell-side-risk,cdd-vdd,revived-supply}` | analytical/research bucket, not yet a serving-grade contract family |
| `/{,health,metrics,whale,dashboard,monitor,power-law,power_law}` | operational pages, not part of the consumer API |

`8001` is allowed to keep these as long as they are clearly labeled research or operator-only and are not silently treated as production contract surfaces.

## 6. Delegate To `BRK` Or Deprecate

These areas should not reopen as default local productization work:

| Area | Disposition |
|---|---|
| overlapping shared macro metrics already exposed by `BRK` | delegate to `BRK` by default rather than opening new local productization |
| `reserve-risk` local route productization | blocked; `BRK`-first unless the source-of-truth manifest is explicitly reopened |
| future shared admitted signal for `realized_price_usd` or `liveliness` | consume from `BRK`, do not create duplicate local admitted routes by default |
| `/api/whale/{latest,historical,history}` | keep deprecated only as explicit `410 Gone` migration stubs |
| `/api/risk/pro*` | keep demoted or reimplement only with real inputs and real history |
| `/api/metrics/puell-multiple` | keep demoted or reimplement only with real miner-revenue history |

## 7. Concrete Repo Shape

The repo is concrete if we treat it as:

- `:8011` = canonical consumer contract
- `:8001` = research/operator/transition app
- `QuestDB` = serving plane
- `DuckDB` = analytical computation plane
- `BRK` = upstream breadth and validation plane

The next meaningful convergence moves are:

1. decide whether selective Wave 2 metrics (e.g. SOPR, Net Flow) should be materialized and promoted to `:8011`
2. unify whale and entity forensics (spec-047)
