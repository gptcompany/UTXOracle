"""
Pydantic models for Custom Price Models Framework API (spec-036)

Models for:
- ModelPredictionResponse: Unified prediction output for API
- ModelInfoResponse: Model metadata for listing
- BacktestResultResponse: Backtest performance metrics
- ModelComparisonResponse: Multi-model comparison results
- EnsembleCreateRequest: Request to create ensemble predictions
"""

from datetime import date as DateType
from typing import Any

import numpy as np
from pydantic import BaseModel, Field, field_validator


class ModelPredictionResponse(BaseModel):
    """API response for model prediction."""

    model_name: str = Field(..., description="Model that generated prediction")
    date: DateType = Field(..., description="Prediction target date")
    predicted_price: float = Field(..., gt=0, description="Predicted BTC/USD price")
    confidence_interval: dict[str, float] = Field(..., description="Lower/upper bounds")
    confidence_level: float = Field(
        ..., ge=0, le=1, description="Confidence level (e.g., 0.68 for 1-sigma)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Model-specific data"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "model_name": "Power Law",
                "date": "2025-12-27",
                "predicted_price": 98500.00,
                "confidence_interval": {"lower": 45000.00, "upper": 210000.00},
                "confidence_level": 0.68,
                "metadata": {"zone": "fair", "deviation_pct": 5.2},
            }
        }
    }


class ModelInfoResponse(BaseModel):
    """API response for model info."""

    name: str = Field(..., description="Model name")
    description: str = Field(..., description="Model methodology")
    required_data: list[str] = Field(..., description="Required data sources")
    is_fitted: bool = Field(..., description="Whether model is calibrated")


class BacktestResultResponse(BaseModel):
    """API response for backtest results."""

    model_name: str = Field(..., description="Model name")
    start_date: DateType = Field(..., description="Backtest start date")
    end_date: DateType = Field(..., description="Backtest end date")
    predictions: int = Field(..., ge=0, description="Number of predictions made")
    metrics: dict[str, float] = Field(..., description="Performance metrics")

    model_config = {
        "json_schema_extra": {
            "example": {
                "model_name": "Power Law",
                "start_date": "2020-01-01",
                "end_date": "2025-12-27",
                "predictions": 2188,
                "metrics": {
                    "mae": 5234.50,
                    "mape": 12.3,
                    "rmse": 7891.20,
                    "direction_accuracy": 0.58,
                    "sharpe_ratio": 0.85,
                    "max_drawdown": -32.5,
                },
            }
        }
    }


class ModelComparisonResponse(BaseModel):
    """API response for model comparison."""

    models: list[str] = Field(..., description="Models compared")
    ranking: list[str] = Field(..., description="Models ranked by MAPE (best first)")
    best_model: str = Field(..., description="Best performing model")
    results: list[BacktestResultResponse] = Field(..., description="Results per model")


class EnsembleCreateRequest(BaseModel):
    """Request to create an ensemble model."""

    models: list[str] = Field(..., min_length=2, description="Models to combine")
    weights: list[float] = Field(..., description="Model weights (sum to 1.0)")
    aggregation: str = Field(default="weighted_avg", description="Aggregation method")
    date: DateType | None = Field(
        default=None, description="Prediction target date (defaults to today)"
    )

    @field_validator("weights")
    @classmethod
    def weights_sum_to_one(cls, v: list[float]) -> list[float]:
        if any(w < 0 for w in v):
            raise ValueError("weights must be non-negative")
        if not np.isclose(sum(v), 1.0):
            raise ValueError("weights must sum to 1.0")
        return v

    @field_validator("aggregation")
    @classmethod
    def valid_aggregation(cls, v: str) -> str:
        valid = {"weighted_avg", "median", "min", "max"}
        if v not in valid:
            raise ValueError(f"aggregation must be one of {valid}")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "models": ["power-law", "stock-to-flow", "thermocap"],
                "weights": [0.4, 0.3, 0.3],
                "aggregation": "weighted_avg",
                "date": "2025-12-27",
            }
        }
    }
