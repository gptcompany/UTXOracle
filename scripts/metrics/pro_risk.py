#!/usr/bin/env python3
"""
PRO Risk Metric - Composite 0-1 Risk Indicator (spec-033)

Aggregates 6 on-chain signals to provide a single-glance market cycle position:
- MVRV Z-Score (30% weight, Grade A)
- SOPR (20% weight, Grade A)
- NUPL (20% weight, Grade A)
- Reserve Risk (15% weight, Grade B)
- Puell Multiple (10% weight, Grade B)
- HODL Waves (5% weight, Grade B)

Usage:
    python -m scripts.metrics.pro_risk [-d YYYY/MM/DD] [--json]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Literal, Optional

import numpy as np

# =============================================================================
# Type Definitions (T005)
# =============================================================================

RiskZone = Literal["extreme_fear", "fear", "neutral", "greed", "extreme_greed"]

# =============================================================================
# Constants (T005)
# =============================================================================

# Component weights - evidence-based fixed weights (research.md)
# Grade A metrics (70% total): proven academic validation
# Grade B metrics (30% total): derived or less validated
COMPONENT_WEIGHTS: dict[str, float] = {
    "mvrv_z": 0.30,  # Grade A - proven cycle indicator
    "sopr": 0.20,  # Grade A - 82.44% directional accuracy
    "nupl": 0.20,  # Grade A - direct profit/loss measure
    "reserve_risk": 0.15,  # Grade B - ARK Invest cointime framework
    "puell": 0.10,  # Grade B - miner-centric, lagging indicator
    "hodl_waves": 0.05,  # Grade B - derivative of age cohorts
}

# Validation: weights must sum to 1.0
assert abs(sum(COMPONENT_WEIGHTS.values()) - 1.0) < 0.001, "Weights must sum to 1.0"

# Zone thresholds (value ranges for classification)
# Based on spec-033 data-model.md state transitions
ZONE_THRESHOLDS: list[tuple[float, float, RiskZone]] = [
    (0.00, 0.20, "extreme_fear"),  # Strong buy signal
    (0.20, 0.40, "fear"),  # Accumulation zone
    (0.40, 0.60, "neutral"),  # Hold / DCA
    (0.60, 0.80, "greed"),  # Caution zone
    (0.80, 1.00, "extreme_greed"),  # Distribution zone
]

# Minimum history days for stable percentile calculation (4 years)
MIN_HISTORY_DAYS = 1460

# Winsorization percentile (cap outliers at 2nd/98th percentile)
WINSORIZE_PCT = 0.02


# =============================================================================
# Dataclasses (T011, T012)
# =============================================================================


@dataclass
class ComponentScore:
    """Single component metric normalized score (T012)."""

    metric_name: str  # e.g., "mvrv_z", "sopr"
    raw_value: float  # Original metric value
    percentile: float  # Normalized 0-1 score
    weight: float  # Weight in composite (0.05-0.30)
    history_days: int  # Days of data available
    is_valid: bool = True  # Whether sufficient history exists

    def __post_init__(self):
        if not 0.0 <= self.percentile <= 1.0:
            raise ValueError(f"percentile must be in [0, 1], got {self.percentile}")
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"weight must be in [0, 1], got {self.weight}")

    @property
    def weighted_contribution(self) -> float:
        """Calculate weighted contribution to composite score."""
        return self.percentile * self.weight if self.is_valid else 0.0


@dataclass
class ProRiskResult:
    """Composite risk metric result for a specific date (T011)."""

    # Core fields
    date: datetime
    value: float  # 0.0 - 1.0 composite score
    zone: RiskZone  # Classification string

    # Component scores (normalized 0-1)
    components: dict[str, float] = field(default_factory=dict)

    # Metadata
    confidence: float = 1.0  # Data availability (0.0-1.0)
    block_height: Optional[int] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"value must be in [0, 1], got {self.value}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")

        # Validate zone is a valid RiskZone value
        valid_zones = {"extreme_fear", "fear", "neutral", "greed", "extreme_greed"}
        if self.zone not in valid_zones:
            raise ValueError(f"zone must be one of {valid_zones}, got {self.zone}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date.strftime("%Y-%m-%d")
            if isinstance(self.date, datetime)
            else str(self.date),
            "value": round(self.value, 4),
            "zone": self.zone,
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "confidence": round(self.confidence, 4),
            "block_height": self.block_height,
            "updated_at": self.updated_at.isoformat()
            if isinstance(self.updated_at, datetime)
            else str(self.updated_at),
        }


# =============================================================================
# Normalization Functions (T004, T013)
# =============================================================================


def normalize_to_percentile(
    value: float,
    historical_data: list[float],
    winsorize_pct: float = WINSORIZE_PCT,
) -> float:
    """
    Normalize a value to 0-1 percentile using historical distribution (T013).

    Uses 4-year window with 2% winsorization to cap extreme outliers.
    Returns 0.5 (neutral) when insufficient historical data.

    Args:
        value: Current metric value to normalize
        historical_data: List of historical values (minimum 1460 days recommended)
        winsorize_pct: Percentile for winsorization (default 0.02 = 2%)

    Returns:
        Normalized 0-1 percentile score
    """
    if len(historical_data) < MIN_HISTORY_DAYS:
        # Insufficient data - return neutral
        return 0.5

    arr = np.array(historical_data)

    # Check for invalid values (NaN, Inf)
    if not np.isfinite(arr).all():
        # Filter out invalid values
        arr = arr[np.isfinite(arr)]
        if len(arr) < MIN_HISTORY_DAYS:
            return 0.5

    # Calculate winsorization bounds (2nd and 98th percentile)
    lower_bound = float(np.percentile(arr, winsorize_pct * 100))
    upper_bound = float(np.percentile(arr, (1 - winsorize_pct) * 100))

    # Cap the value at winsorization bounds
    capped_value = max(lower_bound, min(upper_bound, value))

    # Calculate percentile rank (what fraction of historical values are <= capped_value)
    percentile = float(np.sum(arr <= capped_value) / len(arr))

    return percentile


# =============================================================================
# Zone Classification (T014)
# =============================================================================


def classify_zone(value: float) -> RiskZone:
    """
    Classify a 0-1 PRO Risk value into a zone (T014).

    Args:
        value: Composite PRO Risk value (0.0 - 1.0)

    Returns:
        RiskZone classification
    """
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"value must be in [0, 1], got {value}")

    for min_val, max_val, zone in ZONE_THRESHOLDS:
        if min_val <= value < max_val:
            return zone

    # Edge case: exactly 1.0
    return "extreme_greed"


# =============================================================================
# Confidence Calculation (T015)
# =============================================================================


def calculate_confidence(components: dict[str, float | None]) -> float:
    """
    Calculate data availability confidence based on available components (T015).

    Confidence is the sum of weights for available (non-None) components.

    Args:
        components: Dict of metric_name -> normalized score (or None if unavailable)

    Returns:
        Confidence score (0.0 - 1.0)
    """
    available_weight = sum(
        COMPONENT_WEIGHTS.get(k, 0.0) for k, v in components.items() if v is not None
    )
    return min(1.0, available_weight)


# =============================================================================
# Main Aggregation Function (T016)
# =============================================================================


def _validate_score(name: str, value: float | None) -> float | None:
    """Validate and clamp a component score to [0, 1] range."""
    if value is None:
        return None
    # Clamp to valid range (normalized scores must be in [0, 1])
    return max(0.0, min(1.0, float(value)))


def calculate_pro_risk(
    mvrv_z: float | None = None,
    sopr: float | None = None,
    nupl: float | None = None,
    reserve_risk: float | None = None,
    puell: float | None = None,
    hodl_waves: float | None = None,
    target_date: datetime | date | None = None,
    block_height: int | None = None,
) -> ProRiskResult:
    """
    Calculate composite PRO Risk metric from component scores (T016).

    Each component should already be normalized to 0-1 percentile.
    This function aggregates using weighted average.
    Out-of-range values are clamped to [0, 1].

    Args:
        mvrv_z: Normalized MVRV Z-Score (0-1)
        sopr: Normalized SOPR (0-1)
        nupl: Normalized NUPL (0-1)
        reserve_risk: Normalized Reserve Risk (0-1)
        puell: Normalized Puell Multiple (0-1)
        hodl_waves: Normalized HODL Waves (0-1)
        target_date: Date for the calculation (default: today)
        block_height: Optional block height at calculation time

    Returns:
        ProRiskResult with composite value, zone, and components
    """
    # Validate and clamp input scores
    mvrv_z = _validate_score("mvrv_z", mvrv_z)
    sopr = _validate_score("sopr", sopr)
    nupl = _validate_score("nupl", nupl)
    reserve_risk = _validate_score("reserve_risk", reserve_risk)
    puell = _validate_score("puell", puell)
    hodl_waves = _validate_score("hodl_waves", hodl_waves)

    if target_date is None:
        target_date = datetime.utcnow()
    elif isinstance(target_date, date) and not isinstance(target_date, datetime):
        target_date = datetime.combine(target_date, datetime.min.time())

    # Build components dict
    components_raw: dict[str, float | None] = {
        "mvrv_z": mvrv_z,
        "sopr": sopr,
        "nupl": nupl,
        "reserve_risk": reserve_risk,
        "puell": puell,
        "hodl_waves": hodl_waves,
    }

    # Calculate confidence from available data
    confidence = calculate_confidence(components_raw)

    # Calculate weighted average (only from available components)
    weighted_sum = 0.0
    weight_sum = 0.0

    for metric_name, score in components_raw.items():
        if score is not None:
            weight = COMPONENT_WEIGHTS[metric_name]
            weighted_sum += score * weight
            weight_sum += weight

    # Avoid division by zero
    if weight_sum > 0:
        composite_value = weighted_sum / weight_sum
    else:
        composite_value = 0.5  # No data - neutral

    # Clamp to [0, 1]
    composite_value = max(0.0, min(1.0, composite_value))

    # Classify zone
    zone = classify_zone(composite_value)

    # Build final components dict (only non-None values)
    components_final = {k: v for k, v in components_raw.items() if v is not None}

    return ProRiskResult(
        date=target_date,
        value=composite_value,
        zone=zone,
        components=components_final,
        confidence=confidence,
        block_height=block_height,
        updated_at=datetime.utcnow(),
    )


# =============================================================================
# Component Fetchers (T017) - Placeholder implementations
# =============================================================================


def fetch_mvrv_z(target_date: datetime) -> tuple[float | None, int]:
    """Fetch MVRV-Z score for date. Returns (raw_value, history_days)."""
    # TODO: Implement using scripts.metrics.realized_metrics
    return None, 0


def fetch_sopr(target_date: datetime) -> tuple[float | None, int]:
    """Fetch SOPR for date. Returns (raw_value, history_days)."""
    # TODO: Implement using scripts.metrics.sopr
    return None, 0


def fetch_nupl(target_date: datetime) -> tuple[float | None, int]:
    """Fetch NUPL for date. Returns (raw_value, history_days)."""
    # TODO: Implement using scripts.metrics.nupl
    return None, 0


def fetch_reserve_risk(target_date: datetime) -> tuple[float | None, int]:
    """Fetch Reserve Risk for date. Returns (raw_value, history_days)."""
    # TODO: Implement using scripts.metrics.reserve_risk
    return None, 0


def fetch_puell(target_date: datetime) -> tuple[float | None, int]:
    """Fetch Puell Multiple for date. Returns (raw_value, history_days)."""
    # TODO: Implement using scripts.metrics.puell_multiple
    return None, 0


def fetch_hodl_waves(target_date: datetime) -> tuple[float | None, int]:
    """Fetch HODL Waves for date. Returns (raw_value, history_days)."""
    # TODO: Implement using scripts.metrics.hodl_waves
    return None, 0


# =============================================================================
# CLI Interface (T018)
# =============================================================================


def parse_date(date_str: str) -> datetime:
    """Parse date string in YYYY/MM/DD or YYYY-MM-DD format."""
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid date format: {date_str}. Use YYYY/MM/DD or YYYY-MM-DD")


def main():
    parser = argparse.ArgumentParser(description="Calculate PRO Risk Metric (spec-033)")
    parser.add_argument(
        "-d",
        "--date",
        type=str,
        default=None,
        help="Target date (YYYY/MM/DD or YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    # Parse target date
    if args.date:
        target_date = parse_date(args.date)
    else:
        target_date = datetime.utcnow()

    # TODO: Fetch all component metrics and normalize them
    # For now, return a placeholder result
    result = calculate_pro_risk(
        mvrv_z=None,
        sopr=None,
        nupl=None,
        reserve_risk=None,
        puell=None,
        hodl_waves=None,
        target_date=target_date,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"PRO Risk for {result.date.strftime('%Y-%m-%d')}")
        print(f"  Value: {result.value:.4f}")
        print(f"  Zone: {result.zone}")
        print(f"  Confidence: {result.confidence:.2%}")
        if result.components:
            print("  Components:")
            for name, score in result.components.items():
                print(f"    {name}: {score:.4f}")


if __name__ == "__main__":
    main()
