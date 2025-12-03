#!/usr/bin/env python3
"""
Pydantic model for Urgency Metrics
Task T008: Data model for fee market conditions and urgency thresholds

Represents current mempool fee conditions used for urgency scoring.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Dict
from datetime import datetime, timezone
from enum import Enum


class CongestionLevel(str, Enum):
    """Mempool congestion classification"""

    LOW = "low"  # <10 MB, fees low
    MEDIUM = "medium"  # 10-50 MB, moderate fees
    HIGH = "high"  # 50-100 MB, high fees
    EXTREME = "extreme"  # >100 MB, very high fees


class UrgencyMetrics(BaseModel):
    """
    Current fee market conditions for urgency scoring

    Tracks mempool fee percentiles and congestion levels to
    dynamically calibrate urgency scores for whale transactions.
    """

    # Block context
    current_block_height: int = Field(
        ..., description="Current blockchain height", ge=0
    )

    # Fee percentiles (sat/vB)
    fee_percentiles: Dict[str, float] = Field(
        ...,
        description="Fee rate percentiles (p10, p25, p50, p75, p90)",
    )

    # Confirmation estimates
    estimated_blocks_to_confirmation: Dict[str, int] = Field(
        ...,
        description="Estimated blocks for different fee levels (low_fee, medium_fee, high_fee)",
    )

    # Mempool state
    mempool_size_mb: float = Field(
        ..., description="Current mempool size in megabytes", ge=0.0
    )

    congestion_level: CongestionLevel = Field(
        ..., description="Current congestion classification"
    )

    # Metadata
    last_update: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When these metrics were last updated",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_block_height": 850000,
                "fee_percentiles": {
                    "p10": 5.0,
                    "p25": 10.0,
                    "p50": 20.0,
                    "p75": 35.0,
                    "p90": 50.0,
                },
                "estimated_blocks_to_confirmation": {
                    "low_fee": 6,
                    "medium_fee": 3,
                    "high_fee": 1,
                },
                "mempool_size_mb": 45.2,
                "congestion_level": "medium",
                "last_update": "2025-11-07T16:00:00Z",
            }
        },
        use_enum_values=True,
    )

    @field_validator("fee_percentiles")
    @classmethod
    def validate_percentiles(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Validate fee percentiles are present and ordered"""
        required = {"p10", "p25", "p50", "p75", "p90"}
        if not required.issubset(v.keys()):
            raise ValueError(
                f"Missing required percentiles: {required - set(v.keys())}"
            )

        # Check ordering
        values = [v[k] for k in ["p10", "p25", "p50", "p75", "p90"]]
        if values != sorted(values):
            raise ValueError("Fee percentiles must be in ascending order")

        return v

    @field_validator("estimated_blocks_to_confirmation")
    @classmethod
    def validate_estimates(cls, v: Dict[str, int]) -> Dict[str, int]:
        """Validate confirmation estimates are present"""
        required = {"low_fee", "medium_fee", "high_fee"}
        if not required.issubset(v.keys()):
            raise ValueError(f"Missing required estimates: {required - set(v.keys())}")

        # Check ordering (high fee should confirm faster)
        if not (v["high_fee"] <= v["medium_fee"] <= v["low_fee"]):
            raise ValueError(
                "Estimates must be ordered: high_fee <= medium_fee <= low_fee"
            )

        return v

    def calculate_urgency_score(self, transaction_fee_rate: float) -> float:
        """
        Calculate urgency score based on transaction fee rate

        Args:
            transaction_fee_rate: Fee rate in sat/vB

        Returns:
            Urgency score between 0.0 and 1.0
        """
        # Get percentile boundaries
        p10 = self.fee_percentiles["p10"]
        p25 = self.fee_percentiles["p25"]
        p50 = self.fee_percentiles["p50"]
        p75 = self.fee_percentiles["p75"]
        p90 = self.fee_percentiles["p90"]

        # Map fee rate to urgency score
        if transaction_fee_rate <= p10:
            # Very low fee - 0.0 to 0.2
            return min(0.2, transaction_fee_rate / p10 * 0.2)
        elif transaction_fee_rate <= p25:
            # Low fee - 0.2 to 0.4
            progress = (transaction_fee_rate - p10) / (p25 - p10)
            return 0.2 + (progress * 0.2)
        elif transaction_fee_rate <= p50:
            # Medium fee - 0.4 to 0.6
            progress = (transaction_fee_rate - p25) / (p50 - p25)
            return 0.4 + (progress * 0.2)
        elif transaction_fee_rate <= p75:
            # High fee - 0.6 to 0.8
            progress = (transaction_fee_rate - p50) / (p75 - p50)
            return 0.6 + (progress * 0.2)
        elif transaction_fee_rate <= p90:
            # Very high fee - 0.8 to 0.95
            progress = (transaction_fee_rate - p75) / (p90 - p75)
            return 0.8 + (progress * 0.15)
        else:
            # Extreme fee - 0.95 to 1.0
            # Cap at 1.0 even for very high fees
            excess = min((transaction_fee_rate - p90) / p90, 1.0)
            return min(1.0, 0.95 + (excess * 0.05))

    def predict_confirmation_block(self, transaction_fee_rate: float) -> int:
        """
        Predict confirmation block based on fee rate

        Args:
            transaction_fee_rate: Fee rate in sat/vB

        Returns:
            Predicted block height for confirmation
        """
        # Get percentile boundaries
        p50 = self.fee_percentiles["p50"]
        p75 = self.fee_percentiles["p75"]

        # Estimate blocks until confirmation
        if transaction_fee_rate >= p75:
            blocks_ahead = self.estimated_blocks_to_confirmation["high_fee"]
        elif transaction_fee_rate >= p50:
            blocks_ahead = self.estimated_blocks_to_confirmation["medium_fee"]
        else:
            blocks_ahead = self.estimated_blocks_to_confirmation["low_fee"]

        return self.current_block_height + blocks_ahead

    def classify_congestion(self) -> CongestionLevel:
        """
        Classify mempool congestion based on size

        Returns:
            CongestionLevel enum
        """
        if self.mempool_size_mb < 10:
            return CongestionLevel.LOW
        elif self.mempool_size_mb < 50:
            return CongestionLevel.MEDIUM
        elif self.mempool_size_mb < 100:
            return CongestionLevel.HIGH
        else:
            return CongestionLevel.EXTREME

    @property
    def is_high_congestion(self) -> bool:
        """Check if mempool is highly congested"""
        return self.congestion_level in (CongestionLevel.HIGH, CongestionLevel.EXTREME)

    @property
    def median_fee(self) -> float:
        """Get median fee rate (p50)"""
        return self.fee_percentiles["p50"]

    @property
    def high_priority_fee(self) -> float:
        """Get high priority fee rate (p75)"""
        return self.fee_percentiles["p75"]


