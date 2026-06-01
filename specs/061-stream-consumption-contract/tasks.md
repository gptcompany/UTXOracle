---
description: "Task list for spec-061 — Stream Consumption Contract for nautilus_dev"
---

# Tasks: Stream Consumption Contract for nautilus_dev

**Input**: Design documents in `/media/sam/1TB/UTXOracle/specs/061-stream-consumption-contract/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`

**Tests**: REQUIRED — constitutional principle II is non-negotiable TDD. Every task that ships code has a paired RED test task that MUST be written and fail before the implementation task starts.

**Organization**: by user story. Phase 1 (Setup) + Phase 2 (Foundational) precede everything. Phases 3–6 map to US1–US4 in spec.md priority order (P1, P1, P2, P2). Phase 7 closes out cross-cutting concerns.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers

- **[P]**: Different file, no dependency on incomplete tasks → safe to parallelize.
- **[Story]**: US1 / US2 / US3 / US4 — maps to spec.md user stories. Setup / Foundational / Polish phases carry no story label.

### Path Conventions

Single FastAPI project. Repo root: `/media/sam/1TB/UTXOracle/`. All paths below are repo-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm working tree is clean for the new files, verify dependencies are already present.

- [x] T001 Verify and install spec-061 dependencies. Run `grep -E "^\s*\"(pyyaml|jsonschema)" pyproject.toml`. Of the runtime deps (`fastapi`, `asyncpg`, `pydantic`) only the first three are present; **`pyyaml` and `jsonschema` are MISSING per pyproject.toml line 7-25** (verified during /speckit.analyze remediation 2026-06-01). Add them via `uv add pyyaml jsonschema` and commit the lockfile change in the same commit as T003 / T004. *(2026-06-01: done — pyyaml 6.0.3, jsonschema 4.26.0)*
- [x] T002 Verify the QuestDB instance on `localhost:8812` is reachable from the dev host and that the asyncpg pool in `api/questdb_repository.py` initializes (run `uv run python -c "from api.questdb_repository import create_tables_if_not_exist; import asyncio; asyncio.run(create_tables_if_not_exist())"`). *(2026-06-01: done — asyncpg connect OK, SELECT 1 returned 1)*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Author the registry YAML and the loader helper that every user story depends on.

**⚠️ CRITICAL**: US1 cannot start until the registry is loadable. US3 cannot start until the registry schema is validated. Both foundational tasks below ship before any user-story phase begins.

- [x] T003 Author the 13-entry contract registry at `docs/contracts/stream_registry.yaml` with one entry per stream per `research.md` § R7 (revised). Each entry MUST include `name`, `table`, `freshness_strategy`, `schema_version: "1.0.0"`, `sla_seconds`, `source_spec`, `pinned_columns`. Strategy-specific fields: when `freshness_strategy: max_ts` include `timestamp_column: ts`; when `freshness_strategy: tip_lag_blocks` include `block_column: spent_block`. SLA values: per spec.md SLA table for 12 entries; for `backtest_whale_signals` use **604800** = 168h per spec.md Clarifications Q3. Strategy assignment: `utxo_lifecycle_full` uses `tip_lag_blocks` (its `ts` is row-creation time, not block time — see research.md R7 revised); all other 12 streams use `max_ts`. `pinned_columns` read from `nautilus_dev/strategies/common/flow_discovery/onchain_context.py`.
- [x] T004 [P] Author a JSON-schema validation test at `tests/test_stream_registry.py` that loads `docs/contracts/stream_registry.yaml`, validates it against `specs/061-stream-consumption-contract/contracts/stream_registry.schema.yaml`, and asserts `len(streams) == 13` plus name uniqueness. RED first, then make GREEN by ensuring the YAML matches the schema.
- [x] T004b [P] Add an immutability test at `tests/test_stream_registry.py::test_stream_names_frozen` that pins the 13 contractual names to a constant `EXPECTED_NAMES = ("live_snapshots", "entity_flows_daily", "whale_transactions", "mempool_predictions", "net_flow_metrics", "backtest_whale_signals", "price_analysis", "urpd_features_daily", "utxo_lifecycle_full", "utxo_snapshots", "mvrv_daily", "nupl_daily", "realized_cap_daily")` and asserts `set(s["name"] for s in registry["streams"]) == set(EXPECTED_NAMES)`. Enforces FR-005 (no rename).

---

## Phase 3: User Story 1 — Consumer gates strict-mode runs on overall freshness (P1)

