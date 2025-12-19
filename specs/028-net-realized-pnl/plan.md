# Implementation Plan: Net Realized Profit/Loss

**Branch**: `028-net-realized-pnl` | **Date**: 2025-12-18 | **Spec**: [spec-028](/specs/028-net-realized-pnl/spec.md)
**Input**: Feature specification from `/specs/028-net-realized-pnl/spec.md`

## Summary

Implement Net Realized Profit/Loss metric that aggregates realized gains/losses from spent UTXOs to show actual capital flows. The metric calculates profit (when spent_price > creation_price) and loss (when spent_price < creation_price) for all UTXOs spent within a time window, providing insight into market-wide profitability of coin movements.

**Technical Approach**: Aggregate query on existing `utxo_lifecycle_full` VIEW which already has `creation_price_usd`, `spent_price_usd`, `btc_value`, and `is_spent` columns. No schema changes required.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: DuckDB (existing), FastAPI (existing), Pydantic (existing)
**Storage**: DuckDB via `utxo_lifecycle_full` VIEW (existing - has all required columns)
**Testing**: pytest with existing TDD patterns
**Target Platform**: Linux server (existing deployment)
**Project Type**: Single project - backend metrics module
**Performance Goals**: <100ms query time for 24h window
**Constraints**: Must use existing VIEW schema, no external API calls
**Scale/Scope**: Single metric module, 2 API endpoints

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Check (Phase 0)

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. KISS/YAGNI | ✅ PASS | Single SQL query, reuses existing VIEW, no new dependencies |
| II. TDD Discipline | ✅ READY | pytest-test-generator skill available, test fixtures exist |
| III. UX Consistency | ✅ PASS | Follows existing `/api/metrics/*` patterns |
| IV. Performance | ✅ PASS | Single aggregate query, indexed columns |
| V. Data Privacy | ✅ PASS | Local processing only, no external APIs |

**Pre-Design Gate Result**: PASS - No violations requiring justification.

### Post-Design Check (Phase 1)

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. KISS/YAGNI | ✅ PASS | Data model uses existing dataclass pattern, no new abstractions |
| II. TDD Discipline | ✅ PASS | Test structure defined, fixtures available |
| III. UX Consistency | ✅ PASS | OpenAPI contract follows existing patterns in api/main.py |
| IV. Performance | ✅ PASS | Query uses indexed columns (is_spent, spent_timestamp) |
| V. Data Privacy | ✅ PASS | No external APIs, all data from local DuckDB |

**Post-Design Gate Result**: PASS - Design adheres to all constitution principles.

## Project Structure

### Documentation (this feature)

```
specs/028-net-realized-pnl/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI spec)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```
scripts/
└── metrics/
    └── net_realized_pnl.py      # Calculator module

tests/
└── test_net_realized_pnl.py     # Unit tests

scripts/
└── models/
    └── metrics_models.py        # Add NetRealizedPnLResult dataclass

api/
└── main.py                      # Add /api/metrics/net-realized-pnl endpoints
```

**Structure Decision**: Single project structure. Adds one new metrics module following existing patterns in `scripts/metrics/`. Integrates with existing API in `api/main.py`.

## Complexity Tracking

*No violations requiring justification - feature follows established patterns.*

| Aspect | Complexity Level | Justification |
|--------|------------------|---------------|
| SQL Query | Low | Single aggregate with CASE expressions |
| API | Low | 2 endpoints matching existing patterns |
| Data Model | Low | 1 dataclass, mirrors existing models |
| Testing | Low | Standard unit tests with fixtures |
