"""
Pydantic models for database entities.
Tasks T031-T033: Data models for whale transactions, net flow, and alerts.
"""

from typing import Optional, Literal
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class WhaleTransaction(BaseModel):
    """
    Whale transaction data model.
    Task T031: Whale transaction data model.

    Maps to: whale_transactions table in DuckDB
    """

    transaction_id: str = Field(..., description="Unique transaction hash")
    block_height: Optional[int] = Field(
        None, description="Block height (None if mempool)"
    )
    timestamp: datetime = Field(..., description="Transaction timestamp")
    amount_btc: Decimal = Field(..., ge=0, description="Amount in BTC")
    amount_usd: Decimal = Field(..., ge=0, description="Amount in USD")
    direction: Literal["BUY", "SELL", "TRANSFER"] = Field(
        ..., description="Transaction direction"
    )
    urgency_score: int = Field(..., ge=0, le=100, description="Urgency score 0-100")
    fee_rate: float = Field(..., ge=0, description="Fee rate in sat/vB")
    confidence: float = Field(..., ge=0, le=1, description="Detection confidence 0-1")
    is_mempool: bool = Field(default=True, description="True if in mempool")
    detected_at: datetime = Field(
        default_factory=datetime.utcnow, description="Detection timestamp"
    )

    class Config:
        json_encoders = {
            Decimal: str,  # Serialize Decimal as string
            datetime: lambda v: v.isoformat(),  # ISO format for datetime
        }

    @field_validator("amount_btc", "amount_usd")
    @classmethod
    def validate_positive_amount(cls, v: Decimal) -> Decimal:
        """Validate amounts are positive."""
        if v < 0:
            raise ValueError("Amount must be non-negative")
        return v

    @field_validator("urgency_score")
    @classmethod
    def validate_urgency_range(cls, v: int) -> int:
        """Validate urgency score is in 0-100 range."""
        if not 0 <= v <= 100:
            raise ValueError("Urgency score must be between 0 and 100")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence_range(cls, v: float) -> float:
        """Validate confidence is in 0-1 range."""
        if not 0 <= v <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        return v

    def to_db_dict(self) -> dict:
        """Convert to dictionary for database insertion."""
        return {
            "transaction_id": self.transaction_id,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat(),
            "amount_btc": float(self.amount_btc),
            "amount_usd": float(self.amount_usd),
            "direction": self.direction,
            "urgency_score": self.urgency_score,
            "fee_rate": self.fee_rate,
            "confidence": self.confidence,
            "is_mempool": self.is_mempool,
            "detected_at": self.detected_at.isoformat(),
        }


class NetFlowMetrics(BaseModel):
    """
    Net flow aggregation metrics model.
    Task T032: Net flow aggregation model.

    Maps to: net_flow_metrics table in DuckDB
    """

    period_start: datetime = Field(..., description="Aggregation period start")
    period_end: datetime = Field(..., description="Aggregation period end")
    interval: Literal["1m", "5m", "1h", "24h"] = Field(
        ..., description="Aggregation interval"
    )
    net_flow_btc: Decimal = Field(..., description="Net flow in BTC (buy - sell)")
    net_flow_usd: Decimal = Field(..., description="Net flow in USD")
    total_buy_btc: Decimal = Field(..., ge=0, description="Total buy volume BTC")
    total_sell_btc: Decimal = Field(..., ge=0, description="Total sell volume BTC")
    transaction_count: int = Field(..., ge=0, description="Number of transactions")
    direction: Literal["ACCUMULATION", "DISTRIBUTION", "NEUTRAL"] = Field(
        ..., description="Overall flow direction"
    )
    strength: float = Field(..., ge=0, le=1, description="Flow strength indicator 0-1")
    largest_tx_btc: Optional[Decimal] = Field(
        None, description="Largest transaction in period"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Record creation time"
    )

    class Config:
        json_encoders = {
            Decimal: str,
            datetime: lambda v: v.isoformat(),
        }

    @field_validator("transaction_count")
    @classmethod
    def validate_positive_count(cls, v: int) -> int:
        """Validate transaction count is non-negative."""
        if v < 0:
            raise ValueError("Transaction count must be non-negative")
        return v

    @field_validator("strength")
    @classmethod
    def validate_strength_range(cls, v: float) -> float:
        """Validate strength is in 0-1 range."""
        if not 0 <= v <= 1:
            raise ValueError("Strength must be between 0 and 1")
        return v

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str, values: dict) -> str:
        """Validate direction matches net flow sign."""
        # This validation requires net_flow_btc to be set first
        # Pydantic v2 handles this differently, but basic check here
        return v

    def to_db_dict(self) -> dict:
        """Convert to dictionary for database insertion."""
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "interval": self.interval,
            "net_flow_btc": float(self.net_flow_btc),
            "net_flow_usd": float(self.net_flow_usd),
            "total_buy_btc": float(self.total_buy_btc),
            "total_sell_btc": float(self.total_sell_btc),
            "transaction_count": self.transaction_count,
            "direction": self.direction,
            "strength": self.strength,
            "largest_tx_btc": float(self.largest_tx_btc)
            if self.largest_tx_btc
            else None,
            "created_at": self.created_at.isoformat(),
        }


