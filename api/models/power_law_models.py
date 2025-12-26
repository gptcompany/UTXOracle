"""
Pydantic models for Bitcoin Price Power Law API (spec-034)

Models for:
- PowerLawModel: Fitted model parameters
- PowerLawPrediction: Price prediction for a specific date
- PowerLawResponse: API response combining model and prediction
- PowerLawHistoryPoint: Historical data point for charting
- PowerLawHistoryResponse: API response for history endpoint
"""

from datetime import date as DateType
from typing import Literal

from pydantic import BaseModel, Field


ZoneType = Literal["undervalued", "fair", "overvalued", "unknown"]


class PowerLawModel(BaseModel):
    """Fitted power law model parameters."""

    alpha: float = Field(..., description="Intercept coefficient")
    beta: float = Field(..., description="Slope coefficient (power exponent)")
    r_squared: float = Field(..., ge=0.0, le=1.0, description="Model fit R-squared")
    std_error: float = Field(..., gt=0, description="Standard error in log10 space")
    fitted_on: DateType = Field(..., description="Date model was calibrated")
    sample_size: int = Field(..., gt=0, description="Data points used for fit")

    model_config = {
        "json_schema_extra": {
            "example": {
                "alpha": -17.01,
                "beta": 5.82,
                "r_squared": 0.95,
                "std_error": 0.32,
                "fitted_on": "2025-01-01",
                "sample_size": 5800,
            }
        }
    }


class PowerLawPrediction(BaseModel):
    """Price prediction for a specific date."""

    date: DateType = Field(..., description="Prediction target date")
    days_since_genesis: int = Field(
        ..., gt=0, description="Days since Bitcoin genesis (2009-01-03)"
    )
    fair_value: float = Field(..., gt=0, description="Model predicted price USD")
    lower_band: float = Field(..., gt=0, description="-1 sigma support level")
    upper_band: float = Field(..., gt=0, description="+1 sigma resistance level")
    current_price: float | None = Field(default=None, description="Actual market price")
    deviation_pct: float | None = Field(
        default=None, description="% deviation from fair value"
    )
    zone: ZoneType = Field(
        default="unknown", description="Valuation zone classification"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "date": "2025-12-25",
                "days_since_genesis": 6200,
                "fair_value": 89234.56,
                "lower_band": 42567.89,
                "upper_band": 187012.34,
                "current_price": 98500.00,
                "deviation_pct": 10.4,
                "zone": "fair",
            }
        }
    }


class PowerLawResponse(BaseModel):
    """API response with model and optional prediction."""

    model: PowerLawModel = Field(..., description="Current model parameters")
    prediction: PowerLawPrediction | None = Field(
        default=None, description="Prediction if requested"
    )


class PowerLawHistoryPoint(BaseModel):
    """Historical data point for charting."""

    date: DateType = Field(..., description="Historical date")
    price: float = Field(..., description="Actual BTC/USD price")
    fair_value: float = Field(..., description="Model fair value")
    zone: Literal["undervalued", "fair", "overvalued"] = Field(
        ..., description="Zone classification"
    )


class PowerLawHistoryResponse(BaseModel):
    """API response for history endpoint."""

    model: PowerLawModel = Field(..., description="Current model parameters")
    history: list[PowerLawHistoryPoint] = Field(
        ..., description="Historical data points"
    )
