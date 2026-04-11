# Drift Report: Documentation vs. Runtime on Port 8011

This report captures the mismatches between stated documentation (README, service profiles, contract registry) and actual runtime exposure on the production port `8011`.

| Document | Claim | Actual Runtime Reality | Drift Category |
|---|---|---|---|
| `README.md` (line 85) | "`8011` exposes only `/health` and `/api/v1/live/*`" | `api/apps/live.py` mounts `charts`, `questdb` (metrics, prices), `features`, `signals`, `entities`, `whale`, and `meta` routers. | Boundary Exposure |
| `docs/contracts/feature_contract_registry.yaml` | Uses generic `tier_1_production` for both core execution (`live`) and non-execution routes (`charts`, `prices`). | No distinction in the registry between paths required by `NT` (execution) and operator-facing paths. | Tier Granularity |
| `docs/contracts/feature_contract_registry.yaml` | Some route families (e.g. `/api/meta/features`, `/charts/{chart_id}`) are exposed on `:8011` but missing entirely from the registry. | `api/apps/live.py` mounts these explicitly or via imported routers. | Registry Incompleteness |
