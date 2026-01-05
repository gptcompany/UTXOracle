"""
Data models for on-chain metrics (spec-007 + spec-009).

These dataclasses mirror the DuckDB `metrics` table schema and provide
type-safe data transfer between calculation modules and storage/API.

Spec-009 additions:
- PowerLawResult: Power law regime detection
- SymbolicDynamicsResult: Permutation entropy analysis
- FractalDimensionResult: Box-counting dimension
- EnhancedFusionResult: 7-component Monte Carlo fusion
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional, Literal


@dataclass
class MonteCarloFusionResult:
    """
    Result of Monte Carlo bootstrap signal fusion.

    Upgrades linear fusion (0.7*whale + 0.3*utxo) to probabilistic
    estimation with confidence intervals.

    Attributes:
        signal_mean: Mean of bootstrap samples (-1.0 to 1.0)
        signal_std: Standard deviation of samples
        ci_lower: 95% confidence interval lower bound
        ci_upper: 95% confidence interval upper bound
        action: Trading action derived from signal (BUY/SELL/HOLD)
        action_confidence: Probability that action is correct (0.0 to 1.0)
        n_samples: Number of bootstrap iterations performed
        distribution_type: Shape of distribution (unimodal/bimodal)
    """

    signal_mean: float
    signal_std: float
    ci_lower: float
    ci_upper: float
    action: Literal["BUY", "SELL", "HOLD"]
    action_confidence: float
    n_samples: int = 1000
    distribution_type: Literal["unimodal", "bimodal", "insufficient_data"] = "unimodal"

    def __post_init__(self):
        """Validate signal bounds."""
        if not -1.0 <= self.signal_mean <= 1.0:
            raise ValueError(f"signal_mean out of range: {self.signal_mean}")
        if not 0.0 <= self.action_confidence <= 1.0:
            raise ValueError(
                f"action_confidence out of range: {self.action_confidence}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "signal_mean": self.signal_mean,
            "signal_std": self.signal_std,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "action": self.action,
            "action_confidence": self.action_confidence,
            "n_samples": self.n_samples,
            "distribution_type": self.distribution_type,
        }


@dataclass
class ActiveAddressesMetric:
    """
    Active address count for a block or time period.

    Counts unique addresses participating in transactions as either
    senders (inputs) or receivers (outputs).

    Attributes:
        timestamp: When metric was calculated
        block_height: Bitcoin block height (if single block)
        active_addresses_block: Unique addresses in single block
        active_addresses_24h: Unique addresses in last 24 hours (deduplicated)
        unique_senders: Unique addresses in transaction inputs
        unique_receivers: Unique addresses in transaction outputs
        is_anomaly: True if count > 3 sigma from 30-day moving average
    """

    timestamp: datetime
    block_height: int
    active_addresses_block: int
    active_addresses_24h: Optional[int] = None  # Requires multi-block aggregation
    unique_senders: int = 0
    unique_receivers: int = 0
    is_anomaly: bool = False

    def __post_init__(self):
        """Validate non-negative counts."""
        if self.active_addresses_block < 0:
            raise ValueError(
                f"active_addresses_block must be >= 0: {self.active_addresses_block}"
            )
        if self.unique_senders < 0:
            raise ValueError(f"unique_senders must be >= 0: {self.unique_senders}")
        if self.unique_receivers < 0:
            raise ValueError(f"unique_receivers must be >= 0: {self.unique_receivers}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "block_height": self.block_height,
            "active_addresses_block": self.active_addresses_block,
            "active_addresses_24h": self.active_addresses_24h,
            "unique_senders": self.unique_senders,
            "unique_receivers": self.unique_receivers,
            "is_anomaly": self.is_anomaly,
        }


@dataclass
class TxVolumeMetric:
    """
    Transaction volume metric using UTXOracle price.

    Calculates total BTC transferred and converts to USD using
    on-chain price (not exchange price) for privacy preservation.

    Attributes:
        timestamp: When metric was calculated
        tx_count: Number of transactions in period
        tx_volume_btc: Total BTC transferred (adjusted for change)
        tx_volume_usd: USD equivalent (None if price unavailable)
        utxoracle_price_used: Price used for BTC->USD conversion
        low_confidence: True if UTXOracle confidence < 0.3
    """

    timestamp: datetime
    tx_count: int
    tx_volume_btc: float
    tx_volume_usd: Optional[float] = None
    utxoracle_price_used: Optional[float] = None
    low_confidence: bool = False

    def __post_init__(self):
        """Validate non-negative values."""
        if self.tx_count < 0:
            raise ValueError(f"tx_count must be >= 0: {self.tx_count}")
        if self.tx_volume_btc < 0:
            raise ValueError(f"tx_volume_btc must be >= 0: {self.tx_volume_btc}")
        if self.tx_volume_usd is not None and self.tx_volume_usd < 0:
            raise ValueError(f"tx_volume_usd must be >= 0: {self.tx_volume_usd}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "tx_count": self.tx_count,
            "tx_volume_btc": self.tx_volume_btc,
            "tx_volume_usd": self.tx_volume_usd,
            "utxoracle_price_used": self.utxoracle_price_used,
            "low_confidence": self.low_confidence,
        }


@dataclass
class OnChainMetricsBundle:
    """
    Combined metrics for a single timestamp.

    Used for API response and DuckDB storage. All three metrics
    are calculated together during daily_analysis.py run.

    Attributes:
        timestamp: Common timestamp for all metrics
        monte_carlo: Signal fusion result (may be None if whale data unavailable)
        active_addresses: Address activity metric
        tx_volume: Transaction volume metric
    """

    timestamp: datetime
    monte_carlo: Optional[MonteCarloFusionResult] = None
    active_addresses: Optional[ActiveAddressesMetric] = None
    tx_volume: Optional[TxVolumeMetric] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {"timestamp": self.timestamp.isoformat()}

        if self.monte_carlo:
            result["monte_carlo"] = self.monte_carlo.to_dict()

        if self.active_addresses:
            result["active_addresses"] = self.active_addresses.to_dict()

        if self.tx_volume:
            result["tx_volume"] = self.tx_volume.to_dict()

        return result


# =============================================================================
# Spec-009: Advanced On-Chain Analytics Dataclasses
# =============================================================================


@dataclass
class PowerLawResult:
    """
    Result of power law fit to UTXO value distribution.

    Power law: P(x) ~ x^(-tau)

    Regime classification based on tau:
    - ACCUMULATION: tau < 1.8 (heavy tail, whale concentration)
    - NEUTRAL: 1.8 <= tau <= 2.2 (typical market)
    - DISTRIBUTION: tau > 2.2 (light tail, dispersion)
    """

    tau: float
    tau_std: float
    xmin: float
    ks_statistic: float
    ks_pvalue: float
    is_valid: bool
    regime: str  # "ACCUMULATION" | "NEUTRAL" | "DISTRIBUTION"
    power_law_vote: float
    sample_size: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "tau": self.tau,
            "tau_std": self.tau_std,
            "xmin": self.xmin,
            "ks_statistic": self.ks_statistic,
            "ks_pvalue": self.ks_pvalue,
            "is_valid": self.is_valid,
            "regime": self.regime,
            "power_law_vote": self.power_law_vote,
            "sample_size": self.sample_size,
        }


@dataclass
class SymbolicDynamicsResult:
    """
    Result of symbolic dynamics analysis on UTXO flow time series.

    Permutation entropy H measures temporal complexity:
    - H ~ 0: Perfectly predictable (monotonic trend)
    - H ~ 1: Maximum entropy (random noise)

    Pattern classification based on H and series_trend:
    - ACCUMULATION_TREND: H < 0.4, positive trend
    - DISTRIBUTION_TREND: H < 0.4, negative trend
    - CHAOTIC_TRANSITION: H > 0.7
    - EDGE_OF_CHAOS: 0.4 <= H <= 0.7, C > 0.2
    """

    permutation_entropy: float
    statistical_complexity: float
    order: int
    pattern_counts: dict
    dominant_pattern: str
    complexity_class: str  # "LOW" | "MEDIUM" | "HIGH"
    pattern_type: str  # "ACCUMULATION_TREND" | "DISTRIBUTION_TREND" | "CHAOTIC_TRANSITION" | "EDGE_OF_CHAOS"
    symbolic_vote: float
    series_length: int
    series_trend: float = 0.0  # Positive = accumulation, negative = distribution
    is_valid: bool = True
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "permutation_entropy": self.permutation_entropy,
            "statistical_complexity": self.statistical_complexity,
            "order": self.order,
            "complexity_class": self.complexity_class,
            "pattern_type": self.pattern_type,
            "symbolic_vote": self.symbolic_vote,
            "series_length": self.series_length,
            "series_trend": self.series_trend,
            "is_valid": self.is_valid,
        }


@dataclass
class FractalDimensionResult:
    """
    Result of fractal dimension analysis on UTXO value distribution.

    Box-counting dimension D measures self-similarity:
    - D = 0: Single point (all values identical)
    - D = 1: Line (uniform distribution)
    - D > 1: Space-filling (complex structure)

    Structure classification based on D:
    - WHALE_DOMINATED: D < 0.8 (concentrated in few clusters)
    - MIXED: 0.8 <= D <= 1.2 (typical market)
    - RETAIL_DOMINATED: D > 1.2 (highly dispersed)
    """

    dimension: float
    dimension_std: float
    r_squared: float
    scales_used: list
    counts: list
    is_valid: bool
    structure: str  # "WHALE_DOMINATED" | "MIXED" | "RETAIL_DOMINATED"
    fractal_vote: float
    sample_size: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "dimension": self.dimension,
            "dimension_std": self.dimension_std,
            "r_squared": self.r_squared,
            "is_valid": self.is_valid,
            "structure": self.structure,
            "fractal_vote": self.fractal_vote,
            "sample_size": self.sample_size,
        }


@dataclass
class EnhancedFusionResult:
    """
    Result of enhanced Monte Carlo signal fusion with 9 components.

    Extends spec-007 MonteCarloFusionResult with:
    - Power Law vote (spec-009)
    - Symbolic Dynamics vote (spec-009)
    - Fractal Dimension vote (spec-009)
    - Funding Rate vote (spec-008)
    - Open Interest vote (spec-008)
    - Wasserstein vote (spec-010)
    - Cointime vote (spec-018)
    """

    # Base Monte Carlo fields
    signal_mean: float
    signal_std: float
    ci_lower: float
    ci_upper: float
    action: str  # "BUY" | "SELL" | "HOLD"
    action_confidence: float
    n_samples: int
    distribution_type: str  # "unimodal" | "bimodal"

    # Component votes (None if unavailable)
    whale_vote: Optional[float] = None
    utxo_vote: Optional[float] = None
    funding_vote: Optional[float] = None
    oi_vote: Optional[float] = None
    power_law_vote: Optional[float] = None
    symbolic_vote: Optional[float] = None
    fractal_vote: Optional[float] = None
    wasserstein_vote: Optional[float] = None  # spec-010
    cointime_vote: Optional[float] = None  # spec-018
    sopr_vote: Optional[float] = None  # spec-019
    mvrv_z_vote: Optional[float] = None  # spec-020

    # Component weights (updated for 11 components, sum = 1.0)
    # spec-019: Derivatives weight reduction (funding+oi: 21%→10%)
    # spec-020: MVRV-Z integration (power_law 0.09→0.06, +mvrv_z 0.03)
    # Redistribution: +whale, +wasserstein, +cointime, +sopr (NEW)
    whale_weight: float = 0.24  # +0.03 Primary signal
    utxo_weight: float = 0.12  # unchanged
    funding_weight: float = 0.05  # -0.07 LAGGING
    oi_weight: float = 0.05  # -0.04 LAGGING
    power_law_weight: float = 0.06  # spec-020: -0.03 for mvrv_z
    symbolic_weight: float = 0.12  # unchanged
    fractal_weight: float = 0.09  # unchanged
    wasserstein_weight: float = 0.08  # +0.04 Grade A evidence
    cointime_weight: float = 0.14  # +0.02 AVIV
    sopr_weight: float = 0.02  # NEW spec-019
    mvrv_z_weight: float = 0.03  # spec-020: MVRV-Z cross-cycle

    # Metadata
    components_available: int = 0
    components_used: list = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate signal bounds."""
        if not -1.0 <= self.signal_mean <= 1.0:
            raise ValueError(f"signal_mean out of range: {self.signal_mean}")
        if not 0.0 <= self.action_confidence <= 1.0:
            raise ValueError(
                f"action_confidence out of range: {self.action_confidence}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        # B4 fix: Include ALL component votes and weights for API/DB storage
        return {
            # Base Monte Carlo fields
            "signal_mean": self.signal_mean,
            "signal_std": self.signal_std,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "action": self.action,
            "action_confidence": self.action_confidence,
            "n_samples": self.n_samples,
            "distribution_type": self.distribution_type,
            # Component votes
            "whale_vote": self.whale_vote,
            "utxo_vote": self.utxo_vote,
            "funding_vote": self.funding_vote,
            "oi_vote": self.oi_vote,
            "power_law_vote": self.power_law_vote,
            "symbolic_vote": self.symbolic_vote,
            "fractal_vote": self.fractal_vote,
            "wasserstein_vote": self.wasserstein_vote,
            "cointime_vote": self.cointime_vote,
            "sopr_vote": self.sopr_vote,
            "mvrv_z_vote": self.mvrv_z_vote,  # spec-020
            # Component weights
            "whale_weight": self.whale_weight,
            "utxo_weight": self.utxo_weight,
            "funding_weight": self.funding_weight,
            "oi_weight": self.oi_weight,
            "power_law_weight": self.power_law_weight,
            "symbolic_weight": self.symbolic_weight,
            "fractal_weight": self.fractal_weight,
            "wasserstein_weight": self.wasserstein_weight,
            "cointime_weight": self.cointime_weight,
            "sopr_weight": self.sopr_weight,
            "mvrv_z_weight": self.mvrv_z_weight,  # spec-020
            # Metadata
            "components_available": self.components_available,
            "components_used": self.components_used,
        }


# =============================================================================
# Spec-010: Wasserstein Distance Calculator Dataclasses
# =============================================================================


@dataclass
class WassersteinResult:
    """
    Result of Wasserstein distance calculation between two distributions.

    The Wasserstein-1 distance (Earth Mover's Distance) measures the minimum
    cost to transform one distribution into another. For 1D distributions,
    this is computed via CDF integration.

    Attributes:
        distance: W_1 distance (unnormalized)
        distance_normalized: W_1 / max(range) for scale-invariance
        window_1_size: Sample count in first window
        window_2_size: Sample count in second window
        window_1_mean: Mean of first distribution
        window_2_mean: Mean of second distribution
        window_1_std: Std of first distribution
        window_2_std: Std of second distribution
        shift_direction: "CONCENTRATION" | "DISPERSION" | "NONE"
        is_significant: True if distance > threshold
        is_valid: True if both windows have sufficient samples
        min_samples: Minimum samples required (default: 50)
    """

    distance: float
    distance_normalized: float
    window_1_size: int
    window_2_size: int
    window_1_mean: float
    window_2_mean: float
    window_1_std: float
    window_2_std: float
    shift_direction: str  # "CONCENTRATION" | "DISPERSION" | "NONE"
    is_significant: bool
    is_valid: bool
    min_samples: int = 50
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate Wasserstein result fields."""
        if self.distance < 0:
            raise ValueError(f"distance must be >= 0: {self.distance}")
        valid_directions = {"CONCENTRATION", "DISPERSION", "NONE"}
        if self.shift_direction not in valid_directions:
            raise ValueError(
                f"shift_direction must be one of {valid_directions}: {self.shift_direction}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "distance": self.distance,
            "distance_normalized": self.distance_normalized,
            "window_1_size": self.window_1_size,
            "window_2_size": self.window_2_size,
            "window_1_mean": self.window_1_mean,
            "window_2_mean": self.window_2_mean,
            "window_1_std": self.window_1_std,
            "window_2_std": self.window_2_std,
            "shift_direction": self.shift_direction,
            "is_significant": self.is_significant,
            "is_valid": self.is_valid,
        }


@dataclass
class RollingWassersteinResult:
    """
    Result of rolling Wasserstein analysis over time series.

    Computes Wasserstein distances between consecutive windows to detect
    regime shifts in UTXO value distributions over time.

    Attributes:
        distances: Rolling W values
        timestamps: Timestamp for each W value
        mean_distance: Average W over period
        mean_normalized_distance: Average normalized W (0-1 scale)
        max_distance: Peak W (potential regime change)
        min_distance: Minimum W (stable period)
        std_distance: Stability measure
        dominant_shift_direction: Most common shift direction across windows
        sustained_shift_detected: True if 3+ consecutive high-W
        shift_windows: Indices where W > threshold
        regime_status: "STABLE" | "TRANSITIONING" | "SHIFTED"
        wasserstein_vote: Signal vote (-1 to +1)
        vote_confidence: Based on consistency of direction
        window_size: Blocks per window
        step_size: Blocks between windows
        threshold: Shift detection threshold
        total_samples: Total values analyzed
        windows_analyzed: Number of window pairs compared
        is_valid: True if sufficient data
    """

    distances: list
    timestamps: list
    mean_distance: float
    mean_normalized_distance: float  # B3 fix: added for DB compatibility
    max_distance: float
    min_distance: float
    std_distance: float
    dominant_shift_direction: str  # B4 fix: "CONCENTRATION" | "DISPERSION" | "NONE"
    sustained_shift_detected: bool
    shift_windows: list
    regime_status: str  # "STABLE" | "TRANSITIONING" | "SHIFTED"
    wasserstein_vote: float
    vote_confidence: float
    window_size: int
    step_size: int
    threshold: float
    total_samples: int
    windows_analyzed: int
    is_valid: bool

    def __post_init__(self):
        """Validate rolling Wasserstein result fields."""
        if len(self.distances) != len(self.timestamps):
            raise ValueError(
                f"distances and timestamps length mismatch: "
                f"{len(self.distances)} vs {len(self.timestamps)}"
            )
        valid_statuses = {"STABLE", "TRANSITIONING", "SHIFTED"}
        if self.regime_status not in valid_statuses:
            raise ValueError(
                f"regime_status must be one of {valid_statuses}: {self.regime_status}"
            )
        valid_directions = {"CONCENTRATION", "DISPERSION", "NONE"}
        if self.dominant_shift_direction not in valid_directions:
            raise ValueError(
                f"dominant_shift_direction must be one of {valid_directions}: "
                f"{self.dominant_shift_direction}"
            )
        if not -1.0 <= self.wasserstein_vote <= 1.0:
            raise ValueError(
                f"wasserstein_vote must be in [-1, 1]: {self.wasserstein_vote}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "distances": self.distances,
            "timestamps": [
                t.isoformat() if hasattr(t, "isoformat") else str(t)
                for t in self.timestamps
            ],
            "mean_distance": self.mean_distance,
            "mean_normalized_distance": self.mean_normalized_distance,
            "max_distance": self.max_distance,
            "min_distance": self.min_distance,
            "std_distance": self.std_distance,
            "dominant_shift_direction": self.dominant_shift_direction,
            "sustained_shift_detected": self.sustained_shift_detected,
            "shift_windows": self.shift_windows,
            "regime_status": self.regime_status,
            "wasserstein_vote": self.wasserstein_vote,
            "vote_confidence": self.vote_confidence,
            "window_size": self.window_size,
            "step_size": self.step_size,
            "threshold": self.threshold,
            "total_samples": self.total_samples,
            "windows_analyzed": self.windows_analyzed,
            "is_valid": self.is_valid,
        }


# =============================================================================
# Spec-018: Cointime Economics Dataclasses
# =============================================================================


@dataclass
class CoinblocksMetrics:
    """
    Per-block coinblocks metrics for Cointime Economics.

    Coinblocks measure the economic weight of coins based on:
    - Created: BTC × blocks held (accumulates as coins age)
    - Destroyed: BTC × blocks since creation (when coins are spent)

    Attributes:
        block_height: Bitcoin block height
        timestamp: Block timestamp
        coinblocks_created: Coinblocks created this block
        coinblocks_destroyed: Coinblocks destroyed this block
        cumulative_created: Total coinblocks created (all time)
        cumulative_destroyed: Total coinblocks destroyed (all time)
        liveliness: destroyed / created ratio (0-1)
        vaultedness: 1 - liveliness (0-1)
    """

    block_height: int
    timestamp: datetime
    coinblocks_created: float
    coinblocks_destroyed: float
    cumulative_created: float
    cumulative_destroyed: float
    liveliness: float
    vaultedness: float

    def __post_init__(self):
        """Validate coinblocks metrics."""
        if self.coinblocks_created < 0:
            raise ValueError(
                f"coinblocks_created must be >= 0: {self.coinblocks_created}"
            )
        if self.coinblocks_destroyed < 0:
            raise ValueError(
                f"coinblocks_destroyed must be >= 0: {self.coinblocks_destroyed}"
            )
        if self.cumulative_created < 0:
            raise ValueError(
                f"cumulative_created must be >= 0: {self.cumulative_created}"
            )
        if self.cumulative_destroyed < 0:
            raise ValueError(
                f"cumulative_destroyed must be >= 0: {self.cumulative_destroyed}"
            )
        if not 0.0 <= self.liveliness <= 1.0:
            raise ValueError(f"liveliness must be in [0, 1]: {self.liveliness}")
        if not 0.0 <= self.vaultedness <= 1.0:
            raise ValueError(f"vaultedness must be in [0, 1]: {self.vaultedness}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
            "coinblocks_created": self.coinblocks_created,
            "coinblocks_destroyed": self.coinblocks_destroyed,
            "cumulative_created": self.cumulative_created,
            "cumulative_destroyed": self.cumulative_destroyed,
            "liveliness": self.liveliness,
            "vaultedness": self.vaultedness,
        }


@dataclass
class CointimeSupply:
    """
    Supply breakdown by activity level.

    Active Supply = coins that have moved recently (economically active)
    Vaulted Supply = coins that are dormant (long-term holders)

    Attributes:
        block_height: Bitcoin block height
        timestamp: Block timestamp
        total_supply_btc: Total Bitcoin supply
        active_supply_btc: Supply × liveliness
        vaulted_supply_btc: Supply × vaultedness
        active_supply_pct: Percentage active (0-100)
        vaulted_supply_pct: Percentage vaulted (0-100)
    """

    block_height: int
    timestamp: datetime
    total_supply_btc: float
    active_supply_btc: float
    vaulted_supply_btc: float
    active_supply_pct: float
    vaulted_supply_pct: float

    def __post_init__(self):
        """Validate supply metrics."""
        if self.total_supply_btc < 0:
            raise ValueError(f"total_supply_btc must be >= 0: {self.total_supply_btc}")
        # Allow small floating point errors in sum validation
        supply_sum = self.active_supply_btc + self.vaulted_supply_btc
        if abs(supply_sum - self.total_supply_btc) > 0.01:
            raise ValueError(
                f"active + vaulted must equal total: {supply_sum} != {self.total_supply_btc}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
            "total_supply_btc": self.total_supply_btc,
            "active_supply_btc": self.active_supply_btc,
            "vaulted_supply_btc": self.vaulted_supply_btc,
            "active_supply_pct": self.active_supply_pct,
            "vaulted_supply_pct": self.vaulted_supply_pct,
        }


@dataclass
class CointimeValuation:
    """
    AVIV and True Market Mean valuation metrics.

    True Market Mean = Market Cap / Active Supply
    AVIV = Current Price / True Market Mean (superior MVRV)

    Attributes:
        block_height: Bitcoin block height
        timestamp: Block timestamp
        current_price_usd: Current BTC price in USD
        market_cap_usd: Total market capitalization
        active_supply_btc: Active supply in BTC
        true_market_mean_usd: Activity-adjusted price
        aviv_ratio: AVIV ratio (price / TMM)
        aviv_percentile: Historical percentile (0-100)
        valuation_zone: "UNDERVALUED" | "FAIR" | "OVERVALUED"
    """

    block_height: int
    timestamp: datetime
    current_price_usd: float
    market_cap_usd: float
    active_supply_btc: float
    true_market_mean_usd: float
    aviv_ratio: float
    aviv_percentile: float
    valuation_zone: str

    def __post_init__(self):
        """Validate valuation metrics."""
        valid_zones = {"UNDERVALUED", "FAIR", "OVERVALUED"}
        if self.valuation_zone not in valid_zones:
            raise ValueError(
                f"valuation_zone must be one of {valid_zones}: {self.valuation_zone}"
            )
        if not 0.0 <= self.aviv_percentile <= 100.0:
            raise ValueError(
                f"aviv_percentile must be in [0, 100]: {self.aviv_percentile}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
            "current_price_usd": self.current_price_usd,
            "market_cap_usd": self.market_cap_usd,
            "active_supply_btc": self.active_supply_btc,
            "true_market_mean_usd": self.true_market_mean_usd,
            "aviv_ratio": self.aviv_ratio,
            "aviv_percentile": self.aviv_percentile,
            "valuation_zone": self.valuation_zone,
        }


@dataclass
class CointimeSignal:
    """
    Trading signal from Cointime Economics analysis.

    Combines liveliness trends, AVIV valuation, and pattern detection
    to generate a fusion-compatible vote.

    Attributes:
        block_height: Bitcoin block height
        timestamp: Block timestamp
        liveliness_7d_change: 7-day change in liveliness
        liveliness_30d_change: 30-day change in liveliness
        liveliness_trend: "INCREASING" | "DECREASING" | "STABLE"
        aviv_ratio: Current AVIV ratio
        valuation_zone: "UNDERVALUED" | "FAIR" | "OVERVALUED"
        extreme_dormancy: True if liveliness < 0.15
        supply_squeeze: True if active supply declining
        distribution_warning: True if AVIV > 2.0 + liveliness spike
        cointime_vote: Signal vote (-1 to +1)
        confidence: Signal confidence (0.5 to 1.0)
    """

    block_height: int
    timestamp: datetime
    liveliness_7d_change: float
    liveliness_30d_change: float
    liveliness_trend: str
    aviv_ratio: float
    valuation_zone: str
    extreme_dormancy: bool
    supply_squeeze: bool
    distribution_warning: bool
    cointime_vote: float
    confidence: float

    def __post_init__(self):
        """Validate signal fields."""
        valid_trends = {"INCREASING", "DECREASING", "STABLE"}
        if self.liveliness_trend not in valid_trends:
            raise ValueError(
                f"liveliness_trend must be one of {valid_trends}: {self.liveliness_trend}"
            )
        valid_zones = {"UNDERVALUED", "FAIR", "OVERVALUED"}
        if self.valuation_zone not in valid_zones:
            raise ValueError(
                f"valuation_zone must be one of {valid_zones}: {self.valuation_zone}"
            )
        if not -1.0 <= self.cointime_vote <= 1.0:
            raise ValueError(f"cointime_vote must be in [-1, 1]: {self.cointime_vote}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
            "liveliness_7d_change": self.liveliness_7d_change,
            "liveliness_30d_change": self.liveliness_30d_change,
            "liveliness_trend": self.liveliness_trend,
            "aviv_ratio": self.aviv_ratio,
            "valuation_zone": self.valuation_zone,
            "extreme_dormancy": self.extreme_dormancy,
            "supply_squeeze": self.supply_squeeze,
            "distribution_warning": self.distribution_warning,
            "cointime_vote": self.cointime_vote,
            "confidence": self.confidence,
        }


# =============================================================================
# Spec-017/020: UTXO Lifecycle & MVRV Dataclasses
# =============================================================================


@dataclass
class UTXOLifecycle:
    """Complete lifecycle record for a single UTXO.

    Tracks creation and spending of UTXOs with price data for realized
    metrics calculation. Used by utxo_lifecycle.py engine.

    Spec: spec-017
    """

    # Identity
    outpoint: str  # f"{txid}:{vout_index}"
    txid: str
    vout_index: int

    # Creation
    creation_block: int
    creation_timestamp: datetime
    creation_price_usd: float
    btc_value: float
    realized_value_usd: float  # btc_value × creation_price

    # Spending (None if unspent)
    spent_block: Optional[int] = None
    spent_timestamp: Optional[datetime] = None
    spent_price_usd: Optional[float] = None
    spending_txid: Optional[str] = None

    # Derived
    age_blocks: Optional[int] = None
    age_days: Optional[int] = None
    cohort: str = ""  # "STH" | "LTH"
    sub_cohort: str = ""  # "<1d", "1d-1w", etc.
    sopr: Optional[float] = None

    # Metadata
    is_coinbase: bool = False
    is_spent: bool = False
    price_source: str = "utxoracle"

    def __post_init__(self):
        """Validate UTXO fields."""
        if self.btc_value < 0:
            raise ValueError(f"btc_value must be >= 0: {self.btc_value}")
        if self.creation_price_usd < 0:
            raise ValueError(
                f"creation_price_usd must be >= 0: {self.creation_price_usd}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "outpoint": self.outpoint,
            "txid": self.txid,
            "vout_index": self.vout_index,
            "creation_block": self.creation_block,
            "creation_timestamp": self.creation_timestamp.isoformat()
            if hasattr(self.creation_timestamp, "isoformat")
            else str(self.creation_timestamp),
            "creation_price_usd": self.creation_price_usd,
            "btc_value": self.btc_value,
            "realized_value_usd": self.realized_value_usd,
            "spent_block": self.spent_block,
            "spent_timestamp": self.spent_timestamp.isoformat()
            if self.spent_timestamp and hasattr(self.spent_timestamp, "isoformat")
            else self.spent_timestamp,
            "spent_price_usd": self.spent_price_usd,
            "spending_txid": self.spending_txid,
            "age_blocks": self.age_blocks,
            "age_days": self.age_days,
            "cohort": self.cohort,
            "sub_cohort": self.sub_cohort,
            "sopr": self.sopr,
            "is_coinbase": self.is_coinbase,
            "is_spent": self.is_spent,
            "price_source": self.price_source,
        }


@dataclass
class UTXOSetSnapshot:
    """Point-in-time snapshot of UTXO set metrics.

    Captures supply distribution and realized metrics at a specific
    block height. Used for historical analysis and HODL waves.

    Spec: spec-017
    """

    block_height: int
    timestamp: datetime

    # Supply Distribution
    total_supply_btc: float
    sth_supply_btc: float  # age < 155 days
    lth_supply_btc: float  # age >= 155 days
    supply_by_cohort: dict  # cohort -> BTC

    # Realized Metrics
    realized_cap_usd: float
    market_cap_usd: float
    mvrv: float
    nupl: float

    # HODL Waves
    hodl_waves: dict  # cohort -> % of supply

    def __post_init__(self):
        """Validate snapshot fields."""
        if self.total_supply_btc < 0:
            raise ValueError(f"total_supply_btc must be >= 0: {self.total_supply_btc}")
        if self.realized_cap_usd < 0:
            raise ValueError(f"realized_cap_usd must be >= 0: {self.realized_cap_usd}")
        # B5 fix: Validate market_cap_usd and mvrv
        if self.market_cap_usd < 0:
            raise ValueError(f"market_cap_usd must be >= 0: {self.market_cap_usd}")
        if self.mvrv < 0:
            raise ValueError(f"mvrv must be >= 0: {self.mvrv}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
            "total_supply_btc": self.total_supply_btc,
            "sth_supply_btc": self.sth_supply_btc,
            "lth_supply_btc": self.lth_supply_btc,
            "supply_by_cohort": self.supply_by_cohort,
            "realized_cap_usd": self.realized_cap_usd,
            "market_cap_usd": self.market_cap_usd,
            "mvrv": self.mvrv,
            "nupl": self.nupl,
            "hodl_waves": self.hodl_waves,
        }


@dataclass
class AgeCohortsConfig:
    """Configuration for age cohort classification.

    Defines the STH/LTH boundary and sub-cohort age ranges for
    HODL waves analysis.

    Spec: spec-017
    """

    sth_threshold_days: int = 155

    cohorts: list = field(
        default_factory=lambda: [
            ("<1d", 0, 1),
            ("1d-1w", 1, 7),
            ("1w-1m", 7, 30),
            ("1m-3m", 30, 90),
            ("3m-6m", 90, 180),
            ("6m-1y", 180, 365),
            ("1y-2y", 365, 730),
            ("2y-3y", 730, 1095),
            ("3y-5y", 1095, 1825),
            (">5y", 1825, float("inf")),
        ]
    )

    def classify(self, age_days: int) -> tuple[str, str]:
        """Return (cohort, sub_cohort) for given age.

        Args:
            age_days: Age of UTXO in days.

        Returns:
            Tuple of (main cohort, sub-cohort name).
            Main cohort is "STH" if age < threshold, else "LTH".

        Raises:
            ValueError: If age_days is negative.
        """
        # B3 fix: Validate age_days
        if age_days < 0:
            raise ValueError(f"age_days must be non-negative, got {age_days}")

        cohort = "STH" if age_days < self.sth_threshold_days else "LTH"
        for name, min_days, max_days in self.cohorts:
            if min_days <= age_days < max_days:
                return cohort, name
        return cohort, ">5y"


@dataclass
class SyncState:
    """Tracks sync progress for incremental updates.

    Used by utxo_lifecycle engine to resume from last processed block.

    Spec: spec-017
    """

    last_processed_block: int
    last_processed_timestamp: datetime
    total_utxos_created: int
    total_utxos_spent: int
    sync_started: datetime
    sync_duration_seconds: float

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "last_processed_block": self.last_processed_block,
            "last_processed_timestamp": self.last_processed_timestamp.isoformat()
            if hasattr(self.last_processed_timestamp, "isoformat")
            else str(self.last_processed_timestamp),
            "total_utxos_created": self.total_utxos_created,
            "total_utxos_spent": self.total_utxos_spent,
            "sync_started": self.sync_started.isoformat()
            if hasattr(self.sync_started, "isoformat")
            else str(self.sync_started),
            "sync_duration_seconds": self.sync_duration_seconds,
        }


@dataclass
class MVRVExtendedSignal:
    """Extended MVRV metrics with Z-score and cohort variants.

    Combines base MVRV with Z-score normalization and STH/LTH breakdown.
    Used for signal classification and fusion integration.

    Spec: spec-020
    """

    # Base metrics (from existing calculate_mvrv)
    mvrv: float  # Market Cap / Realized Cap
    market_cap_usd: float
    realized_cap_usd: float

    # Z-Score (NEW)
    mvrv_z: float  # (Market Cap - Realized Cap) / StdDev(Market Cap)
    z_history_days: int  # Number of days used for std calculation

    # Cohort variants (NEW)
    sth_mvrv: float  # Market Cap / STH Realized Cap
    sth_realized_cap_usd: float
    lth_mvrv: float  # Market Cap / LTH Realized Cap
    lth_realized_cap_usd: float

    # Signal classification
    zone: str  # "EXTREME_SELL", "CAUTION", "NORMAL", "ACCUMULATION"
    confidence: float  # 0.0 to 1.0

    # Metadata
    timestamp: datetime
    block_height: int
    threshold_days: int = 155  # STH/LTH boundary

    def __post_init__(self):
        """Validate MVRV extended signal fields."""
        if self.mvrv < 0:
            raise ValueError(f"mvrv must be >= 0: {self.mvrv}")
        # B4 fix: Validate cohort MVRV and realized cap values
        if self.sth_mvrv < 0:
            raise ValueError(f"sth_mvrv must be >= 0: {self.sth_mvrv}")
        if self.lth_mvrv < 0:
            raise ValueError(f"lth_mvrv must be >= 0: {self.lth_mvrv}")
        if self.realized_cap_usd < 0:
            raise ValueError(f"realized_cap_usd must be >= 0: {self.realized_cap_usd}")
        if self.market_cap_usd < 0:
            raise ValueError(f"market_cap_usd must be >= 0: {self.market_cap_usd}")
        valid_zones = {"EXTREME_SELL", "CAUTION", "NORMAL", "ACCUMULATION"}
        if self.zone not in valid_zones:
            raise ValueError(f"zone must be one of {valid_zones}: {self.zone}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "mvrv": self.mvrv,
            "market_cap_usd": self.market_cap_usd,
            "realized_cap_usd": self.realized_cap_usd,
            "mvrv_z": self.mvrv_z,
            "z_history_days": self.z_history_days,
            "sth_mvrv": self.sth_mvrv,
            "sth_realized_cap_usd": self.sth_realized_cap_usd,
            "lth_mvrv": self.lth_mvrv,
            "lth_realized_cap_usd": self.lth_realized_cap_usd,
            "zone": self.zone,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
            "block_height": self.block_height,
            "threshold_days": self.threshold_days,
        }


# =============================================================================
# Spec-021: Advanced On-Chain Metrics Dataclasses
# =============================================================================


@dataclass
class URPDBucket:
    """Single price bucket in URPD distribution.

    Represents BTC supply accumulated within a price range.

    Attributes:
        price_low: Lower bound of bucket (USD)
        price_high: Upper bound of bucket (USD)
        btc_amount: Total BTC in bucket
        utxo_count: Number of UTXOs in bucket
        percentage: % of total supply in bucket
    """

    price_low: float
    price_high: float
    btc_amount: float
    utxo_count: int
    percentage: float

    def __post_init__(self):
        """Validate bucket fields."""
        if self.price_low < 0:
            raise ValueError(f"price_low must be >= 0: {self.price_low}")
        if self.price_high < self.price_low:
            raise ValueError("price_high must be >= price_low")
        if self.btc_amount < 0:
            raise ValueError(f"btc_amount must be >= 0: {self.btc_amount}")
        if self.utxo_count < 0:
            raise ValueError(f"utxo_count must be >= 0: {self.utxo_count}")
        if not 0.0 <= self.percentage <= 100.0:
            raise ValueError(f"percentage must be in [0, 100]: {self.percentage}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "price_low": self.price_low,
            "price_high": self.price_high,
            "btc_amount": self.btc_amount,
            "utxo_count": self.utxo_count,
            "percentage": self.percentage,
        }


@dataclass
class CostBasisPercentiles:
    """Cost basis percentiles weighted by BTC value.

    Shows distribution of UTXO acquisition prices at key percentiles.
    Useful for understanding support/resistance levels where significant
    supply was accumulated.

    Attributes:
        p10: 10th percentile price (10% of supply acquired below this price)
        p25: 25th percentile price (1st quartile)
        p50: 50th percentile price (median cost basis)
        p75: 75th percentile price (3rd quartile)
        p90: 90th percentile price (90% of supply acquired below this price)
    """

    p10: float
    p25: float
    p50: float
    p75: float
    p90: float

    def __post_init__(self):
        """Validate percentiles are in ascending order."""
        percentiles = [self.p10, self.p25, self.p50, self.p75, self.p90]
        for i, p in enumerate(percentiles):
            if p < 0:
                raise ValueError(
                    f"Percentile values must be >= 0: p{[10, 25, 50, 75, 90][i]} = {p}"
                )

        # Check ascending order
        if not all(
            percentiles[i] <= percentiles[i + 1] for i in range(len(percentiles) - 1)
        ):
            raise ValueError(
                f"Percentiles must be in ascending order: "
                f"p10={self.p10}, p25={self.p25}, p50={self.p50}, "
                f"p75={self.p75}, p90={self.p90}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "p10": self.p10,
            "p25": self.p25,
            "p50": self.p50,
            "p75": self.p75,
            "p90": self.p90,
        }


@dataclass
class URPDResult:
    """UTXO Realized Price Distribution result.

    Shows distribution of unspent BTC by acquisition price (cost basis).
    Used for identifying support/resistance zones and profit-taking levels.

    Attributes:
        buckets: List of price buckets (sorted by price descending)
        bucket_size_usd: Size of each bucket in USD
        total_supply_btc: Total BTC in distribution
        current_price_usd: Current BTC price for context
        supply_above_price_btc: BTC with cost basis > current price (in loss)
        supply_below_price_btc: BTC with cost basis < current price (in profit)
        supply_above_price_pct: % of supply in loss
        supply_below_price_pct: % of supply in profit
        dominant_bucket: Bucket with highest BTC amount
        percentiles: Cost basis percentiles (optional)
        block_height: Block height at calculation
        timestamp: Calculation timestamp
    """

    buckets: list  # List[URPDBucket]
    bucket_size_usd: float
    total_supply_btc: float
    current_price_usd: float
    supply_above_price_btc: float
    supply_below_price_btc: float
    supply_above_price_pct: float
    supply_below_price_pct: float
    dominant_bucket: Optional["URPDBucket"]
    block_height: int
    percentiles: Optional[CostBasisPercentiles] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate URPD result fields."""
        if self.bucket_size_usd <= 0:
            raise ValueError(f"bucket_size_usd must be > 0: {self.bucket_size_usd}")
        if self.total_supply_btc < 0:
            raise ValueError(f"total_supply_btc must be >= 0: {self.total_supply_btc}")
        if self.current_price_usd <= 0:
            raise ValueError(f"current_price_usd must be > 0: {self.current_price_usd}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "buckets": [b.to_dict() for b in self.buckets],
            "bucket_size_usd": self.bucket_size_usd,
            "total_supply_btc": self.total_supply_btc,
            "current_price_usd": self.current_price_usd,
            "supply_above_price_btc": self.supply_above_price_btc,
            "supply_below_price_btc": self.supply_below_price_btc,
            "supply_above_price_pct": self.supply_above_price_pct,
            "supply_below_price_pct": self.supply_below_price_pct,
            "dominant_bucket": self.dominant_bucket.to_dict()
            if self.dominant_bucket
            else None,
            "percentiles": self.percentiles.to_dict() if self.percentiles else None,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
        }


@dataclass
class SupplyProfitLossResult:
    """Supply breakdown by profit/loss status.

    Classifies circulating supply by whether UTXOs are in profit
    (current price > creation price) or loss.

    Signals:
        > 95% in profit: Euphoria (cycle top warning)
        80-95% in profit: Bull market
        50-80% in profit: Transition
        < 50% in profit: Capitulation (accumulation zone)

    Attributes:
        current_price_usd: Price used for calculation
        total_supply_btc: Total unspent BTC
        supply_in_profit_btc: BTC where current_price > creation_price
        supply_in_loss_btc: BTC where current_price < creation_price
        supply_breakeven_btc: BTC where current_price == creation_price
        pct_in_profit: % of supply in profit
        pct_in_loss: % of supply in loss
        sth_in_profit_btc: STH (<155d) supply in profit
        sth_in_loss_btc: STH supply in loss
        sth_pct_in_profit: % of STH in profit
        lth_in_profit_btc: LTH (>=155d) supply in profit
        lth_in_loss_btc: LTH supply in loss
        lth_pct_in_profit: % of LTH in profit
        market_phase: "EUPHORIA" | "BULL" | "TRANSITION" | "CAPITULATION"
        signal_strength: 0.0 to 1.0 based on extremity
        block_height: Block height at calculation
        timestamp: Calculation timestamp
    """

    current_price_usd: float
    total_supply_btc: float
    supply_in_profit_btc: float
    supply_in_loss_btc: float
    supply_breakeven_btc: float
    pct_in_profit: float
    pct_in_loss: float
    sth_in_profit_btc: float
    sth_in_loss_btc: float
    sth_pct_in_profit: float
    lth_in_profit_btc: float
    lth_in_loss_btc: float
    lth_pct_in_profit: float
    market_phase: str  # "EUPHORIA" | "BULL" | "TRANSITION" | "CAPITULATION"
    signal_strength: float
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate supply profit/loss fields."""
        valid_phases = {"EUPHORIA", "BULL", "TRANSITION", "CAPITULATION"}
        if self.market_phase not in valid_phases:
            raise ValueError(
                f"market_phase must be one of {valid_phases}: {self.market_phase}"
            )
        if not 0.0 <= self.signal_strength <= 1.0:
            raise ValueError(
                f"signal_strength must be in [0, 1]: {self.signal_strength}"
            )
        if not 0.0 <= self.pct_in_profit <= 100.0:
            raise ValueError(f"pct_in_profit must be in [0, 100]: {self.pct_in_profit}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "current_price_usd": self.current_price_usd,
            "total_supply_btc": self.total_supply_btc,
            "supply_in_profit_btc": self.supply_in_profit_btc,
            "supply_in_loss_btc": self.supply_in_loss_btc,
            "supply_breakeven_btc": self.supply_breakeven_btc,
            "pct_in_profit": self.pct_in_profit,
            "pct_in_loss": self.pct_in_loss,
            "sth_in_profit_btc": self.sth_in_profit_btc,
            "sth_in_loss_btc": self.sth_in_loss_btc,
            "sth_pct_in_profit": self.sth_pct_in_profit,
            "lth_in_profit_btc": self.lth_in_profit_btc,
            "lth_in_loss_btc": self.lth_in_loss_btc,
            "lth_pct_in_profit": self.lth_pct_in_profit,
            "market_phase": self.market_phase,
            "signal_strength": self.signal_strength,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
        }


@dataclass
class ReserveRiskResult:
    """Reserve Risk metric result.

    Measures confidence of long-term holders relative to price.
    Lower values = higher conviction (good buy zones).

    Formula: Reserve Risk = Price / (HODL Bank × Circulating Supply)
    HODL Bank = Cumulative Coindays Destroyed (opportunity cost)

    Signal Zones:
        < 0.002: Strong buy zone (historically cycle bottoms)
        0.002 - 0.008: Accumulation zone
        0.008 - 0.02: Fair value
        > 0.02: Distribution zone (cycle top warning)

    Attributes:
        reserve_risk: Main metric value
        current_price_usd: BTC price used
        hodl_bank: Cumulative coindays destroyed (scaled)
        circulating_supply_btc: Total unspent BTC
        mvrv: MVRV ratio (for context)
        liveliness: Network liveliness (from cointime)
        signal_zone: "STRONG_BUY" | "ACCUMULATION" | "FAIR_VALUE" | "DISTRIBUTION"
        confidence: Signal confidence (0.0 to 1.0)
        block_height: Block height at calculation
        timestamp: Calculation timestamp
    """

    reserve_risk: float
    current_price_usd: float
    hodl_bank: float
    circulating_supply_btc: float
    mvrv: float
    liveliness: float
    signal_zone: str  # "STRONG_BUY" | "ACCUMULATION" | "FAIR_VALUE" | "DISTRIBUTION"
    confidence: float
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate reserve risk fields."""
        valid_zones = {"STRONG_BUY", "ACCUMULATION", "FAIR_VALUE", "DISTRIBUTION"}
        if self.signal_zone not in valid_zones:
            raise ValueError(
                f"signal_zone must be one of {valid_zones}: {self.signal_zone}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")
        if self.reserve_risk < 0:
            raise ValueError(f"reserve_risk must be >= 0: {self.reserve_risk}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "reserve_risk": self.reserve_risk,
            "current_price_usd": self.current_price_usd,
            "hodl_bank": self.hodl_bank,
            "circulating_supply_btc": self.circulating_supply_btc,
            "mvrv": self.mvrv,
            "liveliness": self.liveliness,
            "signal_zone": self.signal_zone,
            "confidence": self.confidence,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
        }


@dataclass
class SellSideRiskResult:
    """Sell-side Risk Ratio result.

    Ratio of realized profit to market cap. High values indicate
    aggressive profit-taking (potential distribution).

    Formula: Sell-side Risk = Realized Profit (30d) / Market Cap
    Realized Profit = Sum((spend_price - creation_price) × btc_value) for spent UTXOs

    Signal Zones:
        < 0.1%: Low distribution (bullish)
        0.1% - 0.3%: Normal profit-taking
        0.3% - 1.0%: Elevated distribution
        > 1.0%: Aggressive distribution (top warning)

    Attributes:
        sell_side_risk: Main metric value (ratio)
        sell_side_risk_pct: Metric as percentage
        realized_profit_usd: Profit realized in window
        realized_loss_usd: Loss realized in window (for context)
        net_realized_pnl_usd: Net realized P&L
        market_cap_usd: Market cap at calculation time
        window_days: Rolling window size (default 30)
        spent_utxos_in_window: Number of UTXOs spent
        signal_zone: "LOW" | "NORMAL" | "ELEVATED" | "AGGRESSIVE"
        confidence: Signal confidence (0.0 to 1.0)
        block_height: Block height at calculation
        timestamp: Calculation timestamp
    """

    sell_side_risk: float
    sell_side_risk_pct: float
    realized_profit_usd: float
    realized_loss_usd: float
    net_realized_pnl_usd: float
    market_cap_usd: float
    window_days: int
    spent_utxos_in_window: int
    signal_zone: str  # "LOW" | "NORMAL" | "ELEVATED" | "AGGRESSIVE"
    confidence: float
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate sell-side risk fields."""
        valid_zones = {"LOW", "NORMAL", "ELEVATED", "AGGRESSIVE"}
        if self.signal_zone not in valid_zones:
            raise ValueError(
                f"signal_zone must be one of {valid_zones}: {self.signal_zone}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")
        if self.sell_side_risk < 0:
            raise ValueError(f"sell_side_risk must be >= 0: {self.sell_side_risk}")
        if self.window_days <= 0:
            raise ValueError(f"window_days must be > 0: {self.window_days}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "sell_side_risk": self.sell_side_risk,
            "sell_side_risk_pct": self.sell_side_risk_pct,
            "realized_profit_usd": self.realized_profit_usd,
            "realized_loss_usd": self.realized_loss_usd,
            "net_realized_pnl_usd": self.net_realized_pnl_usd,
            "market_cap_usd": self.market_cap_usd,
            "window_days": self.window_days,
            "spent_utxos_in_window": self.spent_utxos_in_window,
            "signal_zone": self.signal_zone,
            "confidence": self.confidence,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
        }


@dataclass
class CoinDaysDestroyedResult:
    """Coindays Destroyed (CDD) and Value Days Destroyed (VDD) result.

    CDD: When a UTXO is spent, CDD = age_days × btc_value
    VDD: CDD weighted by price = CDD × price

    Measures "old money" movement - spikes indicate long-term holders
    moving coins (distribution or exchange deposit).

    Attributes:
        cdd_total: Total CDD in period
        cdd_daily_avg: Average daily CDD
        vdd_total: Total VDD in period (CDD × price)
        vdd_daily_avg: Average daily VDD
        vdd_multiple: VDD / 365d_MA(VDD), > 2.0 = significant distribution
        window_days: Analysis window (default 30)
        spent_utxos_count: Number of UTXOs spent
        avg_utxo_age_days: Average age of spent UTXOs
        max_single_day_cdd: Peak CDD in a single day
        max_single_day_date: Date of peak CDD
        current_price_usd: Price used for VDD
        signal_zone: "LOW_ACTIVITY" | "NORMAL" | "ELEVATED" | "SPIKE"
        confidence: Signal confidence (0.0 to 1.0)
        block_height: Block height at calculation
        timestamp: Calculation timestamp
    """

    cdd_total: float
    cdd_daily_avg: float
    vdd_total: float
    vdd_daily_avg: float
    vdd_multiple: Optional[float]  # None if insufficient history for MA
    window_days: int
    spent_utxos_count: int
    avg_utxo_age_days: float
    max_single_day_cdd: float
    max_single_day_date: Optional[datetime]
    current_price_usd: float
    signal_zone: str  # "LOW_ACTIVITY" | "NORMAL" | "ELEVATED" | "SPIKE"
    confidence: float
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate CDD/VDD fields."""
        valid_zones = {"LOW_ACTIVITY", "NORMAL", "ELEVATED", "SPIKE"}
        if self.signal_zone not in valid_zones:
            raise ValueError(
                f"signal_zone must be one of {valid_zones}: {self.signal_zone}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")
        if self.cdd_total < 0:
            raise ValueError(f"cdd_total must be >= 0: {self.cdd_total}")
        if self.vdd_total < 0:
            raise ValueError(f"vdd_total must be >= 0: {self.vdd_total}")
        if self.window_days <= 0:
            raise ValueError(f"window_days must be > 0: {self.window_days}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "cdd_total": self.cdd_total,
            "cdd_daily_avg": self.cdd_daily_avg,
            "vdd_total": self.vdd_total,
            "vdd_daily_avg": self.vdd_daily_avg,
            "vdd_multiple": self.vdd_multiple,
            "window_days": self.window_days,
            "spent_utxos_count": self.spent_utxos_count,
            "avg_utxo_age_days": self.avg_utxo_age_days,
            "max_single_day_cdd": self.max_single_day_cdd,
            "max_single_day_date": self.max_single_day_date.isoformat()
            if self.max_single_day_date
            and hasattr(self.max_single_day_date, "isoformat")
            else self.max_single_day_date,
            "current_price_usd": self.current_price_usd,
            "signal_zone": self.signal_zone,
            "confidence": self.confidence,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
        }


# =============================================================================
# Spec-022: NUPL Oscillator Dataclasses
# =============================================================================


class NUPLZone(str, Enum):
    """NUPL market cycle zones based on Glassnode thresholds.

    Interpretation:
    - CAPITULATION: < 0 (network underwater, extreme fear, historically cycle bottoms)
    - HOPE_FEAR: 0 - 0.25 (recovery phase)
    - OPTIMISM: 0.25 - 0.5 (bull market building)
    - BELIEF: 0.5 - 0.75 (strong conviction)
    - EUPHORIA: > 0.75 (extreme greed, historically cycle tops)

    Spec: spec-022
    """

    CAPITULATION = "CAPITULATION"
    HOPE_FEAR = "HOPE_FEAR"
    OPTIMISM = "OPTIMISM"
    BELIEF = "BELIEF"
    EUPHORIA = "EUPHORIA"


@dataclass
class NUPLResult:
    """NUPL Oscillator result with zone classification.

    Net Unrealized Profit/Loss = (Market Cap - Realized Cap) / Market Cap

    Interpretation:
    - NUPL > 0.75: Euphoria (historically cycle tops)
    - NUPL 0.5-0.75: Belief
    - NUPL 0.25-0.5: Optimism
    - NUPL 0-0.25: Hope/Fear
    - NUPL < 0: Capitulation (historically cycle bottoms)

    Spec: spec-022
    """

    nupl: float
    zone: NUPLZone
    market_cap_usd: float
    realized_cap_usd: float
    unrealized_profit_usd: float
    pct_supply_in_profit: float
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    confidence: float = 0.85  # Default high confidence for Tier A metric

    def __post_init__(self):
        """Validate NUPL result fields."""
        if self.market_cap_usd < 0:
            raise ValueError(f"market_cap_usd must be >= 0: {self.market_cap_usd}")
        if self.realized_cap_usd < 0:
            raise ValueError(f"realized_cap_usd must be >= 0: {self.realized_cap_usd}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")
        if not isinstance(self.zone, NUPLZone):
            raise ValueError(f"zone must be NUPLZone enum: {self.zone}")
        # B1 fix: Validate pct_supply_in_profit range
        if not 0.0 <= self.pct_supply_in_profit <= 100.0:
            raise ValueError(
                f"pct_supply_in_profit must be in [0, 100]: {self.pct_supply_in_profit}"
            )
        # B2 fix: Validate block_height is non-negative
        if self.block_height < 0:
            raise ValueError(f"block_height must be >= 0: {self.block_height}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "nupl": self.nupl,
            "zone": self.zone.value,
            "market_cap_usd": self.market_cap_usd,
            "realized_cap_usd": self.realized_cap_usd,
            "unrealized_profit_usd": self.unrealized_profit_usd,
            "pct_supply_in_profit": self.pct_supply_in_profit,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
            "confidence": self.confidence,
        }


# =============================================================================
# Spec-023: STH/LTH Cost Basis Dataclasses
# =============================================================================


@dataclass
class CostBasisResult:
    """Weighted average cost basis for STH/LTH holder cohorts.

    Cost Basis = SUM(creation_price_usd × btc_value) / SUM(btc_value)

    Key Support/Resistance Levels:
    - STH Cost Basis: Short-term support (often tested during corrections)
    - LTH Cost Basis: Macro support (rarely breached in bull markets)

    MVRV Interpretation:
    - sth_mvrv < 1: STH underwater → capitulation risk
    - lth_mvrv > 1: LTH in profit → distribution risk

    Spec: spec-023
    """

    # Cost basis metrics
    sth_cost_basis: float  # Weighted avg acquisition price for STH (<155 days)
    lth_cost_basis: float  # Weighted avg acquisition price for LTH (>=155 days)
    total_cost_basis: float  # Overall realized price (all unspent UTXOs)

    # Cohort MVRV
    sth_mvrv: float  # current_price / sth_cost_basis
    lth_mvrv: float  # current_price / lth_cost_basis

    # Supply breakdown
    sth_supply_btc: float  # Total BTC held by STH cohort
    lth_supply_btc: float  # Total BTC held by LTH cohort

    # Context
    current_price_usd: float  # Price used for MVRV calculation
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    confidence: float = 0.85  # Default high confidence for Tier A metric

    def __post_init__(self):
        """Validate cost basis result fields."""
        # Cost basis values must be non-negative
        if self.sth_cost_basis < 0:
            raise ValueError(f"sth_cost_basis must be >= 0: {self.sth_cost_basis}")
        if self.lth_cost_basis < 0:
            raise ValueError(f"lth_cost_basis must be >= 0: {self.lth_cost_basis}")
        if self.total_cost_basis < 0:
            raise ValueError(f"total_cost_basis must be >= 0: {self.total_cost_basis}")

        # MVRV values must be non-negative
        if self.sth_mvrv < 0:
            raise ValueError(f"sth_mvrv must be >= 0: {self.sth_mvrv}")
        if self.lth_mvrv < 0:
            raise ValueError(f"lth_mvrv must be >= 0: {self.lth_mvrv}")

        # Supply must be non-negative
        if self.sth_supply_btc < 0:
            raise ValueError(f"sth_supply_btc must be >= 0: {self.sth_supply_btc}")
        if self.lth_supply_btc < 0:
            raise ValueError(f"lth_supply_btc must be >= 0: {self.lth_supply_btc}")

        # Price must be positive
        if self.current_price_usd <= 0:
            raise ValueError(f"current_price_usd must be > 0: {self.current_price_usd}")

        # Block height must be non-negative
        if self.block_height < 0:
            raise ValueError(f"block_height must be >= 0: {self.block_height}")

        # Confidence must be in [0, 1]
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "sth_cost_basis": self.sth_cost_basis,
            "lth_cost_basis": self.lth_cost_basis,
            "total_cost_basis": self.total_cost_basis,
            "sth_mvrv": self.sth_mvrv,
            "lth_mvrv": self.lth_mvrv,
            "sth_supply_btc": self.sth_supply_btc,
            "lth_supply_btc": self.lth_supply_btc,
            "current_price_usd": self.current_price_usd,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
            "confidence": self.confidence,
        }


