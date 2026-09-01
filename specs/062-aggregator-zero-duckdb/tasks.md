---
description: "Task list for spec-062 Aggregator Zero-DuckDB Read Path"
---

# Tasks: Aggregator Zero-DuckDB Read Path

**Input**: Design documents from `/specs/062-aggregator-zero-duckdb/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Test tasks INCLUDED — spec FR-008 and FR-009 require CI test guards. Constitution Principle II (TDD) applies to the cleanup tasks that remain open.

**Organization**: Tasks grouped by user story per spec.md priority. Implementation phases (T001–T020) are marked `[DONE]` — already shipped in commit `6f27cbb`. Open phases (T021+) cover the seven-day green gate, the strangler-fig discoverability surface, and the cleanup follow-up.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers

- **[P]**: Different files, no dependencies → parallelizable
- **[Story]**: Maps to User Story 1–3 in spec.md
- **[DONE]**: Already implemented in commit `6f27cbb` — task retained for traceability

## Path Conventions

- Source: `scripts/metrics/`, `api/`
- Tests: `tests/`
- Docs: `docs/`, `specs/062-aggregator-zero-duckdb/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project state prerequisites for the strangler-fig pattern.

- [x] T001 [DONE] Verify QuestDB `utxo_lifecycle` populated (>170 M rows) — confirmed during spec-061 Phase 1 sign-off.
- [x] T002 [DONE] Verify QuestDB `utxo_snapshots` schema exists (rows may be 0) — established by spec-061 Phase 1.5-v2 DDL.
- [x] T003 [DONE] Verify `api.questdb_repository._open_pg_sync` is callable from synchronous Python — confirmed by Phase 1.5-v2 writers using it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core read-path infrastructure shared across all user stories.

**⚠️ CRITICAL**: All three user stories depend on this phase.

- [x] T004 [DONE] Migrate `get_blocks_for_date` to dual-branch with `questdb_reads` flag in `scripts/metrics/calculate_daily_metrics.py` (already shipped by spec-061 Phase 1.5-v2; spec-062 inherits).
- [x] T005 [DONE] Migrate `get_price_for_date` to dual-branch with `questdb_reads` flag in `scripts/metrics/calculate_daily_metrics.py` (shipped by spec-061 Phase 1.5-v2).
- [x] T006 [DONE] Confirm QuestDB `block_heights` and `daily_prices` populated by Phase 1.5-v2 timers (`utxoracle-block-heights-catchup.timer`, `utxoracle-daily-prices-refresh.timer`).

---

## Phase 3: User Story 1 — Daily metrics produced without touching DuckDB (P1)

**Story goal**: Aggregator runs end-to-end against QuestDB only when `--questdb-reads --questdb-only` set; zero DuckDB file holders.

**Independent test**: `uv run python -m scripts.metrics.calculate_daily_metrics --date YYYY-MM-DD --questdb-reads --questdb-only` succeeds while `fuser data/utxoracle.duckdb` reports no aggregator holders, and the corresponding row appears in QuestDB `mvrv_daily`.

### Implementation (already shipped)

- [x] T007 [DONE] [US1] Migrate `calculate_daily_realized_cap(conn, as_of_block, *, questdb_reads)` in `scripts/metrics/calculate_daily_metrics.py` — QuestDB branch reads `utxo_lifecycle` via `_open_pg_sync`.
- [x] T008 [DONE] [US1] Migrate `calculate_daily_sopr(conn, start_block, end_block, *, questdb_reads)` in `scripts/metrics/calculate_daily_metrics.py` — primary + fallback JOIN with `block_heights` + `daily_prices`.
- [x] T009 [DONE] [US1] Migrate `calculate_cointime_daily(conn, as_of_block, *, questdb_reads)` in `scripts/metrics/calculate_daily_metrics.py` — two SUMs over `utxo_lifecycle`.
- [x] T010 [DONE] [US1] Migrate inline supply query inside `calculate_daily_metrics` in `scripts/metrics/calculate_daily_metrics.py` to use `utxo_lifecycle` when `questdb_reads=True`.
- [x] T011 [DONE] [US1] Propagate `questdb_reads` kwarg through `calculate_daily_metrics(target_date, conn, *, questdb_reads)` call graph in `scripts/metrics/calculate_daily_metrics.py`.
- [x] T012 [DONE] [US1] Gate `duckdb.connect()` behind `duckdb_free = args.questdb_reads and args.questdb_only` in `main()` of `scripts/metrics/calculate_daily_metrics.py` — `conn` is `None` when both flags set; `finally` guard handles the close.
- [x] T013 [DONE] [US1] Handle `--recalculate` path with `_open_pg_sync` to read `daily_prices` count when `duckdb_free=True` in `scripts/metrics/calculate_daily_metrics.py`.

