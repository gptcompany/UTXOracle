# Implementation Plan: entity_flows_daily QuestDB Producer Pilot

**Branch**: `063-entity-flows-daily-questdb` | **Date**: 2026-06-15 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/063-entity-flows-daily-questdb/spec.md`

## Summary

Apply the canonical strangler-fig pattern from `specs/062-aggregator-zero-duckdb/plan.md` Appendix A to the first Phase 2 producer, `entity_flows_daily`. The producer (`scripts/live/flow_aggregator.py::aggregate_flows`) currently writes a single `INSERT OR REPLACE` aggregation to DuckDB `entity_flows_daily` and nothing to QuestDB. After spec-063, every successful invocation also pushes the same row set to QuestDB `entity_flows_daily` via a new sync save method on `api.questdb_repository`, gated by env var `SPEC063_QUESTDB_WRITE` (default ON, OFF on `0|false|no`). QuestDB write failures are isolated from the DuckDB SSOT, produce per-row structured ERROR logs, and surface as exactly one aggregated Discord webhook per failing run. Code discovery confirmed the existing QuestDB DDL (`api/questdb_repository.py:572`) is present but missing `DEDUP UPSERT KEYS`; the plan adds it via an idempotent ALTER TABLE.

## Technical Context

**Language/Version**: Python 3.11 (project pinned)

**Primary Dependencies**:
- `duckdb` (existing legacy SSOT; spec-063 does NOT alter the DuckDB write path)
- `psycopg` v3 via `api.questdb_repository._open_pg_sync` (sync PG-wire writes — already used by spec-061 Phase 1.5-v2 and spec-062 retroactively)
- `urllib.request` for Discord webhook (re-using the helper added by spec-062 FR-012)
- No new third-party dependency introduced.

**Storage**:
- DuckDB file at `data/utxoracle.duckdb` (legacy SSOT; unchanged)
- QuestDB host instance on `:8812` (PG-wire) — same instance spec-061/062 already use

**Testing**: `pytest`, mocked QuestDB connection for unit tests; live QuestDB optional for integration smoke (not gated in CI per spec-061 streams-contract workflow flakiness).

**Target Platform**: Linux server (Ubuntu 22.04), single-host deployment. No platform-specific code.

**Project Type**: single (Python module + producer CLI; no frontend, no API surface added).

**Performance Goals**: Per-run write of N rows (N ≈ cardinality of distinct `(entity_id, date)` pairs for the aggregation window) MUST complete within the same wall-clock budget as the DuckDB write half plus ≤ 25 %. Hard ceiling: 10 s for N ≤ 10 000.

**Constraints**:
- NO new systemd timer / scheduling mechanism (per user input hard constraint).
- NO changes outside `scripts/live/flow_aggregator.py`, `api/questdb_repository.py`, new `tests/test_flow_aggregator_questdb.py`, and optionally `docs/contracts/stream_registry.yaml` (NOT needed per discovery — entry already present).
- NO DuckDB schema change. NO removal of any existing DuckDB write path.
- Cast table in `data-model.md` MUST be signed off; materially lossy casts escalated to `decisions.md` BEFORE plan freeze (FR-010 + Clarify Q3).
- `aggregate_flows()` is currently invoked ONLY by tests — see Constitution Check note and the explicit AC4 caveat below.

**Scale/Scope**:
- 1 producer function modified (`aggregate_flows` in `flow_aggregator.py`)
- 1 repository write method added (`save_entity_flows_daily` in `questdb_repository.py`)
- 1 DDL adjustment (ALTER TABLE for DEDUP UPSERT KEYS)
- 1 new test file with 5 RED guards (a–e)
- 0 schema changes on DuckDB side
- 0 systemd unit changes

## Constitution Check

*GATE: must pass before Phase 0 research. Re-evaluated post Phase 1 design.*

| Principle | Verdict | Evidence |
|---|---|---|
| **I. Code Quality & Simplicity (KISS/YAGNI)** | PASS | Reuses spec-062 strangler-fig pattern verbatim (Appendix A). No new abstractions: env-var toggle is a one-line `os.environ.get`; save method is a thin wrapper over existing `_open_pg_sync`. The dual-write block lands at one site (the existing INSERT OR REPLACE point) in `flow_aggregator.py`, not scattered. |
| **II. Test-First Discipline (NON-NEGOTIABLE)** | PASS (with explicit RED enforcement) | spec-062 was retroactive (post-hoc tests). spec-063 ships TDD per Constitution: 5 RED tests committed BEFORE the corresponding GREEN implementation, separate commits per RED/GREEN cycle. Test list: (a) env toggle gates QuestDB connection open, (b) deterministic payload byte-identity DuckDB ↔ QuestDB, (c) QuestDB failure does not roll back DuckDB, (d) webhook fires exactly once per failing run, (e) cast contract matches data-model.md. tdd-guard agent enforced in pre-commit. |
| **III. User Experience Consistency** | PASS | No CLI changes to `aggregate_flows()` — invocation contract preserved. Env var follows existing `DISCORD_WEBHOOK_URL` convention (spec-062 FR-012). No frontend / WebSocket / HTML surface touched. |
| **IV. Performance Standards** | PASS | New write path adds at most one extra round-trip + one psycopg flush per `aggregate_flows()` invocation. Live measurement target ≤ 10 s for N ≤ 10 000 rows. No Bitcoin Core RPC pressure (the writes are derived from existing DuckDB aggregation). |
| **V. Data Privacy & Security** | PASS | No external surface added. Reads/writes stay on host-local QuestDB. Webhook payload (FR-007) contains only stream name, date, exception class, count — no PII, no addresses, no UTXO contents. |

**Notes**:
- **Production runtime gap**: `aggregate_flows()` is invoked ONLY by tests today. AC4 / SC-001 / SC-005 from spec.md cannot be verified by automatic scheduling — they require an operator-driven manual smoke (run the script once, observe `/v1/streams/health`). This is documented in the rollback runbook and in the spec-063 PR description. A separate spec will own the scheduling decision; spec-063 ships the dual-write half so the next spec only needs to add a timer.
- **Integration-test CI gap (analyze F7)**: The two integration-marked tests `test_entity_flows_daily_dedup_ddl_applied` (T006) and `test_rollback_OFF_does_not_delete_pre_existing_questdb_rows` (T020) require a live QuestDB instance. The spec-061 streams-contract CI workflow is currently flaky on GitHub-hosted runners (independent of spec-063 — see PR #9 thread). spec-063 accepts this gap: the DDL adjustment in T009 (ALTER TABLE … DEDUP ENABLE UPSERT KEYS) is verified by local smoke against the host QuestDB during T029, NOT in CI. A future spec MAY add a mocked-DDL syntactic test that runs in CI without QuestDB; out of scope here.
- **Re-check post-design**: PASS — no design-phase additions introduce constitutional concerns.

## Project Structure

### Documentation (this feature)

```
specs/063-entity-flows-daily-questdb/
├── spec.md              # Feature spec with 3 clarifications integrated
├── plan.md              # This file
├── research.md          # Phase 0 — env var, webhook aggregation, cast strategy, save method placement, transport choice, batch/back-pressure
├── data-model.md        # Phase 1 — cast table per column, DDL diff, DEDUP UPSERT KEYS adjustment
├── quickstart.md        # Phase 1 — operator runbook with manual smoke + rollback runbook
├── contracts/
│   ├── envvars.md                  # SPEC063_QUESTDB_WRITE contract
│   ├── save_entity_flows_daily.md  # Repository save method signature + idempotency contract
│   └── webhook_payload.md          # Discord webhook aggregated payload format
├── decisions.md         # Phase 1 — decisions log: cast escalations (none expected per discovery), escape hatch verdict, lossy cast residual error (none)
├── checklists/
│   └── requirements.md  # Spec quality checklist (12/12 green)
└── tasks.md             # Phase 2 output (created by /speckit.tasks — NOT this command)
```

### Source Code (repository root)

```
scripts/live/
└── flow_aggregator.py                   # MODIFIED: add dual-write block after the existing INSERT OR REPLACE,
                                         # env-var gated, structured logging + webhook on failure

