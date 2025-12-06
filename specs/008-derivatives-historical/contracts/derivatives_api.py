"""
API Contracts for Derivatives Historical Integration (spec-008).

This module defines Pydantic models for API request/response validation.
These contracts ensure type safety and automatic documentation via FastAPI.

Usage:
    from contracts.derivatives_api import (
        FundingRateResponse,
        OpenInterestResponse,
        EnhancedFusionResponse,
        BacktestRequest,
        BacktestResponse,
    )
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Funding Rate API
# =============================================================================


class FundingRateResponse(BaseModel):
    """Response for funding rate signal query."""

    timestamp: datetime = Field(description="When funding rate was collected")
    symbol: str = Field(default="BTCUSDT", description="Trading pair")
    exchange: str = Field(default="binance", description="Source exchange")
    funding_rate: float = Field(description="Raw funding rate (e.g., 0.0015 = 0.15%)")
    funding_vote: float = Field(
        ge=-1.0, le=1.0, description="Contrarian signal vote [-1, 1]"
    )
    is_extreme: bool = Field(description="True if |rate| exceeds normal bounds (±0.1%)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "timestamp": "2025-08-31T17:00:00Z",
                    "symbol": "BTCUSDT",
                    "exchange": "binance",
                    "funding_rate": 0.0015,
                    "funding_vote": -0.8,
                    "is_extreme": True,
                }
            ]
        }
    }


# =============================================================================
# Open Interest API
# =============================================================================


class OpenInterestResponse(BaseModel):
    """Response for open interest signal query."""

    timestamp: datetime = Field(description="When OI was measured")
    symbol: str = Field(default="BTCUSDT", description="Trading pair")
    exchange: str = Field(default="binance", description="Source exchange")
    oi_value: float = Field(gt=0, description="Absolute OI in USD")
    oi_change_1h: float = Field(description="Percentage change in last 1 hour")
    oi_change_24h: float = Field(description="Percentage change in last 24 hours")
    oi_vote: float = Field(ge=-1.0, le=1.0, description="Context-aware signal vote")
    context: Literal[
        "confirming", "diverging", "deleveraging", "neutral", "no_data"
    ] = Field(description="Relationship to whale signal")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "timestamp": "2025-11-17T23:55:00Z",
                    "symbol": "BTCUSDT",
                    "exchange": "binance",
                    "oi_value": 9331378667.0,
                    "oi_change_1h": 0.035,
                    "oi_change_24h": 0.082,
                    "oi_vote": 0.5,
                    "context": "confirming",
                }
            ]
        }
    }


# =============================================================================
# Enhanced Fusion API
# =============================================================================


class ComponentVote(BaseModel):
    """Individual signal component with vote and weight."""

    vote: Optional[float] = Field(
        default=None, ge=-1.0, le=1.0, description="Signal vote (None if unavailable)"
    )
    weight: float = Field(ge=0.0, le=1.0, description="Weight in fusion")


class EnhancedFusionResponse(BaseModel):
    """
    Response for enhanced 4-component fusion query.

    Extends spec-007 MonteCarloFusionResult with derivatives components.
    """

    # Core Monte Carlo fields
    signal_mean: float = Field(ge=-1.0, le=1.0, description="Mean of bootstrap samples")
    signal_std: float = Field(ge=0.0, description="Standard deviation of samples")
    ci_lower: float = Field(ge=-1.0, le=1.0, description="95% CI lower bound")
    ci_upper: float = Field(ge=-1.0, le=1.0, description="95% CI upper bound")
    action: Literal["BUY", "SELL", "HOLD"] = Field(description="Trading action")
    action_confidence: float = Field(
        ge=0.0, le=1.0, description="Probability action is correct"
    )
    n_samples: int = Field(default=1000, gt=0, description="Bootstrap iterations")

    # Component breakdown
    components: dict[str, ComponentVote] = Field(
        description="Individual signal components (whale, utxo, funding, oi)"
    )

    # Metadata
    derivatives_available: bool = Field(
        description="True if both funding and OI were used"
    )
    data_freshness_minutes: int = Field(
        ge=0, description="Age of newest derivatives data"
    )
    distribution_type: Literal["unimodal", "bimodal", "insufficient_data"] = Field(
        default="unimodal", description="Shape of distribution"
    )

    @field_validator("components")
    @classmethod
    def validate_components(cls, v):
        """Ensure required components exist."""
        required = {"whale", "utxo", "funding", "oi"}
        if not required.issubset(v.keys()):
            missing = required - set(v.keys())
            raise ValueError(f"Missing components: {missing}")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "signal_mean": 0.65,
                    "signal_std": 0.12,
                    "ci_lower": 0.42,
                    "ci_upper": 0.88,
                    "action": "BUY",
                    "action_confidence": 0.78,
                    "n_samples": 1000,
                    "components": {
                        "whale": {"vote": 0.8, "weight": 0.40},
                        "utxo": {"vote": 0.6, "weight": 0.20},
                        "funding": {"vote": 0.5, "weight": 0.25},
                        "oi": {"vote": 0.4, "weight": 0.15},
                    },
                    "derivatives_available": True,
                    "data_freshness_minutes": 5,
                    "distribution_type": "unimodal",
                }
            ]
        }
    }


# =============================================================================
# Backtest API
# =============================================================================


class WeightsConfig(BaseModel):
    """Configuration for signal component weights."""

    whale: float = Field(
        default=0.40, ge=0.0, le=1.0, description="Whale signal weight"
    )
    utxo: float = Field(default=0.20, ge=0.0, le=1.0, description="UTXOracle weight")
    funding: float = Field(
        default=0.25, ge=0.0, le=1.0, description="Funding rate weight"
    )
    oi: float = Field(default=0.15, ge=0.0, le=1.0, description="Open interest weight")

    @field_validator("oi")
    @classmethod
    def validate_weights_sum(cls, v, info):
        """Ensure weights sum to 1.0."""
        values = info.data
        total = (
            values.get("whale", 0)
            + values.get("utxo", 0)
            + values.get("funding", 0)
            + v
        )
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        return v


class BacktestRequest(BaseModel):
    """Request to run historical backtest."""

    start_date: datetime = Field(description="Backtest period start")
    end_date: datetime = Field(description="Backtest period end")
    weights: Optional[WeightsConfig] = Field(
        default=None, description="Custom weights (uses defaults if not provided)"
    )
    optimize_weights: bool = Field(
        default=False, description="Run grid search for optimal weights"
    )
    holdout_ratio: float = Field(
        default=0.2, ge=0.0, le=0.5, description="Fraction of data for validation"
    )

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v, info):
        """Ensure end_date > start_date."""
        start = info.data.get("start_date")
        if start and v <= start:
            raise ValueError("end_date must be after start_date")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "start_date": "2025-10-01T00:00:00Z",
                    "end_date": "2025-10-31T23:59:59Z",
                    "weights": {"whale": 0.4, "utxo": 0.2, "funding": 0.25, "oi": 0.15},
                    "optimize_weights": False,
                    "holdout_ratio": 0.2,
                }
            ]
        }
    }


class SignalCounts(BaseModel):
    """Breakdown of signal counts by action."""

    total: int = Field(ge=0, description="Total signals generated")
    buy: int = Field(ge=0, description="BUY signals")
    sell: int = Field(ge=0, description="SELL signals")
    hold: int = Field(ge=0, description="HOLD signals")


class PerformanceMetrics(BaseModel):
    """Performance metrics from backtest."""

    win_rate: float = Field(ge=0.0, le=1.0, description="Correct directional calls")
    total_return: float = Field(description="Cumulative return")
    sharpe_ratio: float = Field(description="Risk-adjusted return")
    max_drawdown: float = Field(le=0.0, description="Worst peak-to-trough (negative)")


class BacktestResponse(BaseModel):
    """Response from historical backtest."""

    period: dict[str, datetime] = Field(description="Backtest period (start, end)")
    signals: SignalCounts = Field(description="Signal breakdown")
    performance: PerformanceMetrics = Field(description="Performance metrics")
    optimal_weights: Optional[WeightsConfig] = Field(
        default=None, description="Best weights from optimization (if run)"
    )
    execution_time_seconds: float = Field(ge=0, description="Backtest execution time")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "period": {
                        "start": "2025-10-01T00:00:00Z",
                        "end": "2025-10-31T23:59:59Z",
                    },
                    "signals": {"total": 744, "buy": 312, "sell": 198, "hold": 234},
                    "performance": {
                        "win_rate": 0.62,
                        "total_return": 0.085,
                        "sharpe_ratio": 1.42,
                        "max_drawdown": -0.034,
                    },
                    "optimal_weights": None,
                    "execution_time_seconds": 12.5,
                }
            ]
        }
    }


# =============================================================================
# Error Responses
# =============================================================================


class DerivativesUnavailableResponse(BaseModel):
    """Response when LiquidationHeatmap is unavailable."""

    status: Literal["degraded"] = Field(
        default="degraded", description="System operating in degraded mode"
    )
    message: str = Field(
        default="Derivatives data unavailable, using 2-component fusion",
        description="Explanation of degradation",
    )
    fallback_used: bool = Field(
        default=True, description="True if fallback to spec-007 fusion"
    )


class DataFreshnessWarning(BaseModel):
    """Warning when derivatives data is stale."""

    warning: str = Field(description="Warning message")
    data_age_minutes: int = Field(ge=0, description="Age of oldest data point")
    threshold_minutes: int = Field(
        default=60, description="Staleness threshold that triggered warning"
    )
