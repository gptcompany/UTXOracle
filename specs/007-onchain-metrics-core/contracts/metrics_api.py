"""
API Contracts for On-Chain Metrics (spec-007).

Pydantic models defining the REST API request/response schemas
for the /api/metrics/* endpoints.

These contracts serve as the source of truth for:
- API documentation (auto-generated OpenAPI/Swagger)
- Request validation
- Response serialization
- Client SDK generation (if needed)
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Response Models
# =============================================================================


class MonteCarloFusionResponse(BaseModel):
    """Monte Carlo signal fusion result."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "signal_mean": 0.75,
                "signal_std": 0.12,
                "ci_lower": 0.52,
                "ci_upper": 0.91,
                "action": "BUY",
                "action_confidence": 0.85,
                "n_samples": 1000,
                "distribution_type": "unimodal",
            }
        }
    )

    signal_mean: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Mean of bootstrap samples, range [-1, 1]",
    )
    signal_std: float = Field(
        ...,
        ge=0.0,
        description="Standard deviation of bootstrap samples",
    )
    ci_lower: float = Field(
        ...,
        description="95% confidence interval lower bound",
    )
    ci_upper: float = Field(
        ...,
        description="95% confidence interval upper bound",
    )
    action: Literal["BUY", "SELL", "HOLD"] = Field(
        ...,
        description="Recommended trading action based on signal",
    )
    action_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Probability that recommended action is correct",
    )
    n_samples: int = Field(
        default=1000,
        description="Number of bootstrap iterations performed",
    )
    distribution_type: Literal["unimodal", "bimodal", "insufficient_data"] = Field(
        default="unimodal",
        description="Shape of signal distribution",
    )


class ActiveAddressesResponse(BaseModel):
    """Active addresses metric response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "block_height": 870000,
                "active_addresses_block": 45230,
                "active_addresses_24h": 892145,
                "unique_senders": 23456,
                "unique_receivers": 34567,
                "is_anomaly": False,
            }
        }
    )

    block_height: int = Field(
        ...,
        description="Bitcoin block height",
    )
    active_addresses_block: int = Field(
        ...,
        ge=0,
        description="Unique addresses active in single block",
    )
    active_addresses_24h: Optional[int] = Field(
        default=None,
        ge=0,
        description="Unique addresses active in last 24 hours",
    )
    unique_senders: int = Field(
        ...,
        ge=0,
        description="Unique addresses in transaction inputs",
    )
    unique_receivers: int = Field(
        ...,
        ge=0,
        description="Unique addresses in transaction outputs",
    )
    is_anomaly: bool = Field(
        default=False,
        description="True if count exceeds 3σ from 30-day moving average",
    )


class TxVolumeResponse(BaseModel):
    """Transaction volume metric response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tx_count": 2847,
                "tx_volume_btc": 15234.56,
                "tx_volume_usd": 1523456000.0,
                "utxoracle_price_used": 100000.0,
                "low_confidence": False,
            }
        }
    )

    tx_count: int = Field(
        ...,
        ge=0,
        description="Number of transactions in period",
    )
    tx_volume_btc: float = Field(
        ...,
        ge=0.0,
        description="Total BTC transferred (adjusted for change outputs)",
    )
    tx_volume_usd: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="USD equivalent (null if UTXOracle price unavailable)",
    )
    utxoracle_price_used: Optional[float] = Field(
        default=None,
        description="UTXOracle price used for BTC→USD conversion",
    )
    low_confidence: bool = Field(
        default=False,
        description="True if UTXOracle confidence was below 0.3",
    )


class MetricsLatestResponse(BaseModel):
    """
    Combined response for /api/metrics/latest endpoint.

    Returns all three metrics for the most recent timestamp.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2025-12-03T14:30:00Z",
                "monte_carlo": {
                    "signal_mean": 0.75,
                    "signal_std": 0.12,
                    "ci_lower": 0.52,
                    "ci_upper": 0.91,
                    "action": "BUY",
                    "action_confidence": 0.85,
                    "n_samples": 1000,
                    "distribution_type": "unimodal",
                },
                "active_addresses": {
                    "block_height": 870000,
                    "active_addresses_block": 45230,
                    "active_addresses_24h": 892145,
                    "unique_senders": 23456,
                    "unique_receivers": 34567,
                    "is_anomaly": False,
                },
                "tx_volume": {
                    "tx_count": 2847,
                    "tx_volume_btc": 15234.56,
                    "tx_volume_usd": 1523456000.0,
                    "utxoracle_price_used": 100000.0,
                    "low_confidence": False,
                },
            }
        }
    )

    timestamp: datetime = Field(
        ...,
        description="Timestamp when metrics were calculated",
    )
    monte_carlo: Optional[MonteCarloFusionResponse] = Field(
        default=None,
        description="Monte Carlo signal fusion (null if whale data unavailable)",
    )
    active_addresses: Optional[ActiveAddressesResponse] = Field(
        default=None,
        description="Active addresses metric",
    )
    tx_volume: Optional[TxVolumeResponse] = Field(
        default=None,
        description="Transaction volume metric",
    )


class MetricsHistoricalResponse(BaseModel):
    """
    Response for /api/metrics/historical endpoint.

    Returns metrics for a date range.
    """

    start: datetime = Field(..., description="Start of date range")
    end: datetime = Field(..., description="End of date range")
    count: int = Field(..., ge=0, description="Number of data points returned")
    data: list[MetricsLatestResponse] = Field(
        default_factory=list,
        description="List of metrics ordered by timestamp descending",
    )


# =============================================================================
# Request Models
# =============================================================================


class MetricsHistoricalRequest(BaseModel):
    """Query parameters for /api/metrics/historical endpoint."""

    days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Number of days of history to return (1-90)",
    )


# =============================================================================
# Error Models
# =============================================================================


class MetricsErrorResponse(BaseModel):
    """Standard error response for metrics endpoints."""

    error: str = Field(..., description="Error message")
    code: str = Field(..., description="Error code for programmatic handling")
    details: Optional[dict] = Field(
        default=None,
        description="Additional error details",
    )


# =============================================================================
# OpenAPI Tags
# =============================================================================

METRICS_TAGS = [
    {
        "name": "metrics",
        "description": "On-chain metrics: Monte Carlo fusion, Active Addresses, TX Volume",
    }
]
