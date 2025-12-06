"""
Wasserstein Distance Calculator (Earth Mover's Distance) for spec-010.

This module computes the Wasserstein-1 distance between UTXO value distributions
to detect regime shifts. The implementation uses the quantile-based algorithm
which is O(n log n) and exact for 1D distributions.

Key features:
- Single-pair Wasserstein distance calculation
- Rolling window analysis for regime detection
- Integration with Enhanced Monte Carlo Fusion (8th component)

References:
- Horvath et al. (2024): "Clustering Market Regimes Using Wasserstein Distance"
- Peyré & Cuturi (2019): "Computational Optimal Transport", Chapter 2.3

Usage:
    from scripts.metrics.wasserstein import wasserstein_1d, rolling_wasserstein

    # Single distance
    result = wasserstein_1d(values_1, values_2)

    # Rolling analysis
    rolling = rolling_wasserstein(all_values, window_size=144, step_size=6)
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.models.metrics_models import (
        RollingWassersteinResult,
        WassersteinResult,
    )

# =============================================================================
# Configuration Constants
# =============================================================================

# Window configuration
DEFAULT_WINDOW_SIZE = 144  # blocks (~24 hours)
DEFAULT_STEP_SIZE = 6  # blocks (~1 hour)

# Detection thresholds
SHIFT_THRESHOLD = 0.10  # W > 0.10 = significant shift
MIN_SAMPLES = 50  # Minimum samples per window
SUSTAINED_COUNT = 3  # Consecutive windows for sustained shift

# Vote parameters
VOTE_SCALE_MAX = 0.15  # Distance above threshold for max vote
CONCENTRATION_VOTE = 0.6  # Max positive vote
DISPERSION_VOTE = -0.4  # Max negative vote


# =============================================================================
# Helper Functions
# =============================================================================


def _interpolate_quantiles(sorted_values: list[float], n: int) -> list[float]:
    """
    Interpolate sorted values to n quantile positions.

    For 1D Wasserstein, we need both distributions at the same quantile
    positions. This function linearly interpolates the sorted values
    to achieve uniform quantile spacing.

    Args:
        sorted_values: Pre-sorted list of values
        n: Number of quantile positions to generate

    Returns:
        List of n interpolated quantile values
    """
    if not sorted_values:
        return []

    m = len(sorted_values)
    if m == 1:
        return [sorted_values[0]] * n

    quantiles = []
    for i in range(n):
        # Position in original array (as float)
        pos = i * (m - 1) / (n - 1) if n > 1 else 0

        # Linear interpolation
        lower_idx = int(pos)
        upper_idx = min(lower_idx + 1, m - 1)
        frac = pos - lower_idx

        value = sorted_values[lower_idx] * (1 - frac) + sorted_values[upper_idx] * frac
        quantiles.append(value)

    return quantiles


def _compute_statistics(values: list[float]) -> tuple[float, float]:
    """
    Compute mean and standard deviation of values.

    Args:
        values: List of numeric values

    Returns:
        Tuple of (mean, std)
    """
    if not values:
        return 0.0, 0.0

    n = len(values)
    mean = sum(values) / n

    if n < 2:
        return mean, 0.0

    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(variance)

    return mean, std


def _detect_shift_direction(
    window_1_mean: float, window_2_mean: float, threshold: float = SHIFT_THRESHOLD
) -> str:
    """
    Detect direction of distribution shift based on mean change.

    CONCENTRATION: Mean increased (fewer, larger values - whale accumulation)
    DISPERSION: Mean decreased (more, smaller values - retail entry)
    NONE: No significant change

    Args:
        window_1_mean: Mean of first distribution
        window_2_mean: Mean of second distribution
        threshold: Minimum relative change to classify as shift

    Returns:
        "CONCENTRATION" | "DISPERSION" | "NONE"
    """
    if window_1_mean == 0:
        return "NONE"

    relative_change = (window_2_mean - window_1_mean) / window_1_mean

    if relative_change > threshold:
        return "CONCENTRATION"
    elif relative_change < -threshold:
        return "DISPERSION"
    else:
        return "NONE"


def _normalize_distance(
    distance: float, values_1: list[float], values_2: list[float]
) -> float:
    """
    Normalize Wasserstein distance to [0, 1] scale.

    Normalization is done by dividing by the range of the combined distribution.

    Args:
        distance: Raw Wasserstein distance
        values_1: First distribution values
        values_2: Second distribution values

    Returns:
        Normalized distance in [0, 1]
    """
    if not values_1 and not values_2:
        return 0.0

    all_values = values_1 + values_2
    min_val = min(all_values)
    max_val = max(all_values)

    range_val = max_val - min_val
    if range_val == 0:
        return 0.0

    return min(1.0, distance / range_val)


# =============================================================================
# Core Wasserstein Algorithm
# =============================================================================


def wasserstein_1d(
    values_1: list[float],
    values_2: list[float],
    threshold: float = SHIFT_THRESHOLD,
    min_samples: int = MIN_SAMPLES,
) -> "WassersteinResult":
    """
    Compute 1D Wasserstein distance (Earth Mover's Distance) between distributions.

    Uses the quantile-based algorithm: sort both distributions, interpolate
    to common length, and sum absolute differences. Complexity: O(n log n).

    For 1D distributions, W_1(P, Q) = (1/n) * sum(|Q_P(i/n) - Q_Q(i/n)|)
    where Q is the quantile function.

    Args:
        values_1: First distribution (e.g., earlier time window)
        values_2: Second distribution (e.g., later time window)
        threshold: Threshold for significant shift classification
        min_samples: Minimum samples required for valid result

    Returns:
        WassersteinResult with distance, direction, and validity

    Example:
        >>> result = wasserstein_1d([1, 2, 3], [2, 3, 4])
        >>> result.distance
        1.0
        >>> result.shift_direction
        'CONCENTRATION'
    """
    # Import here to avoid circular dependency
    from scripts.models.metrics_models import WassersteinResult

    # Check validity
    n1, n2 = len(values_1), len(values_2)
    is_valid = n1 >= min_samples and n2 >= min_samples

    # Compute statistics
    mean_1, std_1 = _compute_statistics(values_1)
    mean_2, std_2 = _compute_statistics(values_2)

    # Handle empty or invalid inputs
    if not values_1 or not values_2:
        return WassersteinResult(
            distance=0.0,
            distance_normalized=0.0,
            window_1_size=n1,
            window_2_size=n2,
            window_1_mean=mean_1,
            window_2_mean=mean_2,
            window_1_std=std_1,
            window_2_std=std_2,
            shift_direction="NONE",
            is_significant=False,
            is_valid=False,
            min_samples=min_samples,
        )

    # Sort both distributions
    sorted_1 = sorted(values_1)
    sorted_2 = sorted(values_2)

    # Interpolate to common length (max of both)
    n = max(n1, n2)
    q1 = _interpolate_quantiles(sorted_1, n)
    q2 = _interpolate_quantiles(sorted_2, n)

    # Compute Wasserstein distance as mean absolute difference
    distance = sum(abs(a - b) for a, b in zip(q1, q2)) / n

    # Normalize distance
    distance_normalized = _normalize_distance(distance, values_1, values_2)

    # Detect shift direction
    shift_direction = _detect_shift_direction(mean_1, mean_2, threshold)

    # Check if significant
    is_significant = distance_normalized > threshold

    return WassersteinResult(
        distance=distance,
        distance_normalized=distance_normalized,
        window_1_size=n1,
        window_2_size=n2,
        window_1_mean=mean_1,
        window_2_mean=mean_2,
        window_1_std=std_1,
        window_2_std=std_2,
        shift_direction=shift_direction,
        is_significant=is_significant,
        is_valid=is_valid,
        min_samples=min_samples,
    )


# =============================================================================
# Rolling Window Analysis
# =============================================================================


def _create_windows(
    values: list[float], window_size: int, step_size: int
) -> list[list[float]]:
    """
    Create sliding windows from value series.

    Args:
        values: Full series of values
        window_size: Number of values per window
        step_size: Step between window starts

    Returns:
        List of windows (each window is a list of values)
    """
    windows = []
    n = len(values)

    for start in range(0, n - window_size + 1, step_size):
        window = values[start : start + window_size]
        windows.append(window)

    return windows


def _detect_sustained_shift(
    is_significant_list: list[bool], sustained_count: int = SUSTAINED_COUNT
) -> tuple[bool, list[int]]:
    """
    Detect if shift is sustained (consecutive high-W windows).

    Args:
        is_significant_list: List of boolean significance flags
        sustained_count: Number of consecutive windows required

    Returns:
        Tuple of (sustained_detected, list of shift window indices)
    """
    shift_windows = [i for i, sig in enumerate(is_significant_list) if sig]

    if len(shift_windows) < sustained_count:
        return False, shift_windows

    # Check for consecutive windows
    for i in range(len(shift_windows) - sustained_count + 1):
        consecutive = True
        for j in range(1, sustained_count):
            if shift_windows[i + j] - shift_windows[i + j - 1] != 1:
                consecutive = False
                break
        if consecutive:
            return True, shift_windows

    return False, shift_windows


def _classify_regime_status(
    sustained_shift: bool, shift_count: int, total_windows: int
) -> str:
    """
    Classify overall regime status.

    STABLE: No significant shifts
    TRANSITIONING: Some shifts but not sustained
    SHIFTED: Sustained shift detected

    Args:
        sustained_shift: Whether sustained shift was detected
        shift_count: Number of significant shift windows
        total_windows: Total number of windows analyzed

    Returns:
        "STABLE" | "TRANSITIONING" | "SHIFTED"
    """
    if sustained_shift:
        return "SHIFTED"

    if shift_count == 0:
        return "STABLE"

    # Transitioning if 1-2 shifts but not sustained
    return "TRANSITIONING"


def wasserstein_vote(
    distance: float, shift_direction: str, threshold: float = SHIFT_THRESHOLD
) -> float:
    """
    Convert Wasserstein distance to directional vote for fusion.

    Vote interpretation:
    - CONCENTRATION shift: positive vote (whale accumulation, bullish)
    - DISPERSION shift: negative vote (retail entry, bearish)
    - No significant shift: neutral vote

    Args:
        distance: Normalized Wasserstein distance
        shift_direction: "CONCENTRATION" | "DISPERSION" | "NONE"
        threshold: Shift detection threshold

    Returns:
        Vote in range [-1, 1]
    """
    if distance < threshold:
        return 0.0

    # Scale vote by distance magnitude (cap at 1.0)
    magnitude = min(1.0, (distance - threshold) / VOTE_SCALE_MAX)

    if shift_direction == "CONCENTRATION":
        return CONCENTRATION_VOTE * magnitude
    elif shift_direction == "DISPERSION":
        return DISPERSION_VOTE * magnitude
    else:
        return 0.0


def rolling_wasserstein(
    values: list[float],
    timestamps: list[datetime] | None = None,
    window_size: int = DEFAULT_WINDOW_SIZE,
    step_size: int = DEFAULT_STEP_SIZE,
    threshold: float = SHIFT_THRESHOLD,
    min_samples: int = MIN_SAMPLES,
) -> "RollingWassersteinResult":
    """
    Compute rolling Wasserstein distances over time series.

    Compares consecutive windows to detect regime transitions.
    Each window pair produces one Wasserstein distance.

    Args:
        values: Full series of UTXO values
        timestamps: Optional timestamps for each window (generated if not provided)
        window_size: Number of values per window (default: 144 = ~24h)
        step_size: Step between window starts (default: 6 = ~1h)
        threshold: Threshold for significant shift
        min_samples: Minimum samples per window

    Returns:
        RollingWassersteinResult with distances, regime status, and vote

    Example:
        >>> rolling = rolling_wasserstein(utxo_values, window_size=144, step_size=6)
        >>> rolling.regime_status
        'STABLE'
        >>> rolling.wasserstein_vote
        0.0
    """
    from scripts.models.metrics_models import RollingWassersteinResult

    # R2-3 fix: Validate parameters to prevent infinite loop or invalid behavior
    if step_size <= 0:
        raise ValueError(f"step_size must be positive, got {step_size}")
    if window_size <= 0:
        raise ValueError(f"window_size must be positive, got {window_size}")
    if min_samples <= 0:
        raise ValueError(f"min_samples must be positive, got {min_samples}")

    # Create windows
    windows = _create_windows(values, window_size, step_size)
    n_windows = len(windows)

    # Check validity
    if n_windows < 2:
        return RollingWassersteinResult(
            distances=[],
            timestamps=[],
            mean_distance=0.0,
            mean_normalized_distance=0.0,  # B3 fix
            max_distance=0.0,
            min_distance=0.0,
            std_distance=0.0,
            dominant_shift_direction="NONE",  # B4 fix
            sustained_shift_detected=False,
            shift_windows=[],
            regime_status="STABLE",
            wasserstein_vote=0.0,
            vote_confidence=0.0,
            window_size=window_size,
            step_size=step_size,
            threshold=threshold,
            total_samples=len(values),
            windows_analyzed=0,
            is_valid=False,
        )

    # Compute distances between consecutive windows
    distances = []
    is_significant_list = []
    directions = []

    for i in range(n_windows - 1):
        result = wasserstein_1d(windows[i], windows[i + 1], threshold, min_samples)
        distances.append(result.distance_normalized)
        is_significant_list.append(result.is_significant)
        directions.append(result.shift_direction)

    # Generate timestamps if not provided
    if timestamps is None:
        timestamps = [datetime.utcnow() for _ in distances]
    elif len(timestamps) > len(distances):
        timestamps = timestamps[: len(distances)]
    elif len(timestamps) < len(distances):
        timestamps = timestamps + [datetime.utcnow()] * (
            len(distances) - len(timestamps)
        )

    # Compute statistics
    mean_dist = sum(distances) / len(distances) if distances else 0.0
    max_dist = max(distances) if distances else 0.0
    min_dist = min(distances) if distances else 0.0

    if len(distances) > 1:
        variance = sum((d - mean_dist) ** 2 for d in distances) / (len(distances) - 1)
        std_dist = math.sqrt(variance)
    else:
        std_dist = 0.0

    # Detect sustained shift
    sustained, shift_windows = _detect_sustained_shift(is_significant_list)

    # Classify regime
    regime_status = _classify_regime_status(
        sustained, len(shift_windows), len(distances)
    )

    # Compute vote based on most recent significant window
    vote = 0.0
    vote_confidence = 0.0

    if shift_windows:
        last_shift_idx = shift_windows[-1]
        vote = wasserstein_vote(
            distances[last_shift_idx], directions[last_shift_idx], threshold
        )

        # Confidence based on direction consistency
        recent_directions = directions[-3:] if len(directions) >= 3 else directions
        direction_counts = {}
        for d in recent_directions:
            direction_counts[d] = direction_counts.get(d, 0) + 1

        if recent_directions:
            most_common_count = max(direction_counts.values())
            vote_confidence = most_common_count / len(recent_directions)

    # B4 fix: Compute dominant shift direction from all directions
    dominant_direction = "NONE"
    if directions:
        all_direction_counts = {}
        for d in directions:
            all_direction_counts[d] = all_direction_counts.get(d, 0) + 1
        # Find most common direction (excluding NONE if others exist)
        non_none_counts = {k: v for k, v in all_direction_counts.items() if k != "NONE"}
        if non_none_counts:
            dominant_direction = max(non_none_counts, key=non_none_counts.get)
        elif all_direction_counts:
            dominant_direction = max(all_direction_counts, key=all_direction_counts.get)

    return RollingWassersteinResult(
        distances=distances,
        timestamps=timestamps,
        mean_distance=mean_dist,
        mean_normalized_distance=mean_dist,  # B3 fix: distances are already normalized
        max_distance=max_dist,
        min_distance=min_dist,
        std_distance=std_dist,
        dominant_shift_direction=dominant_direction,  # B4 fix
        sustained_shift_detected=sustained,
        shift_windows=shift_windows,
        regime_status=regime_status,
        wasserstein_vote=vote,
        vote_confidence=vote_confidence,
        window_size=window_size,
        step_size=step_size,
        threshold=threshold,
        total_samples=len(values),
        windows_analyzed=len(distances),
        is_valid=len(distances) > 0,
    )


# =============================================================================
# Public API
# =============================================================================

__all__ = [
    "wasserstein_1d",
    "rolling_wasserstein",
    "wasserstein_vote",
    "DEFAULT_WINDOW_SIZE",
    "DEFAULT_STEP_SIZE",
    "SHIFT_THRESHOLD",
    "MIN_SAMPLES",
    "SUSTAINED_COUNT",
]