api/
└── questdb_repository.py                # MODIFIED:
                                         # - add save_entity_flows_daily(...) sync method
                                         # - add lazy DEDUP UPSERT KEYS(date, entity_id) via ALTER TABLE inside create_tables_if_not_exist
                                         # - reuse _open_pg_sync (already used by spec-061 Phase 1.5-v2 writers)

tests/
└── test_flow_aggregator_questdb.py      # NEW — 5 RED guards (a–e), all committed before implementation lands

# NOT modified (per discovery):
# - docs/contracts/stream_registry.yaml — entry already present at line 94, freshness/SLA/timestamp_column correct
# - any systemd unit — aggregate_flows is invoked by tests only today; scheduling deferred to a separate spec
# - DuckDB schema in scripts/live/init_flow_artifacts.py — legacy schema unchanged per FR-002
```

**Structure Decision**: single-project layout. spec-063 is a strangler-fig write-side delta, not a new module. The dual-write block lives at the existing producer site; the repository save method is a new method on the existing `api.questdb_repository` module. Matches Constitution Principle I (no premature abstraction, single-purpose change).

## Phase 0 — Research

See [research.md](./research.md). Six decisions consolidated:

1. **Env var format and parsing rules** — Clarify Q1 + restated for test pinning.
2. **Webhook aggregation pattern** — Clarify Q2 + exact JSON payload schema + one-shot-per-run guarantee.
3. **Cast strategy** — Clarify Q3 + discovery; all six columns lossless, no `decisions.md` escalation.
4. **Save method placement** — `api/questdb_repository.save_entity_flows_daily` per existing spec-061/062 convention. Sync (psycopg) to match producer sync context.
5. **Write transport: ILP vs PG-wire** — psycopg sync `INSERT ... ON CONFLICT ... DO UPDATE` (matches spec-061 Phase 1.5-v2 writers). ILP rejected: batch size is typically tiny (≤ 1 000 rows / run); PG-wire INSERT matches the per-row error model spec.md FR-007 mandates; spec-062 reader migration uses psycopg sync.
6. **Batch size + back-pressure** — bound is the row count SELECT returns; memory ceiling ≈ 4 MB for N = 10 000 — trivial, no streaming required.

## Phase 1 — Design & Contracts

### Data Model

See [data-model.md](./data-model.md). Summary:

**Read surface** (where the rows come from): existing DuckDB `INSERT OR REPLACE INTO entity_flows_daily SELECT ... FROM entity_transfer_edges` — unchanged. After the DuckDB INSERT, spec-063 reads back the affected rows from DuckDB via `SELECT * FROM entity_flows_daily WHERE date IN (...)` and pushes them to QuestDB. This avoids re-running the aggregation SQL in QuestDB (which would require migrating `entity_transfer_edges` too — out of scope per spec.md).

**Write surface** (target):

| Column | DuckDB type | QuestDB type | Cast | Lossy? |
|---|---|---|---|---|
| `entity_id` | `VARCHAR` | `SYMBOL INDEX` | implicit string interning | No (SYMBOL preserves string identity) |
| `date` | `DATE` | `TIMESTAMP` | `cast(date as timestamp)` at midnight UTC | No |
| `inflow_btc` | `DOUBLE` | `DOUBLE` | identity | No |
| `outflow_btc` | `DOUBLE` | `DOUBLE` | identity | No |
| `netflow_btc` | `DOUBLE` | `DOUBLE` | identity | No |
| `is_exchange` | `BOOLEAN` | `BOOLEAN` | identity | No |
| `ts` (new) | — (not in DuckDB) | `TIMESTAMP` | `datetime.utcnow()` at write time, used as the designated timestamp for QuestDB partitioning | N/A (write-only) |

**No materially lossy cast detected during discovery.** `decisions.md` will record this verdict explicitly (FR-010 + Clarify Q3 compliance).

**DDL adjustment**: existing `CREATE TABLE IF NOT EXISTS entity_flows_daily (...) timestamp(ts) PARTITION BY DAY` at `api/questdb_repository.py:572` is missing `DEDUP UPSERT KEYS`. spec-063 adds the following inside `create_tables_if_not_exist` after the CREATE TABLE call:

```sql
ALTER TABLE entity_flows_daily SET TYPE WAL;
ALTER TABLE entity_flows_daily DEDUP ENABLE UPSERT KEYS(date, entity_id);
```

Both wrapped in `try/except` to keep them idempotent on existing tables that already have WAL or DEDUP enabled (matches spec-061 Phase 1.5-v2 pattern).

### Contracts

See [contracts/](./contracts/). Three artifacts:

1. **`envvars.md`** — `SPEC063_QUESTDB_WRITE` contract (default ON; OFF on `0`/`false`/`no`, case-insensitive trimmed; any other value or unset = ON). The parser is a `_should_write_questdb()` helper inside `flow_aggregator.py`. Reused by the rollback runbook in `quickstart.md`.

2. **`save_entity_flows_daily.md`** — Repository save method signature:
   ```python
   def save_entity_flows_daily(
       *,
       entity_id: str,
       date: date,
       inflow_btc: float,
       outflow_btc: float,
       netflow_btc: float,
       is_exchange: bool,
   ) -> None:
       """Idempotent per (date, entity_id) via QuestDB DEDUP UPSERT KEYS."""
   ```
   Raises `psycopg.Error` on transport failure. Caller (producer) MUST wrap each call in try/except per FR-002 + FR-003.

3. **`webhook_payload.md`** — Aggregated Discord webhook JSON:
   ```json
   {
     "content": ":rotating_light: entity_flows_daily QuestDB write failed for 2026-06-15: 47 rows failed (psycopg.OperationalError)"
   }
   ```
   Exactly one POST per failing run. Payload contains stream name + date + count + exception class only — no per-row detail (that lives in structured ERROR logs per FR-003).

### Quickstart

See [quickstart.md](./quickstart.md). Operator runbook covering:
- Manual smoke: invoke `aggregate_flows()` once, verify QuestDB row count matches DuckDB row count for the target date.
- Rollback: `export SPEC063_QUESTDB_WRITE=0`, `sudo systemctl restart <invoker>`, verify no QuestDB connection opened.
- Re-enable: `unset SPEC063_QUESTDB_WRITE` (default ON), `sudo systemctl restart <invoker>`, verify next run writes both stores.

### Agent Context Update

Skipped. `CLAUDE.md` already documents the QuestDB SSOT direction and the strangler-fig pattern; no per-spec agent context file needed for this scope.

## Strangler-fig Pattern Application — write-side delta vs spec-062 Appendix A

The six steps from `specs/062-aggregator-zero-duckdb/plan.md` Appendix A apply verbatim with the following write-side deltas:

| Step | spec-062 (read-side) | spec-063 (write-side) — delta |
|---|---|---|
| 1. Verify schema parity | DESCRIBE legacy + SHOW COLUMNS target | Same. Discovery confirmed: QuestDB DDL exists at `api/questdb_repository.py:572`, columns match modulo lossless casts (see data-model.md). |
| 2. Migrate one helper at a time | Dual-branch on `*, questdb_reads=False` flag per read helper | **Delta**: env var `SPEC063_QUESTDB_WRITE` instead of a per-call flag. Rationale: write-side has one call site, env var gives operator a runtime toggle without per-call plumbing. |
| 3. Propagate flag through callers | Forward `questdb_reads` kwarg through call graph | **Delta**: no propagation. The env var is read once at the dual-write site. |
| 4. Gate the legacy connection at `main()` | `duckdb_free = args.questdb_reads and args.questdb_only` | **Delta inverted**: legacy DuckDB connection is NEVER gated off in spec-063 — DuckDB is the SSOT. The env var gates the NEW QuestDB connection, not the legacy DuckDB one. |
| 5. Add three test guards | per-helper + source-grep + entrypoint mode | Five guards (a–e) per Constitution II. Source-grep guard verifies the dual-write site exists. |
| 6. Live smoke + 7-day green gate | Single-date run + fuser + verify row in target | Same shape. Manual smoke (no scheduler), verify QuestDB row count parity, then 7-day SC-005 gate by operator polling. |

## Complexity Tracking

*No Constitution violations to justify.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| — | — | — |

## Plan freeze checklist

- [x] Constitution Check PASS (with TDD RED-first commitment explicit)
- [x] research.md outline complete (6 decisions enumerated)
- [x] data-model.md cast table complete (6 columns + ts, all lossless)
- [x] decisions.md: no lossy cast escalation needed; Option A escape hatch NOT triggered (discovery confirmed no disqualifying conditions)
- [x] contracts/ outline complete (3 files)
- [x] Production runtime gap explicitly noted (aggregate_flows invoked only by tests; spec-063 ships code, scheduling deferred to separate spec)
- [x] Hard constraints honoured (no new timer, no extra files outside the 4 enumerated)
