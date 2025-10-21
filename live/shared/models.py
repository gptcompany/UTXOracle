"""
Shared Data Models

BLACK BOX INTERFACE CONTRACTS between all 5 modules.

This is the ONLY shared file between modules. All inter-module communication
uses these data structures.

Data Flow:
    Bitcoin Core ZMQ
        ↓ (bytes)
    [Module 1: ZMQ Listener]
        ↓ RawTransaction (dataclass)
    [Module 2: TX Processor]
        ↓ ProcessedTransaction (dataclass)
    [Module 3: Mempool Analyzer]
        ↓ MempoolState (dataclass)
    [Module 4: Data Streamer]
        ↓ WebSocketMessage (Pydantic → JSON)
    [Module 5: Visualization]
        ↓ Canvas 2D rendering
    Browser Display
"""

from dataclasses import dataclass
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Internal Models (Python Dataclasses)
# =============================================================================


@dataclass
class RawTransaction:
    """
    Raw transaction received from Bitcoin Core ZMQ.

    This is the black box interface between Module 1 (ZMQ Listener) and Module 2 (TX Processor).

    Validation Rules:
    - raw_bytes: Must be non-empty
    - timestamp: Must be positive float (Unix epoch seconds)
    - topic: Must be exactly 'rawtx'
    """

    raw_bytes: bytes
    """Complete binary transaction data"""

    timestamp: float
    """Unix timestamp (seconds) when transaction was received"""

    topic: Literal["rawtx"]
    """ZMQ topic identifier (always 'rawtx' for mempool transactions)"""

    def __post_init__(self):
        """Validate fields after initialization"""
        if not self.raw_bytes:
            raise ValueError("raw_bytes must be non-empty")
        if self.timestamp <= 0:
            raise ValueError("timestamp must be positive")
        if self.topic != "rawtx":
            raise ValueError("topic must be 'rawtx'")


@dataclass
class ProcessedTransaction:
    """
    Transaction that passed UTXOracle filters with extracted amounts.

    This is the black box interface between Module 2 (TX Processor) and Module 3 (Mempool Analyzer).

    Validation Rules (from UTXOracle.py Step 6):
    - txid: Must be 64-character hex string
    - amounts: Non-empty list, all values in [1e-5, 1e5] BTC range
    - timestamp: Must be positive float
    - input_count: Must be in [1, 5] (UTXOracle filter: ≤5 inputs)
    - output_count: Must be exactly 2 (UTXOracle filter)
    - fee_rate: If provided, must be positive
    """

    txid: str
    """Transaction ID (hex string, 64 characters)"""

    amounts: List[float]
    """BTC amounts from qualifying outputs (filtered range: [1e-5, 1e5])"""

    timestamp: float
    """Unix timestamp (seconds) when transaction was received"""

    fee_rate: Optional[float] = None
    """Fee rate in sat/vB (optional, for future analysis)"""

    input_count: int = 0
    """Number of inputs (must be ≤5 per UTXOracle filter)"""

    output_count: int = 0
    """Number of outputs (must be exactly 2 per UTXOracle filter)"""

    def __post_init__(self):
        """Validate fields after initialization"""
        if len(self.txid) != 64:
            raise ValueError("txid must be 64-character hex string")
        if not all(c in "0123456789abcdef" for c in self.txid.lower()):
            raise ValueError("txid must be valid hex string")
        if not self.amounts:
            raise ValueError("amounts must be non-empty list")
        if not all(1e-5 <= amt <= 1e5 for amt in self.amounts):
            raise ValueError("all amounts must be in range [1e-5, 1e5] BTC")
        if self.timestamp <= 0:
            raise ValueError("timestamp must be positive")
        if not 1 <= self.input_count <= 5:
            raise ValueError("input_count must be in range [1, 5]")
        if self.output_count != 2:
            raise ValueError("output_count must be exactly 2")
        if self.fee_rate is not None and self.fee_rate <= 0:
            raise ValueError("fee_rate must be positive if provided")


