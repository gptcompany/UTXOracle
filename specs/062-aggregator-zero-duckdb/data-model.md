# Data Model: Aggregator Zero-DuckDB Read Path

**Date**: 2026-06-05
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)

## Read surface (per helper)

Each helper acquires its own connection via `_open_pg_sync()` (QuestDB branch) or the passed-in `conn` (DuckDB branch). No shared transaction across helpers — daily-row atomicity is enforced at the write side, not the read side.

### `calculate_daily_realized_cap(conn, as_of_block, *, questdb_reads)`

| Branch | Table | Predicate | Aggregation |
|---|---|---|---|
| QuestDB | `utxo_lifecycle` | `creation_block <= %s` | `SUM(CASE WHEN is_spent = FALSE OR spent_block > %s THEN realized_value_usd ELSE 0 END)` |
| DuckDB | `utxo_lifecycle_full` | `creation_block <= ?` | identical |

Returns: `float` (USD).

### `calculate_daily_sopr(conn, start_block, end_block, *, questdb_reads)`

| Branch | Table(s) | Predicate | Aggregation |
|---|---|---|---|
| QuestDB primary | `utxo_lifecycle` | `is_spent = TRUE AND spent_block BETWEEN %s AND %s AND realized_value_usd > 0 AND spent_price_usd IS NOT NULL` | `SUM(btc_value * spent_price_usd) / SUM(realized_value_usd)` |
| QuestDB fallback | `utxo_lifecycle u JOIN block_heights bh ON u.spent_block = bh.height JOIN daily_prices dp ON cast(bh.ts as date) = cast(dp.date as date)` | `u.is_spent = TRUE AND u.spent_block BETWEEN %s AND %s AND u.realized_value_usd > 0` | `SUM(u.btc_value * dp.price_usd) / SUM(u.realized_value_usd)` |
| DuckDB primary | `utxo_lifecycle_full` | identical with `?` placeholders | identical |
| DuckDB fallback | `utxo_lifecycle_full u JOIN block_heights bh JOIN daily_prices dp ON DATE(EPOCH_MS(CAST(bh.timestamp AS BIGINT) * 1000)) = dp.date` | identical | identical |

Returns: `Optional[float]`. `None` when no spent UTXOs in range or both branches yield zero denominator.

### `calculate_cointime_daily(conn, as_of_block, *, questdb_reads)`

| Branch | Table | Two queries |
|---|---|---|
| QuestDB | `utxo_lifecycle` | (1) `SUM(btc_value * COALESCE(age_blocks, spent_block - creation_block)) WHERE is_spent = TRUE AND spent_block <= %s AND creation_block > 0` → `coinblocks_destroyed`. (2) `SUM(btc_value * (%s - creation_block)) WHERE creation_block <= %s AND creation_block > 0` → `coinblocks_created`. |
| DuckDB | `utxo_lifecycle_full` | identical with `?` |

Returns: `dict` with `liveliness`, `vaultedness`, `activity_to_vaultedness_ratio`, `coinblocks_destroyed`, `coinblocks_created` (all `Optional[float]`).

### Inline supply query in `calculate_daily_metrics`

| Branch | Table | Predicate | Aggregation |
|---|---|---|---|
| QuestDB | `utxo_lifecycle` | `(is_spent = FALSE OR spent_block > %s) AND creation_block <= %s` | `SUM(btc_value)` |
| DuckDB | `utxo_lifecycle_full` | identical with `?` | identical |

Returns: `float` (BTC).

### `mvrv_variants.get_market_cap_history_all_time(conn, max_block_height, *, questdb_reads)`

| Branch | Table | Predicate | Projection |
|---|---|---|---|
| QuestDB | `utxo_snapshots` | `block_height <= %s` (optional) | `market_cap_usd ORDER BY block_height DESC` |
| DuckDB | `utxo_snapshots` (legacy) | `block_height <= ?` (optional) | identical |

Returns: `list[float]`. Empty list when target table is empty (current QuestDB state during transition).

## Write surface

Unchanged from spec-061. The aggregator writes via:
- `api.questdb_repository.save_mvrv_daily(ts, mvrv, mvrv_z, mvrv_z_rbn, market_cap, realized_cap)`
- `api.questdb_repository.save_nupl_daily(ts, nupl, market_cap, realized_cap)`
- `api.questdb_repository.save_realized_cap_daily(ts, realized_cap)`

