# Feature Specification: Aggregator Zero-DuckDB Read Path

**Feature Branch**: `062-aggregator-zero-duckdb`
**Created**: 2026-06-05
**Status**: Draft (retroactive — implementation already shipped in commit `6f27cbb` on branch `061-stream-consumption-contract`)
**Input**: spec-062 — eliminate the last DuckDB dependency from the daily metrics aggregator critical path.

## Clarifications

### Session 2026-06-05

- Q: What observability signals must the aggregator emit on each run? → A: Structured logs (INFO on success, ERROR on failure with full traceback) plus a Discord webhook notification on failure only — no external signal on success. Rationale: matches the existing Phase 1 supervisor pattern (`spec061_post_mirror_chain.sh`) and keeps signal-to-noise ratio high. The `/v1/streams/health` endpoint (spec-061) remains the canonical "is the daily window fresh?" surface.
- Q: What happens when two aggregator runs target the same date concurrently (e.g. timer fires while operator runs a manual backfill)? → A: Last-writer-wins via QuestDB `DEDUP UPSERT KEYS(ts)` on the daily tables — no advisory lock. Valid only because the calculation is deterministic for a given (target_date, as_of_block) pair: two concurrent runs produce identical row values and the UPSERT collapses them. If a future change introduces non-deterministic inputs (e.g. wall-clock-based fields, randomized sampling), this decision MUST be revisited and replaced with either a per-date advisory lock or an explicit run_id discriminator.
- Q: Where does the strangler-fig migration pattern live so the seven Phase 2 producers can reuse it without re-deriving? → A: Inline appendix in `specs/062-aggregator-zero-duckdb/plan.md` (single source of truth, owned by this spec) plus a one-line cross-link from `docs/PATTERNS.md` for discoverability. `docs/PATTERNS.md` MUST NOT copy the content — only index it — so the pattern remains versioned with spec-062 and never drifts.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Daily metrics produced without touching DuckDB (Priority: P1)

The platform owner schedules the daily metrics aggregator (mvrv/nupl/realized_cap/sopr/cointime) as a systemd timer that must run reliably even when other consumers hold a long-lived DuckDB writer or reader lock. The aggregator can run end-to-end against QuestDB only — opening no DuckDB file — so that contention with the live wave1 materializer can no longer block, slow, or corrupt the daily metrics path.

**Why this priority**: Without this slice, the aggregator is one DuckDB lock away from missing a daily window. spec-061 Phase 1.5-v2 removed DuckDB from the freshness producers; this slice closes the matching gap on the read side. Any later observability or alerting work assumes that "no daily metrics for date D" is a real incident, not a DuckDB lock artefact.

**Independent Test**: Run the aggregator for a single date with the dual flag, then assert (a) the row landed in the QuestDB `mvrv_daily` / `nupl_daily` / `realized_cap_daily` tables and (b) no process held an open file descriptor on the legacy DuckDB file during or after the run.

**Acceptance Scenarios**:

1. **Given** a populated QuestDB `utxo_lifecycle` table and a recent `block_heights` + `daily_prices` row, **When** the operator runs the aggregator for a single date in QuestDB-only mode, **Then** within one minute the corresponding daily metric rows appear in QuestDB and the DuckDB file is never opened by the aggregator.
2. **Given** the live wave1 materializer is actively writing to DuckDB and holding its writer lock, **When** the operator runs the aggregator for the same date in QuestDB-only mode, **Then** the run completes successfully and produces the same daily metric values as scenario 1.
3. **Given** the QuestDB `utxo_snapshots` table is empty (Phase 2 producer not yet shipped), **When** the operator runs the aggregator in QuestDB-only mode, **Then** the run completes successfully, the mvrv/nupl/realized_cap/sopr/cointime values are still produced, and the variant that depends on snapshot history (mvrv_z_rbn) is reported as absent rather than fabricated.

---

### User Story 2 — Legacy DuckDB callers still work unchanged (Priority: P2)