**Story goal** (from spec.md US1): a single authenticated `GET /v1/streams/health` returns per-stream freshness for all 13 streams plus a rollup, and the consumer gates strict-mode runs on `overall == "OK"`.

**Independent test**: `curl -H "Authorization: Bearer $TOKEN" http://localhost:8001/v1/streams/health | jq .overall` returns `"OK"` (assuming live data) and the response shape matches `contracts/streams_health.openapi.yaml`.

### Tests for US1 (RED — write first, must fail before implementation)

- [x] T005 [P] [US1] Write unit test `tests/test_streams_health.py::test_all_ok` — mock `read_stream_max_ts` to return fresh timestamps for all 13 streams; assert every stream's `status == "OK"` and `response.overall == "OK"`.
- [x] T006 [P] [US1] Write unit test `tests/test_streams_health.py::test_one_stale` — mock one stream past SLA; assert that stream is `"STALE"` with correct `stale_seconds`, others `"OK"`, overall `"DEGRADED"`.
- [x] T007 [P] [US1] Write unit test `tests/test_streams_health.py::test_table_empty` — mock one stream `max(ts)` returning `None`; assert status `"MISSING"`, no `error` field.
- [x] T008 [P] [US1] Write unit test `tests/test_streams_health.py::test_backend_unreachable` — mock one query raising `asyncpg.exceptions.ConnectionDoesNotExistError`; assert status `"MISSING"` and `error` field carries the exception class name (per spec.md Clarifications Q2).
- [x] T009 [P] [US1] Write unit test `tests/test_streams_health.py::test_auth_required` — call the route without bearer token; assert 401, no body content leaked.
- [ ] T010 [US1] Write integration test `tests/integration/test_streams_health_contract.py::test_overall_ok_after_backfill` — hit live QuestDB on `:8812`, assert response matches the OpenAPI schema and `overall == "OK"`. Marker `@pytest.mark.integration`. **This is the CI gate for closing Issue #8.**

### Implementation for US1 (GREEN)

- [ ] T011 [US1] Add a freshness-probe dispatcher to `api/questdb_repository.py`. Two functions: (a) `read_stream_max_ts(table: str, timestamp_column: str) -> datetime | None` — returns `max(timestamp_column)` or `None` if empty; (b) `read_stream_tip_lag_seconds(table: str, block_column: str, current_tip: int) -> int | None` — returns `(current_tip - max(block_column)) * 600` or `None` if empty. Both use the existing asyncpg pool. Both propagate exceptions (caller handles). The route picks the function by `entry.freshness_strategy`.
- [ ] T011a [P] [US1] Add a Bitcoin Core tip getter to `api/routes/streams.py` (or `api/rpc.py` if a helper module already exists). Function `get_current_tip() -> int` calls `getblockcount` via the existing Bitcoin Core RPC pool. Cached for 60s in module state to avoid hammering RPC across 13-stream polls. Used only by entries with `freshness_strategy: tip_lag_blocks`. Failure raises so the dispatcher in T011 can convert it into a per-stream `MISSING` with `error`.
- [x] T011b [P] [US1] Add unit test `tests/test_streams_health.py::test_tip_lag_blocks_strategy` — mock `get_current_tip()` returning a fixed tip, mock `read_stream_tip_lag_seconds` returning various values; assert correct status mapping for `utxo_lifecycle_full` against `sla_seconds=259200`. Includes a case where `get_current_tip()` raises → status `MISSING` with `error` populated.
- [ ] T012 [P] [US1] Create `api/models/streams.py` with three Pydantic models: `StreamStatus` (Enum `OK`/`STALE`/`MISSING`), `OverallStatus` (Enum `OK`/`DEGRADED`), `StreamHealthReading`, `StreamsHealthResponse`. Match the OpenAPI schema in `specs/061-stream-consumption-contract/contracts/streams_health.openapi.yaml`.
- [ ] T013 [US1] Create `api/routes/streams.py` exposing `router = APIRouter(prefix="/v1/streams", tags=["streams"])` with `@router.get("/health")` handler that: (1) loads the registry once at module import, (2) issues 13 `read_stream_max_ts` calls via `asyncio.gather(*coros, return_exceptions=True)`, (3) computes per-stream status, (4) builds `StreamsHealthResponse`. Reuse `auth_middleware.HTTPBearer` as a dependency.
- [ ] T014 [US1] Add a registry loader helper at the top of `api/routes/streams.py` (or factor into `api/registry.py` if reused later — start inline): `_load_registry() -> list[StreamRegistryEntry]` reads `docs/contracts/stream_registry.yaml`, validates against `specs/061-stream-consumption-contract/contracts/stream_registry.schema.yaml`, caches in module-level state. Raise at startup if invalid (fail-fast).
- [ ] T015 [US1] Wire the router into the existing FastAPI app: in `api/main.py`, add `from api.routes.streams import router as streams_router` and `app.include_router(streams_router)` next to the existing `include_router(questdb_router)` call.
- [ ] T016 [US1] Add structured-logging signals per `research.md` § R2: `logger.info("streams_health.poll", extra={"overall": ..., "n_stale": ..., "n_missing": ...})` on each successful response. Before adding a Prometheus counter, run `grep -rn "prometheus_client\|Counter\|REGISTRY" api/` to determine whether the metrics surface already exists. If yes, register `streams_health_polls_total{status=overall}` against the existing `REGISTRY`. If no, ship log-only for this spec and open a follow-up issue for metrics. Document the resolution in the commit message.