# Example usage and testing
if __name__ == "__main__":
    import json

    # Create urgency metrics
    metrics = UrgencyMetrics(
        current_block_height=850000,
        fee_percentiles={
            "p10": 5.0,
            "p25": 10.0,
            "p50": 20.0,
            "p75": 35.0,
            "p90": 50.0,
        },
        estimated_blocks_to_confirmation={
            "low_fee": 6,
            "medium_fee": 3,
            "high_fee": 1,
        },
        mempool_size_mb=45.2,
        congestion_level=CongestionLevel.MEDIUM,
    )

    print("✅ UrgencyMetrics created successfully")
    print(f"   Block height: {metrics.current_block_height}")
    print(f"   Median fee: {metrics.median_fee} sat/vB")
    print(f"   Mempool size: {metrics.mempool_size_mb} MB")
    print(f"   Congestion: {metrics.congestion_level}")

    # Test urgency scoring
    print("\n📊 Urgency scoring tests:")
    test_fees = [3.0, 15.0, 25.0, 40.0, 60.0, 100.0]
    for fee in test_fees:
        urgency = metrics.calculate_urgency_score(fee)
        predicted_block = metrics.predict_confirmation_block(fee)
        blocks_ahead = predicted_block - metrics.current_block_height
        print(
            f"   Fee {fee:6.1f} sat/vB → Urgency: {urgency:.2f}, "
            f"Confirm in ~{blocks_ahead} blocks"
        )

    # Test JSON serialization
    print("\n📄 JSON representation:")
    print(
        json.dumps(
            {
                "current_block_height": metrics.current_block_height,
                "fee_percentiles": metrics.fee_percentiles,
                "estimated_blocks_to_confirmation": metrics.estimated_blocks_to_confirmation,
                "mempool_size_mb": metrics.mempool_size_mb,
                "congestion_level": metrics.congestion_level,
                "last_update": metrics.last_update.isoformat(),
            },
            indent=2,
        )
    )

    # Test validation
    print("\n✅ Model validation passed")
