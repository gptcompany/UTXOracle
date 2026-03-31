# spec-041 Route Support Matrix

Verified against repo and host runtime on 2026-03-31.

## Production Boundary (`8011`)

| Route Family | Runtime on `8011` | Current Served Source | Target Operational Source | Admission Status |
|---|---|---|---|---|
| `/health` | `200 degraded` or `200 healthy` depending on source freshness | `live_snapshots` in QuestDB | `live_snapshots` in QuestDB | admitted |
| `/api/v1/live/snapshot` | `200` or `503` | `live_snapshots` in QuestDB | `live_snapshots` in QuestDB | admitted |
| `/api/v1/live/history` | `200` | `live_snapshots` in QuestDB | `live_snapshots` in QuestDB | admitted |
| `/api/v1/live/comparison/latest` | `200` or `503` | `live_snapshots` in QuestDB | `live_snapshots` in QuestDB | admitted |
| `/api/v1/live/ready` | `200` or `503` | `live_snapshots` in QuestDB | `live_snapshots` in QuestDB | admitted |

## Legacy Candidates (Not Admitted To `8011`)

| Route Family | Runtime on `8011` | Baseline / Ownership State | Admission Status |
|---|---|---|---|
| `/api/prices/*` | `404` | first parity slice exists for `/api/prices/historical`; DuckDB `price_analysis` used only as offline baseline and dual-read reference | blocked pending ownership and QuestDB route implementation |
| `/api/metrics/*` | `404` | mixed QuestDB, DuckDB, and placeholder behavior on legacy surface | blocked |
| `/api/whale/*` | `404` | incomplete REST-side ownership and placeholder risk | blocked |
| `/api/v1/models/*` | `404` | research-only | blocked |
| `/api/v1/validation/*` | `404` | validation-only | blocked |

## Closure Note

The route boundary is correct on `8011`: unsupported route families are no longer published there.
The route boundary is correct on `8011`, and the retained live family now reads directly from QuestDB.
