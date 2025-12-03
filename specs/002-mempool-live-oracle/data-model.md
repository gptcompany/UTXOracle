# Data Model Specification

**Feature**: UTXOracle Live - Real-time Mempool Price Oracle
**Branch**: 002-mempool-live-oracle
**Date**: 2025-10-19

## Overview

This document defines the data models used across all modules in the UTXOracle Live system. All models use Python dataclasses or Pydantic classes for validation and type safety.

## Shared Data Models

**File**: `live/shared/models.py`

These models are the ONLY shared code between modules. They define the black box interface contracts.

### 1. RawTransaction

**Purpose**: Represents raw transaction data from Bitcoin Core ZMQ feed

**Source**: Module 1 (ZMQ Listener)
**Consumer**: Module 2 (Transaction Processor)

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class RawTransaction:
    """
    Raw transaction received from Bitcoin Core ZMQ.

    This is the black box interface between Module 1 and Module 2.
    """
    raw_bytes: bytes
    """Complete binary transaction data"""

    timestamp: float
    """Unix timestamp (seconds) when transaction was received"""

    topic: Literal['rawtx']
    """ZMQ topic identifier (always 'rawtx' for mempool transactions)"""
```

**Validation Rules**:
- `raw_bytes`: Must be non-empty
- `timestamp`: Must be positive float (Unix epoch seconds)
- `topic`: Must be exactly 'rawtx'

**Example**:
```python
raw_tx = RawTransaction(
    raw_bytes=b'\x02\x00\x00\x00...',  # 250 bytes typical
    timestamp=1678901234.567,
    topic='rawtx'
)
```

---

### 2. ProcessedTransaction

**Purpose**: Parsed and filtered transaction with extracted data

**Source**: Module 2 (Transaction Processor)
**Consumer**: Module 3 (Mempool Analyzer)

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ProcessedTransaction:
    """
    Transaction that passed UTXOracle filters with extracted amounts.

    This is the black box interface between Module 2 and Module 3.
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
```

**Validation Rules** (from UTXOracle.py Step 6):
- `txid`: Must be 64-character hex string
- `amounts`: Non-empty list, all values in [1e-5, 1e5] BTC range
- `timestamp`: Must be positive float
- `input_count`: Must be in [1, 5] (UTXOracle filter: ≤5 inputs)
- `output_count`: Must be exactly 2 (UTXOracle filter)
- `fee_rate`: If provided, must be positive

**Example**:
```python
processed_tx = ProcessedTransaction(
    txid="a1b2c3d4...",  # 64 chars
    amounts=[0.00123456, 0.00654321],  # 2 outputs
    timestamp=1678901234.567,
    fee_rate=25.5,  # sat/vB
    input_count=2,
    output_count=2
)
```

---

### 3. MempoolState

**Purpose**: Current mempool analysis state with price estimate

**Source**: Module 3 (Mempool Analyzer)
**Consumer**: Module 4 (Data Streamer)

```python
from dataclasses import dataclass

@dataclass
class MempoolState:
    """
    Current state of mempool price analysis.

    This is the black box interface between Module 3 and Module 4.
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
```

**Validation Rules**:
- `price`: Must be positive float (typical range: 10k-200k USD)
- `confidence`: Must be in [0.0, 1.0] range
- `active_tx_count`: Must be non-negative integer
- `total_received`: Must be ≥ total_filtered
- `total_filtered`: Must be non-negative integer
- `uptime_seconds`: Must be positive float

**Confidence Score Calculation**:
```python
def calculate_confidence(active_tx_count: int) -> float:
    """
    Confidence based on transaction count:
    - 0-100 tx: Low confidence (0.0-0.3)
    - 100-1000 tx: Medium confidence (0.3-0.8)
    - 1000+ tx: High confidence (0.8-1.0)
    """
    if active_tx_count < 100:
        return min(0.3, active_tx_count / 100 * 0.3)
    elif active_tx_count < 1000:
        return 0.3 + (active_tx_count - 100) / 900 * 0.5
    else:
        return min(1.0, 0.8 + (active_tx_count - 1000) / 5000 * 0.2)
```

**Example**:
```python
state = MempoolState(
    price=113600.50,
    confidence=0.87,
    active_tx_count=4309,
    total_received=12543,
    total_filtered=8234,
    uptime_seconds=3600.5
)
```

---

### 4. WebSocketMessage (Pydantic)

**Purpose**: Client-facing message format for WebSocket stream