Developers and ad-hoc tooling that have historically pointed the aggregator at the local DuckDB file must continue to work without code changes during the transition window, so that the migration can be rolled back per-caller if a regression is discovered in QuestDB.

**Why this priority**: A hard cut-over would force every internal script, test fixture, and notebook onto the new path in the same change. That increases blast radius. Keeping the DuckDB path callable until the new path has run cleanly for at least seven days lets us roll back per-caller without reverting code.

**Independent Test**: Run the existing aggregator test suite — which patches a DuckDB connection — and confirm it passes without invoking any QuestDB code path.

**Acceptance Scenarios**:

1. **Given** an existing test that supplies a mocked DuckDB connection and does not opt into QuestDB reads, **When** the aggregator is invoked, **Then** the legacy DuckDB queries against `utxo_lifecycle_full` and `utxo_snapshots` are executed and no QuestDB connection is opened.
2. **Given** the operator omits the QuestDB-reads flag at runtime, **When** the aggregator is invoked, **Then** the script behaves identically to its pre-spec-062 form (same SQL, same outputs, same exit code).

---

### User Story 3 — Future Phase 2 producers can fill the snapshot gap without code churn (Priority: P3)

When a Phase 2 producer eventually populates QuestDB `utxo_snapshots`, the variant metric that depends on it (mvrv_z_rbn) starts being reported automatically, without requiring further code changes to the aggregator.

**Why this priority**: This guarantees the spec-062 work is forward-compatible with Phase 2. It also documents the explicit "transparent absence" behaviour so that nobody backfills mvrv_z_rbn with stale data to "fix" the None and silently changes the contract.

**Independent Test**: Insert a synthetic row into QuestDB `utxo_snapshots` (≥30 historical points) and confirm the next aggregator run produces a non-null `mvrv_z_rbn` without any code change.

**Acceptance Scenarios**:

1. **Given** QuestDB `utxo_snapshots` has fewer than 30 historical rows, **When** the aggregator runs, **Then** `mvrv_z_rbn` is reported as absent (null) and the run is still considered successful.
2. **Given** QuestDB `utxo_snapshots` has ≥30 historical rows, **When** the aggregator runs, **Then** `mvrv_z_rbn` is computed and persisted alongside the other variants.

---

### Edge Cases