# =============================================================================
# Spec-024: Revived Supply Dataclasses
# =============================================================================


class RevivedZone(str, Enum):
    """Behavioral zone classification for revived supply activity.

    Classifies daily revived supply (BTC) into activity zones based on
    long-term holder movement thresholds.

    Interpretation:
    - DORMANT: < 1000 BTC/day (low LTH activity, stable holding)
    - NORMAL: 1000-5000 BTC/day (baseline movement)
    - ELEVATED: 5000-10000 BTC/day (increased LTH selling, watch closely)
    - SPIKE: > 10000 BTC/day (major distribution event, potential top signal)

    Spec: spec-024
    """

    DORMANT = "dormant"
    NORMAL = "normal"
    ELEVATED = "elevated"
    SPIKE = "spike"


@dataclass
class RevivedSupplyResult:
    """Revived supply metrics for dormant coin movement tracking.

    Tracks coins that have been dormant for specified thresholds (1y, 2y, 5y)
    and are now being spent. Rising revived supply during rallies indicates
    LTH distribution to late buyers (bearish), while low revived supply during
    dips indicates LTH holding strong (bullish conviction).

    Key Signals:
    - Rising revived supply during rally: LTH distributing to late buyers
    - Low revived supply during dip: LTH holding strong
    - 5Y+ coins moving: Extremely rare, significant holder behavior shift
    - Sustained elevated zone: Distribution phase, potential trend reversal

    Spec: spec-024
    """

    # Revived BTC by dormancy threshold
    revived_1y: float  # BTC revived after 1+ year dormancy
    revived_2y: float  # BTC revived after 2+ year dormancy
    revived_5y: float  # BTC revived after 5+ year dormancy

    # Derived metrics
    revived_total_usd: float  # USD value of revived supply (using 1y threshold)
    revived_avg_age: float  # Average age of revived UTXOs (days)

    # Classification
    zone: RevivedZone  # Behavioral zone classification
    utxo_count: int  # Number of revived UTXOs

    # Context
    window_days: int  # Lookback window used
    current_price_usd: float  # Price for USD calculation
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    confidence: float = 0.85  # Default high confidence for Tier A metric

    def __post_init__(self):
        """Validate revived supply result fields."""
        # Revived values must be non-negative
        if self.revived_1y < 0:
            raise ValueError(f"revived_1y must be >= 0: {self.revived_1y}")
        if self.revived_2y < 0:
            raise ValueError(f"revived_2y must be >= 0: {self.revived_2y}")
        if self.revived_5y < 0:
            raise ValueError(f"revived_5y must be >= 0: {self.revived_5y}")

        # Hierarchy constraint: 5y <= 2y <= 1y
        if self.revived_5y > self.revived_2y:
            raise ValueError(
                f"revived_5y ({self.revived_5y}) cannot exceed revived_2y ({self.revived_2y})"
            )
        if self.revived_2y > self.revived_1y:
            raise ValueError(
                f"revived_2y ({self.revived_2y}) cannot exceed revived_1y ({self.revived_1y})"
            )

        # USD value must be non-negative
        if self.revived_total_usd < 0:
            raise ValueError(
                f"revived_total_usd must be >= 0: {self.revived_total_usd}"
            )

        # Average age must be non-negative
        if self.revived_avg_age < 0:
            raise ValueError(f"revived_avg_age must be >= 0: {self.revived_avg_age}")

        # Zone must be RevivedZone enum
        if not isinstance(self.zone, RevivedZone):
            raise ValueError(f"zone must be RevivedZone enum: {self.zone}")

        # UTXO count must be non-negative
        if self.utxo_count < 0:
            raise ValueError(f"utxo_count must be >= 0: {self.utxo_count}")

        # Window days must be positive
        if self.window_days <= 0:
            raise ValueError(f"window_days must be > 0: {self.window_days}")

        # Price must be positive
        if self.current_price_usd <= 0:
            raise ValueError(f"current_price_usd must be > 0: {self.current_price_usd}")

        # Block height must be non-negative
        if self.block_height < 0:
            raise ValueError(f"block_height must be >= 0: {self.block_height}")

        # Confidence must be in [0, 1]
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "revived_1y": self.revived_1y,
            "revived_2y": self.revived_2y,
            "revived_5y": self.revived_5y,
            "revived_total_usd": self.revived_total_usd,
            "revived_avg_age": self.revived_avg_age,
            "zone": self.zone.value,
            "utxo_count": self.utxo_count,
            "window_days": self.window_days,
            "current_price_usd": self.current_price_usd,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
            "confidence": self.confidence,
        }


