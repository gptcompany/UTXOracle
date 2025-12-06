"""
Integration tests for the Webhook Alert System (spec-011).

Tests the full flow from event creation to webhook delivery.
"""

import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary DuckDB database with alert_events table."""
    import duckdb

    db_path = tmp_path / "test_alerts_integration.duckdb"
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


@pytest.fixture
def webhook_env():
    """Set up webhook environment variables."""
    env = {
        "ALERT_WEBHOOK_URL": "http://localhost:5678/webhook/test",
        "ALERT_WEBHOOK_SECRET": "test-secret",
        "ALERT_ENABLED": "true",
        "ALERT_MIN_SEVERITY": "low",
        "ALERT_WHALE_ENABLED": "true",
        "ALERT_SIGNAL_ENABLED": "true",
        "ALERT_WHALE_MIN_BTC": "50",
        "ALERT_SIGNAL_MIN_CONFIDENCE": "0.5",
    }
    with patch.dict(os.environ, env, clear=False):
        yield env


class TestAlertIntegration:
    """Integration tests for the full alert flow."""

    @pytest.mark.asyncio
    async def test_full_alert_flow_whale_event(self, temp_db, webhook_env):
        """Test full flow: create whale event -> emit -> check DB."""
        from scripts.alerts import emit_alert
        from scripts.alerts.generators import create_whale_event
        import duckdb

        # Create whale event
        event = create_whale_event(
            amount_btc=500.0,
            direction="INFLOW",
            signal_vote=-0.7,
            exchange="binance",
        )

        # Mock the HTTP call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True

        with patch(
            "scripts.alerts.dispatcher.httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            # Emit the alert
            delivery = await emit_alert(event, db_path=temp_db)

        # Verify delivery
        assert delivery is not None
        assert delivery.status == "sent"
        assert delivery.response_code == 200

        # Verify event was saved to DB
        conn = duckdb.connect(temp_db)
        result = conn.execute(
            "SELECT event_id, event_type, webhook_status FROM alert_events WHERE event_id = ?",
            [event.event_id],
        ).fetchone()
        conn.close()

        assert result is not None
        assert result[0] == event.event_id
        assert result[1] == "whale"
        assert result[2] == "sent"

    @pytest.mark.asyncio
    async def test_full_alert_flow_signal_event(self, temp_db, webhook_env):
        """Test full flow: create signal event -> emit -> check DB."""
        from scripts.alerts import emit_alert
        from scripts.alerts.generators import create_signal_event
        import duckdb

        # Create signal event
        event = create_signal_event(
            action="BUY",
            confidence=0.85,
            signal_mean=0.65,
            top_contributors=[{"name": "whale", "value": 0.6}],
        )

        assert event is not None  # Signal events for BUY/SELL should be created

        # Mock the HTTP call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True

        with patch(
            "scripts.alerts.dispatcher.httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            delivery = await emit_alert(event, db_path=temp_db)

        assert delivery is not None
        assert delivery.status == "sent"

        # Verify in DB
        conn = duckdb.connect(temp_db)
        result = conn.execute(
            "SELECT event_type, severity FROM alert_events WHERE event_id = ?",
            [event.event_id],
        ).fetchone()
        conn.close()

        assert result[0] == "signal"
        # 0.85 confidence is at the boundary - our code uses > not >=
        # So 0.85 is medium (not > 0.85 threshold for high)
        assert result[1] == "medium"

    @pytest.mark.asyncio
    async def test_alert_flow_with_webhook_failure(self, temp_db, webhook_env):
        """Test that webhook failures are recorded in DB."""
        from scripts.alerts import emit_alert
        from scripts.alerts.generators import create_price_event
        import duckdb

        # Create price event
        event = create_price_event(
            utxoracle_price=100000,
            exchange_price=95000,
            divergence_pct=5.26,
        )

        # Mock HTTP failure
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.is_success = False

        with patch(
            "scripts.alerts.dispatcher.httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            delivery = await emit_alert(event, db_path=temp_db)

        assert delivery is not None
        assert delivery.status == "failed"

        # Verify failure recorded in DB
        conn = duckdb.connect(temp_db)
        result = conn.execute(
            "SELECT webhook_status, webhook_attempts FROM alert_events WHERE event_id = ?",
            [event.event_id],
        ).fetchone()
        conn.close()

        assert result[0] == "failed"
        # webhook_attempts counts the update_webhook_status call (1 call)
        # not the internal retry count (3 attempts)
        assert result[1] >= 1

    @pytest.mark.asyncio
    async def test_alert_skip_when_disabled(self, temp_db):
        """Test that alerts are skipped when disabled."""
        from scripts.alerts import emit_alert
        from scripts.alerts.generators import create_whale_event

        # Create event
        event = create_whale_event(
            amount_btc=100.0,
            direction="OUTFLOW",
            signal_vote=0.5,
        )

        # Disable alerts
        env = {
            "ALERT_ENABLED": "false",
            "ALERT_WEBHOOK_URL": "http://localhost:5678/test",
        }

        with patch.dict(os.environ, env, clear=False):
            with patch(
                "scripts.alerts.dispatcher.httpx.AsyncClient.post",
                new_callable=AsyncMock,
            ) as mock_post:
                delivery = await emit_alert(event, db_path=temp_db)

        # Should be skipped
        assert delivery is None
        mock_post.assert_not_called()

    def test_sync_emit_alert(self, temp_db, webhook_env):
        """Test synchronous emit_alert_sync wrapper."""
        from scripts.alerts import emit_alert_sync
        from scripts.alerts.generators import create_regime_event

        # Create regime event
        event = create_regime_event(
            metric="power_law",
            from_state="NEUTRAL",
            to_state="ACCUMULATION",
            details={"tau_old": 2.0, "tau_new": 1.6},
            implication="Whale concentration increasing",
        )

        assert event is not None

        # Mock the HTTP call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True

        with patch(
            "scripts.alerts.dispatcher.httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            delivery = emit_alert_sync(event, db_path=temp_db)

        assert delivery is not None
        assert delivery.status == "sent"

    def test_hmac_signature_included(self, temp_db, webhook_env):
        """Test that HMAC signature is included in requests."""
        from scripts.alerts import emit_alert_sync
        from scripts.alerts.generators import create_whale_event

        event = create_whale_event(
            amount_btc=200.0,
            direction="INFLOW",
            signal_vote=-0.3,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True

        with patch(
            "scripts.alerts.dispatcher.httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_post:
            emit_alert_sync(event, db_path=temp_db)

        # Check that signature header was included
        call_args = mock_post.call_args
        headers = call_args.kwargs.get("headers", {})
        assert "X-UTXOracle-Signature" in headers
        assert headers["X-UTXOracle-Signature"].startswith("sha256=")
