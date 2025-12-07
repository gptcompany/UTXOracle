"""Statistical tests for metric validation.

Pure Python implementations of statistical significance tests:
- t-test (one-sample)
- Cohen's d effect size
- Bootstrap confidence intervals
- t-distribution CDF approximation

No external dependencies (scipy not required).
"""

import math
import random
from typing import Optional


def mean(data: list[float]) -> float:
    """Calculate arithmetic mean."""
    if not data:
        return 0.0
    return sum(data) / len(data)


def stdev(data: list[float], sample: bool = True) -> float:
    """Calculate standard deviation.

    Args:
        data: List of values
        sample: If True, use sample std (n-1), else population (n)
    """
    n = len(data)
    if n < 2:
        return 0.0

    m = mean(data)
    variance = sum((x - m) ** 2 for x in data)
    divisor = n - 1 if sample else n
    return math.sqrt(variance / divisor)


def _gamma_lanczos(z: float) -> float:
    """Gamma function using Lanczos approximation.

    Accurate for positive real numbers.
    """
    if z < 0.5:
        # Reflection formula
        return math.pi / (math.sin(math.pi * z) * _gamma_lanczos(1 - z))

    z -= 1
    g = 7
    coefficients = [
        0.99999999999980993,
        676.5203681218851,
        -1259.1392167224028,
        771.32342877765313,
        -176.61502916214059,
        12.507343278686905,
        -0.13857109526572012,
        9.9843695780195716e-6,
        1.5056327351493116e-7,
    ]

    x = coefficients[0]
    for i in range(1, g + 2):
        x += coefficients[i] / (z + i)

    t = z + g + 0.5
    return math.sqrt(2 * math.pi) * (t ** (z + 0.5)) * math.exp(-t) * x


