"""
Webhook Notification System - Tasks T056-T060
Comprehensive webhook system with signing, retry logic, and delivery tracking

Features:
- T056: Base webhook notification system
- T057: URL configuration and management
- T058: HMAC-SHA256 payload signing
- T059: Retry logic with exponential backoff
- T060: Delivery status tracking and logging
- KISS principle: Async HTTP client, no external queue dependencies

Usage:
    from api.webhook_system import WebhookManager, WebhookConfig

    # Configure webhooks
    config = WebhookConfig(
        urls=["https://example.com/webhook"],
        secret="my-secret-key",
        max_retries=3
    )

    # Create manager
    manager = WebhookManager(config)

    # Send notification
    await manager.send_notification({
        "event": "whale_detected",
        "amount": 150.5,
        "urgency": "high"
    })

    # Get delivery stats
    stats = manager.get_stats()
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Deque
from collections import deque
from enum import Enum
from threading import Lock

import aiohttp

logger = logging.getLogger(__name__)


class DeliveryStatus(Enum):
    """Webhook delivery status"""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class WebhookDelivery:
    """Record of a webhook delivery attempt"""

    delivery_id: str
    url: str
    payload: dict
    status: DeliveryStatus
    timestamp: float
    attempts: int = 0
    last_attempt: Optional[float] = None
    last_error: Optional[str] = None
    response_code: Optional[int] = None
    response_time_ms: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class WebhookConfig:
    """
    Webhook configuration - T057

    Attributes:
        urls: List of webhook URLs to send notifications to
        secret: Secret key for HMAC-SHA256 signing (T058)
        enabled: Whether webhooks are enabled globally
        max_retries: Maximum retry attempts (T059)
        retry_delay_seconds: Initial retry delay, doubles each attempt (T059)
        timeout_seconds: HTTP request timeout
        max_history: Maximum delivery records to keep (T060)
    """

    urls: List[str] = field(default_factory=list)
    secret: str = ""
    enabled: bool = False
    max_retries: int = 3
    retry_delay_seconds: float = 5.0
    timeout_seconds: float = 10.0
    max_history: int = 1000

    def validate(self) -> List[str]:
        """Validate configuration and return list of errors"""
        errors = []

        if self.enabled:
            if not self.urls:
                errors.append("No webhook URLs configured")

            for url in self.urls:
                if not url.startswith(("http://", "https://")):
                    errors.append(
                        f"Invalid URL: {url} (must start with http:// or https://)"
                    )

            if not self.secret:
                errors.append(
                    "No webhook secret configured (required for payload signing)"
                )

        if self.max_retries < 0:
            errors.append("max_retries must be >= 0")

        if self.retry_delay_seconds <= 0:
            errors.append("retry_delay_seconds must be > 0")

        if self.timeout_seconds <= 0:
            errors.append("timeout_seconds must be > 0")

        return errors


class WebhookManager:
    """
    Manages webhook notifications with signing, retries, and tracking

    Implements:
    - T056: Base notification system
    - T057: URL configuration management
    - T058: HMAC-SHA256 payload signing
    - T059: Exponential backoff retry logic
    - T060: Delivery status tracking

    Example:
        config = WebhookConfig(
            urls=["https://example.com/webhook"],
            secret="secret-key",
            enabled=True
        )

        manager = WebhookManager(config)

        await manager.send_notification({
            "event": "whale_detected",
            "data": {"amount": 150.5}
        })
    """

    def __init__(self, config: WebhookConfig):
        """
        Initialize webhook manager

        Args:
            config: Webhook configuration
        """
        self.config = config
        self.lock = Lock()

        # T060: Delivery tracking
        self.deliveries: Deque[WebhookDelivery] = deque(maxlen=config.max_history)
        self.pending_retries: List[WebhookDelivery] = []

        # Statistics
        self.total_sent = 0
        self.total_failed = 0
        self.total_retries = 0

        # Validate config
        errors = config.validate()
        if errors and config.enabled:
            logger.error(f"Webhook configuration errors: {errors}")
            raise ValueError(f"Invalid webhook configuration: {errors}")

        if config.enabled:
            logger.info(
                f"Webhook manager initialized: {len(config.urls)} URLs, "
                f"max_retries={config.max_retries}, secret={'configured' if config.secret else 'missing'}"
            )
        else:
            logger.info("Webhook manager initialized (disabled)")

    def _sign_payload(self, payload: dict) -> str:
        """
        T058: Generate HMAC-SHA256 signature for payload

        Args:
            payload: Payload to sign

        Returns:
            str: Hex-encoded HMAC signature
        """
        payload_json = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            self.config.secret.encode("utf-8"),
            payload_json.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    async def _send_webhook(
        self, url: str, payload: dict, delivery_id: str, attempt: int = 0
    ) -> WebhookDelivery:
        """
        Send webhook to a single URL with signing

        Args:
            url: Webhook URL
            payload: Payload dictionary
            delivery_id: Unique delivery ID
            attempt: Attempt number (0-indexed)

        Returns:
            WebhookDelivery: Delivery record
        """
        delivery = WebhookDelivery(
            delivery_id=delivery_id,
            url=url,
            payload=payload,
            status=DeliveryStatus.PENDING,
            timestamp=time.time(),
            attempts=attempt + 1,
        )

        try:
            # T058: Sign payload
            signature = self._sign_payload(payload)

            # Add metadata
            enriched_payload = {
                **payload,
                "_metadata": {
                    "delivery_id": delivery_id,
                    "timestamp": time.time(),
                    "attempt": attempt + 1,
                },
            }

            # Prepare headers with signature
            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature,
                "X-Webhook-Delivery-ID": delivery_id,
                "User-Agent": "UTXOracle-Webhook/1.0",
            }

            # Send HTTP POST
            start_time = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=enriched_payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
                ) as response:
                    response_time_ms = (time.time() - start_time) * 1000

                    delivery.last_attempt = time.time()
                    delivery.response_code = response.status
                    delivery.response_time_ms = round(response_time_ms, 2)

                    if 200 <= response.status < 300:
                        delivery.status = DeliveryStatus.SENT
                        logger.info(
                            f"Webhook delivered: {url} [{response.status}] "
                            f"({response_time_ms:.1f}ms) attempt={attempt + 1}"
                        )
                    else:
                        delivery.status = DeliveryStatus.FAILED
                        delivery.last_error = f"HTTP {response.status}"
                        logger.warning(
                            f"Webhook failed: {url} [{response.status}] "
                            f"attempt={attempt + 1}"
                        )

        except asyncio.TimeoutError:
            delivery.status = DeliveryStatus.FAILED
            delivery.last_error = f"Timeout after {self.config.timeout_seconds}s"
            delivery.last_attempt = time.time()
            logger.warning(f"Webhook timeout: {url} attempt={attempt + 1}")

        except Exception as e:
            delivery.status = DeliveryStatus.FAILED
            delivery.last_error = str(e)
            delivery.last_attempt = time.time()
            logger.error(f"Webhook error: {url} - {e} attempt={attempt + 1}")

        return delivery

    async def _retry_with_backoff(
        self, url: str, payload: dict, delivery_id: str, initial_attempt: int = 0
    ) -> WebhookDelivery:
        """
        T059: Retry webhook delivery with exponential backoff

        Args:
            url: Webhook URL
            payload: Payload dictionary
            delivery_id: Unique delivery ID
            initial_attempt: Starting attempt number

        Returns:
            WebhookDelivery: Final delivery record
        """
        delivery = None

        for attempt in range(initial_attempt, self.config.max_retries + 1):
            delivery = await self._send_webhook(url, payload, delivery_id, attempt)

            if delivery.status == DeliveryStatus.SENT:
                break

            if attempt < self.config.max_retries:
                # Calculate backoff delay (exponential)
                delay = self.config.retry_delay_seconds * (2**attempt)
                logger.info(
                    f"Retrying webhook in {delay}s: {url} "
                    f"(attempt {attempt + 1}/{self.config.max_retries})"
                )
                delivery.status = DeliveryStatus.RETRYING
                await asyncio.sleep(delay)
                self.total_retries += 1

        return delivery

    async def send_notification(
        self, payload: dict, event_type: Optional[str] = None
    ) -> List[WebhookDelivery]:
        """
        T056: Send webhook notification to all configured URLs

        Args:
            payload: Notification payload
            event_type: Optional event type to include in payload

        Returns:
            List[WebhookDelivery]: Delivery records for all URLs
        """
        if not self.config.enabled:
            logger.debug("Webhooks disabled, skipping notification")
            return []

        if not self.config.urls:
            logger.warning("No webhook URLs configured")
            return []

        # Add event type if provided
        if event_type:
            payload = {**payload, "event": event_type}

        # Generate delivery ID
        delivery_id = f"wh_{int(time.time() * 1000)}_{id(payload)}"

        logger.info(
            f"Sending webhook notification: delivery_id={delivery_id} urls={len(self.config.urls)}"
        )

        # Send to all URLs concurrently
        tasks = [
            self._retry_with_backoff(url, payload, f"{delivery_id}_{i}")
            for i, url in enumerate(self.config.urls)
        ]

        deliveries = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and track results
        valid_deliveries = []
        with self.lock:
            for delivery in deliveries:
                if isinstance(delivery, Exception):
                    logger.error(f"Webhook task failed: {delivery}")
                    continue

                valid_deliveries.append(delivery)
                self.deliveries.append(delivery)

                if delivery.status == DeliveryStatus.SENT:
                    self.total_sent += 1
                else:
                    self.total_failed += 1

        return valid_deliveries

    def get_delivery_history(self, limit: Optional[int] = None) -> List[Dict]:
        """
        T060: Get webhook delivery history

        Args:
            limit: Maximum number of records to return (default: all)

        Returns:
            List[Dict]: List of delivery records
        """
        with self.lock:
            records = list(self.deliveries)

        if limit:
            records = records[-limit:]

        return [d.to_dict() for d in records]

    def get_stats(self) -> dict:
        """
        T060: Get webhook delivery statistics

        Returns:
            dict: Statistics including total sent, failed, success rate
        """
        with self.lock:
            total_attempts = self.total_sent + self.total_failed
            success_rate = (
                (self.total_sent / total_attempts * 100) if total_attempts > 0 else 0.0
            )

            # Count deliveries by status
            status_counts = {}
            for delivery in self.deliveries:
                status = delivery.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

            # Calculate average response time
            response_times = [
                d.response_time_ms
                for d in self.deliveries
                if d.response_time_ms is not None
            ]
            avg_response_time = (
                sum(response_times) / len(response_times) if response_times else 0.0
            )

            return {
                "enabled": self.config.enabled,
                "configured_urls": len(self.config.urls),
                "total_sent": self.total_sent,
                "total_failed": self.total_failed,
                "total_retries": self.total_retries,
                "success_rate_percent": round(success_rate, 2),
                "avg_response_time_ms": round(avg_response_time, 2),
                "status_counts": status_counts,
                "recent_deliveries": len(self.deliveries),
            }

    def update_config(self, new_config: WebhookConfig):
        """
        T057: Update webhook configuration

        Args:
            new_config: New configuration
        """
        errors = new_config.validate()
        if errors and new_config.enabled:
            raise ValueError(f"Invalid webhook configuration: {errors}")

        with self.lock:
            self.config = new_config

        logger.info(
            f"Webhook configuration updated: enabled={new_config.enabled}, urls={len(new_config.urls)}"
        )


# Global webhook manager instance (optional - can be created per-app)
_global_manager = None


def get_global_manager() -> Optional[WebhookManager]:
    """Get global webhook manager instance"""
    return _global_manager


def initialize_global_manager(config: WebhookConfig):
    """Initialize global webhook manager"""
    global _global_manager
    _global_manager = WebhookManager(config)
    return _global_manager


# Example usage
if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI

    # Configure webhooks
    config = WebhookConfig(
        urls=["http://localhost:9000/webhook"],  # Test endpoint
        secret="test-secret-key-12345",
        enabled=True,
        max_retries=2,
        retry_delay_seconds=2.0,
    )

    # Create manager
    manager = WebhookManager(config)

    # Create test FastAPI app
    app = FastAPI()

    @app.post("/send-test-webhook")
    async def send_test():
        """Send a test webhook"""
        deliveries = await manager.send_notification(
            {"event": "test", "message": "This is a test webhook", "value": 123.45},
            event_type="test_event",
        )

        return {
            "sent": len(deliveries),
            "deliveries": [d.to_dict() for d in deliveries],
        }

    @app.get("/webhook-stats")
    async def webhook_stats():
        """Get webhook statistics"""
        return manager.get_stats()

    @app.get("/webhook-history")
    async def webhook_history(limit: int = 10):
        """Get webhook delivery history"""
        return {"deliveries": manager.get_delivery_history(limit=limit)}

    print("Starting test webhook server on http://localhost:8081")
    print("\nEndpoints:")
    print("  POST /send-test-webhook  - Send a test webhook")
    print("  GET  /webhook-stats      - View statistics")
    print("  GET  /webhook-history    - View delivery history")
    print(
        "\nNote: Configure a webhook receiver at http://localhost:9000/webhook to receive notifications"
    )

    uvicorn.run(app, host="127.0.0.1", port=8081)
