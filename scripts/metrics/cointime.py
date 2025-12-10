"""
Cointime Economics Framework (spec-018).

Implements ARK Invest + Glassnode's Cointime Economics framework for
Bitcoin on-chain analysis. This framework removes heuristic assumptions
by using objective mathematical ratios.

Key concepts:
- Coinblocks: BTC x blocks_held (created) or blocks_since_creation (destroyed)
- Liveliness: cumulative_destroyed / cumulative_created (network activity)
- Vaultedness: 1 - Liveliness (network inactivity)
- Active Supply: total_supply x liveliness
- Vaulted Supply: total_supply x vaultedness
- True Market Mean: market_cap / active_supply
- AVIV Ratio: price / true_market_mean (superior MVRV)

Alpha-Evolve Selection:
- Approach A: Pure Functional with Inline Validation (Winner: 37/40)
- Approach B: Validator Functions (34/40) - more DRY but added complexity
- Approach C: Dataclass-based (19/40) - API mismatch with tests

Reference:
    ARK Invest + Glassnode (2023). "Cointime Economics"
    https://www.ark-invest.com/white-papers/cointime-economics

Usage:
    from scripts.metrics.cointime import (
        calculate_liveliness,
        calculate_aviv,
        generate_cointime_signal,
    )

    liveliness = calculate_liveliness(destroyed=3e9, created=10e9)  # 0.3
    aviv = calculate_aviv(price=100000, tmm=50000)  # 2.0
"""

from typing import Optional, Literal


# =============================================================================
# Constants
# =============================================================================

BLOCKS_PER_DAY = 144  # Average blocks per day (10 min per block)
AVIV_UNDERVALUED_THRESHOLD = 1.0  # Below = undervalued
AVIV_OVERVALUED_THRESHOLD = 2.5  # Above = overvalued
EXTREME_LIVELINESS_LOW = 0.15  # Extreme dormancy threshold
EXTREME_LIVELINESS_HIGH = 0.45  # Extreme activity threshold


# =============================================================================
# Coinblocks Calculation (T013 [E], T014 [E], T015)
# =============================================================================


def calculate_coinblocks_destroyed(
    spent_btc: float, blocks_since_creation: int
) -> float:
    """
    Calculate coinblocks destroyed when a UTXO is spent.

    Coinblocks destroyed = BTC x blocks_since_creation

    This measures the "economic weight" of the spent coins - older coins
    that have been dormant longer contribute more coinblocks when spent.

    Args:
        spent_btc: Amount of BTC spent (must be >= 0)
        blocks_since_creation: Number of blocks since UTXO was created (must be >= 0)

    Returns:
        Coinblocks destroyed (BTC x blocks)

    Raises:
        ValueError: If spent_btc or blocks_since_creation is negative

    Example:
        >>> calculate_coinblocks_destroyed(1.0, 100)
        100.0
        >>> calculate_coinblocks_destroyed(0.5, 1000)
        500.0
    """
    if spent_btc < 0:
        raise ValueError(f"spent_btc must be >= 0, got {spent_btc}")
    if blocks_since_creation < 0:
        raise ValueError(
            f"blocks_since_creation must be >= 0, got {blocks_since_creation}"
        )

    return spent_btc * blocks_since_creation


def calculate_coinblocks_created(btc_amount: float, blocks_held: int = 1) -> float:
    """
    Calculate coinblocks created by holding BTC.

    Coinblocks created = BTC x blocks_held

    Every block that passes while holding BTC creates coinblocks.
    Default is 1 block (per-block accounting).

    Args:
        btc_amount: Amount of BTC held (must be >= 0)
        blocks_held: Number of blocks held (default: 1)

    Returns:
        Coinblocks created (BTC x blocks)

    Raises:
        ValueError: If btc_amount is negative

    Example:
        >>> calculate_coinblocks_created(1.0)
        1.0
        >>> calculate_coinblocks_created(2.0, blocks_held=50)
        100.0
    """
    if btc_amount < 0:
        raise ValueError(f"btc_amount must be >= 0, got {btc_amount}")

    return btc_amount * blocks_held


def update_cumulative_coinblocks(
    previous_created: float,
    previous_destroyed: float,
    block_created: float,
    block_destroyed: float,
) -> tuple[float, float]:
    """
    Update cumulative coinblocks totals with new block data.

    Args:
        previous_created: Cumulative coinblocks created before this block
        previous_destroyed: Cumulative coinblocks destroyed before this block
        block_created: Coinblocks created in this block
        block_destroyed: Coinblocks destroyed in this block

    Returns:
        Tuple of (new_cumulative_created, new_cumulative_destroyed)

    Example:
        >>> update_cumulative_coinblocks(1000.0, 300.0, 100.0, 50.0)
        (1100.0, 350.0)
    """
    new_created = previous_created + block_created
    new_destroyed = previous_destroyed + block_destroyed
    return new_created, new_destroyed


