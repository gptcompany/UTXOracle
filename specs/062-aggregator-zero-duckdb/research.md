# Research: Aggregator Zero-DuckDB Read Path

**Date**: 2026-06-05
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)

## Scope

This is a retroactive research note. The implementation has already shipped in commit `6f27cbb`. This document captures the decisions made during that work so the same questions don't get re-asked when applying the strangler-fig pattern to the seven Phase 2 producers.

## R1 — QuestDB vs DuckDB SQL portability

**Decision**: Treat QuestDB SQL as PostgreSQL-compatible with a small list of known incompatibilities. Translate each per-helper; do not build a query-translation layer.

**Rationale**: The five migrated helpers use a small set of SQL features. A query translator would be ~300 LoC of generic infrastructure to save ~30 LoC of per-helper translation, violating Constitution Principle I (no premature abstraction until 3+ use cases exist). After spec-062 we have one such use case (this spec); after Phase 2 we may have four to seven. Re-evaluate at that point.

**Known incompatibilities encountered**:

| Construct | DuckDB | QuestDB | Notes |
|---|---|---|---|
| Parameter placeholder | `?` | `%s` (psycopg2) | Driver-level, not engine-level — switching driver could change this again. |
| Date from epoch seconds | `DATE(EPOCH_MS(CAST(ts AS BIGINT) * 1000))` | `cast(ts as date)` | QuestDB stores `ts` as `TIMESTAMP` natively. |
| Boolean literal | `= TRUE` / `= FALSE` | `= TRUE` / `= FALSE` | Compatible. |
| `BETWEEN` | works | works | Compatible. |
| `COALESCE` | works | works | Compatible. |
| Table-qualified aliases | `u.btc_value` | `u.btc_value` | Compatible. |
| Cross-table JOIN with date cast | Required EPOCH_MS gymnastics | `JOIN ... ON cast(bh.ts as date) = cast(dp.date as date)` | The QuestDB form is the readable one. |

**Alternatives considered**:
- *Generic SQL translator (SQLGlot or similar)*: rejected. Adds a dependency, adds a translation layer, and the per-helper SQL is small enough that hand-translating is clearer than maintaining an abstraction.
- *Use psycopg2 against DuckDB too (DuckDB has a PG-wire endpoint)*: rejected. DuckDB PG-wire is experimental; switching the legacy branch off `duckdb.execute` would re-litigate every existing test. Out of scope.

## R2 — Where to obtain the QuestDB connection

**Decision**: Reuse `api.questdb_repository._open_pg_sync`. Import directly at module top-level in `calculate_daily_metrics.py`; lazy-import inside the function in `mvrv_variants.py` to avoid an import cycle with `api/`.

**Rationale**: `_open_pg_sync` already encapsulates host/port/credentials via env vars (`QUESTDB_PG_HOST`, `QUESTDB_PG_PORT`, `QUESTDB_PG_USER`, `QUESTDB_PG_PASSWORD`, `QUESTDB_PG_DB`). It is the same entrypoint that spec-061 Phase 1.5-v2 writers use. Reusing it keeps the connection contract single-sourced.

**Alternatives considered**:
- *Build a per-script connection helper*: rejected. Duplicates env handling and connection-pool semantics. Drift risk.
- *Async `asyncpg` path*: rejected. The aggregator is a synchronous CLI script driven by systemd. Forcing async would require an event loop just to run sync queries. No measurable benefit.

## R3 — Handling the empty `utxo_snapshots` table

**Decision**: Report `mvrv_z_rbn = None` when the QuestDB `utxo_snapshots` table has fewer than 30 rows. Do NOT fall back to the DuckDB `utxo_snapshots` table. Do NOT substitute a derived value.

**Rationale**: spec FR-005 and SC-006 require transparent absence. A silent fallback to DuckDB hides the SPOF the spec was created to eliminate (FR-006). A derived surrogate silently changes the contract for nautilus_dev consumers and would have to be reverted when Phase 2 ships the real producer.

**Alternatives considered**:
- *Fall back to DuckDB when QuestDB empty*: rejected per FR-006.
- *Compute mvrv_z_rbn from `realized_cap` history alone (no snapshots needed)*: rejected. Would change the metric definition. Out of scope for this spec.
- *Backfill `utxo_snapshots` synchronously from DuckDB at startup*: rejected. Couples spec-062 to a producer it doesn't own (the Phase 2 utxo_snapshots producer).

## R4 — Strangler-fig vs hard cut-over

