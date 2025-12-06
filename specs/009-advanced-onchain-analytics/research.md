# Research Notes: Advanced On-Chain Analytics

**Feature**: 009-advanced-onchain-analytics
**Created**: 2025-12-04
**Purpose**: Academic foundations and implementation references for advanced statistical modules

---

## 1. Power Law Detection

### Theoretical Background

Power laws are ubiquitous in financial data, including Bitcoin:
- Wealth distribution follows Pareto law
- Transaction sizes follow power law
- UTXO values exhibit heavy-tailed distributions

**Mathematical Definition**:
```
P(X > x) ~ x^(-tau + 1)
p(x) ~ x^(-tau)
```

Where tau (alpha in some literature) is the power law exponent.

### Key Paper: Clauset et al. (2009)

**Citation**: Clauset, A., Shalizi, C. R., & Newman, M. E. J. (2009). Power-law distributions in empirical data. SIAM Review, 51(4), 661-703.

**Key Contributions**:
1. **MLE Estimator for tau**:
   ```
   tau_hat = 1 + n / sum(ln(x_i / x_min))
   ```

2. **KS Test for Validation**:
   - Compare empirical CDF with theoretical power law CDF
   - p-value > 0.05 indicates valid power law fit

3. **x_min Selection**:
   - Minimize KS statistic across candidate x_min values
   - Critical for accurate tau estimation

### Bitcoin-Specific Research

**Kondor et al. (2014)**: "Do the Rich Get Richer? An Empirical Analysis of the Bitcoin Transaction Network"
- Found tau ~ 2.0 for Bitcoin wealth distribution
- Deviations from tau ~ 2.0 correlate with market phases

**Implementation Notes**:
- Use log-binning for histogram computation
- Require minimum 100 samples for stable MLE
- Standard error: tau_std = (tau - 1) / sqrt(n)

---

## 2. Symbolic Dynamics / Permutation Entropy

### Theoretical Background

Permutation entropy measures the complexity of time series by analyzing the order patterns (permutations) of consecutive values.

**Mathematical Definition**:
```
H = -sum(p_i * log(p_i)) / log(d!)
```

Where:
- d = embedding dimension (order)
- p_i = probability of permutation pattern i
- Normalization by log(d!) gives H in [0, 1]

### Key Paper: Bandt & Pompe (2002)

**Citation**: Bandt, C., & Pompe, B. (2002). Permutation entropy: a natural complexity measure for time series. Physical Review Letters, 88(17), 174102.

**Key Contributions**:
1. **Ordinal Pattern Extraction**:
   - Map consecutive d values to permutation pattern
   - E.g., [3.2, 1.1, 2.5] -> pattern "102" (middle < last < first)

2. **Interpretation**:
   - H ~ 0: Perfectly predictable (monotonic)
   - H ~ 1: Maximum randomness (white noise)
   - Intermediate H: Structured complexity

3. **Advantages**:
   - Robust to noise
   - Computationally efficient O(n)
   - Requires no preprocessing

### Statistical Complexity

**Lopez-Ruiz, Mancini & Calbet (1995)**: Introduced statistical complexity C.

```
C = H * D
D = sum((p_i - 1/n)^2)  # Disequilibrium from uniform
```

**H-C Plane Classification**:
- Low H, Low C: Ordered (crystal-like)
- High H, Low C: Random (noise)
- Medium H, High C: Complex (edge of chaos)

### Implementation Notes

**Trend Detection Algorithm** (for ACCUMULATION_TREND vs DISTRIBUTION_TREND):
```python
def compute_series_trend(series: list[float]) -> float:
    """
    Compute trend indicator by comparing first half vs second half means.

    Returns:
        Positive value = accumulation (series trending up)
        Negative value = distribution (series trending down)
        ~0 = no clear trend
    """
    n = len(series)
    mid = n // 2
    first_half = series[:mid]
    second_half = series[mid:]

    first_mean = sum(first_half) / len(first_half)
    second_mean = sum(second_half) / len(second_half)

    # Normalize by standard deviation for scale-invariance
    all_mean = sum(series) / n
    variance = sum((x - all_mean) ** 2 for x in series) / n
    std = variance ** 0.5 if variance > 0 else 1.0

    return (second_mean - first_mean) / std
```

