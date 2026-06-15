---
description: "Task list for spec-063 entity_flows_daily QuestDB Producer Pilot"
---

# Tasks: entity_flows_daily QuestDB Producer Pilot

**Input**: Design documents from `/specs/063-entity-flows-daily-questdb/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, decisions.md, quickstart.md

**Tests**: TDD enforced per Constitution Principle II (NON-NEGOTIABLE). Each test task is RED-first — committed and observed to fail before the corresponding implementation lands in a follow-up commit. The five RED guards (a–e) come from the plan Constitution Check.

**Organization**: Tasks grouped by user story per spec.md priority. Implementation phases run RED → GREEN → REFACTOR within each story slice.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers

- **[P]**: Different files, no dependencies → parallelizable
- **[Story]**: Maps to User Story 1–3 in spec.md
- **[RED]** / **[GREEN]**: TDD phase (RED commits a failing test, GREEN commits the minimum implementation to pass it)

## Path Conventions

- Source: `scripts/live/flow_aggregator.py`, `api/questdb_repository.py`
- Tests: `tests/test_flow_aggregator_questdb.py` (new)
- Docs: `specs/063-entity-flows-daily-questdb/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Touch one file at a time so the dependency graph stays clean. No production code yet — just the test file scaffold and the DDL adjustment confirmed during planning.

- [ ] T001 Read `scripts/live/flow_aggregator.py` lines 1–60 and `api/questdb_repository.py` lines 565–600 to confirm the current code state matches the plan discovery. If anything has drifted since 2026-06-15, update plan.md before continuing.
- [ ] T002 Read `specs/063-entity-flows-daily-questdb/contracts/save_entity_flows_daily.md` and `specs/063-entity-flows-daily-questdb/contracts/envvars.md` to anchor the implementation against the contract files (they are the spec of record).
- [ ] T003 Create `tests/test_flow_aggregator_questdb.py` skeleton (imports + module docstring + a single `def test_placeholder(): assert True`). Commit as the first RED file in its own commit — establishes the file for subsequent RED tests to extend.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The save method, the env var parser, and the QuestDB DDL adjustment are foundational for all three user stories. RED-first per Constitution II.

**⚠️ CRITICAL**: All three user stories depend on this phase.

### RED phase — failing tests committed first

- [ ] T004 [RED] Add `test_should_write_questdb_parser_table` in `tests/test_flow_aggregator_questdb.py` covering all rows of the env var behaviour table in `contracts/envvars.md`. Test imports `_should_write_questdb` from `scripts.live.flow_aggregator`. Commit; verify it fails with `ImportError` (the helper does not exist yet).
- [ ] T005 [RED] Add `test_save_entity_flows_daily_signature` in `tests/test_flow_aggregator_questdb.py` that imports `save_entity_flows_daily` from `api.questdb_repository` and asserts the signature matches `contracts/save_entity_flows_daily.md` (keyword-only args: `entity_id, date, inflow_btc, outflow_btc, netflow_btc, is_exchange`; return type `None`). Use `inspect.signature`. Commit; verify it fails with `ImportError`.
- [ ] T006 [RED] Add `test_entity_flows_daily_dedup_ddl_applied` in `tests/test_create_tables_ddl.py` (extends spec-061 ddl test) asserting that after `create_tables_if_not_exist()` runs against a live QuestDB, `tables()` reports `entity_flows_daily.walEnabled == true` and `entity_flows_daily.dedup == true`. Mark `@pytest.mark.integration` and skip if `QUESTDB_PG_HOST` unset. Commit; verify it fails (DEDUP not yet enabled).

### GREEN phase — minimum implementation to pass

- [ ] T007 [GREEN] Implement `_should_write_questdb()` helper at the top of `scripts/live/flow_aggregator.py` per `contracts/envvars.md`. Commit; verify T004 passes.
- [ ] T008 [GREEN] Implement `save_entity_flows_daily(*, entity_id, date, inflow_btc, outflow_btc, netflow_btc, is_exchange) -> None` as a sync module-level function in `api/questdb_repository.py`, modelled on `save_mvrv_daily`. Use `_open_pg_sync()`. The SQL is `INSERT INTO entity_flows_daily (entity_id, date, inflow_btc, outflow_btc, netflow_btc, is_exchange, ts) VALUES (%s, %s, %s, %s, %s, %s, %s)`; `ts` is `datetime.utcnow()`. Commit; verify T005 passes.
- [ ] T009 [GREEN] Inside `create_tables_if_not_exist()` in `api/questdb_repository.py`, immediately after the existing `CREATE TABLE IF NOT EXISTS entity_flows_daily` block, add two `try/except` ALTER statements: `ALTER TABLE entity_flows_daily SET TYPE WAL` and `ALTER TABLE entity_flows_daily DEDUP ENABLE UPSERT KEYS(date, entity_id)`. Both wrapped to swallow `psycopg.errors.*` for idempotency. Commit; verify T006 passes against live QuestDB.

