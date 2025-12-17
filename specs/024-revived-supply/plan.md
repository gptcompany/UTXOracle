# Implementation Plan: Revived Supply

**Branch**: `024-revived-supply` | **Date**: 2025-12-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/024-revived-supply/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Track dormant coins being spent to signal long-term holder behavior changes. The feature calculates:
- `revived_1y`: BTC revived after 1+ year dormancy
- `revived_2y`: BTC revived after 2+ year dormancy
- `revived_5y`: BTC revived after 5+ year dormancy
- `revived_total_usd`: USD value of revived supply
- `revived_avg_age`: Average age of revived UTXOs

**Technical Approach**: Aggregate query on existing `utxo_lifecycle_full` VIEW filtering by `is_spent=TRUE` and `age_days >= threshold`, following the same pattern as `cost_basis.py` and `nupl.py`.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: DuckDB (existing), FastAPI (existing), Pydantic (existing)
**Storage**: DuckDB via `utxo_lifecycle_full` VIEW (existing infrastructure)
**Testing**: pytest with existing fixtures pattern
**Target Platform**: Linux server (existing deployment)
**Project Type**: Single project - backend metrics module
**Performance Goals**: <100ms query latency for revived supply calculation
**Constraints**: Must work with existing UTXO dataset, 80%+ test coverage
**Scale/Scope**: Single metrics module with 1 API endpoint

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Code Quality & Simplicity | PASS | Extends existing metrics pattern, single-purpose module |
| II. Test-First Discipline | PASS | TDD workflow required, tests before implementation |
| III. User Experience Consistency | PASS | REST API follows existing `/api/metrics/*` pattern |
| IV. Performance Standards | PASS | Aggregate query on indexed VIEW, <100ms target achievable |
| V. Data Privacy & Security | PASS | Local processing only, no external APIs |

**Pre-Design Gate**: PASSED - No violations detected.

## Project Structure

### Documentation (this feature)

```
specs/024-revived-supply/
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
│   ├── revived_supply.py        # NEW: Revived supply calculator
│   └── cost_basis.py            # EXISTING: Similar pattern to follow
├── models/
│   └── metrics_models.py        # MODIFY: Add RevivedZone enum + RevivedSupplyResult dataclass

api/
└── main.py                      # MODIFY: Add /api/metrics/revived-supply endpoint

tests/
└── test_revived_supply.py       # NEW: TDD tests for revived supply module
```

**Structure Decision**: Single project structure - backend metrics module following existing patterns in `scripts/metrics/`. No frontend changes required.

## Complexity Tracking

*No violations detected - no justification needed.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
