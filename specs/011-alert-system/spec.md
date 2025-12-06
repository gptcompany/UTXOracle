# Feature Specification: Webhook Alert System

**Feature Branch**: `011-alert-system`
**Created**: 2025-12-04
**Status**: Draft (v2 - Webhook-First)
**Prerequisites**: spec-009 (Advanced On-Chain Analytics)
**Input**: User description: "Implement a webhook-based alert system for UTXOracle signals. Emit structured events to configurable webhook endpoints (N8N, Zapier, custom). Support whale movements, regime changes, and high-confidence fusion signals."

## Context & Motivation

### Background: Event-Driven Notifications

UTXOracle generates valuable trading signals stored in DuckDB. Traders need **proactive notifications** but building channel-specific integrations (Telegram, Discord, Slack) violates KISS/YAGNI principles.

**Key Insight**: The user already has N8N workflow infrastructure deployed. Building a Telegram bot duplicates functionality N8N provides out-of-the-box.

### KISS Analysis: Bot vs Webhook

| Approach | Dependencies | LOC | Channels | Maintenance |
|----------|-------------|-----|----------|-------------|
| Telegram Bot | +1 (python-telegram-bot) | ~600 | 1 | High (API changes) |
| **Webhook + N8N** | 0 (httpx already present) | ~150 | Unlimited | Low (JSON contract) |

**Decision**: Webhook-first architecture. UTXOracle emits structured JSON events; external workflow tools (N8N, Zapier, Make) handle delivery to any channel.

### Architecture

```
UTXOracle Signal Pipeline
         │
         ▼
┌─────────────────────┐
│   AlertEvent        │
│   (structured JSON) │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  WebhookDispatcher  │
│  - HTTP POST        │
│  - HMAC signing     │
│  - Basic retry      │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│   N8N / Zapier /    │
│   Custom Endpoint   │
└─────────────────────┘
         │
    ┌────┴────┬────────┬─────────┐
    ▼         ▼        ▼         ▼
Telegram  Discord   Slack    Email
```

### Alert Categories

1. **Whale Events**: Large exchange flows (>100 BTC inflow/outflow)
2. **Signal Events**: High-confidence BUY/SELL fusion signals (>0.7)
3. **Regime Events**: Power law regime change, symbolic dynamics shift
4. **Price Events**: UTXOracle vs Exchange divergence (>3%)

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Webhook Configuration (Priority: P1)

As a system administrator, I want to **configure webhook endpoints**, so alerts are sent to my N8N workflow.

**Why this priority**: Foundation - without webhook config, no alerts. ~30 LOC.

**Independent Test**: Can be fully tested by:
1. Setting ALERT_WEBHOOK_URL environment variable
2. Triggering a test event
3. Verifying HTTP POST received at endpoint

**Acceptance Scenarios**:

1. **Given** ALERT_WEBHOOK_URL is set to valid URL
   **When** system starts
   **Then** webhook dispatcher initializes successfully

2. **Given** ALERT_WEBHOOK_URL is not set
   **When** alert event is generated
   **Then** event logged locally, no HTTP request made

3. **Given** ALERT_WEBHOOK_SECRET is set
   **When** event is dispatched
   **Then** request includes X-UTXOracle-Signature header with HMAC-SHA256

---

### User Story 2 - Whale Event Emission (Priority: P1)

As a trader using N8N, I want to receive **whale movement events**, so I can route them to Telegram/Discord.

**Why this priority**: Whale movements are time-sensitive. Most requested alert type. ~40 LOC.

**Independent Test**: Can be fully tested by:
1. Simulating whale flow detection (>100 BTC)
2. Capturing emitted webhook payload
3. Verifying JSON structure matches contract

**Acceptance Scenarios**:

1. **Given** whale_flow_detector detects 500 BTC exchange inflow
   **When** alert system processes event
   **Then** emits JSON: `{"event_type": "whale", "payload": {"amount_btc": 500, "direction": "INFLOW", "signal_vote": -0.7}}`

2. **Given** whale movement below configured threshold
   **When** alert system evaluates event
   **Then** no webhook fired (filtered at source)

---

### User Story 3 - Signal Event Emission (Priority: P1)

As a trader using N8N, I want to receive **high-confidence signal events**, so I can act on strong opportunities.

**Why this priority**: Fusion signals integrate all metrics - highest quality alerts. ~40 LOC.

**Independent Test**: Can be fully tested by:
1. Simulating fusion result with confidence > 0.7
2. Capturing emitted webhook payload
3. Verifying all signal components included

**Acceptance Scenarios**:

1. **Given** enhanced fusion returns BUY with 0.85 confidence
   **When** alert system processes result
   **Then** emits JSON with action, confidence, and top 3 contributing components

2. **Given** HOLD signal with any confidence
   **When** alert system processes result
   **Then** no webhook fired (HOLD not actionable)

3. **Given** signal confidence below threshold (0.7)
   **When** alert system evaluates
   **Then** no webhook fired

---

