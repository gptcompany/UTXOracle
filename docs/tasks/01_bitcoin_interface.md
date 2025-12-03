# Task 01: Bitcoin Interface Module

**Assigned Agent**: `bitcoin-onchain-expert`

**Duration**: 1-2 weeks

**Dependencies**: None (first module to implement)

---

## Objective

Create a ZMQ listener that subscribes to Bitcoin Core mempool transactions in real-time and yields raw transaction bytes for downstream processing.

---

## Requirements

### Functional
1. Subscribe to Bitcoin Core ZMQ socket (`zmqpubrawtx`)
2. Receive raw transaction bytes as they enter mempool
3. Handle connection drops and auto-reconnect
4. Validate transaction format before yielding
5. Provide health check endpoint

### Non-Functional
1. **Latency**: <100ms from Bitcoin Core broadcast to yield
2. **Reliability**: Auto-reconnect within 5 seconds of disconnect
3. **Memory**: <50MB overhead for ZMQ buffers
4. **Dependencies**: Only `pyzmq` (no additional libraries)

---

## Implementation Details

### File Structure
```
live/backend/
├── zmq_listener.py      # Main implementation
├── config.py            # Configuration
└── models.py            # Data models (RawTransaction)
```

### Core Interface

```python
# live/backend/zmq_listener.py

import asyncio
import zmq
import zmq.asyncio
from typing import AsyncGenerator
from .config import Config
from .models import RawTransaction

class BitcoinZMQListener:
    """
    Bitcoin Core ZMQ mempool transaction listener.

    Black Box Contract:
    - Input: Bitcoin Core ZMQ endpoint (tcp://host:port)
    - Output: AsyncGenerator[RawTransaction]
    - Side Effects: None (stateless listener)
    """

    def __init__(self, zmq_endpoint: str):
        self.zmq_endpoint = zmq_endpoint
        self.context = None
        self.socket = None
        self._running = False

    async def connect(self) -> None:
        """Establish ZMQ connection"""
        pass

    async def disconnect(self) -> None:
        """Clean shutdown"""
        pass

    async def stream_transactions(self) -> AsyncGenerator[RawTransaction, None]:
        """
        Yield raw mempool transactions as they arrive.

        Yields:
            RawTransaction(raw_bytes, timestamp, topic)

        Raises:
            ConnectionError: If ZMQ connection fails after retries
        """
        pass

    async def health_check(self) -> bool:
        """Return True if connected and receiving data"""
        pass

# Public API
async def stream_mempool_transactions() -> AsyncGenerator[RawTransaction, None]:
    """
    Main entry point for mempool transaction stream.

    Example:
        async for tx in stream_mempool_transactions():
            print(f"Received {len(tx.raw_bytes)} bytes")
    """
    listener = BitcoinZMQListener(Config.BITCOIN_ZMQ_TX)
    await listener.connect()

    try:
        async for tx in listener.stream_transactions():
            yield tx
    finally:
        await listener.disconnect()
```

### Data Models

```python
# live/backend/models.py

from dataclasses import dataclass
from typing import Literal

@dataclass
class RawTransaction:
    """Raw mempool transaction from ZMQ"""
    raw_bytes: bytes           # Complete transaction bytes
    timestamp: float           # Unix timestamp when received
    topic: Literal['rawtx']    # ZMQ topic (always 'rawtx')

    def __len__(self) -> int:
        return len(self.raw_bytes)
```

### Configuration

```python
# live/backend/config.py

import os

class Config:
    # Bitcoin Core ZMQ
    BITCOIN_ZMQ_TX = os.getenv(
        "BITCOIN_ZMQ_TX",
        "tcp://127.0.0.1:28332"
    )

    # Connection settings
    ZMQ_RECONNECT_INTERVAL_MS = int(os.getenv("ZMQ_RECONNECT_INTERVAL_MS", "5000"))
    ZMQ_TIMEOUT_MS = int(os.getenv("ZMQ_TIMEOUT_MS", "10000"))

    # Health check
    HEALTH_CHECK_INTERVAL_SEC = int(os.getenv("HEALTH_CHECK_INTERVAL_SEC", "30"))
```

---

## Bitcoin Core Setup

### bitcoin.conf Requirements
```conf
# Enable ZMQ publishing
zmqpubrawtx=tcp://127.0.0.1:28332
zmqpubrawblock=tcp://127.0.0.1:28333

# Optional: RPC (for health checks)
rpcuser=utxoracle
rpcpassword=changeme
rpcallowip=127.0.0.1
```

