"""
Webhook Alert System for UTXOracle.

Emits structured JSON events to configurable webhook endpoints.
Supports whale movements, regime changes, high-confidence signals,
and price divergence alerts.

Public API:
    - emit_alert(event): Async emit to webhook
    - emit_alert_sync(event): Sync emit to webhook
    - get_config(): Get current WebhookConfig
    - create_whale_event(): Factory for whale events
    - create_signal_event(): Factory for signal events
    - create_regime_event(): Factory for regime events
    - create_price_event(): Factory for price events
    - save_event(): Persist event to DuckDB
    - get_failed_events(): Get events for replay
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from .models import AlertEvent

# Module logger
logger = logging.getLogger(__name__)

# Default database path (same as daily_analysis.py)
DEFAULT_DB_PATH = "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"

# Public API stubs - implemented in submodules
__all__ = [
    # Config
    "get_config",
    # Dispatcher
    "emit_alert",
    "emit_alert_sync",
    # Models
    "AlertEvent",
    "WebhookConfig",
    "WebhookDelivery",
    # Generators
    "create_whale_event",
    "create_signal_event",
    "create_regime_event",
    "create_price_event",
    # Persistence
    "save_event",
    "update_webhook_status",
    "get_failed_events",
]


def get_config():
    """Get current webhook configuration from environment."""
    from .models import WebhookConfig

    return WebhookConfig.from_env()


async def emit_alert(event, db_path: str | None = None):
    """
    Emit alert event to configured webhook (async).

    This function:
    1. Saves the event to DuckDB for audit
    2. Dispatches to the webhook
    3. Updates the webhook status in DuckDB

    Args:
        event: AlertEvent to emit
        db_path: Optional custom database path (for testing)

    Returns:
        WebhookDelivery object or None if skipped
    """
    from .dispatcher import WebhookDispatcher
    from .models import WebhookConfig

    # Get configuration
    config = WebhookConfig.from_env()

    # Save event to database first (audit trail)
    try:
        if db_path:
            save_event(event, db_path=db_path)
        else:
            save_event(event)
    except Exception as e:
        logger.error(f"Failed to save event {event.event_id}: {e}")
        # Continue anyway - webhook delivery is more important

    # Dispatch to webhook
    dispatcher = WebhookDispatcher(config)
    try:
        delivery = await dispatcher.dispatch(event)

        # Update status in database
        if delivery:
            try:
                if db_path:
                    update_webhook_status(
                        event.event_id,
                        status=delivery.status,
                        response_code=delivery.response_code,
                        error=delivery.error_message,
                        db_path=db_path,
                    )
                else:
                    update_webhook_status(
                        event.event_id,
                        status=delivery.status,
                        response_code=delivery.response_code,
                        error=delivery.error_message,
                    )
            except Exception as e:
                logger.error(f"Failed to update status for event {event.event_id}: {e}")

        return delivery
    finally:
        await dispatcher.close()


def emit_alert_sync(event, db_path: str | None = None):
    """
    Emit alert event to configured webhook (sync wrapper).

    Convenience function for sync code that needs to emit alerts.

    Args:
        event: AlertEvent to emit
        db_path: Optional custom database path (for testing)

    Returns:
        WebhookDelivery object or None if skipped
    """
    return asyncio.run(emit_alert(event, db_path=db_path))


def save_event(event: "AlertEvent", db_path: str = DEFAULT_DB_PATH) -> None:
    """
    Save event to DuckDB for audit/replay.

    Uses INSERT OR IGNORE to safely handle replays of failed events
    without causing duplicate key errors.

    Args:
        event: The AlertEvent to save
        db_path: Path to DuckDB database file
    """
    conn = duckdb.connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO alert_events (
                event_id, event_type, timestamp, severity, payload,
                webhook_status, webhook_attempts, created_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', 0, CURRENT_TIMESTAMP)
            """,
            [
                event.event_id,
                event.event_type,
                event.timestamp,
                event.severity,
                json.dumps(event.payload),
            ],
        )
        logger.debug(f"Saved event {event.event_id} to database")
    finally:
        conn.close()


def update_webhook_status(
    event_id: str,
    status: str,
    response_code: int | None = None,
    error: str | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """
    Update webhook delivery status for an event.

    Args:
        event_id: The event ID to update
        status: New status ("pending", "sent", "failed")
        response_code: HTTP response code (optional)
        error: Error message (optional)
        db_path: Path to DuckDB database file
    """
    conn = duckdb.connect(db_path)
    try:
        sent_at = datetime.now(timezone.utc) if status == "sent" else None

        conn.execute(
            """
            UPDATE alert_events
            SET webhook_status = ?,
                webhook_response_code = ?,
                webhook_error = ?,
                webhook_attempts = webhook_attempts + 1,
                sent_at = ?
            WHERE event_id = ?
            """,
            [status, response_code, error, sent_at, event_id],
        )
        logger.debug(f"Updated event {event_id} status to {status}")
    finally:
        conn.close()


def get_failed_events(
    limit: int = 100, db_path: str = DEFAULT_DB_PATH
) -> list["AlertEvent"]:
    """
    Get failed events for replay.

    Args:
        limit: Maximum number of events to return
        db_path: Path to DuckDB database file

    Returns:
        List of AlertEvent objects with failed webhook status
    """
    from .models import AlertEvent

    conn = duckdb.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT event_id, event_type, timestamp, severity, payload
            FROM alert_events
            WHERE webhook_status = 'failed'
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()

        events = []
        for row in rows:
            event = AlertEvent(
                event_id=row[0],
                event_type=row[1],
                timestamp=row[2].replace(tzinfo=timezone.utc)
                if row[2].tzinfo is None
                else row[2],
                severity=row[3],
                payload=json.loads(row[4]) if isinstance(row[4], str) else row[4],
            )
            events.append(event)

        return events
    finally:
        conn.close()


# Lazy imports to avoid circular dependencies
def __getattr__(name):
    if name in ("AlertEvent", "WebhookConfig", "WebhookDelivery"):
        from .models import AlertEvent, WebhookConfig, WebhookDelivery

        return {
            "AlertEvent": AlertEvent,
            "WebhookConfig": WebhookConfig,
            "WebhookDelivery": WebhookDelivery,
        }[name]
    if name in (
        "create_whale_event",
        "create_signal_event",
        "create_regime_event",
        "create_price_event",
    ):
        from . import generators

        return getattr(generators, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
