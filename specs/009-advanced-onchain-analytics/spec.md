# Feature Specification: Advanced On-Chain Analytics

**Feature Branch**: `009-advanced-onchain-analytics`
**Created**: 2025-12-04
**Status**: Draft
**Prerequisites**: spec-007 (Monte Carlo Fusion) MUST be complete
**Input**: User description: "Implement advanced statistical modules from 'contadino cosmico' architecture: Power Law Detector, Symbolic Dynamics Processor, and Fractal Dimension Analyzer. These modules enhance signal quality by detecting critical regimes, temporal patterns, and structural complexity in UTXO distributions."

## Context & Motivation

### Background: Contadino Cosmico Architecture

This spec implements 3 of 9 modules from the "contadino cosmico" on-chain analytics architecture:

| Module | Purpose | Accuracy Gain | Status |
|--------|---------|---------------|--------|
| UTXOracle Data Extractor | Price calculation | N/A (baseline) | ✅ Implemented |
| Monte Carlo Fusion | Signal aggregation | +10% | ✅ spec-007 |
| Whale Tracker | Flow detection | +5-10% | ✅ spec-004/005 |
| **Power Law Detector** | Critical regimes | **+5%** | 🎯 This spec |
| **Symbolic Dynamics** | Temporal patterns | **+25%** | 🎯 This spec |
| **Fractal Dimension** | Structural complexity | **+10%** | 🎯 This spec |
| Wasserstein Distance | Distribution shifts | +5% | ❌ Future |
| Reservoir Computer | ML prediction | +5-10%? | ❌ Future |
| Evolutionary Optimizer | Sharpe optimization | +5% | ❌ Future |

**Expected Combined Accuracy Gain**: +40% over baseline whale+utxo fusion

### Scientific Foundation

1. **Power Law (Self-Organized Criticality)**: Bitcoin UTXO distributions follow power laws P(x) ~ x^(-τ). Deviations from typical τ ≈ 2.0 indicate regime changes (Kondor et al., 2014).

2. **Symbolic Dynamics (Permutation Entropy)**: Time series complexity measured via ordinal patterns. Low entropy = predictable accumulation; High entropy = chaotic distribution (Bandt & Pompe, 2002).

3. **Fractal Dimension (Box-Counting)**: Self-similarity measure of UTXO value distributions. D < 1.5 = concentrated (whale activity); D > 1.8 = dispersed (retail) (Mandelbrot, 1982).

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Power Law Regime Detection (Priority: P1)

As a Bitcoin trader, I want to know when UTXO distributions **deviate from typical power law behavior**, so I can detect regime shifts that often precede major price movements.

**Why this priority**: Power law exponent τ is a leading indicator of market regime. τ < 1.8 indicates whale concentration (bullish); τ > 2.2 indicates distribution (bearish). Academic research shows 70%+ correlation with price direction. ~120 LOC.

**Independent Test**: Can be fully tested by:
1. Providing synthetic UTXO value distributions with known power law exponents
2. Running MLE fit with KS validation
3. Verifying τ estimate within ±0.1 of true value

**Acceptance Scenarios**:

1. **Given** UTXO values following P(x) ~ x^(-2.0) distribution (1000 samples)
   **When** power law detector runs
   **Then** estimated τ is 2.0 ± 0.1, `is_valid=True` (KS test p > 0.05)

2. **Given** UTXO values with τ = 1.6 (heavy tail, whale concentration)
   **When** regime is classified
   **Then** `regime="ACCUMULATION"`, `power_law_vote=+0.7`

3. **Given** UTXO values with τ = 2.4 (light tail, distribution)
   **When** regime is classified
   **Then** `regime="DISTRIBUTION"`, `power_law_vote=-0.5`

4. **Given** UTXO values that fail KS test (not power law)
   **When** power law detector runs
   **Then** `is_valid=False`, `power_law_vote=0.0` (excluded from fusion)

---

### User Story 2 - Symbolic Dynamics Pattern Detection (Priority: P1)

As a Bitcoin trader, I want to measure **temporal complexity** of UTXO flow patterns, so I can distinguish between predictable accumulation phases and chaotic market transitions.

**Why this priority**: Permutation entropy is the highest ROI metric from academic literature (+25% accuracy gain). Low complexity → trending behavior → follow the trend. High complexity → uncertain → reduce position size. ~100 LOC.

**Independent Test**: Can be fully tested by:
1. Providing time series with known ordinal patterns
2. Computing permutation entropy with order d=5
3. Comparing with analytical solution for synthetic data

**Acceptance Scenarios**:

1. **Given** monotonically increasing time series [1,2,3,4,5,6,7,8,9,10]
   **When** permutation entropy is calculated (order=5)
   **Then** H ≈ 0.0 (perfectly predictable), `complexity_class="LOW"`

