"""
Monte Carlo Signal Fusion (spec-007 + spec-009).

spec-007: Original 2-component fusion (whale + utxo)
spec-009: Enhanced 7-component fusion with advanced metrics

Usage:
    # spec-007 (backward compatible)
    from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion
    result = monte_carlo_fusion(whale_vote=0.8, whale_confidence=0.9,
                                utxo_vote=0.7, utxo_confidence=0.85)

    # spec-009 (enhanced)
    from scripts.metrics.monte_carlo_fusion import enhanced_fusion
    result = enhanced_fusion(whale_vote=0.8, whale_conf=0.9, utxo_vote=0.7,
                             utxo_conf=0.85, symbolic_vote=0.6, ...)
"""

import random
from statistics import mean, stdev
from typing import Literal, Optional
from scripts.models.metrics_models import MonteCarloFusionResult, EnhancedFusionResult

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


# =============================================================================
# spec-009 + spec-010 + spec-014 + spec-016: Enhanced 9-Component Fusion
# =============================================================================

# Legacy weights (spec-009 original, 7 components)
LEGACY_WEIGHTS = {
    "whale": 0.25,
    "utxo": 0.15,
    "funding": 0.15,
    "oi": 0.10,
    "power_law": 0.10,
    "symbolic": 0.15,
    "fractal": 0.10,
}

# Evidence-based weights (spec-014, 8 components)
# Adjusted based on academic literature review
EVIDENCE_BASED_WEIGHTS = {
    "whale": 0.15,  # Reduced from 0.25 (low evidence grade)
    "utxo": 0.20,  # Increased from 0.15 (entity-adjusted)
    "funding": 0.05,  # Reduced from 0.15 (LAGGING indicator)
    "oi": 0.10,
    "power_law": 0.15,  # Increased from 0.10
    "symbolic": 0.15,
    "fractal": 0.10,
    "wasserstein": 0.10,  # spec-010
}

# Default weights for enhanced fusion (sum = 1.0)
# Updated for 9 components including SOPR (spec-016)
# SOPR weight 0.15 based on evidence grade A-B (82.44% accuracy - Omole & Enke 2024)
ENHANCED_WEIGHTS = {
    "whale": 0.12,  # Primary signal (reduced from 0.23)
    "utxo": 0.18,  # Price signal (entity-adjusted)
    "funding": 0.05,  # Derivatives (LAGGING indicator)
    "oi": 0.08,  # Derivatives
    "power_law": 0.12,  # Regime
    "symbolic": 0.12,  # Temporal
    "fractal": 0.08,  # Structure
    "wasserstein": 0.10,  # Distribution shift (spec-010)
    "sopr": 0.15,  # SOPR signal (spec-016) - Highest evidence grade
}


def validate_weights(weights: dict[str, float]) -> bool:
    """
    Validate that weights are valid (sum to 1.0, all non-negative).

    Args:
        weights: Dictionary of component weights

    Returns:
        True if valid

    Raises:
        ValueError: If weights are invalid
    """
    # Check for negative weights
    for key, value in weights.items():
        if value < 0:
            raise ValueError(f"Weight for '{key}' must be non-negative, got {value}")

    # Check sum (with tolerance)
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        raise ValueError(f"Weights must sum to 1.0, got {total:.4f}")

    return True


def load_weights_from_env() -> dict[str, float]:
    """
    Load fusion weights from environment variables.

    If FUSION_USE_LEGACY_WEIGHTS=true, returns legacy weights.
    Otherwise returns evidence-based weights (can be overridden by env vars).

    Returns:
        Dictionary of component weights
    """
    import os

    if os.getenv("FUSION_USE_LEGACY_WEIGHTS", "false").lower() == "true":
        return LEGACY_WEIGHTS.copy()

    # Start with evidence-based defaults
    weights = EVIDENCE_BASED_WEIGHTS.copy()

    # Allow per-component overrides
    env_mapping = {
        "FUSION_WHALE_WEIGHT": "whale",
        "FUSION_UTXO_WEIGHT": "utxo",
        "FUSION_FUNDING_WEIGHT": "funding",
        "FUSION_OI_WEIGHT": "oi",
        "FUSION_POWER_LAW_WEIGHT": "power_law",
        "FUSION_SYMBOLIC_WEIGHT": "symbolic",
        "FUSION_FRACTAL_WEIGHT": "fractal",
        "FUSION_WASSERSTEIN_WEIGHT": "wasserstein",
    }

    for env_var, component in env_mapping.items():
        if env_val := os.getenv(env_var):
            weights[component] = float(env_val)

    validate_weights(weights)
    return weights


