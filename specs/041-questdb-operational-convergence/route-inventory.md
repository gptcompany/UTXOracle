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
| `/api/prices/*` | legacy | Historical mixed surface from `api.main` |
| `/api/metrics/*` | research/legacy | Mixed QuestDB, DuckDB, and placeholder behavior |
| `/api/whale/*` | research/legacy | Placeholder/partial implementation on REST side |
| `/api/v1/models/*` | research | Model endpoints not yet admitted to production |
| `/api/v1/validation/*` | research | Validation tooling, not production live contract |
| `/`, `/dashboard`, `/monitor`, `/whale`, `/power_law`, `/power-law` | legacy UI | UI/debug surface, not production API |

## Notes

- `api.main:app` remains the mixed legacy surface.
- `api.apps.live:app` is the canonical production-scoped runtime for `8011`.
- `api.apps.legacy:app` is an explicit legacy alias for `8001` while the full router split is still in progress.
