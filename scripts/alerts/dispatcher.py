"""
Webhook Dispatcher for the Alert System.

Handles HTTP POST to webhooks with HMAC signing and retry logic.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from .models import AlertEvent, WebhookConfig, WebhookDelivery

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """
    Dispatches AlertEvents to configured webhook endpoints.

    Features:
    - HMAC-SHA256 request signing (when secret configured)
    - Retry with exponential backoff
    - Configurable timeout
    - Graceful skip when disabled
    """

    def __init__(self, config: WebhookConfig):
        """Initialize dispatcher with configuration."""
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _sign(self, payload: dict) -> str:
        """
        Generate HMAC-SHA256 signature for payload.

        Args:
            payload: The JSON payload to sign

        Returns:
            Signature string in format "sha256=<hex>"
        """
        if not self.config.secret:
            return ""

        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            self.config.secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        return f"sha256={signature}"

    async def dispatch(self, event: AlertEvent) -> WebhookDelivery | None:
        """
        Dispatch an alert event to the configured webhook.

        Args:
            event: The AlertEvent to send

        Returns:
            WebhookDelivery tracking object, or None if skipped
        """
        # Skip if disabled
        if not self.config.enabled:
            logger.debug(f"Webhook disabled, skipping event {event.event_id}")
            return None

        # Skip if no URL configured
        if not self.config.url:
            logger.warning(
                f"No webhook URL configured, skipping event {event.event_id}"
            )
            return None

        # Create delivery tracking object
        delivery = WebhookDelivery(
            delivery_id=str(uuid4()),
            event_id=event.event_id,
            webhook_url=self.config.url,
            status="pending",
            attempt_count=0,
        )

        # Prepare payload and headers
        payload = event.to_webhook_payload()
        headers = {"Content-Type": "application/json"}

        if self.config.secret:
            signature = self._sign(payload)
            headers["X-UTXOracle-Signature"] = signature

        # Retry loop with exponential backoff
        client = await self._get_client()
        last_error: Exception | None = None

        for attempt in range(self.config.max_retries):
            delivery.attempt_count = attempt + 1

            try:
                response = await client.post(
                    url=self.config.url,
                    json=payload,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                )

                delivery.response_code = response.status_code

                if response.is_success:
                    delivery.status = "sent"
                    delivery.sent_at = datetime.now(timezone.utc)
                    logger.info(
                        f"Event {event.event_id} delivered to {self.config.url} "
                        f"(attempt {attempt + 1}, status {response.status_code})"
                    )
                    return delivery

                # Non-success response, will retry
                logger.warning(
                    f"Webhook returned {response.status_code} for event {event.event_id}, "
                    f"attempt {attempt + 1}/{self.config.max_retries}"
                )

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Webhook request failed for event {event.event_id}: {e}, "
                    f"attempt {attempt + 1}/{self.config.max_retries}"
                )

            # Exponential backoff before retry (skip on last attempt)
            if attempt < self.config.max_retries - 1:
                backoff = 2**attempt  # 1s, 2s, 4s...
                await asyncio.sleep(backoff)

        # All retries exhausted
        delivery.status = "failed"
        if last_error:
            delivery.error_message = str(last_error)
        else:
            delivery.error_message = (
                f"HTTP {delivery.response_code} after {delivery.attempt_count} attempts"
            )

        logger.error(
            f"Event {event.event_id} delivery failed after {delivery.attempt_count} attempts: "
            f"{delivery.error_message}"
        )

        return delivery