**Source**: Module 4 (Data Streamer)
**Consumer**: Module 5 (Visualization Renderer)

```python
from pydantic import BaseModel, Field, validator
from typing import List, Dict

class TransactionPoint(BaseModel):
    """Single transaction point for visualization"""
    timestamp: float = Field(..., gt=0, description="Unix timestamp (seconds)")
    price: float = Field(..., gt=0, description="Estimated price for this transaction (USD)")

class SystemStats(BaseModel):
    """Operational statistics"""
    total_received: int = Field(..., ge=0, description="Total transactions received")
    total_filtered: int = Field(..., ge=0, description="Total transactions filtered out")
    active_in_window: int = Field(..., ge=0, description="Active transactions in 3-hour window")
    uptime_seconds: float = Field(..., gt=0, description="System uptime (seconds)")

    @validator('total_filtered')
    def filtered_not_greater_than_received(cls, v, values):
        if 'total_received' in values and v > values['total_received']:
            raise ValueError('total_filtered cannot exceed total_received')
        return v

class MempoolUpdateData(BaseModel):
    """Mempool update payload"""
    price: float = Field(..., gt=0, description="Current BTC/USD price estimate")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score [0.0-1.0]")
    transactions: List[TransactionPoint] = Field(default_factory=list, description="Recent transactions for visualization")
    stats: SystemStats
    timestamp: float = Field(..., gt=0, description="Message timestamp (seconds)")

class WebSocketMessage(BaseModel):
    """
    Complete WebSocket message sent to browser clients.

    This is the black box interface between Module 4 and Module 5.
    """
    type: str = Field(default="mempool_update", description="Message type identifier")
    data: MempoolUpdateData

    class Config:
        json_schema_extra = {
            "example": {
                "type": "mempool_update",
                "data": {
                    "price": 113600.50,
                    "confidence": 0.87,
                    "transactions": [
                        {"timestamp": 1678901234.1, "price": 113500.0},
                        {"timestamp": 1678901234.2, "price": 113700.0}
                    ],
                    "stats": {
                        "total_received": 12543,
                        "total_filtered": 8234,
                        "active_in_window": 4309,
                        "uptime_seconds": 3600.5
                    },
                    "timestamp": 1678901234.567
                }
            }
        }
```

**Validation Rules** (Pydantic automatic):
- All numeric fields validated against constraints (gt, ge, le)
- `total_filtered` cannot exceed `total_received` (custom validator)
- Timestamps must be positive floats
- JSON serialization/deserialization automatic

**Example Usage**:
```python
# Create message
msg = WebSocketMessage(
    data=MempoolUpdateData(
        price=113600.50,
        confidence=0.87,
        transactions=[
            TransactionPoint(timestamp=1678901234.1, price=113500.0),
            TransactionPoint(timestamp=1678901234.2, price=113700.0)
        ],
        stats=SystemStats(
            total_received=12543,
            total_filtered=8234,
            active_in_window=4309,
            uptime_seconds=3600.5
        ),
        timestamp=1678901234.567
    )
)

# Serialize to JSON
json_str = msg.model_dump_json()

# Send via WebSocket
await websocket.send_text(json_str)
```

---

## Module-Specific Models

These models are internal to specific modules and NOT shared.

### Module 2: Transaction Processor Internals

**File**: `live/backend/tx_processor.py`

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class TransactionInput:
    """Parsed transaction input (internal to Module 2)"""
    prev_tx: str  # Previous transaction ID
    prev_index: int  # Previous output index
    script_sig: bytes  # Signature script
    sequence: int

@dataclass
class TransactionOutput:
    """Parsed transaction output (internal to Module 2)"""
    value: int  # Satoshis (int64)
    script_pubkey: bytes  # Locking script

    def to_btc(self) -> float:
        """Convert satoshis to BTC"""
        return self.value / 100_000_000

@dataclass
class ParsedTransaction:
    """
    Fully parsed transaction (internal to Module 2).

    This is NOT exported to other modules.
    Converted to ProcessedTransaction after filtering.
    """
    version: int
    inputs: List[TransactionInput]
    outputs: List[TransactionOutput]
    locktime: int
    is_segwit: bool
    witness_data: Optional[bytes] = None
```

---

### Module 3: Mempool Analyzer Internals

**File**: `live/backend/mempool_analyzer.py`

```python
from dataclasses import dataclass
from typing import Dict
import numpy as np

@dataclass
class HistogramBin:
    """Single histogram bin (internal to Module 3)"""
    price_min: float  # USD
    price_max: float  # USD
    count: float  # Transaction count (weighted)

