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
    Result of enhanced Monte Carlo signal fusion with 8 components.

    Extends spec-007 MonteCarloFusionResult with:
    - Power Law vote (spec-009)
    - Symbolic Dynamics vote (spec-009)
    - Fractal Dimension vote (spec-009)
    - Funding Rate vote (spec-008)
    - Open Interest vote (spec-008)
    - Wasserstein vote (spec-010)
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

    # Component weights (updated for 8 components, sum = 1.0)
    whale_weight: float = 0.23
    utxo_weight: float = 0.14
    funding_weight: float = 0.14
    oi_weight: float = 0.09
    power_law_weight: float = 0.09
    symbolic_weight: float = 0.14
    fractal_weight: float = 0.09
    wasserstein_weight: float = 0.08  # spec-010

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
# Spec-016: SOPR STH/LTH Dataclasses
# =============================================================================


@dataclass
class SOPRResult:
    """
    Spent Output Profit Ratio (SOPR) calculation result.

    SOPR = realized_value / spent_value
    - SOPR > 1: Holders selling at profit
    - SOPR = 1: Selling at cost basis
    - SOPR < 1: Holders selling at loss

    Attributes:
        sopr: Overall SOPR value
        sopr_sth: Short-term holder SOPR (age < 155 days)
        sopr_lth: Long-term holder SOPR (age >= 155 days)
        sample_count: Number of spent outputs analyzed
        sth_count: Number of STH outputs
        lth_count: Number of LTH outputs
        is_valid: True if sufficient samples
    """

    sopr: float
    sopr_sth: Optional[float] = None
    sopr_lth: Optional[float] = None
    sample_count: int = 0
    sth_count: int = 0
    lth_count: int = 0
    is_valid: bool = True
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "sopr": self.sopr,
            "sopr_sth": self.sopr_sth,
            "sopr_lth": self.sopr_lth,
            "sample_count": self.sample_count,
            "sth_count": self.sth_count,
            "lth_count": self.lth_count,
            "is_valid": self.is_valid,
        }


# =============================================================================
# Spec-017: UTXO Lifecycle Engine Dataclasses
# =============================================================================


@dataclass
class UTXOLifecycle:
    """
    Complete lifecycle record for a single UTXO.

    Tracks creation, spending, and derived metrics like age and SOPR.
    This is the foundation for Tier A metrics (MVRV, Realized Cap, HODL Waves).

    Attributes:
        outpoint: Unique identifier "{txid}:{vout_index}"
        txid: Transaction ID that created this UTXO
        vout_index: Output index within the transaction

        creation_block: Block height when UTXO was created
        creation_timestamp: Block timestamp when created
        creation_price_usd: UTXOracle price at creation time
        btc_value: BTC amount in this UTXO
        realized_value_usd: btc_value × creation_price

        spent_block: Block height when spent (None if unspent)
        spent_timestamp: Block timestamp when spent
        spent_price_usd: UTXOracle price at spend time
        spending_txid: Transaction that spent this UTXO

        age_blocks: Age in blocks (current or at spend)
        age_days: Age in days (current or at spend)
        cohort: "STH" or "LTH"
        sub_cohort: Age band ("<1d", "1d-1w", etc.)
        sopr: Spent Output Profit Ratio (None if unspent)

        is_coinbase: True if from coinbase transaction
        is_spent: True if UTXO has been spent
        price_source: "utxoracle" or "mempool" (fallback)
    """

    # Identity
    outpoint: str
    txid: str
    vout_index: int

    # Creation
    creation_block: int
    creation_timestamp: datetime
    creation_price_usd: float
    btc_value: float
    realized_value_usd: float

    # Spending (None if unspent)
    spent_block: Optional[int] = None
    spent_timestamp: Optional[datetime] = None
    spent_price_usd: Optional[float] = None
    spending_txid: Optional[str] = None

    # Derived
    age_blocks: Optional[int] = None
    age_days: Optional[int] = None
    cohort: str = ""
    sub_cohort: str = ""
    sopr: Optional[float] = None

    # Metadata
    is_coinbase: bool = False
    is_spent: bool = False
    price_source: str = "utxoracle"

    def __post_init__(self):
        """Validate and compute derived fields."""
        if self.btc_value < 0:
            raise ValueError(f"btc_value must be >= 0: {self.btc_value}")
        if self.creation_price_usd < 0:
            raise ValueError(
                f"creation_price_usd must be >= 0: {self.creation_price_usd}"
            )

    def mark_spent(
        self,
        spent_block: int,
        spent_timestamp: datetime,
        spent_price_usd: float,
        spending_txid: str,
        blocks_per_day: int = 144,
    ) -> None:
        """Mark this UTXO as spent and calculate derived metrics."""
        self.spent_block = spent_block
        self.spent_timestamp = spent_timestamp
        self.spent_price_usd = spent_price_usd
        self.spending_txid = spending_txid
        self.is_spent = True

        # Calculate age
        self.age_blocks = spent_block - self.creation_block
        self.age_days = self.age_blocks // blocks_per_day

        # Calculate SOPR
        if self.creation_price_usd > 0:
            self.sopr = spent_price_usd / self.creation_price_usd

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "outpoint": self.outpoint,
            "txid": self.txid,
            "vout_index": self.vout_index,
            "creation_block": self.creation_block,
            "creation_timestamp": self.creation_timestamp.isoformat()
            if self.creation_timestamp
            else None,
            "creation_price_usd": self.creation_price_usd,
            "btc_value": self.btc_value,
            "realized_value_usd": self.realized_value_usd,
            "spent_block": self.spent_block,
            "spent_timestamp": self.spent_timestamp.isoformat()
            if self.spent_timestamp
            else None,
            "spent_price_usd": self.spent_price_usd,
            "age_days": self.age_days,
            "cohort": self.cohort,
            "sub_cohort": self.sub_cohort,
            "sopr": self.sopr,
            "is_coinbase": self.is_coinbase,
            "is_spent": self.is_spent,
        }