2. **Given** random shuffle of values (uniform distribution)
   **When** permutation entropy is calculated (order=5)
   **Then** H ≈ 1.0 (maximum entropy), `complexity_class="HIGH"`

3. **Given** UTXO flow series with H = 0.35 (low entropy)
   **When** symbolic dynamics classifier runs
   **Then** `pattern="ACCUMULATION_TREND"`, `symbolic_vote=+0.8`

4. **Given** UTXO flow series with H = 0.85 (high entropy)
   **When** symbolic dynamics classifier runs
   **Then** `pattern="CHAOTIC_TRANSITION"`, `symbolic_vote=0.0` (no directional signal)

5. **Given** UTXO flow series with H = 0.55 and strong autocorrelation
   **When** complexity (C) is calculated
   **Then** H-C plane classification: "EDGE_OF_CHAOS" (interesting regime)

---

### User Story 3 - Fractal Dimension Analysis (Priority: P2)

As a Bitcoin analyst, I want to measure the **fractal dimension** of UTXO value distributions, so I can assess whether market structure is concentrated (whale-dominated) or dispersed (retail-dominated).

**Why this priority**: Box-counting dimension D reveals structural properties invisible to mean/variance statistics. D complements power law τ - both together provide robust regime classification. ~80 LOC.

**Independent Test**: Can be fully tested by:
1. Providing point sets with known fractal dimensions (Cantor set D≈0.63, uniform D=1.0)
2. Running box-counting algorithm across multiple scales
3. Verifying D estimate within ±0.1 of theoretical value

**Acceptance Scenarios**:

1. **Given** uniformly distributed UTXO values in [0, 1]
   **When** fractal dimension is calculated
   **Then** D ≈ 1.0 ± 0.1 (fills 1D space uniformly)

2. **Given** UTXO values clustered in 3 distinct ranges (whale wallets)
   **When** fractal dimension is calculated
   **Then** D < 0.8 (sparse, concentrated structure)

3. **Given** D = 0.6 (highly concentrated)
   **When** fractal classifier runs
   **Then** `structure="WHALE_DOMINATED"`, `fractal_vote=+0.5` (bullish - smart money)

4. **Given** D = 1.4 (highly dispersed)
   **When** fractal classifier runs
   **Then** `structure="RETAIL_DOMINATED"`, `fractal_vote=-0.3` (neutral-bearish)

---

### User Story 4 - Enhanced Monte Carlo Fusion (Priority: P1)

As a Bitcoin trader, I want the **Monte Carlo fusion to incorporate all 7 signals** (whale, utxo, funding, oi, power_law, symbolic, fractal), so I get a comprehensive market view with proper uncertainty quantification.

**Why this priority**: Integration point for all analytics. Extends spec-007 Monte Carlo with 3 new signal sources. Configurable weights allow tuning based on backtest results.

**Independent Test**: Can be fully tested by:
1. Providing all 7 signal components with known values
2. Running enhanced Monte Carlo fusion (1000 samples)
3. Verifying weighted combination and confidence intervals

**Acceptance Scenarios**:

1. **Given** all signals aligned bullish (whale, utxo, power_law, symbolic, fractal all positive)
   **When** enhanced fusion runs with default weights
   **Then** `signal_mean > 0.8`, `signal_std < 0.1`, `action="BUY"`

2. **Given** conflicting signals (power_law bullish, symbolic bearish, fractal neutral)
   **When** enhanced fusion runs
   **Then** `signal_std > 0.3` (high uncertainty reflected)

3. **Given** one signal unavailable (e.g., power_law `is_valid=False`)
   **When** enhanced fusion runs
   **Then** weights are renormalized, fusion continues without power_law

4. **Given** backtest shows symbolic dynamics has highest predictive power
   **When** weights are optimized
   **Then** `symbolic_weight` increases relative to others

---

### Edge Cases

- **What happens when UTXO sample size is too small for power law fit?**
  → Require minimum 100 samples; return `is_valid=False` if fewer.

- **What happens when permutation entropy order exceeds series length?**
  → Require series length ≥ 2 * factorial(order); reduce order if necessary.

- **What happens when box-counting produces degenerate scales?**
  → Use adaptive scale selection (2^k for k=1..10); require ≥5 valid scales for fit.

- **What happens when all advanced metrics fail validation?**
  → Fall back to spec-007 fusion (whale + utxo + derivatives only); log warning.

---

## Requirements *(mandatory)*

### Functional Requirements

**Power Law Detector**:
- **FR-001**: Power law detector MUST use Maximum Likelihood Estimation (MLE) for τ
- **FR-002**: Power law detector MUST validate fit using Kolmogorov-Smirnov test (p > 0.05)
- **FR-003**: Power law detector MUST classify regime: ACCUMULATION (τ < 1.8), NEUTRAL (1.8-2.2), DISTRIBUTION (τ > 2.2)
- **FR-004**: Power law detector MUST return `is_valid=False` if sample size < 100 or KS test fails