### Verify ZMQ is working
```bash
# Install zmq tools
sudo apt-get install libzmq3-dev

# Test subscription (should print hex tx as they arrive)
python3 -c "
import zmq
ctx = zmq.Context()
sock = ctx.socket(zmq.SUB)
sock.connect('tcp://127.0.0.1:28332')
sock.subscribe(b'rawtx')
while True:
    topic, body = sock.recv_multipart()
    print(f'Received {len(body)} bytes')
"
```

---

## Testing Strategy

### Unit Tests
```python
# tests/test_zmq_listener.py

import pytest
from live.backend.zmq_listener import BitcoinZMQListener
from unittest.mock import Mock, AsyncMock

@pytest.mark.asyncio
async def test_connect():
    listener = BitcoinZMQListener("tcp://127.0.0.1:28332")
    await listener.connect()
    assert listener._running == True
    await listener.disconnect()

@pytest.mark.asyncio
async def test_stream_transactions():
    listener = BitcoinZMQListener("tcp://127.0.0.1:28332")

    # Mock ZMQ socket
    listener.socket = Mock()
    listener.socket.recv_multipart = AsyncMock(
        return_value=[b'rawtx', b'\x01\x00\x00\x00...']
    )

    async for tx in listener.stream_transactions():
        assert len(tx.raw_bytes) > 0
        break  # Test first tx only

@pytest.mark.asyncio
async def test_reconnect_on_failure():
    """Test auto-reconnect when ZMQ connection drops"""
    listener = BitcoinZMQListener("tcp://127.0.0.1:28332")

    # Simulate connection drop
    listener.socket = Mock()
    listener.socket.recv_multipart = AsyncMock(
        side_effect=[zmq.error.Again, [b'rawtx', b'\x01\x00']]
    )

    count = 0
    async for tx in listener.stream_transactions():
        count += 1
        if count >= 1:
            break

    assert count == 1  # Reconnected and received tx
```

### Integration Tests
```bash
# Requires running Bitcoin Core node
pytest tests/integration/test_zmq_real.py -v

# Expected output:
# test_receive_real_mempool_tx PASSED
# test_connection_stability PASSED  (runs for 60 seconds)
```

---

## Edge Cases to Handle

1. **ZMQ socket timeout**: Reconnect after 5 seconds
2. **Invalid transaction bytes**: Log warning, skip transaction
3. **Bitcoin Core restart**: Detect disconnect, auto-reconnect
4. **Network congestion**: Buffer up to 1000 pending tx, drop oldest if full
5. **Malformed ZMQ messages**: Validate topic == 'rawtx' before processing

---

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Latency | <100ms | Time from Bitcoin broadcast to yield |
| Throughput | 10k tx/sec | Stress test with simulated mempool |
| Memory | <50MB | Monitor process RSS during peak |
| Reconnect time | <5sec | Kill Bitcoin, measure time to reconnect |

---

## Deliverables

- [ ] `live/backend/zmq_listener.py` - Fully implemented
- [ ] `live/backend/config.py` - Configuration with env vars
- [ ] `live/backend/models.py` - RawTransaction dataclass
- [ ] `tests/test_zmq_listener.py` - Unit tests (>90% coverage)
- [ ] `tests/integration/test_zmq_real.py` - Integration tests
- [ ] `docs/bitcoin_zmq_setup.md` - Setup guide for users

---

## Acceptance Criteria

✅ **Must Have**:
1. Connects to Bitcoin Core ZMQ on startup
2. Yields raw transaction bytes in real-time
3. Auto-reconnects on connection failure
4. Unit tests pass with >90% coverage
5. Integration test runs for 5 minutes without errors

✅ **Should Have**:
1. Health check returns status
2. Graceful shutdown (no hanging sockets)
3. Logging for connection events

❌ **Won't Have** (out of scope):
- Transaction parsing (handled by Task 02)
- Filtering logic (handled by Task 02)
- Storage/persistence (handled by Task 03)

---

## Dependencies

**Install**:
```bash
uv add pyzmq
```

**Bitcoin Core**: v25.0+ (tested on v25, v26, v27)

---

## Questions for Agent

1. Should we buffer transactions if downstream processing is slow?
2. How should we handle ZMQ topic changes (e.g., 'hashtx' vs 'rawtx')?
3. Should health check ping Bitcoin Core RPC or just check socket status?

---

## Completion Checklist

- [ ] Code written and tested locally
- [ ] Unit tests pass
- [ ] Integration test runs successfully
- [ ] Documentation updated
- [ ] Code review by maintainer
- [ ] Merge to `feature/mempool-live` branch

---

**Status**: NOT STARTED
**Assigned Date**: __________
**Target Completion**: __________ (2 weeks from start)
**Actual Completion**: __________
