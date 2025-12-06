"""
Fractal Dimension Analyzer (spec-009)

Measures fractal dimension of UTXO value distributions via box-counting.
Based on Liebovitch & Toth (1989) - "A fast algorithm to determine
fractal dimensions by box counting."

Key functions:
- box_count(): Count boxes of size epsilon needed to cover value set
- linear_regression(): Log-log regression for dimension estimation
- analyze(): Full fractal analysis with structure classification

Usage:
    from scripts.metrics.fractal_dimension import analyze

    result = analyze(utxo_values)
    print(f"Structure: {result.structure}, D: {result.dimension:.2f}")
"""

from math import log
from scripts.models.metrics_models import FractalDimensionResult


# =============================================================================
# Thresholds (from spec-009)
# =============================================================================

D_WHALE_THRESHOLD = 0.8  # Below = concentrated (whale activity)
D_RETAIL_THRESHOLD = 1.2  # Above = dispersed (retail fragmentation)
R_SQUARED_MIN = 0.7  # Minimum R² for valid fit (relaxed for clustered data)
MIN_SCALES = 5  # Minimum number of scales for valid fit


# =============================================================================
# Core Algorithms
# =============================================================================


def box_count(values: list[float], epsilon: float) -> int:
    """
    Count boxes of size epsilon needed to cover the value set.

    Divides the value range into boxes of size epsilon and counts
    how many boxes contain at least one value.

    Args:
        values: Sorted list of values
        epsilon: Box size

    Returns:
        Number of non-empty boxes

    Example:
        >>> box_count([0.1, 0.2, 0.5, 0.9], epsilon=0.3)
        3  # Boxes: [0-0.3], [0.3-0.6], [0.6-0.9]
    """
    if not values or epsilon <= 0:
        return 0

    v_min = values[0]

    # Count unique box indices
    boxes = set()
    for v in values:
        box_idx = int((v - v_min) / epsilon)
        boxes.add(box_idx)

    return len(boxes)


def linear_regression(x: list[float], y: list[float]) -> tuple[float, float, float]:
    """
    Simple linear regression: y = slope * x + intercept.

    Args:
        x: Independent variable values
        y: Dependent variable values

    Returns:
        Tuple of (slope, intercept, r_squared)
    """
    n = len(x)
    if n < 2 or n != len(y):
        return 0.0, 0.0, 0.0

    # Compute means
    x_mean = sum(x) / n
    y_mean = sum(y) / n

    # Compute slope
    numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    denominator = sum((xi - x_mean) ** 2 for xi in x)

    if denominator == 0:
        return 0.0, 0.0, 0.0

    slope = numerator / denominator
    intercept = y_mean - slope * x_mean

    # Compute R²
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))

    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return slope, intercept, r_squared


def _compute_dimension(
    values: list[float], min_scales: int = MIN_SCALES
) -> tuple[float, float, float, list[float], list[int]]:
    """
    Compute box-counting dimension.

    Uses multiple scales (powers of 2) and performs log-log regression.

    Args:
        values: List of values to analyze
        min_scales: Minimum number of scales for valid fit

    Returns:
        Tuple of (D, D_std, r_squared, scales, counts)
    """
    if not values:
        return 0.0, 0.0, 0.0, [], []

    sorted_values = sorted(values)
    v_min, v_max = sorted_values[0], sorted_values[-1]
    v_range = v_max - v_min

    if v_range == 0:
        # All values identical
        return 0.0, 0.0, 0.0, [], []

    # Generate scales (powers of 2)
    scales = []
    counts = []

    k = 1
    while True:
        epsilon = v_range / (2**k)
        if epsilon < v_range / 1000:  # Stop at fine resolution
            break

        n_boxes = box_count(sorted_values, epsilon)
        if n_boxes > 0:
            scales.append(epsilon)
            counts.append(n_boxes)

        k += 1

    if len(scales) < min_scales:
        return 0.0, 0.0, 0.0, scales, counts

    # Log-log regression: log(N) = D * log(1/epsilon) + c
    # So D is the slope of log(N) vs log(1/epsilon)
    log_inv_eps = [log(1.0 / e) for e in scales]
    log_counts = [log(n) for n in counts]

    D, _, r_squared = linear_regression(log_inv_eps, log_counts)

    # Standard error approximation
    n = len(scales)
    if n > 2 and r_squared < 1.0:
        ss_res = sum((log_counts[i] - D * log_inv_eps[i]) ** 2 for i in range(n))
        x_var = sum((x - sum(log_inv_eps) / n) ** 2 for x in log_inv_eps)
        D_std = (ss_res / ((n - 2) * x_var)) ** 0.5 if x_var > 0 else 0.0
    else:
        D_std = 0.0

    return D, D_std, r_squared, scales, counts