### Tests (FR-008, FR-009)

- [x] T014 [DONE] [P] [US1] `test_realized_cap_can_read_questdb` in `tests/test_calculate_daily_metrics_questdb.py` — asserts QuestDB branch never touches the DuckDB mock.
- [x] T015 [DONE] [P] [US1] `test_sopr_can_read_questdb` in `tests/test_calculate_daily_metrics_questdb.py` — primary-branch QuestDB read guard.
- [x] T016 [DONE] [P] [US1] `test_cointime_can_read_questdb` in `tests/test_calculate_daily_metrics_questdb.py` — two-shot fetchone guard.
- [x] T017 [DONE] [P] [US1] `test_aggregator_never_opens_duckdb_under_dual_flags` in `tests/test_calculate_daily_metrics_questdb.py` — source-grep guard for `duckdb_free` in `main()`.

### Live verification (SC-001, SC-002, SC-004)

- [x] T018 [DONE] [US1] Run aggregator for 2026-06-04 with `--questdb-reads --questdb-only`; confirm row present in QuestDB `mvrv_daily` and `fuser data/utxoracle.duckdb` empty. Recorded duration: ~25 s on 170 M rows.

---

## Phase 4: User Story 2 — Legacy DuckDB callers still work unchanged (P2)

**Story goal**: Pre-spec-062 callers (tests, ad-hoc tooling) continue to work without code changes during the transition window.

**Independent test**: The seven pre-existing tests in `tests/test_calculate_daily_metrics_questdb.py` pass without modification when `questdb_reads` is False.

- [x] T019 [DONE] [US2] Preserve legacy DuckDB else-branch in each of the five migrated helpers in `scripts/metrics/calculate_daily_metrics.py` and `scripts/metrics/mvrv_variants.py`. Add `assert conn is not None` guards on the else-side (silences pyright, zero runtime cost).
- [x] T020 [DONE] [US2] Confirm 7 pre-existing tests in `tests/test_calculate_daily_metrics_questdb.py` still pass (T020 was the validation run after T019).

---

## Phase 5: User Story 3 — Forward-compat with Phase 2 producers (P3)

**Story goal**: When Phase 2 populates `utxo_snapshots`, `mvrv_z_rbn` starts being reported automatically — no code change needed in the aggregator.

**Independent test**: Insert ≥30 synthetic rows into QuestDB `utxo_snapshots`; next aggregator run produces non-null `mvrv_z_rbn` with zero code changes.

- [x] T021 [DONE] [US3] Migrate `get_market_cap_history_all_time(conn, max_block_height, *, questdb_reads)` in `scripts/metrics/mvrv_variants.py` to dual-branch (lazy import of `_open_pg_sync` to avoid import cycle with `api/`).
- [x] T022 [DONE] [US3] Propagate `questdb_reads` through `calculate_both_mvrv_z(..., *, questdb_reads)` in `scripts/metrics/mvrv_variants.py`.
- [x] T023 [DONE] [P] [US3] `test_mvrv_variants_can_read_questdb` in `tests/test_calculate_daily_metrics_questdb.py` — guards the `utxo_snapshots` QuestDB branch and asserts the empty-table case yields `[]`.
- [x] T024 [DONE] [US3] Verify empty-table behaviour in live smoke: aggregator run for 2026-06-04 emits `mvrv_z_rbn = None` and persists `mvrv_daily` row with the null/absent column — confirmed in T018 output.

