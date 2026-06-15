# Research: entity_flows_daily QuestDB Producer Pilot

**Date**: 2026-06-15
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)

## Scope

This document consolidates the six decisions the plan depends on. Code discovery (the plan freeze prerequisite) is captured in the relevant sections below; the cast table itself lives in [data-model.md](./data-model.md).

---

## R1 — Env var format and parsing rules (FR-005)

**Decision**: A single environment variable `SPEC063_QUESTDB_WRITE`. Parsed as OFF when its value (after `.strip().lower()`) is exactly one of the strings `0`, `false`, `no`. Any other value, **including unset**, evaluates to ON.

**Rationale**:
- Matches Clarify Q1 verbatim.
- Mirrors the env-var ergonomics spec-062 already established for `DISCORD_WEBHOOK_URL` (operator-controllable from systemd `EnvironmentFile`).
- "Unset = ON" is the safest default for a pilot: operators must take an explicit action (set the env var) to disable the new QuestDB write half. The legacy DuckDB path is never disturbed by this toggle.
- Restricting OFF to three specific tokens (`0`, `false`, `no`) prevents typos like `False` or `nope` from silently leaving the producer in ON state without the operator realising.

**Alternatives considered**:
- *CLI flag `--no-questdb-write`* — rejected. The producer's only visible CLI surface is `aggregate_flows()` invoked from `__main__`; adding a flag would change the invocation contract and risk breaking any future scheduler that doesn't know about it.
- *Default OFF (opt-in deploy)* — rejected. The whole point of spec-063 is to start populating the QuestDB consumer-facing table. Default OFF would leave the stream MISSING until a separate operator action enabled it, defeating the unblock.
- *Module constant in `api/questdb_repository.py`* — rejected. Cannot be flipped without restarting the Python process, and would break the spec-062 convention of operator-controllable env vars.

---

## R2 — Webhook aggregation pattern (FR-007)

**Decision**: Exactly one POST to `DISCORD_WEBHOOK_URL` per `aggregate_flows()` run that produced ≥ 1 QuestDB write failure. The payload is a single-line summary:

```json
{
  "content": ":rotating_light: entity_flows_daily QuestDB write failed for {date}: {failed_count} rows failed ({ExceptionClass})"
}
```

Where:
- `{date}` is the ISO date string (`YYYY-MM-DD`) of the target window. If the run produced rows for multiple dates and all of them had failures, use a range (`YYYY-MM-DD..YYYY-MM-DD`).
- `{failed_count}` is the count of distinct `(entity_id, date)` pairs whose QuestDB save raised.
- `{ExceptionClass}` is the qualified class name of the most common failure exception (e.g. `psycopg.OperationalError`). If multiple exception classes were observed, report `MultipleFailureClasses` and the per-class breakdown lives in the structured ERROR logs.

**Rationale**:
- Matches Clarify Q2 verbatim and spec-062 FR-012's one-message-per-run model.
- Per-row Discord notifications would flood when QuestDB is wholly down (could be thousands of rows in a backfill).
- The structured ERROR log (FR-003) is the authoritative per-row diagnostic source. The webhook is a paging signal.
- Reuses the `_post_discord_failure` helper from spec-062 — no new helper to maintain.

**Alternatives considered**:
- *Per-row webhook* — rejected per flood risk above.
- *Threshold-based (only POST if failed_rows ≥ 1 % of total)* — rejected. Adds parameter that operators would have to tune. spec.md FR-007 is unambiguous: any failure pages.
- *No webhook* — rejected. SC-005 requires operator-visible failure signal; without webhook the operator must poll `/v1/streams/health`.

---

## R3 — Cast strategy (FR-010)

**Decision**: Each DuckDB column maps to its QuestDB counterpart via the per-column cast table in [data-model.md](./data-model.md). Discovery confirmed all six columns are lossless. No `decisions.md` escalation needed for type loss.

**Rationale**:
- Matches Clarify Q3 verbatim.
- Discovery findings (recorded in plan.md "Data Model" section):
  - `entity_id VARCHAR → SYMBOL INDEX` is lossless: QuestDB SYMBOL is an interned string with full identity preservation.
  - `date DATE → TIMESTAMP` is lossless: DATE has midnight-UTC precision; TIMESTAMP can encode any DATE without loss.
  - `inflow_btc / outflow_btc / netflow_btc DOUBLE → DOUBLE` is identity.
  - `is_exchange BOOLEAN → BOOLEAN` is identity.
- A new `ts TIMESTAMP` column exists in the QuestDB DDL but not in DuckDB. It's the designated timestamp for partition. Populated at write time with `datetime.utcnow()`.