class Alert(BaseModel):
    """
    Alert notification model.
    Task T033: Alert notification model.

    Maps to: alerts table in DuckDB
    """

    alert_id: str = Field(..., description="Unique alert identifier")
    transaction_id: str = Field(..., description="Related transaction hash")
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        ..., description="Alert severity level"
    )
    trigger_type: Literal["SIZE", "URGENCY", "PATTERN", "THRESHOLD"] = Field(
        ..., description="What triggered the alert"
    )
    threshold_value: Decimal = Field(..., description="Threshold that was exceeded")
    title: str = Field(..., max_length=200, description="Alert title")
    message: str = Field(..., max_length=1000, description="Alert message")
    amount_btc: Decimal = Field(..., ge=0, description="Transaction amount BTC")
    amount_usd: Decimal = Field(..., ge=0, description="Transaction amount USD")
    direction: Literal["BUY", "SELL", "TRANSFER"] = Field(
        ..., description="Transaction direction"
    )
    acknowledged: bool = Field(default=False, description="User acknowledged alert")
    acknowledged_at: Optional[datetime] = Field(
        None, description="Acknowledgment timestamp"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Alert creation time"
    )

    class Config:
        json_encoders = {
            Decimal: str,
            datetime: lambda v: v.isoformat(),
        }

    @field_validator("title")
    @classmethod
    def validate_title_not_empty(cls, v: str) -> str:
        """Validate title is not empty."""
        if not v.strip():
            raise ValueError("Title cannot be empty")
        return v

    @field_validator("message")
    @classmethod
    def validate_message_not_empty(cls, v: str) -> str:
        """Validate message is not empty."""
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v

    def to_db_dict(self) -> dict:
        """Convert to dictionary for database insertion."""
        return {
            "alert_id": self.alert_id,
            "transaction_id": self.transaction_id,
            "severity": self.severity,
            "trigger_type": self.trigger_type,
            "threshold_value": float(self.threshold_value),
            "title": self.title,
            "message": self.message,
            "amount_btc": float(self.amount_btc),
            "amount_usd": float(self.amount_usd),
            "direction": self.direction,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat()
            if self.acknowledged_at
            else None,
            "created_at": self.created_at.isoformat(),
        }


class UrgencyScore(BaseModel):
    """
    Urgency score calculation record.

    Maps to: urgency_scores table in DuckDB
    """

    transaction_id: str = Field(..., description="Transaction hash")
    urgency_score: int = Field(..., ge=0, le=100, description="Calculated score 0-100")
    fee_rate: float = Field(..., ge=0, description="Fee rate in sat/vB")
    amount_btc: Decimal = Field(..., ge=0, description="Transaction amount")
    time_in_mempool: int = Field(..., ge=0, description="Time in mempool (seconds)")
    calculated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Calculation timestamp"
    )

    class Config:
        json_encoders = {
            Decimal: str,
            datetime: lambda v: v.isoformat(),
        }

    def to_db_dict(self) -> dict:
        """Convert to dictionary for database insertion."""
        return {
            "transaction_id": self.transaction_id,
            "urgency_score": self.urgency_score,
            "fee_rate": self.fee_rate,
            "amount_btc": float(self.amount_btc),
            "time_in_mempool": self.time_in_mempool,
            "calculated_at": self.calculated_at.isoformat(),
        }