**Checkpoint US1**: All US1 unit tests GREEN; `T010` integration test GREEN once backfill completes (operational dep tracked in Phase 7). US1 is independently demonstrable end-to-end.

---

## Phase 4: User Story 2 — Daily aggregations stay fresh automatically (P1)

**Story goal** (from spec.md US2): a scheduled systemd timer runs `calculate_daily_metrics.py` daily; the three daily aggregates are written to QuestDB; freshness stays inside the 48h SLA.

**Independent test**: enable the timer, wait one cycle, query `/v1/streams/health`, observe `mvrv_daily`/`nupl_daily`/`realized_cap_daily` all `status: "OK"`.

### Tests for US2 (RED — write first)

- [ ] T017 [P] [US2] Write unit test `tests/test_calculate_daily_metrics_questdb.py::test_dual_write_mvrv` — mock the QuestDB pool; run `persist_metrics`; assert one INSERT was issued to `mvrv_daily` with the computed row.
- [ ] T018 [P] [US2] Write unit test `tests/test_calculate_daily_metrics_questdb.py::test_dual_write_nupl` — same shape for `nupl_daily`.
- [ ] T019 [P] [US2] Write unit test `tests/test_calculate_daily_metrics_questdb.py::test_dual_write_realized_cap` — same shape for `realized_cap_daily`.
- [ ] T020 [P] [US2] Write unit test `tests/test_calculate_daily_metrics_questdb.py::test_questdb_failure_does_not_block_duckdb` — mock QuestDB raising; assert DuckDB write completes, error is logged not raised (per `research.md` § R5).
- [ ] T021 [P] [US2] Write systemd-unit smoke test `tests/test_daily_aggregator_timer.py::test_unit_files_valid` — call `systemd-analyze verify utxoracle-daily-aggregator.service utxoracle-daily-aggregator.timer`; assert exit 0.

### Implementation for US2 (GREEN)