**Symbolic Dynamics**:
- **FR-005**: Symbolic dynamics MUST compute permutation entropy with configurable order (default: 5)
- **FR-006**: Symbolic dynamics MUST compute statistical complexity C for H-C plane classification
- **FR-007**: Symbolic dynamics MUST classify patterns: ACCUMULATION_TREND (H<0.4, positive trend), DISTRIBUTION_TREND (H<0.4, negative trend), CHAOTIC_TRANSITION (H>0.7), EDGE_OF_CHAOS (0.4<H<0.7, high C). Trend direction is determined by comparing mean of first half vs second half of series: positive if second_half > first_half, negative otherwise.
- **FR-008**: Symbolic dynamics MUST complete in <10ms for 1000-point series

**Fractal Dimension**:
- **FR-009**: Fractal analyzer MUST use box-counting algorithm with log-log regression
- **FR-010**: Fractal analyzer MUST use adaptive scales (powers of 2) from min to max value range
- **FR-011**: Fractal analyzer MUST require R² > 0.9 for valid dimension estimate
- **FR-012**: Fractal analyzer MUST classify structure: WHALE_DOMINATED (D<0.8), MIXED (0.8-1.2), RETAIL_DOMINATED (D>1.2)

**Integration**:
- **FR-013**: Enhanced fusion MUST support configurable weights for 7 components (whale, utxo, funding, oi, power_law, symbolic, fractal)
- **FR-014**: Default weights: whale=0.25, utxo=0.15, funding=0.15, oi=0.10, power_law=0.10, symbolic=0.15, fractal=0.10
- **FR-015**: Enhanced fusion MUST renormalize weights when components are unavailable
- **FR-016**: All metrics MUST be stored in DuckDB `metrics` table (extend from spec-007)
- **FR-017**: API endpoint `/api/metrics/advanced` MUST return all advanced metrics

### Non-Functional Requirements

- **NFR-001**: All modules MUST be pure Python (no numpy/scipy required, but may use if available)
- **NFR-002**: Total advanced metrics calculation MUST complete in <100ms
- **NFR-003**: Backward compatible: existing spec-007 fusion still works if advanced metrics disabled
- **NFR-004**: All modules MUST follow existing patterns in `scripts/metrics/`

### Key Entities *(mandatory)*

```python
@dataclass
class PowerLawResult:
    tau: float                    # Power law exponent (typically 1.5-2.5)
    tau_std: float                # Standard error of τ estimate
    xmin: float                   # Minimum value for fit (cutoff)
    ks_statistic: float           # Kolmogorov-Smirnov test statistic
    ks_pvalue: float              # KS test p-value (>0.05 = valid)
    is_valid: bool                # True if fit passes KS test
    regime: str                   # "ACCUMULATION" | "NEUTRAL" | "DISTRIBUTION"
    power_law_vote: float         # Signal vote (-1 to +1)
    sample_size: int              # Number of UTXO values used

@dataclass
class SymbolicDynamicsResult:
    permutation_entropy: float    # Normalized entropy H ∈ [0, 1]
    statistical_complexity: float # Complexity C ∈ [0, 0.5]
    order: int                    # Embedding dimension (default: 5)
    pattern_counts: dict          # Frequency of each ordinal pattern
    dominant_pattern: str         # Most frequent pattern (e.g., "012345")
    complexity_class: str         # "LOW" | "MEDIUM" | "HIGH"
    pattern_type: str             # "ACCUMULATION_TREND" | "DISTRIBUTION_TREND" | "CHAOTIC_TRANSITION" | "EDGE_OF_CHAOS"
    symbolic_vote: float          # Signal vote (-1 to +1)
    series_length: int            # Input series length

@dataclass
class FractalDimensionResult:
    dimension: float              # Box-counting dimension D
    dimension_std: float          # Standard error of D estimate
    r_squared: float              # Goodness of fit (>0.9 required)
    scales_used: list[float]      # Box sizes used for counting
    counts: list[int]             # Box counts at each scale
    is_valid: bool                # True if R² > 0.9
    structure: str                # "WHALE_DOMINATED" | "MIXED" | "RETAIL_DOMINATED"
    fractal_vote: float           # Signal vote (-1 to +1)
    sample_size: int              # Number of UTXO values used

@dataclass
class EnhancedFusionResult:
    # Base Monte Carlo fields (from spec-007)
    signal_mean: float
    signal_std: float
    ci_lower: float
    ci_upper: float
    action: str                   # BUY/SELL/HOLD
    action_confidence: float
    n_samples: int
    distribution_type: str

    # All component votes and weights
    whale_vote: float | None
    whale_weight: float
    utxo_vote: float | None
    utxo_weight: float
    funding_vote: float | None    # From spec-008
    funding_weight: float
    oi_vote: float | None         # From spec-008
    oi_weight: float
    power_law_vote: float | None  # NEW
    power_law_weight: float
    symbolic_vote: float | None   # NEW
    symbolic_weight: float
    fractal_vote: float | None    # NEW
    fractal_weight: float

    # Metadata
    components_available: int     # Count of valid components (0-7)
    timestamp: datetime
```

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Power law τ estimate within ±0.1 of true value for synthetic data
- **SC-002**: Permutation entropy H within ±0.05 of analytical solution for known series
- **SC-003**: Fractal dimension D within ±0.1 of theoretical value for Cantor set
- **SC-004**: Enhanced fusion with all 7 components completes in <100ms
- **SC-005**: Backtest on 30 days shows enhanced fusion win rate > spec-007 baseline
- **SC-006**: Code coverage for new modules ≥85%
- **SC-007**: Zero regressions in existing tests (spec-007, spec-004, spec-005)

