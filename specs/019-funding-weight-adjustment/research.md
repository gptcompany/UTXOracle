# Research: spec-019 Derivatives Weight Reduction

## Research Questions

### Q1: SOPR Signal Integration

**Decision**: Use `aggregate_sopr` from `BlockSOPR` dataclass, convert to vote using deviation from 1.0

**Rationale**:
- SOPR = 1.0 is the breakeven point (neutral)
- SOPR > 1.0 = coins sold at profit (bearish pressure)
- SOPR < 1.0 = coins sold at loss (bullish - capitulation signal)
- This aligns with existing vote convention (-1 to +1)

**Implementation**:
```python
def sopr_to_vote(sopr_value: float, confidence: float) -> tuple[float, float]:
    """Convert SOPR to fusion vote.

    SOPR > 1.0 = profit taking = bearish = negative vote
    SOPR < 1.0 = capitulation = bullish = positive vote
    SOPR = 1.0 = neutral
    """
    if sopr_value > 1.0:
        # Profit taking - bearish signal
        vote = -min(0.8, (sopr_value - 1.0) * 2)
    elif sopr_value < 1.0:
        # Capitulation - bullish signal
        vote = min(0.8, (1.0 - sopr_value) * 2)
    else:
        vote = 0.0
    return (vote, confidence)
```

**Alternatives Considered**:
1. Use STH-SOPR only (more reactive but less stable)
2. Use LTH-SOPR only (better for cycle signals but less frequent)
3. Weighted average of STH/LTH (more complex, deferred to future spec)

### Q2: Weight Validation Approach

**Decision**: Add module-level assertion after `ENHANCED_WEIGHTS` definition

**Rationale**:
- Fail fast on import if weights misconfigured
- Prevents silent runtime errors
- Zero performance overhead (runs once at import)
- Standard Python pattern for configuration validation

**Implementation**:
```python
ENHANCED_WEIGHTS = { ... }

# Validate weights sum to 1.0
_weight_sum = sum(ENHANCED_WEIGHTS.values())
assert abs(_weight_sum - 1.0) < 0.001, f"ENHANCED_WEIGHTS sum to {_weight_sum}, expected 1.0"
```

**Alternatives Considered**:
1. Runtime validation in `enhanced_fusion()` - rejected (per-call overhead)
2. Test-only validation - rejected (not fail-fast enough)
3. Pydantic model validation - rejected (over-engineering for dict)

### Q3: Backward Compatibility Strategy

**Decision**: Use `Optional[float] = None` for new parameters, existing normalization handles missing components

**Rationale**:
- Existing callers continue to work without modification
- Weight normalization already redistributes weights for missing signals
- No breaking change to API contract
- Gradual adoption possible

**Implementation**:
```python
def enhanced_fusion(
    # ... existing params ...
    sopr_vote: Optional[float] = None,  # NEW
    sopr_conf: Optional[float] = None,  # NEW
    weights: Optional[dict] = None,
) -> EnhancedFusionResult:
    w = weights if weights else ENHANCED_WEIGHTS.copy()

    # Existing normalization handles missing components
    if sopr_vote is not None and sopr_conf is not None:
        components["sopr"] = (sopr_vote, sopr_conf)
```

**Alternatives Considered**:
1. Required parameters with migration - rejected (breaking change)
2. New function `enhanced_fusion_v2()` - rejected (code duplication)
3. Builder pattern - rejected (over-engineering)

## Evidence Review

### Coinbase Research (2024) - Funding Rate Analysis

**Finding**: Funding rate is a lagging indicator
- Follows price action by 1-4 hours on average
- Predictive value diminishes in trending markets
- Better suited for mean-reversion strategies than trend following

**Impact on spec-019**: Validates reduction of `funding` weight from 0.12 to 0.05

### Omole & Enke (2024) - SOPR Study

**Finding**: 82.44% directional accuracy for SOPR-based signals
- STH-SOPR particularly effective for short-term reversals
- LTH-SOPR signals rare but high conviction
- Aggregate SOPR balances reactivity and stability

**Impact on spec-019**: Validates adding SOPR signal with 0.02 weight

### Horvath (2021) - Wasserstein Distance

**Finding**: Grade A evidence for distribution shift detection
- 5% alpha improvement in regime detection
- Robust to outliers unlike mean-based measures
- Computationally efficient for real-time use

**Impact on spec-019**: Validates increasing `wasserstein` weight from 0.04 to 0.08

## Dependencies Verified

| Dependency | Status | Location |
|------------|--------|----------|
| `sopr.py` | ✅ On main | `scripts/metrics/sopr.py` |
| `BlockSOPR` | ✅ Exported | `scripts/metrics/sopr.py:BlockSOPR` |
| `monte_carlo_fusion.py` | ✅ Exists | `scripts/metrics/monte_carlo_fusion.py` |
| `EnhancedFusionResult` | ✅ Exists | `scripts/metrics/monte_carlo_fusion.py` |

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Backtest performance degradation | Low | Medium | Run backtest before merge |
| Missing SOPR data in some blocks | Medium | Low | Graceful handling via None defaults |
| Weight sum rounding errors | Low | Low | 0.001 tolerance in assertion |
