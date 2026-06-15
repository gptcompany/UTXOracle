# Feature Specification: entity_flows_daily QuestDB Producer Pilot

**Feature Branch**: `063-entity-flows-daily-questdb`
**Created**: 2026-06-15
**Status**: Draft
**Input**: spec-063 — first Phase 2 producer migrating `entity_flows_daily` to QuestDB via the canonical strangler-fig pattern published in `specs/062-aggregator-zero-duckdb/plan.md` Appendix A. Pilot for the remaining six Phase 2 producers.

## Clarifications

### Session 2026-06-15

- Q: Which mechanism and default state controls the QuestDB write half rollback toggle (FR-005)? → A: Environment variable `SPEC063_QUESTDB_WRITE`, default ON. The variable is interpreted as OFF when its value (case-insensitive, trimmed) equals one of `0`, `false`, or `no`; any other value (including unset) is treated as ON. Rationale: matches the env-var pattern spec-062 FR-012 already uses for `DISCORD_WEBHOOK_URL`; rollback is a systemd service restart (≈ 15 s), no code change; default ON unblocks the consumer contract immediately on deploy.
- Q: What granularity for the Discord webhook on QuestDB write failure (FR-007)? → A: One webhook POST per `aggregate_flows()` run with an aggregate summary: target date(s), count of failed rows, exception class. Per-row failure detail stays in structured ERROR logs (FR-003) — the webhook is the paging signal, not a log replacement. Rationale: matches the spec-062 FR-012 one-message-per-run pattern; prevents Discord flood when QuestDB is wholly down and N rows fail in a single run; the structured log is the canonical source for per-row diagnostics.
- Q: How does spec-063 handle DuckDB ↔ QuestDB type mismatches in the `entity_flows_daily` schema (FR-010)? → A: Each column gets a deterministic cast enumerated in `data-model.md` during `/speckit.plan`. Lossless casts (e.g. DuckDB `DECIMAL(18,8)` BTC values → QuestDB `DOUBLE` with full precision retention for the 8-decimal domain) are applied silently. Any materially lossy cast (definition: a cast where the round-trip QuestDB→DuckDB would not recover the original value at the documented precision) MUST be called out in `decisions.md` with the exact column, the cast direction, and the residual error bound BEFORE plan is frozen. Rationale: matches spec-062's precedent for `block_heights.timestamp INTEGER` (unix seconds) → `block_heights.ts TIMESTAMP` cast; fail-fast on every mismatch would block the Phase 2 pilot prematurely; silent runtime coercion would hide drift from reviewers.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — `entity_flows_daily` consumer-facing stream stops being empty (Priority: P1)

The nautilus_dev consumer (and any other reader of `/v1/streams/health`) currently sees `entity_flows_daily` as MISSING in QuestDB because the producer only writes DuckDB. After spec-063 lands, every successful `flow_aggregator` invocation populates the QuestDB consumer-facing table in addition to the DuckDB legacy table, and the stream transitions to OK with `stale_seconds` within its declared SLA.

**Why this priority**: This is the user-visible outcome that unblocks the consumer contract. Without this slice, the consumer cannot read `entity_flows_daily` from the QuestDB consumer surface and falls back to the inaccessible DuckDB file. The remaining six Phase 2 producers will reuse whatever pattern spec-063 validates here.

**Independent Test**: Invoke `aggregate_flows()` against a real DuckDB source containing entity events for at least one day. Then query QuestDB `SELECT count(*) FROM entity_flows_daily WHERE date = <today>` and assert the row count matches the DuckDB count for the same date. `/v1/streams/health` reports the stream OK.

**Acceptance Scenarios**:

