"""
Tests for Webhook Alert System (spec-011).

TDD approach: RED tests written first, then GREEN implementation.
"""

import os
from datetime import datetime, timezone
from unittest.mock import patch


# =============================================================================
# Phase 2: Data Models Tests (T004-T006)
# =============================================================================


class TestAlertEventSerialization:
    """T004: Test AlertEvent JSON serialization."""

    def test_alert_event_to_webhook_payload(self):
        """AlertEvent.to_webhook_payload() returns valid JSON dict."""
        from scripts.alerts.models import AlertEvent

        event = AlertEvent(
            event_id="test-uuid-1234",
            event_type="whale",
            timestamp=datetime(2025, 12, 4, 15, 30, 0, tzinfo=timezone.utc),
            severity="high",
            payload={"amount_btc": 500.0, "direction": "INFLOW"},
        )

        result = event.to_webhook_payload()

        assert result["event_id"] == "test-uuid-1234"
        assert result["event_type"] == "whale"
        assert result["timestamp"] == "2025-12-04T15:30:00+00:00"
        assert result["severity"] == "high"
        assert result["payload"]["amount_btc"] == 500.0
        assert result["payload"]["direction"] == "INFLOW"

    def test_alert_event_payload_is_json_serializable(self):
        """Webhook payload can be serialized to JSON."""
        import json
        from scripts.alerts.models import AlertEvent

        event = AlertEvent(
            event_id="test-uuid-1234",
            event_type="signal",
            timestamp=datetime(2025, 12, 4, 15, 30, 0, tzinfo=timezone.utc),
            severity="medium",
            payload={"action": "BUY", "confidence": 0.85},
        )

        payload = event.to_webhook_payload()
        json_str = json.dumps(payload)

        assert '"event_id": "test-uuid-1234"' in json_str
        assert '"event_type": "signal"' in json_str


class TestWebhookConfigFromEnv:
    """T005: Test WebhookConfig.from_env() loads from environment."""

    def test_webhook_config_from_env_basic(self):
        """WebhookConfig.from_env() loads URL and enabled flag."""
        from scripts.alerts.models import WebhookConfig

        env = {
            "ALERT_WEBHOOK_URL": "http://localhost:5678/webhook/test",
            "ALERT_ENABLED": "true",
        }

        with patch.dict(os.environ, env, clear=False):
            config = WebhookConfig.from_env()

        assert config.url == "http://localhost:5678/webhook/test"
        assert config.enabled is True

    def test_webhook_config_from_env_with_secret(self):
        """WebhookConfig.from_env() loads optional HMAC secret."""
        from scripts.alerts.models import WebhookConfig

        env = {
            "ALERT_WEBHOOK_URL": "http://localhost:5678/webhook/test",
            "ALERT_WEBHOOK_SECRET": "my-secret-key",
        }

        with patch.dict(os.environ, env, clear=False):
            config = WebhookConfig.from_env()

        assert config.secret == "my-secret-key"

    def test_webhook_config_from_env_thresholds(self):
        """WebhookConfig.from_env() loads threshold values."""
        from scripts.alerts.models import WebhookConfig

        env = {
            "ALERT_WEBHOOK_URL": "http://localhost:5678/webhook/test",
            "ALERT_WHALE_MIN_BTC": "200",
            "ALERT_SIGNAL_MIN_CONFIDENCE": "0.8",
            "ALERT_PRICE_MIN_DIVERGENCE": "5.0",
        }

        with patch.dict(os.environ, env, clear=False):
            config = WebhookConfig.from_env()

        assert config.whale_min_btc == 200.0
        assert config.signal_min_confidence == 0.8
        assert config.price_min_divergence == 5.0

    def test_webhook_config_from_env_event_toggles(self):
        """WebhookConfig.from_env() loads per-event-type toggles."""
        from scripts.alerts.models import WebhookConfig

        env = {
            "ALERT_WEBHOOK_URL": "http://localhost:5678/webhook/test",
            "ALERT_WHALE_ENABLED": "false",
            "ALERT_SIGNAL_ENABLED": "true",
            "ALERT_REGIME_ENABLED": "false",
            "ALERT_PRICE_ENABLED": "true",
        }

        with patch.dict(os.environ, env, clear=False):
            config = WebhookConfig.from_env()

        assert config.whale_enabled is False
        assert config.signal_enabled is True
        assert config.regime_enabled is False
        assert config.price_enabled is True

    def test_webhook_config_from_env_defaults(self):
        """WebhookConfig.from_env() uses sensible defaults."""
        from scripts.alerts.models import WebhookConfig

        # Clear relevant env vars
        env = {"ALERT_WEBHOOK_URL": ""}
        with patch.dict(os.environ, env, clear=False):
            config = WebhookConfig.from_env()

        assert config.url == ""
        assert config.secret is None
        assert config.timeout_seconds == 5.0
        assert config.max_retries == 3
        assert config.enabled is True
        assert config.min_severity == "medium"
        assert config.whale_min_btc == 100.0
        assert config.signal_min_confidence == 0.7
        assert config.price_min_divergence == 3.0