def enhanced_fusion(
    whale_vote: Optional[float] = None,
    whale_conf: Optional[float] = None,
    utxo_vote: Optional[float] = None,
    utxo_conf: Optional[float] = None,
    funding_vote: Optional[float] = None,
    oi_vote: Optional[float] = None,
    power_law_vote: Optional[float] = None,
    symbolic_vote: Optional[float] = None,
    fractal_vote: Optional[float] = None,
    wasserstein_vote: Optional[float] = None,  # spec-010
    sopr_vote: Optional[float] = None,  # spec-016
    n_samples: int = 1000,
    weights: Optional[dict[str, float]] = None,
) -> EnhancedFusionResult:
    """
    Enhanced Monte Carlo fusion with 9 signal components.

    Extends spec-007 with spec-009 advanced metrics (power law, symbolic,
    fractal), spec-008 derivatives (funding, oi), spec-010 Wasserstein,
    and spec-016 SOPR (STH/LTH).

    Components:
    - whale: Whale flow signal
    - utxo: UTXOracle price signal (entity-adjusted)
    - funding: Funding rate signal (spec-008)
    - oi: Open interest signal (spec-008)
    - power_law: Power law regime signal (spec-009)
    - symbolic: Symbolic dynamics signal (spec-009)
    - fractal: Fractal dimension signal (spec-009)
    - wasserstein: Distribution shift signal (spec-010)
    - sopr: Spent Output Profit Ratio signal (spec-016) - Highest evidence grade

    Args:
        whale_vote: Whale flow vote (-1 to +1), None if unavailable
        whale_conf: Whale signal confidence (0 to 1)
        utxo_vote: UTXOracle vote (-1 to +1), None if unavailable
        utxo_conf: UTXOracle confidence (0 to 1)
        funding_vote: Funding rate vote, None if unavailable
        oi_vote: Open interest vote, None if unavailable
        power_law_vote: Power law regime vote, None if unavailable
        symbolic_vote: Symbolic dynamics vote, None if unavailable
        fractal_vote: Fractal dimension vote, None if unavailable
        wasserstein_vote: Wasserstein shift vote, None if unavailable (spec-010)
        sopr_vote: SOPR signal vote, None if unavailable (spec-016)
        n_samples: Number of bootstrap samples (default: 1000)
        weights: Custom weights dict (uses ENHANCED_WEIGHTS if None)

    Returns:
        EnhancedFusionResult with fused signal and all component info
    """
    # Use default weights if not provided
    w = weights if weights else ENHANCED_WEIGHTS.copy()

    # Collect available components and renormalize weights
    components = {}
    components_used = []

    if whale_vote is not None:
        components["whale"] = (whale_vote, whale_conf if whale_conf else 1.0)
        components_used.append("whale")
    if utxo_vote is not None:
        components["utxo"] = (utxo_vote, utxo_conf if utxo_conf else 1.0)
        components_used.append("utxo")
    if funding_vote is not None:
        components["funding"] = (funding_vote, 1.0)  # No confidence for derivatives
        components_used.append("funding")
    if oi_vote is not None:
        components["oi"] = (oi_vote, 1.0)
        components_used.append("oi")
    if power_law_vote is not None:
        components["power_law"] = (power_law_vote, 1.0)
        components_used.append("power_law")
    if symbolic_vote is not None:
        components["symbolic"] = (symbolic_vote, 1.0)
        components_used.append("symbolic")
    if fractal_vote is not None:
        components["fractal"] = (fractal_vote, 1.0)
        components_used.append("fractal")
    if wasserstein_vote is not None:
        components["wasserstein"] = (wasserstein_vote, 1.0)
        components_used.append("wasserstein")
    if sopr_vote is not None:
        components["sopr"] = (sopr_vote, 1.0)  # spec-016
        components_used.append("sopr")

    n_components = len(components)

    if n_components == 0:
        # No components available - return neutral result
        return EnhancedFusionResult(
            signal_mean=0.0,
            signal_std=0.0,
            ci_lower=0.0,
            ci_upper=0.0,
            action="HOLD",
            action_confidence=0.0,
            n_samples=0,
            distribution_type="insufficient_data",
            components_available=0,
            components_used=[],
        )

    # Renormalize weights for available components
    total_weight = sum(w.get(c, 0) for c in components.keys())
    if total_weight > 0:
        normalized_weights = {c: w.get(c, 0) / total_weight for c in components.keys()}
    else:
        # Equal weights if no weights defined
        normalized_weights = {c: 1.0 / n_components for c in components.keys()}

    # Bootstrap sampling
    samples = []
    for _ in range(n_samples):
        sample_sum = 0.0
        for comp_name, (vote, conf) in components.items():
            # Sample vote with confidence as Bernoulli success rate
            sampled_vote = vote if random.random() < conf else 0.0
            sample_sum += normalized_weights[comp_name] * sampled_vote
        samples.append(sample_sum)

    # Calculate statistics
    signal_mean = mean(samples)
    signal_std = stdev(samples) if len(samples) > 1 else 0.0

    # Calculate 95% CI
    sorted_samples = sorted(samples)
    ci_lower = sorted_samples[int(0.025 * n_samples)]
    ci_upper = sorted_samples[int(0.975 * n_samples)]

    # Detect distribution type
    distribution_type = detect_bimodal(samples)

    # Determine action and confidence
    action, action_confidence = determine_action(signal_mean, ci_lower, ci_upper)

    return EnhancedFusionResult(
        signal_mean=signal_mean,
        signal_std=signal_std,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        action=action,
        action_confidence=action_confidence,
        n_samples=n_samples,
        distribution_type=distribution_type,
        whale_vote=whale_vote,
        utxo_vote=utxo_vote,
        funding_vote=funding_vote,
        oi_vote=oi_vote,
        power_law_vote=power_law_vote,
        symbolic_vote=symbolic_vote,
        fractal_vote=fractal_vote,
        wasserstein_vote=wasserstein_vote,  # spec-010
        sopr_vote=sopr_vote,  # spec-016
        whale_weight=normalized_weights.get("whale", 0.0),
        utxo_weight=normalized_weights.get("utxo", 0.0),
        funding_weight=normalized_weights.get("funding", 0.0),
        oi_weight=normalized_weights.get("oi", 0.0),
        power_law_weight=normalized_weights.get("power_law", 0.0),
        symbolic_weight=normalized_weights.get("symbolic", 0.0),
        fractal_weight=normalized_weights.get("fractal", 0.0),
        wasserstein_weight=normalized_weights.get("wasserstein", 0.0),  # spec-010
        sopr_weight=normalized_weights.get("sopr", 0.0),  # spec-016
        components_available=n_components,
        components_used=components_used,
    )
