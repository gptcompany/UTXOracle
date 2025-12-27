"""
Pydantic models for RBN API Integration (spec-035).
Tasks T005-T009: Data models for RBN fetcher, validation, and comparison.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, SecretStr


# =============================================================================
# T005: Core Enums and Configuration
# =============================================================================


class RBNTier(int, Enum):
    """API access tiers with different quotas."""

    FREE = 0  # 100 queries/week, 1 year history
    STANDARD = 1  # 300 queries/week, full history
    PREMIUM = 2  # 10,000 queries/week, all metrics


class RBNCategory(str, Enum):
    """RBN API endpoint categories."""

    MVRV = "market_value_to_realized_value"
    SOPR = "spent_output_profit_ratio"
    NUPL = "net_unrealized_profit_loss"
    REALIZED_CAP = "realizedcap"
    PRICE_MODELS = "price_models"
    COINTIME = "cointime_statistics"
    SUPPLY = "supply_distribution"
    FEES = "fees"
    NETWORK = "network_statistics"
    HODL_AGE = "hodl_by_age"
    UTXO_DIST = "utxo_distributions"


class RBNConfig(BaseModel):
    """RBN API configuration."""

    model_config = ConfigDict(env_prefix="RBN_")

    base_url: str = Field(
        default="https://api.researchbitcoin.net/v1",
        description="RBN API base URL",
    )
    token: SecretStr = Field(
        ...,
        description="API authentication token (UUID format)",
    )
    tier: RBNTier = Field(
        default=RBNTier.FREE,
        description="API access tier",
    )
    cache_ttl_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Cache time-to-live in hours",
    )
    timeout_seconds: float = Field(
        default=30.0,
        ge=5.0,
        le=120.0,
        description="HTTP request timeout",
    )


class RBNMetricInfo(BaseModel):
    """Metadata for a single RBN metric."""

    name: str = Field(..., description="Human-readable metric name")
    category: RBNCategory
    data_field: str = Field(..., description="API data_field parameter")
    tier_required: RBNTier = Field(default=RBNTier.FREE)
    utxoracle_spec: Optional[str] = Field(
        default=None,
        description="Matching UTXOracle spec number (e.g., 'spec-007')",
    )
    description: str = Field(default="")

    @property
    def endpoint(self) -> str:
        """Full API endpoint path."""
        return f"/{self.category.value}/{self.data_field}"


# Static registry of known metrics
RBN_METRICS: dict[str, RBNMetricInfo] = {
    "mvrv": RBNMetricInfo(
        name="MVRV Ratio",
        category=RBNCategory.MVRV,
        data_field="mvrv",
        utxoracle_spec="spec-007",
        description="Market Value to Realized Value ratio",
    ),
    "mvrv_z": RBNMetricInfo(
        name="MVRV Z-Score",
        category=RBNCategory.MVRV,
        data_field="mvrv_z",
        utxoracle_spec="spec-007",
        description="MVRV normalized by standard deviation",
    ),
    "sopr": RBNMetricInfo(
        name="SOPR",
        category=RBNCategory.SOPR,
        data_field="sopr",
        utxoracle_spec="spec-016",
        description="Spent Output Profit Ratio",
    ),
    "nupl": RBNMetricInfo(
        name="Net Unrealized Profit/Loss",
        category=RBNCategory.NUPL,
        data_field="net_unrealized_profit_loss",
        utxoracle_spec="spec-007",
        description="NUPL indicator",
    ),
    "realized_cap": RBNMetricInfo(
        name="Realized Cap",
        category=RBNCategory.REALIZED_CAP,
        data_field="realized_cap",
        utxoracle_spec="spec-007",
        description="Realized capitalization",
    ),
    "price_power_law": RBNMetricInfo(
        name="Power Law Price Model",
        category=RBNCategory.PRICE_MODELS,
        data_field="price_power_law_qr",
        utxoracle_spec="spec-034",
        description="Quantile regression power law model",
    ),
    "liveliness": RBNMetricInfo(
        name="Liveliness",
        category=RBNCategory.COINTIME,
        data_field="liveliness",
        utxoracle_spec="spec-018",
        description="Cointime liveliness metric",
    ),
    "thermo_cap": RBNMetricInfo(
        name="Thermocap",
        category=RBNCategory.COINTIME,
        data_field="thermo_cap",
        tier_required=RBNTier.FREE,
        description="Thermodynamic capitalization",
    ),
}


# =============================================================================
# T006: Request/Response Models
# =============================================================================


class RBNDataPoint(BaseModel):
    """Single data point from RBN response."""

    date: date
    value: float


class RBNMetricResponse(BaseModel):
    """Parsed response from RBN API."""

    status: str
    message: str
    metric_id: str
    data: list[RBNDataPoint]
    output_format: str
    timestamp: datetime
    cached: bool = Field(
        default=False,
        description="Whether response was served from cache",
    )

    @classmethod
    def from_api_response(
        cls,
        response: dict[str, Any],
        metric_id: str,
        cached: bool = False,
    ) -> "RBNMetricResponse":
        """Parse raw API response into structured model."""
        raw_data = response.get("data", [])

        # Handle two possible formats:
        # 1. List of dicts: [{"date": "2025-12-26", "mvrv_z": 1.123}, ...]
        # 2. Dict with arrays: {"dates": [...], "values": [...]}
        data_points = []

        if isinstance(raw_data, list):
            # Format 1: List of dicts (actual RBN API format)
            for item in raw_data:
                if isinstance(item, dict) and "date" in item:
                    dt = item["date"]
                    # Value key is the metric name (e.g., "mvrv_z", "sopr")
                    # Find the non-date key
                    value = None
                    for key, val in item.items():
                        if key != "date" and isinstance(val, (int, float)):
                            value = val
                            break
                    if value is not None:
                        data_points.append(RBNDataPoint(date=dt, value=value))
        elif isinstance(raw_data, dict):
            # Format 2: Dict with arrays (legacy format)
            dates = raw_data.get("dates", [])
            values = raw_data.get("values", [])
            if len(dates) == len(values):
                data_points = [
                    RBNDataPoint(date=d, value=v) for d, v in zip(dates, values)
                ]

        return cls(
            status=response.get("status", "unknown"),
            message=response.get("message", ""),
            metric_id=metric_id,
            data=data_points,
            output_format=response.get("output_format", "json"),
            timestamp=datetime.fromisoformat(
                response.get("timestamp", datetime.now().isoformat()).replace(
                    "+00:00", ""
                )
            ),
            cached=cached,
        )


class RBNErrorResponse(BaseModel):
    """Error response from RBN API."""

    status: str = "error"
    error: str
    timestamp: datetime
    details: Optional[dict[str, Any]] = None


# =============================================================================
# T007: Comparison Models
# =============================================================================


class ComparisonStatus(str, Enum):
    """Status of a single metric comparison."""

    MATCH = "match"  # <1% deviation
    MINOR_DIFF = "minor_diff"  # 1-5% deviation
    MAJOR_DIFF = "major_diff"  # >5% deviation
    MISSING = "missing"  # Data not available on one side


class MetricComparison(BaseModel):
    """Comparison result for a single date."""

    metric_id: str
    date: date
    utxoracle_value: Optional[float] = None
    rbn_value: Optional[float] = None
    absolute_diff: Optional[float] = None
    relative_diff_pct: Optional[float] = None
    status: ComparisonStatus

    @classmethod
    def create(
        cls,
        metric_id: str,
        dt: date,
        utxo_val: Optional[float],
        rbn_val: Optional[float],
        tolerance_pct: float = 1.0,
    ) -> "MetricComparison":
        """Factory method to create comparison with auto-calculated status."""
        if utxo_val is None or rbn_val is None:
            return cls(
                metric_id=metric_id,
                date=dt,
                utxoracle_value=utxo_val,
                rbn_value=rbn_val,
                status=ComparisonStatus.MISSING,
            )

        abs_diff = abs(utxo_val - rbn_val)

        # Handle edge case: both values are zero (they are equal)
        if abs_diff == 0:
            rel_diff = 0.0
        elif rbn_val != 0:
            rel_diff = (abs_diff / abs(rbn_val)) * 100
        else:
            # rbn_val is 0 but utxo_val is not - cap at 999.99% to avoid infinity in JSON
            rel_diff = 999.99

        if rel_diff < tolerance_pct:
            status = ComparisonStatus.MATCH
        elif rel_diff < 5.0:
            status = ComparisonStatus.MINOR_DIFF
        else:
            status = ComparisonStatus.MAJOR_DIFF

        return cls(
            metric_id=metric_id,
            date=dt,
            utxoracle_value=utxo_val,
            rbn_value=rbn_val,
            absolute_diff=abs_diff,
            relative_diff_pct=rel_diff,
            status=status,
        )


# =============================================================================
# T008: Validation Report Models
# =============================================================================


class ValidationReport(BaseModel):
    """Aggregate validation report for a metric."""

    metric_id: str
    metric_name: str
    date_range_start: date
    date_range_end: date
    total_comparisons: int
    matches: int
    minor_diffs: int
    major_diffs: int
    missing: int
    match_rate_pct: float
    avg_deviation_pct: Optional[float] = None
    max_deviation_pct: Optional[float] = None
    generated_at: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_comparisons(
        cls,
        metric_id: str,
        metric_name: str,
        comparisons: list[MetricComparison],
    ) -> "ValidationReport":
        """Generate report from list of comparisons."""
        if not comparisons:
            raise ValueError("Cannot generate report from empty comparisons")

        matches = sum(1 for c in comparisons if c.status == ComparisonStatus.MATCH)
        minor = sum(1 for c in comparisons if c.status == ComparisonStatus.MINOR_DIFF)
        major = sum(1 for c in comparisons if c.status == ComparisonStatus.MAJOR_DIFF)
        missing = sum(1 for c in comparisons if c.status == ComparisonStatus.MISSING)
        total = len(comparisons)

        valid_diffs = [
            c.relative_diff_pct for c in comparisons if c.relative_diff_pct is not None
        ]
        avg_dev = sum(valid_diffs) / len(valid_diffs) if valid_diffs else None
        max_dev = max(valid_diffs) if valid_diffs else None

        dates = sorted([c.date for c in comparisons])

        return cls(
            metric_id=metric_id,
            metric_name=metric_name,
            date_range_start=dates[0],
            date_range_end=dates[-1],
            total_comparisons=total,
            matches=matches,
            minor_diffs=minor,
            major_diffs=major,
            missing=missing,
            match_rate_pct=(matches / total) * 100,
            avg_deviation_pct=avg_dev,
            max_deviation_pct=max_dev,
        )


class ValidationEndpointResponse(BaseModel):
    """Response for /api/v1/validation/rbn/{metric_id} endpoint."""

    metric: str
    date_range: tuple[str, str]
    comparisons: int
    matches: int
    match_rate: float
    avg_deviation_pct: Optional[float]
    status: str = Field(
        default="success",
        description="API response status",
    )
    details: Optional[list[MetricComparison]] = None


class ValidationReportListResponse(BaseModel):
    """Response for /api/v1/validation/rbn/report endpoint."""

    reports: list[ValidationReport]
    generated_at: datetime
    total_metrics: int
    overall_match_rate: float


# =============================================================================
# T009: Quota Tracking Models
# =============================================================================


class QuotaInfo(BaseModel):
    """API quota tracking."""

    tier: RBNTier
    weekly_limit: int
    used_this_week: int
    remaining: int
    reset_at: datetime

    @property
    def usage_pct(self) -> float:
        """Calculate usage percentage."""
        if self.weekly_limit == 0:
            return 0.0
        return (self.used_this_week / self.weekly_limit) * 100


class QuotaExceededError(Exception):
    """Raised when API quota is exceeded."""

    def __init__(self, quota_info: QuotaInfo):
        self.quota_info = quota_info
        super().__init__(
            f"RBN API quota exceeded: {quota_info.used_this_week}/{quota_info.weekly_limit} "
            f"(resets at {quota_info.reset_at})"
        )
