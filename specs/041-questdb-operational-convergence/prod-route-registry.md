# PROD_ROUTE_REGISTRY

Initial production route registry for spec-041.

## Route Families

| Route Family | Source Table / Query | Writer / Owner | Max Staleness | Empty / Stale Policy |
|---|---|---|---|---|
| `/health` | `live_snapshots` via live health summary | `scripts.live.runtime` / live worker | 60s | `200 degraded` when live summary is stale or unavailable |
| `/api/v1/live/snapshot` | `live_snapshots` latest row | `scripts.live.runtime` / live worker | 60s operational target | `503` when no snapshot is available |
| `/api/v1/live/history` | `live_snapshots` recent time window | `scripts.live.runtime` / live worker | 60s operational target | `200 []` when no rows exist in requested window |
| `/api/v1/live/comparison/latest` | `live_snapshots` latest row projected to comparison view | `scripts.live.runtime` / live worker | 60s operational target | `503` when no snapshot is available |
| `/api/v1/live/ready` | `live_snapshots` latest row + freshness check | `scripts.live.runtime` / live worker | hard 60s | `503` when no snapshot exists or latest row is stale |

## Route Admission Notes

- All current production routes are backed by the live QuestDB snapshot path.
- No DuckDB-backed route is admitted to `8011`.
- Model, validation, whale, price, and metric routes remain outside the production boundary until they satisfy route admission and parity requirements.
