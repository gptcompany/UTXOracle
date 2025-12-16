# Implementation Plan: STH/LTH Cost Basis

**Branch**: `023-cost-basis-cohorts` | **Date**: 2025-12-16 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/023-cost-basis-cohorts/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Implement weighted average cost basis calculation per holder cohort (STH/LTH) to identify key support/resistance levels. The feature calculates:
- `sth_cost_basis`: Average acquisition price for Short-Term Holders (<155 days)
- `lth_cost_basis`: Average acquisition price for Long-Term Holders (>=155 days)
- Cohort-specific MVRV ratios for market positioning signals

**Technical Approach**: Aggregate query on existing `utxo_lifecycle_full` VIEW with weighted average formula, similar to existing `calculate_cohort_realized_cap()` pattern in `realized_metrics.py`.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: DuckDB (existing), FastAPI (existing), Pydantic (existing)
**Storage**: DuckDB via `utxo_lifecycle_full` VIEW (existing infrastructure)
**Testing**: pytest with existing fixtures (`tests/test_realized_metrics.py` pattern)
**Target Platform**: Linux server (existing deployment)
**Project Type**: Single project - backend metrics module
**Performance Goals**: <100ms query latency for cost basis calculation
**Constraints**: Must work with existing UTXO dataset (~millions of records), 80%+ test coverage
**Scale/Scope**: Single metrics module with 1 API endpoint

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Code Quality & Simplicity | PASS | Extends existing `realized_metrics.py` pattern, single-purpose module |
| II. Test-First Discipline | PASS | TDD workflow required, tests before implementation |
| III. User Experience Consistency | PASS | REST API follows existing `/api/metrics/*` pattern |
| IV. Performance Standards | PASS | Aggregate query on indexed VIEW, <100ms target achievable |
| V. Data Privacy & Security | PASS | Local processing only, no external APIs |

**Pre-Design Gate**: PASSED - No violations detected.

## Project Structure

### Documentation (this feature)

```
specs/023-cost-basis-cohorts/
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
│   ├── cost_basis.py            # NEW: Cost basis calculator
│   └── realized_metrics.py      # EXISTING: Base functions to import
├── models/
│   └── metrics_models.py        # MODIFY: Add CostBasisResult dataclass

api/
└── main.py                      # MODIFY: Add /api/metrics/cost-basis endpoint

tests/
└── test_cost_basis.py           # NEW: TDD tests for cost basis module
```

**Structure Decision**: Single project structure - backend metrics module following existing patterns in `scripts/metrics/`. No frontend changes required.

## Complexity Tracking

*No violations detected - no justification needed.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