# =============================================================================
# Spec-025: Wallet Waves & Absorption Rates Dataclasses
# =============================================================================


class WalletBand(str, Enum):
    """Wallet size classification bands.

    Standard 6-band classification aligned with industry standards (Glassnode/IntoTheBlock):
    - SHRIMP: < 1 BTC (sub-retail, casual holders)
    - CRAB: 1-10 BTC (retail accumulation target)
    - FISH: 10-100 BTC (high net worth individuals)
    - SHARK: 100-1,000 BTC (small institutions, funds)
    - WHALE: 1,000-10,000 BTC (major institutions)
    - HUMPBACK: > 10,000 BTC (exchanges, ETF custodians)

    Spec: spec-025
    """

    SHRIMP = "shrimp"
    CRAB = "crab"
    FISH = "fish"
    SHARK = "shark"
    WHALE = "whale"
    HUMPBACK = "humpback"


# Threshold constants for wallet band classification (min_btc, max_btc exclusive)
BAND_THRESHOLDS: dict[WalletBand, tuple[float, float]] = {
    WalletBand.SHRIMP: (0, 1),
    WalletBand.CRAB: (1, 10),
    WalletBand.FISH: (10, 100),
    WalletBand.SHARK: (100, 1000),
    WalletBand.WHALE: (1000, 10000),
    WalletBand.HUMPBACK: (10000, float("inf")),
}