**Alternatives considered**:
- *Fail-fast on any type mismatch* — rejected per Clarify Q3 reasoning (would block the pilot prematurely).
- *Runtime coercion with WARNING per mismatched row* — rejected: would hide drift from reviewers and produce noisy logs without surfacing the type issue in code review.
- *Verbatim DuckDB types in QuestDB (no SYMBOL, use VARCHAR)* — rejected: VARCHAR has no index on QuestDB by default and would inflate disk for an entity_id column whose cardinality is much smaller than its row count (perfect SYMBOL use case).

---

## R4 — Save method placement (`api/questdb_repository.save_entity_flows_daily`)

**Decision**: A new SYNCHRONOUS module-level function `save_entity_flows_daily(...)` lives in `api/questdb_repository.py`, alongside the existing sync writers (`save_mvrv_daily`, `save_nupl_daily`, `save_realized_cap_daily`). It uses `_open_pg_sync()` under the hood — same connection pattern as spec-061 Phase 1.5-v2 writers.

**Rationale**:
- `flow_aggregator.py::aggregate_flows()` is sync (no async loop). A sync save method matches the caller's context.
- The existing async `get_entity_flows()` (at `api/questdb_repository.py:1861`) is for read traffic served by the FastAPI endpoint; it's a different concern and does not preclude adding a sync writer.
- Placement in the repository module preserves the spec-061/062 convention of "one stream = one `save_<stream>_daily` symbol" — discoverable by grep, testable by patching at a single import path.

**Alternatives considered**:
- *Producer-local helper inside `flow_aggregator.py`* — rejected. Splits the QuestDB write surface across two modules; would require duplicating connection management.
- *Async save method using `asyncpg`* — rejected. Forces the producer to spin up an event loop for a single batch write. Adds complexity for no measurable benefit at the spec-063 batch size.
- *Bulk `executemany` instead of per-row `execute`* — considered. Rejected for the pilot to keep per-row error isolation (FR-002, FR-003). A future spec can revisit if measured wall-clock exceeds the 10 s ceiling.

---

## R5 — Write transport: psycopg PG-wire vs ILP

**Decision**: psycopg sync `INSERT ... ON CONFLICT ... DO UPDATE` via `_open_pg_sync()`. ILP rejected.

**Rationale**:
- spec-061 Phase 1.5-v2 already uses psycopg sync for `block_heights` and `daily_prices`. spec-062 reader migration reuses the same import. Consistency.
- ILP is optimised for high-throughput append-only ingestion (millions of rows/s). spec-063's per-run batch is typically ≤ 1 000 rows; ILP's batching benefits are wasted at this scale and would force a flush-and-confirm dance that complicates per-row error reporting.
- The per-row error model (FR-002, FR-003: each save isolated, each failure logged) maps directly to psycopg's per-`cur.execute` semantics. ILP's "Sender.row()" calls don't fail until `flush()`, making per-row attribution harder.
- DEDUP UPSERT KEYS handles both transport models, so idempotency is not a discriminator.

**Alternatives considered**:
- *ILP Sender per row + flush per save* — rejected: complicates error attribution.
- *ILP Sender per batch with bulk flush* — rejected: loses per-row error model.
- *Async asyncpg COPY* — rejected: async dependency injection into sync producer.

---

## R6 — Batch size and back-pressure

**Decision**: Read all rows produced by the DuckDB `INSERT OR REPLACE` aggregation into memory via `SELECT * FROM entity_flows_daily WHERE date = <run_date>`. Iterate Python-side and call `save_entity_flows_daily(...)` per row. No streaming, no chunking, no back-pressure mechanism.

**Rationale**:
- Discovery: `aggregate_flows()` is a single-run batch operation. Cardinality of distinct `(entity_id, date)` pairs is bounded by the entity registry size — empirically << 10 000 rows per run today.
- Memory envelope: 10 000 rows × 6 columns × ~ 64 B/value ≈ 4 MB. Trivially in-memory.
- Streaming would add complexity (cursor management, partial-state error handling) for a problem we don't have.
- Back-pressure (slowing reads if writes lag) doesn't apply: the read source is local DuckDB; the write target is local QuestDB. Both are on the same host, no network bottleneck.

**Alternatives considered**:
- *Server-side cursor with chunked fetch* — rejected: complexity without benefit at current scale.
- *Pandas DataFrame intermediate* — rejected: adds a heavy dependency (pandas) for a 4 MB workload.

**Reopening trigger**: if per-run cardinality crosses 100 000 rows, revisit. Likely solution at that point is bulk `executemany` per chunk, not streaming.
