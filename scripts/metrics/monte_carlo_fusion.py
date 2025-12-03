"""
Monte Carlo Signal Fusion (spec-007, User Story 1).

Upgrades linear fusion (0.7*whale + 0.3*utxo) to bootstrap sampling
with 95% confidence intervals.

Usage:
    from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion
    result = monte_carlo_fusion(whale_vote=0.8, whale_confidence=0.9,
                                utxo_vote=0.7, utxo_confidence=0.85)
"""

import random
from statistics import mean, stdev
from typing import Literal
from scripts.models.metrics_models import MonteCarloFusionResult

# Default weights for signal fusion
WHALE_WEIGHT = 0.7
UTXO_WEIGHT = 0.3

# Signal thresholds for action determination
BUY_THRESHOLD = 0.5
SELL_THRESHOLD = -0.5


def monte_carlo_fusion(
    whale_vote: float,
    whale_confidence: float,
    utxo_vote: float,
    utxo_confidence: float,
    n_samples: int = 1000,
) -> MonteCarloFusionResult:
    """
    Bootstrap sample the signal fusion with uncertainty propagation.

    The fusion uses weighted combination: 0.7*whale + 0.3*utxo
    Each signal is sampled with confidence as Bernoulli success rate.

    Args:
        whale_vote: Whale signal vote (-1.0 to 1.0)
        whale_confidence: Whale signal confidence (0.0 to 1.0)
        utxo_vote: UTXOracle signal vote (-1.0 to 1.0)
        utxo_confidence: UTXOracle signal confidence (0.0 to 1.0)
        n_samples: Number of bootstrap iterations (default 1000)

    Returns:
        MonteCarloFusionResult with signal stats and 95% CI
    """
    # Generate bootstrap samples
    samples = []
    for _ in range(n_samples):
        # Sample whale vote with confidence as Bernoulli success rate
        w = whale_vote if random.random() < whale_confidence else 0.0
        # Sample utxo vote with confidence as Bernoulli success rate
        u = utxo_vote if random.random() < utxo_confidence else 0.0
        # Fuse with weights
        samples.append(WHALE_WEIGHT * w + UTXO_WEIGHT * u)

    # Calculate statistics
    signal_mean = mean(samples)
    signal_std = stdev(samples) if len(samples) > 1 else 0.0

    # Calculate 95% CI (2.5% and 97.5% percentiles)
    sorted_samples = sorted(samples)
    ci_lower = sorted_samples[int(0.025 * n_samples)]
    ci_upper = sorted_samples[int(0.975 * n_samples)]

    # Detect distribution type
    distribution_type = detect_bimodal(samples)

    # Determine action and confidence
    action, action_confidence = determine_action(signal_mean, ci_lower, ci_upper)

    return MonteCarloFusionResult(
        signal_mean=signal_mean,
        signal_std=signal_std,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        action=action,
        action_confidence=action_confidence,
        n_samples=n_samples,
        distribution_type=distribution_type,
    )


def detect_bimodal(
    samples: list[float], n_bins: int = 20
) -> Literal["unimodal", "bimodal", "insufficient_data"]:
    """
    Detect if distribution is bimodal using histogram gap analysis.

    Args:
        samples: List of bootstrap samples
        n_bins: Number of histogram bins

    Returns:
        "bimodal" if gap detected, "unimodal" otherwise
    """
    if len(samples) < 50:
        return "insufficient_data"

    # Create histogram
    min_val, max_val = min(samples), max(samples)
    if max_val <= min_val:
        return "unimodal"

    bin_width = (max_val - min_val) / n_bins
    bins = [0] * n_bins

    for s in samples:
        idx = min(int((s - min_val) / bin_width), n_bins - 1)
        bins[idx] += 1

    # Detect gap: look for valley between two peaks
    threshold = len(samples) * 0.05  # 5% of samples per bin = significant

    peaks = [i for i, b in enumerate(bins) if b > threshold]

    if len(peaks) < 2:
        return "unimodal"

    # Check if there's a valley between peaks
    for i in range(peaks[0] + 1, peaks[-1]):
        if bins[i] < threshold * 0.3:  # Valley = <30% of peak threshold
            return "bimodal"

    return "unimodal"


def determine_action(
    signal_mean: float, ci_lower: float, ci_upper: float
) -> tuple[Literal["BUY", "SELL", "HOLD"], float]:
    """
    Determine trading action and confidence from signal distribution.

    Action rules:
    - BUY: signal_mean > 0.5
    - SELL: signal_mean < -0.5
    - HOLD: otherwise

    Confidence is based on CI crossing zero or threshold.

    Args:
        signal_mean: Mean of bootstrap samples
        ci_lower: 95% CI lower bound
        ci_upper: 95% CI upper bound

    Returns:
        Tuple of (action, confidence)
    """
    # Determine action based on mean
    if signal_mean > BUY_THRESHOLD:
        action = "BUY"
    elif signal_mean < SELL_THRESHOLD:
        action = "SELL"
    else:
        action = "HOLD"

    # Calculate action confidence
    # Higher confidence if CI doesn't cross zero (for BUY/SELL) or stays near zero (HOLD)
    ci_width = ci_upper - ci_lower

    if action == "BUY":
        # Confidence high if ci_lower > 0 (whole CI positive)
        if ci_lower > 0:
            action_confidence = min(0.95, 0.7 + 0.25 * (ci_lower / signal_mean))
        else:
            action_confidence = max(0.3, 0.5 - ci_width / 2)

    elif action == "SELL":
        # Confidence high if ci_upper < 0 (whole CI negative)
        if ci_upper < 0:
            action_confidence = min(
                0.95, 0.7 + 0.25 * (abs(ci_upper) / abs(signal_mean))
            )
        else:
            action_confidence = max(0.3, 0.5 - ci_width / 2)

    else:  # HOLD
        # Confidence high if signal is clearly near zero
        if ci_lower > -0.3 and ci_upper < 0.3:
            action_confidence = 0.8
        else:
            action_confidence = max(0.3, 0.6 - abs(signal_mean))

    return action, round(action_confidence, 3)
