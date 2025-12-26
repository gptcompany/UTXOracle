"""
Pydantic models for PRO Risk API (spec-033)

Models for:
- T022: ProRiskResponseAPI
- T023: ProRiskComponentAPI
"""

from datetime import date as DateType
from typing import Literal, Optional

from pydantic import BaseModel, Field


RiskZoneType = Literal["extreme_fear", "fear", "neutral", "greed", "extreme_greed"]


class ProRiskComponentAPI(BaseModel):
    """API response for individual component (T023)."""

    metric: str = Field(..., description="Metric identifier (e.g., 'mvrv_z', 'sopr')")
    raw_value: float = Field(
        ..., description="Original metric value before normalization"
    )
    normalized: float = Field(
        ..., ge=0.0, le=1.0, description="Percentile-normalized 0-1 score"
    )
    weight: float = Field(..., description="Weight in composite calculation")
    weighted: float = Field(
        ..., description="Contribution to composite (normalized * weight)"
    )


class HistoricalContextAPI(BaseModel):
    """Historical context percentiles."""

    percentile_30d: float = Field(..., ge=0.0, le=1.0, description="30-day percentile")
    percentile_1y: float = Field(..., ge=0.0, le=1.0, description="1-year percentile")


class ProRiskResponseAPI(BaseModel):
    """API response for PRO Risk endpoint (T022)."""

    date: DateType = Field(..., description="Date of calculation")
    value: float = Field(..., ge=0.0, le=1.0, description="Composite PRO Risk score")
    zone: RiskZoneType = Field(..., description="Risk zone classification")
    components: list[ProRiskComponentAPI] = Field(
        ..., description="Individual component scores"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Data availability confidence"
    )
    historical_context: Optional[HistoricalContextAPI] = Field(
        None, description="30d/1y percentile context"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "date": "2025-12-25",
                "value": 0.62,
                "zone": "greed",
                "components": [
                    {
                        "metric": "mvrv_z",
                        "raw_value": 2.1,
                        "normalized": 0.71,
                        "weight": 0.30,
                        "weighted": 0.213,
                    },
                    {
                        "metric": "sopr",
                        "raw_value": 1.02,
                        "normalized": 0.55,
                        "weight": 0.20,
                        "weighted": 0.110,
                    },
                ],
                "confidence": 0.95,
                "historical_context": {"percentile_30d": 0.78, "percentile_1y": 0.65},
            }
        }
    }


class ProRiskHistoryPointAPI(BaseModel):
    """Single point in PRO Risk history."""

    date: DateType = Field(..., description="Date")
    value: float = Field(..., ge=0.0, le=1.0, description="PRO Risk value")
    zone: RiskZoneType = Field(..., description="Zone classification")


class ProRiskHistoryResponseAPI(BaseModel):
    """API response for PRO Risk history endpoint."""

    start_date: DateType = Field(..., description="Start of date range")
    end_date: DateType = Field(..., description="End of date range")
    data: list[ProRiskHistoryPointAPI] = Field(
        ..., description="Historical data points"
    )


class ZoneDefinitionAPI(BaseModel):
    """Zone definition with thresholds."""

    name: RiskZoneType = Field(..., description="Zone name")
    min_value: float = Field(..., description="Minimum value (inclusive)")
    max_value: float = Field(
        ..., description="Maximum value (exclusive, except for extreme_greed)"
    )
    interpretation: str = Field(..., description="Human-readable interpretation")


class ZoneDefinitionsResponseAPI(BaseModel):
    """API response for zone definitions endpoint."""

    zones: list[ZoneDefinitionAPI] = Field(..., description="List of zone definitions")


class ErrorResponseAPI(BaseModel):
    """API error response."""

    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
