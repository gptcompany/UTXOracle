"""
Enhanced Monte Carlo Fusion for Derivatives Historical Integration (spec-008).

Extends spec-007 Monte Carlo fusion from 2 components (whale + utxo)
to 4 components (whale + utxo + funding + oi).

Features:
- Bootstrap sampling with 1000 iterations
- 95% confidence intervals
- Dynamic weight redistribution when components unavailable
- Bimodal distribution detection for conflicting signals
"""

import logging
from typing import Literal, Optional

import numpy as np

from scripts.models.derivatives_models import EnhancedFusionResult

logger = logging.getLogger(__name__)

# Default weights (sum to 1.0)
DEFAULT_WEIGHTS = {
    "whale": 0.40,
    "utxo": 0.20,
    "funding": 0.25,
    "oi": 0.15,
}

# Monte Carlo settings
N_BOOTSTRAP_SAMPLES = 1000
CONFIDENCE_LEVEL = 0.95

# Action thresholds
BUY_THRESHOLD = 0.15
SELL_THRESHOLD = -0.15
HIGH_CONFIDENCE_THRESHOLD = 0.7


def redistribute_weights(
    missing_components: list[str],
) -> dict[str, float]:
    """
    Redistribute weights when some components are unavailable.

    Args:
        missing_components: List of missing component names.

    Returns:
        New weight dictionary summing to 1.0.

    Example:
        >>> redistribute_weights(["funding", "oi"])
        {"whale": 0.67, "utxo": 0.33, "funding": 0.0, "oi": 0.0}
    """
    weights = DEFAULT_WEIGHTS.copy()

    if not missing_components:
        return weights

    # Zero out missing components
    missing_weight = 0.0
    for comp in missing_components:
        if comp in weights:
            missing_weight += weights[comp]
            weights[comp] = 0.0

    # Redistribute to remaining components proportionally
    remaining = [k for k, v in weights.items() if v > 0]
    if remaining:
        total_remaining = sum(weights[k] for k in remaining)
        for comp in remaining:
            weights[comp] = weights[comp] / total_remaining

    logger.debug(f"Redistributed weights: {weights}")
    return weights


def detect_distribution_type(
    samples: np.ndarray,
) -> Literal["unimodal", "bimodal", "insufficient_data"]:
    """
    Detect if the sample distribution is bimodal (conflicting signals).

    Uses simple heuristic: if std > 0.35 and samples span positive/negative,
    likely bimodal (conflicting signals).

    Args:
        samples: Bootstrap sample array.

    Returns:
        Distribution type string.
    """
    if len(samples) < 100:
        return "insufficient_data"

    std = np.std(samples)
    has_positive = np.any(samples > 0.1)
    has_negative = np.any(samples < -0.1)

    if std > 0.35 and has_positive and has_negative:
        return "bimodal"
    return "unimodal"


def determine_action(
    signal_mean: float,
    action_confidence: float,
) -> Literal["BUY", "SELL", "HOLD"]:
    """
    Determine trading action from signal.

    Args:
        signal_mean: Mean signal value.
        action_confidence: Confidence in the action.

    Returns:
        BUY, SELL, or HOLD.
    """
    if signal_mean > BUY_THRESHOLD:
        return "BUY"
    elif signal_mean < SELL_THRESHOLD:
        return "SELL"
    else:
        return "HOLD"


