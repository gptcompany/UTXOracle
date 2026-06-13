# URPD Features Daily Surface

`urpd_features_daily` is the production serving surface for Nautilus Spec080 URPD scalar features. Nautilus should query this table with latest-at-or-before semantics and must not scan `utxo_lifecycle_full` at startup.

## Schema

Required fields:

| Field | Type | Notes |
| --- | --- | --- |
| `ts` | timestamp | Feature observation timestamp. |
| `availability_timestamp` | timestamp | Time the materializer produced the row. `created_at` is also written for legacy freshness checks. |
| `block_height` | long | Latest block at or before `ts`. |
| `current_price_usd` | double nullable | Latest daily BTC/USD price at or before `ts`. |
| `bucket_size_usd` | double | URPD bucket width persisted with every row. |
| `total_supply_btc` | double nullable | Priced point-in-time supply included in the URPD distribution. |
| `supply_below_price_pct` | double nullable | Supply with cost basis below current price. |
| `supply_above_price_pct` | double nullable | Supply with cost basis above current price. |
| `top_bucket_concentration` | double nullable | Largest single bucket share of priced supply. |
| `dominant_bucket_distance_pct` | double nullable | Dominant bucket midpoint distance from current price. |
| `distribution_entropy` | double nullable | Normalized Shannon entropy of bucket shares. |
| `confidence` | double | `0.85` healthy, `0.5` degraded but distribution available, `0.0` unavailable/empty. |
| `schema_version` | symbol | Current value: `urpd_features_daily.v1`. |

Provenance fields:

| Field | Type | Notes |
| --- | --- | --- |
| `source_health_json` | string | JSON health report with UTXO counts, missing creation-price counts, price source, and freshness. |
| `source_freshness_seconds` | double nullable | Age of the block timestamp relative to `ts`, when `block_heights` is available. |
| `created_at` | timestamp | Insert/materialization time. |

Missing metrics are emitted as `NULL`, not `0.0`. Check `source_health_json.status` before interpreting nullable fields.

## Cadence

Default cadence is daily at `00:20 UTC` via:

- `utxoracle-urpd-features.service`
- `utxoracle-urpd-features.timer`

Manual one-shot materialization:

```bash
uv run python -m scripts.metrics.materialize_urpd_features
```

Historical backfill:

```bash
uv run python -m scripts.metrics.materialize_urpd_features \
  --start-date 2025-01-01 \
  --end-date 2025-12-31
```

Recent rolling backfill:

```bash
uv run python -m scripts.metrics.materialize_urpd_features --backfill-days 90
```

Dry-run without QuestDB writes:

```bash
uv run python -m scripts.metrics.materialize_urpd_features --timestamp 2026-05-09T00:00:00Z --dry-run
```

## Consumer Queries

QuestDB latest-at-or-before:

```sql
SELECT *
FROM urpd_features_daily
WHERE ts <= '2026-05-09T12:00:00.000000Z'
ORDER BY ts DESC, block_height DESC, created_at DESC
LIMIT 1;
```

DuckDB sample against an exported or attached copy:

```sql
SELECT *
FROM urpd_features_daily
WHERE ts <= TIMESTAMP '2026-05-09 12:00:00+00'
ORDER BY ts DESC, block_height DESC, created_at DESC
LIMIT 1;
```