@dataclass
class WalletBandMetrics:
    """Metrics for a single wallet band.

    Represents supply distribution within a specific wallet size range.

    Attributes:
        band: Wallet band classification (shrimp to humpback)
        supply_btc: Total BTC held by addresses in this band
        supply_pct: Percentage of total supply in this band (0-100)
        address_count: Number of addresses in this band
        avg_balance: Average balance per address in this band

    Spec: spec-025
    """

    band: WalletBand
    supply_btc: float
    supply_pct: float
    address_count: int
    avg_balance: float

    def __post_init__(self):
        """Validate wallet band metrics."""
        if self.supply_btc < 0:
            raise ValueError(f"supply_btc must be non-negative: {self.supply_btc}")
        if not 0 <= self.supply_pct <= 100:
            raise ValueError(f"supply_pct must be between 0 and 100: {self.supply_pct}")
        if self.address_count < 0:
            raise ValueError(
                f"address_count must be non-negative: {self.address_count}"
            )
        if self.avg_balance < 0:
            raise ValueError(f"avg_balance must be non-negative: {self.avg_balance}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "band": self.band.value,
            "supply_btc": self.supply_btc,
            "supply_pct": self.supply_pct,
            "address_count": self.address_count,
            "avg_balance": self.avg_balance,
        }


