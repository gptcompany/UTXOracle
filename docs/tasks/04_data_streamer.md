# Task 04: Data Streamer Module

**Assigned Agent**: `general-purpose`

**Duration**: 2 weeks

**Dependencies**: Task 03 (Mempool Analyzer)

---

## Objective

Create FastAPI WebSocket server to stream real-time mempool data and price estimates to browser clients.

---

## Requirements

### Functional
1. WebSocket endpoint for mempool transaction stream
2. Send price updates every 500ms
3. Handle multiple concurrent clients
4. Graceful client connection/disconnection
5. Health check endpoint

### Non-Functional
1. **Latency**: <100ms from analyzer update to WebSocket send
2. **Concurrency**: Support 100 concurrent clients
3. **Bandwidth**: <1MB/sec per client
4. **Dependencies**: FastAPI, Uvicorn only

---

## Implementation Details

### File Structure
```
live/backend/
├── api.py              # FastAPI app + WebSocket
├── streamer.py         # Data streaming logic
└── orchestrator.py     # Coordinates ZMQ → Analyzer → Streamer
```

### Core Interface

```python
# live/backend/api.py

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import asyncio
import json
from typing import List
from .orchestrator import MempoolOrchestrator

app = FastAPI(title="UTXOracle Live")

# Mount frontend static files
app.mount("/static", StaticFiles(directory="live/frontend"), name="static")

# Global orchestrator (single instance)
orchestrator = MempoolOrchestrator()

class ConnectionManager:
    """Manage WebSocket client connections"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Send message to all connected clients"""
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                dead_connections.append(connection)

        # Remove dead connections
        for conn in dead_connections:
            self.active_connections.remove(conn)

manager = ConnectionManager()

@app.on_event("startup")
async def startup_event():
    """Start mempool orchestrator on server startup"""
    asyncio.create_task(orchestrator.run())
    asyncio.create_task(broadcast_updates())

@app.websocket("/ws/mempool")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time mempool data.

    Sends updates every 500ms with:
    - Current mempool price estimate
    - Recent transaction points (for visualization)
    - Confidence score
    - Mempool stats
    """
    await manager.connect(websocket)

    try:
        # Keep connection alive
        while True:
            # Wait for client messages (ping/pong)
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def broadcast_updates():
    """
    Periodically broadcast mempool state to all clients.

    Runs every 500ms.
    """
    while True:
        await asyncio.sleep(0.5)

        # Get current state from orchestrator
        state = orchestrator.get_current_state()

        # Broadcast to all clients
        await manager.broadcast(state)

@app.get("/")
async def get_index():
    """Serve frontend HTML"""
    with open("live/frontend/index.html") as f:
        return HTMLResponse(content=f.read())

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "clients_connected": len(manager.active_connections),
        "mempool_active_txs": orchestrator.analyzer.get_stats()["active_txs_in_window"],
        "uptime_seconds": orchestrator.get_uptime()
    }
```

### Orchestrator