**Permutation Entropy Algorithm**:
```python
def permutation_entropy(series, order=5, delay=1):
    """
    Compute normalized permutation entropy.

    Args:
        series: Time series (length >= 2 * factorial(order))
        order: Embedding dimension (3-7 typical)
        delay: Time delay (usually 1)

    Returns:
        H in [0, 1]
    """
    from itertools import permutations
    from math import factorial, log

    n = len(series)
    patterns = {}

    for i in range(n - (order - 1) * delay):
        # Extract window
        window = [series[i + j * delay] for j in range(order)]
        # Convert to ordinal pattern
        pattern = tuple(sorted(range(order), key=lambda k: window[k]))
        patterns[pattern] = patterns.get(pattern, 0) + 1

    # Compute entropy
    total = sum(patterns.values())
    probs = [c / total for c in patterns.values()]
    H = -sum(p * log(p) for p in probs if p > 0)

    # Normalize
    H_max = log(factorial(order))
    return H / H_max if H_max > 0 else 0
```

---

## 3. Fractal Dimension (Box-Counting)

### Theoretical Background

Fractal dimension D measures the self-similarity and space-filling properties of a set.

**Mathematical Definition (Box-Counting)**:
```
D = lim(epsilon -> 0) log(N(epsilon)) / log(1/epsilon)
```

Where N(epsilon) is the number of boxes of size epsilon needed to cover the set.

### Key Paper: Liebovitch & Toth (1989)

**Citation**: Liebovitch, L. S., & Toth, T. (1989). A fast algorithm to determine fractal dimensions by box counting. Physics Letters A, 141(8-9), 386-390.

**Algorithm**:
1. Choose scale range [epsilon_min, epsilon_max]
2. For each epsilon (typically powers of 2):
   - Partition space into boxes of size epsilon
   - Count non-empty boxes N(epsilon)
3. Fit log(N) vs log(1/epsilon)
4. Slope = fractal dimension D

### Financial Interpretation

**Mandelbrot (1982)**: "The Fractal Geometry of Nature"
- Financial time series exhibit self-similarity
- D < 1.5: Trending behavior (persistent)
- D > 1.5: Mean-reverting (anti-persistent)
- D = 1.5: Random walk

**For UTXO Distributions**:
- D < 0.8: Concentrated (few large clusters) -> Whale activity
- D ~ 1.0: Uniform distribution -> Normal market
- D > 1.2: Highly dispersed -> Retail fragmentation

### Implementation Notes

```python
def box_counting_dimension(values, min_scales=5):
    """
    Compute box-counting dimension of value distribution.

    Args:
        values: List of values to analyze
        min_scales: Minimum number of scales for valid fit

    Returns:
        (D, D_std, r_squared, scales, counts)
    """
    import math

    values = sorted(values)
    v_min, v_max = values[0], values[-1]
    v_range = v_max - v_min

    if v_range == 0:
        return 0.0, 0.0, 0.0, [], []

    # Generate scales (powers of 2)
    scales = []
    counts = []

    k = 1
    while True:
        epsilon = v_range / (2 ** k)
        if epsilon < v_range / 1000:  # Stop at fine resolution
            break

        # Count non-empty boxes
        n_boxes = 0
        current_box = -1
        for v in values:
            box = int((v - v_min) / epsilon)
            if box != current_box:
                n_boxes += 1
                current_box = box

        scales.append(epsilon)
        counts.append(n_boxes)
        k += 1

    if len(scales) < min_scales:
        return 0.0, 0.0, 0.0, scales, counts

    # Linear regression: log(N) = -D * log(epsilon) + c
    log_inv_eps = [math.log(1/e) for e in scales]
    log_counts = [math.log(n) for n in counts]

    # Compute D via least squares
    n = len(scales)
    sum_x = sum(log_inv_eps)
    sum_y = sum(log_counts)
    sum_xy = sum(x*y for x, y in zip(log_inv_eps, log_counts))
    sum_x2 = sum(x*x for x in log_inv_eps)

    D = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)

    # R-squared
    y_mean = sum_y / n
    ss_tot = sum((y - y_mean) ** 2 for y in log_counts)
    c = (sum_y - D * sum_x) / n
    ss_res = sum((y - (D * x + c)) ** 2 for x, y in zip(log_inv_eps, log_counts))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    # Standard error
    D_std = math.sqrt(ss_res / ((n - 2) * (sum_x2 - sum_x ** 2 / n))) if n > 2 else 0

    return D, D_std, r_squared, scales, counts
```

