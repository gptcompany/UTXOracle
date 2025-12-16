# Implementation Plan: NUPL Oscillator

**Branch**: `022-nupl-oscillator` | **Date**: 2025-12-16 | **Spec**: [spec-022](spec.md)
**Input**: Feature specification from `/specs/022-nupl-oscillator/spec.md`

## Summary

Implement a dedicated NUPL (Net Unrealized Profit/Loss) Oscillator module with zone classification for market cycle analysis. Reuses existing `calculate_nupl()` from `realized_metrics.py` and adds zone classification (CAPITULATION, HOPE_FEAR, OPTIMISM, BELIEF, EUPHORIA) with API endpoint for CheckOnChain dashboard integration.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: DuckDB, FastAPI, Pydantic
**Storage**: DuckDB (`utxo_lifecycle_full` VIEW, `utxo_snapshots` table)
**Testing**: pytest
**Target Platform**: Linux server
**Project Type**: Single project (backend metrics module)
**Performance Goals**: <100ms API response time
**Constraints**: Reuse existing `realized_metrics.py` infrastructure
**Scale/Scope**: Single API endpoint, ~190 lines of new code

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Code Quality & Simplicity** | PASS | ~190 LOC, single-purpose module, reuses existing infrastructure |
| **II. Test-First Discipline** | PASS | TDD workflow defined in tasks.md |
| **III. User Experience Consistency** | PASS | Follows existing `/api/metrics/*` pattern |
| **IV. Performance Standards** | PASS | Simple calculation, <100ms expected |
| **V. Data Privacy & Security** | PASS | Local-only data, no external API calls |

## Project Structure

### Documentation (this feature)

```
specs/022-nupl-oscillator/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api.yaml         # OpenAPI contract
└── tasks.md             # Phase 2 output (exists)
```

### Source Code (repository root)

```
scripts/
├── metrics/
│   ├── realized_metrics.py    # EXISTING - calculate_nupl() function
│   └── nupl.py                # NEW - Zone classification, orchestrator
└── models/
    └── metrics_models.py      # EDIT - Add NUPLResult, NUPLZone

api/
└── main.py                    # EDIT - Add GET /api/metrics/nupl

tests/
└── test_nupl.py               # NEW - Unit tests
```

**Structure Decision**: Single project structure. New module `scripts/metrics/nupl.py` integrates with existing metrics infrastructure.

## Complexity Tracking

*No violations - implementation is straightforward.*

| Aspect | Assessment |
|--------|------------|
| New dependencies | None (uses existing DuckDB, FastAPI) |
| New abstractions | NUPLZone enum (minimal, justified) |
| Code reuse | High (~80% from existing realized_metrics.py) |
| API surface | Single endpoint following established pattern |

## Implementation Phases

### Phase 1: Setup (T001-T002)
- Add `NUPLResult` dataclass to `scripts/models/metrics_models.py`
- Add `NUPLZone` enum to same file

### Phase 2: Tests (T003-T009) - TDD RED
- Create `tests/test_nupl.py` with zone classification tests
- Test edge cases (zero market cap, negative values)

### Phase 3: Implementation (T010-T013) - TDD GREEN
- Create `scripts/metrics/nupl.py` with `calculate_nupl_signal()`
- Implement `_classify_zone()` helper
- Add structured logging

### Phase 4: API (T014-T017)
- Add `GET /api/metrics/nupl` endpoint to `api/main.py`
- Run all tests to verify

## Effort Estimate

| Phase | Tasks | Estimate |
|-------|-------|----------|
| Setup | T001-T002 | 15 min |
| Tests (RED) | T003-T009 | 20 min |
| Implementation (GREEN) | T010-T013 | 25 min |
| API | T014-T017 | 15 min |
| Polish | T018-T020 | 10 min |
| **Total** | 20 tasks | **~1.5 hours** |

## Dependencies

- `scripts/metrics/realized_metrics.py` (existing)
- `utxo_lifecycle_full` VIEW (existing)
- `api/main.py` router (existing)

## Generated Artifacts

- `research.md` - Technical decisions and alternatives
- `data-model.md` - Entity definitions and schema
- `contracts/api.yaml` - OpenAPI specification
- `quickstart.md` - Usage examples