Each uses QuestDB ILP behind the scenes; idempotency is via `DEDUP UPSERT KEYS(ts)` on the three target tables (spec-061 Phase 1.5-v2 DDL).

## Entity reference

### `utxo_lifecycle` (QuestDB)

The QuestDB SSOT for per-UTXO lifecycle data. Established by spec-061 Phase 1. Row count at 2026-06-05: ~174.2 M.

| Column | Type | Used by spec-062? |
|---|---|---|
| `outpoint` | STRING | no |
| `txid` | STRING | no |
| `vout_index` | LONG | no |
| `creation_block` | LONG | yes (all four lifecycle helpers) |
| `ts` | TIMESTAMP | designated timestamp |
| `creation_price_usd` | DOUBLE | no |
| `btc_value` | DOUBLE | yes (sopr, cointime, supply) |
| `realized_value_usd` | DOUBLE | yes (realized_cap, sopr) |
| `spent_block` | LONG | yes (realized_cap, sopr, cointime, supply) |
| `spent_timestamp` | TIMESTAMP | no |
| `spent_price_usd` | DOUBLE | yes (sopr primary branch) |
| `spending_txid` | STRING | no |
| `age_blocks` | LONG | yes (cointime, with COALESCE fallback) |
| `age_days` | LONG | no |
| `cohort` | SYMBOL | no |
| `sub_cohort` | SYMBOL | no |
| `sopr` | DOUBLE | no (pre-computed but we sum at the daily level) |
| `is_coinbase` | BOOLEAN | no |
| `is_spent` | BOOLEAN | yes (all four lifecycle helpers) |
| `price_source` | SYMBOL | no |

### `utxo_snapshots` (QuestDB)

The QuestDB SSOT for per-block snapshot rollups. Schema established by spec-061 Phase 1.5-v2 DDL; row count at 2026-06-05: 0. Phase 2 will populate it.

| Column | Type | Used by spec-062? |
|---|---|---|
| `block_height` | (LONG) | yes (mvrv_variants predicate) |
| `ts` | TIMESTAMP | designated timestamp |
| `total_supply_btc` | DOUBLE | no |
| `sth_supply_btc` | DOUBLE | no |
| `lth_supply_btc` | DOUBLE | no |
| `realized_cap_usd` | DOUBLE | no |
| `market_cap_usd` | DOUBLE | yes (mvrv_variants projection) |
| `mvrv` | DOUBLE | no |
| `nupl` | DOUBLE | no |
| `hodl_waves_json` | STRING | no |

### `block_heights` (QuestDB)

Established by spec-061 Phase 1.5-v2. Used by spec-062 only inside the SOPR fallback JOIN.

| Column | Type |
|---|---|
| `height` | LONG |
| `ts` | TIMESTAMP (designated) |
| `fetched_at` | TIMESTAMP |

### `daily_prices` (QuestDB)

Established by spec-061 Phase 1.5-v2. Used by spec-062 only inside the SOPR fallback JOIN.

| Column | Type |
|---|---|
| `date` | TIMESTAMP (designated) |
| `price_usd` | DOUBLE |
| `source` | SYMBOL |
| `fetched_at` | TIMESTAMP |

## Identity & idempotency

| Table | Primary identity | Idempotency mechanism |
|---|---|---|
| `utxo_lifecycle` | `outpoint` (functional key) | producer-side dedup via spec-061 Phase 1 backfill scripts |
| `utxo_snapshots` | `block_height` | producer-side (Phase 2) |
| `block_heights` | `(ts, height)` | `DEDUP UPSERT KEYS(ts, height)` |
| `daily_prices` | `date` | `DEDUP UPSERT KEYS(date)` |
| `mvrv_daily` / `nupl_daily` / `realized_cap_daily` | `ts` | `DEDUP UPSERT KEYS(ts)` |

The daily-table DEDUP is what makes per-date concurrency a no-op (FR-013, plan R5).

## State transitions

The aggregator is stateless between runs. There is no per-run state machine. The only persisted state is the daily rows themselves and (transitively) the `block_heights` / `daily_prices` source-freshness rows owned by spec-061 Phase 1.5-v2 timers.
