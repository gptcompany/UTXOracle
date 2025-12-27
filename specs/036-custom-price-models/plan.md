# Implementation Plan: Custom Price Models Framework

**Branch**: `036-custom-price-models` | **Date**: 2025-12-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/036-custom-price-models/spec.md`

## Summary

Implement a flexible framework for custom Bitcoin price models enabling experimentation with various valuation approaches (Power Law, S2F, Thermocap, UTXOracle). The framework provides: abstract base class (`PriceModel` ABC), model registry pattern, ensemble aggregation, and unified backtesting. Key deliverables: model framework in `scripts/models/`, API endpoints for model comparison, integration with existing backtest infrastructure.

## Technical Context

**Language/Version**: Python 3.11 (per constitution - "boring technology")
**Primary Dependencies**: numpy, pandas (existing), FastAPI (existing API), abc (stdlib)
**Storage**: Uses existing `daily_prices` DuckDB table; model configs in `config/models.yaml`
**Testing**: pytest (existing infrastructure), TDD mandatory
**Target Platform**: Linux server (existing production environment)
**Project Type**: web (backend API + optional frontend visualization)
**Performance Goals**: <100ms model prediction, <500ms backtest per 1000 days
**Constraints**: Must integrate with existing `scripts/backtest/engine.py`, no breaking changes to spec-034 Power Law
**Scale/Scope**: 4 built-in models (Power Law, S2F, Thermocap, UTXOracle wrapper), 5 API endpoints, 1 ensemble aggregator

## Constitution Check (Pre-Design)

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Code Quality & Simplicity ✅ PASS

| Criterion | Assessment | Status |
|-----------|------------|--------|
| KISS/YAGNI | Framework abstracts shared model logic; 3+ use cases justify abstraction | ✅ |
| Boring technology | Python ABC + numpy (existing deps), no new frameworks | ✅ |
| Module purpose | One module per model (power_law.py, stock_to_flow.py, etc.) | ✅ |
| Minimal dependencies | Uses pandas (already in project), no new deps | ✅ |
| Code reuse | Wraps existing `price_power_law.py`, extends existing backtest engine | ✅ |

### Principle II: Test-First Discipline ✅ PASS

| Criterion | Assessment | Status |
|-----------|------------|--------|
| TDD cycle | Tests BEFORE implementation | ✅ Required |
| Coverage target | 80% minimum for all model modules | ✅ Required |
| Integration tests | Model registry, ensemble, backtest integration | ✅ Required |
| Test location | `tests/test_models/` (new directory for model tests) | ✅ |

### Principle III: User Experience Consistency ✅ PASS

| Criterion | Assessment | Status |
|-----------|------------|--------|
| API Standards | REST endpoints under `/api/v1/models/` | ✅ |
| Response format | JSON with Pydantic models (existing pattern) | ✅ |
| Backward compatibility | Existing Power Law endpoints unaffected | ✅ |

### Principle IV: Performance Standards ✅ PASS

| Criterion | Assessment | Status |
|-----------|------------|--------|
| API latency | <100ms for single prediction | ✅ |
| Backtest performance | <500ms per 1000 data points | ✅ |
| Memory | Model state minimal (coefficients only) | ✅ |

### Principle V: Data Privacy & Security ✅ PASS

| Criterion | Assessment | Status |
|-----------|------------|--------|
| Local-first | All data from local sources (DuckDB, blockchain) | ✅ |
| No external APIs | S2F/Thermocap data derived from local blockchain data | ✅ |
| Input validation | Pydantic models for all API params | ✅ |

**Gate Status: ✅ PASS** - No constitution violations identified.

## Project Structure

### Documentation (this feature)

```
specs/036-custom-price-models/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```
# Extend existing web application structure

scripts/models/
├── __init__.py              # Update exports
├── base.py                  # PriceModel ABC, ModelPrediction dataclass
├── registry.py              # ModelRegistry class
├── ensemble.py              # EnsembleModel, EnsembleConfig
├── stock_to_flow.py         # StockToFlowModel
├── thermocap.py             # ThermocapModel
├── utxoracle_model.py       # UTXOracleModel (wrapper)
└── price_power_law.py       # EXISTING (spec-034) - wrap with ABC adapter

scripts/models/backtest/
├── __init__.py
└── model_backtester.py      # Backtester for PriceModel instances

api/models/
├── model_framework.py       # Pydantic models for framework (ModelPrediction, BacktestResult, etc.)
└── power_law_models.py      # EXISTING (spec-034) - unchanged

api/
├── main.py                  # Add new model framework endpoints
└── routes/
    └── models.py            # New router for /api/v1/models/* endpoints

config/
└── models.yaml              # Model configuration

tests/test_models/
├── __init__.py
├── test_base.py             # ABC contract tests
├── test_registry.py         # Registry tests
├── test_ensemble.py         # Ensemble aggregation tests
├── test_stock_to_flow.py    # S2F model tests
├── test_thermocap.py        # Thermocap model tests
├── test_utxoracle_model.py  # UTXOracle wrapper tests
├── test_model_backtester.py # Backtest integration tests
└── test_api_models.py       # API endpoint tests
```

