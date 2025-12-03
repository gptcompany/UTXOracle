# Whale Detection Dashboard - API Documentation

**Version**: 1.0
**Last Updated**: 2025-11-29
**Base URL**: `http://localhost:8000` (development) | `https://your-domain.com` (production)

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [REST API Endpoints](#rest-api-endpoints)
4. [WebSocket API](#websocket-api)
5. [Data Models](#data-models)
6. [Error Handling](#error-handling)
7. [Rate Limiting](#rate-limiting)
8. [Examples](#examples)

---

## Overview

The Whale Detection Dashboard API provides real-time and historical data about Bitcoin whale transactions (>100 BTC). The API supports both REST endpoints for historical data and WebSocket connections for real-time streaming.

### Key Features

- Real-time whale transaction monitoring
- Net flow calculations (buy/sell pressure)
- Historical data access (24h charts)
- WebSocket streaming for live updates
- Multi-channel alert system

### Technology Stack

- **Backend**: FastAPI (Python 3.8+)
- **WebSocket**: Native FastAPI WebSocket support
- **Database**: DuckDB (for historical data)
- **Frontend**: Vanilla JavaScript + Plotly.js

---

## Authentication

### Development Mode (No Auth)

Currently, the dashboard operates without authentication for development. All endpoints are publicly accessible.

### Production Mode (JWT - Future)

WebSocket connections will require JWT authentication:

```javascript
const token = await fetch('/api/auth/token').then(r => r.json());
const ws = new WebSocket(`ws://localhost:8000/ws/whale?token=${token.access_token}`);
```

---

## REST API Endpoints

### 1. Get Latest Whale Data

**Endpoint**: `GET /api/whale/latest`

Returns the most recent whale net flow data.

#### Response

```json
{
  "whale_net_flow": 250.5,
  "whale_direction": "BUY",
  "btc_price": 95000,
  "timestamp": "2025-11-29T14:30:00Z",
  "window_minutes": 5
}
```

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `whale_net_flow` | float | Net BTC flow (positive = accumulation, negative = distribution) |
| `whale_direction` | string | Direction: "BUY", "SELL", or "NEUTRAL" |
| `btc_price` | float | Current BTC/USD price |
| `timestamp` | string | ISO 8601 timestamp |
| `window_minutes` | int | Time window for calculation (default: 5) |

#### Example

```bash
curl http://localhost:8000/api/whale/latest
```

```javascript
const data = await fetch('/api/whale/latest').then(r => r.json());
console.log(`Net flow: ${data.whale_net_flow} BTC (${data.whale_direction})`);
```

---

### 2. Get Historical Net Flow Data

**Endpoint**: `GET /api/whale/history`

Returns historical net flow data for charting.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeframe` | string | `24h` | Time range: `1h`, `6h`, `24h`, `7d` |
| `interval` | int | `5` | Interval in minutes |

#### Response

```json
{
  "timeframe": "24h",
  "data": [
    {
      "timestamp": "2025-11-29T00:00:00Z",
      "net_flow_btc": 150.2,
      "net_flow_usd": 14269000,
      "direction": "BUY",
      "transaction_count": 12
    },
    ...
  ]
}
```

#### Example

```bash
# Get last 6 hours of data
curl "http://localhost:8000/api/whale/history?timeframe=6h&interval=5"
```

```javascript
// Fetch and plot historical data
const history = await fetch('/api/whale/history?timeframe=24h').then(r => r.json());

const timestamps = history.data.map(d => d.timestamp);
const netFlows = history.data.map(d => d.net_flow_btc);

Plotly.newPlot('chart', [{
  x: timestamps,
  y: netFlows,
  type: 'scatter',
  mode: 'lines',
  name: 'Net Flow'
}]);
```

---

### 3. Get Recent Whale Transactions

**Endpoint**: `GET /api/whale/transactions`

Returns recent whale transactions (>100 BTC).

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | `50` | Max transactions to return (1-100) |
| `min_amount` | float | `100` | Min BTC amount filter |
| `direction` | string | - | Filter by direction: "BUY", "SELL", "NEUTRAL" |
| `min_urgency` | int | - | Filter by urgency score (0-100) |

#### Response

```json
{
  "count": 25,
  "transactions": [
    {
      "transaction_id": "abc123...",
      "timestamp": "2025-11-29T14:25:30Z",
      "amount_btc": 523.45,
      "amount_usd": 49727750,
      "direction": "SELL",
      "urgency_score": 85,
      "fee_rate": 50.5,
      "is_mempool": true
    },
    ...
  ]
}
```

#### Example

```bash
# Get last 20 high-urgency sell transactions
curl "http://localhost:8000/api/whale/transactions?limit=20&direction=SELL&min_urgency=80"
```

```javascript
// Filter and display transactions
const txs = await fetch('/api/whale/transactions?min_amount=200').then(r => r.json());

txs.transactions.forEach(tx => {
  console.log(`${tx.direction}: ${tx.amount_btc.toFixed(2)} BTC @ ${tx.fee_rate} sat/vB`);
});
```

---

### 4. Health Check

**Endpoint**: `GET /health`

Returns API health status.

#### Response

```json
{
  "status": "healthy",
  "version": "1.0",
  "uptime_seconds": 3600,
  "connections": {
    "websocket": 15,
    "http": 23
  }
}
```

---

## WebSocket API

### Connection

**URL**: `ws://localhost:8000/ws/whale`

**Protocol**: WebSocket (RFC 6455)

### Connection Flow

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/whale');

ws.onopen = () => {
  console.log('Connected to Whale WebSocket');

  // Subscribe to channels
  ws.send(JSON.stringify({
    type: 'subscribe',
    channels: ['transactions', 'netflow', 'alerts']
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Received:', message.type, message.data);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('WebSocket closed');
};
```

### Message Types

#### 1. Subscribe

**Client → Server**

```json
{
  "type": "subscribe",
  "channels": ["transactions", "netflow", "alerts"]
}
```

#### 2. Transaction Event

**Server → Client**

```json
{
  "type": "transaction",
  "data": {
    "transaction_id": "abc123...",
    "timestamp": "2025-11-29T14:25:30Z",
    "amount_btc": 523.45,
    "amount_usd": 49727750,
    "direction": "SELL",
    "urgency_score": 85,
    "fee_rate": 50.5,
    "is_mempool": true
  }
}
```

#### 3. Net Flow Update

**Server → Client**

```json
{
  "type": "netflow",
  "data": {
    "net_flow_btc": 250.5,
    "net_flow_usd": 23797500,
    "direction": "BUY",
    "timestamp": "2025-11-29T14:30:00Z"
  }
}
```

#### 4. Alert Event

**Server → Client**

```json
{
  "type": "alert",
  "data": {
    "severity": "critical",
    "message": "🚨 ↓ 523.45 BTC ($49.73M)",
    "transaction_id": "abc123...",
    "timestamp": "2025-11-29T14:25:30Z"
  }
}
```

#### 5. Error

**Server → Client**

```json
{
  "type": "error",
  "message": "Invalid subscription channel",
  "code": "INVALID_CHANNEL"
}
```

---

## Data Models

### Transaction

```typescript
interface Transaction {
  transaction_id: string;      // Bitcoin transaction hash
  timestamp: string;            // ISO 8601 timestamp
  amount_btc: number;          // Amount in BTC
  amount_usd: number;          // Equivalent USD value
  direction: "BUY" | "SELL" | "NEUTRAL";  // Transaction direction
  urgency_score: number;       // 0-100, higher = more urgent
  fee_rate: number;            // Satoshis per virtual byte
  is_mempool: boolean;         // True if unconfirmed
}
```

### NetFlowData

```typescript
interface NetFlowData {
  net_flow_btc: number;        // Net BTC flow
  net_flow_usd: number;        // Equivalent USD value
  direction: "BUY" | "SELL" | "NEUTRAL";
  timestamp: string;            // ISO 8601 timestamp
  window_minutes?: number;     // Time window (default: 5)
}
```

### Alert

```typescript
interface Alert {
  severity: "critical" | "high" | "medium";
  message: string;
  transaction_id: string;
  timestamp: string;
}
```

---

## Error Handling

### HTTP Error Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request (invalid parameters) |
| 404 | Not Found |
| 429 | Too Many Requests (rate limited) |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

### Error Response Format

```json
{
  "error": {
    "code": "INVALID_TIMEFRAME",
    "message": "Timeframe must be one of: 1h, 6h, 24h, 7d",
    "details": {
      "provided": "12h",
      "allowed": ["1h", "6h", "24h", "7d"]
    }
  }
}
```

---

## Rate Limiting

### REST API

- **Limit**: 100 requests per minute per IP
- **Headers**:
  - `X-RateLimit-Limit`: Max requests per window
  - `X-RateLimit-Remaining`: Remaining requests
  - `X-RateLimit-Reset`: Unix timestamp when limit resets

### WebSocket

- **Connection Limit**: 5 connections per IP
- **Message Rate**: 10 messages per second per connection

---

## Examples

### Complete Dashboard Integration

```javascript
class WhaleDashboardAPI {
  constructor(baseURL = 'http://localhost:8000') {
    this.baseURL = baseURL;
    this.ws = null;
  }

  // REST API - Get latest data
  async getLatest() {
    const response = await fetch(`${this.baseURL}/api/whale/latest`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  // REST API - Get historical data
  async getHistory(timeframe = '24h') {
    const response = await fetch(
      `${this.baseURL}/api/whale/history?timeframe=${timeframe}`
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  // WebSocket - Connect and subscribe
  connectWebSocket(onTransaction, onNetFlow, onAlert) {
    const wsURL = this.baseURL.replace('http', 'ws');
    this.ws = new WebSocket(`${wsURL}/ws/whale`);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.ws.send(JSON.stringify({
        type: 'subscribe',
        channels: ['transactions', 'netflow', 'alerts']
      }));
    };

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);

      switch (message.type) {
        case 'transaction':
          onTransaction(message.data);
          break;
        case 'netflow':
          onNetFlow(message.data);
          break;
        case 'alert':
          onAlert(message.data);
          break;
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.ws.onclose = () => {
      console.log('WebSocket closed - reconnecting in 5s');
      setTimeout(() => this.connectWebSocket(onTransaction, onNetFlow, onAlert), 5000);
    };
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// Usage
const api = new WhaleDashboardAPI();

// Fetch latest data
const latest = await api.getLatest();
console.log(`Current net flow: ${latest.whale_net_flow} BTC`);

// Connect to real-time feed
api.connectWebSocket(
  (tx) => console.log('New transaction:', tx),
  (netflow) => console.log('Net flow update:', netflow),
  (alert) => console.log('ALERT:', alert)
);
```

### Python Client Example

```python
import asyncio
import aiohttp
import websockets
import json

class WhaleAPIClient:
    def __init__(self, base_url='http://localhost:8000'):
        self.base_url = base_url
        self.ws_url = base_url.replace('http', 'ws')

    async def get_latest(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self.base_url}/api/whale/latest') as resp:
                return await resp.json()

    async def stream_transactions(self):
        async with websockets.connect(f'{self.ws_url}/ws/whale') as ws:
            # Subscribe
            await ws.send(json.dumps({
                'type': 'subscribe',
                'channels': ['transactions', 'netflow']
            }))

            # Listen for messages
            async for message in ws:
                data = json.loads(message)
                print(f"Received: {data['type']}")
                yield data

# Usage
async def main():
    client = WhaleAPIClient()

    # Get latest
    latest = await client.get_latest()
    print(f"Net flow: {latest['whale_net_flow']} BTC")

    # Stream real-time data
    async for message in client.stream_transactions():
        if message['type'] == 'transaction':
            tx = message['data']
            print(f"{tx['direction']}: {tx['amount_btc']:.2f} BTC")

asyncio.run(main())
```

---

## Support

For issues or feature requests, contact: [Your Support Info]

**GitHub**: https://github.com/your-repo/UTXOracle
**Documentation**: https://docs.your-domain.com
