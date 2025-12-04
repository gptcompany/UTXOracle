# Feature Specification: Wasserstein Distance Calculator

**Feature Branch**: `010-wasserstein-distance`
**Created**: 2025-12-04
**Status**: Draft
**Prerequisites**: spec-009 (Advanced On-Chain Analytics) MUST be complete
**Input**: User description: "Implement Wasserstein Distance Calculator (Earth Mover's Distance) to detect distribution shifts in UTXO value patterns. Based on Horvath et al. (2024) - 'Clustering Market Regimes Using Wasserstein Distance'. This module enables regime shift detection by measuring how much 'work' is needed to transform one UTXO distribution into another."

## Context & Motivation

### Background: Distribution Shift Detection

UTXO value distributions change over time as market participants shift behavior. The Wasserstein distance (EMD - Earth Mover's Distance) provides a mathematically principled way to measure how different two distributions are, considering both shape and position.

| Metric | What it Measures | Limitation |
|--------|------------------|------------|
| Mean/Variance | Central tendency | Misses shape changes |
| Histogram Overlap | Bin-by-bin similarity | Ignores spatial structure |
| KS Statistic | Max CDF difference | Point estimate only |
| **Wasserstein** | Optimal transport cost | **None for distributions** |

**Expected Accuracy Gain**: +5% over spec-009 baseline (from academic literature)

### Scientific Foundation

The Wasserstein distance W_p(P, Q) measures the minimum cost to transform probability distribution P into Q:

```
W_1(P, Q) = inf_{γ ∈ Γ(P,Q)} E_{(x,y)~γ}[|x - y|]
```

For 1D distributions (our case), this simplifies to:

```
W_1(P, Q) = ∫|F_P(x) - F_Q(x)| dx
```

Where F_P and F_Q are the cumulative distribution functions.

**Why Wasserstein?**
- **Metric property**: W(P,Q) = 0 iff P = Q
- **Captures geometry**: Accounts for the "ground distance" between values
- **Regime detection**: Large W indicates distribution shift (market regime change)
- **Academic validation**: Horvath et al. (2024) demonstrates significant predictive power

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Distribution Shift Detection (Priority: P1)

As a Bitcoin trader, I want to detect when the **UTXO value distribution shifts significantly** between time windows, so I can identify market regime changes that often precede price movements.

**Why this priority**: Distribution shifts are leading indicators of market regime changes. A shift from concentrated (whale) to dispersed (retail) distribution typically precedes distribution phases. ~100 LOC, O(n log n) complexity.

**Independent Test**: Can be fully tested by:
1. Providing two synthetic distributions with known Wasserstein distance
2. Computing EMD using CDF integration
3. Verifying distance within ±0.01 of analytical solution

**Acceptance Scenarios**:

1. **Given** two identical distributions (same values)
   **When** Wasserstein distance is calculated
   **Then** W_1 = 0.0 (zero distance)

2. **Given** distribution P = Uniform[0,1] and Q = Uniform[0.5, 1.5]
   **When** Wasserstein distance is calculated
   **Then** W_1 = 0.5 (shift by 0.5)

3. **Given** UTXO distributions from two consecutive 6-hour windows
   **When** Wasserstein distance exceeds threshold (W > 0.1)
   **Then** `regime_shift=True`, `wasserstein_vote` reflects direction

4. **Given** stable market (similar distributions over 24h)
   **When** Wasserstein distances are calculated for rolling windows
   **Then** All W < 0.05, `regime_shift=False`

---

### User Story 2 - Rolling Window Analysis (Priority: P1)

As a Bitcoin analyst, I want to compute **rolling Wasserstein distances** over time, so I can track distribution stability and detect sudden shifts.

**Why this priority**: Single-point detection is useful, but rolling windows reveal trends. Increasing W over time suggests growing instability; decreasing W suggests consolidation.

**Independent Test**: Can be fully tested by:
1. Providing time series of values with known regime change at t=500
2. Computing rolling W with window=100, step=10
3. Verifying W spike at regime change point

**Acceptance Scenarios**:

1. **Given** 1000-point series with regime change at t=500
   **When** rolling Wasserstein is computed (window=100, step=10)
   **Then** W peaks at t=500 ± 20

2. **Given** stable series (no regime change)
   **When** rolling Wasserstein is computed
   **Then** W variance < 0.02 (low variability)

3. **Given** rolling W > 0.15 for 3+ consecutive windows
   **When** classifier runs
   **Then** `sustained_shift=True`, confidence increased

---

### User Story 3 - Integration with Enhanced Fusion (Priority: P2)

As a Bitcoin trader, I want the **Wasserstein signal integrated into Monte Carlo fusion**, so regime shift detection contributes to the overall trading signal.

**Why this priority**: Standalone metrics are less useful than fused signals. Wasserstein complements existing metrics by detecting structural changes they might miss.

**Independent Test**: Can be fully tested by:
1. Providing fusion with wasserstein_vote=+0.5 (shift toward concentration)
2. Running enhanced fusion with all 8 components
3. Verifying wasserstein contribution to final signal

**Acceptance Scenarios**:

1. **Given** Wasserstein detects shift toward concentration (whale)
   **When** enhanced fusion runs with wasserstein_weight=0.10
   **Then** `wasserstein_vote=+0.6` contributes positively

2. **Given** Wasserstein detects shift toward dispersion (retail)
   **When** enhanced fusion runs
   **Then** `wasserstein_vote=-0.4` contributes negatively

3. **Given** no significant distribution shift (W < 0.05)
   **When** enhanced fusion runs
   **Then** `wasserstein_vote=0.0` (neutral)

---

### Edge Cases

- **What happens when window sizes are unequal?**
  → Normalize distributions to same mass (sum to 1.0) before computing EMD.

- **What happens when distributions have different supports?**
  → Extend support to union of both ranges, pad with zeros.

- **What happens when sample size is too small?**
  → Require minimum 50 samples per window; return `is_valid=False` if fewer.

- **What happens when all values are identical?**
  → Return W=0.0 (zero variance distribution).

---

## Requirements *(mandatory)*

### Functional Requirements

**Wasserstein Distance**:
- **FR-001**: Wasserstein calculator MUST compute 1D Earth Mover's Distance using CDF integration
- **FR-002**: Wasserstein calculator MUST handle arbitrary positive value distributions
- **FR-003**: Wasserstein calculator MUST normalize distributions to unit mass before comparison
- **FR-004**: Wasserstein calculator MUST return `is_valid=False` if sample size < 50

**Rolling Analysis**:
- **FR-005**: Rolling Wasserstein MUST support configurable window size (default: 144 blocks = 24h)
- **FR-006**: Rolling Wasserstein MUST support configurable step size (default: 6 blocks = 1h)
- **FR-007**: Rolling Wasserstein MUST detect sustained shifts (3+ consecutive high-W windows)

**Regime Classification**:
- **FR-008**: Wasserstein classifier MUST classify shifts: CONCENTRATION_SHIFT (toward whale), DISPERSION_SHIFT (toward retail), STABLE (no shift)
- **FR-009**: Wasserstein classifier MUST use adaptive threshold based on historical W variance
- **FR-010**: Default shift threshold: W > 0.10 (configurable via .env)

**Integration**:
- **FR-011**: Enhanced fusion MUST accept wasserstein_vote as 8th component
- **FR-012**: Default wasserstein_weight: 0.08 (rebalanced from spec-009)
- **FR-013**: Wasserstein metrics MUST be stored in DuckDB `metrics` table
- **FR-014**: API endpoint `/api/metrics/wasserstein` MUST return rolling W and regime status

### Non-Functional Requirements

- **NFR-001**: Wasserstein calculation MUST complete in <50ms for 1000-sample distributions
- **NFR-002**: Pure Python implementation (no scipy.stats required)
- **NFR-003**: Backward compatible: spec-009 fusion still works without Wasserstein
- **NFR-004**: Thread-safe for concurrent window calculations

### Key Entities *(mandatory)*

```python
@dataclass
class WassersteinResult:
    distance: float                   # W_1 distance between distributions
    distance_normalized: float        # W_1 / max(range) for scale-invariance
    window_1_size: int               # Sample count in first window
    window_2_size: int               # Sample count in second window
    window_1_mean: float             # Mean of first distribution
    window_2_mean: float             # Mean of second distribution
    shift_direction: str             # "CONCENTRATION" | "DISPERSION" | "NONE"
    is_valid: bool                   # True if both windows have sufficient samples

@dataclass
class RollingWassersteinResult:
    distances: list[float]           # Rolling W values
    timestamps: list[datetime]       # Timestamp for each W value
    mean_distance: float             # Average W over period
    max_distance: float              # Peak W (potential regime change)
    std_distance: float              # Stability measure
    sustained_shift_detected: bool   # True if 3+ consecutive high-W
    regime_status: str               # "STABLE" | "TRANSITIONING" | "SHIFTED"
    wasserstein_vote: float          # Signal vote (-1 to +1)

@dataclass
class EnhancedFusionResultV2:
    # All fields from EnhancedFusionResult (spec-009)
    # Plus:
    wasserstein_vote: float | None    # NEW
    wasserstein_weight: float         # NEW (default: 0.08)
    components_available: int         # Now 0-8
```

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Wasserstein distance within ±0.01 of analytical solution for synthetic distributions
- **SC-002**: Rolling Wasserstein detects synthetic regime changes with 90%+ accuracy
- **SC-003**: Wasserstein calculation <50ms for 1000-sample distributions
- **SC-004**: Enhanced fusion with 8 components completes in <120ms
- **SC-005**: Backtest on 30 days shows regime detection correlates with price volatility (r > 0.6)
- **SC-006**: Code coverage for Wasserstein module ≥85%
- **SC-007**: Zero regressions in spec-009 tests

### Definition of Done

- [ ] Wasserstein distance calculator implemented with CDF integration
- [ ] Rolling window analysis with configurable parameters
- [ ] Regime classification (CONCENTRATION/DISPERSION/STABLE)
- [ ] Enhanced fusion extended for 8 components
- [ ] DuckDB schema extended for Wasserstein metrics
- [ ] API endpoint `/api/metrics/wasserstein` returns rolling W
- [ ] Unit tests for Wasserstein module (≥85% coverage)
- [ ] Integration test: daily_analysis.py with Wasserstein
- [ ] Performance validated (<50ms per calculation)
- [ ] Documentation updated in CLAUDE.md

---

## Technical Notes

### Implementation Order (KISS)

1. **Core Wasserstein** (~60 LOC) - CDF integration for W_1
2. **Rolling Analysis** (~40 LOC) - Window management
3. **Regime Classification** (~30 LOC) - Threshold-based voting
4. **Fusion Integration** (~20 LOC) - Extend Monte Carlo

### Files to Create

- `scripts/metrics/wasserstein.py` - Core EMD calculation and rolling analysis
- `tests/test_wasserstein.py` - Test suite for Wasserstein module

### Files to Modify

- `scripts/metrics/monte_carlo_fusion.py` - Add wasserstein_vote (8th component)
- `scripts/daily_analysis.py` - Add Wasserstein calculation to pipeline
- `api/main.py` - Add `/api/metrics/wasserstein` endpoint
- `scripts/models/metrics_models.py` - Add WassersteinResult, RollingWassersteinResult

### Algorithm: 1D Wasserstein (Earth Mover's Distance)

```python
def wasserstein_1d(values_1: list[float], values_2: list[float]) -> float:
    """
    Compute 1D Wasserstein distance using CDF integration.

    W_1(P, Q) = ∫|F_P(x) - F_Q(x)| dx

    For discrete samples, this equals the sum of absolute differences
    between sorted quantile values.
    """
    # Sort both distributions
    sorted_1 = sorted(values_1)
    sorted_2 = sorted(values_2)

    # Compute quantile positions
    n1, n2 = len(sorted_1), len(sorted_2)

    # Create combined sorted list of all values
    all_values = sorted(set(sorted_1 + sorted_2))

    # Compute CDFs at each point
    cdf_1 = [sum(1 for v in sorted_1 if v <= x) / n1 for x in all_values]
    cdf_2 = [sum(1 for v in sorted_2 if v <= x) / n2 for x in all_values]

    # Integrate |F_1 - F_2| using trapezoidal rule
    w_distance = 0.0
    for i in range(1, len(all_values)):
        dx = all_values[i] - all_values[i-1]
        avg_diff = (abs(cdf_1[i] - cdf_2[i]) + abs(cdf_1[i-1] - cdf_2[i-1])) / 2
        w_distance += avg_diff * dx

    return w_distance
```

### Optimized Algorithm (O(n log n))

```python
def wasserstein_1d_fast(values_1: list[float], values_2: list[float]) -> float:
    """
    Optimized 1D Wasserstein using quantile matching.

    For 1D distributions, W_1 = (1/n) * sum(|Q_1(i/n) - Q_2(i/n)|)
    where Q is the quantile function.
    """
    # Interpolate to same length
    n = max(len(values_1), len(values_2))
    q1 = quantile_function(values_1, n)
    q2 = quantile_function(values_2, n)

    # Sum absolute differences
    return sum(abs(a - b) for a, b in zip(q1, q2)) / n
```

### Configuration

```bash
# .env additions
WASSERSTEIN_ENABLED=true
WASSERSTEIN_WINDOW_SIZE=144        # blocks (24h)
WASSERSTEIN_STEP_SIZE=6            # blocks (1h)
WASSERSTEIN_SHIFT_THRESHOLD=0.10   # W > this = regime shift
WASSERSTEIN_MIN_SAMPLES=50         # minimum per window
WASSERSTEIN_WEIGHT=0.08            # weight in enhanced fusion
```

### Dependencies

- **Internal**: spec-009 Enhanced Fusion (prerequisite)
- **External**: None required (pure Python)
- **Data**: UTXO values from daily_analysis.py transactions

### Updated Fusion Weights (8 components)

```python
# Rebalanced for 8 components (sum = 1.0)
ENHANCED_WEIGHTS_V2 = {
    "whale": 0.23,        # was 0.25
    "utxo": 0.14,         # was 0.15
    "funding": 0.14,      # was 0.15
    "oi": 0.09,           # was 0.10
    "power_law": 0.09,    # was 0.10
    "symbolic": 0.14,     # was 0.15
    "fractal": 0.09,      # was 0.10
    "wasserstein": 0.08,  # NEW
}
```

---

## Out of Scope

- 2D/multi-dimensional Wasserstein (not needed for 1D UTXO values)
- Sinkhorn approximation (exact solution fast enough for our scale)
- Optimal transport plan visualization (nice-to-have, not MVP)
- Real-time streaming Wasserstein (batch only)

---

## References

1. **Horvath, B., Teichmann, J., & Zuric, Z. (2024)**. "Clustering Market Regimes Using Wasserstein Distance." *arXiv:2110.11848*.
   - Demonstrates Wasserstein for regime clustering in financial markets
   - Shows significant predictive power for regime changes

2. **Villani, C. (2009)**. "Optimal Transport: Old and New." *Springer*.
   - Mathematical foundation for Wasserstein distance
   - 1D simplification formulas

3. **Ramdas, A., Garcia, N., & Cuturi, M. (2017)**. "On Wasserstein Two-Sample Testing and Related Families of Nonparametric Tests." *Entropy*.
   - Statistical testing with Wasserstein distance