**Decision**: Strangler-fig with an opt-in `--questdb-reads` flag. Default OFF — legacy callers untouched.

**Rationale**:
1. The legacy callers include a sizeable test suite and ad-hoc tooling that would all need migration in one PR under a hard cut-over. Blast radius too large.
2. The seven-day green production gate (plan Appendix A, Step 6) needs the legacy path callable so it can be the fallback if a regression is found.
3. Strangler-fig is the canonical pattern for read-side replacements where dual-write isn't on the table (we don't dual-write; we dual-read).

**Alternatives considered**:
- *Hard cut-over (delete the DuckDB branch in the same PR)*: rejected per blast-radius argument above.
- *Feature flag via env var instead of CLI flag*: rejected. Hidden state. The systemd timer always passes the flag explicitly; ad-hoc callers benefit from the explicit choice.

## R5 — Concurrency model on `mvrv_daily` / `nupl_daily` / `realized_cap_daily`

**Decision**: Last-writer-wins via the QuestDB `DEDUP UPSERT KEYS(ts)` already configured on the three daily tables by spec-061 Phase 1.5-v2 DDL. No advisory lock, no run-id discriminator.

**Rationale**: The aggregator's computation is deterministic for a given `(target_date, as_of_block)` pair: two concurrent runs against the same date produce byte-identical rows because the inputs and the SQL are deterministic. The UPSERT collapses identical rows to one. No coordination is needed.

**Alternatives considered**:
- *Per-date advisory lock via filesystem*: rejected as premature. Adds operational complexity (stale lock cleanup) for a class of bug that cannot occur with deterministic computation.
- *Reject second run if row already exists*: rejected. Breaks the idempotent re-run property that the systemd timer relies on for crash recovery.

**Reopening trigger**: if a future change introduces non-deterministic inputs (e.g. wall-clock-based fields, randomized sampling), this decision MUST be revisited. The spec Clarifications section documents this.

## R6 — Observability surface

**Decision**: Structured INFO log on success (target date, wall-clock duration, count of rows written); structured ERROR log with traceback on failure; Discord webhook POST on failure only.

**Rationale** (per spec Q1):
- Matches the existing Phase 1 supervisor pattern in `scripts/bootstrap/spec061_post_mirror_chain.sh`.
- Keeps the success path silent at the external-notification layer — the `/v1/streams/health` endpoint (spec-061) is the canonical "is the daily window fresh?" surface.
- A Discord ping on every success would be noise; a missing ping is not a signal (Discord silence can mean "all good" OR "aggregator dead"). The /v1/streams/health endpoint disambiguates.

**Alternatives considered**:
- *Prometheus counter `aggregator_runs_total{date,status}`*: deferred. Worth adding when the observability spec lands (Phase 3.a); not needed to close spec-062.
- *Healthchecks.io heartbeat on every success*: deferred. Adds an external dependency the local stack doesn't yet integrate.
- *Logs only, no external notification*: rejected — operator wants a paging signal for daily-window failures and `/v1/streams/health` alone requires someone to be looking.

## R7 — Where the pattern documentation lives

**Decision**: Inline appendix in `specs/062-aggregator-zero-duckdb/plan.md` (Appendix A, "Strangler-Fig Migration Pattern"). One-line cross-link from `docs/PATTERNS.md`. `docs/PATTERNS.md` MUST NOT duplicate the content.

**Rationale** (per spec Q3): spec-062 owns FR-010, so the canonical artifact must live in spec-062's deliverables. `docs/PATTERNS.md` becomes an index, not a copy — eliminates drift risk.

## R8 — Performance baseline

**Measured**: single-date aggregation for 2026-06-04 against the 170 M-row `utxo_lifecycle` table on host QuestDB:
- Total wall-clock: ~25 s (well under the SC-001 budget of 90 s).
- `calculate_daily_realized_cap`: ~6 s.
- Inline supply query: ~6 s.
- `calculate_cointime_daily` (two SUMs): ~10 s.
- `calculate_daily_sopr` (two SUMs + JOIN fallback path tried): ~3 s.
- `mvrv_variants.get_market_cap_history_all_time`: <1 s (empty table).

**No tuning required**. The DDL spec-061 Phase 1.5-v2 published (`PARTITION BY YEAR WAL`) is sufficient at this scale.

**Reopening trigger**: if `utxo_lifecycle` row count exceeds ~500 M or the aggregation budget tightens below 30 s, revisit partition strategy.