---

## Phase 3: User Story 1 — `entity_flows_daily` consumer-facing stream stops being empty (P1)

**Story goal**: After `aggregate_flows()` runs, both DuckDB and QuestDB contain the same row set for `entity_flows_daily`. The stream transitions from MISSING to OK on `/v1/streams/health`.

**Independent test**: Invoke `aggregate_flows()` against a populated DuckDB. Query QuestDB `SELECT count(*) FROM entity_flows_daily WHERE date = current_date()` and assert the count equals the DuckDB count. `/v1/streams/health` reports OK.

### RED phase — guards (b) and (e) from plan Constitution Check

- [ ] T010 [RED] [US1] Add `test_dual_write_payload_byte_identity` in `tests/test_flow_aggregator_questdb.py`: patch `save_entity_flows_daily` to record calls, invoke `aggregate_flows()` against a fixture DuckDB containing 3 known entities × 1 day, assert each call's kwargs exactly match the row produced by the SELECT (entity_id, date, inflow_btc, outflow_btc, netflow_btc, is_exchange). Commit; verify it fails (dual-write block does not exist yet).
- [ ] T011 [RED] [US1] Add `test_cast_contract_matches_data_model` in `tests/test_flow_aggregator_questdb.py`: assert that for each known row, the value passed to `save_entity_flows_daily` for `date` is a `datetime.date` (not a string, not a datetime), `entity_id` is `str`, `*_btc` are `float`, `is_exchange` is `bool`. Commit; verify it fails.

### GREEN phase

- [ ] T012 [GREEN] [US1] Inside `aggregate_flows()` in `scripts/live/flow_aggregator.py`, after the existing `INSERT OR REPLACE INTO entity_flows_daily` block at line ~121, add the dual-write block per `contracts/save_entity_flows_daily.md` pseudocode: read back via `SELECT entity_id, date, inflow_btc, outflow_btc, netflow_btc, is_exchange FROM entity_flows_daily WHERE date = current_date`, iterate, call `save_entity_flows_daily(...)` per row. Gated by `_should_write_questdb()`. Commit; verify T010 and T011 pass.

### Live verification

- [ ] T013 [US1] Run the quickstart manual smoke (Step 1–4 of `quickstart.md`) against the host QuestDB. Confirm row-count parity between DuckDB and QuestDB for `current_date`. Record the duration and row count in a smoke log at `validation/reports/$(date +%F)_spec063_smoke.md`.

---

## Phase 4: User Story 2 — Strangler-fig template proves itself on a real Phase 2 producer (P2)

**Story goal**: The reviewer can validate the spec-063 PR against the spec-062 Appendix A checklist in under 30 minutes. Every checklist item maps to a code change in the diff. Lessons feed back into Appendix A within one revision.

**Independent test**: Walk a reviewer through the PR with spec-062 Appendix A open side-by-side. Each of the six steps either has a code change OR an explicit decision in `decisions.md`. No silent gaps.

### RED phase — guards (a) and (c) — env toggle + DuckDB integrity

- [ ] T014 [RED] [US2] Add `test_env_toggle_gates_questdb_connection_open` in `tests/test_flow_aggregator_questdb.py`: monkeypatch `os.environ["SPEC063_QUESTDB_WRITE"]="0"`, patch `api.questdb_repository._open_pg_sync` to raise `AssertionError("must not be called")`, invoke `aggregate_flows()`, assert NO `_open_pg_sync` call was attempted. Commit; verify it fails (env-var gating not implemented yet).
- [ ] T015 [RED] [US2] Add `test_questdb_failure_does_not_roll_back_duckdb` in `tests/test_flow_aggregator_questdb.py`: monkeypatch env var ON, patch `save_entity_flows_daily` to raise `psycopg.OperationalError`, invoke `aggregate_flows()`. Assert: (a) the function returns without raising; (b) the DuckDB row count for `entity_flows_daily` matches the count from a pre-spec-063 run on the same fixture; (c) the DuckDB transaction was committed (verifiable by re-opening the connection and SELECTing). Commit; verify it fails.

### GREEN phase

- [ ] T016 [GREEN] [US2] Refine the dual-write block in `scripts/live/flow_aggregator.py` (already added in T012) to wrap the per-row `save_entity_flows_daily` call in `try/except psycopg.Error`. On exception: append `(entity_id, date, exception_class)` to a `failed_rows` list and emit a structured ERROR log per FR-003. Commit; verify T014 and T015 pass.