def _classify_structure(dimension: float, is_valid: bool) -> tuple[str, float]:
    """
    Classify market structure based on fractal dimension.

    Args:
        dimension: Box-counting dimension D
        is_valid: Whether the fit is statistically valid

    Returns:
        Tuple of (structure, vote):
        - structure: "WHALE_DOMINATED" | "MIXED" | "RETAIL_DOMINATED" | "INVALID"
        - vote: Signal vote in [-1, 1]
    """
    if not is_valid:
        return "INVALID", 0.0

    if dimension < D_WHALE_THRESHOLD:
        # Concentrated = whale activity = bullish (smart money)
        vote = 0.5 * (D_WHALE_THRESHOLD - dimension) / D_WHALE_THRESHOLD
        return "WHALE_DOMINATED", vote

    elif dimension > D_RETAIL_THRESHOLD:
        # Dispersed = retail fragmentation = neutral to bearish
        deviation = dimension - D_RETAIL_THRESHOLD
        vote = -0.3 * deviation / (2.0 - D_RETAIL_THRESHOLD)
        return "RETAIL_DOMINATED", vote

    else:
        return "MIXED", 0.0


# =============================================================================
# Main Analysis Function
# =============================================================================


def analyze(
    values: list[float], min_scales: int = MIN_SCALES
) -> FractalDimensionResult:
    """
    Analyze value distribution using box-counting fractal dimension.

    Computes box-counting dimension D, validates fit quality (R²),
    and classifies market structure.

    Args:
        values: List of UTXO values
        min_scales: Minimum number of scales for valid fit (default: 5)

    Returns:
        FractalDimensionResult with dimension and structure classification

    Structure classification:
        - D < 0.8: WHALE_DOMINATED (concentrated, few clusters)
        - 0.8 <= D <= 1.2: MIXED (typical market)
        - D > 1.2: RETAIL_DOMINATED (highly dispersed)

    Example:
        >>> import random
        >>> random.seed(42)
        >>> uniform = [random.random() for _ in range(500)]
        >>> result = analyze(uniform)
        >>> 0.9 < result.dimension < 1.1
        True
    """
    # Filter positive values
    positive_values = [v for v in values if v > 0]
    n = len(positive_values)

    if n < 10:
        return FractalDimensionResult(
            dimension=0.0,
            dimension_std=0.0,
            r_squared=0.0,
            scales_used=[],
            counts=[],
            is_valid=False,
            structure="INVALID",
            fractal_vote=0.0,
            sample_size=n,
        )

    # Compute dimension
    D, D_std, r_squared, scales, counts = _compute_dimension(
        positive_values, min_scales
    )

    # Determine validity
    is_valid = len(scales) >= min_scales and r_squared >= R_SQUARED_MIN

    # Classify structure
    structure, vote = _classify_structure(D, is_valid)

    return FractalDimensionResult(
        dimension=D,
        dimension_std=D_std,
        r_squared=r_squared,
        scales_used=scales,
        counts=counts,
        is_valid=is_valid,
        structure=structure,
        fractal_vote=vote,
        sample_size=n,
    )