class TestWebhookDeliveryStatusTransitions:
    """T006: Test WebhookDelivery status transitions."""

    def test_webhook_delivery_initial_state(self):
        """WebhookDelivery starts in pending status."""
        from scripts.alerts.models import WebhookDelivery

        delivery = WebhookDelivery(
            delivery_id="delivery-uuid-1234",
            event_id="event-uuid-1234",
            webhook_url="http://localhost:5678/webhook/test",
        )

        assert delivery.status == "pending"
        assert delivery.attempt_count == 0
        assert delivery.response_code is None
        assert delivery.error_message is None

    def test_webhook_delivery_success_transition(self):
        """WebhookDelivery can transition to sent status."""
        from scripts.alerts.models import WebhookDelivery
        from datetime import datetime, timezone

        delivery = WebhookDelivery(
            delivery_id="delivery-uuid-1234",
            event_id="event-uuid-1234",
            webhook_url="http://localhost:5678/webhook/test",
        )

        # Simulate successful delivery
        delivery.status = "sent"
        delivery.attempt_count = 1
        delivery.response_code = 200
        delivery.sent_at = datetime(2025, 12, 4, 15, 30, 0, tzinfo=timezone.utc)

        assert delivery.status == "sent"
        assert delivery.attempt_count == 1
        assert delivery.response_code == 200
        assert delivery.sent_at is not None

    def test_webhook_delivery_failure_transition(self):
        """WebhookDelivery can transition to failed status."""
        from scripts.alerts.models import WebhookDelivery

        delivery = WebhookDelivery(
            delivery_id="delivery-uuid-1234",
            event_id="event-uuid-1234",
            webhook_url="http://localhost:5678/webhook/test",
        )

        # Simulate failed delivery after retries
        delivery.status = "failed"
        delivery.attempt_count = 3
        delivery.error_message = "Connection timeout after 3 attempts"

        assert delivery.status == "failed"
        assert delivery.attempt_count == 3
        assert delivery.error_message == "Connection timeout after 3 attempts"


# =============================================================================
# Phase 3: Webhook Dispatcher Tests (T011-T015)
# =============================================================================


import pytest
from unittest.mock import AsyncMock, MagicMock


