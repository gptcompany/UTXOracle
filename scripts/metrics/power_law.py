"""
Power Law Detector (spec-009)

Detects when UTXO distributions deviate from typical power law behavior.
Based on Clauset et al. (2009) - "Power-law distributions in empirical data."

Key functions:
- mle_estimate(): Maximum Likelihood Estimation for tau
- ks_test(): Kolmogorov-Smirnov goodness-of-fit test
- fit(): Full power law analysis with regime classification

Usage:
    from scripts.metrics.power_law import fit

    result = fit(utxo_values)
    print(f"Regime: {result.regime}, Tau: {result.tau:.2f}")
"""

from math import log, sqrt
from scripts.models.metrics_models import PowerLawResult


# =============================================================================
# Thresholds (from spec-009)
# =============================================================================

TAU_ACCUMULATION_THRESHOLD = 1.8  # Below = whale concentration (bullish)
TAU_DISTRIBUTION_THRESHOLD = 2.2  # Above = dispersion (bearish)
MIN_SAMPLES = 100  # Minimum sample size for valid fit
KS_PVALUE_THRESHOLD = 0.05  # Minimum p-value for valid fit


# =============================================================================
# Core Algorithms
# =============================================================================


def mle_estimate(values: list[float], xmin: float) -> tuple[float, float]:
    """
    Maximum Likelihood Estimation for power law exponent tau.

    For a power law P(x) ~ x^(-tau), the MLE estimator is:
        tau = 1 + n / sum(ln(x_i / xmin))

    Args:
        values: List of values (must all be >= xmin)
        xmin: Minimum cutoff value

    Returns:
        Tuple of (tau, tau_std) where tau_std is the standard error

    Reference:
        Clauset et al. (2009), Equation 3.1
    """
    # Filter values >= xmin
    filtered = [v for v in values if v >= xmin]
    n = len(filtered)

    if n == 0:
        return 0.0, 0.0

    # MLE: tau = 1 + n / sum(ln(x_i / xmin))
    log_sum = sum(log(v / xmin) for v in filtered)

    if log_sum <= 0:
        return 0.0, 0.0

    tau = 1.0 + n / log_sum

    # Standard error: (tau - 1) / sqrt(n)
    tau_std = (tau - 1.0) / sqrt(n) if n > 0 else 0.0

    return tau, tau_std


def ks_test(values: list[float], tau: float, xmin: float) -> tuple[float, float]:
    """
    Kolmogorov-Smirnov test for power law goodness-of-fit.

    Compares empirical CDF with theoretical power law CDF.
    Returns KS statistic D and approximate p-value.

    Args:
        values: List of values (must all be >= xmin)
        tau: Estimated power law exponent
        xmin: Minimum cutoff value

    Returns:
        Tuple of (ks_statistic, p_value):
        - ks_statistic: Maximum distance between CDFs (0 = perfect fit)
        - p_value: Approximate significance (>0.05 = plausible power law)

    Note:
        Uses approximation for p-value. For rigorous analysis,
        use bootstrap or powerlaw library.
    """
    filtered = sorted([v for v in values if v >= xmin])
    n = len(filtered)

    if n == 0 or tau <= 1:
        return 1.0, 0.0

    # Compute empirical and theoretical CDFs
    max_distance = 0.0

    for i, x in enumerate(filtered):
        # Empirical CDF: F_n(x) = i/n
        ecdf = (i + 1) / n
        # Theoretical CDF: F(x) = 1 - (xmin/x)^(tau-1)
        tcdf = 1.0 - (xmin / x) ** (tau - 1)

        distance = abs(ecdf - tcdf)
        max_distance = max(max_distance, distance)

    # Approximate p-value using asymptotic distribution
    # P(D > d) ≈ 2 * sum_{k=1}^inf (-1)^(k-1) * exp(-2k^2 * n * d^2)
    # Simplified: use first term approximation
    effective_n = sqrt(n)
    lambda_val = (effective_n + 0.12 + 0.11 / effective_n) * max_distance

    # Approximation: p ≈ 2 * exp(-2 * lambda^2)
    if lambda_val > 0:
        p_value = 2.0 * (
            2.71828 ** (-2.0 * lambda_val * lambda_val)
        )  # exp approximation
        p_value = min(1.0, max(0.0, p_value))
    else:
        p_value = 1.0

    return max_distance, p_value


