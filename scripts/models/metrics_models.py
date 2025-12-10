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
from datetime import datetime
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

    # Component weights (updated for 9 components, sum = 1.0)
    # Rebalanced: whale 0.23→0.21, utxo 0.14→0.12, funding 0.14→0.12
    # symbolic 0.14→0.12, oi/power_law/fractal/wasserstein unchanged
    # Added cointime 0.12
    whale_weight: float = 0.21
    utxo_weight: float = 0.12
    funding_weight: float = 0.12
    oi_weight: float = 0.09
    power_law_weight: float = 0.09
    symbolic_weight: float = 0.12
    fractal_weight: float = 0.09
    wasserstein_weight: float = 0.04  # spec-010 (reduced from 0.08)
    cointime_weight: float = 0.12  # spec-018

    # Metadata
    components_available: int = 0
    components_used: list = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

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