class Histogram:
    """
    Rolling histogram for price estimation (internal to Module 3).

    This implements UTXOracle.py Steps 5-7.
    """
    def __init__(self, num_bins: int = 10000):
        self.bins: Dict[int, float] = {}  # bin_index → count
        self.num_bins = num_bins
        self.price_min = 0.0
        self.price_max = 200000.0  # USD

    def add_transaction(self, amount_btc: float, estimated_price: float):
        """Add transaction to histogram"""
        bin_index = self._get_bin_index(estimated_price)
        self.bins[bin_index] = self.bins.get(bin_index, 0.0) + amount_btc

    def _get_bin_index(self, price: float) -> int:
        """Map price to bin index"""
        if price <= self.price_min:
            return 0
        if price >= self.price_max:
            return self.num_bins - 1
        return int((price - self.price_min) / (self.price_max - self.price_min) * self.num_bins)

@dataclass
class PriceFindingStencil:
    """
    Statistical clustering stencil (internal to Module 3).

    This implements UTXOracle.py Step 8.
    """
    center_price: float  # USD
    width: float  # USD
    weight: float  # Cluster weight
```

---

## Data Flow Summary

```
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
```

**Black Box Principle**: Modules only communicate via these 4 data structures. Internal implementations are hidden.

---

## Type Safety & Validation

### Dataclass vs Pydantic

**Dataclasses** (Python stdlib):
- Used for internal Python-only models
- Lightweight, zero dependencies
- No automatic validation (validation in module logic)
- Examples: RawTransaction, ProcessedTransaction, MempoolState

**Pydantic** (external library):
- Used for API boundary (WebSocket JSON)
- Automatic validation with descriptive errors
- JSON serialization/deserialization
- OpenAPI schema generation
- Examples: WebSocketMessage, MempoolUpdateData

### Type Checking

All models are fully type-annotated for static analysis:

```bash
# Run mypy for type checking
uv run mypy live/shared/models.py --strict
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_models.py

def test_raw_transaction_creation():
    """Test RawTransaction dataclass"""
    tx = RawTransaction(
        raw_bytes=b'\x01\x02\x03',
        timestamp=1678901234.567,
        topic='rawtx'
    )
    assert tx.topic == 'rawtx'
    assert len(tx.raw_bytes) == 3

def test_processed_transaction_validation():
    """Test ProcessedTransaction constraints"""
    # Valid transaction
    tx = ProcessedTransaction(
        txid="a" * 64,
        amounts=[0.001, 0.002],
        timestamp=1678901234.567,
        input_count=2,
        output_count=2
    )
    assert len(tx.amounts) == 2

    # Edge cases
    assert all(1e-5 <= amt <= 1e5 for amt in tx.amounts)

def test_websocket_message_serialization():
    """Test Pydantic JSON serialization"""
    msg = WebSocketMessage(
        data=MempoolUpdateData(
            price=113600.50,
            confidence=0.87,
            transactions=[],
            stats=SystemStats(
                total_received=100,
                total_filtered=50,
                active_in_window=50,
                uptime_seconds=60.0
            ),
            timestamp=1678901234.567
        )
    )

    # Serialize and deserialize
    json_str = msg.model_dump_json()
    msg2 = WebSocketMessage.model_validate_json(json_str)
    assert msg2.data.price == 113600.50

def test_confidence_score_ranges():
    """Test confidence score calculation"""
    assert 0.0 <= calculate_confidence(0) <= 0.3
    assert 0.3 <= calculate_confidence(500) <= 0.8
    assert 0.8 <= calculate_confidence(2000) <= 1.0
```

---

## JSON Schema Export

Pydantic models can be exported as JSON Schema for API documentation:

```python
# Generate JSON Schema
from live.shared.models import WebSocketMessage

schema = WebSocketMessage.model_json_schema()
# Save to specs/002-mempool-live-oracle/contracts/websocket-api.json
```

**Output**: See `contracts/websocket-api.json`

---

## Next Steps

1. **Implement models**: Create `live/shared/models.py` with dataclass and Pydantic definitions
2. **Generate JSON schemas**: Export Pydantic schemas to `contracts/` directory
3. **Write unit tests**: Test all validation rules and edge cases
4. **Document contracts**: Update `contracts/README.md` with usage examples

---

*Data Model Specification v1.0*
*Created*: 2025-10-19
*Status*: Complete - Ready for implementation
