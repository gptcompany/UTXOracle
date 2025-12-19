# Implementation Plan: Binary CDD Indicator

**Branch**: `027-binary-cdd` | **Date**: 2025-12-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/027-binary-cdd/spec.md`

## Summary

Binary CDD is a statistical significance flag that converts noisy Coin Days Destroyed (CDD) data into actionable signals. It calculates a z-score against a 365-day rolling baseline and outputs a binary flag when CDD exceeds a configurable N-sigma threshold (default: 2.0). This transforms raw CDD metrics from spec-021 into clear, high-conviction long-term holder movement events.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: numpy (statistics), duckdb (historical queries), FastAPI (API endpoint)
**Storage**: DuckDB (utxo_lifecycle.duckdb - existing from spec-021)
**Testing**: pytest with TDD discipline
**Target Platform**: Linux server
**Project Type**: Single module addition to existing metrics system
**Performance Goals**: <100ms calculation time (simple z-score math)
**Constraints**: Requires 365 days of historical CDD data for meaningful statistics
**Scale/Scope**: Single endpoint, single calculator module

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|-----------|-------|--------|
| I. Code Quality & Simplicity | Simple z-score calculation, no over-engineering | PASS |
| II. Test-First Discipline | TDD required, tests before implementation | PASS |
| III. User Experience Consistency | Follows existing `/api/metrics/*` patterns | PASS |
| IV. Performance Standards | Simple math, well within <100ms target | PASS |
| V. Data Privacy & Security | Local-only processing, no external APIs | PASS |

**Gate Status**: PASS - All constitutional principles satisfied.

## Project Structure

### Documentation (this feature)

```
specs/027-binary-cdd/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api.yaml         # OpenAPI spec
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```
scripts/
├── metrics/
│   ├── cdd_vdd.py           # Existing CDD calculator (spec-021)
│   └── binary_cdd.py        # NEW: Binary CDD calculator
└── models/
    └── metrics_models.py    # ADD: BinaryCDDResult dataclass

api/
└── main.py                  # ADD: /api/metrics/binary-cdd endpoint

tests/
└── test_binary_cdd.py       # NEW: TDD tests
```

**Structure Decision**: Single project structure - adding to existing metrics infrastructure with one new calculator module, one dataclass, and one API endpoint.

## Complexity Tracking

*No violations - implementation follows KISS/YAGNI principles*

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| No custom statistics | Use numpy.mean/std | Standard library sufficient |
| No caching layer | Query DuckDB directly | 365-day window is fast enough |
| No separate service | Add to existing API | Single endpoint doesn't justify new service |

## Post-Design Constitution Re-Check

*Re-evaluated after Phase 1 design completion*

| Principle | Design Artifact | Compliance |
|-----------|-----------------|------------|
| I. KISS/YAGNI | data-model.md | PASS - Single dataclass, minimal fields |
| II. TDD | tasks.md (pending) | PASS - TDD tests defined first |
| III. UX Consistency | contracts/api.yaml | PASS - Matches existing `/api/metrics/*` patterns |
| IV. Performance | research.md | PASS - Simple z-score math, <100ms |
| V. Privacy | quickstart.md | PASS - Local DuckDB only, no external APIs |

**Final Gate Status**: PASS - Design ready for task generation.