@dataclass
class WalletWavesResult:
    """Complete wallet waves distribution snapshot.

    Point-in-time snapshot of supply distribution across 6 wallet size bands.
    Used for HODL wave analysis and tracking retail vs institutional accumulation.

    Attributes:
        timestamp: When snapshot was calculated
        block_height: Bitcoin block height at calculation
        total_supply_btc: Total circulating supply (unspent)
        bands: List of 6 WalletBandMetrics (one per band)
        retail_supply_pct: Combined percentage for bands 1-3 (shrimp+crab+fish)
        institutional_supply_pct: Combined percentage for bands 4-6 (shark+whale+humpback)
        address_count_total: Total number of addresses with balance > 0
        null_address_btc: BTC in UTXOs without decoded address (OP_RETURN, etc)
        confidence: Data quality score (0.0-1.0)

    Spec: spec-025
    """

    timestamp: datetime
    block_height: int
    total_supply_btc: float
    bands: list  # list[WalletBandMetrics]
    retail_supply_pct: float
    institutional_supply_pct: float
    address_count_total: int
    null_address_btc: float
    confidence: float

    def __post_init__(self):
        """Validate wallet waves result."""
        if len(self.bands) != 6:
            raise ValueError(f"Must have exactly 6 bands, got {len(self.bands)}")
        if self.total_supply_btc <= 0:
            raise ValueError(
                f"total_supply_btc must be positive: {self.total_supply_btc}"
            )
        if self.block_height < 0:
            raise ValueError(f"block_height must be non-negative: {self.block_height}")
        if self.address_count_total < 0:
            raise ValueError(
                f"address_count_total must be non-negative: {self.address_count_total}"
            )
        if self.null_address_btc < 0:
            raise ValueError(
                f"null_address_btc must be non-negative: {self.null_address_btc}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")

        # Validate band percentages sum correctly (accounting for null addresses)
        # When null_address_btc > 0, bands won't sum to 100% - that's correct!
        band_sum = sum(b.supply_pct for b in self.bands)
        expected_sum = 100.0 * (1 - self.null_address_btc / self.total_supply_btc)
        tolerance = 1.0  # Allow ±1% for floating point
        if abs(band_sum - expected_sum) > tolerance:
            raise ValueError(
                f"Band percentages must sum to ~{expected_sum:.1f}% "
                f"(accounting for null addresses), got {band_sum:.2f}%"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
            "block_height": self.block_height,
            "total_supply_btc": self.total_supply_btc,
            "bands": [b.to_dict() for b in self.bands],
            "retail_supply_pct": self.retail_supply_pct,
            "institutional_supply_pct": self.institutional_supply_pct,
            "address_count_total": self.address_count_total,
            "null_address_btc": self.null_address_btc,
            "confidence": self.confidence,
        }


