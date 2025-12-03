#!/usr/bin/env python3
"""
Pydantic model for Prediction Outcomes
Task T007: Data model for tracking prediction accuracy

Represents the actual outcome of a whale prediction after confirmation/drop.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
from datetime import datetime, timezone
from enum import Enum


class OutcomeType(str, Enum):
    """Actual outcome of predicted transaction"""

    CONFIRMED = "confirmed"  # Transaction confirmed on-chain
    DROPPED = "dropped"  # Transaction dropped from mempool
    REPLACED = "replaced"  # Transaction replaced via RBF


class PredictionOutcome(BaseModel):
    """
    Tracks the actual outcome of a whale prediction

    Records what actually happened to a predicted transaction and
    calculates accuracy metrics for correlation analysis.
    """

    # Identity
    outcome_id: str = Field(
        ..., description="Unique identifier for this outcome (UUID)"
    )
    prediction_id: str = Field(
        ..., description="Reference to original prediction (foreign key)"
    )
    transaction_id: str = Field(
        ...,
        description="Bitcoin transaction hash (64-character hex)",
        min_length=64,
        max_length=64,
    )

    # Original prediction
    predicted_flow: str = Field(
        ...,
        description="Originally predicted flow type (inflow/outflow/internal/unknown)",
    )

    # Actual outcome
    actual_outcome: Optional[OutcomeType] = Field(
        None, description="What actually happened to the transaction"
    )

    # Confirmation metrics
    confirmation_time: Optional[datetime] = Field(
        None, description="When transaction was confirmed (if applicable)"
    )
    confirmation_block: Optional[int] = Field(
        None, description="Block height where transaction confirmed", ge=0
    )

    # Accuracy metrics
    accuracy_score: Optional[float] = Field(
        None,
        description="Accuracy score for this prediction (0.0-1.0)",
        ge=0.0,
        le=1.0,
    )
    time_to_confirmation: Optional[int] = Field(
        None, description="Minutes from detection to confirmation", ge=0
    )

    # Fee analysis
    final_fee_rate: Optional[float] = Field(
        None, description="Final fee rate when confirmed/replaced", gt=0.0
    )

    # Metadata
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Database record creation timestamp",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "outcome_id": "660e9500-f39c-52e5-b827-557766551111",
                "prediction_id": "550e8400-e29b-41d4-a716-446655440000",
                "transaction_id": "a1b2c3d4e5f6789012345678901234567890abcdef0123456789abcdef012345",
                "predicted_flow": "inflow",
                "actual_outcome": "confirmed",
                "confirmation_time": "2025-11-07T16:30:00Z",
                "confirmation_block": 850001,
                "accuracy_score": 0.95,
                "time_to_confirmation": 25,
                "final_fee_rate": 25.0,
            }
        },
        use_enum_values=True,
    )

    @field_validator("transaction_id")
    @classmethod
    def validate_txid(cls, v: str) -> str:
        """Validate transaction ID format (64 hex characters)"""
        if not all(c in "0123456789abcdef" for c in v.lower()):
            raise ValueError("Transaction ID must be hexadecimal")
        return v.lower()

    def calculate_accuracy(
        self, predicted_urgency: float, predicted_block: Optional[int]
    ) -> float:
        """
        Calculate accuracy score based on prediction vs outcome

        Args:
            predicted_urgency: Original urgency score (0.0-1.0)
            predicted_block: Originally predicted confirmation block

        Returns:
            Accuracy score (0.0-1.0)
        """
        if not self.actual_outcome or self.actual_outcome != OutcomeType.CONFIRMED:
            # Transaction didn't confirm - partial score based on urgency
            return 0.3 if predicted_urgency < 0.5 else 0.1

        # Transaction confirmed - calculate based on timing accuracy
        if predicted_block and self.confirmation_block:
            block_diff = abs(self.confirmation_block - predicted_block)
            # Perfect if within 1 block, degrading to 0.5 at 6+ blocks
            timing_score = max(0.5, 1.0 - (block_diff * 0.1))
        else:
            timing_score = 0.7  # Partial score if no block prediction

        # Factor in urgency prediction accuracy
        if self.time_to_confirmation:
            # High urgency should confirm quickly
            expected_fast = predicted_urgency > 0.7
            actual_fast = self.time_to_confirmation < 30  # 30 minutes
            urgency_correct = expected_fast == actual_fast
            urgency_score = 1.0 if urgency_correct else 0.6
        else:
            urgency_score = 0.8  # Partial score

        # Combined score
        accuracy = (timing_score * 0.6) + (urgency_score * 0.4)
        return round(accuracy, 2)

    def to_db_dict(self) -> dict:
        """
        Convert to dictionary format for database insertion

        Returns:
            Dict with proper types for DuckDB
        """
        return {
            "outcome_id": self.outcome_id,
            "prediction_id": self.prediction_id,
            "transaction_id": self.transaction_id,
            "predicted_flow": self.predicted_flow,
            "actual_outcome": self.actual_outcome if self.actual_outcome else None,
            "confirmation_time": self.confirmation_time.isoformat()
            if self.confirmation_time
            else None,
            "confirmation_block": self.confirmation_block,
            "accuracy_score": self.accuracy_score,
            "time_to_confirmation": self.time_to_confirmation,
            "final_fee_rate": self.final_fee_rate,
        }

    @property
    def was_accurate(self) -> bool:
        """Check if prediction was accurate (>0.7 accuracy)"""
        return self.accuracy_score is not None and self.accuracy_score > 0.7

    @property
    def was_confirmed(self) -> bool:
        """Check if transaction was confirmed"""
        return self.actual_outcome == OutcomeType.CONFIRMED

    @property
    def was_replaced(self) -> bool:
        """Check if transaction was replaced via RBF"""
        return self.actual_outcome == OutcomeType.REPLACED


# Example usage and testing
if __name__ == "__main__":
    import uuid
    import json

    # Create an outcome for a confirmed transaction
    outcome = PredictionOutcome(
        outcome_id=str(uuid.uuid4()),
        prediction_id=str(uuid.uuid4()),
        transaction_id="b" * 64,
        predicted_flow="inflow",
        actual_outcome=OutcomeType.CONFIRMED,
        confirmation_time=datetime.now(timezone.utc),
        confirmation_block=850001,
        time_to_confirmation=25,
        final_fee_rate=25.0,
    )

    # Calculate accuracy
    accuracy = outcome.calculate_accuracy(
        predicted_urgency=0.75, predicted_block=850001
    )
    outcome.accuracy_score = accuracy

    print("✅ PredictionOutcome created successfully")
    print(f"   Transaction: {outcome.transaction_id[:16]}...")
    print(f"   Predicted: {outcome.predicted_flow}")
    print(f"   Actual: {outcome.actual_outcome}")
    print(f"   Accuracy: {outcome.accuracy_score}")
    print(f"   Was accurate: {outcome.was_accurate}")
    print(f"   Was confirmed: {outcome.was_confirmed}")

    # Test serialization
    print("\n💾 Database format:")
    print(json.dumps(outcome.to_db_dict(), indent=2, default=str))

    # Test edge cases
    print("\n🧪 Testing edge cases:")

    # Dropped transaction
    dropped = PredictionOutcome(
        outcome_id=str(uuid.uuid4()),
        prediction_id=str(uuid.uuid4()),
        transaction_id="c" * 64,
        predicted_flow="outflow",
        actual_outcome=OutcomeType.DROPPED,
    )
    dropped.accuracy_score = dropped.calculate_accuracy(
        predicted_urgency=0.3, predicted_block=None
    )
    print(f"   Dropped tx (low urgency): accuracy={dropped.accuracy_score}")

    # Replaced transaction
    replaced = PredictionOutcome(
        outcome_id=str(uuid.uuid4()),
        prediction_id=str(uuid.uuid4()),
        transaction_id="d" * 64,
        predicted_flow="inflow",
        actual_outcome=OutcomeType.REPLACED,
        final_fee_rate=50.0,  # Increased fee
    )
    replaced.accuracy_score = replaced.calculate_accuracy(
        predicted_urgency=0.5, predicted_block=None
    )
    print(f"   Replaced tx (RBF): accuracy={replaced.accuracy_score}")

    print("\n✅ Model validation passed")
