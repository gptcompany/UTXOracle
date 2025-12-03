# Implementation Plan: Derivatives Historical Integration

**Branch**: `008-derivatives-historical` | **Date**: 2025-12-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-derivatives-historical/spec.md`

## Summary

Integrate Binance Futures historical data (Funding Rates, Open Interest) from the existing LiquidationHeatmap DuckDB into UTXOracle's signal fusion. Uses DuckDB `ATTACH` for cross-database reads (zero data duplication). Extends spec-007 Monte Carlo fusion from 2 components (whale + utxo) to 4 components (whale + utxo + funding + oi). Includes backtest script for historical validation.

## Technical Context

**Language/Version**: Python 3.11+ (matches existing UTXOracle)
**Primary Dependencies**: DuckDB (already installed), dataclasses (stdlib), spec-007 Monte Carlo fusion
**Storage**: DuckDB (UTXOracle cache) + DuckDB (LiquidationHeatmap - READ_ONLY ATTACH)
**Testing**: pytest (existing test infrastructure)
**Target Platform**: Linux server (Ubuntu 24.04, same as production)
**Project Type**: Single project (extends existing scripts/)
**Performance Goals**: Cross-DB query <500ms, signal calculation <100ms (inherits spec-007)
**Constraints**: Zero data duplication, graceful degradation if LiquidationHeatmap unavailable
**Scale/Scope**: ~500 LOC new code, 4 user stories, integrates with existing daily_analysis.py

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Code Quality & Simplicity (KISS/YAGNI)

| Requirement | Status | Notes |
|-------------|--------|-------|
| Boring technology | ✅ PASS | Python, DuckDB - already used in project |
| Single purpose modules | ✅ PASS | funding_rate_reader.py, oi_reader.py, enhanced_fusion.py |
| Minimize dependencies | ✅ PASS | Zero new dependencies (DuckDB ATTACH reuses existing) |
| No premature abstraction | ✅ PASS | No exchange abstraction until Bybit added (spec-009) |
| Delete dead code | ⏳ N/A | New feature, no dead code yet |

### Principle II: Test-First Discipline

| Requirement | Status | Notes |
|-------------|--------|-------|
| RED phase first | ✅ WILL ENFORCE | Tests in test_derivatives_integration.py before impl |
| 80% coverage | ✅ WILL ENFORCE | All signal calculation functions covered |
| Integration tests | ✅ WILL ENFORCE | Cross-DB query, graceful degradation tests |

### Principle III: User Experience Consistency

| Requirement | Status | Notes |
|-------------|--------|-------|
| CLI standards | ⏳ N/A | No new CLI (backtest script follows existing patterns) |
| Visualization | ⏳ N/A | No new visualization (uses existing whale dashboard) |
| API standards | ✅ PASS | Extends /api/metrics/latest response |

### Principle IV: Performance Standards

| Requirement | Status | Notes |
|-------------|--------|-------|
| Cross-DB latency <500ms | ✅ WILL ENFORCE | Tested in SC-001 |
| Fusion <100ms | ✅ INHERITED | From spec-007 Monte Carlo |

### Principle V: Data Privacy & Security

| Requirement | Status | Notes |
|-------------|--------|-------|
| Local-first processing | ✅ PASS | LiquidationHeatmap is self-hosted |
| No external APIs | ✅ PASS | Reads local DuckDB only |
| Path configurable | ✅ PASS | Via .env (no hardcoded paths in code) |

**GATE RESULT**: ✅ PASS - No constitution violations.

## Project Structure

### Documentation (this feature)

```
specs/008-derivatives-historical/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (API schemas)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```
scripts/
├── derivatives/                     # NEW: Derivatives integration module
│   ├── __init__.py                 # Module init with helpers
│   ├── funding_rate_reader.py      # US1: Funding rate from LiquidationHeatmap
│   ├── oi_reader.py                # US2: Open Interest from LiquidationHeatmap
│   └── enhanced_fusion.py          # US3: 4-component Monte Carlo
├── backtest_derivatives.py         # US4: Historical backtesting script
├── daily_analysis.py               # MODIFY: Add derivatives to main flow
└── metrics/
    └── monte_carlo_fusion.py       # EXTEND: Support 4 components

api/
└── main.py                         # MODIFY: Add derivatives to /api/metrics/latest

tests/
├── test_derivatives_integration.py  # NEW: Full test suite
└── integration/
    └── test_derivatives_e2e.py      # NEW: End-to-end with real LiquidationHeatmap
```

**Structure Decision**: Extends existing UTXOracle structure. New `scripts/derivatives/` module follows pattern of `scripts/metrics/` from spec-007. No new architectural patterns introduced.

## Complexity Tracking

*No constitution violations - table not required.*

## Implementation Phases

### Phase 0: Research

See [research.md](./research.md) for:
- LiquidationHeatmap DuckDB schema discovery
- Funding rate normalization approach
- OI change calculation methodology
- Weight optimization strategy

### Phase 1: Design & Contracts

See:
- [data-model.md](./data-model.md) - Entity definitions
- [contracts/](./contracts/) - API schemas (Pydantic models)
- [quickstart.md](./quickstart.md) - Developer getting started guide

### Phase 2: Tasks

See [tasks.md](./tasks.md) (generated by `/speckit.tasks`)

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LiquidationHeatmap schema changes | Pin schema version, add validation |
| Cross-DB lock contention | READ_ONLY mode, connection pooling |
| Stale derivatives data | Check data freshness, log warnings |
| Weight overfitting in backtest | Use holdout validation set |