@dataclass
class AbsorptionRateMetrics:
    """Absorption rate for a single wallet band.

    Tracks how much of newly mined supply each wallet band has absorbed
    over a given time window.

    Attributes:
        band: Wallet band classification
        absorption_rate: Rate of new supply absorbed (0.0-1.0+), None if no historical data
        supply_delta_btc: Change in BTC held over window
        supply_start_btc: BTC held at window start
        supply_end_btc: BTC held at window end

    Spec: spec-025
    """

    band: WalletBand
    absorption_rate: Optional[float]  # None if no historical data
    supply_delta_btc: float
    supply_start_btc: float
    supply_end_btc: float

    def __post_init__(self):
        """Validate absorption rate metrics."""
        if self.absorption_rate is not None and self.absorption_rate < -10:
            raise ValueError(
                f"absorption_rate suspiciously negative: {self.absorption_rate}"
            )
        if self.supply_start_btc < 0:
            raise ValueError(
                f"supply_start_btc must be non-negative: {self.supply_start_btc}"
            )
        if self.supply_end_btc < 0:
            raise ValueError(
                f"supply_end_btc must be non-negative: {self.supply_end_btc}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "band": self.band.value,
            "absorption_rate": self.absorption_rate,
            "supply_delta_btc": self.supply_delta_btc,
            "supply_start_btc": self.supply_start_btc,
            "supply_end_btc": self.supply_end_btc,
        }


@dataclass
class AbsorptionRatesResult:
    """Absorption rates across all wallet bands.

    Tracks the rate at which each wallet band absorbs newly mined supply.
    Used to identify which cohorts are accumulating (conviction) vs distributing.

    Attributes:
        timestamp: When calculation was performed
        block_height: Bitcoin block height at calculation
        window_days: Lookback window in days (7, 30, 90)
        mined_supply_btc: New BTC mined during window
        bands: List of 6 AbsorptionRateMetrics (one per band)
        dominant_absorber: Band with highest absorption rate
        retail_absorption: Combined absorption for bands 1-3
        institutional_absorption: Combined absorption for bands 4-6
        confidence: Data quality score (0.0-1.0)
        has_historical_data: False if baseline snapshot unavailable

    Spec: spec-025
    """

    timestamp: datetime
    block_height: int
    window_days: int
    mined_supply_btc: float
    bands: list  # list[AbsorptionRateMetrics]
    dominant_absorber: WalletBand
    retail_absorption: float
    institutional_absorption: float
    confidence: float
    has_historical_data: bool

    def __post_init__(self):
        """Validate absorption rates result."""
        if len(self.bands) != 6:
            raise ValueError(f"Must have exactly 6 bands, got {len(self.bands)}")
        if self.window_days <= 0:
            raise ValueError(f"window_days must be positive: {self.window_days}")
        if self.mined_supply_btc < 0:
            raise ValueError(
                f"mined_supply_btc must be non-negative: {self.mined_supply_btc}"
            )
        if self.block_height < 0:
            raise ValueError(f"block_height must be non-negative: {self.block_height}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
            "block_height": self.block_height,
            "window_days": self.window_days,
            "mined_supply_btc": self.mined_supply_btc,
            "bands": [b.to_dict() for b in self.bands],
            "dominant_absorber": self.dominant_absorber.value,
            "retail_absorption": self.retail_absorption,
            "institutional_absorption": self.institutional_absorption,
            "confidence": self.confidence,
            "has_historical_data": self.has_historical_data,
        }


# =============================================================================
# Spec-026: Exchange Netflow Dataclasses
# =============================================================================


class NetflowZone(str, Enum):
    """Exchange netflow behavioral zone classification.

    Classifies daily netflow (inflow - outflow) into sentiment zones.
    Positive netflow = BTC flowing into exchanges (selling pressure).
    Negative netflow = BTC flowing out of exchanges (accumulation).

    Zone Thresholds (BTC/day):
    - STRONG_OUTFLOW: < -1000 (heavy accumulation, bullish)
    - WEAK_OUTFLOW: -1000 to 0 (mild accumulation, neutral-bullish)
    - WEAK_INFLOW: 0 to 1000 (mild selling, neutral-bearish)
    - STRONG_INFLOW: > 1000 (heavy selling pressure, bearish)

    Spec: spec-026
    """

    STRONG_OUTFLOW = "strong_outflow"
    WEAK_OUTFLOW = "weak_outflow"
    WEAK_INFLOW = "weak_inflow"
    STRONG_INFLOW = "strong_inflow"


@dataclass
class ExchangeNetflowResult:
    """Exchange netflow metrics for capital flow tracking.

    Tracks BTC movement to/from known exchange addresses to identify
    selling pressure vs accumulation. Primary indicator for exchange
    deposit/withdrawal behavior.

    Key Signals:
    - Positive netflow: BTC flowing into exchanges (selling pressure)
    - Negative netflow: BTC flowing out of exchanges (accumulation)
    - Rising 7d MA with positive netflow: Sustained selling
    - Falling 7d MA with negative netflow: Sustained accumulation

    Attributes:
        exchange_inflow: BTC flowing into exchanges (sell pressure)
        exchange_outflow: BTC flowing out of exchanges (accumulation)
        netflow: Inflow - Outflow (positive = selling, negative = accumulation)
        netflow_7d_ma: 7-day moving average of daily netflow
        netflow_30d_ma: 30-day moving average of daily netflow
        zone: Behavioral zone classification
        window_hours: Lookback window in hours (default 24)
        exchange_count: Number of exchanges in address dataset
        address_count: Number of exchange addresses matched
        current_price_usd: Price for USD value calculation
        inflow_usd: USD value of exchange inflow
        outflow_usd: USD value of exchange outflow
        block_height: Bitcoin block height at calculation
        timestamp: Calculation timestamp
        confidence: Data quality indicator (0.0-1.0), default 0.75 (B-C grade)

    Spec: spec-026
    """

    exchange_inflow: float
    exchange_outflow: float
    netflow: float
    netflow_7d_ma: float
    netflow_30d_ma: float

    zone: NetflowZone

    window_hours: int
    exchange_count: int
    address_count: int

    current_price_usd: float
    inflow_usd: float
    outflow_usd: float

    block_height: int
    timestamp: datetime
    confidence: float = 0.75  # B-C grade metric (limited address coverage)

    def __post_init__(self):
        """Validate field constraints."""
        # Inflow/outflow must be non-negative
        if self.exchange_inflow < 0:
            raise ValueError(f"exchange_inflow must be >= 0: {self.exchange_inflow}")
        if self.exchange_outflow < 0:
            raise ValueError(f"exchange_outflow must be >= 0: {self.exchange_outflow}")

        # USD values must be non-negative
        if self.inflow_usd < 0:
            raise ValueError(f"inflow_usd must be >= 0: {self.inflow_usd}")
        if self.outflow_usd < 0:
            raise ValueError(f"outflow_usd must be >= 0: {self.outflow_usd}")

        # Price must be positive (or zero if unavailable)
        if self.current_price_usd < 0:
            raise ValueError(
                f"current_price_usd must be >= 0: {self.current_price_usd}"
            )

        # Window must be positive
        if self.window_hours <= 0:
            raise ValueError(f"window_hours must be > 0: {self.window_hours}")

        # Counts must be non-negative
        if self.exchange_count < 0:
            raise ValueError(f"exchange_count must be >= 0: {self.exchange_count}")
        if self.address_count < 0:
            raise ValueError(f"address_count must be >= 0: {self.address_count}")

        # Block height must be non-negative
        if self.block_height < 0:
            raise ValueError(f"block_height must be >= 0: {self.block_height}")

        # Confidence must be in [0, 1]
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")

        # Zone must be NetflowZone enum
        if not isinstance(self.zone, NetflowZone):
            raise ValueError(f"zone must be NetflowZone enum: {self.zone}")

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        return {
            "exchange_inflow": self.exchange_inflow,
            "exchange_outflow": self.exchange_outflow,
            "netflow": self.netflow,
            "netflow_7d_ma": self.netflow_7d_ma,
            "netflow_30d_ma": self.netflow_30d_ma,
            "zone": self.zone.value,
            "window_hours": self.window_hours,
            "exchange_count": self.exchange_count,
            "address_count": self.address_count,
            "current_price_usd": self.current_price_usd,
            "inflow_usd": self.inflow_usd,
            "outflow_usd": self.outflow_usd,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
            "confidence": self.confidence,
        }


