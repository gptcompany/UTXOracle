# Implementation Plan: Bitcoin Price Power Law Model

**Branch**: `034-price-power-law` | **Date**: 2025-12-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/034-price-power-law/spec.md`

## Summary

Implement the Bitcoin Power Law price model - a mathematical relationship between Bitcoin's price and time since genesis block (2009-01-03). This model provides long-term fair value estimation using log-log linear regression on historical prices. Key deliverables: core algorithm module, API endpoint, and frontend visualization chart.

## Technical Context

**Language/Version**: Python 3.11 (per constitution - "boring technology")
**Primary Dependencies**: numpy (already in project), FastAPI (existing API)
**Storage**: DuckDB (existing `daily_prices` table for historical data)
**Testing**: pytest (existing test infrastructure)
**Target Platform**: Linux server (existing production environment)
**Project Type**: web (backend API + frontend visualization)
**Performance Goals**: <50ms model prediction, <100ms API response
**Constraints**: Use existing `daily_prices` table for model fitting, monthly refresh schedule
**Scale/Scope**: Single model, 3 API endpoints, 1 chart component

## Constitution Check (Pre-Design)

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Code Quality & Simplicity ✅ PASS

| Criterion | Assessment | Status |
|-----------|------------|--------|
| KISS/YAGNI | Single-purpose module for power law calculation | ✅ |
| Boring technology | Python + numpy (existing deps) | ✅ |
| Module purpose | One module (`scripts/models/power_law.py`) = one purpose | ✅ |
| Minimal dependencies | Uses numpy (already in project), no new deps | ✅ |

### Principle II: Test-First Discipline ✅ PASS

| Criterion | Assessment | Status |
|-----------|------------|--------|
| TDD cycle | Tests BEFORE implementation | ✅ Required |
| Coverage target | 80% minimum | ✅ Required |
| Integration tests | API endpoint tests required | ✅ Required |
| Test location | `tests/test_power_law.py` | ✅ |

### Principle III: User Experience Consistency ✅ PASS

| Criterion | Assessment | Status |
|-----------|------------|--------|
| API Standards | REST endpoints match existing `/api/` patterns | ✅ |
| Visualization | Plotly.js chart consistent with existing dashboard | ✅ |
| Response format | JSON with Pydantic models | ✅ |

### Principle IV: Performance Standards ✅ PASS

| Criterion | Assessment | Status |
|-----------|------------|--------|
| API latency | <100ms target (simple calculation) | ✅ |
| Model fitting | <5s for ~5000 data points (monthly) | ✅ |
| Memory | Minimal - only model coefficients in memory | ✅ |

### Principle V: Data Privacy & Security ✅ PASS

| Criterion | Assessment | Status |
|-----------|------------|--------|
| Local-first | Uses existing local `daily_prices` table | ✅ |
| No external APIs | Model fit from local historical data | ✅ |
| Input validation | Pydantic models for API params | ✅ |

**Gate Status: ✅ PASS** - No constitution violations identified.

## Project Structure

### Documentation (this feature)

```
specs/034-price-power-law/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```
# Web application structure (backend + frontend)
scripts/models/
└── price_power_law.py        # Core model (named to avoid conflict with spec-009 power_law.py)

api/
├── main.py                   # Add /models/power-law endpoints
└── models/
    └── power_law_models.py   # Pydantic response models

frontend/
├── charts/
│   └── power_law_chart.js    # Plotly.js visualization
└── power_law.html            # Standalone chart page

tests/
├── test_price_power_law.py   # Unit tests for model
└── test_api_power_law.py     # API integration tests
```

**Structure Decision**: Web application structure (existing pattern). Core model in `scripts/models/` (following existing `metrics_models.py` pattern), API endpoints in `api/main.py`, frontend chart in `frontend/charts/`.

**Note**: Using `price_power_law.py` to distinguish from existing `scripts/metrics/power_law.py` (spec-009 UTXO distribution power law).

## Complexity Tracking

*No constitution violations requiring justification.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | - | - |

---

## Constitution Check (Post-Design)

*Re-evaluation after Phase 1 artifacts generated.*

### Principle I: Code Quality & Simplicity ✅ PASS

| Criterion | Post-Design Assessment | Status |
|-----------|------------------------|--------|
| KISS/YAGNI | 4 endpoints (model, predict, history, recalibrate) - minimal | ✅ |
| Boring technology | numpy log-log regression, no exotic algorithms | ✅ |
| Module structure | `price_power_law.py` (logic) + `power_law_models.py` (Pydantic) | ✅ |
| No over-engineering | Default coefficients + optional recalibration, not complex | ✅ |

### Principle II: Test-First Discipline ✅ PASS

| Criterion | Post-Design Assessment | Status |
|-----------|------------------------|--------|
| Test plan | Unit tests for core functions, API integration tests | ✅ |
| Coverage target | All public functions testable | ✅ |
| Test files | `test_price_power_law.py`, `test_api_power_law.py` | ✅ |

### Principle III: User Experience Consistency ✅ PASS

| Criterion | Post-Design Assessment | Status |
|-----------|------------------------|--------|
| API patterns | `/api/v1/models/power-law` follows existing structure | ✅ |
| Response format | OpenAPI 3.1 contract with Pydantic validation | ✅ |
| Frontend | Plotly.js log-log chart matches existing dashboard style | ✅ |
| Quickstart | Clear usage examples provided | ✅ |

### Principle IV: Performance Standards ✅ PASS

| Criterion | Post-Design Assessment | Status |
|-----------|------------------------|--------|
| API latency | Simple formula evaluation <10ms | ✅ |
| History endpoint | DuckDB query + model calc, <500ms for 5000 points | ✅ |
| Memory footprint | 6 floats per model, negligible | ✅ |

### Principle V: Data Privacy & Security ✅ PASS

| Criterion | Post-Design Assessment | Status |
|-----------|------------------------|--------|
| Local-first | All data from local `daily_prices` table | ✅ |
| No external APIs | No network calls for model fit or prediction | ✅ |
| Input validation | Query params validated via FastAPI/Pydantic | ✅ |

**Post-Design Gate Status: ✅ PASS** - Design consistent with constitution.

---

## Generated Artifacts

| Artifact | Path | Status |
|----------|------|--------|
| plan.md | `specs/034-price-power-law/plan.md` | ✅ Complete |
| research.md | `specs/034-price-power-law/research.md` | ✅ Complete |
| data-model.md | `specs/034-price-power-law/data-model.md` | ✅ Complete |
| contracts/openapi.yaml | `specs/034-price-power-law/contracts/openapi.yaml` | ✅ Complete |
| quickstart.md | `specs/034-price-power-law/quickstart.md` | ✅ Complete |
| tasks.md | `specs/034-price-power-law/tasks.md` | ✅ Complete |
