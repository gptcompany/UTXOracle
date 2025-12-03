# Quickstart Guide: Real-time Mempool Whale Detection

## Prerequisites

Before starting, ensure you have:

1. **Python 3.8+** installed
2. **mempool.space Docker stack** running locally
3. **WhaleFlowDetector** implemented (from feature 004)
4. **DuckDB** installed (`pip install duckdb`)

Verify prerequisites:

```bash
# Check Python version
python3 --version  # Should be 3.8 or higher

# Check mempool.space is running
curl http://localhost:8999/api/v1/prices  # Should return BTC price

# Check WhaleFlowDetector exists
ls scripts/whale_flow_detector.py  # Should exist

# Check DuckDB
python3 -c "import duckdb; print(duckdb.__version__)"
```

## Installation

### 1. Install Python Dependencies

```bash
# Using UV (recommended)
uv pip install websockets asyncio aiohttp psutil

# Or using pip
pip install websockets asyncio aiohttp psutil
```

### 2. Create Database

```bash
# Create data directory if not exists
mkdir -p data

# Initialize database with schema
python3 -c "
import duckdb

conn = duckdb.connect('data/mempool_predictions.db')

# Create tables
conn.execute('''
    CREATE TABLE IF NOT EXISTS mempool_predictions (
        prediction_id TEXT PRIMARY KEY,
        transaction_id TEXT NOT NULL,
        flow_type TEXT NOT NULL,
        btc_value REAL NOT NULL CHECK (btc_value > 100),
        fee_rate REAL NOT NULL CHECK (fee_rate > 0),
        urgency_score REAL NOT NULL CHECK (urgency_score >= 0 AND urgency_score <= 1),
        rbf_enabled BOOLEAN NOT NULL,
        detection_timestamp TIMESTAMP NOT NULL,
        predicted_confirmation_block INTEGER,
        exchange_addresses TEXT,
        confidence_score REAL,
        was_modified BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

conn.execute('''
    CREATE TABLE IF NOT EXISTS prediction_outcomes (
        outcome_id TEXT PRIMARY KEY,
        prediction_id TEXT NOT NULL,
        transaction_id TEXT NOT NULL,
        predicted_flow TEXT NOT NULL,
        actual_outcome TEXT,
        confirmation_time TIMESTAMP,
        confirmation_block INTEGER,
        accuracy_score REAL,
        time_to_confirmation INTEGER,
        final_fee_rate REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

print('Database initialized successfully')
conn.close()
"
```

## Quick Start

### 1. Start the Whale Monitor (Backend)

```python
# scripts/mempool_whale_monitor.py - Minimal example

import asyncio
import websockets
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def monitor_mempool():
    uri = "ws://localhost:8999/ws/track-mempool-tx"

    async with websockets.connect(uri) as websocket:
        logger.info("Connected to mempool.space WebSocket")

        # Subscribe to transaction stream
        await websocket.send(json.dumps({
            "action": "subscribe",
            "type": "mempool-tx"
        }))

        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)

                # Check if transaction is whale (>100 BTC)
                if 'value' in data and data['value'] > 10000000000:  # 100 BTC in sats
                    btc_value = data['value'] / 100000000
                    logger.info(f"🐋 WHALE ALERT: {btc_value:.2f} BTC - TX: {data['txid']}")

                    # Here you would:
                    # 1. Call WhaleFlowDetector.classify_transaction()
                    # 2. Calculate urgency score
                    # 3. Store in database
                    # 4. Broadcast to dashboard clients

            except Exception as e:
                logger.error(f"Error processing message: {e}")

if __name__ == "__main__":
    asyncio.run(monitor_mempool())
```

Run it:
```bash
python3 scripts/mempool_whale_monitor.py
```

### 2. Start the Alert Broadcaster (WebSocket Server)

