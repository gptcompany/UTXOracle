# Implementation Plan: PRO Risk Metric

**Branch**: `033-pro-risk-metric` | **Date**: 2025-12-25 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/033-pro-risk-metric/spec.md`

## Summary

Implement a composite 0-1 scale risk metric that aggregates 6 on-chain signals (MVRV Z-Score, SOPR, Reserve Risk, Puell Multiple, NUPL, HODL Waves) using historical percentile normalization. Provides single-glance market cycle position with zone classification (extreme_fear → extreme_greed).

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Existing metrics modules (spec-007, 016, 017, 018), Pydantic for models
**Storage**: DuckDB tables (`risk_percentiles`, `pro_risk_daily`) per research decision
**Testing**: pytest with existing fixtures from `tests/fixtures/`
**Target Platform**: Linux server (same as UTXOracle)
**Project Type**: single (extends existing scripts/metrics/)
**Performance Goals**: Daily calculation <1s, percentile lookup O(1) with pre-computed data
**Constraints**: No external APIs (privacy-first per Constitution V), all inputs from existing specs
**Scale/Scope**: Single metric aggregator, ~200 LOC

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Code Quality & Simplicity | PASS | Single-purpose module, uses existing metrics, no new dependencies |
| II. Test-First Discipline | PASS | Will use `pytest-test-generator` skill, TDD workflow |
| III. User Experience Consistency | PASS | Follows existing CLI patterns (-d flag), JSON output |
| IV. Performance Standards | PASS | Daily calculation, no real-time requirements |
| V. Data Privacy & Security | PASS | All inputs from local blockchain data, no external APIs |

**No violations. Proceeding to Phase 0.**

## Project Structure

### Documentation (this feature)

```
specs/033-pro-risk-metric/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```
scripts/metrics/
├── pro_risk.py              # Core PRO Risk calculation
├── puell_multiple.py        # Puell Multiple (new)
├── init_risk_db.py          # DuckDB schema setup
├── bootstrap_percentiles.py # 4-year historical data bootstrap
└── [existing metrics]       # Input sources (sopr.py, nupl.py, etc.)

api/
├── main.py              # Existing FastAPI (add route)
├── routes/risk.py       # PRO Risk endpoints
└── models/risk_models.py # Pydantic models

tests/
├── test_pro_risk.py     # Unit tests
├── test_api_risk.py     # API tests
└── fixtures/            # Test data
```

**Structure Decision**: Extends existing `scripts/metrics/` pattern. Single module `pro_risk.py` with API endpoint added to `api/main.py`.

## Complexity Tracking

*No violations to justify - design follows KISS principles.*