---

## 4. Integration into Signal Fusion

### Weight Selection Rationale

Based on literature review and backtesting principles:

| Component | Weight | Rationale |
|-----------|--------|-----------|
| Whale Flow | 0.25 | Strongest single predictor (smart money) |
| Symbolic | 0.15 | Highest academic accuracy gain (+25%) |
| UTXOracle | 0.15 | Core price signal |
| Funding | 0.15 | Strong contrarian indicator |
| OI | 0.10 | Confirms leverage buildup |
| Power Law | 0.10 | Regime detection |
| Fractal | 0.10 | Structure confirmation |

### Confidence Interval Interpretation

From Monte Carlo bootstrap sampling:
- CI contains zero: Uncertain, recommend HOLD
- CI entirely positive: High confidence BUY
- CI entirely negative: High confidence SELL
- Wide CI: High uncertainty, reduce position size

### Regime Classification Matrix

| Power Law | Symbolic | Fractal | Interpretation |
|-----------|----------|---------|----------------|
| ACCUMULATION | LOW_H | WHALE | Strong BUY |
| ACCUMULATION | HIGH_H | WHALE | Uncertain (whale + chaos) |
| DISTRIBUTION | LOW_H | RETAIL | Strong SELL |
| NEUTRAL | EDGE | MIXED | Watch for breakout |

---

## 5. References

### Primary Sources

1. Clauset, A., Shalizi, C. R., & Newman, M. E. J. (2009). Power-law distributions in empirical data. SIAM Review, 51(4), 661-703.

2. Bandt, C., & Pompe, B. (2002). Permutation entropy: a natural complexity measure for time series. Physical Review Letters, 88(17), 174102.

3. Liebovitch, L. S., & Toth, T. (1989). A fast algorithm to determine fractal dimensions by box counting. Physics Letters A, 141(8-9), 386-390.

4. Mandelbrot, B. B. (1982). The Fractal Geometry of Nature. W.H. Freeman.

### Bitcoin-Specific

5. Kondor, D., Posfai, M., Csabai, I., & Vattay, G. (2014). Do the rich get richer? An empirical analysis of the Bitcoin transaction network. PLoS ONE, 9(2), e86197.

6. Kristoufek, L. (2015). What are the main drivers of the Bitcoin price? Evidence from wavelet coherence analysis. PLoS ONE, 10(4), e0123923.

### Complexity Theory

7. Lopez-Ruiz, R., Mancini, H. L., & Calbet, X. (1995). A statistical measure of complexity. Physics Letters A, 209(5-6), 321-326.

8. Rosso, O. A., Larrondo, H. A., Martin, M. T., Plastino, A., & Fuentes, M. A. (2007). Distinguishing noise from chaos. Physical Review Letters, 99(15), 154102.

---

## 6. Implementation Checklist

- [ ] Power Law: MLE estimator with KS validation
- [ ] Power Law: x_min auto-selection (use 10th percentile as default)
- [ ] Power Law: Regime classification thresholds
- [ ] Symbolic: Permutation pattern extraction
- [ ] Symbolic: Normalized entropy computation
- [ ] Symbolic: Statistical complexity (H-C plane)
- [ ] Symbolic: Series trend computation (first-half vs second-half mean)
- [ ] Symbolic: Pattern type classification (ACCUMULATION vs DISTRIBUTION based on trend)
- [ ] Fractal: Box-counting algorithm
- [ ] Fractal: Linear regression with R^2
- [ ] Fractal: Structure classification
- [ ] Integration: 7-component fusion weights
- [ ] Integration: Weight renormalization
- [ ] Integration: Backward compatibility
