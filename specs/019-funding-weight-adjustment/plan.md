# Implementation Plan: Derivatives Weight Reduction

**Branch**: `019-funding-weight-adjustment` | **Date**: 2025-12-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/019-funding-weight-adjustment/spec.md`

## Summary

Reduce derivatives signal weights (Funding Rate + Open Interest) from 21% to 10% in Monte Carlo Fusion, redistributing to higher-evidence signals (whale, wasserstein, cointime, sopr). This addresses the LAGGING nature of derivatives indicators documented in Coinbase Research (2024).

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: DuckDB (existing), pytest (testing)
**Storage**: N/A (configuration change only)
**Testing**: pytest with existing test suite
**Target Platform**: Linux server (same as existing)
**Project Type**: Single project (existing codebase)
**Performance Goals**: <10ms per fusion call (no regression)
**Constraints**: Weights must sum to 1.0, backward compatibility required
**Scale/Scope**: 1 module modification, 1 test file update

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Code Quality & Simplicity** | ✅ PASS | Simple weight adjustment, no new abstractions |
| **II. Test-First Discipline** | ✅ PASS | Update existing tests, add SOPR integration test |
| **III. UX Consistency** | ✅ PASS | No user-facing changes |
| **IV. Performance Standards** | ✅ PASS | <10ms target maintained |
| **V. Data Privacy & Security** | ✅ PASS | No external data, local processing only |

**Gate Result**: ✅ PASS - All principles satisfied

## Project Structure

### Documentation (this feature)

```
specs/019-funding-weight-adjustment/
├── plan.md              # This file
├── research.md          # Phase 0 output (minimal - straightforward change)
├── data-model.md        # Phase 1 output (N/A - no new data models)
├── quickstart.md        # Phase 1 output (testing instructions)
├── contracts/           # Phase 1 output (N/A - internal API only)
└── tasks.md             # Already created
```

### Source Code (repository root)

```
scripts/
├── metrics/
│   ├── monte_carlo_fusion.py   # MODIFY: Update ENHANCED_WEIGHTS, add SOPR params
│   └── sopr.py                 # EXISTS: SOPR calculation (spec-016)
└── daily_analysis.py           # OPTIONAL: Pass SOPR to fusion

tests/
└── test_monte_carlo_fusion.py  # MODIFY: Update weight assertions, add SOPR test
```

**Structure Decision**: Existing single-project structure. Only modifying 2 files in `scripts/metrics/` and 1 test file.

## Complexity Tracking

*No violations - this is a minimal configuration change*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | - | - |

---

## Phase 0: Research

### Research Questions

1. **SOPR Integration**: How does `sopr.py` expose its signal for fusion?
2. **Weight Validation**: Best practice for ensuring weights sum to 1.0?
3. **Backward Compatibility**: How to handle missing SOPR parameters?

### Findings

**Q1: SOPR Integration**
- `sopr.py` provides `BlockSOPR` dataclass with `aggregate_sopr`, `sth_sopr`, `lth_sopr`
- Signal extraction: Use `aggregate_sopr` value, derive vote from deviation from 1.0
- Confidence: Based on `valid_outputs` count relative to `min_samples`

**Q2: Weight Validation**
- Add assertion after `ENHANCED_WEIGHTS` definition
- `assert abs(sum(ENHANCED_WEIGHTS.values()) - 1.0) < 0.001`
- Fail fast on module import if misconfigured

**Q3: Backward Compatibility**
- Use `Optional[float] = None` for new parameters
- Weight normalization already handles missing components
- No breaking change to existing callers

---

## Phase 1: Design

### Data Model Changes

**No new data models required.** Existing structures:
- `EnhancedFusionResult` - add `sopr_weight: float = 0.0` field

### API Contract Changes

**Internal API only - no external contracts.**

Function signature update:
```python
def enhanced_fusion(
    # ... existing params ...
    sopr_vote: Optional[float] = None,
    sopr_conf: Optional[float] = None,
    # ...
) -> EnhancedFusionResult
```

### Configuration Changes

```python
# BEFORE (total: 1.00)
ENHANCED_WEIGHTS = {
    "whale": 0.21,
    "utxo": 0.12,
    "funding": 0.12,
    "oi": 0.09,
    "power_law": 0.09,
    "symbolic": 0.12,
    "fractal": 0.09,
    "wasserstein": 0.04,
    "cointime": 0.12,
}

# AFTER (total: 1.00)
ENHANCED_WEIGHTS = {
    "whale": 0.24,      # +0.03
    "utxo": 0.12,       # unchanged
    "funding": 0.05,    # -0.07
    "oi": 0.05,         # -0.04
    "power_law": 0.09,  # unchanged
    "symbolic": 0.12,   # unchanged
    "fractal": 0.09,    # unchanged
    "wasserstein": 0.08,# +0.04
    "cointime": 0.14,   # +0.02
    "sopr": 0.02,       # NEW
}
```

---

## Quickstart

### Prerequisites
- Python 3.11+
- `uv` package manager
- Existing test suite passing

### Development Setup
```bash
# Ensure on feature branch
git checkout 019-funding-weight-adjustment

# Install dependencies
uv sync

# Verify existing tests pass
uv run pytest tests/test_monte_carlo_fusion.py -v
```

### Implementation Steps
1. Update `ENHANCED_WEIGHTS` in `scripts/metrics/monte_carlo_fusion.py`
2. Add weight sum assertion
3. Add SOPR parameters to `enhanced_fusion()`
4. Update `EnhancedFusionResult` dataclass
5. Update tests

### Verification
```bash
# Run tests
uv run pytest tests/test_monte_carlo_fusion.py -v

# Verify weights sum
python -c "from scripts.metrics.monte_carlo_fusion import ENHANCED_WEIGHTS; print(sum(ENHANCED_WEIGHTS.values()))"
# Expected: 1.0
```