- [ ] T022 [P] [US2] Extend `api/questdb_repository.py::create_tables_if_not_exist` with DDL for **two missing tables** identified during /speckit.analyze remediation 2026-06-01: (a) `realized_cap_daily (ts TIMESTAMP, realized_cap DOUBLE, ...)` partitioned by month with `dedup upsert keys(ts)`; (b) `backtest_whale_signals (ts TIMESTAMP, ...)` matching the consumer-side schema (read pinned columns from `nautilus_dev/strategies/common/flow_discovery/onchain_context.py`). Then add three save methods: `save_mvrv_daily(ts, value, ...)`, `save_nupl_daily(ts, value, ...)`, `save_realized_cap_daily(ts, value, ...)`. Follow the existing `save_*` pattern (asyncpg INSERT via the pool, idempotent on `ts` per FR-010).
- [ ] T022a [P] [US2] Add DDL coverage test `tests/test_create_tables_ddl.py::test_required_tables_exist` — call `create_tables_if_not_exist` against a clean QuestDB; assert all 13 contract tables AND `address_clusters`, `address_clusters_staging` exist. Enforces R9 (no missing DDL).
- [ ] T023 [US2] Patch `scripts/metrics/calculate_daily_metrics.py::persist_metrics` to call a new `_persist_to_questdb(metrics)` immediately after the DuckDB writes. Wrap the QuestDB call in `try/except` that logs the exception via the existing logger but does NOT re-raise (per `research.md` § R5 strangler-fig).
- [ ] T023b [P] [US2] Add idempotency test at `tests/test_calculate_daily_metrics_idempotent.py::test_same_day_double_run` that: (1) seeds QuestDB with fixture source data for one date, (2) runs `calculate_daily_metrics` twice for that date, (3) asserts the resulting rows in `mvrv_daily`, `nupl_daily`, `realized_cap_daily` are identical row-for-row between runs (no duplicated metric semantics, no row count drift). Enforces FR-010.
- [ ] T024 [P] [US2] Create `utxoracle-daily-aggregator.service` at repo root, copied from `utxoracle-urpd-features.service`, with `ExecStart=/usr/bin/env uv run python -m scripts.metrics.calculate_daily_metrics`. Keep the same `User=`, `WorkingDirectory=`, and `Environment=` shape.
- [ ] T025 [P] [US2] Create `utxoracle-daily-aggregator.timer` at repo root with `OnCalendar=*-*-* 02:30:00 UTC`, `Persistent=true`, `Unit=utxoracle-daily-aggregator.service` (per `research.md` § R4).
- [ ] T026 [US2] Install the units locally: `sudo cp utxoracle-daily-aggregator.{service,timer} /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now utxoracle-daily-aggregator.timer`. Verify with `systemctl list-timers | grep utxoracle-daily`.
- [ ] T026a [US2] Author `scripts/metrics/mirror_backtest_whale_signals.py` — reads from `scripts/whale_flow_backtest.py`'s DuckDB output table (timestamp BIGINT), converts `timestamp BIGINT` → `ts TIMESTAMP` (UTC), and writes to QuestDB `backtest_whale_signals` via the existing `save_*` pattern. Idempotent: re-running for the same time range overwrites identical rows (per FR-010). Required because the producer writes DuckDB only (research.md R8). Bridge until producer rewrite.
- [ ] T026b [P] [US2] Add unit test `tests/test_mirror_backtest_whale_signals.py::test_duckdb_to_questdb_roundtrip` — seed DuckDB fixture with timestamp BIGINT rows, run mirror, assert QuestDB `backtest_whale_signals` contains rows with `ts` as UTC TIMESTAMP matching `to_timestamp(BIGINT)`.
- [ ] T026c [US2] Create `utxoracle-backtest-mirror.service` + `utxoracle-backtest-mirror.timer` at repo root. Timer: `OnCalendar=*-*-* 03:00:00 UTC` (offset from daily aggregator at 02:30). Service: `ExecStart=/usr/bin/env uv run python -m scripts.metrics.mirror_backtest_whale_signals`. Install procedure mirrors T026.

**Checkpoint US2**: dual-write tests GREEN; first scheduled run lands rows in `mvrv_daily`/`nupl_daily`/`realized_cap_daily`; those three streams report `status: "OK"` via the US1 endpoint.

---

## Phase 5: User Story 3 — Schema changes never silently break the consumer (P2)

**Story goal** (from spec.md US3): every stream entry carries a `schema_version`; breaking changes require a 30-day overlap window; soft-deprecation rule is documented.

**Independent test**: `yq '.streams[].schema_version' docs/contracts/stream_registry.yaml` returns `"1.0.0"` for all 13 entries; `docs/SCHEMA_VERSIONING.md` documents the rule with a worked example.

### Tests for US3 (RED — write first)

- [ ] T027 [P] [US3] Write test `tests/test_stream_registry.py::test_schema_version_present_and_valid` — assert every stream entry has a `schema_version` matching `^\d+\.\d+\.\d+$`.
- [ ] T028 [P] [US3] Write test `tests/test_streams_health.py::test_schema_version_echoed_in_response` — mock the registry; assert each stream's `schema_version` is echoed in its `StreamHealthReading`.
- [ ] T029 [P] [US3] Write test `tests/test_streams_health.py::test_deprecated_at_field_optional` — register one stream with `deprecated_at: "2026-05-31"`; assert the registry loads without error and the stream is still queried.

### Implementation for US3 (GREEN)

- [ ] T030 [US3] Ensure the registry from T003 already includes `schema_version: "1.0.0"` for all 13 entries (it should by Foundational design; this task is a verification + fix-up gate).
- [ ] T031 [US3] Ensure `StreamHealthReading` (T012) and the route response (T013) echo `schema_version`. Update T012 / T013 if missing.
- [ ] T032 [US3] Author `docs/SCHEMA_VERSIONING.md` documenting: (1) what counts as additive vs breaking per FR-006, (2) the 30-day soft-deprecation rule from FR-009, (3) the registry edit workflow from `quickstart.md` § "Edit the contract", (4) a worked example showing the old + new entry living side by side. Cross-link to existing `docs/contracts/CHANGE_POLICY.md` for the broader policy.

