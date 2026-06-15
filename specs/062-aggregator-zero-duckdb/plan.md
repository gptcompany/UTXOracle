# Implementation Plan: Aggregator Zero-DuckDB Read Path

**Branch**: `062-aggregator-zero-duckdb` | **Date**: 2026-06-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/062-aggregator-zero-duckdb/spec.md`
**Status**: Retroactive plan — implementation already shipped in commit `6f27cbb`. Plan documents the design as built so the strangler-fig pattern can be reused by the seven Phase 2 producers.

## Summary

The daily metrics aggregator (`scripts/metrics/calculate_daily_metrics.py`, `scripts/metrics/mvrv_variants.py`) historically opened the DuckDB file `data/utxoracle.duckdb` to read `utxo_lifecycle_full` and `utxo_snapshots`. Under contention with the live wave1 materializer's writer lock, this was a SPOF for the daily window. spec-061 Phase 1.5-v2 had already moved the source freshness producers (`block_heights`, `daily_prices`) off DuckDB; this plan closes the remaining read-side gap.

Approach: strangler-fig with an opt-in `--questdb-reads` flag. Each of the five lifecycle/snapshot read helpers gains a QuestDB branch (via `_open_pg_sync` and `utxo_lifecycle` / `utxo_snapshots` tables) that runs in parallel to the legacy DuckDB branch. `main()` gates the DuckDB connection itself behind `not (questdb_reads and questdb_only)`: when both flags are set, `duckdb.connect()` is never called. Two test guards (per-function `duckdb_conn.execute.assert_not_called()` and a source-grep assertion that `main()` supports the `duckdb_free` mode) prevent regression. Discord-webhook-on-failure + structured logs handle observability per Q1; QuestDB `DEDUP UPSERT KEYS(ts)` handles per-date concurrency per Q2.

## Technical Context

**Language/Version**: Python 3.11 (project pinned)
**Primary Dependencies**:
- `duckdb` (legacy read branch only — slated for removal once seven-day green gate clears)
- `psycopg2-binary` via `api.questdb_repository._open_pg_sync` (QuestDB PG-wire reads)
- `questdb` (ILP writes to `mvrv_daily` / `nupl_daily` / `realized_cap_daily`, owned by spec-061)
- No new dependencies introduced by this spec
**Storage**:
- QuestDB host instance on `:9000` (HTTP) / `:8812` (PG-wire) / `:9009` (ILP)
- DuckDB file at `data/utxoracle.duckdb` (legacy, eligible for read-only fallback)
**Testing**: `pytest`, fully mocked QuestDB connection (no live infrastructure needed for unit tests)
**Target Platform**: Linux server (Ubuntu 22.04), single-host deployment
**Project Type**: single (Python module + CLI script driven by systemd timer)
**Performance Goals**: single-date aggregation in <90 s end-to-end against the 170 M-row `utxo_lifecycle` table (SC-001). Smoke run measured ~25 s for 2026-06-04.
**Constraints**:
- ZERO DuckDB file descriptors held by the aggregator process when both flags are set (SC-002)
- 100 % backwards compatibility with the legacy DuckDB callers when the flags are unset (SC-003)
- Atomic per-date persistence: either all five daily rows land or none do (FR-007)
- Fail-fast on QuestDB unreachable — no silent DuckDB fallback (FR-006)
**Scale/Scope**:
- 5 helper functions migrated (`calculate_daily_realized_cap`, `calculate_daily_sopr`, `calculate_cointime_daily`, inline supply query in `calculate_daily_metrics`, `get_market_cap_history_all_time`)
- 2 source files touched (`calculate_daily_metrics.py`, `mvrv_variants.py`)
- 1 test file extended (`tests/test_calculate_daily_metrics_questdb.py` — 5 new guards, 12 total)
- 0 schema changes (consumer tables owned by spec-061)

## Constitution Check

*GATE: PASS — no violations to justify.*

| Principle | Verdict | Evidence |
|---|---|---|
| I. Code Quality & Simplicity (KISS/YAGNI) | PASS | Dual-branch pattern is the minimum viable change to remove the SPOF without churning unrelated callers. No new abstractions, no premature generalization, no new dependencies. The five migrated helpers are still single-purpose. |
| II. Test-First Discipline | PASS (with post-hoc caveat) | 7 pre-existing tests + 5 new spec-062 guards: `test_realized_cap_can_read_questdb`, `test_cointime_can_read_questdb`, `test_sopr_can_read_questdb`, `test_aggregator_never_opens_duckdb_under_dual_flags` (source-grep guard, FR-009), `test_mvrv_variants_can_read_questdb`. All 12 green. Each guard asserts `duckdb_conn.execute.assert_not_called()` in the QuestDB branch (FR-008). **Caveat (analyze H4)**: spec-062 is retroactive — tests were written alongside the implementation in the same commit, not before. True RED→GREEN→REFACTOR was not observed for this spec. The seven Phase 2 producer specs (Phase 9 task list) MUST run proper TDD per the strangler-fig pattern Appendix A Step 5 ("Add three test guards" before live smoke). |
| III. User Experience Consistency | PASS | CLI surface unchanged (`--date`, `--backfill`, `--dry-run`, `--questdb-only` already shipped by spec-061). New flag `--questdb-reads` follows the same naming convention. No frontend / WebSocket / HTML surface touched. |
| IV. Performance Standards | PASS | SC-001 measured: ~25 s for 170 M rows vs 90 s budget. Structured logs (FR-011) include duration; no new RPC pressure on Bitcoin Core (reads come from QuestDB, not the chain). |
| V. Data Privacy & Security | PASS | No external surface added. Reads/writes stay on host-local QuestDB. Discord webhook payload (FR-012) contains date + exception class only — no PII, no UTXO contents, no addresses. Failure traceback stays in journal/stderr, not in webhook. |

**Re-check post-design**: still PASS — no design-phase additions introduce constitutional concerns.

## Project Structure

### Documentation (this feature)

```
specs/062-aggregator-zero-duckdb/
├── spec.md              # Feature spec (Q1/Q2/Q3 clarifications integrated)
├── plan.md              # This file — includes the canonical strangler-fig pattern appendix
├── research.md          # Phase 0 output — what was learned about QuestDB vs DuckDB SQL gaps
├── data-model.md        # Phase 1 output — read/write surface across the 5 helpers
├── quickstart.md        # Phase 1 output — operator runbook
├── contracts/
│   └── aggregator-cli.md  # CLI contract: flags, exit codes, observability surface
├── checklists/
│   └── requirements.md  # Spec quality checklist (all green)
└── tasks.md             # Phase 2 output (created by /speckit.tasks — NOT this command)
```

### Source Code (repository root)

```
scripts/
├── metrics/
│   ├── calculate_daily_metrics.py    # MODIFIED: 5 read helpers + main() now support questdb_reads
│   └── mvrv_variants.py              # MODIFIED: get_market_cap_history_all_time supports questdb_reads
└── bootstrap/
    └── install_phase15_v2_timers.sh  # ALREADY SHIPPED (spec-061) — installs the timer that drives the aggregator