@dataclass
class BinaryCDDResult:
    """Binary CDD statistical significance result.

    Converts raw CDD (Coin Days Destroyed) into actionable binary signals
    based on z-score threshold exceeding N-sigma. Filters out noise from
    normal LTH activity.

    Key Signals:
    - binary_cdd=0: Normal long-term holder activity (noise)
    - binary_cdd=1: Significant event (z-score >= threshold sigma)

    Z-Score Interpretation:
    - < 2σ (97.5%): Normal noise, binary=0
    - >= 2σ (97.5%): Significant event, binary=1
    - >= 3σ (99.9%): Extreme event, binary=1 (high conviction)

    Attributes:
        cdd_today: Today's total Coin Days Destroyed
        cdd_mean: Mean CDD over lookback window
        cdd_std: Standard deviation of CDD over window
        cdd_zscore: Z-score (null if insufficient data or zero std)
        cdd_percentile: Percentile rank (0-100)
        binary_cdd: Binary flag (0 or 1)
        threshold_used: Sigma threshold applied
        window_days: Lookback window size
        data_points: Actual data points available
        insufficient_data: True if < 30 days history
        block_height: Block height at calculation
        timestamp: Calculation timestamp

    Spec: spec-027
    """

    cdd_today: float
    cdd_mean: float
    cdd_std: float
    cdd_zscore: Optional[float]
    cdd_percentile: Optional[float]
    binary_cdd: int  # 0 or 1
    threshold_used: float
    window_days: int
    data_points: int
    insufficient_data: bool
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate Binary CDD fields."""
        if self.cdd_today < 0:
            raise ValueError(f"cdd_today must be >= 0: {self.cdd_today}")
        if self.cdd_mean < 0:
            raise ValueError(f"cdd_mean must be >= 0: {self.cdd_mean}")
        if self.cdd_std < 0:
            raise ValueError(f"cdd_std must be >= 0: {self.cdd_std}")
        if self.cdd_percentile is not None and not 0 <= self.cdd_percentile <= 100:
            raise ValueError(
                f"cdd_percentile must be in [0, 100]: {self.cdd_percentile}"
            )
        if self.binary_cdd not in (0, 1):
            raise ValueError(f"binary_cdd must be 0 or 1: {self.binary_cdd}")
        if not 1.0 <= self.threshold_used <= 4.0:
            raise ValueError(
                f"threshold_used must be in [1.0, 4.0]: {self.threshold_used}"
            )
        if not 30 <= self.window_days <= 730:
            raise ValueError(f"window_days must be in [30, 730]: {self.window_days}")
        if self.data_points < 1:
            raise ValueError(f"data_points must be > 0: {self.data_points}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "cdd_today": self.cdd_today,
            "cdd_mean": self.cdd_mean,
            "cdd_std": self.cdd_std,
            "cdd_zscore": self.cdd_zscore,
            "cdd_percentile": self.cdd_percentile,
            "binary_cdd": self.binary_cdd,
            "threshold_used": self.threshold_used,
            "window_days": self.window_days,
            "data_points": self.data_points,
            "insufficient_data": self.insufficient_data,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
        }


# =============================================================================
# Spec-028: Net Realized Profit/Loss
# =============================================================================


@dataclass
class NetRealizedPnLResult:
    """
    Net Realized Profit/Loss metric result (spec-028).

    Aggregates realized gains/losses from spent UTXOs to show actual
    capital flows during the specified time window.

    Attributes:
        realized_profit_usd: Total profit realized (USD) from profitable UTXOs
        realized_loss_usd: Total loss realized (USD) from unprofitable UTXOs
        net_realized_pnl_usd: Net P/L = profit - loss
        realized_profit_btc: Profit in BTC terms (volume of profitable UTXOs)
        realized_loss_btc: Loss in BTC terms (volume of unprofitable UTXOs)
        net_realized_pnl_btc: Net BTC volume (profit - loss)
        profit_utxo_count: Number of UTXOs spent at profit
        loss_utxo_count: Number of UTXOs spent at loss
        profit_loss_ratio: Profit/Loss ratio (> 1 = profit dominant)
        signal: Interpretation (PROFIT_DOMINANT, LOSS_DOMINANT, NEUTRAL)
        window_hours: Time window for calculation
        timestamp: When metric was calculated
    """

    realized_profit_usd: float
    realized_loss_usd: float
    net_realized_pnl_usd: float
    realized_profit_btc: float
    realized_loss_btc: float
    net_realized_pnl_btc: float
    profit_utxo_count: int
    loss_utxo_count: int
    profit_loss_ratio: float
    signal: Literal["PROFIT_DOMINANT", "LOSS_DOMINANT", "NEUTRAL"]
    window_hours: int
    timestamp: datetime

    def __post_init__(self):
        """Validate field constraints."""
        if self.realized_profit_usd < 0:
            raise ValueError(
                f"realized_profit_usd must be >= 0: {self.realized_profit_usd}"
            )
        if self.realized_loss_usd < 0:
            raise ValueError(
                f"realized_loss_usd must be >= 0: {self.realized_loss_usd}"
            )
        if self.realized_profit_btc < 0:
            raise ValueError(
                f"realized_profit_btc must be >= 0: {self.realized_profit_btc}"
            )
        if self.realized_loss_btc < 0:
            raise ValueError(
                f"realized_loss_btc must be >= 0: {self.realized_loss_btc}"
            )
        if self.profit_utxo_count < 0:
            raise ValueError(
                f"profit_utxo_count must be >= 0: {self.profit_utxo_count}"
            )
        if self.loss_utxo_count < 0:
            raise ValueError(f"loss_utxo_count must be >= 0: {self.loss_utxo_count}")
        if self.profit_loss_ratio < 0:
            raise ValueError(
                f"profit_loss_ratio must be >= 0: {self.profit_loss_ratio}"
            )
        if self.window_hours < 1:
            raise ValueError(f"window_hours must be > 0: {self.window_hours}")
        if self.signal not in ("PROFIT_DOMINANT", "LOSS_DOMINANT", "NEUTRAL"):
            raise ValueError(f"Invalid signal: {self.signal}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "realized_profit_usd": self.realized_profit_usd,
            "realized_loss_usd": self.realized_loss_usd,
            "net_realized_pnl_usd": self.net_realized_pnl_usd,
            "realized_profit_btc": self.realized_profit_btc,
            "realized_loss_btc": self.realized_loss_btc,
            "net_realized_pnl_btc": self.net_realized_pnl_btc,
            "profit_utxo_count": self.profit_utxo_count,
            "loss_utxo_count": self.loss_utxo_count,
            "profit_loss_ratio": self.profit_loss_ratio,
            "signal": self.signal,
            "window_hours": self.window_hours,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
        }


@dataclass
class NetRealizedPnLHistoryPoint:
    """
    Single data point in Net Realized P/L history (spec-028).

    Used for daily aggregated P/L data for trend analysis.

    Attributes:
        date: Date for this data point
        realized_profit_usd: Total profit realized (USD)
        realized_loss_usd: Total loss realized (USD)
        net_realized_pnl_usd: Net P/L (profit - loss)
        profit_utxo_count: Number of UTXOs spent at profit
        loss_utxo_count: Number of UTXOs spent at loss
    """

    date: date
    realized_profit_usd: float
    realized_loss_usd: float
    net_realized_pnl_usd: float
    profit_utxo_count: int
    loss_utxo_count: int

    def __post_init__(self):
        """Validate field constraints."""
        if self.realized_profit_usd < 0:
            raise ValueError(
                f"realized_profit_usd must be >= 0: {self.realized_profit_usd}"
            )
        if self.realized_loss_usd < 0:
            raise ValueError(
                f"realized_loss_usd must be >= 0: {self.realized_loss_usd}"
            )
        if self.profit_utxo_count < 0:
            raise ValueError(
                f"profit_utxo_count must be >= 0: {self.profit_utxo_count}"
            )
        if self.loss_utxo_count < 0:
            raise ValueError(f"loss_utxo_count must be >= 0: {self.loss_utxo_count}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date.isoformat()
            if hasattr(self.date, "isoformat")
            else str(self.date),
            "realized_profit_usd": self.realized_profit_usd,
            "realized_loss_usd": self.realized_loss_usd,
            "net_realized_pnl_usd": self.net_realized_pnl_usd,
            "profit_utxo_count": self.profit_utxo_count,
            "loss_utxo_count": self.loss_utxo_count,
        }


# =============================================================================
# Spec-029: P/L Ratio (Dominance) Dataclasses
# =============================================================================


class PLDominanceZone(Enum):
    """
    Zone classification for P/L dominance metric (spec-029).

    Provides market regime interpretation based on P/L ratio and dominance values.
    Used for identifying market extremes (potential tops/bottoms).

    Thresholds:
        EXTREME_PROFIT: ratio > 5.0, dominance > 0.67 (euphoria, potential top)
        PROFIT: ratio 1.5-5.0, dominance 0.2-0.67 (healthy bull market)
        NEUTRAL: ratio 0.67-1.5, dominance -0.2-0.2 (equilibrium)
        LOSS: ratio 0.2-0.67, dominance -0.67--0.2 (bear market)
        EXTREME_LOSS: ratio < 0.2, dominance < -0.67 (capitulation, potential bottom)
    """

    EXTREME_PROFIT = "EXTREME_PROFIT"
    PROFIT = "PROFIT"
    NEUTRAL = "NEUTRAL"
    LOSS = "LOSS"
    EXTREME_LOSS = "EXTREME_LOSS"


@dataclass
class PLRatioResult:
    """
    P/L Ratio (Dominance) calculation result (spec-029).

    Derived from Net Realized P/L (spec-028) to provide ratio and normalized
    dominance metrics for market regime identification.

    Attributes:
        pl_ratio: Raw ratio (Profit / Loss), >= 0
        pl_dominance: Normalized (-1 to +1), (Profit - Loss) / (Profit + Loss)
        profit_dominant: True if ratio > 1
        dominance_zone: Zone classification for market regime
        realized_profit_usd: Source profit value from spec-028
        realized_loss_usd: Source loss value from spec-028
        window_hours: Time window for calculation (1-720)
        timestamp: When metric was calculated
    """

    pl_ratio: float
    pl_dominance: float
    profit_dominant: bool
    dominance_zone: PLDominanceZone
    realized_profit_usd: float
    realized_loss_usd: float
    window_hours: int
    timestamp: datetime

    def __post_init__(self):
        """Validate field constraints."""
        if self.pl_ratio < 0:
            raise ValueError(f"pl_ratio must be >= 0: {self.pl_ratio}")
        if not -1.0 <= self.pl_dominance <= 1.0:
            raise ValueError(f"pl_dominance must be in [-1, 1]: {self.pl_dominance}")
        if self.realized_profit_usd < 0:
            raise ValueError(
                f"realized_profit_usd must be >= 0: {self.realized_profit_usd}"
            )
        if self.realized_loss_usd < 0:
            raise ValueError(
                f"realized_loss_usd must be >= 0: {self.realized_loss_usd}"
            )
        if not 1 <= self.window_hours <= 720:
            raise ValueError(
                f"window_hours must be between 1 and 720: {self.window_hours}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "pl_ratio": self.pl_ratio,
            "pl_dominance": self.pl_dominance,
            "profit_dominant": self.profit_dominant,
            "dominance_zone": self.dominance_zone.value,
            "realized_profit_usd": self.realized_profit_usd,
            "realized_loss_usd": self.realized_loss_usd,
            "window_hours": self.window_hours,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
        }


@dataclass
class PLRatioHistoryPoint:
    """
    Single data point in P/L Ratio history (spec-029).

    Used for daily aggregated P/L ratio data for trend analysis.

    Attributes:
        date: Date for this data point
        pl_ratio: Raw ratio for the day (>= 0)
        pl_dominance: Normalized dominance (-1 to +1)
        dominance_zone: Zone classification
        realized_profit_usd: Daily profit (USD)
        realized_loss_usd: Daily loss (USD)
    """

    date: date
    pl_ratio: float
    pl_dominance: float
    dominance_zone: PLDominanceZone
    realized_profit_usd: float
    realized_loss_usd: float

    def __post_init__(self):
        """Validate field constraints."""
        if self.pl_ratio < 0:
            raise ValueError(f"pl_ratio must be >= 0: {self.pl_ratio}")
        if not -1.0 <= self.pl_dominance <= 1.0:
            raise ValueError(f"pl_dominance must be in [-1, 1]: {self.pl_dominance}")
        if self.realized_profit_usd < 0:
            raise ValueError(
                f"realized_profit_usd must be >= 0: {self.realized_profit_usd}"
            )
        if self.realized_loss_usd < 0:
            raise ValueError(
                f"realized_loss_usd must be >= 0: {self.realized_loss_usd}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date.isoformat()
            if hasattr(self.date, "isoformat")
            else str(self.date),
            "pl_ratio": self.pl_ratio,
            "pl_dominance": self.pl_dominance,
            "dominance_zone": self.dominance_zone.value,
            "realized_profit_usd": self.realized_profit_usd,
            "realized_loss_usd": self.realized_loss_usd,
        }


# =============================================================================
# Spec-030: Mining Economics (Hash Ribbons + Mining Pulse)
# =============================================================================


class MiningPulseZone(str, Enum):
    """Classification of mining network status based on block intervals (spec-030).

    Determines network hashrate trend from average block interval:
    - FAST: Hashrate increasing (blocks found faster than expected)
    - NORMAL: Stable mining conditions
    - SLOW: Hashrate decreasing or difficulty spike
    """

    FAST = "FAST"  # Avg interval < 540s (-10% from 600s target)
    NORMAL = "NORMAL"  # Avg interval 540-660s (±10% from target)
    SLOW = "SLOW"  # Avg interval > 660s (+10% from target)


@dataclass
class HashRibbonsResult:
    """Hash Ribbons miner stress indicator (spec-030).

    Detects miner capitulation/recovery via 30d/60d MA crossovers:
    - ribbon_signal=True: 30d MA < 60d MA (miner stress active)
    - recovery_signal=True: Just crossed back up (bullish)

    Signal Interpretation:
    - No ribbon: Normal mining, no stress
    - Ribbon < 7 days: Early miner stress, watch
    - Ribbon 7-30 days: Confirmed capitulation
    - Ribbon > 30 days: Extended stress, potential bottom
    - Recovery: Miners recovering, bullish signal

    Attributes:
        hashrate_current: Current network hashrate (EH/s)
        hashrate_ma_30d: 30-day moving average hashrate (EH/s)
        hashrate_ma_60d: 60-day moving average hashrate (EH/s)
        ribbon_signal: True if 30d < 60d (miner stress active)
        capitulation_days: Consecutive days in stress state
        recovery_signal: True if just crossed back up
        data_source: "api" or "difficulty_estimated"
        timestamp: Calculation timestamp

    Spec: spec-030
    """

    hashrate_current: float  # EH/s
    hashrate_ma_30d: float  # EH/s
    hashrate_ma_60d: float  # EH/s
    ribbon_signal: bool
    capitulation_days: int
    recovery_signal: bool
    data_source: str  # "api" | "difficulty_estimated"
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate Hash Ribbons fields."""
        if self.hashrate_current < 0:
            raise ValueError(f"hashrate_current must be >= 0: {self.hashrate_current}")
        if self.hashrate_ma_30d < 0:
            raise ValueError(f"hashrate_ma_30d must be >= 0: {self.hashrate_ma_30d}")
        if self.hashrate_ma_60d < 0:
            raise ValueError(f"hashrate_ma_60d must be >= 0: {self.hashrate_ma_60d}")
        if self.capitulation_days < 0:
            raise ValueError(
                f"capitulation_days must be >= 0: {self.capitulation_days}"
            )
        if self.data_source not in ("api", "difficulty_estimated"):
            raise ValueError(
                f"data_source must be 'api' or 'difficulty_estimated': {self.data_source}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "hashrate_current": self.hashrate_current,
            "hashrate_ma_30d": self.hashrate_ma_30d,
            "hashrate_ma_60d": self.hashrate_ma_60d,
            "ribbon_signal": self.ribbon_signal,
            "capitulation_days": self.capitulation_days,
            "recovery_signal": self.recovery_signal,
            "data_source": self.data_source,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
        }


