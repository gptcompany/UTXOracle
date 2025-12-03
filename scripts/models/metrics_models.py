"""
Data models for on-chain metrics (spec-007).

These dataclasses mirror the DuckDB `metrics` table schema and provide
type-safe data transfer between calculation modules and storage/API.
"""

from dataclasses import dataclass
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