# =============================================================================
# Liveliness and Vaultedness (T020 [E], T021 [E], T022, T023d)
# =============================================================================


def calculate_liveliness(
    cumulative_destroyed: float, cumulative_created: float
) -> float:
    """
    Calculate network liveliness ratio.

    Liveliness = cumulative_destroyed / cumulative_created

    Measures what fraction of all coinblocks ever created have been
    destroyed (spent). Higher liveliness = more active network.

    The result is clamped to [0, 1]:
    - 0.0 = fully dormant (no coins ever spent)
    - 1.0 = maximum activity (all coinblocks destroyed)

    Args:
        cumulative_destroyed: Total coinblocks destroyed all-time
        cumulative_created: Total coinblocks created all-time (must be > 0)

    Returns:
        Liveliness ratio in range [0, 1]

    Raises:
        ValueError: If cumulative_created <= 0

    Example:
        >>> calculate_liveliness(3_000_000_000.0, 10_000_000_000.0)
        0.3
    """
    if cumulative_created <= 0:
        raise ValueError(f"cumulative_created must be > 0, got {cumulative_created}")

    raw_liveliness = cumulative_destroyed / cumulative_created

    # Clamp to [0, 1] - edge case where destroyed > created shouldn't happen
    # in practice but we handle it defensively
    return max(0.0, min(1.0, raw_liveliness))


def calculate_vaultedness(liveliness: float) -> float:
    """
    Calculate network vaultedness ratio.

    Vaultedness = 1 - Liveliness

    Measures what fraction of all coinblocks ever created are still
    "vaulted" (not spent). Higher vaultedness = more dormant network.

    Args:
        liveliness: Liveliness ratio in range [0, 1]

    Returns:
        Vaultedness ratio in range [0, 1]

    Raises:
        ValueError: If liveliness not in [0, 1]

    Example:
        >>> calculate_vaultedness(0.3)
        0.7
    """
    if not 0.0 <= liveliness <= 1.0:
        raise ValueError(f"liveliness must be in [0, 1], got {liveliness}")

    return 1.0 - liveliness


def calculate_rolling_liveliness(
    destroyed_series: list[float],
    created_series: list[float],
    window_days: int,
) -> Optional[float]:
    """
    Calculate rolling liveliness over a time window.

    Computes liveliness using only the coinblocks created and destroyed
    within the specified window (7d, 30d, or 90d).

    Args:
        destroyed_series: Per-block destroyed coinblocks (most recent last)
        created_series: Per-block created coinblocks (most recent last)
        window_days: Window size in days (7, 30, or 90)

    Returns:
        Rolling liveliness ratio, or None if insufficient data

    Example:
        >>> destroyed = [10.0] * 1008  # 7 days
        >>> created = [100.0] * 1008
        >>> calculate_rolling_liveliness(destroyed, created, window_days=7)
        0.1
    """
    window_blocks = window_days * BLOCKS_PER_DAY

    if len(destroyed_series) < window_blocks or len(created_series) < window_blocks:
        return None

    # Sum over window (take last window_blocks entries)
    window_destroyed = sum(destroyed_series[-window_blocks:])
    window_created = sum(created_series[-window_blocks:])

    if window_created <= 0:
        return None

    raw_liveliness = window_destroyed / window_created
    return max(0.0, min(1.0, raw_liveliness))


# =============================================================================
# Supply Split (T027 [E], T028 [E])
# =============================================================================


def calculate_active_supply(total_supply_btc: float, liveliness: float) -> float:
    """
    Calculate active supply (BTC actively circulating).

    Active Supply = Total Supply x Liveliness

    Represents the portion of Bitcoin supply that is actively
    participating in the economy (being moved).

    Args:
        total_supply_btc: Total BTC supply (e.g., 19.5M)
        liveliness: Liveliness ratio in range [0, 1]

    Returns:
        Active supply in BTC

    Example:
        >>> calculate_active_supply(19_500_000.0, 0.3)
        5850000.0
    """
    return total_supply_btc * liveliness


def calculate_vaulted_supply(total_supply_btc: float, vaultedness: float) -> float:
    """
    Calculate vaulted supply (BTC held dormant).

    Vaulted Supply = Total Supply x Vaultedness

    Represents the portion of Bitcoin supply that is dormant
    (not being moved, likely in cold storage).

    Args:
        total_supply_btc: Total BTC supply (e.g., 19.5M)
        vaultedness: Vaultedness ratio in range [0, 1]

    Returns:
        Vaulted supply in BTC

    Example:
        >>> calculate_vaulted_supply(19_500_000.0, 0.7)
        13650000.0
    """
    return total_supply_btc * vaultedness


