#!/usr/bin/env python3
"""
Tests for WebSocket Reconnection Utility
Task: P2 - Test coverage for resilience components

Focus: Error paths and edge cases
- Connection failures
- Exponential backoff calculation
- State transitions
- Statistics tracking
- Jitter behavior
- Max retries enforcement
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# Import module under test
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "utils"))

try:
    from websocket_reconnect import (
        WebSocketReconnector,
        ConnectionState,
        ReconnectionStats,
    )

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    pytest.skip("websockets library not available", allow_module_level=True)


class TestConnectionState:
    """Test ConnectionState enum"""

    def test_connection_states_exist(self):
        """All required states should be defined"""
        assert ConnectionState.DISCONNECTED == "disconnected"
        assert ConnectionState.CONNECTING == "connecting"
        assert ConnectionState.CONNECTED == "connected"
        assert ConnectionState.RECONNECTING == "reconnecting"
        assert ConnectionState.FAILED == "failed"


class TestReconnectionStats:
    """Test ReconnectionStats dataclass"""

    def test_default_initialization(self):
        """Stats should initialize with default values"""
        stats = ReconnectionStats()

        assert stats.total_attempts == 0
        assert stats.successful_connections == 0
        assert stats.failed_connections == 0
        assert stats.current_streak == 0
        assert stats.max_streak == 0
        assert stats.last_success is None
        assert stats.last_failure is None
        assert stats.total_uptime_seconds == 0.0
        assert stats.connection_start is None


class TestWebSocketReconnector:
    """Test WebSocketReconnector class"""

    @pytest.fixture
    def mock_callback(self):
        """Mock async callback for connection"""
        return AsyncMock()

    @pytest.fixture
    def reconnector(self, mock_callback):
        """Create reconnector instance"""
        return WebSocketReconnector(
            url="ws://localhost:8765",
            on_connect_callback=mock_callback,
            max_retries=3,
            initial_delay=1.0,
            max_delay=10.0,
        )

    def test_initialization(self, reconnector):
        """Reconnector should initialize with correct parameters"""
        assert reconnector.url == "ws://localhost:8765"
        assert reconnector.max_retries == 3
        assert reconnector.initial_delay == 1.0
        assert reconnector.max_delay == 10.0
        assert reconnector.state == ConnectionState.DISCONNECTED
        assert isinstance(reconnector.stats, ReconnectionStats)

    def test_is_connected_when_disconnected(self, reconnector):
        """is_connected should return False when disconnected"""
        assert reconnector.is_connected is False

    def test_is_connected_when_connected(self, reconnector):
        """is_connected should return True when connected"""
        reconnector.state = ConnectionState.CONNECTED
        assert reconnector.is_connected is True

    def test_calculate_backoff_delay_exponential_growth(self, reconnector):
        """Backoff delay should grow exponentially"""
        # First attempt: 1.0s (with jitter, so between 0.8-1.2)
        delay1 = reconnector._calculate_backoff_delay()
        assert 0.8 <= delay1 <= 1.2

        # Second attempt: 2.0s (with jitter, so between 1.6-2.4)
        delay2 = reconnector._calculate_backoff_delay()
        assert 1.6 <= delay2 <= 2.4

        # Third attempt: 4.0s (with jitter, so between 3.2-4.8)
        delay3 = reconnector._calculate_backoff_delay()
        assert 3.2 <= delay3 <= 4.8

    def test_calculate_backoff_delay_respects_max(self, reconnector):
        """Backoff delay should not exceed max_delay"""
        # Force high current delay
        reconnector._current_delay = 100.0

        delay = reconnector._calculate_backoff_delay()

        # Should be capped at max_delay (10.0) with jitter ±20%
        assert 8.0 <= delay <= 12.0

    def test_calculate_backoff_delay_without_jitter(self, mock_callback):
        """Backoff should be exact without jitter"""
        reconnector = WebSocketReconnector(
            url="ws://localhost:8765",
            on_connect_callback=mock_callback,
            jitter=False,
            initial_delay=2.0,
        )

        delay = reconnector._calculate_backoff_delay()
        assert delay == 2.0  # Exact value, no jitter

    def test_reset_backoff(self, reconnector):
        """Reset should restore initial delay and clear streak"""
        # Simulate several failures
        reconnector._current_delay = 16.0
        reconnector.stats.current_streak = 5

        reconnector._reset_backoff()

        assert reconnector._current_delay == 1.0
        assert reconnector.stats.current_streak == 0

    @pytest.mark.asyncio
    async def test_connect_success(self, reconnector, mock_callback):
        """Successful connection should update stats and state"""
        with patch("websockets.connect", new_callable=AsyncMock) as mock_ws:
            mock_ws.return_value = MagicMock()

            result = await reconnector._connect()

            assert result is True
            assert reconnector.state == ConnectionState.CONNECTED
            assert reconnector.stats.total_attempts == 1
            assert reconnector.stats.successful_connections == 1
            assert reconnector.stats.failed_connections == 0
            assert reconnector.stats.last_success is not None
            mock_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, reconnector, mock_callback):
        """Failed connection should update stats and state"""
        with patch("websockets.connect", new_callable=AsyncMock) as mock_ws:
            mock_ws.side_effect = ConnectionError("Connection refused")

            result = await reconnector._connect()

            assert result is False
            assert reconnector.state == ConnectionState.DISCONNECTED
            assert reconnector.stats.total_attempts == 1
            assert reconnector.stats.successful_connections == 0
            assert reconnector.stats.failed_connections == 1
            assert reconnector.stats.current_streak == 1
            assert reconnector.stats.last_failure is not None
            mock_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_connect_multiple_failures_updates_max_streak(
        self, reconnector, mock_callback
    ):
        """Multiple failures should update max_streak"""
        with patch("websockets.connect", new_callable=AsyncMock) as mock_ws:
            mock_ws.side_effect = ConnectionError("Connection refused")

            # Fail 3 times
            for _ in range(3):
                await reconnector._connect()

            assert reconnector.stats.current_streak == 3
            assert reconnector.stats.max_streak == 3
            assert reconnector.stats.failed_connections == 3

    @pytest.mark.asyncio
    async def test_handle_disconnection_updates_uptime(self, reconnector):
        """Disconnection should calculate and add uptime"""
        # Simulate connection start
        reconnector.stats.connection_start = datetime.now(timezone.utc)

        # Wait a bit
        await asyncio.sleep(0.1)

        await reconnector._handle_disconnection()

        assert reconnector.stats.total_uptime_seconds > 0
        assert reconnector.stats.connection_start is None

    @pytest.mark.asyncio
    async def test_stop_closes_connection(self, reconnector, mock_callback):
        """stop() should close WebSocket and set disconnected state"""
        # Mock active connection
        mock_ws = AsyncMock()
        reconnector._websocket = mock_ws
        reconnector.state = ConnectionState.CONNECTED

        await reconnector.stop()

        mock_ws.close.assert_called_once()
        assert reconnector.state == ConnectionState.DISCONNECTED
        assert reconnector._stop_event.is_set()

    def test_get_stats_returns_dict(self, reconnector):
        """get_stats should return properly formatted dictionary"""
        reconnector.stats.total_attempts = 5
        reconnector.stats.successful_connections = 3
        reconnector.stats.failed_connections = 2

        stats_dict = reconnector.get_stats()

        assert isinstance(stats_dict, dict)
        assert stats_dict["state"] == "disconnected"
        assert stats_dict["total_attempts"] == 5
        assert stats_dict["successful_connections"] == 3
        assert stats_dict["failed_connections"] == 2
        assert stats_dict["success_rate"] == 60.0  # 3/5 * 100

    def test_get_stats_success_rate_zero_attempts(self, reconnector):
        """Success rate should be 0 when no attempts"""
        stats_dict = reconnector.get_stats()
        assert stats_dict["success_rate"] == 0

    def test_uptime_seconds_when_not_connected(self, reconnector):
        """uptime_seconds should be 0 when not connected"""
        assert reconnector.uptime_seconds == 0.0

    def test_uptime_seconds_when_connected(self, reconnector):
        """uptime_seconds should calculate correctly when connected"""
        reconnector.state = ConnectionState.CONNECTED
        reconnector.stats.connection_start = datetime.now(timezone.utc)

        # Small delay
        import time

        time.sleep(0.1)

        uptime = reconnector.uptime_seconds
        assert uptime > 0.0
        assert uptime < 1.0  # Should be fraction of a second


class TestWebSocketReconnectorEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.mark.asyncio
    async def test_importerror_when_websockets_unavailable(self):
        """Should raise ImportError if websockets library not available"""
        with patch("scripts.utils.websocket_reconnect.WEBSOCKETS_AVAILABLE", False):
            with pytest.raises(ImportError, match="websockets library required"):
                WebSocketReconnector(
                    url="ws://localhost:8765", on_connect_callback=AsyncMock()
                )

    @pytest.mark.asyncio
    async def test_max_retries_reached(self):
        """Should fail after max_retries exceeded"""
        reconnector = WebSocketReconnector(
            url="ws://localhost:8765",
            on_connect_callback=AsyncMock(),
            max_retries=2,
            initial_delay=0.1,
            max_delay=0.2,
        )

        with patch("websockets.connect", new_callable=AsyncMock) as mock_ws:
            mock_ws.side_effect = ConnectionError("Connection refused")

            # Start reconnection loop (will timeout after short delay)
            task = asyncio.create_task(reconnector.start())

            # Wait for max retries to be exceeded
            await asyncio.sleep(0.5)

            # Stop the reconnector
            await reconnector.stop()

            # Wait for task to complete
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except asyncio.TimeoutError:
                task.cancel()

            # Should have failed after max_retries
            assert reconnector.stats.failed_connections >= 2

    def test_callback_optional(self):
        """on_disconnect_callback should be optional"""
        reconnector = WebSocketReconnector(
            url="ws://localhost:8765",
            on_connect_callback=AsyncMock(),
            on_disconnect_callback=None,  # Explicitly None
        )

        assert reconnector.on_disconnect_callback is None
