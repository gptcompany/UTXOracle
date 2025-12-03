#!/usr/bin/env python3
"""
Pydantic model for Mempool Whale Signals
Task T006: Data model for whale transaction detection events

Represents a detected whale transaction with classification and urgency scoring.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum


class FlowType(str, Enum):
    """Exchange flow direction classification"""

    INFLOW = "inflow"  # Moving TO exchange (potential sell pressure)
    OUTFLOW = "outflow"  # Moving FROM exchange (potential buy pressure)
    INTERNAL = "internal"  # Exchange-to-exchange transfer
    UNKNOWN = "unknown"  # Cannot classify


class MempoolWhaleSignal(BaseModel):
    """
    Whale transaction signal from mempool monitoring

    Represents a >100 BTC transaction detected in the mempool with
    classification, urgency scoring, and prediction metadata.
    """

    # Core transaction data
    prediction_id: str = Field(
        ..., description="Unique identifier for this prediction (UUID)"
    )
    transaction_id: str = Field(
        ...,
        description="Bitcoin transaction hash (64-character hex)",
        min_length=64,
        max_length=64,
    )

    # Classification
    flow_type: FlowType = Field(
        ..., description="Exchange flow direction classification"
    )

    # Volume metrics
    btc_value: float = Field(
        ...,
        description="Total BTC value of transaction",
        gt=100.0,  # Must be >100 BTC
    )

    # Fee analysis
    fee_rate: float = Field(
        ...,
        description="Transaction fee rate in sat/vB",
        gt=0.0,  # Must be positive
    )

    urgency_score: float = Field(
        ...,
        description="Fee-based urgency score (0.0-1.0)",
        ge=0.0,
        le=1.0,  # Must be in range [0, 1]
    )

    # Transaction flags
    rbf_enabled: bool = Field(
        ..., description="Whether Replace-By-Fee is enabled for this transaction"
    )

    # Timestamps
    detection_timestamp: datetime = Field(
        ..., description="When this whale was detected in mempool"
    )

    # Predictions
    predicted_confirmation_block: Optional[int] = Field(
        None, description="Estimated block height for confirmation", ge=0
    )

    # Exchange metadata
    exchange_addresses: List[str] = Field(
        default_factory=list,
        description="List of identified exchange addresses involved",
    )

    confidence_score: Optional[float] = Field(
        None,
        description="Confidence in flow_type classification (0.0-1.0)",
        ge=0.0,
        le=1.0,
    )

    # Modification tracking
    was_modified: bool = Field(
        default=False, description="Whether transaction was replaced via RBF"
    )

    # Metadata
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Database record creation timestamp",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "prediction_id": "550e8400-e29b-41d4-a716-446655440000",
                "transaction_id": "a1b2c3d4e5f6789012345678901234567890abcdef0123456789abcdef012345",
                "flow_type": "inflow",
                "btc_value": 150.5,
                "fee_rate": 25.0,
                "urgency_score": 0.75,
                "rbf_enabled": False,
                "detection_timestamp": "2025-11-07T16:00:00Z",
                "predicted_confirmation_block": 850000,
                "exchange_addresses": ["bc1qexample...", "3ExampleAddr..."],
                "confidence_score": 0.85,
                "was_modified": False,
            }
        },
        # Use enum values in JSON
        use_enum_values=True,
    )

    @field_validator("transaction_id")
    @classmethod
    def validate_txid(cls, v: str) -> str:
        """Validate transaction ID format (64 hex characters)"""
        if not all(c in "0123456789abcdef" for c in v.lower()):
            raise ValueError("Transaction ID must be hexadecimal")
        return v.lower()

    @field_validator("exchange_addresses")
    @classmethod
    def validate_addresses(cls, v: List[str]) -> List[str]:
        """Validate exchange addresses are not empty strings"""
        return [addr.strip() for addr in v if addr and addr.strip()]

    def to_db_dict(self) -> dict:
        """
        Convert to dictionary format for database insertion

        Returns:
            Dict with proper types for DuckDB
        """
        return {
            "prediction_id": self.prediction_id,
            "transaction_id": self.transaction_id,
            "flow_type": self.flow_type,  # Already a string due to use_enum_values
            "btc_value": self.btc_value,
            "fee_rate": self.fee_rate,
            "urgency_score": self.urgency_score,
            "rbf_enabled": self.rbf_enabled,
            "detection_timestamp": self.detection_timestamp.isoformat(),
            "predicted_confirmation_block": self.predicted_confirmation_block,
            "exchange_addresses": ",".join(self.exchange_addresses)
            if self.exchange_addresses
            else None,
            "confidence_score": self.confidence_score,
            "was_modified": self.was_modified,
        }

    def to_broadcast_dict(self) -> dict:
        """
        Convert to dictionary format for WebSocket broadcasting

        Returns:
            Dict with JSON-serializable values
        """
        return {
            "type": "whale_alert",
            "prediction_id": self.prediction_id,
            "transaction_id": self.transaction_id,
            "flow_type": self.flow_type,  # Already a string due to use_enum_values
            "btc_value": self.btc_value,
            "fee_rate": self.fee_rate,
            "urgency_score": self.urgency_score,
            "rbf_enabled": self.rbf_enabled,
            "detection_timestamp": self.detection_timestamp.isoformat(),
            "predicted_confirmation_block": self.predicted_confirmation_block,
            "exchange_addresses": self.exchange_addresses,
            "confidence_score": self.confidence_score,
            "was_modified": self.was_modified,
        }

    @property
    def is_high_urgency(self) -> bool:
        """Check if this is a high-urgency whale transaction"""
        return self.urgency_score > 0.7

    @property
    def is_large_whale(self) -> bool:
        """Check if this is a particularly large whale (>500 BTC)"""
        return self.btc_value > 500.0

    @property
    def expected_confirmation_soon(self) -> bool:
        """Check if confirmation is expected soon (high fee)"""
        return self.urgency_score > 0.8


# Example usage and testing
if __name__ == "__main__":
    import uuid
    import json

    # Create a whale signal
    signal = MempoolWhaleSignal(
        prediction_id=str(uuid.uuid4()),
        transaction_id="a" * 64,  # 64 hex characters
        flow_type=FlowType.INFLOW,
        btc_value=150.5,
        fee_rate=25.0,
        urgency_score=0.75,
        rbf_enabled=False,
        detection_timestamp=datetime.now(timezone.utc),
        predicted_confirmation_block=850000,
        exchange_addresses=["bc1qexample123", "3ExampleAddr456"],
        confidence_score=0.85,
    )

    print("✅ MempoolWhaleSignal created successfully")
    print(f"   Transaction: {signal.transaction_id[:16]}...")
    print(f"   Flow: {signal.flow_type}")
    print(f"   Value: {signal.btc_value} BTC")
    print(f"   Urgency: {signal.urgency_score}")
    print(f"   High urgency: {signal.is_high_urgency}")

    # Test serialization
    print("\n📄 JSON representation:")
    print(json.dumps(signal.to_broadcast_dict(), indent=2))

    # Test database format
    print("\n💾 Database format:")
    print(json.dumps(signal.to_db_dict(), indent=2))

    # Test validation
    print("\n✅ Model validation passed")