### User Story 4 - Regime Event Emission (Priority: P2)

As a market analyst using N8N, I want to receive **regime change events**, so I can adjust strategy.

**Why this priority**: Regime changes are less frequent but significant. ~30 LOC.

**Independent Test**: Can be fully tested by:
1. Simulating power law regime change
2. Capturing emitted webhook payload
3. Verifying old/new regime included

**Acceptance Scenarios**:

1. **Given** power_law regime changes from NEUTRAL to ACCUMULATION
   **When** alert system detects change
   **Then** emits JSON: `{"event_type": "regime", "payload": {"metric": "power_law", "from": "NEUTRAL", "to": "ACCUMULATION"}}`

2. **Given** Wasserstein detects distribution shift (W > 0.15)
   **When** alert system processes detection
   **Then** emits regime event with wasserstein details

---

### User Story 5 - Price Divergence Event (Priority: P2)

As a trader using N8N, I want to receive **price divergence events**, so I know when UTXOracle differs from exchanges.

**Why this priority**: Useful for arbitrage and confidence validation. ~30 LOC.

**Acceptance Scenarios**:

1. **Given** UTXOracle price is $100,000 and exchange is $97,000 (3% diff)
   **When** divergence exceeds threshold
   **Then** emits JSON: `{"event_type": "price", "payload": {"utxoracle_price": 100000, "exchange_price": 97000, "divergence_pct": 3.09}}`

---

### Edge Cases

- **What happens when webhook endpoint is unreachable?**
  → Retry 3 times with exponential backoff (1s, 2s, 4s), then log and continue.

- **What happens when N8N is down?**
  → Events logged to DuckDB `alert_events` table for manual replay.

- **What happens when too many events fire simultaneously?**
  → Basic rate limiting: max 60 events/minute to webhook. Queue excess.

- **What happens when webhook returns non-2xx?**
  → Treat as failure, trigger retry logic.

---

## Requirements *(mandatory)*

### Functional Requirements

**Webhook Core**:
- **FR-001**: System MUST support configurable webhook URL via environment variable
- **FR-002**: System MUST support optional HMAC-SHA256 request signing
- **FR-003**: System MUST emit events as JSON with consistent schema
- **FR-004**: System MUST include event metadata (id, timestamp, type, severity)

**Event Types**:
- **FR-005**: Whale events MUST include: amount_btc, direction, exchange (if known), signal_vote
- **FR-006**: Signal events MUST include: action, confidence, signal_mean, top_contributors
- **FR-007**: Regime events MUST include: metric, from_state, to_state, implication
- **FR-008**: Price events MUST include: utxoracle_price, exchange_price, divergence_pct

**Filtering**:
- **FR-009**: System MUST support minimum severity filter (critical, high, medium, low)
- **FR-010**: System MUST support per-event-type enable/disable via config
- **FR-011**: Default thresholds: whale_min=100 BTC, signal_min_confidence=0.7, price_divergence_min=3%

**Reliability**:
- **FR-012**: Failed webhook calls MUST retry with exponential backoff (max 3 attempts)
- **FR-013**: All events MUST be logged to DuckDB for audit/replay
- **FR-014**: System MUST continue operating if webhook is unavailable

**Integration**:
- **FR-015**: Alert system MUST hook into daily_analysis.py signal pipeline
- **FR-016**: Alert system MUST hook into whale_flow_detector.py (when available)

### Non-Functional Requirements

- **NFR-001**: Event emission latency <100ms (excluding network)
- **NFR-002**: Webhook timeout: 5 seconds per request
- **NFR-003**: Rate limit: max 60 events/minute to single webhook
- **NFR-004**: Zero external dependencies (use httpx already in project)

### Key Entities *(mandatory)*

```python
@dataclass
class AlertEvent:
    event_id: str                     # UUID
    event_type: str                   # "whale" | "signal" | "regime" | "price"
    timestamp: datetime               # When event occurred
    severity: str                     # "critical" | "high" | "medium" | "low"
    payload: dict                     # Event-specific data (see contracts)

    def to_webhook_payload(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity,
            "payload": self.payload
        }

@dataclass
class WebhookConfig:
    url: str                          # Webhook endpoint URL
    secret: str | None                # HMAC signing secret (optional)
    timeout_seconds: float = 5.0      # Request timeout
    max_retries: int = 3              # Retry attempts
    enabled_events: list[str] = None  # None = all events
    min_severity: str = "medium"      # Minimum severity to emit

@dataclass
class WebhookDelivery:
    delivery_id: str                  # UUID
    event_id: str                     # Reference to AlertEvent
    webhook_url: str                  # Target URL
    status: str                       # "pending" | "sent" | "failed"
    attempt_count: int                # Number of attempts
    response_code: int | None         # HTTP response code
    error_message: str | None         # If failed, why
    sent_at: datetime | None          # When successfully sent
```

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Event emission latency p95 < 50ms (excluding network)
- **SC-002**: 99% of events successfully delivered to reachable webhooks (with retries)
- **SC-003**: Zero events lost (all logged to DuckDB regardless of webhook status)
- **SC-004**: Webhook payload matches JSON schema contract
- **SC-005**: Code coverage for alert module ≥85%