@dataclass
class UTXOSetSnapshot:
    """
    Point-in-time snapshot of UTXO set metrics.

    Created periodically (e.g., daily) to track supply distribution
    and realized metrics over time.

    Attributes:
        block_height: Block height of this snapshot
        timestamp: Block timestamp

        total_supply_btc: Total BTC in unspent UTXOs
        sth_supply_btc: BTC held by short-term holders (< 155 days)
        lth_supply_btc: BTC held by long-term holders (>= 155 days)
        supply_by_cohort: BTC by age cohort

        realized_cap_usd: Sum of (btc_value × creation_price) for all UTXOs
        market_cap_usd: total_supply × current_price
        mvrv: Market Cap / Realized Cap
        nupl: (Market Cap - Realized Cap) / Market Cap

        hodl_waves: Percentage of supply by age cohort
    """

    block_height: int
    timestamp: datetime

    # Supply Distribution
    total_supply_btc: float
    sth_supply_btc: float
    lth_supply_btc: float
    supply_by_cohort: dict

    # Realized Metrics
    realized_cap_usd: float
    market_cap_usd: float
    mvrv: float
    nupl: float

    # HODL Waves (cohort -> % of supply)
    hodl_waves: dict

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
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
    """
    Configuration for UTXO age cohort classification.

    Standard cohorts follow industry convention:
    - STH (Short-Term Holder): < 155 days
    - LTH (Long-Term Holder): >= 155 days

    Sub-cohorts for HODL Waves visualization:
    - <1d, 1d-1w, 1w-1m, 1m-3m, 3m-6m (STH bands)
    - 6m-1y, 1y-2y, 2y-3y, 3y-5y, >5y (LTH bands)
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

    def classify(self, age_days: int) -> tuple:
        """
        Classify UTXO by age into cohort and sub-cohort.

        Args:
            age_days: UTXO age in days.

        Returns:
            Tuple of (cohort, sub_cohort) where cohort is "STH" or "LTH"
            and sub_cohort is the specific age band.
        """
        # B5 fix: Guard against negative age_days (defensive for invalid data)
        if age_days < 0:
            return "STH", "<1d"

        cohort = "STH" if age_days < self.sth_threshold_days else "LTH"

        for name, min_days, max_days in self.cohorts:
            if min_days <= age_days < max_days:
                return cohort, name

        return cohort, ">5y"


@dataclass
class SyncState:
    """
    Tracks sync progress for incremental UTXO updates.

    Allows resuming sync from last processed block without full rescan.

    Attributes:
        last_processed_block: Most recent block fully processed
        last_processed_timestamp: Timestamp of that block
        total_utxos_created: Cumulative UTXOs created
        total_utxos_spent: Cumulative UTXOs spent
        sync_started: When current sync session began
        sync_duration_seconds: Total sync time so far
    """

    last_processed_block: int
    last_processed_timestamp: datetime
    total_utxos_created: int
    total_utxos_spent: int
    sync_started: datetime = field(default_factory=datetime.utcnow)
    sync_duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "last_processed_block": self.last_processed_block,
            "last_processed_timestamp": self.last_processed_timestamp.isoformat()
            if self.last_processed_timestamp
            else None,
            "total_utxos_created": self.total_utxos_created,
            "total_utxos_spent": self.total_utxos_spent,
            "sync_started": self.sync_started.isoformat()
            if self.sync_started
            else None,
            "sync_duration_seconds": self.sync_duration_seconds,
        }
