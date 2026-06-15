# Decisions Log: entity_flows_daily QuestDB Producer Pilot

**Date**: 2026-06-15
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)
**Research**: [research.md](./research.md)

This log records spec-level architectural decisions that the plan freeze depends on. Each entry has: decision, rationale, rejected alternatives. Decisions made during `/speckit.clarify` live in `spec.md` under `## Clarifications`; this file collects the ones made during `/speckit.plan`.

---

## D1 — Keep spec-063 scoped to `entity_flows_daily` only

**Decision**: spec-063 ships dual-write for `entity_flows_daily` only. The four sibling tables that `aggregate_flows()` also writes (`entity_movement_events`, `entity_transfer_edges`, `entity_balance_snapshots_daily`, `entity_counterparty_edges_daily`) remain DuckDB-only and are out of scope.

**Rationale**: spec-063 is the **pilot** application of the spec-062 Appendix A pattern. It validates the dual-write contract, observability surface, rollback toggle, and 7-day green observation gate on a single consumer-facing stream. Expanding to all five tables in one spec would:
- Triple the schema parity / cast-table surface (five tables, each with its own column list, instead of one).
- Multiply the failure modes the test suite must cover (cross-table consistency on partial QuestDB failures).
- Inflate review surface and slow production unblock for the consumer who only needs `entity_flows_daily`.
- Risk turning the pilot into a "mini-migration of the entity intelligence surface" — work that can be done with much less uncertainty AFTER the pilot validates the pattern.

After spec-063 lands and clears its 7-day green gate, follow-up Phase 2 specs will migrate the four sibling tables one-by-one using the spec-063 deliverables as a working template.

**Rejected alternative**: *Migrate all five `aggregate_flows()` tables in a single spec-063.*  Rejected due to increased blast radius (5× the column casts, 5× the test guards, 5× the rollback surface) and slower production unblock for the one stream (`entity_flows_daily`) that is consumer-facing.

---

## D2 — Lossy-cast escalation verdict: none required

**Decision**: No materially lossy DuckDB→QuestDB cast was identified during discovery. All six column casts enumerated in `data-model.md` are lossless under the round-trip definition Clarify Q3 declared.

**Rationale**: Per [data-model.md](./data-model.md) cast table, the six columns map as:
- `entity_id VARCHAR` → `SYMBOL INDEX` — lossless (SYMBOL is an interned string with full identity preservation; round-trip recovers the exact original string).
- `date DATE` → `TIMESTAMP` — lossless (DATE has midnight-UTC precision, TIMESTAMP encodes it exactly).
- `inflow_btc / outflow_btc / netflow_btc DOUBLE` → `DOUBLE` — identity (IEEE 754 binary64 on both engines).
- `is_exchange BOOLEAN` → `BOOLEAN` — identity.

The new QuestDB-only column `ts TIMESTAMP` (designated timestamp for partitioning) has no DuckDB twin and is therefore N/A for the round-trip check.

**Rejected alternative**: *Force a lossy-cast entry anyway for "future-proofing"* — rejected. Adding a fictional lossy entry would mislead reviewers of the next Phase 2 spec who use spec-063 as a template; the precedent must be honest.

---

## D3 — Escape hatch (Option A: mirror script) NOT triggered

**Decision**: spec-063 stays on Baseline B (dual-write in `aggregate_flows()`). The Option A escape hatch declared in `spec.md` "Escape hatch" section is NOT activated.

**Rationale** (per spec.md disqualifying-condition check):
- *Is `aggregate_flows()` the runtime active path?* — Discovery: it is invoked ONLY by tests today. There is **no** competing runtime active path elsewhere. The function is the canonical producer, just not currently scheduled. spec-063 ships the dual-write code; a follow-up spec (out of scope per user input) will schedule the invocation.
- *Does the producer hold a long DuckDB transaction?* — No. Each `INSERT OR REPLACE` is a separate statement; the `with duckdb.connect(...) as conn:` block scopes the connection lifecycle to one batch.
- *Does it run inside a critical event loop?* — No. The function is synchronous; no asyncio, no event loop, no callback hot-path.
- *Does it depend on hot-reload behaviour?* — No. It is a module-level function with a clean `__main__` entrypoint.