### Definition of Done

- [ ] Webhook configuration via environment variables
- [ ] AlertEvent model with JSON serialization
- [ ] WebhookDispatcher with retry logic
- [ ] Whale event generation and emission
- [ ] Signal event generation and emission
- [ ] Regime event generation and emission
- [ ] Price divergence event generation
- [ ] Event logging to DuckDB
- [ ] HMAC request signing (optional)
- [ ] Integration with daily_analysis.py
- [ ] Unit tests (≥85% coverage)
- [ ] N8N workflow template provided
- [ ] Documentation for webhook setup

---

## Technical Notes

### Implementation Order (KISS)

1. **Models** (~30 LOC) - AlertEvent, WebhookConfig, WebhookDelivery
2. **Webhook Dispatcher** (~50 LOC) - HTTP POST, signing, retry
3. **Event Generators** (~60 LOC) - Whale, Signal, Regime, Price
4. **Integration** (~20 LOC) - Hook into daily_analysis.py
5. **Persistence** (~30 LOC) - Log events to DuckDB

### Files to Create

- `scripts/alerts/__init__.py` - Public API: emit_alert()
- `scripts/alerts/models.py` - AlertEvent, WebhookConfig, WebhookDelivery
- `scripts/alerts/dispatcher.py` - WebhookDispatcher class
- `scripts/alerts/generators.py` - Event factory functions
- `tests/test_alerts.py` - Test suite
- `examples/n8n/utxoracle-alerts.json` - N8N workflow template

### Files to Modify

- `scripts/daily_analysis.py` - Hook alert emission after fusion
- `.env.example` - Add ALERT_* variables

### Environment Configuration

```bash
# .env
ALERT_WEBHOOK_URL=http://localhost:5678/webhook/utxoracle-alerts
ALERT_WEBHOOK_SECRET=your-optional-hmac-secret
ALERT_ENABLED=true
ALERT_MIN_SEVERITY=medium
ALERT_WHALE_ENABLED=true
ALERT_SIGNAL_ENABLED=true
ALERT_REGIME_ENABLED=true
ALERT_PRICE_ENABLED=true
ALERT_WHALE_MIN_BTC=100
ALERT_SIGNAL_MIN_CONFIDENCE=0.7
ALERT_PRICE_MIN_DIVERGENCE=3.0
```

### Webhook Payload Contracts

```json
// Whale Event
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

// Signal Event
{
  "event_id": "...",
  "event_type": "signal",
  "timestamp": "...",
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

// Regime Event
{
  "event_id": "...",
  "event_type": "regime",
  "timestamp": "...",
  "severity": "medium",
  "payload": {
    "metric": "power_law",
    "from_state": "NEUTRAL",
    "to_state": "ACCUMULATION",
    "details": {"tau_old": 2.0, "tau_new": 1.6},
    "implication": "Whale concentration increasing"
  }
}

// Price Event
{
  "event_id": "...",
  "event_type": "price",
  "timestamp": "...",
  "severity": "low",
  "payload": {
    "utxoracle_price": 100000,
    "exchange_price": 97000,
    "divergence_pct": 3.09,
    "direction": "ABOVE"
  }
}
```

### DuckDB Schema

```sql
CREATE TABLE IF NOT EXISTS alert_events (
    event_id VARCHAR PRIMARY KEY,
    event_type VARCHAR NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    severity VARCHAR NOT NULL,
    payload JSON NOT NULL,
    webhook_status VARCHAR DEFAULT 'pending',
    webhook_attempts INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alert_type ON alert_events(event_type);
CREATE INDEX idx_alert_severity ON alert_events(severity);
CREATE INDEX idx_alert_timestamp ON alert_events(timestamp);
```

---

## Out of Scope

- Telegram/Discord/Slack direct integration (handled by N8N)
- User registration and preference management (handled by N8N)
- Rate limiting per user (handled by N8N)
- Message formatting per channel (handled by N8N)
- Bot commands (not applicable - webhook only)
- Multi-webhook fanout (single webhook, N8N handles distribution)

---

## N8N Integration

### Provided Template

An N8N workflow template will be provided at `examples/n8n/utxoracle-alerts.json` that:

1. Receives webhook from UTXOracle
2. Routes by event_type (Switch node)
3. Formats messages per channel (Function nodes)
4. Sends to Telegram, Discord, or Slack (configurable)

### User Customization

Users can modify the N8N workflow to:
- Add/remove notification channels
- Customize message templates per channel
- Add user-specific filtering logic
- Implement their own rate limiting
- Store alerts in their own database

---

## Future Extensions

- Multiple webhook endpoints (fanout)
- Webhook health monitoring
- Event replay API endpoint
- WebSocket push (alternative to polling)
- Prometheus metrics for alert volume