### Definition of Done

- [ ] Power law detector implemented with MLE + KS validation
- [ ] Symbolic dynamics implemented with permutation entropy + complexity
- [ ] Fractal dimension implemented with box-counting + R² validation
- [ ] Enhanced fusion integrates all 7 signal components
- [ ] DuckDB schema extended for advanced metrics
- [ ] API endpoint `/api/metrics/advanced` returns all metrics
- [ ] Unit tests for each module (≥85% coverage)
- [ ] Integration test: full daily_analysis.py with advanced metrics
- [ ] Performance validated (<100ms total)
- [ ] Documentation updated in CLAUDE.md

---

## Technical Notes

### Implementation Order (KISS)

1. **Symbolic Dynamics** (~100 LOC) - Highest ROI, simplest algorithm
2. **Power Law** (~120 LOC) - Well-documented MLE approach
3. **Fractal Dimension** (~80 LOC) - Straightforward box-counting
4. **Enhanced Fusion** (~60 LOC) - Extend existing Monte Carlo

### Files to Create

- `scripts/metrics/power_law.py` - Power law detection and regime classification
- `scripts/metrics/symbolic_dynamics.py` - Permutation entropy and complexity
- `scripts/metrics/fractal_dimension.py` - Box-counting and structure classification
- `tests/test_advanced_metrics.py` - Test suite for all three modules

### Files to Modify

- `scripts/metrics/monte_carlo_fusion.py` - Extend for 7 components
- `scripts/daily_analysis.py` - Add advanced metric calculations
- `api/main.py` - Add `/api/metrics/advanced` endpoint
- `scripts/models/metrics_models.py` - Add new dataclasses

### Algorithm References

1. **Power Law MLE**: Clauset, A., Shalizi, C. R., & Newman, M. E. (2009). "Power-law distributions in empirical data." SIAM review.
   - τ = 1 + n / Σ ln(x_i / x_min)
   - KS statistic: max|S_n(x) - P(x)|

2. **Permutation Entropy**: Bandt, C., & Pompe, B. (2002). "Permutation entropy: a natural complexity measure for time series." Physical review letters.
   - H = -Σ p_i log(p_i) / log(d!)
   - d = embedding dimension (order)

3. **Box-Counting Dimension**: Liebovitch, L. S., & Toth, T. (1989). "A fast algorithm to determine fractal dimensions by box counting." Physics Letters A.
   - D = lim(ε→0) log(N(ε)) / log(1/ε)
   - N(ε) = number of boxes of size ε needed to cover the set

### Configuration

```bash
# .env additions
ADVANCED_METRICS_ENABLED=true
POWER_LAW_MIN_SAMPLES=100
SYMBOLIC_ORDER=5
FRACTAL_MIN_SCALES=5
ENHANCED_FUSION_WEIGHTS=whale:0.25,utxo:0.15,funding:0.15,oi:0.10,power_law:0.10,symbolic:0.15,fractal:0.10
```

### Dependencies

- **Internal**: spec-007 Monte Carlo fusion (prerequisite), spec-008 derivatives (optional)
- **External**: None required (pure Python); numpy optional for performance
- **Data**: UTXO values from daily_analysis.py transactions

---

## Out of Scope

- GPU acceleration (not needed for <100ms target)
- Real-time streaming (batch only, like spec-007)
- Wasserstein distance calculator (future spec)
- Reservoir computer / ML models (future spec)
- Evolutionary optimizer (future spec)
- Automatic weight optimization via ML (research task)

---

## Future Extensions

After validation, potential enhancements:
- **spec-010**: Wasserstein distance for distribution shift detection
- **spec-011**: Reservoir computing for time series prediction
- **spec-012**: Evolutionary optimization of signal weights
- Adaptive order selection for symbolic dynamics based on series characteristics
- Multi-scale fractal analysis for different UTXO ranges