**Checkpoint US3**: registry validates; endpoint echoes `schema_version`; documentation merged; the policy is referenceable by future PRs.

---

## Phase 6: User Story 4 — Backend target is a single explicit choice (P2)

**Story goal** (from spec.md US4): one decision record names the backend (QuestDB single-tenant via PG-wire) as the consumption surface for all streams.

**Independent test**: `cat specs/061-stream-consumption-contract/decisions.md` shows the backend named and justified; `grep -l questdb docs/contracts/stream_registry.yaml` confirms every stream's backing surface lives in QuestDB.

### Implementation for US4 (no separate tests — documentation only)

- [ ] T033 [US4] Author `specs/061-stream-consumption-contract/decisions.md` with one section per decision: (1) Backend target = QuestDB single-tenant via PG-wire, (2) Why (per `research.md` § R1: column-store fits `max(ts)` shape, pool already exists, transport is JWT-bearer over existing FastAPI), (3) Alternatives rejected (REST per-stream — duplicated routes; Parquet shared volume — no atomic transactional shape), (4) Reversibility (the registry's `table` field is the only coupling; switching backend is a registry change + route swap).

**Checkpoint US4**: decision is in writing; consumer team has one authoritative reference.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: operational prerequisites for `SC-001` (`overall == "OK"`), CI hookup, Issue #8 closure ritual.

- [ ] T034 [P] Add `--target-backend {duckdb,questdb}` CLI flag to `scripts/bootstrap/historical_spent_backfill.py` defaulting to `duckdb`. When `questdb`, route batch writes through `save_utxo_lifecycle` per `research.md` § R6. Preserve the existing `data/backfill_checkpoint.json` format.
- [ ] T035 [P] Write test `tests/test_historical_spent_backfill_target_backend.py::test_questdb_path` — mock the QuestDB pool, invoke the script with `--target-backend questdb`, assert at least one batch went through `save_utxo_lifecycle` and the checkpoint advanced.
- [ ] T036 Launch the `utxo_lifecycle` catch-up backfill in background. **Resolve the live tip first** to avoid the script's static default `927966` (`scripts/bootstrap/historical_spent_backfill.py:220`): `TIP=$(bitcoin-cli getblockcount)` then `setsid uv run python -m scripts.bootstrap.historical_spent_backfill --resume --target-backend questdb --end-block "$TIP" >> /tmp/backfill_utxo_lifecycle.log 2>&1 &`. Capture the PID. **Completion criterion**: `jq .last_block data/backfill_checkpoint.json` returns a value within `(bitcoin-cli getblockcount) - 432` (=72h at 10min/block) of the current Bitcoin Core tip. This is the operational gate for `T010` going GREEN against live data. Monitor with `tail -f /tmp/backfill_utxo_lifecycle.log`.
- [ ] T037 Verify `--backfill N` flag exists: `uv run python -m scripts.metrics.calculate_daily_metrics --help | grep backfill`. If absent, add a sub-task T037a to implement the flag (parse `--backfill N` → loop over the last N days, call existing single-day code path per day). Then run `calculate_daily_metrics --backfill 160` once the `utxo_lifecycle` backfill is past tip-72h, to populate `mvrv_daily` / `nupl_daily` / `realized_cap_daily` to within 48h.
- [ ] T038 Add the integration test to CI: append `tests/integration/test_streams_health_contract.py` to the existing pytest invocation in the project's CI workflow (or local pre-commit gate), with `-m integration` markers honored.
- [ ] T038b [P] Add perf test at `tests/test_streams_health_perf.py::test_p95_under_500ms` using `pytest-benchmark` (add to `pyproject.toml` dev-deps if absent). Mock `read_stream_max_ts` with a 5ms artificial delay per call to simulate QuestDB RTT. Invoke the route 100 times via `httpx.AsyncClient`. Assert p95 < 500ms per plan.md `Performance Goals`. Enforces Constitution Principle IV.
- [ ] T039 [P] Run `uv run ruff check . && uv run ruff format .` over the changed files (`api/routes/streams.py`, `api/models/streams.py`, `api/questdb_repository.py`, `scripts/metrics/calculate_daily_metrics.py`, `scripts/bootstrap/historical_spent_backfill.py`).
- [ ] T040 [P] Update `docs/ARCHITECTURE.md` with one paragraph naming `/v1/streams/health` as the consumer-facing freshness surface, plus a pointer to `docs/contracts/stream_registry.yaml`.
- [ ] T041 Comment on Issue #8 (gptcompany/UTXOracle) with the commit hash per deliverable: (1) registry → commit hash, (2) endpoint → commit hash, (3) backend decision → commit hash, (4) schema_version → commit hash, (5) timer → commit hash. Close Issue #8 only after `T010` is GREEN against live data.

**Final checkpoint**: SC-001 satisfied (`overall == "OK"` against live data); SC-003 measurable from day 0 of timer (will materialize over 14-day window); Issue #8 closed; nautilus_dev PR #146 unblocked.

---

## Dependencies

```
Phase 1 (Setup: T001, T002)
   └→ Phase 2 (Foundational: T003, T004, T004b)
         ├→ Phase 3 (US1: T005..T016 + T011a, T011b)   ── P1 ── MVP candidate
         ├→ Phase 4 (US2: T017..T026 + T022a, T023b, T026a, T026b, T026c) ── P1
         ├→ Phase 5 (US3: T027..T032)                  ── P2 (depends on US1 T012 + T013)
         └→ Phase 6 (US4: T033)                        ── P2 (documentation only)

Phase 7 (Polish: T034..T041 + T038b)
   ├→ T034..T037 are operational prereqs for the LIVE green of T010 (US1) but
   │   do NOT block US1 mock-based unit tests.
   └→ T041 (Issue #8 closure) requires T010 GREEN.
```

### Within-story parallelism

- US1 tests T005–T009 are `[P]` (different test names in the same file — write each in its own commit; if file-level parallelism is required, split into one test class per case).
- US1 model + repo writes are `[P]` (T011 in `questdb_repository.py`, T012 in `api/models/streams.py` — different files).
- US2 tests T017–T021 are `[P]` (each in its own test function/file).
- US2 implementation T022 (repo) and T024+T025 (systemd units) are `[P]` (three different files); T023 (script patch) and T026 (install) are sequential.
- US3 tests T027–T029 are `[P]` (different files / different tests).
- Phase 7 T034 + T035 + T039 + T040 are `[P]` (different files).

### Suggested MVP scope

User Story 1 alone (Phase 1 + Phase 2 + Phase 3) is a shippable MVP: the endpoint exists, returns the real freshness state, the consumer can gate strict-mode runs. Phases 4–7 raise the contract from "true now" to "true durably".

---

## Format validation

All 51 tasks (T001–T041 plus T004b, T011a, T011b, T022a, T023b, T026a, T026b, T026c, T038b added during /speckit.analyze remediations on 2026-05-31 and 2026-06-01) follow `- [ ] T### [P?] [Story?] Description with explicit file path` per the speckit.tasks command rules. No task is missing a checkbox, ID, or file path. Story labels appear on Phase 3–6 tasks only; Phase 1, 2, and 7 carry no story label per template.

## Remediation history

| Date | Source | Edits applied |
|---|---|---|
| 2026-05-31 | `/speckit.analyze` findings C1/C2/C3/F1/A1/A2/U1 | Edited T003 (F1), T016 (A1), T036 (A2), T037 (U1); inserted T004b (C1), T023b (C2), T038b (C3); updated Dependencies graph. Accepted as-is: D1 (intentional gates), U2 (design invariant), F2 (plan-level refinement). |
| 2026-06-01 | User-supplied review findings (7 issues, 2 minor) | **H1** utxo_lifecycle_full false-OK: introduced `freshness_strategy: max_ts \| tip_lag_blocks` per-stream (data-model.md, research.md R7 revised, stream_registry.schema.yaml, T003, T011, +T011a, +T011b). **H2** backtest_whale_signals lives in DuckDB: added mirror task chain (research.md R8, +T026a, +T026b, +T026c). **H3** realized_cap_daily DDL missing: extended T022 with DDL block, added T022a coverage test (research.md R9). **M1** T036 backfill --end-block static default: pass dynamic `bitcoin-cli getblockcount`. **M2** OpenAPI examples broke schema: relaxed streams_health.openapi.yaml from `minItems/maxItems: 13` to `minItems: 1` with description noting test-side enforcement. **M3** pyyaml+jsonschema not in pyproject.toml: T001 extended to `uv add`. **minor1** plan.md path typo fixed. **minor2** spec.md Status: Draft → Final (post-clarify, post-analyze remediation). |