```python
# live/backend/orchestrator.py

"""
Coordinates all modules: ZMQ → Processor → Analyzer → Streamer

Black Box Contract:
- Manages lifecycle of all components
- Provides unified state for WebSocket broadcast
"""

import asyncio
import time
from .zmq_listener import stream_mempool_transactions
from .tx_processor import process_mempool_transaction
from .mempool_analyzer import MempoolAnalyzer
from .mempool_state import MempoolState

class MempoolOrchestrator:
    """Coordinates mempool data pipeline"""

    def __init__(self):
        self.analyzer = MempoolAnalyzer(rolling_window_hours=3)
        self.mempool_state = MempoolState()
        self.start_time = time.time()

        # Metrics
        self.total_txs_received = 0
        self.total_txs_filtered = 0

    async def run(self):
        """
        Main pipeline: ZMQ → Process → Analyze

        Runs indefinitely, processing mempool transactions.
        """
        async for raw_tx in stream_mempool_transactions():
            self.total_txs_received += 1

            # Process transaction
            processed_tx = process_mempool_transaction(raw_tx)

            if processed_tx is None:
                self.total_txs_filtered += 1
                continue

            # Add to mempool state
            self.mempool_state.add_transaction(processed_tx)

            # Update analyzer
            self.analyzer.add_transaction(processed_tx)

    def get_current_state(self) -> dict:
        """
        Get current mempool state for WebSocket broadcast.

        Returns:
            {
                'price': float,
                'confidence': float,
                'transactions': List[dict],  # Recent tx for viz
                'stats': dict,
                'timestamp': float
            }
        """
        # Estimate current price
        price, confidence = self.analyzer.estimate_price()

        # Get recent transactions (last 1000 for visualization)
        recent_txs = self._get_recent_transactions_for_viz(1000)

        return {
            'price': round(price, 2),
            'confidence': round(confidence, 3),
            'transactions': recent_txs,
            'stats': {
                'total_received': self.total_txs_received,
                'total_filtered': self.total_txs_filtered,
                'active_in_window': len(self.analyzer.tx_queue),
                'uptime_seconds': self.get_uptime()
            },
            'timestamp': time.time()
        }

    def _get_recent_transactions_for_viz(self, limit: int) -> List[dict]:
        """
        Get recent transactions formatted for visualization.

        Returns minimal data for Canvas/WebGL rendering:
        - timestamp (x-axis)
        - price (y-axis)
        """
        recent = list(self.analyzer.tx_queue)[-limit:]

        # Calculate implied price for each tx amount
        current_price, _ = self.analyzer.estimate_price()

        viz_points = []
        for amount, timestamp in recent:
            # Estimate which USD amount this corresponds to
            for usd in [5, 10, 20, 50, 100, 200, 500, 1000]:
                expected_btc = usd / current_price
                if abs(amount - expected_btc) / expected_btc < 0.25:  # Within 25%
                    implied_price = usd / amount
                    viz_points.append({
                        'timestamp': timestamp,
                        'price': round(implied_price, 2)
                    })
                    break

        return viz_points

    def get_uptime(self) -> float:
        """Return uptime in seconds"""
        return time.time() - self.start_time
```

---

## WebSocket Message Format

### Client → Server (Ping)
```json
{
    "type": "ping",
    "timestamp": 1678901234.567
}
```

### Server → Client (State Update)
```json
{
    "price": 113600.50,
    "confidence": 0.87,
    "transactions": [
        {"timestamp": 1678901234.1, "price": 113500},
        {"timestamp": 1678901234.2, "price": 113700},
        ...
    ],
    "stats": {
        "total_received": 12543,
        "total_filtered": 8234,
        "active_in_window": 4309,
        "uptime_seconds": 3600
    },
    "timestamp": 1678901234.567
}
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_api.py

from fastapi.testclient import TestClient
from live.backend.api import app

def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert "status" in response.json()
    assert response.json()["status"] == "ok"

def test_websocket_connection():
    client = TestClient(app)

    with client.websocket_connect("/ws/mempool") as websocket:
        # Should receive initial state
        data = websocket.receive_json()

        assert "price" in data
        assert "confidence" in data
        assert "transactions" in data
```

### Load Tests

```python
# tests/load_test_websocket.py

import asyncio
import websockets

async def stress_test_connections():
    """Test 100 concurrent WebSocket clients"""

    async def client():
        uri = "ws://localhost:8000/ws/mempool"
        async with websockets.connect(uri) as websocket:
            for _ in range(60):  # 60 updates (30 seconds @ 0.5s interval)
                message = await websocket.recv()
                data = json.loads(message)
                assert "price" in data

    # Run 100 clients concurrently
    await asyncio.gather(*[client() for _ in range(100)])

asyncio.run(stress_test_connections())
```

---

## Deployment

### Run Development Server

```bash
# Install dependencies
uv add fastapi uvicorn[standard] websockets

# Run server
uv run uvicorn live.backend.api:app --reload --host 0.0.0.0 --port 8000
```

### Production Server

```bash
# Use Uvicorn with workers
uv run uvicorn live.backend.api:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info \
    --access-log
```

**Note**: Only 1 worker (single process) due to in-memory state.

---

## Deliverables

- [ ] `live/backend/api.py`
- [ ] `live/backend/orchestrator.py`
- [ ] `live/backend/streamer.py`
- [ ] Unit tests
- [ ] Load tests (100 concurrent clients)
- [ ] Deployment documentation

---

## Acceptance Criteria

✅ **Must Have**:
1. WebSocket streams data at 500ms intervals
2. Handles 100 concurrent clients without lag
3. Health check endpoint functional
4. Graceful client disconnection

✅ **Should Have**:
1. Automatic reconnection logic (client-side)
2. Logging for connections/disconnections
3. Rate limiting (max 10 connections per IP)

---

**Status**: NOT STARTED
**Dependencies**: Task 03 complete
**Target Completion**: __________ (2 weeks from Task 03 completion)