- What happens when `block_heights` has no rows for the target date? The aggregator surfaces a missing-blocks error and does NOT persist any partial daily metric row — the daily window simply does not exist until the source freshness producers catch up.
- What happens when `daily_prices` has no row for the target date? Price-dependent metrics (market_cap, sopr fallback) report as absent; the cointime metrics that are price-independent still produce.
- What happens when QuestDB is unreachable? The aggregator fails fast with a connection error and does NOT silently fall back to DuckDB — that would mask the SPOF this spec was created to eliminate.
- What happens when both flags are unset? The legacy DuckDB path runs unchanged (User Story 2).
- What happens during a partial mid-run failure (e.g., `save_mvrv_daily` succeeds but `save_nupl_daily` raises)? Per FR-007, sibling-row writes are NOT rolled back in either mode — the successful row stays. In **legacy dual-write** mode the failure is logged and swallowed (DuckDB SSOT preserves the data). In **QuestDB-only** mode all per-row save attempts run to completion first, then `QuestDBPersistenceError` is raised, the Discord webhook fires (FR-012), and the process exits non-zero. In both cases the next idempotent re-run upserts the missing rows via `DEDUP UPSERT KEYS(ts)`. `/v1/streams/health` will show the failing stream as STALE until the next successful run.
- What happens when two aggregator runs target the same date concurrently? Both succeed; the QuestDB `DEDUP UPSERT KEYS(ts)` constraint collapses the two writes to a single row. Because the calculation is deterministic for `(target_date, as_of_block)`, the resulting row is byte-identical regardless of arrival order.
- What happens if the operator passes `--questdb-reads` without `--questdb-only`? The aggregator reads source freshness from QuestDB but still attempts the DuckDB persist path — useful for verifying read-side parity before flipping the write side.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The daily metrics aggregator MUST be runnable in a mode in which no DuckDB file is opened by the aggregator process or any of its calculation helpers.
- **FR-002**: When invoked in that mode, the aggregator MUST compute the same daily metric values as the legacy DuckDB path for the same date, defined as: integer columns byte-identical; floating-point columns within `abs(qdb_val - duckdb_val) / max(abs(qdb_val), abs(duckdb_val), 1.0) < 1e-9` relative tolerance (covers SUM ordering jitter without permitting semantic drift).
- **FR-003**: When invoked in the legacy mode (no flag), the aggregator MUST behave identically to its pre-spec-062 form: same SQL, same outputs, no QuestDB connection opened.
- **FR-004**: The aggregator MUST persist mvrv/nupl/realized_cap rows into the corresponding QuestDB daily tables for the target date, idempotently (re-running the same date overwrites by primary key).
- **FR-005**: When the snapshot-dependent variant (mvrv_z_rbn) cannot be computed because the snapshot history is too short, the aggregator MUST report it as explicitly absent rather than substituting zero, the last known value, or a value computed from a different source.
- **FR-006**: The aggregator MUST fail fast and exit non-zero if the configured QuestDB instance is unreachable when running in the zero-DuckDB mode — it MUST NOT silently fall back to DuckDB.
- **FR-007**: Each daily row (`mvrv_daily`, `nupl_daily`, `realized_cap_daily`) is persisted independently with mode-dependent failure semantics. Successful sibling-row writes MUST NEVER be rolled back regardless of mode (per-row idempotency via `DEDUP UPSERT KEYS(ts)`, FR-004). The failure handling differs:
  - **Legacy dual-write mode** (no `--questdb-only`): a QuestDB per-row save failure logs ERROR and is swallowed; DuckDB remains SSOT. Rationale: strangler-fig R5 preserves the fallback path.
  - **QuestDB-only mode** (`--questdb-only`): a QuestDB per-row save failure logs ERROR, raises `QuestDBPersistenceError` after all per-row attempts complete (so successful siblings still land), triggers the Discord webhook (FR-012), and exits non-zero. Rationale: in zero-DuckDB mode there is no fallback SSOT, so silent partial success would let `/v1/streams/health` lie about the daily window.
- **FR-008**: The automated test suite MUST include a guard that fails CI if any of the migrated read helpers is invoked in QuestDB-reads mode and observably opens a DuckDB connection.
- **FR-009**: The automated test suite MUST include a source-level guard that fails CI if the entrypoint stops supporting the "no DuckDB file opened" mode (e.g., if a future refactor unconditionally opens DuckDB).
- **FR-010**: Documentation MUST record the strangler-fig pattern (dual-flag, opt-in, parallel branches) so that the same pattern can be applied verbatim to the seven Phase 2 stream producers. The canonical pattern document MUST live in `specs/062-aggregator-zero-duckdb/plan.md` as a dedicated appendix; `docs/PATTERNS.md` MUST contain a one-line cross-link to it and MUST NOT duplicate the content.
- **FR-011**: The aggregator MUST emit a structured INFO log on every successful single-date run (including the target date, the wall-clock duration, and the count of metric rows written), and a structured ERROR log with full traceback on every failure.
- **FR-012**: On failure only, the aggregator MUST post a notification to the configured Discord webhook (`DISCORD_WEBHOOK_URL`) containing the failing date, the exception type, and a one-line summary. Successful runs MUST NOT produce any external notification — staleness detection is delegated to the `/v1/streams/health` endpoint.
- **FR-013**: Two concurrent runs targeting the same date MUST both succeed and converge to identical persisted values, with the second-arriving write overwriting the first via the QuestDB `DEDUP UPSERT KEYS(ts)` constraint. No advisory lock or run rejection is required while inputs remain deterministic in `(target_date, as_of_block)`.

### Key Entities *(include if feature involves data)*