api/
└── questdb_repository.py             # CONSUMED (no changes): provides _open_pg_sync + save_mvrv_daily/save_nupl_daily/save_realized_cap_daily

tests/
└── test_calculate_daily_metrics_questdb.py  # MODIFIED: +5 spec-062 guards, 12 tests total

docs/
└── PATTERNS.md                       # NEW (one-line cross-link to this plan, per FR-010)

# Systemd units in repo root (not directly modified by spec-062):
utxoracle-daily-aggregator.service   # OWNED BY: spec-061 (Phase 1). CONSUMED BY: spec-062
utxoracle-daily-aggregator.timer     #   ExecStart MUST include `--questdb-reads --questdb-only`
                                     #   so the zero-DuckDB property holds at runtime
```

**Structure Decision**: single-project layout, no new module boundaries. The aggregator stays a CLI script driven by a systemd timer. The strangler-fig pattern is a code-level convention applied to the existing `calculate_daily_metrics.py`, not a new architectural layer. This matches Constitution Principle I (no premature abstraction).

## Phase 0 — Research

See [research.md](./research.md). Key findings:

- **QuestDB SQL is PostgreSQL-compatible but with notable gaps**: no `DATE(EPOCH_MS(...))` — replaced with `cast(... as date)`; no `?` placeholders — psycopg2 uses `%s`; `BOOLEAN = FALSE` syntax works on both engines.
- **`utxo_lifecycle` schema matches `utxo_lifecycle_full` 1:1**: all 18 lifecycle columns (creation_block, realized_value_usd, btc_value, is_spent, spent_block, spent_price_usd, age_blocks, etc.) are present and typed identically. No translation layer needed beyond placeholder syntax.
- **`utxo_snapshots` is empty in QuestDB**: schema exists (created by spec-061 Phase 1.5-v2 DDL) but no producer yet. Graceful degradation via `mvrv_z_rbn = None` (FR-005) is the only correct response — fabricating a value would silently change the contract for nautilus_dev.
- **`_open_pg_sync` is the established sync-PG-wire entrypoint** in `api/questdb_repository.py`. Reusing it avoids a new connection abstraction and inherits its env-var configuration (`QUESTDB_PG_HOST`, port, credentials).
- **DEDUP UPSERT KEYS(ts)** on the three consumer tables (already configured by spec-061) makes per-date concurrency a no-op (Q2): two writers producing identical values collapse to a single row.

## Phase 1 — Design & Contracts

### Data Model

See [data-model.md](./data-model.md). Summary:

| Source table | Engine | Helper(s) reading | Action |
|---|---|---|---|
| `utxo_lifecycle` | QuestDB | `calculate_daily_realized_cap`, `calculate_daily_sopr` (primary + fallback), `calculate_cointime_daily`, inline supply query | NEW read branch under `questdb_reads=True` |
| `utxo_lifecycle_full` | DuckDB | same four helpers | LEGACY else-branch, kept callable |
| `utxo_snapshots` | QuestDB | `mvrv_variants.get_market_cap_history_all_time` | NEW read branch (empty during transition) |
| `utxo_snapshots` | DuckDB | same | LEGACY else-branch |
| `block_heights` | QuestDB | `get_blocks_for_date` (already migrated by spec-061) | unchanged from spec-061 |
| `daily_prices` | QuestDB | `get_price_for_date` (already migrated by spec-061), SOPR fallback JOIN | extended JOIN added by spec-062 |
| `mvrv_daily` / `nupl_daily` / `realized_cap_daily` | QuestDB | `persist_metrics_for_target` (already migrated by spec-061) | unchanged from spec-061 |

No schema changes. No new tables. spec-062 is read-side only on the lifecycle/snapshot tables.

### Contracts

See [contracts/aggregator-cli.md](./contracts/aggregator-cli.md). Highlights:

- CLI flags: `--date`, `--backfill`, `--end-date`, `--dry-run`, `--questdb-only`, `--questdb-reads`, `--recalculate`, `--db-path`. The only flag added by spec-062 is `--questdb-reads`; the rest existed.
- `--questdb-reads --questdb-only` together: `main()` does NOT open DuckDB at all (`duckdb_free = True` path).
- `--questdb-reads` alone: reads from QuestDB but writes through both DuckDB and QuestDB (useful for read-side parity verification before flipping the write side).
- Exit codes: 0 on success, non-zero (Python exception propagation) on any failure. No graceful "partial date" exit.
- Observability surface: structured INFO logs to stdout/journal on success; structured ERROR logs with traceback on failure; Discord webhook POST on failure only (FR-012).

### Quickstart

See [quickstart.md](./quickstart.md). Operator runbook.

### Agent Context Update

Skipped: the project already has `CLAUDE.md` and `.claude/` configuration documenting QuestDB SSOT, DuckDB legacy status, and the strangler-fig direction. No new agent-specific file needed for this spec.

---

## Appendix A — Strangler-Fig Migration Pattern (canonical, per FR-010)

> **Purpose**: this appendix is the canonical reusable pattern referenced by spec-062 FR-010 and SC-005. The seven Phase 2 producers (entity_flows_daily, mempool_predictions, net_flow_metrics, backtest_whale_signals, price_analysis, utxo_snapshots, and the utxo_lifecycle_full reader cleanup) MUST follow this pattern verbatim. `docs/PATTERNS.md` cross-links here.

### When to apply

You have a Python module that:

1. Currently reads (and/or writes) some legacy data store (e.g. DuckDB file).
2. Has a candidate replacement (e.g. QuestDB) that holds equivalent or richer data.
3. Has callers (tests, ad-hoc scripts, notebooks) that would break under a hard cut-over.
4. Is on a critical path where lock contention or single-store failures cost a daily window.

If all four match, apply this pattern. If only #1 and #2 match (no live callers, no critical path), a hard cut-over is simpler.

### The six steps

#### Step 1: Verify schema parity

Before touching code, prove the target store has the columns and types the source store has:

```bash
# legacy
duckdb data/utxoracle.duckdb "DESCRIBE <legacy_table>"
# target
curl -s "http://localhost:9000/exec?query=SHOW+COLUMNS+FROM+<target_table>" | jq '.dataset[]'
```

If columns are missing on the target, you need a producer spec FIRST — do not start the strangler-fig migration on top of an incomplete target.

#### Step 2: Migrate one helper at a time

For each function `f(conn, ...)` that reads the legacy store:

```python
def f(
    conn: Optional[duckdb.DuckDBPyConnection],   # was: duckdb.DuckDBPyConnection
    ...,
    *,
    questdb_reads: bool = False,                  # NEW: opt-in flag, default OFF
) -> ReturnType:
    """Docstring — explain both branches."""
    if questdb_reads:
        with _open_pg_sync() as qdb:
            with qdb.cursor() as cur:
                cur.execute(
                    """
                    -- QuestDB SQL: %s placeholders, no DATE(EPOCH_MS(...)) calls,
                    -- table name is the QuestDB table (not _full).
                    SELECT ... FROM <target_table> WHERE ts >= %s AND ts < %s
                    """,
                    (param1, param2),
                )
                result = cur.fetchone()
    else:
        assert conn is not None, "DuckDB conn required when questdb_reads=False"
        result = conn.execute(
            """
            -- Legacy DuckDB SQL: ? placeholders, table name keeps _full suffix.
            SELECT ... FROM <legacy_table> WHERE timestamp >= ? AND timestamp < ?
            """,
            [param1, param2],
        ).fetchone()
    return _normalize(result)
