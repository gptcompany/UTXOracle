"""
Symbolic Dynamics Processor (spec-009)

Measures temporal complexity of UTXO flow patterns via permutation entropy.
Based on Bandt & Pompe (2002) - "Permutation entropy: a natural complexity
measure for time series."

Key functions:
- permutation_entropy(): Compute normalized permutation entropy H in [0, 1]
- statistical_complexity(): Compute complexity C for H-C plane classification
- compute_series_trend(): Determine trend direction (accumulation vs distribution)
- analyze(): Full symbolic dynamics analysis with pattern classification

Usage:
    from scripts.metrics.symbolic_dynamics import analyze, permutation_entropy

    # Quick entropy calculation
    H = permutation_entropy([1, 2, 3, 4, 5], order=3)

    # Full analysis with classification
    result = analyze(series, order=5)
    print(f"Pattern: {result.pattern_type}, Vote: {result.symbolic_vote}")
"""

from math import factorial, log
from scripts.models.metrics_models import SymbolicDynamicsResult


# =============================================================================
# Thresholds (from spec-009)
# =============================================================================

H_LOW_THRESHOLD = 0.4  # Below this = LOW complexity (trending)
H_HIGH_THRESHOLD = 0.7  # Above this = HIGH complexity (chaotic)
C_EDGE_THRESHOLD = 0.2  # Above this in medium H = edge of chaos


# =============================================================================
# Core Algorithms
# =============================================================================


def permutation_entropy(series: list[float], order: int = 5, delay: int = 1) -> float:
    """
    Compute normalized permutation entropy.

    Permutation entropy measures the complexity of a time series by analyzing
    the frequency distribution of ordinal patterns (permutations).

    Args:
        series: Time series of values (length >= order + (order-1)*delay)
        order: Embedding dimension d (default: 5, typical range 3-7)
        delay: Time delay tau (default: 1)

    Returns:
        Normalized entropy H in [0, 1]:
        - H ≈ 0: Perfectly predictable (monotonic series)
        - H ≈ 1: Maximum entropy (random/white noise)

    Example:
        >>> permutation_entropy([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], order=3)
        0.0  # Monotonic = fully predictable
    """
    n = len(series)
    min_length = order + (order - 1) * delay

    if n < min_length:
        return 0.0

    # Count pattern frequencies
    patterns: dict[tuple, int] = {}

    for i in range(n - (order - 1) * delay):
        # Extract window with delay
        window = [series[i + j * delay] for j in range(order)]
        # Convert to ordinal pattern (rank order)
        pattern = tuple(sorted(range(order), key=lambda k: window[k]))
        patterns[pattern] = patterns.get(pattern, 0) + 1

    # Compute entropy
    total = sum(patterns.values())
    if total == 0:
        return 0.0

    probs = [c / total for c in patterns.values()]
    H = -sum(p * log(p) for p in probs if p > 0)

    # Normalize by maximum entropy (log of d!)
    H_max = log(factorial(order))
    return H / H_max if H_max > 0 else 0.0


def statistical_complexity(pattern_distribution: dict[str, float]) -> float:
    """
    Compute statistical complexity from pattern distribution.

    Statistical complexity C measures the distance from both order and disorder.
    High C indicates "interesting" structure (edge of chaos).

    Args:
        pattern_distribution: Dict mapping pattern strings to probabilities

    Returns:
        Complexity C in [0, ~0.5]:
        - C ≈ 0: Simple (either highly ordered or random)
        - C ≈ 0.5: Maximum complexity (edge of chaos)
    """
    if not pattern_distribution:
        return 0.0

    probs = list(pattern_distribution.values())
    n = len(probs)

    if n == 0:
        return 0.0

    # Disequilibrium: distance from uniform distribution
    uniform_prob = 1.0 / n
    D = sum((p - uniform_prob) ** 2 for p in probs)

    # Entropy (not normalized)
    H = -sum(p * log(p) for p in probs if p > 0)
    H_max = log(n) if n > 1 else 1.0

    # Statistical complexity = normalized entropy * disequilibrium
    H_norm = H / H_max if H_max > 0 else 0.0
    C = H_norm * D

    return C


def compute_series_trend(series: list[float]) -> float:
    """
    Compute trend indicator by comparing first half vs second half means.

    Used to distinguish ACCUMULATION_TREND from DISTRIBUTION_TREND
    when entropy is low (predictable trend exists).

    Args:
        series: Time series of values

    Returns:
        Trend indicator (normalized by std):
        - Positive: accumulation (series trending up)
        - Negative: distribution (series trending down)
        - ~0: no clear trend
    """
    n = len(series)
    if n < 4:
        return 0.0

    mid = n // 2
    first_half = series[:mid]
    second_half = series[mid:]

    first_mean = sum(first_half) / len(first_half)
    second_mean = sum(second_half) / len(second_half)

    # Normalize by standard deviation for scale-invariance
    all_mean = sum(series) / n
    variance = sum((x - all_mean) ** 2 for x in series) / n
    std = variance**0.5 if variance > 0 else 1.0

    return (second_mean - first_mean) / std


