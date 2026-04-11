# Route Inventory: Port 8011

This inventory lists every route family currently mounted on `:8011` by `api/apps/live.py`, cross-referenced with its current tier in `docs/contracts/feature_contract_registry.yaml`.

| Route Family | Mount Prefix | HTTP Methods | Source Module | Current Registry Tier |
|---|---|---|---|---|
| `/health` | `/health` (direct) | GET | `api/apps/live.py` | `tier_1_execution` (`live_health_surface`) |
| `/docs` | FastAPI generated docs route | GET | `api/apps/live.py` (`docs_url="/docs"`) | `tier_2_operator` (`fastapi_docs_surface`) |
| `/redoc` | FastAPI generated docs route | GET | `api/apps/live.py` (`redoc_url="/redoc"`) | `tier_2_operator` (`fastapi_docs_surface`) |
| `/openapi.json` | FastAPI generated OpenAPI route | GET | `api/apps/live.py` (default `openapi_url`) | `tier_2_operator` (`fastapi_docs_surface`) |
| `/api/v1/live/*` | `/api/v1` + `/live` | GET | `api/routes/live.py` | `tier_1_execution` (`live_snapshot_surface`) |
| `/api/v1/charts/*` | `/api/v1` + `/charts` | GET | `api/routes/charts.py` | `tier_2_operator` (`live_chart_surface`) |
| `/api/prices/*` | None (defined on routes) | GET | `api/routes/questdb.py` | `tier_2_operator` (`prices_surface`) |
| `/api/metrics/latest` | None (defined on routes) | GET | `api/routes/questdb.py` | `tier_2_operator` (`metrics_latest_surface`) |
| `/api/metrics/address-cohorts` | None (defined on routes) | GET | `api/routes/questdb.py` | `tier_2_operator` (`wallet_and_cohort_surface`) |
| `/api/metrics/wallet-waves` | None (defined on routes) | GET | `api/routes/questdb.py` | `tier_2_operator` (`wallet_and_cohort_surface`) |
| `/api/metrics/absorption-rates` | None (defined on routes) | GET | `api/routes/questdb.py` | `tier_2_operator` (`wallet_and_cohort_surface`) |
| `/api/metrics/cost-basis` | None (defined on routes) | GET | `api/routes/questdb.py` | `tier_2_operator` (`cost_basis_surface`; registry canonical host `:8001`) |
| `/api/research/tier-stats` | None (defined on routes) | GET | `api/routes/questdb.py` | `tier_3_research` (`research_operations_surface`) |
| `/api/features/btc/*` | `/api/features/btc` | GET | `api/routes/features.py` | `tier_1_execution` (`btc_feature_bundles_surface`) |
| `/api/signals/btc/*` | `/api/signals/btc` | GET | `api/routes/signals.py` | `tier_1_execution` (`btc_signal_snapshot_surface`) |
| `/api/entities/*` | `/api/entities` | GET | `api/routes/entities.py` | `tier_2_operator` (`entity_intelligence_surface`) |
| `/api/whale/*` | `/api/whale` | GET | `api/mempool_whale_endpoints.py` | `tier_2_operator` (`whale_query_surface`) |
| `/api/meta/features` | None (defined on routes) | GET | `api/routes/meta.py` | `tier_2_operator` (`feature_meta_surface`) |
| `/charts/{chart_id}` | `/charts` (direct) | GET | `api/apps/live.py` | `tier_2_operator` (`live_chart_page_surface`) |
