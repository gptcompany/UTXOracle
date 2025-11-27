"""
Pydantic models for WebSocket messages.
Task T023: Add Pydantic models for all message types.
"""

from typing import List, Optional, Dict, Any, Literal
from decimal import Decimal
from pydantic import BaseModel, Field


# Base message structure
class BaseMessage(BaseModel):
    """Base structure for all WebSocket messages."""

    type: str = Field(..., description="Message type identifier")
    timestamp: int = Field(..., description="Unix timestamp in milliseconds")
    sequence: int = Field(..., description="Message sequence number")


# Client -> Server Messages


class SubscribeMessage(BaseMessage):
    """Client subscription request."""

    type: Literal["subscribe"] = "subscribe"
    channels: List[str] = Field(..., description="Channels to subscribe to")
    filters: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Optional filters for subscription"
    )


class UnsubscribeMessage(BaseMessage):
    """Client unsubscription request."""

    type: Literal["unsubscribe"] = "unsubscribe"
    channels: List[str] = Field(..., description="Channels to unsubscribe from")


class PingMessage(BaseMessage):
    """Client ping for keep-alive."""

    type: Literal["ping"] = "ping"


class HistoricalRequestMessage(BaseMessage):
    """Request for historical data."""

    type: Literal["historical_request"] = "historical_request"
    data_type: str = Field(
        ..., description="Type of data requested (netflow, transactions)"
    )
    time_range: Dict[str, Any] = Field(..., description="Time range specification")


# Server -> Client Messages


class TransactionData(BaseModel):
    """Whale transaction data."""

    transaction_id: str
    amount_btc: Decimal
    amount_usd: Decimal
    direction: Literal["BUY", "SELL", "TRANSFER"]
    urgency_score: int = Field(..., ge=0, le=100)
    fee_rate: float
    timestamp: str  # ISO format
    block_height: Optional[int] = None
    is_mempool: bool = True
    confidence: float = Field(..., ge=0, le=1)


class TransactionUpdate(BaseMessage):
    """New whale transaction detected."""

    type: Literal["transaction"] = "transaction"
    data: TransactionData


class NetFlowData(BaseModel):
    """Net flow metrics data."""

    period_start: str  # ISO format
    period_end: str  # ISO format
    interval: Literal["1m", "5m", "1h", "24h"]
    net_flow_btc: Decimal
    net_flow_usd: Decimal
    total_buy_btc: Decimal
    total_sell_btc: Decimal
    transaction_count: int
    direction: Literal["ACCUMULATION", "DISTRIBUTION", "NEUTRAL"]
    strength: float = Field(..., ge=0, le=1)
    largest_tx_btc: Optional[Decimal] = None


class NetFlowUpdate(BaseMessage):
    """Aggregated flow metrics update."""

    type: Literal["netflow"] = "netflow"
    data: NetFlowData


class AlertData(BaseModel):
    """Alert notification data."""

    alert_id: str
    transaction_id: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    trigger_type: Literal["SIZE", "URGENCY", "PATTERN", "THRESHOLD"]
    threshold_value: Decimal
    title: str
    message: str
    amount_btc: Decimal
    amount_usd: Decimal
    direction: Literal["BUY", "SELL", "TRANSFER"]


class AlertNotification(BaseMessage):
    """Critical whale movement alert."""

    type: Literal["alert"] = "alert"
    data: AlertData


class HistoricalValue(BaseModel):
    """Single historical data point."""

    timestamp: str  # ISO format
    net_flow_btc: Decimal
    direction: Literal["ACCUMULATION", "DISTRIBUTION", "NEUTRAL"]


class HistoricalResponseData(BaseModel):
    """Historical data response."""

    data_type: str
    time_range: Dict[str, Any]
    values: List[HistoricalValue]


class HistoricalResponse(BaseMessage):
    """Response to historical data request."""

    type: Literal["historical_response"] = "historical_response"
    request_sequence: int = Field(
        ..., description="Sequence number of original request"
    )
    data: HistoricalResponseData


class AckData(BaseModel):
    """Acknowledgment data."""

    request_sequence: int
    status: Literal["success", "error"]
    subscribed_channels: List[str]
    server_time: int


class ConnectionAck(BaseMessage):
    """Connection acknowledgment."""

    type: Literal["ack"] = "ack"
    request_sequence: int
    status: Literal["success", "error"]
    subscribed_channels: List[str] = Field(default_factory=list)
    server_time: int


class ErrorData(BaseModel):
    """Error details."""

    code: str
    message: str
    retry_after: Optional[int] = None


class ErrorMessage(BaseMessage):
    """Error notification."""

    type: Literal["error"] = "error"
    error: ErrorData


class PongMessage(BaseMessage):
    """Server pong response."""

    type: Literal["pong"] = "pong"
    ping_sequence: int = Field(..., description="Sequence number of ping message")
    server_time: int


class BatchMessage(BaseMessage):
    """Multiple updates in single message."""

    type: Literal["batch"] = "batch"
    messages: List[Dict[str, Any]] = Field(..., description="Array of batched messages")


# Message router types
ClientMessage = (
    SubscribeMessage | UnsubscribeMessage | PingMessage | HistoricalRequestMessage
)

ServerMessage = (
    TransactionUpdate
    | NetFlowUpdate
    | AlertNotification
    | HistoricalResponse
    | ConnectionAck
    | ErrorMessage
    | PongMessage
    | BatchMessage
)


# Validation helpers
def validate_message_type(data: Dict[str, Any]) -> BaseMessage:
    """
    Validate and parse incoming WebSocket message.

    Args:
        data: Raw message dictionary

    Returns:
        Parsed message object

    Raises:
        ValueError: If message type is invalid
    """
    msg_type = data.get("type")

    type_map = {
        "subscribe": SubscribeMessage,
        "unsubscribe": UnsubscribeMessage,
        "ping": PingMessage,
        "historical_request": HistoricalRequestMessage,
        "transaction": TransactionUpdate,
        "netflow": NetFlowUpdate,
        "alert": AlertNotification,
        "historical_response": HistoricalResponse,
        "ack": ConnectionAck,
        "error": ErrorMessage,
        "pong": PongMessage,
        "batch": BatchMessage,
    }

    message_class = type_map.get(msg_type)
    if not message_class:
        raise ValueError(f"Unknown message type: {msg_type}")

    return message_class(**data)


# Filter models
class TransactionFilter(BaseModel):
    """Filters for transaction subscriptions."""

    min_amount: Optional[Decimal] = Field(
        default=Decimal("100"), description="Minimum BTC amount"
    )
    max_amount: Optional[Decimal] = None
    urgency_threshold: Optional[int] = Field(default=0, ge=0, le=100)
    directions: Optional[List[Literal["BUY", "SELL", "TRANSFER"]]] = None


class NetFlowFilter(BaseModel):
    """Filters for net flow subscriptions."""

    interval: Literal["1m", "5m", "1h", "24h"] = "5m"
    min_strength: Optional[float] = Field(default=0, ge=0, le=1)


class AlertFilter(BaseModel):
    """Filters for alert subscriptions."""

    min_severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"
    trigger_types: Optional[List[str]] = None