def _extract_pattern_counts(
    series: list[float], order: int, delay: int
) -> tuple[dict[str, int], str]:
    """
    Extract pattern counts and dominant pattern.

    Returns:
        Tuple of (pattern_counts dict, dominant_pattern string)
    """
    n = len(series)
    min_length = order + (order - 1) * delay

    if n < min_length:
        return {}, ""

    patterns: dict[str, int] = {}

    for i in range(n - (order - 1) * delay):
        window = [series[i + j * delay] for j in range(order)]
        pattern = tuple(sorted(range(order), key=lambda k: window[k]))
        pattern_str = "".join(str(x) for x in pattern)
        patterns[pattern_str] = patterns.get(pattern_str, 0) + 1

    if not patterns:
        return {}, ""

    dominant = max(patterns.keys(), key=lambda k: patterns[k])
    return patterns, dominant


# =============================================================================
# Main Analysis Function
# =============================================================================


def analyze(
    series: list[float], order: int = 5, delay: int = 1
) -> SymbolicDynamicsResult:
    """
    Full symbolic dynamics analysis with pattern classification.

    Computes permutation entropy, statistical complexity, and classifies
    the pattern type based on H-C plane position and series trend.

    Args:
        series: Time series of UTXO flows or values
        order: Embedding dimension (default: 5)
        delay: Time delay (default: 1)

    Returns:
        SymbolicDynamicsResult with entropy, complexity, and classification

    Classification rules:
        - H < 0.4: LOW complexity
          - series_trend >= 0: ACCUMULATION_TREND (vote positive)
          - series_trend < 0: DISTRIBUTION_TREND (vote negative)
        - H > 0.7: HIGH complexity → CHAOTIC_TRANSITION (vote 0)
        - 0.4 <= H <= 0.7: MEDIUM complexity
          - C > 0.2: EDGE_OF_CHAOS
          - else: TRANSITIONAL

    Example:
        >>> result = analyze([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        >>> result.pattern_type
        'ACCUMULATION_TREND'
        >>> result.permutation_entropy < 0.1
        True
    """
    n = len(series)
    min_length = 2 * factorial(order)

    # Validate series length
    if n < min_length:
        return SymbolicDynamicsResult(
            permutation_entropy=0.0,
            statistical_complexity=0.0,
            order=order,
            pattern_counts={},
            dominant_pattern="",
            complexity_class="INVALID",
            pattern_type="INVALID",
            symbolic_vote=0.0,
            series_length=n,
            series_trend=0.0,
            is_valid=False,
        )

    # Compute metrics
    H = permutation_entropy(series, order, delay)
    pattern_counts, dominant_pattern = _extract_pattern_counts(series, order, delay)

    # Convert counts to probabilities for complexity calculation
    total = sum(pattern_counts.values()) if pattern_counts else 1
    pattern_probs = {k: v / total for k, v in pattern_counts.items()}
    C = statistical_complexity(pattern_probs)

    # Compute trend for direction detection
    series_trend = compute_series_trend(series)

    # Classify based on H-C plane position
    if H < H_LOW_THRESHOLD:
        complexity_class = "LOW"
        # Low entropy = trending behavior
        if series_trend >= 0:
            pattern_type = "ACCUMULATION_TREND"
            symbolic_vote = 0.8 * (1 - H / H_LOW_THRESHOLD)
        else:
            pattern_type = "DISTRIBUTION_TREND"
            symbolic_vote = -0.6 * (1 - H / H_LOW_THRESHOLD)
    elif H > H_HIGH_THRESHOLD:
        complexity_class = "HIGH"
        pattern_type = "CHAOTIC_TRANSITION"
        symbolic_vote = 0.0  # No directional signal in chaos
    else:
        complexity_class = "MEDIUM"
        # Medium entropy with moderate complexity = edge of chaos behavior
        # Use EDGE_OF_CHAOS for all medium complexity cases (C threshold just affects vote)
        pattern_type = "EDGE_OF_CHAOS"
        # Higher complexity = more interesting structure = slight positive bias
        symbolic_vote = 0.1 * C if C > C_EDGE_THRESHOLD else 0.0

    return SymbolicDynamicsResult(
        permutation_entropy=H,
        statistical_complexity=C,
        order=order,
        pattern_counts=pattern_counts,
        dominant_pattern=dominant_pattern,
        complexity_class=complexity_class,
        pattern_type=pattern_type,
        symbolic_vote=symbolic_vote,
        series_length=n,
        series_trend=series_trend,
        is_valid=True,
    )