- **utxo_lifecycle**: The QuestDB table containing per-UTXO lifecycle rows (creation block, creation price, btc value, spent block, spent price, realized value, age, cohort). This spec migrates four read paths off the legacy DuckDB equivalent (`utxo_lifecycle_full`) onto this table: realized cap, SOPR, cointime liveliness, and total supply.
- **utxo_snapshots**: The QuestDB table containing per-block daily snapshots of market/realized cap, supply by holder age cohort, and HODL waves. This spec migrates the all-time market cap history reader (used by the MVRV-Z RBN variant) onto this table. The table may be empty during the transition window — the aggregator handles that explicitly (User Story 3).
- **mvrv_daily / nupl_daily / realized_cap_daily**: The QuestDB consumer-facing daily tables that receive the aggregator's output. These are the same tables spec-061 publishes to nautilus_dev — this spec does not change their schema, only adds a write path that does not depend on DuckDB.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The daily metrics aggregator completes a single-date run in under 90 seconds end-to-end against the production-scale `utxo_lifecycle` table (~170 million rows) using only the QuestDB read path.
- **SC-002**: During and after a zero-DuckDB aggregator run, zero processes hold an open file descriptor on the legacy DuckDB file (`fuser` reports no holders attributable to the aggregator).
- **SC-003**: 100% of the existing daily-metrics test cases continue to pass without modification when not opting into the new path.
- **SC-004**: The aggregator can run on the same host, at the same minute, as a live DuckDB writer holding an exclusive lock, without blocking, retrying, or losing the daily window.
- **SC-005**: A documented strangler-fig pattern is published in the repository such that an engineer applying it to one of the Phase 2 producers can complete the migration of a single stream in under one working day, end-to-end (code + tests + smoke).
- **SC-006**: When `utxo_snapshots` is empty, the aggregator surfaces `mvrv_z_rbn` as explicitly absent in 100% of runs — never as zero, last-known, or any computed surrogate.

## Assumptions

- The QuestDB `utxo_lifecycle` table already contains the same per-UTXO columns as the legacy DuckDB `utxo_lifecycle_full` table (creation_block, creation_price_usd, btc_value, realized_value_usd, is_spent, spent_block, spent_price_usd, age_blocks). spec-061 Phase 1 established and verified this table at ~170 million rows.
- The QuestDB `block_heights` and `daily_prices` tables are populated and kept fresh by the spec-061 Phase 1.5-v2 timers (`utxoracle-block-heights-catchup.timer`, `utxoracle-daily-prices-refresh.timer`).
- The legacy DuckDB read path will remain callable until at least seven consecutive days of green production runs on the QuestDB path have been observed; only then is it eligible for removal under a follow-up spec.
- The opt-in flag model (the operator explicitly requests QuestDB reads) is acceptable because the systemd timer is the only production caller and it always passes both flags; ad-hoc callers default to the legacy path until they migrate.
- "No DuckDB file opened" is observable from the host via `fuser` / `lsof` against the canonical DuckDB file path; the test suite simulates this via a connection mock that records whether `execute` was called.
- The seven Phase 2 stream producers (entity_flows_daily, mempool_predictions, net_flow_metrics, backtest_whale_signals, price_analysis, utxo_lifecycle_full reader cleanup, utxo_snapshots producer) are tracked under separate specs and are explicitly out of scope here.

## Out of Scope

- Producers for the seven Phase 2 streams listed above. Each will be specified separately and will reuse the strangler-fig pattern established here.
- Removal of the legacy DuckDB read branches. That removal is a separate spec triggered by the seven-day green production gate.
- Migration of unrelated DuckDB consumers (URPD feature pipeline, wave1 materializer, ad-hoc analytical scripts). They have their own consumers and are out of the daily metrics critical path.
- Schema changes to the consumer-facing `mvrv_daily` / `nupl_daily` / `realized_cap_daily` tables. spec-061 owns that contract.
- Performance tuning of QuestDB itself (indexing, partitioning, WAL settings). spec-061 Phase 1.5-v2 owns the DDL.