# =============================================================================
# Valuation Metrics (T033, T034, T035)
# =============================================================================


def calculate_true_market_mean(
    market_cap_usd: float, active_supply_btc: float
) -> float:
    """
    Calculate True Market Mean (activity-adjusted realized price).

    True Market Mean = Market Cap / Active Supply

    Unlike realized price which divides by total supply, TMM divides
    only by the actively circulating supply, giving a more accurate
    picture of the "true" cost basis of active coins.

    Args:
        market_cap_usd: Total market capitalization in USD
        active_supply_btc: Active supply in BTC (must be > 0)

    Returns:
        True Market Mean price in USD

    Raises:
        ValueError: If active_supply_btc <= 0

    Example:
        >>> calculate_true_market_mean(1_000_000_000_000.0, 5_000_000.0)
        200000.0
    """
    if active_supply_btc <= 0:
        raise ValueError(f"active_supply_btc must be > 0, got {active_supply_btc}")

    return market_cap_usd / active_supply_btc


def calculate_aviv(current_price_usd: float, true_market_mean_usd: float) -> float:
    """
    Calculate AVIV ratio (Activity-adjusted Value-to-Invested Value).

    AVIV = Current Price / True Market Mean

    AVIV is a superior alternative to MVRV because it accounts for
    the fact that much of the supply is dormant ("vaulted").

    Interpretation:
    - AVIV < 1.0: Undervalued (price below active cost basis)
    - AVIV 1.0-2.5: Fair value range
    - AVIV > 2.5: Overvalued (price well above active cost basis)

    Args:
        current_price_usd: Current BTC price in USD
        true_market_mean_usd: True Market Mean in USD (must be > 0)

    Returns:
        AVIV ratio

    Raises:
        ValueError: If true_market_mean_usd <= 0

    Example:
        >>> calculate_aviv(100_000.0, 50_000.0)
        2.0
    """
    if true_market_mean_usd <= 0:
        raise ValueError(
            f"true_market_mean_usd must be > 0, got {true_market_mean_usd}"
        )

    return current_price_usd / true_market_mean_usd


def classify_valuation_zone(
    aviv_ratio: float,
    undervalued_threshold: float = AVIV_UNDERVALUED_THRESHOLD,
    overvalued_threshold: float = AVIV_OVERVALUED_THRESHOLD,
) -> Literal["UNDERVALUED", "FAIR", "OVERVALUED"]:
    """
    Classify valuation zone based on AVIV ratio.

    Args:
        aviv_ratio: AVIV ratio value
        undervalued_threshold: Below this = UNDERVALUED (default: 1.0)
        overvalued_threshold: Above this = OVERVALUED (default: 2.5)

    Returns:
        Valuation zone: "UNDERVALUED", "FAIR", or "OVERVALUED"

    Example:
        >>> classify_valuation_zone(0.8)
        'UNDERVALUED'
        >>> classify_valuation_zone(1.5)
        'FAIR'
        >>> classify_valuation_zone(3.0)
        'OVERVALUED'
    """
    if aviv_ratio < undervalued_threshold:
        return "UNDERVALUED"
    elif aviv_ratio > overvalued_threshold:
        return "OVERVALUED"
    else:
        return "FAIR"


# =============================================================================
# Signal Generation (T039)
# =============================================================================


def calculate_confidence(
    cointime_vote: float, aviv_ratio: float, extreme_dormancy: bool
) -> float:
    """
    Calculate confidence level for cointime signal.

    Confidence = base + signal_strength + zone_bonus + dormancy_bonus

    Components:
    - base: 0.5 (minimum confidence)
    - signal_strength: |cointime_vote| x 0.3 (stronger vote = more confident)
    - zone_bonus: 0.1 if AVIV in extreme zone (<0.8 or >2.5)
    - dormancy_bonus: 0.1 if extreme_dormancy detected

    Args:
        cointime_vote: Vote value in [-1, 1]
        aviv_ratio: AVIV ratio value
        extreme_dormancy: Whether extreme dormancy is detected

    Returns:
        Confidence level in range [0.5, 1.0]

    Example:
        >>> calculate_confidence(0.8, 0.5, True)  # High vote + extreme zone + dormancy
        1.0
    """
    base = 0.5
    signal_strength = abs(cointime_vote) * 0.3
    zone_bonus = 0.1 if (aviv_ratio < 0.8 or aviv_ratio > 2.5) else 0.0
    dormancy_bonus = 0.1 if extreme_dormancy else 0.0

    return min(1.0, base + signal_strength + zone_bonus + dormancy_bonus)


