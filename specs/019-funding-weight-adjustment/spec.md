# spec-019: Derivatives Weight Reduction

## Overview

Reduce weight of derivatives signals (Funding Rate + Open Interest) in Monte Carlo Fusion due to their LAGGING nature. Research (Coinbase institutional report) demonstrates derivatives signals follow price action rather than predict it.

## Problem Statement

Current weights in `scripts/metrics/monte_carlo_fusion.py`:
- `funding`: 0.12 (12%)
- `oi`: 0.09 (9%)
- **Total derivatives**: 21% of fusion signal

This overweights LAGGING indicators that provide minimal predictive value.

## Evidence

| Source | Finding |
|--------|---------|
| Coinbase Research (2024) | Funding rate is a lagging indicator |
| Empirical backtest | Derivatives signals show <5% alpha contribution |
| Academic consensus | On-chain metrics outperform derivatives for prediction |

## Proposed Changes

### New Weights

| Signal | Current | New | Delta |
|--------|---------|-----|-------|
| funding | 0.12 | 0.05 | -0.07 |
| oi | 0.09 | 0.05 | -0.04 |
| **Derivatives Total** | 0.21 | 0.10 | -0.11 |

### Weight Redistribution

Redistribute 0.11 to high-evidence signals:

| Signal | Current | New | Delta | Justification |
|--------|---------|-----|-------|---------------|
| whale | 0.21 | 0.24 | +0.03 | Primary signal, proven alpha |
| wasserstein | 0.04 | 0.08 | +0.04 | Grade A evidence (Horvath 2021) |
| cointime | 0.12 | 0.14 | +0.02 | AVIV superiority over MVRV |
| sopr | N/A | 0.02 | +0.02 | NEW: 82.44% accuracy (Omole 2024) |

### Final Weight Distribution

```python
ENHANCED_WEIGHTS = {
    "whale": 0.24,      # +0.03 Primary signal
    "utxo": 0.12,       # unchanged
    "funding": 0.05,    # -0.07 LAGGING
    "oi": 0.05,         # -0.04 LAGGING
    "power_law": 0.09,  # unchanged
    "symbolic": 0.12,   # unchanged
    "fractal": 0.09,    # unchanged
    "wasserstein": 0.08,# +0.04 Grade A
    "cointime": 0.14,   # +0.02 AVIV
    "sopr": 0.02,       # NEW signal
}
# Total: 1.00
```

## Functional Requirements

### FR-001: Update ENHANCED_WEIGHTS
- Modify `scripts/metrics/monte_carlo_fusion.py` with new weights
- Ensure weights sum to 1.0

### FR-002: Add SOPR Signal Integration
- Add `sopr_vote` and `sopr_conf` parameters to `enhanced_fusion()`
- Integrate SOPR from `scripts/metrics/sopr.py`

### FR-003: Backward Compatibility
- Existing API calls without SOPR parameters must work
- Default None for new parameters

## Non-Functional Requirements

### NFR-001: Performance
- No performance regression in fusion calculation
- <10ms per fusion call

### NFR-002: Testing
- Update existing tests with new weights
- Add SOPR integration test

## Acceptance Criteria

1. [ ] `ENHANCED_WEIGHTS` updated with new values
2. [ ] Weights sum verified = 1.0
3. [ ] SOPR signal integrated
4. [ ] All existing tests pass
5. [ ] Backtest shows stable or improved performance

## Dependencies

- `scripts/metrics/sopr.py` (spec-016, already on main)
- `scripts/metrics/monte_carlo_fusion.py`

## Effort Estimate

**1 day** - Simple weight update + SOPR integration

## Files to Modify

1. `scripts/metrics/monte_carlo_fusion.py` - weights + SOPR integration
2. `tests/test_monte_carlo_fusion.py` - update expected weights
3. `scripts/daily_analysis.py` - pass SOPR to fusion (if applicable)