```

Rules:
- `Optional[conn]` and `*, questdb_reads: bool = False` — keyword-only flag prevents accidental positional clobbering.
- `assert conn is not None` in the else-branch — silences pyright on the legacy-only path without runtime cost.
- Identical normalization at the end — same return type, same coercion, same None-handling.
- Identical semantics — the QuestDB SQL must compute the same value as the DuckDB SQL for any input that would be valid for both. If you need a placeholder rewrite (DuckDB `?` → psycopg2 `%s`), do it. If you need a function rewrite (`DATE(EPOCH_MS(...))` → `cast(... as date)`), do it. If you need any other semantic change, stop and write a follow-up spec.

#### Step 3: Propagate the flag through callers

Every function that calls a migrated helper must accept and forward `questdb_reads`:

```python
def calculate_daily_metrics(
    target_date: date,
    conn: Optional[duckdb.DuckDBPyConnection],
    *,
    questdb_reads: bool = False,
) -> dict:
    start_block, end_block = get_blocks_for_date(target_date, conn, questdb_reads=questdb_reads)
    realized_cap = calculate_daily_realized_cap(conn, end_block, questdb_reads=questdb_reads)
    ...
```

Do NOT introduce a thread-local or env var to side-channel the flag. Explicit is better than implicit; the flag belongs in the call graph.

#### Step 4: Gate the legacy connection at `main()`

```python
def main():
    ...
    duckdb_free = args.questdb_reads and args.questdb_only
    conn: Optional[duckdb.DuckDBPyConnection] = (
        None
        if duckdb_free
        else duckdb.connect(args.db_path, read_only=args.questdb_only or args.dry_run)
    )
    try:
        ...
    finally:
        if conn is not None:
            conn.close()