### Documentation

- [ ] T017 [US2] In `specs/063-entity-flows-daily-questdb/decisions.md`, append a "Lessons surfaced" section enumerating any deltas observed during implementation that differ from spec-062 plan Appendix A's six-step pattern. If no deltas, write "No deltas observed; Appendix A applies verbatim to write-side migration of a sync producer." Commit.

---

## Phase 5: User Story 3 — Rollback path is callable without code revert (P3)

**Story goal**: Operator can disable the QuestDB write half via env var. The DuckDB SSOT is untouched. Existing QuestDB rows from previous runs are NOT deleted (forward-only rollback).

**Independent test**: Set `SPEC063_QUESTDB_WRITE=0`, restart the producer, invoke `aggregate_flows()`. Assert no QuestDB connection opened (already in T014). Then query QuestDB for any pre-existing rows and confirm they remain.

### RED phase — guard (d) — aggregated webhook + forward-only rollback

- [ ] T018 [RED] [US3] Add `test_aggregated_webhook_fires_exactly_once_per_failing_run` in `tests/test_flow_aggregator_questdb.py`: simulate 47 row failures spanning a single date, patch `urllib.request.urlopen`, invoke `aggregate_flows()`, assert `urlopen` was called exactly once, parse the JSON body, regex-match the payload against `^:rotating_light: entity_flows_daily QuestDB write failed for \d{4}-\d{2}-\d{2}: 47 rows failed \([\w\.]+\)$`. Commit; verify it fails.
- [ ] T019 [RED] [US3] Add `test_webhook_NOT_fired_on_successful_run` in `tests/test_flow_aggregator_questdb.py`: simulate all rows succeeding, patch `urllib.request.urlopen`, invoke `aggregate_flows()`, assert `urlopen` was NOT called. Commit; verify it fails (no helper yet wired).
- [ ] T020 [RED] [US3] Add `test_rollback_OFF_does_not_delete_pre_existing_questdb_rows` in `tests/test_flow_aggregator_questdb.py`: seed QuestDB `entity_flows_daily` with 2 known rows via direct INSERT, set `SPEC063_QUESTDB_WRITE=0`, invoke `aggregate_flows()`, assert the 2 pre-existing rows still exist in QuestDB unchanged. Mark `@pytest.mark.integration`. Commit; verify it fails (no env-var gating yet — but T014 GREEN already lands this, so T020 may turn green simultaneously with T016).

### GREEN phase

- [ ] T021 [GREEN] [US3] Implement `_post_aggregated_webhook(target_date, failed_rows)` helper in `scripts/live/flow_aggregator.py` per `contracts/webhook_payload.md`. Use `urllib.request.urlopen` with 3s timeout; swallow webhook errors per spec-062 FR-012. Commit; verify T018 and T019 pass.
- [ ] T022 [GREEN] [US3] In `scripts/live/flow_aggregator.py`, at the end of the dual-write block (after the `for row in rows:` loop), call `_post_aggregated_webhook(...)` iff `failed_rows` is non-empty. Wrap in a `try/except` so a webhook failure does not affect the function exit code. Commit; verify T018 and T019 remain green after integration.

### Live verification

- [ ] T023 [US3] Run the quickstart rollback runbook (Step 1–3 of `quickstart.md` Rollback section): set `SPEC063_QUESTDB_WRITE=0`, restart, invoke `aggregate_flows()`, verify no QuestDB connection opened (journal grep), verify pre-existing rows untouched. Record the verification in the smoke report.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Observability, source-grep guards (FR-008/FR-009), final integration smoke, PR-ready state.

### Source-grep guards

- [ ] T024 Add `test_dual_write_site_exists_in_source` in `tests/test_flow_aggregator_questdb.py`: `assert "save_entity_flows_daily" in Path("scripts/live/flow_aggregator.py").read_text()` and `assert "_should_write_questdb" in Path("scripts/live/flow_aggregator.py").read_text()`. Catches a future refactor that silently removes the QuestDB write half (FR-009 guard).
- [ ] T025 Add `test_duckdb_write_path_preserved` in `tests/test_flow_aggregator_questdb.py`: `assert "INSERT OR REPLACE INTO entity_flows_daily" in Path("scripts/live/flow_aggregator.py").read_text()`. Catches a future refactor that removes the DuckDB write half before the legacy-removal follow-up spec authorises it (FR-009 guard).

### Observability

