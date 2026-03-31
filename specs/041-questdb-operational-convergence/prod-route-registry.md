# PROD_ROUTE_REGISTRY

Initial production route registry for spec-041.

## Route Families

| Route Family | Current Served Source | Target Operational Source | Writer / Owner | Max Staleness | Empty / Stale Policy |
|---|---|---|---|---|---|
| `/health` | `live_snapshots` in QuestDB via live health summary | `live_snapshots` in QuestDB | `scripts.live.runtime` / live worker | 60s | `200 degraded` when live summary is stale or unavailable |
| `/api/v1/live/snapshot` | latest row in `live_snapshots` | latest row in `live_snapshots` | `scripts.live.runtime` / live worker | 60s operational target | `503` when no snapshot is available |
| `/api/v1/live/history` | recent window in `live_snapshots` | recent window in `live_snapshots` | `scripts.live.runtime` / live worker | 60s operational target | `200 []` when no rows exist in requested window |
| `/api/v1/live/comparison/latest` | latest row in `live_snapshots` projected to comparison view | latest row in `live_snapshots` projected to comparison view | `scripts.live.runtime` / live worker | 60s operational target | `503` when no snapshot is available |
| `/api/v1/live/ready` | latest row in `live_snapshots` + freshness check | latest row in `live_snapshots` + freshness check | `scripts.live.runtime` / live worker | hard 60s | `503` when no snapshot exists or latest row is stale |

## Route Admission Notes

- The production route boundary is correct on `8011`, and the retained live family is now QuestDB-backed.
- No DuckDB-backed route is admitted to `8011`.
- `/api/prices/*` is the first legacy family under parity review, using DuckDB `price_analysis` only as an offline baseline while dual-read logging is prepared on `/api/prices/historical`.
- Model, validation, whale, price, and metric routes remain outside the production boundary until they satisfy route admission and parity requirements.
