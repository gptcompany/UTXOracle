from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict

from pydantic import BaseModel, Field


class PriceEntry(BaseModel):
    """Single price comparison entry"""

    timestamp: str
    utxoracle_price: Optional[float] = None
    mempool_price: Optional[float] = None
    confidence: float
    tx_count: Optional[int] = None
    fetch_tier: Optional[int] = None
    diff_amount: Optional[float] = None
    diff_percent: Optional[float] = None
    is_valid: bool


class ComparisonStats(BaseModel):
    """Statistical comparison metrics"""

    avg_diff: Optional[float] = None
    max_diff: Optional[float] = None
    min_diff: Optional[float] = None
    avg_diff_percent: Optional[float] = None
    total_entries: int
    valid_entries: int
    timeframe_days: int = 7


class MonteCarloFusionResponse(BaseModel):
    """Monte Carlo signal fusion result."""

    signal_mean: float = Field(..., description="Mean of bootstrap samples")
    signal_std: float = Field(..., description="Standard deviation of samples")
    ci_lower: float = Field(..., description="95% CI lower bound")
    ci_upper: float = Field(..., description="95% CI upper bound")
    action: str = Field(..., description="Recommended action: BUY/SELL/HOLD")
    action_confidence: float = Field(..., description="Confidence in action")
    n_samples: int = Field(default=1000, description="Bootstrap iterations")
    distribution_type: str = Field(default="unimodal", description="unimodal/bimodal")


class ActiveAddressesResponse(BaseModel):
    """Active addresses metric."""

    block_height: int = Field(..., description="Bitcoin block height")
    active_addresses_block: int = Field(..., description="Unique addresses in block")
    active_addresses_24h: Optional[int] = Field(
        None, description="24h unique addresses"
    )
    unique_senders: int = Field(..., description="Unique senders")
    unique_receivers: int = Field(..., description="Unique receivers")
    is_anomaly: bool = Field(default=False, description="Anomaly detected")


class TxVolumeResponse(BaseModel):
    """Transaction volume metric."""

    tx_count: int = Field(..., description="Transaction count")
    tx_volume_btc: float = Field(..., description="Volume in BTC")
    tx_volume_usd: Optional[float] = Field(None, description="Volume in USD")
    utxoracle_price_used: Optional[float] = Field(None, description="Price used")
    low_confidence: bool = Field(default=False, description="Low confidence flag")


class MetricsLatestResponse(BaseModel):
    """Combined metrics response for /api/metrics/latest."""

    timestamp: datetime = Field(..., description="Metrics timestamp")
    monte_carlo: Optional[MonteCarloFusionResponse] = Field(
        None, description="Signal fusion"
    )
    active_addresses: Optional[ActiveAddressesResponse] = Field(
        None, description="Address metrics"
    )
    tx_volume: Optional[TxVolumeResponse] = Field(None, description="Volume metrics")


# =============================================================================
# Wave 1 (spec-046) Promoted Models
# =============================================================================

class CohortMetricsResponse(BaseModel):
    cohort: str
    cost_basis: float
    supply_btc: float
    supply_pct: float
    mvrv: float
    address_count: int


class AddressCohortsResponse(BaseModel):
    timestamp: datetime
    block_height: int
    current_price_usd: float
    cohorts: Dict[str, CohortMetricsResponse]
    whale_retail_spread: float
    whale_retail_mvrv_ratio: float
    total_supply_btc: float
    total_addresses: int


class CostBasisResponse(BaseModel):
    timestamp: datetime
    block_height: int
    current_price_usd: float
    total_cost_basis: float
    sth_cost_basis: float
    lth_cost_basis: float
    sth_mvrv: float
    lth_mvrv: float
    sth_supply_btc: float
    lth_supply_btc: float
    confidence: float


class URPDFeaturesResponse(BaseModel):
    timestamp: datetime
    block_height: int
    current_price_usd: float
    bucket_size_usd: float
    total_supply_btc: float
    supply_below_price_pct: float
    supply_above_price_pct: float
    top_bucket_concentration: float
    dominant_bucket_distance_pct: float
    distribution_entropy: float
    confidence: float


class WalletBandMetricsResponse(BaseModel):
    band: str
    supply_btc: float
    supply_pct: float
    address_count: int
    avg_balance: float


class WalletWavesResponse(BaseModel):
    timestamp: datetime
    block_height: int
    total_supply_btc: float
    bands: List[WalletBandMetricsResponse]
    retail_supply_pct: float
    institutional_supply_pct: float
    address_count_total: int
    null_address_btc: float
    confidence: float


class AbsorptionRateMetricsResponse(BaseModel):
    band: str
    absorption_rate: Optional[float]
    supply_delta_btc: float
    supply_start_btc: float
    supply_end_btc: float


class AbsorptionRatesResponse(BaseModel):
    timestamp: datetime
    block_height: int
    window_days: int
    mined_supply_btc: float
    bands: List[AbsorptionRateMetricsResponse]
    dominant_absorber: str
    retail_absorption: float
    institutional_absorption: float
    confidence: float
    has_historical_data: bool


# =============================================================================
# Research & Operations (spec-003 Hardening)
# =============================================================================

class TierStats(BaseModel):
    """Observability for fetch tiers."""
    tier: int
    count: int
    percentage: float


class TierObservabilityResponse(BaseModel):
    """Response for /api/research/tier-stats."""
    timeframe_days: int
    total_samples: int
    stats: List[TierStats]
    last_tier_used: Optional[int] = None