1. **Given** the DuckDB `entity_flows_daily` table contains rows for date D, **When** `aggregate_flows()` is invoked, **Then** QuestDB `entity_flows_daily` contains exactly the same set of rows (by `(entity_id, date)` identity) with byte-identical numerical payload.
2. **Given** the QuestDB instance is reachable, **When** `aggregate_flows()` runs, **Then** both DuckDB and QuestDB writes complete and a single structured INFO log captures `rows_written_duckdb` and `rows_written_questdb`.
3. **Given** the QuestDB instance is unreachable mid-run, **When** `aggregate_flows()` runs, **Then** the DuckDB write still lands, a structured ERROR log captures the QuestDB exception, and the process exits zero (legacy SSOT integrity preserved per strangler-fig R5).

---

### User Story 2 — Strangler-fig template proves itself on a real Phase 2 producer (Priority: P2)

The canonical pattern in spec-062 plan Appendix A was written and validated against a read-side migration. spec-063 is the first **write-side** application of the same pattern. The pattern's six steps and three test guards must transfer cleanly to a producer.

**Why this priority**: If the pattern needs material adjustments for write-side producers, every subsequent Phase 2 spec (six more) inherits that lesson. Discovering the gap here, on one stream, is much cheaper than discovering it in six parallel specs.

**Independent Test**: A reviewer can validate the spec-063 implementation PR against the spec-062 Appendix A checklist in under 30 minutes. Every checklist item maps to a concrete code change visible in the diff.

**Acceptance Scenarios**:

1. **Given** the spec-062 Appendix A checklist, **When** a reviewer walks the spec-063 PR against it, **Then** every checklist item has a corresponding code change or explicit decision documented in `decisions.md` (no unexplained gaps).
2. **Given** the lessons surfaced by spec-063, **When** the next Phase 2 producer spec is drafted, **Then** the Appendix A pattern document is updated (or a delta note is added) to reflect anything that required adjustment on the write side.

---

### User Story 3 — Rollback path is callable without code revert (Priority: P3)

