# Research: Webhook Alert System

**Feature**: spec-011 | **Date**: 2025-12-04 | **Status**: Complete

## Research Question

Should UTXOracle implement direct Telegram/Discord integration or use a webhook-first architecture?

## Options Analyzed

### Option A: Telegram Bot (Original spec-011 v1)

**Approach**: Use `python-telegram-bot` library to build a full Telegram bot with user registration, commands, and direct message delivery.

**Pros**:
- Direct control over user experience
- No external dependencies beyond Telegram

**Cons**:
- +1 new dependency (python-telegram-bot)
- ~600 LOC to implement
- Single channel (Telegram only)
- User registration/preferences in DuckDB
- Rate limiting implementation required
- Retry logic implementation required
- API changes require code updates

### Option B: Webhook + N8N (Selected)

**Approach**: Emit structured JSON events to a configurable webhook URL. External workflow tools (N8N, Zapier, Make) handle delivery to any channel.

**Pros**:
- Zero new dependencies (httpx already present)
- ~150 LOC to implement
- Unlimited channels (N8N handles routing)
- User preferences in N8N workflow (visual config)
- Rate limiting built into N8N
- Retry logic built into N8N
- JSON contract is stable, channels can change freely

**Cons**:
- Requires N8N/Zapier infrastructure (user already has N8N)
- Less direct control over end-user experience

## Decision Matrix

| Criteria | Weight | Telegram Bot | Webhook + N8N |
|----------|--------|--------------|---------------|
| KISS compliance | 30% | 2/5 | 5/5 |
| YAGNI compliance | 25% | 2/5 | 5/5 |
| Code reuse | 20% | 1/5 | 5/5 |
| Flexibility | 15% | 2/5 | 5/5 |
| Maintenance | 10% | 2/5 | 5/5 |
| **Weighted Score** | | **1.95** | **5.00** |

## KISS/YAGNI Analysis

### Current Infrastructure (User Has)

- ✅ N8N workflow automation (deployed)
- ✅ Bitcoin Core node
- ✅ DuckDB database
- ✅ httpx HTTP client (in project)

### What Telegram Bot Would Add

- ❌ python-telegram-bot dependency
- ❌ User registration system
- ❌ Preference storage in DuckDB
- ❌ Bot command handlers
- ❌ Message formatting per channel
- ❌ Rate limiting implementation
- ❌ Retry queue implementation

### What Webhook Approach Reuses

- ✅ N8N for channel routing (already deployed)
- ✅ N8N for rate limiting (built-in)
- ✅ N8N for retry logic (built-in)
- ✅ N8N for user preferences (workflow config)
- ✅ httpx for HTTP requests (already in project)

## Code Comparison

### Telegram Bot Approach (~600 LOC)

```python
# telegram_bot.py (~200 LOC)
from telegram import Update
from telegram.ext import Application, CommandHandler

async def start(update: Update, context):
    # Register user, save preferences, send welcome...

async def config(update: Update, context):
    # Parse args, validate, update DB...

# alert_dispatcher.py (~150 LOC)
class TelegramDispatcher:
    async def send_alert(self, chat_id, message):
        # Format message, handle rate limits, retry...

# models.py (~100 LOC)
# TelegramUser, AlertPreferences, AlertQueue...

# rate_limiter.py (~80 LOC)
# Token bucket, per-user tracking...

# retry_queue.py (~70 LOC)
# Exponential backoff, dead letter queue...
```

### Webhook Approach (~150 LOC)

```python
# dispatcher.py (~50 LOC)
class WebhookDispatcher:
    async def emit(self, event: AlertEvent):
        payload = event.to_webhook_payload()
        signature = self._sign(payload) if self.secret else None

        for attempt in range(self.max_retries):
            try:
                response = await self.client.post(
                    self.url,
                    json=payload,
                    headers={"X-UTXOracle-Signature": signature},
                    timeout=self.timeout
                )
                if response.is_success:
                    return True
            except Exception:
                await asyncio.sleep(2 ** attempt)
        return False

# models.py (~30 LOC)
@dataclass
class AlertEvent:
    event_id: str
    event_type: str
    timestamp: datetime
    severity: str
    payload: dict

# generators.py (~60 LOC)
def create_whale_event(amount_btc, direction, signal_vote) -> AlertEvent:
    return AlertEvent(
        event_id=str(uuid4()),
        event_type="whale",
        timestamp=datetime.utcnow(),
        severity="high" if amount_btc > 500 else "medium",
        payload={"amount_btc": amount_btc, "direction": direction, ...}
    )
```

## Conclusion

**Decision**: Webhook-first architecture (Option B)

**Rationale**:
1. **75% code reduction** (150 LOC vs 600 LOC)
2. **Zero new dependencies** (Constitution Principle I)
3. **Reuses existing infrastructure** (N8N already deployed)
4. **Unlimited flexibility** (any channel N8N supports)
5. **Lower maintenance** (JSON contract is stable)

**Trade-off accepted**: Requires N8N/Zapier infrastructure. User already has N8N deployed, so this is not a blocker.

## References

- N8N Webhook documentation: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/
- HMAC signing best practices: https://webhooks.fyi/security/hmac