---

## Phase 6: Discoverability & Documentation (FR-010, SC-005)

**Purpose**: The strangler-fig pattern must be discoverable and reusable by the seven Phase 2 producer specs without re-derivation.

- [x] T025 [DONE] Document the canonical strangler-fig migration pattern in Appendix A of `specs/062-aggregator-zero-duckdb/plan.md` (six steps + anti-patterns + Phase 2 checklist).
- [x] T026 [DONE] Create `docs/PATTERNS.md` as a one-line cross-link index pointing at the plan Appendix A. No content duplication.
- [ ] T027 Cross-reference the pattern from `docs/ARCHITECTURE.md` "Migration patterns" section if/when that section exists; otherwise defer until the next ARCHITECTURE.md update.

---

## Phase 6.5: Analyze Remediation (FR-006, FR-011, FR-012, FR-013, FR-002, H4)

**Purpose**: Close gaps surfaced by `/speckit.analyze` 2026-06-05 report. These tasks address CRITICAL (C1, C2) and HIGH (H1, H2, H3, H4) findings.

- [x] T044 [DONE] [P] [US1] FR-011 implemented in `scripts/metrics/calculate_daily_metrics.py::_run_single_date`: measures wall-clock duration, counts metric rows written, emits structured INFO `spec-062 aggregator success: date=... duration_s=... rows_written=...` on success and structured ERROR with `exc_info=True` on failure.
- [x] T045 [DONE] [P] [US1] FR-012 implemented in `_post_discord_failure`: POSTs one-line payload to `DISCORD_WEBHOOK_URL` on failure only; 3-second timeout; webhook errors swallowed and logged at WARNING so they cannot mask the original exception.
- [x] T046 [DONE] [P] [US1] Tests `test_failure_emits_discord_webhook` + `test_success_does_not_emit_discord_webhook` in `tests/test_calculate_daily_metrics_questdb.py` — webhook fires exactly once on failure, never on success.
- [x] T047 [DONE] [P] [US1] `test_questdb_unreachable_fails_fast` covers FR-006: patches `_open_pg_sync` to raise `ConnectionError`, asserts propagation from `calculate_daily_realized_cap(questdb_reads=True)` and `duckdb_conn.execute.assert_not_called()`.
- [x] T048 [DONE] [P] [US1] `test_concurrent_runs_converge_via_dedup` covers FR-013: two `_persist_to_questdb` calls with identical metrics emit byte-identical save_* arguments (6 calls total, pairs equal).
- [x] T049 [DONE] Constitution Check Principle II row in plan.md now records post-hoc TDD caveat for spec-062 and the RED→GREEN→REFACTOR requirement for the seven Phase 2 producer specs.
- [x] T050 [DONE] plan.md "Source Code" section explicitly annotates `utxoracle-daily-aggregator.{service,timer}` ownership (spec-061) and consumption (spec-062 via `--questdb-reads --questdb-only`).
- [x] T051 [DONE] Live re-smoke 2026-06-11: failure path with `QUESTDB_PG_PORT=9999` produced `psycopg.OperationalError: Connection refused` with no DuckDB fallback (FR-006 satisfied); success path with default QuestDB produced `spec-062 dry-run complete: date=2026-06-04 duration_s=14.17 rows_written=0` (FR-011 satisfied).
- [x] T052 [DONE] Full pytest re-run 2026-06-11 once host memory pressure cleared: **16/16 tests green** in 0.13s. T044–T048 sign-off complete.

---

## Phase 7: Seven-Day Green Production Gate

**Purpose**: Validate the QuestDB read path under production load before legacy-branch removal is even considered.