None of the disqualifying conditions are present. Option B remains the baseline.

**Rejected alternative**: *Pre-emptively activate Option A (mirror script DuckDB→QuestDB) for safety* — rejected. Adding a separate mirror service would introduce a new scheduling surface (forbidden by user input hard constraints) AND perpetuate the dependency on DuckDB as a producer, violating the spirit of Phase 2 migration.

---

## D4 — Sync `save_entity_flows_daily` placement

**Decision**: The save method lives in `api/questdb_repository.py` as a sync, module-level, keyword-only-arguments function. NOT a method on an existing class. NOT async.

**Rationale**:
- Matches the spec-061/062 convention: `save_mvrv_daily`, `save_nupl_daily`, `save_realized_cap_daily` are all module-level sync functions in the same module.
- The producer (`aggregate_flows`) is sync; an async save method would force an event loop spin-up for what is effectively a per-row blocking `cur.execute`.
- The existing async `get_entity_flows()` (line 1861) serves the FastAPI endpoint — different concern, different runtime context. Coexistence is fine.

**Rejected alternative**: *Producer-local helper inside `flow_aggregator.py`* — rejected per [research.md](./research.md) R4. Splits the QuestDB write surface, duplicates connection management.

---

## D5 — psycopg PG-wire transport, NOT ILP

**Decision**: Writes go through psycopg sync `INSERT ... ON CONFLICT ... DO UPDATE` via `_open_pg_sync()`. ILP is rejected.

**Rationale**: Per [research.md](./research.md) R5. Per-row error isolation (FR-002, FR-003) maps cleanly to psycopg's per-`cur.execute` semantics; ILP's batched flush model would make per-row attribution harder. spec-061 Phase 1.5-v2 sets the precedent (psycopg sync for `block_heights`, `daily_prices`).

**Rejected alternative**: *ILP Sender per row + flush per save* — rejected; complicates error attribution. *Bulk `executemany`* — considered, deferred for the pilot to preserve per-row isolation; revisit if measured wall-clock exceeds 10 s at N = 10 000 rows.

---

## D6 — Production runtime gap is acknowledged, not solved here

**Decision**: spec-063 ships the dual-write code, the DDL adjustment, the env-var toggle, and the test suite. spec-063 does NOT add a systemd timer or any other scheduling mechanism for `aggregate_flows()`. The function will be invoked via an operator-driven manual smoke (per [quickstart.md](./quickstart.md)) for acceptance verification. Scheduling is deferred to a separate follow-up spec.

**Rationale**:
- User input hard constraint forbids new timers / scheduling mechanisms.
- Discovery confirmed `aggregate_flows()` is invoked only by tests today. Adding a scheduler implicitly here would expand the spec scope to include "first production deployment of the entity intelligence pipeline" — much larger than the pilot.
- The acceptance criteria SC-001 / SC-005 are formally satisfiable post-spec-063 via the operator-driven smoke: run the script once, observe `/v1/streams/health` for an hour to validate SC-001's 95% OK polling rate, then continue daily for SC-005's 7-day gate.

**Rejected alternative**: *Add a systemd timer in spec-063* — rejected per user input. *Defer the entire spec-063 until a scheduling spec lands first* — rejected: that would block the pilot validation of the pattern, and the operator-driven smoke is sufficient to validate the dual-write contract.

---

## Sign-off

Plan freeze checklist (from plan.md):

- [x] Constitution Check PASS (TDD RED-first commitment explicit)
- [x] research.md complete (6 decisions enumerated)
- [x] data-model.md cast table complete (6 columns + ts, all lossless — confirmed in D2)
- [x] decisions.md: no lossy cast escalation needed (D2); Option A escape hatch NOT triggered (D3); pilot scope guard in place (D1)
- [x] contracts/ outline complete (3 files: envvars.md, save_entity_flows_daily.md, webhook_payload.md)
- [x] Production runtime gap explicitly noted (D6, plan.md Constitution Check note)
- [x] Hard constraints honoured (no new timer, no extra files outside the 4 enumerated)

**Plan is frozen. Ready for review and `/speckit.tasks`.**
