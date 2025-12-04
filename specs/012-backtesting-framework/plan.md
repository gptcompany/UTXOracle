# Implementation Plan: Backtesting Framework

**Branch**: `012-backtesting-framework` | **Date**: 2025-12-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/012-backtesting-framework/spec.md`

## Summary

Implement a backtesting framework to validate all on-chain metrics and fusion signals against historical data (2024-2025). Calculate Sharpe ratio, win rate, max drawdown, and other performance metrics. Enable comparison between different signal combinations and weight configurations.

**Primary Value**: Empirical validation of signal predictive power before production deployment

## Technical Context

**Language/Version**: Python 3.11+ (matches existing codebase)
**Primary Dependencies**: None required (pure Python); pandas optional for DataFrame convenience
**Storage**: DuckDB (read from `prices` table, write to `backtest_results` table)
**Testing**: pytest with fixtures from `tests/fixtures/`
**Target Platform**: Linux server (same as daily_analysis.py)
**Project Type**: Single project (new backtest module)
**Performance Goals**: <60s for 365-day backtest
**Constraints**: Pure Python, backward compatible, no look-ahead bias
**Scale/Scope**: Historical data 672+ days, multiple signal sources

## Constitution Check

### Principle I: Code Quality & Simplicity ✅ PASS

| Requirement | Status | Evidence |
|-------------|--------|----------|
| KISS: boring technology | ✅ | Pure Python, standard algorithms |
| YAGNI: no generic solutions | ✅ | Specific to UTXOracle signals |
| Single purpose per module | ✅ | `backtest/` package with focused modules |
| Minimize dependencies | ✅ | pandas optional, no ML libraries |

### Principle II: Test-First Discipline ✅ PASS

| Requirement | Status | Evidence |
|-------------|--------|----------|
| TDD RED-GREEN-REFACTOR | ✅ | Tests first for each metric |
| 80% coverage minimum | ✅ | Target 85% |
| Integration tests | ✅ | Full backtest pipeline test |

### Principle III: User Experience Consistency ✅ PASS

| Requirement | Status | Evidence |
|-------------|--------|----------|
| CLI standards | ✅ | Follow existing patterns |
| Output format | ✅ | JSON + human-readable |

### Principle IV: Performance Standards ✅ PASS

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Processing speed | ✅ | <60s for 365 days |
| Memory limits | ✅ | <500MB for 1-year backtest |

### Principle V: Data Privacy & Security ✅ PASS

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Local-first processing | ✅ | All data local (DuckDB) |
| No external APIs | ✅ | Pure Python, local data |

**Constitution Gate: PASSED**

## Project Structure

### Documentation (this feature)

```
specs/012-backtesting-framework/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code

```
scripts/
├── backtest/
│   ├── __init__.py          # Public API
│   ├── engine.py            # Core backtest logic
│   ├── data_loader.py       # Historical data loading
│   ├── metrics.py           # Performance calculations
│   └── optimizer.py         # Weight optimization

tests/
├── test_backtest.py         # Unit tests
└── integration/
    └── test_backtest_pipeline.py

api/
└── main.py                  # Add /api/backtest/* endpoints
```

## Phase 0: Research

See [research.md](./research.md)

## Phase 1: Design

See [data-model.md](./data-model.md), [quickstart.md](./quickstart.md)