def enhanced_monte_carlo_fusion(
    whale_vote: float,
    whale_conf: float,
    utxo_vote: float,
    utxo_conf: float,
    funding_vote: Optional[float] = None,
    oi_vote: Optional[float] = None,
    n_samples: int = N_BOOTSTRAP_SAMPLES,
    custom_weights: Optional[dict[str, float]] = None,
    seed: Optional[int] = None,
) -> EnhancedFusionResult:
    """
    Perform 4-component Monte Carlo signal fusion.

    Uses bootstrap sampling to combine signals with uncertainty quantification.

    Args:
        whale_vote: Whale flow signal (-1 to 1).
        whale_conf: Whale signal confidence (0 to 1).
        utxo_vote: UTXOracle confidence signal (-1 to 1).
        utxo_conf: UTXOracle confidence (0 to 1).
        funding_vote: Funding rate contrarian signal (optional).
        oi_vote: Open interest signal (optional).
        n_samples: Number of bootstrap iterations.
        custom_weights: Optional custom weights dict for optimization.
        seed: Optional random seed (None = non-deterministic, 42 = reproducible).

    Returns:
        EnhancedFusionResult with signal stats, action, and component breakdown.
    """
    # Determine which components are available
    missing = []
    if funding_vote is None:
        missing.append("funding")
    if oi_vote is None:
        missing.append("oi")

    derivatives_available = len(missing) == 0

    # Get weights (custom, redistributed, or default)
    if custom_weights is not None:
        weights = custom_weights.copy()
        # Zero out missing components and redistribute to remaining
        missing_weight = 0.0
        for comp in missing:
            if comp in weights:
                missing_weight += weights[comp]
                weights[comp] = 0.0
        # Redistribute missing weight proportionally to remaining components
        if missing_weight > 0:
            remaining = [k for k, v in weights.items() if v > 0 and k not in missing]
            if remaining:
                total_remaining = sum(weights[k] for k in remaining)
                for comp in remaining:
                    weights[comp] += missing_weight * (weights[comp] / total_remaining)
    else:
        weights = redistribute_weights(missing)

    # Build component arrays for sampling
    components = {
        "whale": (whale_vote, whale_conf, weights["whale"]),
        "utxo": (utxo_vote, utxo_conf, weights["utxo"]),
    }

    if funding_vote is not None:
        # Funding rate has fixed confidence (it's a direct contrarian signal)
        components["funding"] = (funding_vote, 0.8, weights["funding"])

    if oi_vote is not None:
        # OI signal has context-dependent confidence
        components["oi"] = (oi_vote, 0.7, weights["oi"])

    # Bootstrap sampling
    # Use seed if provided (for testing), otherwise non-deterministic
    if seed is not None:
        np.random.seed(seed)
    samples = np.zeros(n_samples)

    for i in range(n_samples):
        weighted_sum = 0.0

        for name, (vote, conf, weight) in components.items():
            if weight > 0:
                # Sample with noise based on confidence
                # Higher noise for lower confidence, and base noise for signal disagreement
                base_noise = 0.3  # Base uncertainty
                conf_factor = 1 - conf  # Lower confidence = more noise
                noise_std = base_noise * (0.5 + conf_factor)

                sampled_vote = vote + np.random.normal(0, noise_std)
                sampled_vote = np.clip(sampled_vote, -1, 1)
                weighted_sum += sampled_vote * weight

        samples[i] = weighted_sum

    # Calculate statistics
    signal_mean = float(np.mean(samples))
    signal_std = float(np.std(samples))

    # 95% confidence interval
    alpha = 1 - CONFIDENCE_LEVEL
    ci_lower = float(np.percentile(samples, alpha / 2 * 100))
    ci_upper = float(np.percentile(samples, (1 - alpha / 2) * 100))

    # Determine action and confidence
    # Confidence based on how strongly the signal points in one direction
    if signal_mean > 0:
        action_confidence = float(np.mean(samples > 0))
    elif signal_mean < 0:
        action_confidence = float(np.mean(samples < 0))
    else:
        # Exactly 0 mean: confidence is proportion of samples near zero (within threshold)
        action_confidence = float(np.mean(np.abs(samples) < BUY_THRESHOLD))

    action = determine_action(signal_mean, action_confidence)
    distribution_type = detect_distribution_type(samples)

    logger.info(
        f"Enhanced fusion: mean={signal_mean:.3f}, std={signal_std:.3f}, "
        f"CI=[{ci_lower:.3f}, {ci_upper:.3f}], action={action} "
        f"(conf={action_confidence:.2f}, derivatives={derivatives_available})"
    )

    return EnhancedFusionResult(
        signal_mean=signal_mean,
        signal_std=signal_std,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        action=action,
        action_confidence=action_confidence,
        n_samples=n_samples,
        whale_vote=whale_vote,
        whale_weight=weights["whale"],
        utxo_vote=utxo_vote,
        utxo_weight=weights["utxo"],
        funding_vote=funding_vote,
        funding_weight=weights["funding"],
        oi_vote=oi_vote,
        oi_weight=weights["oi"],
        derivatives_available=derivatives_available,
        data_freshness_minutes=0,  # To be set by caller
        distribution_type=distribution_type,
    )


def create_enhanced_result(
    whale_vote: float,
    whale_conf: float,
    utxo_vote: float,
    utxo_conf: float,
    funding_vote: Optional[float],
    oi_vote: Optional[float],
    data_freshness_minutes: int = 0,
    custom_weights: Optional[dict[str, float]] = None,
    seed: Optional[int] = None,
) -> EnhancedFusionResult:
    """
    High-level function to create enhanced fusion result.

    Wraps enhanced_monte_carlo_fusion with data freshness tracking.

    Args:
        whale_vote: Whale flow signal.
        whale_conf: Whale signal confidence.
        utxo_vote: UTXOracle confidence signal.
        utxo_conf: UTXOracle confidence.
        funding_vote: Funding rate contrarian signal (optional).
        oi_vote: Open interest signal (optional).
        data_freshness_minutes: Age of derivatives data.
        custom_weights: Optional custom weights dict for optimization.
        seed: Optional random seed.

    Returns:
        EnhancedFusionResult with all metadata.
    """
    result = enhanced_monte_carlo_fusion(
        whale_vote=whale_vote,
        whale_conf=whale_conf,
        utxo_vote=utxo_vote,
        utxo_conf=utxo_conf,
        funding_vote=funding_vote,
        oi_vote=oi_vote,
        custom_weights=custom_weights,
        seed=seed,
    )

    # Update freshness (create new instance since dataclass is frozen-like)
    return EnhancedFusionResult(
        signal_mean=result.signal_mean,
        signal_std=result.signal_std,
        ci_lower=result.ci_lower,
        ci_upper=result.ci_upper,
        action=result.action,
        action_confidence=result.action_confidence,
        n_samples=result.n_samples,
        whale_vote=result.whale_vote,
        whale_weight=result.whale_weight,
        utxo_vote=result.utxo_vote,
        utxo_weight=result.utxo_weight,
        funding_vote=result.funding_vote,
        funding_weight=result.funding_weight,
        oi_vote=result.oi_vote,
        oi_weight=result.oi_weight,
        derivatives_available=result.derivatives_available,
        data_freshness_minutes=data_freshness_minutes,
        distribution_type=result.distribution_type,
    )


__all__ = [
    "enhanced_monte_carlo_fusion",
    "redistribute_weights",
    "create_enhanced_result",
    "DEFAULT_WEIGHTS",
    "N_BOOTSTRAP_SAMPLES",
]