```

This is the only place the legacy connection is acquired. Once `duckdb_free` is True, no `duckdb.connect()` call runs in the entire process. That's the property that `fuser data/<legacy>.duckdb` observably verifies (SC-002).

#### Step 5: Add three test guards

```python
def test_<helper>_can_read_questdb(duckdb_conn):
    """Per-helper assertion: QuestDB branch never touches the DuckDB mock."""
    qdb = _FakeQuestDBConnection((expected_value,))
    with patch("scripts.metrics.<module>._open_pg_sync", return_value=qdb):
        result = helper(duckdb_conn, ..., questdb_reads=True)
    assert result == expected_value
    duckdb_conn.execute.assert_not_called()      # this is the load-bearing line
    query, _ = qdb.cursor_obj.executed[0]
    assert "FROM <target_table>" in query        # no _full suffix
    assert "<legacy_table>" not in query

def test_<entrypoint>_never_opens_duckdb_under_dual_flags():
    """Source-grep guard: main() must support duckdb_free mode."""
    src = Path("scripts/metrics/<module>.py").read_text()
    assert "duckdb_free = args.questdb_reads and args.questdb_only" in src
    assert "if conn is not None:" in src
```

These guards are what catches a future refactor that silently reverts the migration. They are non-negotiable (FR-008, FR-009).

#### Step 6: Live smoke and seven-day gate

Before declaring the helper migrated:

```bash
# 1) Run a single date with both flags.
uv run python -m scripts.metrics.<module> --date YYYY-MM-DD --questdb-reads --questdb-only

