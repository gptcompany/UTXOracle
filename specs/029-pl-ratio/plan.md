# Implementation Plan: P/L Ratio (Dominance)

**Branch**: `029-pl-ratio` | **Date**: 2025-12-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/029-pl-ratio/spec.md`

## Summary

Implement P/L Ratio and P/L Dominance metrics as derivatives of spec-028 Net Realized P/L. The feature calculates the ratio of profit-taking to loss-taking activity, providing a normalized indicator of market regime. This is a "Quick Win" implementation with very low complexity since it reuses existing spec-028 infrastructure.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: DuckDB (existing), dataclasses (stdlib)
**Storage**: DuckDB (reuses `utxo_lifecycle_full` VIEW from spec-017)
**Testing**: pytest with DuckDB in-memory fixtures
**Target Platform**: Linux server (matches existing infrastructure)
**Project Type**: single (extends existing scripts/metrics/ module)
**Performance Goals**: <100ms calculation time (reuses existing VIEW)
**Constraints**: Must reuse spec-028 profit/loss data, no additional database queries
**Scale/Scope**: Single metric module, 2 API endpoints

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Code Quality & Simplicity ✅

| Check | Status | Notes |
|-------|--------|-------|
| KISS/YAGNI | ✅ | Reuses spec-028 data, no new infrastructure |
| Single purpose | ✅ | One module: P/L ratio calculation |
| Minimal dependencies | ✅ | No new dependencies |
| Readability | ✅ | Simple ratio calculation (profit/loss) |
| No premature abstraction | ✅ | Direct implementation, no generics |

### Principle II: Test-First Discipline ✅

| Check | Status | Notes |
|-------|--------|-------|
| TDD cycle | ✅ | RED tests first (will use pytest-test-generator skill) |
| 80% coverage | ✅ | Target 100% for simple module |
| Integration tests | ✅ | Required for API endpoints |

### Principle III: User Experience Consistency ✅

| Check | Status | Notes |
|-------|--------|-------|
| CLI standards | N/A | No CLI component |
| API standards | ✅ | REST endpoints follow existing patterns |
| Output format | ✅ | JSON response matches existing metrics |

### Principle IV: Performance Standards ✅

| Check | Status | Notes |
|-------|--------|-------|
| Calculation time | ✅ | <100ms target (simple division) |
| Resource limits | ✅ | No additional DB queries needed |

### Principle V: Data Privacy & Security ✅

| Check | Status | Notes |
|-------|--------|-------|
| Local processing | ✅ | All calculations local |
| Input validation | ✅ | Pydantic models for API |

**GATE STATUS: PASSED** - No violations, proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```
specs/029-pl-ratio/
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
├── metrics/
│   ├── net_realized_pnl.py   # spec-028 (dependency)
│   └── pl_ratio.py           # NEW: P/L ratio calculator
└── models/
    └── metrics_models.py     # ADD: PLRatioResult, PLDominanceZone

tests/
├── test_pl_ratio.py          # NEW: TDD tests

api/
└── main.py                   # ADD: /api/metrics/pl-ratio endpoints
```

**Structure Decision**: Extends existing `scripts/metrics/` module structure, following the established pattern from spec-028 (Net Realized P/L).

## Complexity Tracking

*No violations requiring justification.*

## Post-Design Constitution Re-Check

*Re-evaluated after Phase 1 artifacts (data-model.md, contracts/, quickstart.md) generated.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality & Simplicity | ✅ PASSED | Single module, reuses spec-028, no new deps |
| II. Test-First Discipline | ✅ PASSED | TDD tests defined in data-model.md |
| III. User Experience Consistency | ✅ PASSED | API follows existing patterns (OpenAPI spec) |
| IV. Performance Standards | ✅ PASSED | Simple calculation, no new DB queries |
| V. Data Privacy & Security | ✅ PASSED | Local processing, input validation via Pydantic |

**FINAL STATUS: READY FOR TASK GENERATION** - Run `/speckit.tasks` to generate tasks.md.
