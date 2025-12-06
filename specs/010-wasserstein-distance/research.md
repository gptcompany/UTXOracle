# Research: Wasserstein Distance Calculator

**Feature**: spec-010 | **Date**: 2025-12-04 | **Status**: Complete

## Research Topics

### 1. Optimal 1D Wasserstein Algorithm

**Question**: What is the most efficient algorithm for computing 1D Wasserstein distance on discrete samples?

**Decision**: Use quantile-based approach with sorted arrays

**Rationale**:
For 1D distributions, the Wasserstein-1 distance (Earth Mover's Distance) simplifies to:

```
W_1(P, Q) = ∫|F_P(x) - F_Q(x)| dx
```

For discrete samples, this can be computed exactly using:

1. **Sort both distributions**: O(n log n)
2. **Interpolate to same length**: Linear interpolation of quantile functions
3. **Sum absolute differences**: O(n)

Total complexity: O(n log n) - dominated by sorting

**Alternatives Considered**:
| Algorithm | Complexity | Pros | Cons |
|-----------|------------|------|------|
| LP Solver | O(n³) | Exact, general | Too slow for 1000+ samples |
| Sinkhorn | O(n² / ε²) | GPU-friendly | Approximation, needs tuning |
| **Quantile (chosen)** | O(n log n) | Exact, fast | 1D only (sufficient for us) |
| CDF Integration | O(n²) | Simple | Slower than quantile |

**Implementation**:
```python
def wasserstein_1d(values_1: list[float], values_2: list[float]) -> float:
    """O(n log n) exact 1D Wasserstein via quantile matching."""
    # Sort both
    sorted_1 = sorted(values_1)
    sorted_2 = sorted(values_2)

    # Interpolate to common length
    n = max(len(sorted_1), len(sorted_2))
    q1 = _interpolate_quantiles(sorted_1, n)
    q2 = _interpolate_quantiles(sorted_2, n)

    # Sum absolute differences
    return sum(abs(a - b) for a, b in zip(q1, q2)) / n
```

**Reference**: Peyré & Cuturi (2019), "Computational Optimal Transport", Chapter 2.3

---

### 2. Rolling Window Strategy

**Question**: How should rolling windows be configured for regime detection?

**Decision**: Fixed-size sliding window with 1-hour step

**Rationale**:
- **Window size**: 144 blocks (~24 hours)
  - Captures full daily distribution
  - Enough samples for statistical significance
  - Aligns with existing UTXOracle daily analysis

- **Step size**: 6 blocks (~1 hour)
  - Provides hourly regime updates
  - Balance between responsiveness and noise

- **Sustained shift detection**: 3+ consecutive high-W windows
  - Filters momentary spikes
  - Confirms regime transition

**Configuration**:
```python
DEFAULT_WINDOW_SIZE = 144    # blocks (~24h)
DEFAULT_STEP_SIZE = 6        # blocks (~1h)
SHIFT_THRESHOLD = 0.10       # W > 0.10 = significant shift
SUSTAINED_COUNT = 3          # 3+ consecutive = sustained
```

**Alternatives Considered**:
| Strategy | Pros | Cons |
|----------|------|------|
| Exponential MA | Smooth | Loses sharp transitions |
| Adaptive window | Responsive | Complex, over-engineered |
| **Fixed sliding (chosen)** | Simple, interpretable | Fixed lag |

---

### 3. Integration with Monte Carlo Fusion

**Question**: How should Wasserstein integrate with existing enhanced fusion?

**Decision**: Add as 8th component with 0.08 weight, renormalize others

**Rationale**:
Current spec-009 weights sum to 1.0 for 7 components. Adding Wasserstein requires rebalancing:

| Component | spec-009 Weight | spec-010 Weight | Change |
|-----------|-----------------|-----------------|--------|
| whale | 0.25 | 0.23 | -0.02 |
| utxo | 0.15 | 0.14 | -0.01 |
| funding | 0.15 | 0.14 | -0.01 |
| oi | 0.10 | 0.09 | -0.01 |
| power_law | 0.10 | 0.09 | -0.01 |
| symbolic | 0.15 | 0.14 | -0.01 |
| fractal | 0.10 | 0.09 | -0.01 |
| **wasserstein** | - | **0.08** | NEW |
| **Total** | 1.00 | 1.00 | - |

**Vote Calculation**:
```python
def wasserstein_vote(w_distance: float, shift_direction: str) -> float:
    """
    Convert Wasserstein distance to directional vote.

    - CONCENTRATION shift (toward whale): positive vote
    - DISPERSION shift (toward retail): negative vote
    - No significant shift: neutral vote
    """
    if w_distance < SHIFT_THRESHOLD:
        return 0.0  # No significant shift

    # Scale vote by distance magnitude (cap at 1.0)
    magnitude = min(1.0, (w_distance - SHIFT_THRESHOLD) / 0.15)

    if shift_direction == "CONCENTRATION":
        return 0.6 * magnitude  # Bullish (whale accumulation)
    elif shift_direction == "DISPERSION":
        return -0.4 * magnitude  # Bearish (retail entry)
    else:
        return 0.0
```

**Direction Detection**:
Compare mean of window_1 vs window_2:
- If mean_2 > mean_1: CONCENTRATION (fewer, larger values)
- If mean_2 < mean_1: DISPERSION (more, smaller values)

---

## Technical Findings

### Performance Benchmarks

Based on existing spec-009 module patterns:

| Operation | Expected Time | Measured Baseline |
|-----------|---------------|-------------------|
| Sort 1000 values | ~0.1ms | Python built-in |
| Quantile interpolation | ~0.5ms | Linear interpolation |
| Sum 1000 differences | ~0.1ms | Generator expression |
| **Total per calculation** | **<1ms** | Well under 50ms target |

### Edge Cases

1. **Identical distributions**: W = 0.0 exactly
2. **Single value**: Degenerate case, return W = |v1 - v2|
3. **Different lengths**: Interpolate to longer length
4. **Empty input**: Return `is_valid=False`
5. **All zeros**: Treat as identical (W = 0.0)

### Validation Strategy

| Test Case | Expected W | Purpose |
|-----------|------------|---------|
| P = Q (identical) | 0.0 | Zero distance |
| P = Uniform[0,1], Q = Uniform[0.5,1.5] | 0.5 | Known shift |
| P = N(0,1), Q = N(1,1) | 1.0 | Mean shift |
| Random samples | ~0.0 | Stability check |

---

## Conclusions

1. **Algorithm**: Quantile-based O(n log n) approach is optimal for 1D discrete samples
2. **Window**: 144-block window with 6-block step balances accuracy and responsiveness
3. **Integration**: 8th fusion component with 0.08 weight, minimal rebalancing
4. **Performance**: Well within 50ms target (<1ms expected)

**Ready for Phase 1 design.**
