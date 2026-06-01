# Implementation Plan: Stream Consumption Contract for nautilus_dev

**Branch**: `061-stream-consumption-contract` | **Date**: 2026-05-31 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/061-stream-consumption-contract/spec.md`

## Summary

Expose a single authenticated freshness endpoint (`GET /v1/streams/health`) that returns the per-stream state of the 13 contractual onchain streams plus a rollup status, backed by a single YAML registry that pins each stream's name, schema version, freshness SLA, and source surface. Schedule the daily aggregation job that keeps three of those streams within SLA. Reuse already-implemented internal SLO/schema/observability infrastructure (specs 056–059) — this spec is the consumer-facing adapter, not a re-implementation.

Technical approach: a thin FastAPI route module reads a YAML registry once at startup, queries `max(ts)` on the 13 backing tables in parallel via the existing QuestDB asyncpg pool, computes status per stream from SLA + measured staleness, and returns a Pydantic-modeled JSON response. A systemd timer wraps the existing `calculate_daily_metrics.py` script, which is patched to dual-write its three aggregates into QuestDB through the existing `save_*` pattern. The operational backfill of `utxo_lifecycle` runs out-of-band via the existing bootstrap script with a new `--target-backend questdb` flag.

## Technical Context

**Language/Version**: Python 3.11 (project baseline — `uv` managed)
**Primary Dependencies**: FastAPI (existing `api/main.py`), asyncpg (existing QuestDB pool in `api/questdb_repository.py`), Pydantic (existing response models), PyYAML (existing — used by `docs/contracts/*.yaml`)
**Storage**: QuestDB single-tenant via PG-wire on `:8812` (the chosen backend per FR-008). Stream registry as YAML at `docs/contracts/stream_registry.yaml`. No new persistent storage introduced.
**Testing**: pytest with asyncio + asynctest mocks for the unit layer; pytest with a live QuestDB instance for `tests/integration/test_streams_health_contract.py` (the acceptance gate)
**Target Platform**: Linux server (the existing UTXOracle API host); systemd for the timer
**Project Type**: Single project — extends existing `api/` FastAPI service. No new top-level project added.
**Performance Goals**: Endpoint p95 < 500ms with all 13 streams polled in parallel. Consumer poll budget assumed at most 1 req/strict-mode-run-start (low single-digit QPS).
**Constraints**: Endpoint must remain stateless — no in-memory caching that masks `STALE` after a backend recovery. Registry is the only configuration; runtime behavior MUST match what the registry declares.
**Scale/Scope**: 13 stream entries fixed by contract. 1 new route. 1 new YAML registry. 1 new systemd timer + service unit. 4 modified files in the existing codebase.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|---|---|---|
| I. Code Quality & Simplicity (KISS/YAGNI) | PASS | One route, one YAML, one timer. Zero new abstractions. Reuses existing `auth_middleware`, `questdb_repository`, systemd template, save_* pattern. |
| II. Test-First Discipline (TDD, 80% cov) | PASS | Acceptance test pre-registered as a hard gate (FR-012). Unit tests for 4 status cases listed in spec. RED-GREEN-REFACTOR enforced. |
| III. User Experience Consistency | PASS | Endpoint returns JSON via existing FastAPI surface; Pydantic models follow project pattern. No CLI/visualization affected. |
| IV. Performance Standards | PASS | 13 `max(ts)` queries in parallel via asyncpg pool. Well within Bitcoin Core RPC connection pool budget. No real-time path touched. |
| V. Data Privacy & Security | PASS | Reuses HTTPBearer (`api/auth_middleware.py`). No external API. Registry is committed in-repo, no PII. Consumer-facing surface authenticates per the existing pattern. |

**Result**: PASS — no violations, no complexity tracking entries required.

## Project Structure

### Documentation (this feature)

```
specs/061-stream-consumption-contract/
├── spec.md                  # Feature specification
├── plan.md                  # This file
├── research.md              # Phase 0 output
├── data-model.md            # Phase 1 output
├── quickstart.md            # Phase 1 output
├── contracts/
│   ├── streams_health.openapi.yaml   # OpenAPI fragment for GET /v1/streams/health
│   └── stream_registry.schema.yaml   # JSON Schema for docs/contracts/stream_registry.yaml
├── checklists/
│   └── requirements.md      # Quality checklist (from /speckit.specify)
└── tasks.md                 # Phase 2 output (from /speckit.tasks — NOT this command)
```

### Source Code (repository root)

This feature extends the existing single-project FastAPI service. No new top-level directory is introduced.

```
api/
├── main.py                           # MODIFIED: include_router(streams_router)
├── auth_middleware.py                # REUSED unchanged (HTTPBearer)
├── questdb_repository.py             # MODIFIED: add save_mvrv_daily, save_nupl_daily,
│                                     #           save_realized_cap_daily, read_stream_max_ts
├── models/
│   └── streams.py                    # NEW: Pydantic response models
└── routes/
    └── streams.py                    # NEW: GET /v1/streams/health

docs/
├── contracts/
│   └── stream_registry.yaml          # NEW: 13-entry SSOT for the contract
└── SCHEMA_VERSIONING.md              # NEW: 30-day soft-deprecation rules (refs CHANGE_POLICY.md)

scripts/
├── metrics/
│   └── calculate_daily_metrics.py    # MODIFIED: dual-write to QuestDB
└── bootstrap/
    └── historical_spent_backfill.py  # MODIFIED: --target-backend questdb flag

tests/
├── test_streams_health.py            # NEW: unit (4 status cases, mocked repo)
├── test_calculate_daily_metrics_questdb.py  # NEW: dual-write test
└── integration/
    └── test_streams_health_contract.py      # NEW: acceptance gate (live QuestDB)

# Systemd units (repo root, installed to /etc/systemd/system/)
utxoracle-daily-aggregator.service    # NEW: copy of utxoracle-urpd-features.service
utxoracle-daily-aggregator.timer      # NEW: OnCalendar=*-*-* 02:30:00 UTC
```

**Structure Decision**: Single FastAPI project extension. The new route, models, and YAML registry live alongside their existing peers (`api/routes/`, `api/models/`, `docs/contracts/`). No new package layer, no service boundary added. This is the minimal-friction structure for an adapter that wires existing internal surfaces to one external endpoint.

## Complexity Tracking

No constitutional violations. This section intentionally left empty.