# 2) Verify no holders on the legacy file.
fuser data/utxoracle.duckdb   # must be empty (or only unrelated processes)

# 3) Verify the target table received the row.
curl -s "http://localhost:9000/exec?query=SELECT+...+FROM+<output_table>+WHERE+ts='YYYY-MM-DD'" | jq

# 4) Verify the legacy callers still work.
uv run pytest tests/test_<module>_questdb.py -q
```

The DuckDB else-branch stays callable until seven consecutive days of green systemd timer runs on the QuestDB path. Only then is removal of the else-branch a separate-spec candidate.

### Anti-patterns (do not do these)

- **Silent fallback**: if QuestDB fails, do NOT fall back to DuckDB. That hides the SPOF and defeats the purpose of the migration (FR-006).
- **Thread-local flag**: do NOT side-channel `questdb_reads` through a thread-local or env var. The flag belongs in the call graph.
- **Mid-migration schema rename**: do NOT rename `utxo_lifecycle_full` to `utxo_lifecycle` at the DuckDB side to "tidy up". The legacy branch must stay byte-identical to its pre-migration form so it remains a working fallback.
- **Same-PR removal of the else-branch**: do NOT remove the DuckDB branch in the same PR that adds the QuestDB branch. It is what lets you roll back per-caller.
- **Fabricated value when target empty**: do NOT substitute zero, last-known, or computed surrogate when the target table is empty (e.g. `utxo_snapshots` during transition). Report absence (None) explicitly — FR-005, SC-006.

### Phase 2 producer checklist

For each of the seven Phase 2 producers, the migration is complete when:

- [ ] Schema parity verified (Step 1).
- [ ] All read helpers for the stream migrated to dual-branch (Step 2).
- [ ] Flag propagated through the call graph (Step 3).
- [ ] `main()` (or the producer's entrypoint) gates the legacy connection (Step 4).
- [ ] Three test guards added (per-helper + entrypoint, Step 5).
- [ ] Live smoke for one date passes; `fuser` clean; target table received row (Step 6).
- [ ] Systemd timer enabled and running for seven consecutive days without ERROR (gate).
- [ ] `/v1/streams/health` reports the stream as OK for seven consecutive days (gate).

When all eight boxes are checked, the stream is eligible for legacy-branch removal under a separate spec.

---

## Complexity Tracking

*No violations to justify — Constitution Check passed.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| — | — | — |