def generate_cointime_signal(
    liveliness: float,
    liveliness_7d_change: float,
    liveliness_30d_change: float,
    aviv_ratio: float,
    active_supply_btc: float,
    previous_active_supply_btc: Optional[float] = None,
) -> dict:
    """
    Generate comprehensive cointime trading signal.

    Combines liveliness trends, AVIV valuation, and supply dynamics
    to generate a signal vote and detect patterns.

    Signal Logic:
    - Bullish: Low liveliness (dormancy) + undervalued AVIV + declining liveliness
    - Bearish: High liveliness (activity) + overvalued AVIV + rising liveliness
    - Neutral: Fair value + stable liveliness

    Pattern Detection:
    - extreme_dormancy: liveliness < 0.15 (accumulation phase)
    - distribution_warning: liveliness rising + overvalued
    - supply_squeeze: active supply declining significantly

    Args:
        liveliness: Current liveliness ratio
        liveliness_7d_change: 7-day change in liveliness
        liveliness_30d_change: 30-day change in liveliness
        aviv_ratio: Current AVIV ratio
        active_supply_btc: Current active supply in BTC
        previous_active_supply_btc: Previous active supply (for squeeze detection)

    Returns:
        Dictionary with signal data:
        - cointime_vote: float in [-1, 1]
        - confidence: float in [0.5, 1.0]
        - valuation_zone: "UNDERVALUED" | "FAIR" | "OVERVALUED"
        - extreme_dormancy: bool
        - distribution_warning: bool
        - supply_squeeze: bool

    Example:
        >>> signal = generate_cointime_signal(
        ...     liveliness=0.1,
        ...     liveliness_7d_change=-0.02,
        ...     liveliness_30d_change=-0.05,
        ...     aviv_ratio=0.7,
        ...     active_supply_btc=5_000_000.0,
        ... )
        >>> signal["cointime_vote"] > 0.5
        True
        >>> signal["extreme_dormancy"]
        True
    """
    # Classify valuation zone
    valuation_zone = classify_valuation_zone(aviv_ratio)

    # Detect patterns
    extreme_dormancy = liveliness < EXTREME_LIVELINESS_LOW
    extreme_activity = liveliness > EXTREME_LIVELINESS_HIGH
    liveliness_rising = liveliness_7d_change > 0.01 or liveliness_30d_change > 0.03
    liveliness_falling = liveliness_7d_change < -0.01 or liveliness_30d_change < -0.03

    # Distribution warning: activity increasing while overvalued
    distribution_warning = (valuation_zone == "OVERVALUED" and liveliness_rising) or (
        extreme_activity and valuation_zone == "OVERVALUED"
    )

    # Supply squeeze: active supply declining significantly
    supply_squeeze = False
    if previous_active_supply_btc is not None and previous_active_supply_btc > 0:
        supply_change_pct = (
            active_supply_btc - previous_active_supply_btc
        ) / previous_active_supply_btc
        supply_squeeze = supply_change_pct < -0.05  # >5% decline

    # Calculate cointime vote
    vote = 0.0

    # AVIV component: undervalued = bullish, overvalued = bearish
    if valuation_zone == "UNDERVALUED":
        # More undervalued = stronger bullish signal
        aviv_contribution = min(0.5, (AVIV_UNDERVALUED_THRESHOLD - aviv_ratio) * 0.5)
        vote += aviv_contribution
    elif valuation_zone == "OVERVALUED":
        # More overvalued = stronger bearish signal
        aviv_contribution = min(0.5, (aviv_ratio - AVIV_OVERVALUED_THRESHOLD) * 0.2)
        vote -= aviv_contribution

    # Liveliness component: falling = bullish (accumulation), rising = bearish
    if liveliness_falling:
        vote += 0.2
    elif liveliness_rising:
        vote -= 0.2

    # Extreme dormancy bonus (strong accumulation signal)
    if extreme_dormancy:
        vote += 0.3

    # Distribution warning penalty
    if distribution_warning:
        vote -= 0.3

    # Supply squeeze bonus
    if supply_squeeze:
        vote += 0.2

    # Clamp vote to [-1, 1]
    vote = max(-1.0, min(1.0, vote))

    # Calculate confidence
    confidence = calculate_confidence(vote, aviv_ratio, extreme_dormancy)

    return {
        "cointime_vote": vote,
        "confidence": confidence,
        "valuation_zone": valuation_zone,
        "extreme_dormancy": extreme_dormancy,
        "distribution_warning": distribution_warning,
        "supply_squeeze": supply_squeeze,
        "liveliness": liveliness,
        "aviv_ratio": aviv_ratio,
        "active_supply_btc": active_supply_btc,
    }