class TestWebhookDispatcher:
    """Tests for WebhookDispatcher HTTP POST functionality."""

    @pytest.fixture
    def sample_event(self):
        """Create a sample AlertEvent for tests."""
        from scripts.alerts.models import AlertEvent

        return AlertEvent(
            event_id="test-event-1234",
            event_type="whale",
            timestamp=datetime(2025, 12, 4, 15, 30, 0, tzinfo=timezone.utc),
            severity="high",
            payload={"amount_btc": 500.0, "direction": "INFLOW"},
        )

    @pytest.fixture
    def config(self):
        """Create a basic WebhookConfig for tests."""
        from scripts.alerts.models import WebhookConfig

        return WebhookConfig(
            url="http://localhost:5678/webhook/test",
            secret=None,
            timeout_seconds=5.0,
            max_retries=3,
            enabled=True,
        )

    @pytest.fixture
    def config_with_secret(self):
        """Create a WebhookConfig with HMAC secret."""
        from scripts.alerts.models import WebhookConfig

        return WebhookConfig(
            url="http://localhost:5678/webhook/test",
            secret="my-secret-key",
            timeout_seconds=5.0,
            max_retries=3,
            enabled=True,
        )

    @pytest.fixture
    def config_disabled(self):
        """Create a disabled WebhookConfig."""
        from scripts.alerts.models import WebhookConfig

        return WebhookConfig(
            url="http://localhost:5678/webhook/test",
            secret=None,
            timeout_seconds=5.0,
            max_retries=3,
            enabled=False,
        )

    @pytest.mark.asyncio
    async def test_dispatcher_posts_to_webhook(self, sample_event, config):
        """T011: Dispatcher sends HTTP POST to configured URL."""
        from scripts.alerts.dispatcher import WebhookDispatcher

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True

        with patch(
            "scripts.alerts.dispatcher.httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_post:
            dispatcher = WebhookDispatcher(config)
            result = await dispatcher.dispatch(sample_event)

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args.kwargs["url"] == "http://localhost:5678/webhook/test"
            assert call_args.kwargs["json"]["event_id"] == "test-event-1234"
            assert result.status == "sent"

    @pytest.mark.asyncio
    async def test_dispatcher_signs_request_when_secret_set(
        self, sample_event, config_with_secret
    ):
        """T012: Dispatcher adds HMAC signature when secret is configured."""
        from scripts.alerts.dispatcher import WebhookDispatcher

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True

        with patch(
            "scripts.alerts.dispatcher.httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_post:
            dispatcher = WebhookDispatcher(config_with_secret)
            await dispatcher.dispatch(sample_event)

            call_args = mock_post.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "X-UTXOracle-Signature" in headers
            # Signature should be sha256=<hex>
            assert headers["X-UTXOracle-Signature"].startswith("sha256=")

    @pytest.mark.asyncio
    async def test_dispatcher_retries_on_failure(self, sample_event, config):
        """T013: Dispatcher retries up to max_retries on HTTP failure."""
        from scripts.alerts.dispatcher import WebhookDispatcher

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.is_success = False

        with patch(
            "scripts.alerts.dispatcher.httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_post:
            dispatcher = WebhookDispatcher(config)
            result = await dispatcher.dispatch(sample_event)

            # Should have tried max_retries times
            assert mock_post.call_count == config.max_retries
            assert result.status == "failed"
            assert result.attempt_count == config.max_retries

    @pytest.mark.asyncio
    async def test_dispatcher_respects_timeout(self, sample_event, config):
        """T014: Dispatcher uses configured timeout for requests."""
        from scripts.alerts.dispatcher import WebhookDispatcher

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True

        with patch(
            "scripts.alerts.dispatcher.httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_post:
            dispatcher = WebhookDispatcher(config)
            await dispatcher.dispatch(sample_event)

            call_args = mock_post.call_args
            assert call_args.kwargs["timeout"] == config.timeout_seconds

    @pytest.mark.asyncio
    async def test_dispatcher_skips_when_disabled(self, sample_event, config_disabled):
        """T015: Dispatcher skips sending when config.enabled is False."""
        from scripts.alerts.dispatcher import WebhookDispatcher

        with patch(
            "scripts.alerts.dispatcher.httpx.AsyncClient.post",
            new_callable=AsyncMock,
        ) as mock_post:
            dispatcher = WebhookDispatcher(config_disabled)
            result = await dispatcher.dispatch(sample_event)

            # Should not make any HTTP calls
            mock_post.assert_not_called()
            # Return value indicates skipped
            assert result is None or result.status == "skipped"


# =============================================================================
# Phase 4: Event Generators Tests (T020-T025)
# =============================================================================


class TestEventGenerators:
    """Tests for event factory functions."""

    def test_create_whale_event(self):
        """T020: create_whale_event() produces valid whale event."""
        from scripts.alerts.generators import create_whale_event

        event = create_whale_event(
            amount_btc=500.0,
            direction="INFLOW",
            signal_vote=-0.7,
            exchange="binance",
            usd_value=50_000_000,
        )

        assert event.event_type == "whale"
        assert event.payload["amount_btc"] == 500.0
        assert event.payload["direction"] == "INFLOW"
        assert event.payload["signal_vote"] == -0.7
        assert event.payload["exchange"] == "binance"
        assert event.payload["usd_value"] == 50_000_000
        assert event.event_id  # UUID is set
        assert event.timestamp  # Timestamp is set

    def test_whale_event_severity_by_amount(self):
        """T021: Whale event severity determined by amount_btc."""
        from scripts.alerts.generators import create_whale_event

        # Critical: >1000 BTC
        event_critical = create_whale_event(
            amount_btc=1500.0, direction="INFLOW", signal_vote=-0.5
        )
        assert event_critical.severity == "critical"

        # High: >500 BTC
        event_high = create_whale_event(
            amount_btc=750.0, direction="OUTFLOW", signal_vote=0.5
        )
        assert event_high.severity == "high"

        # Medium: >100 BTC (default)
        event_medium = create_whale_event(
            amount_btc=200.0, direction="INFLOW", signal_vote=-0.3
        )
        assert event_medium.severity == "medium"

        # Low: <=100 BTC
        event_low = create_whale_event(
            amount_btc=50.0, direction="OUTFLOW", signal_vote=0.2
        )
        assert event_low.severity == "low"

    def test_create_signal_event(self):
        """T022: create_signal_event() produces valid signal event."""
        from scripts.alerts.generators import create_signal_event

        event = create_signal_event(
            action="BUY",
            confidence=0.85,
            signal_mean=0.65,
            top_contributors=[
                {"name": "whale", "value": 0.60},
                {"name": "symbolic", "value": 0.80},
            ],
        )

        assert event.event_type == "signal"
        assert event.payload["action"] == "BUY"
        assert event.payload["confidence"] == 0.85
        assert event.payload["signal_mean"] == 0.65
        assert len(event.payload["top_contributors"]) == 2
        assert event.event_id
        assert event.timestamp

    def test_signal_event_excludes_hold(self):
        """T023: create_signal_event() returns None for HOLD action."""
        from scripts.alerts.generators import create_signal_event

        event = create_signal_event(
            action="HOLD",
            confidence=0.5,
            signal_mean=0.0,
            top_contributors=[],
        )

        assert event is None

    def test_signal_event_severity_by_confidence(self):
        """Signal event severity determined by confidence."""
        from scripts.alerts.generators import create_signal_event

        # Critical: >0.95
        event_critical = create_signal_event(
            action="BUY", confidence=0.98, signal_mean=0.8, top_contributors=[]
        )
        assert event_critical.severity == "critical"

        # High: >0.85
        event_high = create_signal_event(
            action="SELL", confidence=0.90, signal_mean=-0.7, top_contributors=[]
        )
        assert event_high.severity == "high"

        # Medium: >0.70
        event_medium = create_signal_event(
            action="BUY", confidence=0.75, signal_mean=0.5, top_contributors=[]
        )
        assert event_medium.severity == "medium"

    def test_create_regime_event(self):
        """T024: create_regime_event() produces valid regime event."""
        from scripts.alerts.generators import create_regime_event

        event = create_regime_event(
            metric="power_law",
            from_state="NEUTRAL",
            to_state="ACCUMULATION",
            details={"tau_old": 2.0, "tau_new": 1.6},
            implication="Whale concentration increasing",
        )

        assert event.event_type == "regime"
        assert event.payload["metric"] == "power_law"
        assert event.payload["from_state"] == "NEUTRAL"
        assert event.payload["to_state"] == "ACCUMULATION"
        assert event.payload["details"]["tau_new"] == 1.6
        assert event.payload["implication"] == "Whale concentration increasing"
        assert event.event_id
        assert event.timestamp

    def test_create_price_event(self):
        """T025: create_price_event() produces valid price event."""
        from scripts.alerts.generators import create_price_event

        event = create_price_event(
            utxoracle_price=100000,
            exchange_price=97000,
            divergence_pct=3.09,
        )

        assert event.event_type == "price"
        assert event.payload["utxoracle_price"] == 100000
        assert event.payload["exchange_price"] == 97000
        assert event.payload["divergence_pct"] == 3.09
        assert event.payload["direction"] == "ABOVE"
        assert event.event_id
        assert event.timestamp

    def test_price_event_direction_below(self):
        """Price event direction is BELOW when UTXOracle < exchange."""
        from scripts.alerts.generators import create_price_event

        event = create_price_event(
            utxoracle_price=95000,
            exchange_price=100000,
            divergence_pct=-5.0,
        )

        assert event.payload["direction"] == "BELOW"

    def test_regime_event_no_change(self):
        """Regime event returns None when from_state == to_state."""
        from scripts.alerts.generators import create_regime_event

        event = create_regime_event(
            metric="power_law",
            from_state="NEUTRAL",
            to_state="NEUTRAL",
            details={},
            implication="No change",
        )

        assert event is None


# =============================================================================
# Phase 5: Persistence Tests (T031-T033)
# =============================================================================


class TestPersistence:
    """Tests for DuckDB event persistence."""

    @pytest.fixture
    def sample_event(self):
        """Create a sample AlertEvent for tests."""
        from scripts.alerts.models import AlertEvent

        return AlertEvent(
            event_id="test-persist-1234",
            event_type="whale",
            timestamp=datetime(2025, 12, 4, 15, 30, 0, tzinfo=timezone.utc),
            severity="high",
            payload={"amount_btc": 500.0, "direction": "INFLOW"},
        )

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary DuckDB database."""
        import duckdb

        db_path = tmp_path / "test_alerts.duckdb"
        conn = duckdb.connect(str(db_path))

        # Create the alert_events table
        conn.execute("""
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
            )
        """)
        conn.close()

        return str(db_path)

    def test_save_event_to_db(self, sample_event, temp_db):
        """T031: save_event() persists event to DuckDB."""
        from scripts.alerts import save_event
        import duckdb

        save_event(sample_event, db_path=temp_db)

        # Verify event was saved
        conn = duckdb.connect(temp_db)
        result = conn.execute(
            "SELECT event_id, event_type, severity FROM alert_events WHERE event_id = ?",
            [sample_event.event_id],
        ).fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "test-persist-1234"
        assert result[1] == "whale"
        assert result[2] == "high"

    def test_update_event_webhook_status(self, sample_event, temp_db):
        """T032: update_webhook_status() updates delivery status."""
        from scripts.alerts import save_event, update_webhook_status
        import duckdb

        # First save the event
        save_event(sample_event, db_path=temp_db)

        # Update status to sent
        update_webhook_status(
            sample_event.event_id,
            status="sent",
            response_code=200,
            db_path=temp_db,
        )

        # Verify update
        conn = duckdb.connect(temp_db)
        result = conn.execute(
            "SELECT webhook_status, webhook_response_code FROM alert_events WHERE event_id = ?",
            [sample_event.event_id],
        ).fetchone()
        conn.close()

        assert result[0] == "sent"
        assert result[1] == 200

    def test_get_failed_events_for_replay(self, temp_db):
        """T033: get_failed_events() returns events with failed status."""
        from scripts.alerts import save_event, update_webhook_status, get_failed_events
        from scripts.alerts.models import AlertEvent

        # Create and save multiple events
        events = [
            AlertEvent(
                event_id=f"event-{i}",
                event_type="whale",
                timestamp=datetime(2025, 12, 4, 15, 30, i, tzinfo=timezone.utc),
                severity="medium",
                payload={"amount_btc": 100 + i},
            )
            for i in range(5)
        ]

        for event in events:
            save_event(event, db_path=temp_db)

        # Mark some as failed
        update_webhook_status(
            "event-1", status="failed", error="Connection timeout", db_path=temp_db
        )
        update_webhook_status(
            "event-3", status="failed", error="HTTP 500", db_path=temp_db
        )
        update_webhook_status(
            "event-2", status="sent", response_code=200, db_path=temp_db
        )

        # Get failed events
        failed = get_failed_events(db_path=temp_db)

        assert len(failed) == 2
        event_ids = [e.event_id for e in failed]
        assert "event-1" in event_ids
        assert "event-3" in event_ids
        assert "event-2" not in event_ids