**Structure Decision**: Extends existing `scripts/models/` with new files for ABC, registry, and individual model implementations. Creates new `api/routes/models.py` for cleaner endpoint organization. Uses new test directory `tests/test_models/` to organize model-specific tests.

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
| KISS/YAGNI | 4 models + 1 ensemble, 5 API endpoints - minimal | ✅ |
| Boring technology | ABC + dataclass (stdlib), numpy | ✅ |
| Module structure | One file per model, clear separation | ✅ |
| No over-engineering | Simple registry pattern, no DI frameworks | ✅ |

### Principle II: Test-First Discipline ✅ PASS

| Criterion | Post-Design Assessment | Status |
|-----------|------------------------|--------|
| Test plan | tests/test_models/ directory, TDD for each model | ✅ |
| Coverage target | All public methods testable | ✅ |
| Test files | 8 test files covering all components | ✅ |

### Principle III: User Experience Consistency ✅ PASS

| Criterion | Post-Design Assessment | Status |
|-----------|------------------------|--------|
| API patterns | `/api/v1/models/*` follows existing structure | ✅ |
| Response format | OpenAPI 3.1 contract, Pydantic validation | ✅ |
| Backward compatibility | Existing Power Law endpoints unchanged | ✅ |
| Quickstart | Clear usage examples in quickstart.md | ✅ |

### Principle IV: Performance Standards ✅ PASS

| Criterion | Post-Design Assessment | Status |
|-----------|------------------------|--------|
| API latency | Simple formula evaluation <50ms | ✅ |
| Backtest performance | Linear time O(n) per model | ✅ |
| Memory footprint | Coefficients only, ~100 bytes per model | ✅ |

### Principle V: Data Privacy & Security ✅ PASS

| Criterion | Post-Design Assessment | Status |
|-----------|------------------------|--------|
| Local-first | All data from local DuckDB/blockchain | ✅ |
| No external APIs | S2F/Thermocap calculated from blockchain data | ✅ |
| Input validation | Pydantic models for all API params | ✅ |

**Post-Design Gate Status: ✅ PASS** - Design consistent with constitution.

---

## Generated Artifacts

| Artifact | Path | Status |
|----------|------|--------|
| plan.md | `specs/036-custom-price-models/plan.md` | ✅ Complete |
| research.md | `specs/036-custom-price-models/research.md` | ✅ Complete |
| data-model.md | `specs/036-custom-price-models/data-model.md` | ✅ Complete |
| contracts/openapi.yaml | `specs/036-custom-price-models/contracts/openapi.yaml` | ✅ Complete |
| quickstart.md | `specs/036-custom-price-models/quickstart.md` | ✅ Complete |
| tasks.md | `specs/036-custom-price-models/tasks.md` | ✅ Complete |