@dataclass
class MiningPulseResult:
    """Mining Pulse real-time hashrate indicator (spec-030).

    Analyzes block intervals to detect hashrate changes before
    difficulty adjusts. Works RPC-only, no external dependencies.

    Pulse Zones:
    - FAST (< 540s avg): Hashrate increasing rapidly
    - NORMAL (540-660s avg): Stable mining
    - SLOW (> 660s avg): Hashrate dropping or difficulty spike

    Attributes:
        avg_block_interval: Average interval (seconds)
        interval_deviation_pct: Deviation from 600s target (%)
        blocks_fast: Blocks < 600s in window
        blocks_slow: Blocks >= 600s in window
        implied_hashrate_change: Inferred % hashrate delta
        pulse_zone: FAST | NORMAL | SLOW classification
        window_blocks: Number of blocks analyzed
        tip_height: Current block height
        timestamp: Calculation timestamp

    Spec: spec-030
    """

    avg_block_interval: float  # seconds
    interval_deviation_pct: float  # percentage
    blocks_fast: int
    blocks_slow: int
    implied_hashrate_change: float  # percentage
    pulse_zone: MiningPulseZone
    window_blocks: int
    tip_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate Mining Pulse fields."""
        if self.avg_block_interval <= 0:
            raise ValueError(
                f"avg_block_interval must be > 0: {self.avg_block_interval}"
            )
        if not -50 <= self.interval_deviation_pct <= 100:
            raise ValueError(
                f"interval_deviation_pct must be in [-50, 100]: {self.interval_deviation_pct}"
            )
        if self.blocks_fast < 0:
            raise ValueError(f"blocks_fast must be >= 0: {self.blocks_fast}")
        if self.blocks_slow < 0:
            raise ValueError(f"blocks_slow must be >= 0: {self.blocks_slow}")
        if self.window_blocks < 2:
            raise ValueError(f"window_blocks must be >= 2: {self.window_blocks}")
        if self.tip_height <= 0:
            raise ValueError(f"tip_height must be > 0: {self.tip_height}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "avg_block_interval": self.avg_block_interval,
            "interval_deviation_pct": self.interval_deviation_pct,
            "blocks_fast": self.blocks_fast,
            "blocks_slow": self.blocks_slow,
            "implied_hashrate_change": self.implied_hashrate_change,
            "pulse_zone": self.pulse_zone.value,
            "window_blocks": self.window_blocks,
            "tip_height": self.tip_height,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
        }


@dataclass
class MiningEconomicsResult:
    """Combined mining economics view (spec-030).

    Aggregates Hash Ribbons (external API) and Mining Pulse (RPC-only)
    into a unified signal for miner health assessment.

    Combined Signal Logic:
    - "recovery": Ribbons show recovery signal (bullish)
    - "miner_stress": Ribbons active 7+ days OR pulse zone SLOW
    - "healthy": Pulse FAST or no stress indicators
    - "unknown": No ribbon data available

    Attributes:
        hash_ribbons: Hash Ribbons analysis (None if API unavailable)
        mining_pulse: Mining Pulse analysis (always available via RPC)
        combined_signal: Aggregated interpretation
        timestamp: Calculation timestamp

    Spec: spec-030
    """

    hash_ribbons: Optional[HashRibbonsResult]
    mining_pulse: MiningPulseResult
    combined_signal: str  # "miner_stress" | "recovery" | "healthy" | "unknown"
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate Mining Economics fields."""
        valid_signals = ("miner_stress", "recovery", "healthy", "unknown")
        if self.combined_signal not in valid_signals:
            raise ValueError(
                f"combined_signal must be one of {valid_signals}: {self.combined_signal}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "hash_ribbons": self.hash_ribbons.to_dict() if self.hash_ribbons else None,
            "mining_pulse": self.mining_pulse.to_dict(),
            "combined_signal": self.combined_signal,
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
        }


# =============================================================================
# Address Balance Cohorts (spec-039)
# =============================================================================


class AddressCohort(Enum):
    """Address balance cohort classification.

    Three-tier structure aligned with whale detection thresholds:
    - RETAIL: Small holders (< 1 BTC)
    - MID_TIER: Affluent individuals (1-100 BTC)
    - WHALE: Institutions/Funds (>= 100 BTC)

    The 100 BTC whale threshold aligns with spec-004, spec-005.
    Spec: spec-039
    """

    RETAIL = "retail"  # < 1 BTC
    MID_TIER = "mid_tier"  # 1-100 BTC
    WHALE = "whale"  # >= 100 BTC


@dataclass
class CohortMetrics:
    """Metrics for a single address balance cohort.

    Per-cohort aggregation of cost basis, supply, and MVRV.
    Cost basis uses same methodology as spec-023 (weighted average).

    Attributes:
        cohort: Enum value for type safety
        cost_basis: Weighted avg acquisition price (SUM(price*btc)/SUM(btc))
        supply_btc: Total BTC held by this cohort
        supply_pct: Percentage of total supply held
        mvrv: Market value to realized value (current_price / cost_basis)
        address_count: Number of unique addresses in cohort

    Spec: spec-039
    """

    cohort: AddressCohort
    cost_basis: float
    supply_btc: float
    supply_pct: float
    mvrv: float
    address_count: int

    def __post_init__(self):
        """Validate cohort metrics fields."""
        if self.cost_basis < 0:
            raise ValueError(f"cost_basis must be >= 0: {self.cost_basis}")
        if self.supply_btc < 0:
            raise ValueError(f"supply_btc must be >= 0: {self.supply_btc}")
        if not 0 <= self.supply_pct <= 100:
            raise ValueError(f"supply_pct must be 0-100: {self.supply_pct}")
        if self.mvrv < 0:
            raise ValueError(f"mvrv must be >= 0: {self.mvrv}")
        if self.address_count < 0:
            raise ValueError(f"address_count must be >= 0: {self.address_count}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "cohort": self.cohort.value,
            "cost_basis": self.cost_basis,
            "supply_btc": self.supply_btc,
            "supply_pct": self.supply_pct,
            "mvrv": self.mvrv,
            "address_count": self.address_count,
        }


@dataclass
class AddressCohortsResult:
    """Complete address cohorts analysis result.

    Combines per-cohort metrics with cross-cohort analysis signals.
    Reveals accumulation/distribution patterns and conviction levels.

    Cross-Cohort Signals:
    - whale_retail_spread > 0: Whales bought higher (retail has better basis)
    - whale_retail_spread < 0: Whales bought lower (whales have conviction)
    - whale_retail_mvrv_ratio < 1: Whales more profitable than retail

    Attributes:
        timestamp: When analysis was performed
        block_height: Bitcoin block height at calculation time
        current_price_usd: Price used for MVRV calculations
        retail: Metrics for retail cohort (< 1 BTC)
        mid_tier: Metrics for mid-tier cohort (1-100 BTC)
        whale: Metrics for whale cohort (>= 100 BTC)
        whale_retail_spread: whale_cost_basis - retail_cost_basis
        whale_retail_mvrv_ratio: whale_mvrv / retail_mvrv
        total_supply_btc: Sum of all cohort supplies
        total_addresses: Sum of all cohort address counts

    Spec: spec-039
    """

    timestamp: datetime
    block_height: int
    current_price_usd: float
    retail: CohortMetrics
    mid_tier: CohortMetrics
    whale: CohortMetrics
    whale_retail_spread: float
    whale_retail_mvrv_ratio: float
    total_supply_btc: float
    total_addresses: int

    def __post_init__(self):
        """Validate address cohorts result fields."""
        if self.current_price_usd <= 0:
            raise ValueError(f"current_price_usd must be > 0: {self.current_price_usd}")
        if self.total_supply_btc < 0:
            raise ValueError(f"total_supply_btc must be >= 0: {self.total_supply_btc}")
        if self.total_addresses < 0:
            raise ValueError(f"total_addresses must be >= 0: {self.total_addresses}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
            "block_height": self.block_height,
            "current_price_usd": self.current_price_usd,
            "cohorts": {
                "retail": self.retail.to_dict(),
                "mid_tier": self.mid_tier.to_dict(),
                "whale": self.whale.to_dict(),
            },
            "analysis": {
                "whale_retail_spread": self.whale_retail_spread,
                "whale_retail_mvrv_ratio": self.whale_retail_mvrv_ratio,
            },
            "total_supply_btc": self.total_supply_btc,
            "total_addresses": self.total_addresses,
        }
