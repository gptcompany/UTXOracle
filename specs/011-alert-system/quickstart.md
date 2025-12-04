# Quickstart: Webhook Alert System

**Feature**: spec-011 | **Date**: 2025-12-04

## Setup

### 1. Configure Environment Variables

```bash
# .env
ALERT_WEBHOOK_URL=http://localhost:5678/webhook/utxoracle-alerts
ALERT_WEBHOOK_SECRET=your-optional-hmac-secret
ALERT_ENABLED=true
ALERT_MIN_SEVERITY=medium

# Event toggles
ALERT_WHALE_ENABLED=true
ALERT_SIGNAL_ENABLED=true
ALERT_REGIME_ENABLED=true
ALERT_PRICE_ENABLED=true

# Thresholds
ALERT_WHALE_MIN_BTC=100
ALERT_SIGNAL_MIN_CONFIDENCE=0.7
ALERT_PRICE_MIN_DIVERGENCE=3.0
```

### 2. Import N8N Workflow

1. Open N8N at `http://localhost:5678`
2. Go to Workflows → Import from File
3. Select `examples/n8n/utxoracle-alerts.json`
4. Configure your Telegram/Discord/Slack credentials
5. Activate the workflow

### 3. Test Webhook

```bash
# Send test event
curl -X POST http://localhost:5678/webhook/utxoracle-alerts \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "test-001",
    "event_type": "whale",
    "timestamp": "2025-12-04T15:30:00Z",
    "severity": "high",
    "payload": {
      "amount_btc": 500,
      "direction": "INFLOW",
      "signal_vote": -0.7
    }
  }'
```

## Programmatic Usage

### Emit Alert from Code

```python
from scripts.alerts import emit_alert, create_whale_event

# Create and emit whale event
event = create_whale_event(
    amount_btc=500,
    direction="INFLOW",
    signal_vote=-0.7,
    exchange="binance"
)

# Emit to webhook (async)
await emit_alert(event)

# Or sync version
emit_alert_sync(event)
```

### Manual Event Creation

```python
from scripts.alerts import AlertEvent, emit_alert
from datetime import datetime
from uuid import uuid4

event = AlertEvent(
    event_id=str(uuid4()),
    event_type="signal",
    timestamp=datetime.utcnow(),
    severity="high",
    payload={
        "action": "BUY",
        "confidence": 0.85,
        "signal_mean": 0.65,
        "top_contributors": [
            {"name": "whale", "value": 0.60},
            {"name": "symbolic", "value": 0.80}
        ]
    }
)

await emit_alert(event)
```

## Webhook Payload Examples

### Whale Event

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "whale",
  "timestamp": "2025-12-04T15:30:00Z",
  "severity": "high",
  "payload": {
    "amount_btc": 500.0,
    "direction": "INFLOW",
    "exchange": "binance",
    "signal_vote": -0.70,
    "usd_value": 50000000
  }
}
```

### Signal Event

```json
{
  "event_id": "...",
  "event_type": "signal",
  "timestamp": "2025-12-04T15:30:00Z",
  "severity": "high",
  "payload": {
    "action": "BUY",
    "confidence": 0.85,
    "signal_mean": 0.65,
    "top_contributors": [
      {"name": "whale", "value": 0.60},
      {"name": "symbolic", "value": 0.80},
      {"name": "power_law", "value": 0.40}
    ]
  }
}
```

### Regime Event

```json
{
  "event_id": "...",
  "event_type": "regime",
  "timestamp": "2025-12-04T15:30:00Z",
  "severity": "medium",
  "payload": {
    "metric": "power_law",
    "from_state": "NEUTRAL",
    "to_state": "ACCUMULATION",
    "details": {"tau_old": 2.0, "tau_new": 1.6},
    "implication": "Whale concentration increasing"
  }
}
```

### Price Event

```json
{
  "event_id": "...",
  "event_type": "price",
  "timestamp": "2025-12-04T15:30:00Z",
  "severity": "low",
  "payload": {
    "utxoracle_price": 100000,
    "exchange_price": 97000,
    "divergence_pct": 3.09,
    "direction": "ABOVE"
  }
}
```

## N8N Workflow Structure

```
[Webhook Trigger]
       │
       ▼
[Switch: event_type]
   │   │   │   │
   ▼   ▼   ▼   ▼
whale signal regime price
   │   │   │   │
   ▼   ▼   ▼   ▼
[Format Message]
       │
       ▼
[Switch: severity]
       │
   ┌───┴───┐
   ▼       ▼
critical  other
   │       │
   ▼       ▼
[Telegram + Discord] [Telegram only]
```

## HMAC Signature Verification (N8N)

If `ALERT_WEBHOOK_SECRET` is set, verify signature in N8N:

```javascript
// N8N Function node
const crypto = require('crypto');
const secret = $env.UTXORACLE_WEBHOOK_SECRET;
const signature = $input.first().headers['x-utxoracle-signature'];
const payload = JSON.stringify($input.first().json);

const expected = crypto
  .createHmac('sha256', secret)
  .update(payload)
  .digest('hex');

if (signature !== `sha256=${expected}`) {
  throw new Error('Invalid signature');
}

return $input.first();
```

## Troubleshooting

### Webhook not receiving events

1. Check `ALERT_WEBHOOK_URL` is set correctly
2. Verify N8N workflow is active
3. Check UTXOracle logs for errors
4. Test with curl to verify endpoint is reachable

### Events logged but not delivered

1. Check `webhook_status` in `alert_events` table
2. Review `webhook_error` column for failure reason
3. Verify network connectivity to webhook URL

### Events filtered unexpectedly

1. Check `ALERT_MIN_SEVERITY` setting
2. Verify per-event-type toggles (ALERT_WHALE_ENABLED, etc.)
3. Check threshold settings match your expectations