**Gate**: All seven sub-tasks below MUST report green over seven consecutive days before T035 (legacy removal) becomes eligible. This phase is observation-only — no code changes.

**Day-0 baseline (2026-06-15)**: PR #9 merged (`12912ef`); service file installed on host with `ExecStart=...calculate_daily_metrics --questdb-reads --questdb-only` + `EnvironmentFile=-.env`. Three Phase 1.5-v2 / spec-062 systemd units verified live via manual trigger:
- `utxoracle-block-heights-catchup.service`: SUCCESS, inserted 85 block_heights rows up to height 953798.
- `utxoracle-daily-prices-refresh.service`: SUCCESS (`Already fresh: start=2026-06-15 end=2026-06-14`).
- `utxoracle-daily-aggregator.service`: SUCCESS, `spec-062 aggregator success: date=2026-06-14 duration_s=98.63 rows_written=3`.

Day-1 observation window opens with the next timer fire at 03:30 WEST on 2026-06-16.

- [ ] T028 Day 1 verification: `journalctl -u utxoracle-daily-aggregator.service --since "1 day ago" -p err` returns zero ERROR lines for the daily run.
- [ ] T029 Day 1 verification: `/v1/streams/health` reports `mvrv_daily`, `nupl_daily`, `realized_cap_daily` all OK with `stale_seconds` < SLA.
- [ ] T030 Day 1 verification: `fuser data/utxoracle.duckdb` immediately after the systemd timer fires reports no aggregator-attributable holders.
- [ ] T031 Day 7 verification (repeat T028 over a rolling seven-day window): zero ERROR lines.
- [ ] T032 Day 7 verification (repeat T029): all three daily tables green every day.
- [ ] T033 Day 7 verification (repeat T030): aggregator never opened the DuckDB file across seven runs.
- [ ] T034 Day 7 sign-off: commit a verification report at `validation/reports/YYYY-MM-DD_spec062_seven_day_gate.md` summarising the above and authorising Phase 8.

---

## Phase 8: Legacy Cleanup (Follow-Up Spec Trigger)

**Purpose**: Once Phase 7 gate is green, the DuckDB else-branches become removable. This phase only authorises the work; the actual removal is a separate spec.

- [ ] T035 Open follow-up spec `specs/06X-aggregator-duckdb-removal/` that (a) deletes the five DuckDB else-branches in `scripts/metrics/calculate_daily_metrics.py` and `scripts/metrics/mvrv_variants.py`, (b) removes the `--questdb-reads` flag (becomes implicit), (c) updates `main()` to assume `duckdb_free=True` unconditionally, (d) deletes the legacy DuckDB tests, (e) updates `quickstart.md`. Trigger: Phase 7 gate green.
- [ ] T036 Decommission `data/utxoracle.duckdb` from the aggregator runtime path — remove from `--db-path` default, remove from `EnvironmentFile` of `utxoracle-daily-aggregator.service`. Trigger: T035 merged.

---

## Phase 9: Phase 2 Producer Application (Out of Scope for spec-062)

**Purpose**: Track that the strangler-fig pattern is being applied to the seven Phase 2 producers. These are NOT spec-062 deliverables; they are listed here only to confirm the pattern from this spec is being consumed downstream.

- [ ] T037 [P] Phase 2 spec for `entity_flows_daily` producer (pilot — first application of the pattern to validate it scales).
- [ ] T038 [P] Phase 2 spec for `mempool_predictions` producer.
- [ ] T039 [P] Phase 2 spec for `net_flow_metrics` producer.
- [ ] T040 [P] Phase 2 spec for `backtest_whale_signals` producer.
- [ ] T041 [P] Phase 2 spec for `price_analysis` producer.
- [ ] T042 [P] Phase 2 spec for `utxo_snapshots` producer (unblocks `mvrv_z_rbn`).
- [ ] T043 [P] Phase 2 cleanup spec for residual `utxo_lifecycle_full` reader references in unrelated modules.

