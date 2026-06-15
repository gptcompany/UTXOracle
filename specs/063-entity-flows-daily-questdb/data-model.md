# Data Model: entity_flows_daily QuestDB Producer Pilot

**Date**: 2026-06-15
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)

## Source surface (DuckDB)

`scripts/live/init_flow_artifacts.py:46` defines:

```sql
CREATE TABLE IF NOT EXISTS entity_flows_daily (
    entity_id VARCHAR,
    date DATE,
    inflow_btc DOUBLE,
    outflow_btc DOUBLE,
    netflow_btc DOUBLE,
    is_exchange BOOLEAN,
    PRIMARY KEY (entity_id, date)
);
```

The producer `scripts/live/flow_aggregator.py::aggregate_flows()` writes this table via a single `INSERT OR REPLACE INTO entity_flows_daily SELECT ... FROM entity_transfer_edges GROUP BY entity_id, date` at line 121. Spec-063 does NOT modify this DuckDB DDL or write path.

## Target surface (QuestDB) — current state

`api/questdb_repository.py:572` already defines:

```sql
CREATE TABLE IF NOT EXISTS entity_flows_daily (
    entity_id SYMBOL INDEX,
    date TIMESTAMP,
    inflow_btc DOUBLE,
    outflow_btc DOUBLE,
    netflow_btc DOUBLE,
    is_exchange BOOLEAN,
    ts TIMESTAMP
) timestamp(ts) PARTITION BY DAY;
```

**Missing for spec-063**: WAL + DEDUP UPSERT KEYS configuration.

## Target surface (QuestDB) — post spec-063

Same schema, plus the idempotent ALTER TABLE block added inside `create_tables_if_not_exist` after the CREATE TABLE call:

```sql
ALTER TABLE entity_flows_daily SET TYPE WAL;
ALTER TABLE entity_flows_daily DEDUP ENABLE UPSERT KEYS(date, entity_id);
```

Both wrapped in `try/except` for idempotency on tables that already have WAL or DEDUP enabled (matches spec-061 Phase 1.5-v2 pattern).

## Column-by-column cast table

| Column | DuckDB type | QuestDB type | Cast applied at write time | Lossless? | Notes |
|---|---|---|---|---|---|
| `entity_id` | `VARCHAR` | `SYMBOL INDEX` | string identity (psycopg coerces Python `str` → SYMBOL) | **Yes** | QuestDB SYMBOL is an interned string; full round-trip identity. INDEX makes lookups by entity_id O(1). |
| `date` | `DATE` | `TIMESTAMP` | `datetime.combine(date_value, datetime.min.time(), tzinfo=UTC)` | **Yes** | DATE has midnight-UTC precision; TIMESTAMP encodes it exactly. Round-trip: `cast(ts as date) == original_date`. |
| `inflow_btc` | `DOUBLE` | `DOUBLE` | identity | **Yes** | IEEE 754 binary64 on both sides. |
| `outflow_btc` | `DOUBLE` | `DOUBLE` | identity | **Yes** | IEEE 754 binary64 on both sides. |
| `netflow_btc` | `DOUBLE` | `DOUBLE` | identity | **Yes** | IEEE 754 binary64 on both sides. |
| `is_exchange` | `BOOLEAN` | `BOOLEAN` | identity | **Yes** | Both engines store as 1-byte boolean. |
| `ts` (QuestDB only — designated timestamp) | — | `TIMESTAMP` | `datetime.utcnow()` at the moment of the `cur.execute(INSERT...)` call | N/A (write-only field, has no DuckDB twin) | Used by QuestDB for daily partitioning. The `date` column remains the consumer-facing day key; `ts` is implementation metadata. |

**Discovery verdict (signed off here, fulfils plan freeze checklist item 3)**:

All six DuckDB→QuestDB column casts are lossless under the round-trip definition declared in Clarify Q3 (`Q3 round-trip QuestDB → DuckDB recovers the original value at the documented precision`). `decisions.md` records this verdict explicitly and triggers no `materially lossy cast` entry.

## Identity & idempotency

| Property | DuckDB | QuestDB |
|---|---|---|
| Primary identity | `(entity_id, date)` (PRIMARY KEY) | `(entity_id, date)` (DEDUP UPSERT KEYS — added by spec-063) |
| Idempotency on re-write | `INSERT OR REPLACE` | `DEDUP UPSERT KEYS(date, entity_id)` |
| Concurrent invocation | Last-writer-wins (DuckDB INSERT OR REPLACE) | Last-writer-wins (QuestDB DEDUP UPSERT KEYS) |
| Cross-store reconciliation | Per-row identity matches by `(entity_id, date)` | Same — re-run of `aggregate_flows()` recovers any missed QuestDB row by upserting from DuckDB |

The two stores share the same identity tuple. A re-run of `aggregate_flows()` after a partial QuestDB failure reconciles: DuckDB upserts to same values (no change), QuestDB upserts the previously-failed rows.

## State transitions

`aggregate_flows()` is a single batch run. There is no per-row state machine. The only persisted state is the row itself in both stores. Cross-run state lives in DuckDB only (the source `entity_transfer_edges` table that spec-063 does NOT touch).

## Out-of-table contract

Three downstream consumers of QuestDB `entity_flows_daily` are documented in `docs/contracts/stream_registry.yaml` line 94:

| Property | Value | Source |
|---|---|---|
| `name` | `entity_flows_daily` | stream_registry.yaml |
| `freshness_strategy` | `max_ts` | stream_registry.yaml |
| `timestamp_column` | `ts` | stream_registry.yaml |
| `sla_seconds` | `129600` (36 h) | stream_registry.yaml |
| `pinned_columns` | (see stream_registry.yaml for the canonical list) | stream_registry.yaml |

spec-063 does NOT modify this registry entry. The freshness strategy (`max_ts` on `ts`) is already correct: as soon as a row is written, `max(ts)` advances and the stream becomes OK in `/v1/streams/health`.

## What spec-063 does NOT model

- `entity_movement_events` (DuckDB-only, out of scope)
- `entity_transfer_edges` (DuckDB-only, source of the aggregation, out of scope)
- `entity_balance_snapshots_daily` (DuckDB; QuestDB DDL exists but separate Phase 2 spec will own it)
- `entity_counterparty_edges_daily` (DuckDB; QuestDB DDL exists but separate Phase 2 spec will own it)

Per `decisions.md` D1 (pilot scope guard), spec-063 ships dual-write for `entity_flows_daily` only. The four sibling tables remain DuckDB-only until follow-up Phase 2 specs land.
