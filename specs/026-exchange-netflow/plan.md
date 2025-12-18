# Implementation Plan: Exchange Netflow

**Branch**: `026-exchange-netflow` | **Date**: 2025-12-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/026-exchange-netflow/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Track BTC movement to/from known exchange addresses to identify selling pressure vs accumulation. The feature calculates:
- `exchange_inflow`: BTC flowing into exchanges (sell pressure indicator)
- `exchange_outflow`: BTC flowing out of exchanges (accumulation indicator)
- `netflow`: Net flow (positive = selling, negative = accumulation)
- `netflow_7d_ma`: 7-day moving average of netflow
- `netflow_30d_ma`: 30-day moving average of netflow

**Technical Approach**: Aggregate query on existing `utxo_lifecycle_full` VIEW joining against a curated exchange address lookup table (CSV/DuckDB). Exchange addresses sourced from existing `data/exchange_addresses.csv` file with 10 known exchange addresses.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: DuckDB (existing), FastAPI (existing), Pydantic (existing)
**Storage**: DuckDB via `utxo_lifecycle_full` VIEW + `exchange_addresses` lookup table
**Testing**: pytest with existing fixtures pattern
**Target Platform**: Linux server (existing deployment)
**Project Type**: Single project - backend metrics module
**Performance Goals**: <200ms query latency for netflow calculation (JOIN on address column)
**Constraints**: Must work with existing UTXO dataset, 80%+ test coverage, exchange address data quality dependent on community-curated list
**Scale/Scope**: Single metrics module with 2 API endpoints

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Code Quality & Simplicity | PASS | Extends existing metrics pattern, single-purpose module, uses existing CSV data |
| II. Test-First Discipline | PASS | TDD workflow required, tests before implementation |
| III. User Experience Consistency | PASS | REST API follows existing `/api/metrics/*` pattern |
| IV. Performance Standards | PASS | Aggregate query with indexed JOIN, <200ms target achievable |
| V. Data Privacy & Security | PASS | Local processing only, exchange addresses are public data |

**Pre-Design Gate**: PASSED - No violations detected.

## Project Structure

### Documentation (this feature)

```
specs/026-exchange-netflow/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```
scripts/
├── metrics/
│   ├── exchange_netflow.py      # NEW: Exchange netflow calculator
│   └── revived_supply.py        # EXISTING: Similar pattern to follow
├── models/
│   └── metrics_models.py        # MODIFY: Add NetflowZone enum + ExchangeNetflowResult dataclass
├── data/
│   └── exchange_addresses.csv   # EXISTING: Curated exchange address list (10 addresses)

api/
└── main.py                      # MODIFY: Add /api/metrics/exchange-netflow endpoints

tests/
└── test_exchange_netflow.py     # NEW: TDD tests for exchange netflow module
```

**Structure Decision**: Single project structure - backend metrics module following existing patterns in `scripts/metrics/`. Uses existing `data/exchange_addresses.csv` rather than creating new data source.

## Complexity Tracking

*No violations detected - no justification needed.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |

---

## Post-Design Constitution Re-Check

*GATE: Re-evaluated after Phase 1 design completion.*

| Principle | Status | Post-Design Evidence |
|-----------|--------|----------------------|
| I. Code Quality & Simplicity | PASS | Single module (`exchange_netflow.py`), reuses existing CSV data, no new dependencies |
| II. Test-First Discipline | PASS | TDD tests defined in research.md, follows existing `test_revived_supply.py` pattern |
| III. User Experience Consistency | PASS | API follows `/api/metrics/*` pattern, JSON response matches other metrics |
| IV. Performance Standards | PASS | <200ms target validated via single JOIN query, TTL caching planned |
| V. Data Privacy & Security | PASS | All processing local, exchange addresses are public blockchain data |

**Post-Design Gate**: PASSED - Design validated against all constitutional principles.