- [ ] T026 At the end of `aggregate_flows()` in `scripts/live/flow_aggregator.py`, emit the structured INFO log per FR-004: `spec-063 entity_flows_daily dual-write success: date=... duration_s=... rows_written_duckdb=... rows_written_questdb=...`. Include both counts even when env var OFF (rows_written_questdb=0). Commit; spot-check by running the function.

### Final verification

- [ ] T027 Run the full test file: `uv run pytest tests/test_flow_aggregator_questdb.py -q`. All tasks T004, T005, T010, T011, T014, T015, T018, T019, T024, T025 must pass. The two integration-marked tests (T006, T020) require live QuestDB.
- [ ] T028 Run `ruff check scripts/live/flow_aggregator.py api/questdb_repository.py tests/test_flow_aggregator_questdb.py`. Resolve any findings. Commit fixes if any.
- [ ] T029 Live end-to-end smoke from `quickstart.md`: manual smoke success path + rollback verification + re-enable. Capture the full transcript into `validation/reports/$(date +%F)_spec063_smoke.md`.
- [ ] T030 Update PR description with: link to `quickstart.md`, summary of D1–D6 from `decisions.md`, link to smoke report from T029, confirmation that all spec-062 Appendix A six steps map to tasks (cross-reference in `decisions.md` T017 lessons section).

---

## Dependencies

```
Phase 1 Setup (T001 → T002 → T003)
    └── Phase 2 Foundational
          T004,T005,T006 (RED — parallel within file but same file so serial commits)
              └── T007,T008,T009 (GREEN — serial commits, different files OK to parallel)
                    └── Phase 3 US1 (T010,T011 RED → T012 GREEN → T013 smoke)
                        Phase 4 US2 (T014,T015 RED → T016 GREEN → T017 docs)
                        Phase 5 US3 (T018,T019,T020 RED → T021,T022 GREEN → T023 smoke)
                              └── Phase 6 Polish (T024–T030)
```

All three user stories depend on Phase 2 completion. Within each story, RED tests must commit before GREEN implementation. Phase 6 depends on all stories.

## Parallel Execution Examples

### Within Phase 2 (different files)

T008 and T009 touch different code regions of `api/questdb_repository.py`. They could in principle be done in parallel, but committing in one file at a time keeps the audit trail simpler. **No [P] markers.**

### Within Phase 3 / 4 / 5

Each story phase has only one source file (`scripts/live/flow_aggregator.py`) being modified across GREEN tasks; tests are all in one new file. **No [P] markers within stories.**

### Across stories

Phases 3, 4, 5 could theoretically progress in parallel after Phase 2 — but they all touch the same `aggregate_flows()` function body. Recommend serial execution **with explicit commits per story** for review clarity. No [P] markers across stories.

## Implementation Strategy

### MVP scope

User Story 1 alone is the MVP — it delivers the dual-write that unblocks the consumer-facing stream. US2 and US3 are pattern-validation and rollback affordances that ride along; they're not strictly required for the consumer to see rows in QuestDB.

A minimum acceptable shipping bundle would be:
- Phase 1 + Phase 2 + Phase 3 + T013 smoke → consumer sees rows.
- Phase 4 + Phase 5 + Phase 6 → operator + reviewer experience hardened.

But because Phase 4 (US2) is mostly docs + 2 tests, and Phase 5 (US3) is the rollback toggle that the user explicitly required (Clarify Q1), the recommended bundle is **all phases together**.

### Incremental delivery

1. Phase 1 setup commits (1 PR commit per task)
2. Phase 2 RED commits (3 commits, one per RED guard)
3. Phase 2 GREEN commits (3 commits)
4. Phase 3 RED → GREEN → smoke (4 commits)
5. Phase 4 RED → GREEN → docs (4 commits)
6. Phase 5 RED → GREEN → smoke (6 commits)
7. Phase 6 polish (~7 commits)

Estimated 26–28 commits total. Branch is `063-entity-flows-daily-questdb`. Final PR `063 → main` after smoke green.

### Task count summary

| Phase | Total | RED | GREEN | Docs/Smoke |
|---|---|---|---|---|
| 1 — Setup | 3 | 0 | 0 | 3 |
| 2 — Foundational | 6 | 3 | 3 | 0 |
| 3 — US1 | 4 | 2 | 1 | 1 |
| 4 — US2 | 4 | 2 | 1 | 1 |
| 5 — US3 | 6 | 3 | 2 | 1 |
| 6 — Polish | 7 | 2 | 1 | 4 |
| **Total** | **30** | **12** | **8** | **10** |

12 RED tasks committed before any GREEN task — Constitution II TDD discipline observable in git history.
