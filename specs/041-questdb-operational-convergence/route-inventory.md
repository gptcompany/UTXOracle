# spec-041 Route Inventory

Verified against repo state on 2026-03-31.

## Production Surface for `8011`

The retained production route families are intentionally narrow:

| Route Family | Classification | Notes |
|---|---|---|
| `/health` | production | Live-first health summary for the production app |
| `/api/v1/live/snapshot` | production | Current live snapshot contract |
| `/api/v1/live/history` | production | Recent live snapshot history |
| `/api/v1/live/comparison/latest` | production | Current comparison-only projection |
| `/api/v1/live/ready` | production | Strict readiness gate for automation |

## Legacy / Research Surface

These route families remain outside the production app until QuestDB ownership and route admission are complete:

| Route Family | Classification | Reason |
|---|---|---|
| `/api/prices/*` | legacy candidate | First parity slice uses DuckDB `price_analysis` as offline baseline against QuestDB-backed `/api/prices/historical`; stays off `8011` until parity and ownership are explicit |
| `/api/metrics/*` | research/legacy | Mixed QuestDB, DuckDB, and placeholder behavior |
| `/api/whale/*` | research/legacy | Placeholder/partial implementation on REST side |
| `/api/v1/models/*` | research | Model endpoints not yet admitted to production |
| `/api/v1/validation/*` | research | Validation tooling, not production live contract |
| `/`, `/dashboard`, `/monitor`, `/whale`, `/power_law`, `/power-law` | legacy UI | UI/debug surface, not production API |

## Notes

- `api.main:app` remains the mixed legacy surface.
- `api.apps.live:app` is the canonical production-scoped runtime for `8011`.
- `api.apps.legacy:app` is an explicit legacy alias for `8001` while the full router split is still in progress.
- The first retained migration family under parity review is `/api/prices/*`, starting with `/api/prices/historical` dual-read logging behind an explicit opt-in flag.
- Runtime drift found earlier on 2026-03-31 was corrected: `/api/prices/*` now returns `404` on `8011`, and the live Docker app is actually running `api.apps.live:app`.
- The retained live family is now served directly from QuestDB `live_snapshots`; the remaining legacy families stay outside `8011` by route-admission decision, not by boundary drift.
