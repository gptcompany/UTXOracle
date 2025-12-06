# Data Model: Webhook Alert System

**Feature**: spec-011 | **Date**: 2025-12-04

## Entities

### AlertEvent

Core event structure emitted to webhooks.

```python
@dataclass
class AlertEvent:
    event_id: str           # UUID v4
    event_type: str         # "whale" | "signal" | "regime" | "price"
    timestamp: datetime     # UTC timestamp
    severity: str           # "critical" | "high" | "medium" | "low"
    payload: dict           # Event-specific data

    def to_webhook_payload(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity,
            "payload": self.payload
        }
```

### WebhookConfig

Configuration loaded from environment variables.

```python
@dataclass
class WebhookConfig:
    url: str                        # ALERT_WEBHOOK_URL
    secret: str | None = None       # ALERT_WEBHOOK_SECRET (optional)
    timeout_seconds: float = 5.0    # Request timeout
    max_retries: int = 3            # Retry attempts
    enabled: bool = True            # ALERT_ENABLED
    min_severity: str = "medium"    # ALERT_MIN_SEVERITY

    # Per-event-type toggles
    whale_enabled: bool = True      # ALERT_WHALE_ENABLED
    signal_enabled: bool = True     # ALERT_SIGNAL_ENABLED
    regime_enabled: bool = True     # ALERT_REGIME_ENABLED
    price_enabled: bool = True      # ALERT_PRICE_ENABLED

    # Thresholds
    whale_min_btc: float = 100.0    # ALERT_WHALE_MIN_BTC
    signal_min_confidence: float = 0.7  # ALERT_SIGNAL_MIN_CONFIDENCE
    price_min_divergence: float = 3.0   # ALERT_PRICE_MIN_DIVERGENCE

    @classmethod
    def from_env(cls) -> "WebhookConfig":
        return cls(
            url=os.getenv("ALERT_WEBHOOK_URL", ""),
            secret=os.getenv("ALERT_WEBHOOK_SECRET"),
            enabled=os.getenv("ALERT_ENABLED", "true").lower() == "true",
            min_severity=os.getenv("ALERT_MIN_SEVERITY", "medium"),
            whale_enabled=os.getenv("ALERT_WHALE_ENABLED", "true").lower() == "true",
            signal_enabled=os.getenv("ALERT_SIGNAL_ENABLED", "true").lower() == "true",
            regime_enabled=os.getenv("ALERT_REGIME_ENABLED", "true").lower() == "true",
            price_enabled=os.getenv("ALERT_PRICE_ENABLED", "true").lower() == "true",
            whale_min_btc=float(os.getenv("ALERT_WHALE_MIN_BTC", "100")),
            signal_min_confidence=float(os.getenv("ALERT_SIGNAL_MIN_CONFIDENCE", "0.7")),
            price_min_divergence=float(os.getenv("ALERT_PRICE_MIN_DIVERGENCE", "3.0")),
        )
```

### WebhookDelivery

Tracks delivery status for audit/replay.

```python
@dataclass
class WebhookDelivery:
    delivery_id: str            # UUID v4
    event_id: str               # Reference to AlertEvent
    webhook_url: str            # Target URL
    status: str                 # "pending" | "sent" | "failed"
    attempt_count: int = 0      # Number of attempts
    response_code: int | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    sent_at: datetime | None = None
```

## Event Payloads

### Whale Event Payload

```python
WhalePayload = TypedDict('WhalePayload', {
    'amount_btc': float,
    'direction': str,        # "INFLOW" | "OUTFLOW"
    'exchange': str | None,  # Exchange name if known
    'signal_vote': float,    # -1.0 to +1.0
    'usd_value': float       # Amount in USD
})
```

### Signal Event Payload

```python
SignalPayload = TypedDict('SignalPayload', {
    'action': str,           # "BUY" | "SELL"
    'confidence': float,     # 0.0 to 1.0
    'signal_mean': float,    # -1.0 to +1.0
    'top_contributors': list[dict]  # [{name, value}, ...]
})
```

### Regime Event Payload

```python
RegimePayload = TypedDict('RegimePayload', {
    'metric': str,           # "power_law" | "symbolic" | "wasserstein"
    'from_state': str,       # Previous regime
    'to_state': str,         # New regime
    'details': dict,         # Metric-specific details
    'implication': str       # Human-readable interpretation
})
```

### Price Event Payload

```python
PricePayload = TypedDict('PricePayload', {
    'utxoracle_price': float,
    'exchange_price': float,
    'divergence_pct': float,
    'direction': str         # "ABOVE" | "BELOW"
})
```

## Database Schema

### alert_events Table

```sql
CREATE TABLE IF NOT EXISTS alert_events (
    event_id VARCHAR PRIMARY KEY,
    event_type VARCHAR NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    severity VARCHAR NOT NULL,
    payload JSON NOT NULL,
    webhook_status VARCHAR DEFAULT 'pending',
    webhook_attempts INTEGER DEFAULT 0,
    webhook_response_code INTEGER,
    webhook_error VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_alert_type ON alert_events(event_type);
CREATE INDEX IF NOT EXISTS idx_alert_severity ON alert_events(severity);
CREATE INDEX IF NOT EXISTS idx_alert_timestamp ON alert_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_alert_status ON alert_events(webhook_status);
```

## Severity Levels

| Level | Description | Examples |
|-------|-------------|----------|
| critical | Immediate action required | >1000 BTC whale, >95% confidence signal |
| high | Important, time-sensitive | >500 BTC whale, >85% confidence signal |
| medium | Noteworthy | >100 BTC whale, >70% confidence signal |
| low | Informational | Price divergence, minor regime shifts |

## Relationships

```
AlertEvent (1) ──────► (1) WebhookDelivery
     │
     │ stored in
     ▼
alert_events table (DuckDB)
```