A regression introduced by the QuestDB write path (e.g. a save method that raises on a corner case the dual-write didn't anticipate) must be containable without reverting code. The operator can disable the QuestDB write half via configuration and ride on the legacy DuckDB-only writer while the bug is fixed.

**Why this priority**: Strangler-fig migrations are valuable because they preserve a rollback option. spec-063 must keep that option exercisable for the duration of the 7-day green observation gate.

**Independent Test**: Setting an explicit feature flag (env var or CLI flag, defined in plan) to disable the QuestDB write half makes `aggregate_flows()` produce zero QuestDB rows and only DuckDB rows. Existing tests remain green.

**Acceptance Scenarios**:

1. **Given** the QuestDB write feature flag is set to OFF, **When** `aggregate_flows()` runs, **Then** no QuestDB rows are produced for that invocation and no QuestDB connection is opened.
2. **Given** the flag is OFF and a previous run produced QuestDB rows, **When** `aggregate_flows()` runs, **Then** the existing QuestDB rows are NOT deleted — the rollback is forward-only, the legacy DuckDB SSOT remains the recovery source.

---

### Edge Cases

- What happens when QuestDB `entity_flows_daily` table does not yet exist? The producer's first run MUST create it via the same `create_tables_if_not_exist` pattern that spec-061/062 use; first invocation provisions the table, subsequent invocations are idempotent via `DEDUP UPSERT KEYS`.
- What happens when DuckDB write fails (disk full, schema drift, etc.)? Per Story 1 acceptance scenario 3 inverted: the legacy SSOT failure surfaces as a Python exception out of `aggregate_flows()`, the QuestDB write is NOT attempted, and the process exits non-zero. DuckDB integrity is non-negotiable during the transition window.
- What happens when DuckDB and QuestDB report different row counts at end of run? The structured INFO log carries both counts; any divergence > 0 fires the Discord webhook for operator attention and is logged at WARNING. The run still exits zero (rows are reconcilable via re-run idempotency).
- What happens when `aggregate_flows()` is invoked with `sample_limit` set? Both writes honour the same limit — DuckDB legacy and QuestDB pilot produce identical row sets for the limited sample.
- What happens during a concurrent invocation (two `aggregate_flows()` runs overlapping)? QuestDB `DEDUP UPSERT KEYS(date, entity_id)` collapses concurrent writes to a single row per `(entity_id, date)` pair. DuckDB `INSERT OR REPLACE` provides analogous semantics. Outcome converges deterministically.
- What happens if code discovery reveals `aggregate_flows()` is not the production runtime path? The escape hatch in `decisions.md` kicks in and spec-063 degrades to Option A (mirror script) — see Out of Scope.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every successful `aggregate_flows()` invocation MUST write the same set of `(entity_id, date)` rows to QuestDB `entity_flows_daily` that it writes to DuckDB `entity_flows_daily`, with byte-identical numerical payload (inflow_btc, outflow_btc, net_flow_btc, transaction_count where applicable).
- **FR-002**: The legacy DuckDB write MUST remain the source of truth during the transition window. A QuestDB write failure MUST NOT roll back, retry, or in any way affect the DuckDB write that has already succeeded.
- **FR-003**: A QuestDB write failure MUST produce a structured ERROR log identifying the failing per-row payload (or the count of failing rows), the exception class, and a one-line summary suitable for the Discord webhook (FR-007).
- **FR-004**: The producer MUST emit a structured INFO log per successful invocation including `rows_written_duckdb`, `rows_written_questdb`, the date range covered, and the wall-clock duration of each write half.
- **FR-005**: The producer MUST expose a rollback configuration toggle via the environment variable `SPEC063_QUESTDB_WRITE`. Default is ON. The variable is treated as OFF when its value (case-insensitive, whitespace-trimmed) is exactly `0`, `false`, or `no`. Any other value, including unset, is treated as ON. With the toggle OFF, `aggregate_flows()` MUST NOT open any QuestDB connection and MUST NOT modify any pre-existing QuestDB rows.
- **FR-006**: QuestDB `entity_flows_daily` MUST have `DEDUP UPSERT KEYS(date, entity_id)` configured so re-runs of the same date are idempotent and concurrent invocations converge.
- **FR-007**: A QuestDB write failure MUST post exactly one Discord webhook notification per `aggregate_flows()` run (re-using the spec-062 FR-012 surface) with `entity_flows_daily` as the stream identifier, the target date(s), the count of failed rows, and the exception class. Per-row failure detail lives in the structured ERROR logs (FR-003), NOT in the webhook payload. Successful runs MUST NOT post. A run where some rows succeed and others fail MUST still post exactly one webhook summarising the failure count.
- **FR-008**: The automated test suite MUST include a guard that fails CI if the producer is invoked under nominal conditions and the QuestDB write half is silently skipped (e.g. because of a missing import or a typo'd config key).
- **FR-009**: The automated test suite MUST include a guard that fails CI if a future refactor removes the DuckDB write half before the legacy-removal follow-up spec authorises it.
- **FR-010**: Schema parity: the QuestDB `entity_flows_daily` columns MUST be a 1:1 mirror of the DuckDB columns as observed at the start of spec-063, with column-by-column casts enumerated in `data-model.md`. Lossless casts (round-trip preserves the original value at the documented precision for the domain) are applied silently. Materially lossy casts MUST be enumerated in `decisions.md` with column, direction, and residual error bound before plan is frozen — and MUST be re-confirmed by the owner during `/speckit.plan`.
- **FR-011**: The producer MUST be observable via `/v1/streams/health`: a successful run transitions `entity_flows_daily` from MISSING to OK; a failed QuestDB half is reflected as STALE within one SLA window without any code change in the health endpoint.

### Key Entities *(include if feature involves data)*

- **`entity_flows_daily` (DuckDB)**: The legacy SSOT table. Schema is what `aggregate_flows()` currently produces via the `INSERT OR REPLACE` statement at the producer site. Spec-063 does NOT change this schema.
- **`entity_flows_daily` (QuestDB)**: The new consumer-facing target. Schema mirrors DuckDB columns 1:1, designated timestamp on `date`, `DEDUP UPSERT KEYS(date, entity_id)`. Schema details captured in `data-model.md` during planning.
- **`entity_movement_events` (DuckDB)**: The source table from which `entity_flows_daily` is computed. spec-063 does NOT migrate this — it stays DuckDB. Only the *result* table (`entity_flows_daily`) is dual-written.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After spec-063 lands and a single `aggregate_flows()` invocation runs in production, `/v1/streams/health` reports `entity_flows_daily` as OK with `stale_seconds` ≤ the declared SLA for ≥ 95 % of polls over a one-hour window.
- **SC-002**: For any date D where the DuckDB `entity_flows_daily` table holds N rows, the QuestDB `entity_flows_daily` table also holds N rows for date D within 5 seconds of the `aggregate_flows()` invocation completing.
- **SC-003**: A simulated QuestDB write failure during `aggregate_flows()` MUST NOT cause a missing or corrupted row in the DuckDB legacy table; 100 % of pre-failure DuckDB writes persist.
- **SC-004**: An engineer migrating the next Phase 2 producer (e.g. `mempool_predictions`) reuses the spec-063 deliverables as a working template and completes the equivalent write-side migration in under one working day end-to-end (spec + code + tests + smoke), with no new entries needing to be added to the spec-062 Appendix A pattern document.
- **SC-005**: For seven consecutive days after spec-063 deployment, the `entity_flows_daily` stream in `/v1/streams/health` reports OK at every poll and the producer emits zero ERROR logs from the QuestDB write path.

## Assumptions

- `scripts/live/flow_aggregator.py::aggregate_flows()` is the canonical write path for `entity_flows_daily`. Code discovery in planning will confirm this; if a different runtime path is found, the escape hatch in `decisions.md` activates.
- DuckDB `entity_flows_daily` schema is what `aggregate_flows()`'s `INSERT OR REPLACE ... SELECT ...` statement produces. `data-model.md` will enumerate the actual column list during planning.
- The QuestDB host instance reachable on `:8812` (PG-wire) and `:9009` (ILP) is the same instance that spec-061 Phase 1.5-v2 and spec-062 already consume.
- The Discord webhook reused for FR-007 is the same `DISCORD_WEBHOOK_URL` already configured for spec-062 FR-012 — no new alerting channel is introduced.
- The 7-day green observation gate (SC-005) runs in parallel to spec-062's Phase 7 gate; both can complete simultaneously.
- Phase 2 producer migrations after spec-063 are out of scope but the lessons surfaced here feed back into spec-062 plan Appendix A within one revision.

## Out of Scope

- Migrating the other six Phase 2 streams (`mempool_predictions`, `net_flow_metrics`, `backtest_whale_signals`, `price_analysis`, `utxo_snapshots`, residual `utxo_lifecycle_full` reader cleanup). Each gets its own spec.
- Removing the DuckDB `entity_flows_daily` write half. That removal is a follow-up spec triggered by the 7-day green observation gate (SC-005), parallel to spec-062 Phase 8.
- Migrating `entity_movement_events`, `entity_transfer_edges`, `entity_balance_snapshots_daily`, `entity_counterparty_edges_daily` — the four sibling tables that `aggregate_flows()` also writes. spec-063 covers ONLY `entity_flows_daily`. Sibling tables will be handled by separate Phase 2 specs once spec-063 has validated the pattern on a single stream.
- Changing the `entity_flows_daily` schema beyond column-add. The contract MUST match the DuckDB schema 1:1 at first.
- Performance optimisation of the underlying DuckDB aggregation. spec-063 is a transport-layer migration; the SQL stays as-is.
- A new systemd timer or scheduling mechanism for `aggregate_flows()`. The producer's existing invocation contract (whatever it is — to be confirmed in planning) is preserved.
- Code changes outside `scripts/live/flow_aggregator.py`, `api/questdb_repository.py`, and the new tests + new spec docs. If discovery surfaces a need to touch broader code (e.g. the health endpoint mapping), it goes in a follow-up spec.