```python
# scripts/whale_alert_broadcaster.py - Minimal example

import asyncio
import websockets
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Connected clients
clients = set()

async def handle_client(websocket):
    """Handle a connected dashboard client."""
    clients.add(websocket)
    logger.info(f"Client connected. Total: {len(clients)}")

    try:
        await websocket.wait_closed()
    finally:
        clients.remove(websocket)
        logger.info(f"Client disconnected. Total: {len(clients)}")

async def broadcast_alert(alert_data):
    """Broadcast alert to all connected clients."""
    if clients:
        message = json.dumps({
            "type": "whale_alert",
            "data": alert_data,
            "timestamp": datetime.now().isoformat()
        })

        await asyncio.gather(
            *[client.send(message) for client in clients],
            return_exceptions=True
        )

async def start_server():
    """Start WebSocket server for dashboard clients."""
    async with websockets.serve(handle_client, "localhost", 8765):
        logger.info("Alert broadcaster started on ws://localhost:8765")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(start_server())
```

Run it:
```bash
python3 scripts/whale_alert_broadcaster.py
```

### 3. Test the Dashboard Connection

Create a simple test client:

```html
<!-- test_dashboard.html -->
<!DOCTYPE html>
<html>
<head>
    <title>Whale Alert Test</title>
</head>
<body>
    <h1>Mempool Whale Alerts</h1>
    <div id="alerts"></div>

    <script>
        const ws = new WebSocket('ws://localhost:8765');

        ws.onopen = () => {
            console.log('Connected to whale alert server');
            document.getElementById('alerts').innerHTML += '<p>✅ Connected</p>';
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('Whale alert:', data);

            if (data.type === 'whale_alert') {
                const alert = data.data;
                document.getElementById('alerts').innerHTML +=
                    `<p>🐋 ${alert.btc_value} BTC - ${alert.flow_type} - Urgency: ${alert.urgency_score}</p>`;
            }
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            document.getElementById('alerts').innerHTML += '<p>❌ Connection error</p>';
        };
    </script>
</body>
</html>
```

Open in browser:
```bash
python3 -m http.server 8080
# Then visit http://localhost:8080/test_dashboard.html
```

## Full Integration Example

### Complete Monitoring Script with WhaleFlowDetector

```python
# Full integration example
import asyncio
import sys
sys.path.append('scripts')  # Add scripts directory to path

from whale_flow_detector import WhaleFlowDetector
from whale_urgency_scorer import calculate_urgency_score
from whale_alert_broadcaster import broadcast_alert
import duckdb
import uuid

async def process_mempool_transaction(tx_data):
    """Process a transaction from mempool."""

    # Initialize WhaleFlowDetector
    detector = WhaleFlowDetector()

    # Classify transaction
    result = await detector.classify_transaction(tx_data)

    if result and result['btc_value'] > 100:
        # Calculate urgency
        urgency = calculate_urgency_score(tx_data['fee_rate'])

        # Create prediction
        prediction = {
            'prediction_id': str(uuid.uuid4()),
            'transaction_id': tx_data['txid'],
            'flow_type': result['flow_type'],
            'btc_value': result['btc_value'],
            'fee_rate': tx_data['fee_rate'],
            'urgency_score': urgency,
            'rbf_enabled': tx_data.get('rbf', False),
            'detection_timestamp': datetime.now().isoformat(),
            'exchange_addresses': result['exchange_addresses'],
            'confidence_score': urgency * 0.7 + 0.3  # Simple confidence
        }

        # Store in database
        conn = duckdb.connect('data/mempool_predictions.db')
        conn.execute('''
            INSERT INTO mempool_predictions
            (prediction_id, transaction_id, flow_type, btc_value, fee_rate,
             urgency_score, rbf_enabled, detection_timestamp, exchange_addresses,
             confidence_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', tuple(prediction.values()))
        conn.close()

        # Broadcast alert
        await broadcast_alert(prediction)

        return prediction

    return None
```

## Testing

### 1. Unit Test Example

```python
# tests/test_mempool_whale/test_urgency_scorer.py
import pytest
from scripts.whale_urgency_scorer import calculate_urgency_score

def test_urgency_score_calculation():
    # Low fee = low urgency
    assert calculate_urgency_score(5) < 0.3

    # Medium fee = medium urgency
    assert 0.3 <= calculate_urgency_score(25) <= 0.7

    # High fee = high urgency
    assert calculate_urgency_score(100) > 0.8

    # Score capped at 1.0
    assert calculate_urgency_score(1000) == 1.0
```

Run tests:
```bash
pytest tests/test_mempool_whale/
```

### 2. Integration Test Example