---

## Dependencies

```
Phase 1 (Setup, DONE)
  └── Phase 2 (Foundational, DONE)
        └── Phase 3 (US1, DONE) ─┐
            Phase 4 (US2, DONE) ─┼── Phase 6 (Docs, DONE except T027)
            Phase 5 (US3, DONE) ─┘
                                  └── Phase 7 (Seven-day gate, OPEN)
                                        └── Phase 8 (Cleanup, blocked by T034)
                                              └── (legacy DuckDB removal — separate spec)

Phase 9 (Phase 2 producer applications) — independent of spec-062 cleanup; depends only on Phase 6 docs being in place.
```

User Story 1, 2, 3 are independent — each was implementable in isolation. They were shipped together in commit `6f27cbb` because they touched the same source files; the dependency was file-level, not logical.

## Parallel Execution Examples

### Phase 3 tests (already shipped, retained for pattern reference)

All four guard tests landed in separate `def test_...` blocks of the same file. Per the [P] rule ("different files only"), they did NOT carry [P] in this list:

```
T014 → tests/test_calculate_daily_metrics_questdb.py (same file as T015/T016/T017)
T015 → tests/test_calculate_daily_metrics_questdb.py (same)
T016 → tests/test_calculate_daily_metrics_questdb.py (same)
T017 → tests/test_calculate_daily_metrics_questdb.py (same)
```

The [P] markers on T014–T017 indicate they are logically independent (each tests a separate helper); they would be parallelizable IF moved to separate files. Kept as a single file for cohesion.

### Phase 9 Phase 2 specs (genuinely parallel)

T037–T043 target seven distinct spec directories and seven distinct producer modules. All seven can be drafted in parallel by different agents/contributors:

```
Agent A: T037 specs/063-entity-flows-daily-producer/ → scripts/metrics/entity_flows_daily_producer.py
Agent B: T042 specs/064-utxo-snapshots-producer/    → scripts/metrics/utxo_snapshots_producer.py
Agent C: T038 specs/065-mempool-predictions-producer/ → ...
...
```

The pilot pattern (Phase 2 first stream) should land before the other six start, so the canonical pattern in spec-062 plan Appendix A gets validated before being replicated 6x.

## Implementation Strategy

### MVP scope

User Story 1 alone IS the MVP — it delivers the zero-DuckDB read path that closes the SPOF. User Stories 2 and 3 are non-regression / forward-compat guarantees that ride along.

The MVP is already shipped (commit `6f27cbb`). spec-062's open work is Phase 7 (verify it stays green) and Phase 8 (clean up the legacy fallback once verified).

### Incremental delivery

1. ✅ MVP (US1 + US2 + US3) — landed.
2. ⏳ Seven-day green gate (Phase 7) — observation-only, ~7 days elapsed.
3. ⏳ Legacy cleanup follow-up spec (Phase 8) — blocked by T034.
4. ⏳ Pattern propagation (Phase 9) — independent, can begin immediately using the canonical pattern in plan Appendix A.

### Task count summary

| Phase | Total | Done | Open |
|---|---|---|---|
| 1 — Setup | 3 | 3 | 0 |
| 2 — Foundational | 3 | 3 | 0 |
| 3 — US1 | 12 | 12 | 0 |
| 4 — US2 | 2 | 2 | 0 |
| 5 — US3 | 4 | 4 | 0 |
| 6 — Discoverability | 3 | 2 | 1 (T027) |
| 6.5 — Analyze remediation | 9 | 9 | 0 (T044–T052 all done) |
| 7 — Seven-day gate | 7 | 0 | 7 |
| 8 — Cleanup | 2 | 0 | 2 |
| 9 — Phase 2 propagation | 7 | 0 | 7 |
| **Total** | **52** | **35** | **17** |

35/52 done (67 %). Remaining 17 split: 7 time-gated (Phase 7), 10 scope-deferred (Phases 8–9 + T027).
