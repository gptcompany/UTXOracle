"""
Data models for the Webhook Alert System.

AlertEvent: Core event structure emitted to webhooks.
WebhookConfig: Configuration loaded from environment variables.
WebhookDelivery: Tracks delivery status for audit/replay.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AlertEvent:
    """Core event structure emitted to webhooks."""

    event_id: str
    event_type: str  # "whale" | "signal" | "regime" | "price"
    timestamp: datetime
    severity: str  # "critical" | "high" | "medium" | "low"
    payload: dict[str, Any]

    def to_webhook_payload(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict for webhook POST."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity,
            "payload": self.payload,
        }


@dataclass
class WebhookConfig:
    """Configuration loaded from environment variables."""

    url: str
    secret: str | None = None
    timeout_seconds: float = 5.0
    max_retries: int = 3
    enabled: bool = True
    min_severity: str = "medium"

    # Per-event-type toggles
    whale_enabled: bool = True
    signal_enabled: bool = True
    regime_enabled: bool = True
    price_enabled: bool = True

    # Thresholds
    whale_min_btc: float = 100.0
    signal_min_confidence: float = 0.7
    price_min_divergence: float = 3.0

    @classmethod
    def from_env(cls) -> "WebhookConfig":
        """Load configuration from environment variables."""
        return cls(
            url=os.getenv("ALERT_WEBHOOK_URL", ""),
            secret=os.getenv("ALERT_WEBHOOK_SECRET"),
            timeout_seconds=float(os.getenv("ALERT_TIMEOUT_SECONDS", "5.0")),
            max_retries=int(os.getenv("ALERT_MAX_RETRIES", "3")),
            enabled=os.getenv("ALERT_ENABLED", "true").lower() == "true",
            min_severity=os.getenv("ALERT_MIN_SEVERITY", "medium"),
            whale_enabled=os.getenv("ALERT_WHALE_ENABLED", "true").lower() == "true",
            signal_enabled=os.getenv("ALERT_SIGNAL_ENABLED", "true").lower() == "true",
            regime_enabled=os.getenv("ALERT_REGIME_ENABLED", "true").lower() == "true",
            price_enabled=os.getenv("ALERT_PRICE_ENABLED", "true").lower() == "true",
            whale_min_btc=float(os.getenv("ALERT_WHALE_MIN_BTC", "100")),
            signal_min_confidence=float(
                os.getenv("ALERT_SIGNAL_MIN_CONFIDENCE", "0.7")
            ),
            price_min_divergence=float(os.getenv("ALERT_PRICE_MIN_DIVERGENCE", "3.0")),
        )


@dataclass
class WebhookDelivery:
    """Tracks delivery status for audit/replay."""

    delivery_id: str
    event_id: str
    webhook_url: str
    status: str = "pending"  # "pending" | "sent" | "failed"
    attempt_count: int = 0
    response_code: int | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: datetime | None = None