def _beta_incomplete(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b).

    Uses continued fraction approximation.
    """
    if x < 0 or x > 1:
        raise ValueError("x must be in [0, 1]")

    if x == 0 or x == 1:
        return x

    # Use symmetry: I_x(a, b) = 1 - I_{1-x}(b, a)
    if x > (a + 1) / (a + b + 2):
        return 1.0 - _beta_incomplete(b, a, 1 - x)

    # Calculate continued fraction
    # Using Lentz's algorithm
    eps = 1e-14
    max_iter = 200

    # Front factor
    lnbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1 - x) - lnbeta) / a

    # Continued fraction
    f = 1.0
    c = 1.0
    d = 0.0

    for m in range(max_iter):
        # Calculate a_m coefficient
        if m == 0:
            am = 1.0
        elif m % 2 == 1:
            k = (m - 1) // 2
            am = -(a + k) * (a + b + k) * x / ((a + 2 * k) * (a + 2 * k + 1))
        else:
            k = m // 2
            am = k * (b - k) * x / ((a + 2 * k - 1) * (a + 2 * k))

        d = 1.0 + am * d
        if abs(d) < eps:
            d = eps
        d = 1.0 / d

        c = 1.0 + am / c
        if abs(c) < eps:
            c = eps

        delta = c * d
        f *= delta

        if abs(delta - 1.0) < eps:
            break

    return front * f


def t_cdf(t: float, df: float) -> float:
    """Cumulative distribution function of Student's t-distribution.

    Args:
        t: t-statistic value
        df: Degrees of freedom

    Returns:
        Probability P(T <= t) for T ~ t(df)
    """
    if df <= 0:
        return float("nan")

    # Use relationship to incomplete beta function
    # P(T <= t) = 1 - 0.5 * I_{x}(df/2, 0.5)
    # where x = df / (df + t^2)

    x = df / (df + t * t)

    try:
        ibeta = _beta_incomplete(df / 2, 0.5, x)
    except (ValueError, OverflowError):
        # Fallback for numerical issues
        if t > 10:
            return 0.99999
        if t < -10:
            return 0.00001
        return 0.5

    if t >= 0:
        return 1 - 0.5 * ibeta
    else:
        return 0.5 * ibeta


def t_test_vs_baseline(
    actual: float,
    baseline_samples: list[float],
) -> tuple[float, float]:
    """One-sample t-test: is actual significantly different from baseline?

    Tests whether the actual value is significantly different from
    the mean of the baseline samples.

    Args:
        actual: The observed value to test
        baseline_samples: Sample distribution to compare against

    Returns:
        Tuple of (t_statistic, two_tailed_p_value)
    """
    if not baseline_samples or len(baseline_samples) < 2:
        return 0.0, 1.0

    n = len(baseline_samples)
    mean_baseline = mean(baseline_samples)
    std_baseline = stdev(baseline_samples)

    if std_baseline == 0:
        # No variance in baseline - can't compute t-test
        return 0.0, 1.0 if actual == mean_baseline else 0.0

    # Standard error of the mean
    se = std_baseline / math.sqrt(n)

    # t-statistic: how many standard errors is actual from baseline mean?
    t_stat = (actual - mean_baseline) / se

    # Two-tailed p-value
    df = n - 1
    p_value = 2 * (1 - t_cdf(abs(t_stat), df))

    return t_stat, p_value


def cohens_d(
    actual: float,
    baseline_samples: list[float],
) -> float:
    """Calculate Cohen's d effect size.

    Effect size interpretation (absolute value):
    - 0.2: small effect
    - 0.5: medium effect
    - 0.8: large effect
    - 1.2+: very large effect

    Args:
        actual: The observed value
        baseline_samples: Sample distribution to compare against

    Returns:
        Cohen's d (positive = actual > baseline mean)
    """
    if not baseline_samples:
        return 0.0

    mean_baseline = mean(baseline_samples)
    std_baseline = stdev(baseline_samples)

    if std_baseline == 0:
        return 0.0 if actual == mean_baseline else float("inf")

    return (actual - mean_baseline) / std_baseline


def interpret_cohens_d(d: float) -> str:
    """Interpret Cohen's d effect size.

    Args:
        d: Cohen's d value (can be negative)

    Returns:
        Human-readable interpretation
    """
    abs_d = abs(d)
    direction = "above" if d > 0 else "below"

    if abs_d < 0.2:
        return f"Negligible effect ({direction} baseline)"
    elif abs_d < 0.5:
        return f"Small effect ({direction} baseline)"
    elif abs_d < 0.8:
        return f"Medium effect ({direction} baseline)"
    elif abs_d < 1.2:
        return f"Large effect ({direction} baseline)"
    else:
        return f"Very large effect ({direction} baseline)"


def bootstrap_ci(
    data: list[float],
    confidence: float = 0.95,
    n_bootstrap: int = 1000,
    seed: Optional[int] = 42,
) -> tuple[float, float]:
    """Bootstrap confidence interval for the mean.

    Uses percentile method.

    Args:
        data: Sample data
        confidence: Confidence level (e.g., 0.95 for 95%)
        n_bootstrap: Number of bootstrap samples
        seed: Random seed for reproducibility

    Returns:
        Tuple of (lower_bound, upper_bound)
    """
    if not data:
        return 0.0, 0.0

    n = len(data)
    if n == 1:
        return data[0], data[0]

    if seed is not None:
        random.seed(seed)

    # Generate bootstrap means
    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = random.choices(data, k=n)
        bootstrap_means.append(mean(sample))

    # Sort for percentiles
    bootstrap_means.sort()

    # Calculate percentile indices
    alpha = 1 - confidence
    lower_idx = int(alpha / 2 * n_bootstrap)
    upper_idx = int((1 - alpha / 2) * n_bootstrap) - 1

    # Clamp indices
    lower_idx = max(0, min(lower_idx, n_bootstrap - 1))
    upper_idx = max(0, min(upper_idx, n_bootstrap - 1))

    return bootstrap_means[lower_idx], bootstrap_means[upper_idx]


def two_sample_t_test(
    sample1: list[float],
    sample2: list[float],
    equal_variance: bool = False,
) -> tuple[float, float]:
    """Two-sample t-test (independent samples).

    Tests whether two samples have significantly different means.

    Args:
        sample1: First sample
        sample2: Second sample
        equal_variance: If True, use pooled variance (Student's t-test)
                       If False, use Welch's t-test (default)

    Returns:
        Tuple of (t_statistic, two_tailed_p_value)
    """
    n1 = len(sample1)
    n2 = len(sample2)

    if n1 < 2 or n2 < 2:
        return 0.0, 1.0

    mean1 = mean(sample1)
    mean2 = mean(sample2)
    var1 = stdev(sample1) ** 2
    var2 = stdev(sample2) ** 2

    if equal_variance:
        # Pooled variance (Student's t-test)
        sp2 = ((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2)
        se = math.sqrt(sp2 * (1 / n1 + 1 / n2))
        df = n1 + n2 - 2
    else:
        # Welch's t-test (unequal variances)
        se = math.sqrt(var1 / n1 + var2 / n2)
        if se == 0:
            return 0.0, 1.0 if mean1 == mean2 else 0.0

        # Welch-Satterthwaite degrees of freedom
        num = (var1 / n1 + var2 / n2) ** 2
        denom = (var1 / n1) ** 2 / (n1 - 1) + (var2 / n2) ** 2 / (n2 - 1)
        df = num / denom if denom > 0 else n1 + n2 - 2

    if se == 0:
        return 0.0, 1.0 if mean1 == mean2 else 0.0

    t_stat = (mean1 - mean2) / se
    p_value = 2 * (1 - t_cdf(abs(t_stat), df))

    return t_stat, p_value