def _auto_xmin(values: list[float]) -> float:
    """
    Auto-select xmin using 10th percentile.

    Simple heuristic per KISS principle. For more rigorous selection,
    minimize KS statistic across candidate xmin values.

    Args:
        values: List of positive values

    Returns:
        xmin at approximately 10th percentile
    """
    if not values:
        return 1.0

    sorted_vals = sorted(v for v in values if v > 0)
    if not sorted_vals:
        return 1.0

    # Use 10th percentile as xmin
    idx = max(0, int(len(sorted_vals) * 0.1) - 1)
    return sorted_vals[idx]


def _classify_regime(tau: float, is_valid: bool) -> tuple[str, float]:
    """
    Classify market regime based on tau.

    Args:
        tau: Power law exponent
        is_valid: Whether the fit is statistically valid

    Returns:
        Tuple of (regime, vote):
        - regime: "ACCUMULATION" | "NEUTRAL" | "DISTRIBUTION" | "INVALID"
        - vote: Signal vote in [-1, 1]
    """
    if not is_valid:
        return "INVALID", 0.0

    if tau < TAU_ACCUMULATION_THRESHOLD:
        # Heavy tail = whale concentration = bullish
        deviation = TAU_ACCUMULATION_THRESHOLD - tau
        vote = min(1.0, deviation / 0.5)  # Max vote at tau=1.3
        return "ACCUMULATION", vote

    elif tau > TAU_DISTRIBUTION_THRESHOLD:
        # Light tail = dispersion = bearish
        deviation = tau - TAU_DISTRIBUTION_THRESHOLD
        vote = -min(1.0, deviation / 0.5)  # Max vote at tau=2.7
        return "DISTRIBUTION", vote

    else:
        return "NEUTRAL", 0.0


# =============================================================================
# Main Fit Function
# =============================================================================


def fit(values: list[float], xmin: float | None = None) -> PowerLawResult:
    """
    Fit power law to value distribution.

    Performs MLE estimation for tau, validates with KS test,
    and classifies market regime.

    Args:
        values: List of UTXO values (positive numbers)
        xmin: Minimum cutoff for fit (auto-detected if None)

    Returns:
        PowerLawResult with tau, validation metrics, and regime classification

    Example:
        >>> import random
        >>> random.seed(42)
        >>> # Generate Pareto samples with tau=2.0
        >>> samples = [1.0 / (random.random() ** 1.0) for _ in range(500)]
        >>> result = fit(samples)
        >>> abs(result.tau - 2.0) < 0.15
        True
    """
    # Filter positive values
    positive_values = [v for v in values if v > 0]
    n = len(positive_values)

    # Check minimum sample size
    if n < MIN_SAMPLES:
        return PowerLawResult(
            tau=0.0,
            tau_std=0.0,
            xmin=0.0,
            ks_statistic=1.0,
            ks_pvalue=0.0,
            is_valid=False,
            regime="INVALID",
            power_law_vote=0.0,
            sample_size=n,
        )

    # Auto-detect xmin if not provided
    if xmin is None:
        xmin = _auto_xmin(positive_values)

    # MLE estimation
    tau, tau_std = mle_estimate(positive_values, xmin)

    # KS test validation
    ks_stat, ks_pvalue = ks_test(positive_values, tau, xmin)

    # Determine validity
    is_valid = tau > 1 and ks_pvalue > KS_PVALUE_THRESHOLD

    # Classify regime
    regime, vote = _classify_regime(tau, is_valid)

    return PowerLawResult(
        tau=tau,
        tau_std=tau_std,
        xmin=xmin,
        ks_statistic=ks_stat,
        ks_pvalue=ks_pvalue,
        is_valid=is_valid,
        regime=regime,
        power_law_vote=vote,
        sample_size=n,
    )