@dataclass
class MempoolState:
    """
    Current state of mempool price analysis.

    This is the black box interface between Module 3 (Mempool Analyzer) and Module 4 (Data Streamer).

    Validation Rules:
    - price: Must be positive float (typical range: 10k-200k USD)
    - confidence: Must be in [0.0, 1.0] range
    - active_tx_count: Must be non-negative integer
    - total_received: Must be >= total_filtered
    - total_filtered: Must be non-negative integer
    - uptime_seconds: Must be positive float

    Confidence Score Calculation:
    - 0-100 tx: Low confidence (0.0-0.3)
    - 100-1000 tx: Medium confidence (0.3-0.8)
    - 1000+ tx: High confidence (0.8-1.0)
    """

    price: float
    """Estimated BTC/USD price from mempool analysis"""

    confidence: float
    """Confidence score [0.0, 1.0] based on transaction count and distribution"""

    active_tx_count: int
    """Number of transactions currently in 3-hour rolling window"""

    total_received: int
    """Total transactions received since startup"""

    total_filtered: int
    """Total transactions filtered out (didn't pass UTXOracle criteria)"""

    uptime_seconds: float
    """Time since analyzer started (seconds)"""

    def __post_init__(self):
        """Validate fields after initialization"""
        if self.price <= 0:
            raise ValueError("price must be positive")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in range [0.0, 1.0]")
        if self.active_tx_count < 0:
            raise ValueError("active_tx_count must be non-negative")
        if self.total_received < 0:
            raise ValueError("total_received must be non-negative")
        if self.total_filtered < 0:
            raise ValueError("total_filtered must be non-negative")
        if self.total_received < self.total_filtered:
            raise ValueError("total_received must be >= total_filtered")
        if self.uptime_seconds <= 0:
            raise ValueError("uptime_seconds must be positive")


# =============================================================================
# Helper Functions
# =============================================================================


def calculate_confidence(active_tx_count: int) -> float:
    """
    Calculate confidence score based on transaction count.

    Rules:
    - 0-100 tx: Low confidence (0.0-0.3)
    - 100-1000 tx: Medium confidence (0.3-0.8)
    - 1000+ tx: High confidence (0.8-1.0)

    Args:
        active_tx_count: Number of active transactions in window

    Returns:
        Confidence score in range [0.0, 1.0]
    """
    if active_tx_count < 100:
        return min(0.3, active_tx_count / 100 * 0.3)
    elif active_tx_count < 1000:
        return 0.3 + (active_tx_count - 100) / 900 * 0.5
    else:
        return min(1.0, 0.8 + (active_tx_count - 1000) / 5000 * 0.2)


# =============================================================================
# API Boundary Models (Pydantic)
# =============================================================================


class TransactionPoint(BaseModel):
    """Single transaction point for visualization"""

    timestamp: float = Field(..., gt=0, description="Unix timestamp (seconds)")
    price: float = Field(
        ..., gt=0, description="Estimated price for this transaction (USD)"
    )


class SystemStats(BaseModel):
    """Operational statistics"""

    total_received: int = Field(..., ge=0, description="Total transactions received")
    total_filtered: int = Field(
        ..., ge=0, description="Total transactions filtered out"
    )
    active_in_window: int = Field(
        ..., ge=0, description="Active transactions in 3-hour window"
    )
    uptime_seconds: float = Field(..., gt=0, description="System uptime (seconds)")

    @field_validator("total_filtered")
    @classmethod
    def filtered_not_greater_than_received(cls, v: int, info) -> int:
        """Validate that total_filtered does not exceed total_received"""
        if "total_received" in info.data and v > info.data["total_received"]:
            raise ValueError("total_filtered cannot exceed total_received")
        return v


class MempoolUpdateData(BaseModel):
    """Mempool update payload"""

    price: float = Field(..., gt=0, description="Current BTC/USD price estimate")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score [0.0-1.0]")
    transactions: List[TransactionPoint] = Field(
        default_factory=list, description="Recent transactions for visualization"
    )
    stats: SystemStats
    timestamp: float = Field(..., gt=0, description="Message timestamp (seconds)")


class WebSocketMessage(BaseModel):
    """
    Complete WebSocket message sent to browser clients.

    This is the black box interface between Module 4 (Data Streamer) and Module 5 (Visualization).
    """

    type: str = Field(default="mempool_update", description="Message type identifier")
    data: MempoolUpdateData

    model_config = {
        "json_schema_extra": {
            "example": {
                "type": "mempool_update",
                "data": {
                    "price": 113600.50,
                    "confidence": 0.87,
                    "transactions": [
                        {"timestamp": 1678901234.1, "price": 113500.0},
                        {"timestamp": 1678901234.2, "price": 113700.0},
                    ],
                    "stats": {
                        "total_received": 12543,
                        "total_filtered": 8234,
                        "active_in_window": 4309,
                        "uptime_seconds": 3600.5,
                    },
                    "timestamp": 1678901234.567,
                },
            }
        }
    }


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "RawTransaction",
    "ProcessedTransaction",
    "MempoolState",
    "TransactionPoint",
    "SystemStats",
    "MempoolUpdateData",
    "WebSocketMessage",
    "calculate_confidence",
]