```python
# tests/integration/test_mempool_realtime.py
import pytest
import asyncio
import websockets

@pytest.mark.asyncio
async def test_websocket_connection():
    """Test connection to mempool.space WebSocket."""
    uri = "ws://localhost:8999/ws/track-mempool-tx"

    async with websockets.connect(uri) as ws:
        # Should connect successfully
        assert ws.open

        # Should receive data
        message = await asyncio.wait_for(ws.recv(), timeout=10)
        assert message is not None
```

## Monitoring & Debugging

### Check System Status

```python
# scripts/check_status.py
import psutil
import duckdb
import asyncio
import websockets

def check_system():
    # Check memory usage
    memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
    print(f"Memory usage: {memory_mb:.1f} MB")

    # Check database
    conn = duckdb.connect('data/mempool_predictions.db', read_only=True)
    count = conn.execute("SELECT COUNT(*) FROM mempool_predictions").fetchone()[0]
    print(f"Total predictions: {count}")

    # Check pending predictions
    pending = conn.execute("""
        SELECT COUNT(*) FROM mempool_predictions
        WHERE prediction_id NOT IN (
            SELECT prediction_id FROM prediction_outcomes
        )
    """).fetchone()[0]
    print(f"Pending predictions: {pending}")
    conn.close()

async def check_websocket():
    try:
        async with websockets.connect("ws://localhost:8765") as ws:
            print("✅ Alert broadcaster is running")
    except:
        print("❌ Alert broadcaster is not running")

if __name__ == "__main__":
    check_system()
    asyncio.run(check_websocket())
```

### View Logs

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Run with verbose output
python3 -u scripts/mempool_whale_monitor.py 2>&1 | tee whale_monitor.log

# Follow logs in real-time
tail -f whale_monitor.log | grep "WHALE ALERT"
```

## Production Deployment

### 1. SystemD Service

```ini
# /etc/systemd/system/whale-monitor.service
[Unit]
Description=Mempool Whale Monitor
After=network.target docker.service

[Service]
Type=simple
User=bitcoin
WorkingDirectory=/media/sam/1TB/UTXOracle
ExecStart=/usr/bin/python3 scripts/mempool_whale_monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable whale-monitor
sudo systemctl start whale-monitor
sudo systemctl status whale-monitor
```

### 2. Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.8-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY scripts/ ./scripts/
COPY data/ ./data/

CMD ["python3", "scripts/mempool_whale_monitor.py"]
```

Build and run:
```bash
docker build -t whale-monitor .
docker run -d --name whale-monitor \
    --network host \
    -v $(pwd)/data:/app/data \
    whale-monitor
```

## Troubleshooting

### WebSocket Connection Failed

```bash
# Check mempool.space is running
docker ps | grep mempool

# Test WebSocket endpoint
wscat -c ws://localhost:8999/ws/track-mempool-tx

# Check firewall
sudo ufw status
```

### High Memory Usage

```python
# Add memory monitoring
import gc
import psutil

def check_memory_pressure():
    memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
    if memory_mb > 400:  # 80% of 500MB limit
        gc.collect()  # Force garbage collection
        return True
    return False
```

### Missing Transactions

```python
# Add comprehensive logging
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('whale_monitor.log'),
        logging.StreamHandler()
    ]
)
```

## Next Steps

1. **Enhance Urgency Scoring**: Integrate with mempool.space fee estimates API
2. **Add Redis Support**: Prepare for NautilusTrader integration
3. **Implement Webhooks**: Allow external systems to receive alerts
4. **Dashboard Polish**: Enhance visualization with charts and statistics
5. **Performance Tuning**: Optimize for high-volume transaction streams

---

**Quick Reference Card**

| Component | Port | Purpose |
|-----------|------|---------|
| mempool.space WS | 8999 | Transaction stream |
| Alert Broadcaster | 8765 | Dashboard WebSocket |
| REST API | 8000 | Historical queries |
| Test Dashboard | 8080 | Development UI |

| File | Purpose |
|------|---------|
| `scripts/mempool_whale_monitor.py` | Main monitoring service |
| `scripts/whale_urgency_scorer.py` | Fee urgency calculation |
| `scripts/whale_alert_broadcaster.py` | WebSocket server |
| `data/mempool_predictions.db` | DuckDB database |

---

*For complete documentation, see the full specification in `/specs/005-mempool-whale-realtime/`*