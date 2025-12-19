# Implementation Plan: Validation Framework

**Branch**: `031-validation-framework` | **Date**: 2025-12-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/031-validation-framework/spec.md`

## Summary

Complete the validation framework for verifying UTXOracle metrics against CheckOnChain.com reference. The framework provides numerical validation (API value comparison), visual validation (screenshot comparison), and automated baseline management. Partially implemented - need to complete visual_validator.py, populate baselines, write tests, and integrate with spec-032 frontend pages.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: httpx (HTTP client), Playwright/Chrome DevTools MCP (screenshots), pytest (testing)
**Storage**: JSON files (baselines, cache, reports)
**Testing**: pytest with validation-specific fixtures
**Target Platform**: Linux (development), GitHub Actions (CI)
**Project Type**: Single project (validation module)
**Performance Goals**: Validation run <60s for all metrics
**Constraints**: Rate limit CheckOnChain requests (1 req/2s), cache for 1 hour
**Scale/Scope**: 8 metrics, 2 validation layers (numerical + visual)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Code Quality & Simplicity | PASS | Pure Python, minimal deps (httpx only), clear single-purpose modules |
| II. Test-First Discipline | PASS | Will write tests for validation framework itself |
| III. User Experience Consistency | PASS | Markdown reports, consistent with CLI standards |
| IV. Performance Standards | PASS | Rate limiting built-in, caching prevents excessive requests |
| V. Data Privacy & Security | PASS | Only fetches public CheckOnChain data, no user data involved |

**Gate Status: PASS** - No violations.

## Project Structure

### Documentation (this feature)

```
specs/031-validation-framework/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── spec.md              # Original spec
```

### Source Code (existing + additions)

```
validation/
├── framework/
│   ├── __init__.py              # EXISTS
│   ├── validator.py             # EXISTS - core validation logic
│   ├── checkonchain_fetcher.py  # EXISTS - reference data fetcher
│   ├── comparison_engine.py     # EXISTS - comparison orchestration
│   └── visual_validator.py      # NEW - screenshot comparison
├── baselines/
│   ├── mvrv_baseline.json       # NEW - populate from CheckOnChain
│   ├── nupl_baseline.json       # NEW
│   ├── sopr_baseline.json       # NEW
│   ├── cdd_baseline.json        # NEW
│   ├── hash_ribbons_baseline.json # NEW
│   └── cost_basis_baseline.json # NEW
├── reports/
│   └── YYYY-MM-DD_validation.md # Generated
├── screenshots/
│   ├── ours/                    # Our chart screenshots
│   └── reference/               # CheckOnChain screenshots
├── tests/
│   ├── __init__.py              # EXISTS
│   ├── test_validator.py        # NEW
│   ├── test_fetcher.py          # NEW
│   └── test_comparison.py       # NEW
└── README.md                    # EXISTS

frontend/metrics/                # FROM spec-032 - validation targets
├── mvrv.html
├── nupl.html
├── sopr.html
├── cost_basis.html
├── hash_ribbons.html
├── binary_cdd.html
├── wallet_waves.html
└── exchange_netflow.html
```

**Structure Decision**: Extend existing `validation/` directory. Visual validator integrates with MCP tools (Playwright/Chrome DevTools) for screenshot capture.

## Existing Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| validator.py | ✅ Complete | Core comparison logic, tolerances defined |
| checkonchain_fetcher.py | ✅ Complete | Plotly.js data extraction, rate limiting, caching |
| comparison_engine.py | ✅ Complete | Orchestration, report generation |
| visual_validator.py | ❌ Missing | Screenshot capture and comparison |
| baselines/*.json | ❌ Empty | Need to populate from CheckOnChain |
| tests/*.py | ❌ Empty | Only __init__.py exists |
| CI/CD | ❌ Missing | GitHub Action for nightly validation |

## Complexity Tracking

*No violations to justify - straightforward completion of existing framework.*

---

## Phase 0: Research Outcomes

See [research.md](research.md) for detailed findings.

**Key Decisions:**
1. Use Playwright MCP for screenshots (already configured)
2. JSON baselines with 1-hour cache
3. Tolerance thresholds per metric (defined in validator.py)
4. Integration with spec-032 frontend pages at `frontend/metrics/*.html`

## Phase 1: Design Outputs

- **Data Model**: [data-model.md](data-model.md) - Baseline and report schemas
- **Quickstart**: [quickstart.md](quickstart.md) - How to run validation

## Next Steps

Run `/speckit.tasks` to generate implementation tasks after design review.
