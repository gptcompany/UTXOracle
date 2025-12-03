# API Contracts - UTXOracle Live

**Feature**: 002-mempool-live-oracle
**Date**: 2025-10-19

## Overview

This directory contains JSON Schema definitions for all data contracts in the UTXOracle Live system. These schemas define the black box interfaces between modules.

## Contract Files

### 1. websocket-api.json

**Purpose**: WebSocket message format for real-time streaming

**Direction**: Backend (Module 4) → Frontend (Module 5)

**Endpoint**: `ws://localhost:8000/ws/mempool`

**Message Type**: Server-to-client updates (one-way stream for MVP)

**Update Frequency**: Every 500ms

**Example**:
```json
{
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
```

**Validation**:
- All schemas validated via JSON Schema Draft 07
- Pydantic provides runtime validation on backend
- Frontend performs basic type checking

**Client Implementation** (JavaScript):
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/mempool');

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);

    // Validate message type
    if (message.type !== 'mempool_update') {
        console.error('Unknown message type:', message.type);
        return;
    }

    // Extract data
    const { price, confidence, transactions, stats } = message.data;

    // Update visualization
    updatePriceDisplay(price, confidence);
    updateScatterPlot(transactions);
    updateStats(stats);
};
```

---

### 2. data-models.json

**Purpose**: Shared data structures for module interfaces

**Definitions**:

1. **RawTransaction** (Module 1 → Module 2)
   - Binary transaction data from Bitcoin Core ZMQ
   - Fields: raw_bytes (base64), timestamp, topic

2. **ProcessedTransaction** (Module 2 → Module 3)
   - Parsed and filtered transaction
   - Fields: txid, amounts, timestamp, fee_rate, input_count, output_count
   - Validation: UTXOracle filters (≤5 inputs, exactly 2 outputs, amounts in [1e-5, 1e5] BTC)

3. **MempoolState** (Module 3 → Module 4)
   - Current analysis state
   - Fields: price, confidence, active_tx_count, total_received, total_filtered, uptime_seconds

**Python Implementation**:
```python
from dataclasses import dataclass
from typing import List, Optional, Literal

@dataclass
class ProcessedTransaction:
    txid: str
    amounts: List[float]
    timestamp: float
    fee_rate: Optional[float] = None
    input_count: int = 0
    output_count: int = 0
```

---

## Contract Validation

### JSON Schema Validation

```bash
# Install validator
uv add --dev jsonschema

# Validate example messages
uv run python -c "
import json
import jsonschema

# Load schema
with open('specs/002-mempool-live-oracle/contracts/websocket-api.json') as f:
    schema = json.load(f)

# Load example message
example = schema['examples'][0]

# Validate
jsonschema.validate(instance=example, schema=schema)
print('✅ Validation passed')
"
```

### Runtime Validation (Pydantic)

Backend uses Pydantic for automatic validation:

```python
from pydantic import BaseModel, ValidationError

try:
    msg = WebSocketMessage.model_validate_json(json_str)
except ValidationError as e:
    print(f"❌ Invalid message: {e}")
```

---

## Breaking Changes Policy

### Versioning

Contracts follow semantic versioning:
- **MAJOR**: Breaking changes to existing fields (e.g., rename, type change)
- **MINOR**: New optional fields
- **PATCH**: Documentation updates, clarifications

**Current Version**: 1.0.0

### Backward Compatibility

For MVP (single-server, no public API):
- Breaking changes allowed during development
- Must coordinate backend + frontend updates

For Production (public WebSocket API):
- Breaking changes require version negotiation
- Add `version` field to WebSocketMessage
- Support multiple schema versions simultaneously

---

## Testing Contracts

### Unit Tests

```python
# tests/test_contracts.py

import json
import jsonschema
from live.shared.models import WebSocketMessage

def test_websocket_message_matches_schema():
    """Verify Pydantic model matches JSON Schema"""
    # Create message via Pydantic
    msg = WebSocketMessage(...)
    json_data = json.loads(msg.model_dump_json())

    # Load JSON Schema
    with open('specs/002-mempool-live-oracle/contracts/websocket-api.json') as f:
        schema = json.load(f)

    # Validate
    jsonschema.validate(instance=json_data, schema=schema)
```

### Integration Tests

```python
# tests/integration/test_websocket.py

async def test_websocket_contract_compliance():
    """Verify actual WebSocket messages match contract"""
    async with websockets.connect('ws://localhost:8000/ws/mempool') as ws:
        # Receive message
        msg_str = await ws.recv()
        msg_data = json.loads(msg_str)

        # Validate against schema
        with open('specs/002-mempool-live-oracle/contracts/websocket-api.json') as f:
            schema = json.load(f)
        jsonschema.validate(instance=msg_data, schema=schema)
```

---

## Contract Evolution

### Adding New Fields

**Safe** (backward compatible):
```json
// Before
{
  "price": 113600.50,
  "confidence": 0.87
}

// After (add optional field)
{
  "price": 113600.50,
  "confidence": 0.87,
  "volatility": 0.05  // NEW (optional)
}
```

**Breaking** (requires version bump):
```json
// Before
{
  "price": 113600.50
}

// After (rename field)
{
  "btc_usd_price": 113600.50  // BREAKING
}
```

### Deprecation Process

1. Add new field, mark old field as deprecated (MINOR version bump)
2. Update clients to use new field
3. Remove old field (MAJOR version bump)

**Timeline**: Minimum 1 month between steps 1 and 3

---

## Documentation

### Auto-Generated Docs

JSON Schemas can be rendered as interactive documentation:

**Tools**:
- [json-schema.org/implementations](https://json-schema.org/implementations.html#documentation-generators)
- [Redoc](https://github.com/Redocly/redoc) (OpenAPI from JSON Schema)
- [Stoplight](https://stoplight.io/) (API design & documentation)

**Example** (generate HTML docs):
```bash
# Install generator
npm install -g json-schema-to-markdown

# Generate Markdown docs
json-schema-to-markdown specs/002-mempool-live-oracle/contracts/websocket-api.json > docs/api/websocket.md
```

---

## Related Documents

- **Feature Spec**: [../spec.md](../spec.md) - User requirements and acceptance criteria
- **Data Model Spec**: [../data-model.md](../data-model.md) - Detailed Pydantic/dataclass definitions
- **Implementation Plan**: [../plan.md](../plan.md) - Technical architecture and roadmap

---

*Contract Documentation v1.0*
*Created*: 2025-10-19
*Status*: Complete - Ready for implementation
