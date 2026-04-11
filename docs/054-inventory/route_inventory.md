# Route Inventory: Port 8011

This inventory lists every route family currently mounted on `:8011` by `api/apps/live.py`, cross-referenced with its current tier in `docs/contracts/feature_contract_registry.yaml`.

| Route Family | Mount Prefix | HTTP Methods | Source Module | Current Registry Tier |
|---|---|---|---|---|
| `/health` | `/health` (direct) | GET | `api/apps/live.py` | `tier_4_not_admitted` (main_operational_pages_surface) |
| `/api/v1/live/*` | `/api/v1` + `/live` | GET | `api/routes/live.py` | `tier_1_production` |
| `/api/v1/charts/*` | `/api/v1` + `/charts` | GET | `api/routes/charts.py` | `tier_1_production` |
| `/api/prices/*` | None (defined on routes) | GET | `api/routes/questdb.py` | `tier_1_production` |
| `/api/metrics/latest` | None (defined on routes) | GET | `api/routes/questdb.py` | `tier_1_production` |
| `/api/metrics/address-cohorts` | None (defined on routes) | GET | `api/routes/questdb.py` | `tier_1_production` |
| `/api/metrics/wallet-waves` | None (defined on routes) | GET | `api/routes/questdb.py` | `tier_1_production` |
| `/api/metrics/absorption-rates`| None (defined on routes) | GET | `api/routes/questdb.py` | `tier_1_production` |
| `/api/metrics/cost-basis` | None (defined on routes) | GET | `api/routes/questdb.py` | `tier_3_research` |
| `/api/research/tier-stats` | None (defined on routes) | GET | `api/routes/questdb.py` | `tier_3_research` |
| `/api/features/btc/*` | `/api/features/btc` | GET | `api/routes/features.py` | `tier_1_production` |
| `/api/signals/btc/*` | `/api/signals/btc` | GET | `api/routes/signals.py` | `tier_1_production` |
| `/api/entities/*` | `/api/entities` | GET | `api/routes/entities.py` | `tier_3_research` |
| `/api/whale/*` | `/api/whale` | GET | `api/mempool_whale_endpoints.py` | `tier_2_production_with_caveats` |
| `/api/meta/features` | None (defined on routes) | GET | `api/routes/meta.py` | Not listed |
| `/charts/{chart_id}` | `/charts` (direct) | GET | `api/apps/live.py` | Not listed |
