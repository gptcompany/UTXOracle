# WebSocket Message Contracts

**Feature**: Real-Time Whale Detection Dashboard
**Protocol**: WebSocket (wss://)
**Endpoint**: `/ws/whale-alerts`
**Date**: 2025-11-25

## Connection Protocol

### Connection Handshake

**Request**:
```http
GET /ws/whale-alerts?token=<JWT_TOKEN> HTTP/1.1
Host: localhost:8001
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Sec-WebSocket-Extensions: permessage-deflate
```

**Response** (Success):
```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
Sec-WebSocket-Extensions: permessage-deflate
```

**Response** (Auth Failure):
```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"error": "Invalid or expired token"}
```

## Message Types

All messages follow this base structure:

```typescript
interface BaseMessage {
  type: string;           // Message type identifier
  timestamp: number;      // Unix timestamp (milliseconds)
  sequence: number;       // Message sequence number
}
```

### 1. Client → Server Messages

#### 1.1 Subscribe

Subscribe to specific data streams.

```json
{
  "type": "subscribe",
  "timestamp": 1700000000000,
  "sequence": 1,
  "channels": ["transactions", "netflow", "alerts"],
  "filters": {
    "min_amount": 100,
    "max_amount": null,
    "urgency_threshold": 0
  }
}
```

#### 1.2 Unsubscribe

Unsubscribe from data streams.

```json
{
  "type": "unsubscribe",
  "timestamp": 1700000000000,
  "sequence": 2,
  "channels": ["alerts"]
}
```

#### 1.3 Ping

Keep-alive message.

```json
{
  "type": "ping",
  "timestamp": 1700000000000,
  "sequence": 3
}
```

#### 1.4 Request Historical

Request historical data.

```json
{
  "type": "historical_request",
  "timestamp": 1700000000000,
  "sequence": 4,
  "data_type": "netflow",
  "time_range": {
    "start": 1699900000000,
    "end": 1700000000000,
    "interval": "5m"
  }
}
```

### 2. Server → Client Messages

#### 2.1 Transaction Update

New whale transaction detected.

```json
{
  "type": "transaction",
  "timestamp": 1700000000000,
  "sequence": 1001,
  "data": {
    "transaction_id": "3a5f...8b2c",
    "amount_btc": 150.5,
    "amount_usd": 6022500.00,
    "direction": "BUY",
    "urgency_score": 82,
    "fee_rate": 45.5,
    "timestamp": "2025-11-25T19:30:00Z",
    "block_height": null,
    "is_mempool": true,
    "confidence": 0.95
  }
}
```

#### 2.2 Net Flow Update

Aggregated flow metrics update.

```json
{
  "type": "netflow",
  "timestamp": 1700000000000,
  "sequence": 1002,
  "data": {
    "period_start": "2025-11-25T19:25:00Z",
    "period_end": "2025-11-25T19:30:00Z",
    "interval": "5m",
    "net_flow_btc": 245.8,
    "net_flow_usd": 9832000.00,
    "total_buy_btc": 520.3,
    "total_sell_btc": 274.5,
    "transaction_count": 8,
    "direction": "ACCUMULATION",
    "strength": 0.72,
    "largest_tx_btc": 150.5
  }
}
```

#### 2.3 Alert Notification

Critical whale movement alert.

```json
{
  "type": "alert",
  "timestamp": 1700000000000,
  "sequence": 1003,
  "data": {
    "alert_id": "alert_123456",
    "transaction_id": "3a5f...8b2c",
    "severity": "HIGH",
    "trigger_type": "SIZE",
    "threshold_value": 500,
    "title": "Massive Whale Movement Detected",
    "message": "550 BTC moved with high urgency score (92/100)",
    "amount_btc": 550,
    "amount_usd": 22000000.00,
    "direction": "SELL"
  }
}
```

#### 2.4 Historical Response

Response to historical data request.

```json
{
  "type": "historical_response",
  "timestamp": 1700000000000,
  "sequence": 1004,
  "request_sequence": 4,
  "data": {
    "data_type": "netflow",
    "time_range": {
      "start": 1699900000000,
      "end": 1700000000000,
      "interval": "5m"
    },
    "values": [
      {
        "timestamp": "2025-11-25T18:00:00Z",
        "net_flow_btc": 125.5,
        "direction": "ACCUMULATION"
      },
      {
        "timestamp": "2025-11-25T18:05:00Z",
        "net_flow_btc": -85.2,
        "direction": "DISTRIBUTION"
      }
    ]
  }
}
```

#### 2.5 Connection Acknowledgment

Confirms successful subscription.

```json
{
  "type": "ack",
  "timestamp": 1700000000000,
  "sequence": 1000,
  "request_sequence": 1,
  "status": "success",
  "subscribed_channels": ["transactions", "netflow", "alerts"],
  "server_time": 1700000000000
}
```

#### 2.6 Error Message

Error notification.

```json
{
  "type": "error",
  "timestamp": 1700000000000,
  "sequence": 1005,
  "error": {
    "code": "RATE_LIMIT",
    "message": "Rate limit exceeded: 20 messages/second",
    "retry_after": 1000
  }
}
```

#### 2.7 Pong

Response to ping.

```json
{
  "type": "pong",
  "timestamp": 1700000000000,
  "sequence": 1006,
  "ping_sequence": 3,
  "server_time": 1700000000000
}
```

#### 2.8 Batch Message

Multiple updates in single message (for efficiency).

```json
{
  "type": "batch",
  "timestamp": 1700000000000,
  "sequence": 1007,
  "messages": [
    {
      "type": "transaction",
      "data": { /* transaction data */ }
    },
    {
      "type": "netflow",
      "data": { /* netflow data */ }
    }
  ]
}
```

## Binary Protocol (Optional Optimization)

For high-frequency updates, a binary protocol can be used:

```
[1 byte: message type]
[4 bytes: timestamp (seconds since epoch)]
[2 bytes: sequence number]
[N bytes: message payload (MessagePack encoded)]
```

Message Type Codes:
- `0x01`: Transaction
- `0x02`: Net Flow
- `0x03`: Alert
- `0x04`: Historical
- `0x10`: Ping
- `0x11`: Pong
- `0xFF`: Error

## Error Codes

| Code | Description | Retry |
|------|-------------|-------|
| `AUTH_FAILED` | Authentication failed | No |
| `TOKEN_EXPIRED` | JWT token expired | Yes (refresh) |
| `RATE_LIMIT` | Rate limit exceeded | Yes (backoff) |
| `INVALID_MESSAGE` | Malformed message | No |
| `SUBSCRIPTION_FAILED` | Cannot subscribe to channel | No |
| `SERVER_ERROR` | Internal server error | Yes |
| `MAINTENANCE` | Server under maintenance | Yes |

## Connection Management

### Reconnection Strategy

```javascript
class ReconnectionStrategy {
  baseDelay = 1000;      // 1 second
  maxDelay = 30000;      // 30 seconds
  factor = 1.5;          // Exponential backoff factor
  maxRetries = 10;       // Maximum retry attempts

  calculateDelay(attempt) {
    const delay = Math.min(
      this.baseDelay * Math.pow(this.factor, attempt),
      this.maxDelay
    );
    // Add jitter (±20%)
    return delay * (0.8 + Math.random() * 0.4);
  }
}
```

### Heartbeat Protocol

- Client sends `ping` every 30 seconds
- Server responds with `pong` within 5 seconds
- Connection considered dead after 3 missed pongs
- Automatic reconnection initiated on connection loss

## Rate Limiting

### Message Limits

| Action | Limit | Window | Penalty |
|--------|-------|--------|---------|
| Connection attempts | 5 | 1 minute | 5-minute ban |
| Messages sent | 20 | 1 second | Disconnect |
| Historical requests | 10 | 1 minute | Throttle |
| Subscription changes | 5 | 1 minute | Ignore |

### Throttling Response

When rate limited, server sends:

```json
{
  "type": "error",
  "error": {
    "code": "RATE_LIMIT",
    "message": "Rate limit exceeded",
    "retry_after": 5000,
    "limit": 20,
    "window": 1000,
    "current": 25
  }
}
```

## Security Considerations

### Message Validation

All messages MUST:
- Have valid JSON structure
- Include required fields for message type
- Pass schema validation (see data-model.md)
- Have sequence numbers in ascending order
- Have timestamps within ±5 minutes of server time

### Authentication Flow

1. Client obtains JWT from `/api/auth/token`
2. Client connects with token in query param
3. Server validates token on connection
4. Server checks token expiry before each message
5. Client refreshes token 5 minutes before expiry
6. Server closes connection on invalid/expired token

## Client Implementation Example

```javascript
class WhaleWebSocket {
  constructor(token) {
    this.token = token;
    this.sequence = 0;
    this.ws = null;
  }

  connect() {
    const url = `wss://localhost:8001/ws/whale-alerts?token=${this.token}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.subscribe(['transactions', 'netflow', 'alerts']);
      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      this.handleMessage(message);
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      this.reconnect();
    };
  }

  subscribe(channels) {
    this.send({
      type: 'subscribe',
      channels: channels,
      filters: {
        min_amount: 100,
        urgency_threshold: 0
      }
    });
  }

  send(message) {
    message.timestamp = Date.now();
    message.sequence = ++this.sequence;
    this.ws.send(JSON.stringify(message));
  }

  handleMessage(message) {
    switch(message.type) {
      case 'transaction':
        this.onTransaction(message.data);
        break;
      case 'netflow':
        this.onNetFlow(message.data);
        break;
      case 'alert':
        this.onAlert(message.data);
        break;
      case 'error':
        this.onError(message.error);
        break;
    }
  }
}
```

---

This contract specification ensures:
- ✅ Type safety with defined schemas
- ✅ Security through JWT authentication
- ✅ Resilience with reconnection strategy
- ✅ Performance via batching and binary option
- ✅ Rate limiting for stability