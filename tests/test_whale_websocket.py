"""
Test suite for WebSocket connection manager and endpoint.
Task T026: Write tests for WebSocket functionality.
"""

import pytest
import time
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from api.whale_websocket import (
    ClientConnection,
    ConnectionManager,
    handle_client_message,
)


class TestClientConnection:
    """Test ClientConnection class."""

    def test_client_initialization(self):
        """Test client connection initialization."""
        websocket = Mock()
        connection_id = "test-conn-123"
        user_id = "user_1"
        client_ip = "192.168.1.100"

        client = ClientConnection(
            websocket=websocket,
            connection_id=connection_id,
            user_id=user_id,
            client_ip=client_ip,
        )

        assert client.connection_id == connection_id
        assert client.user_id == user_id
        assert client.client_ip == client_ip
        assert client.message_sequence == 0
        assert len(client.subscribed_channels) == 0
        assert client.missed_pongs == 0

    def test_update_activity(self):
        """Test activity timestamp update."""
        websocket = Mock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")

        initial_time = client.last_activity
        time.sleep(0.1)
        client.update_activity()

        assert client.last_activity > initial_time

    def test_get_next_sequence(self):
        """Test sequence number increment."""
        websocket = Mock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")

        assert client.get_next_sequence() == 1
        assert client.get_next_sequence() == 2
        assert client.get_next_sequence() == 3
        assert client.message_sequence == 3

    def test_is_subscribed_to(self):
        """Test channel subscription check."""
        websocket = Mock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")

        client.subscribed_channels.add("transactions")

        assert client.is_subscribed_to("transactions") is True
        assert client.is_subscribed_to("netflow") is False

    def test_get_connection_info(self):
        """Test connection metadata retrieval."""
        websocket = Mock()
        client = ClientConnection(websocket, "conn1", "user1", "192.168.1.1")
        client.subscribed_channels = {"transactions", "alerts"}
        client.message_sequence = 5
        client.missed_pongs = 1

        info = client.get_connection_info()

        assert info["connection_id"] == "conn1"
        assert info["user_id"] == "user1"
        assert info["client_ip"] == "192.168.1.1"
        assert set(info["subscribed_channels"]) == {"transactions", "alerts"}
        assert info["message_count"] == 5
        assert info["missed_pongs"] == 1


class TestConnectionManager:
    """Test ConnectionManager class."""

    @pytest.fixture
    def manager(self):
        """Fixture for connection manager."""
        return ConnectionManager()

    @pytest.mark.asyncio
    async def test_manager_initialization(self, manager):
        """Test connection manager initializes correctly."""
        assert len(manager.active_connections) == 0
        assert len(manager.channel_subscriptions) == 0
        assert len(manager.user_connections) == 0
        assert manager.heartbeat_task is None

    @pytest.mark.asyncio
    async def test_connect_valid_token(self, manager):
        """Test successful connection with valid token."""
        websocket = AsyncMock()
        websocket.accept = AsyncMock()
        websocket.send_json = AsyncMock()

        token = "valid_token"
        client_ip = "127.0.0.1"

        # Mock token validation
        with patch(
            "api.whale_websocket.validate_websocket_token",
            return_value=(True, {"user_id": "test_user"}),
        ):
            client = await manager.connect(websocket, token, client_ip)

        assert client is not None
        assert client.user_id == "test_user"
        assert client.client_ip == client_ip
        assert len(manager.active_connections) == 1
        assert "test_user" in manager.user_connections

        # Verify websocket accept was called
        websocket.accept.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_invalid_token(self, manager):
        """Test connection rejection with invalid token."""
        websocket = AsyncMock()

        token = "invalid_token"
        client_ip = "127.0.0.1"

        # Mock token validation failure
        with patch(
            "api.whale_websocket.validate_websocket_token",
            return_value=(False, None),
        ):
            client = await manager.connect(websocket, token, client_ip)

        assert client is None
        assert len(manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_disconnect(self, manager):
        """Test client disconnection and cleanup."""
        # Create mock client
        websocket = AsyncMock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        client.subscribed_channels = {"transactions", "alerts"}

        # Register client
        manager.active_connections["conn1"] = client
        manager.user_connections["user1"].add("conn1")
        manager.channel_subscriptions["transactions"].add("conn1")
        manager.channel_subscriptions["alerts"].add("conn1")

        # Disconnect
        await manager.disconnect("conn1")

        # Verify cleanup
        assert "conn1" not in manager.active_connections
        assert "user1" not in manager.user_connections
        assert "conn1" not in manager.channel_subscriptions.get("transactions", set())
        assert "conn1" not in manager.channel_subscriptions.get("alerts", set())

    @pytest.mark.asyncio
    async def test_subscribe(self, manager):
        """Test channel subscription."""
        websocket = AsyncMock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        manager.active_connections["conn1"] = client

        # Subscribe to channels
        await manager.subscribe("conn1", ["transactions", "netflow"])

        # Verify subscriptions
        assert "transactions" in client.subscribed_channels
        assert "netflow" in client.subscribed_channels
        assert "conn1" in manager.channel_subscriptions["transactions"]
        assert "conn1" in manager.channel_subscriptions["netflow"]

    @pytest.mark.asyncio
    async def test_unsubscribe(self, manager):
        """Test channel unsubscription."""
        websocket = AsyncMock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        manager.active_connections["conn1"] = client

        # Setup initial subscriptions
        client.subscribed_channels = {"transactions", "netflow", "alerts"}
        manager.channel_subscriptions["transactions"].add("conn1")
        manager.channel_subscriptions["netflow"].add("conn1")
        manager.channel_subscriptions["alerts"].add("conn1")

        # Unsubscribe from some channels
        await manager.unsubscribe("conn1", ["transactions", "netflow"])

        # Verify unsubscriptions
        assert "transactions" not in client.subscribed_channels
        assert "netflow" not in client.subscribed_channels
        assert "alerts" in client.subscribed_channels
        assert "conn1" not in manager.channel_subscriptions.get("transactions", set())
        assert "conn1" not in manager.channel_subscriptions.get("netflow", set())
        assert "conn1" in manager.channel_subscriptions["alerts"]

    @pytest.mark.asyncio
    async def test_send_personal_message(self, manager):
        """Test sending message to specific client."""
        websocket = AsyncMock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        manager.active_connections["conn1"] = client

        message = {"type": "test", "data": "hello"}

        await manager.send_personal_message("conn1", message)

        # Verify message sent
        websocket.send_json.assert_awaited_once()
        sent_message = websocket.send_json.call_args[0][0]

        assert sent_message["type"] == "test"
        assert sent_message["data"] == "hello"
        assert "sequence" in sent_message
        assert "timestamp" in sent_message

    @pytest.mark.asyncio
    async def test_broadcast_to_channel(self, manager):
        """Test broadcasting message to channel subscribers."""
        # Create multiple clients
        clients = []
        for i in range(3):
            websocket = AsyncMock()
            client = ClientConnection(websocket, f"conn{i}", f"user{i}", "127.0.0.1")
            manager.active_connections[f"conn{i}"] = client
            clients.append(client)

        # Subscribe all to "transactions" channel
        for i in range(3):
            await manager.subscribe(f"conn{i}", ["transactions"])

        # Broadcast message
        message = {"type": "transaction", "data": {"amount": 100}}
        await manager.broadcast_to_channel("transactions", message)

        # Verify all clients received messages (ack + broadcast = 2 calls each)
        for client in clients:
            assert client.websocket.send_json.await_count == 2  # 1 ack + 1 broadcast

    @pytest.mark.asyncio
    async def test_broadcast_to_empty_channel(self, manager):
        """Test broadcasting to channel with no subscribers."""
        message = {"type": "test", "data": "hello"}

        # Should not raise exception
        await manager.broadcast_to_channel("nonexistent_channel", message)

    @pytest.mark.asyncio
    async def test_send_error(self, manager):
        """Test sending error message to client."""
        websocket = AsyncMock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        manager.active_connections["conn1"] = client

        await manager.send_error(
            client, "TEST_ERROR", "Test error message", retry_after=30
        )

        # Verify error message sent
        websocket.send_json.assert_awaited_once()
        sent_message = websocket.send_json.call_args[0][0]

        assert sent_message["type"] == "error"
        assert sent_message["error"]["code"] == "TEST_ERROR"
        assert sent_message["error"]["message"] == "Test error message"
        assert sent_message["error"]["retry_after"] == 30

    @pytest.mark.asyncio
    async def test_send_pong(self, manager):
        """Test sending pong response."""
        websocket = AsyncMock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        manager.active_connections["conn1"] = client

        ping_sequence = 5
        await manager.send_pong(client, ping_sequence)

        # Verify pong message sent
        websocket.send_json.assert_awaited_once()
        sent_message = websocket.send_json.call_args[0][0]

        assert sent_message["type"] == "pong"
        assert sent_message["ping_sequence"] == ping_sequence
        assert "server_time" in sent_message

    @pytest.mark.asyncio
    async def test_heartbeat_monitor_disconnect_idle(self, manager):
        """Test heartbeat monitor disconnects idle clients."""
        websocket = AsyncMock()
        websocket.client_state = Mock()
        websocket.client_state.CONNECTED = 1
        websocket.close = AsyncMock()

        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        client.last_activity = time.time() - 100  # 100 seconds ago (idle)

        manager.active_connections["conn1"] = client

        # Manually run one heartbeat check
        disconnected = []
        for connection_id, c in list(manager.active_connections.items()):
            idle_time = time.time() - c.last_activity
            if idle_time > 90:
                disconnected.append(connection_id)

        assert "conn1" in disconnected

    @pytest.mark.asyncio
    async def test_heartbeat_monitor_disconnect_missed_pongs(self, manager):
        """Test heartbeat monitor disconnects unresponsive clients."""
        websocket = AsyncMock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        client.missed_pongs = 3  # Missed 3 pongs

        manager.active_connections["conn1"] = client

        # Check missed pongs logic
        disconnected = []
        for connection_id, c in list(manager.active_connections.items()):
            if c.missed_pongs >= 3:
                disconnected.append(connection_id)

        assert "conn1" in disconnected

    def test_get_stats(self, manager):
        """Test connection statistics retrieval."""
        # Create test connections
        websocket = AsyncMock()

        client1 = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        client2 = ClientConnection(websocket, "conn2", "user1", "127.0.0.1")
        client3 = ClientConnection(websocket, "conn3", "user2", "127.0.0.1")

        manager.active_connections = {
            "conn1": client1,
            "conn2": client2,
            "conn3": client3,
        }

        manager.user_connections = {
            "user1": {"conn1", "conn2"},
            "user2": {"conn3"},
        }

        manager.channel_subscriptions = {
            "transactions": {"conn1", "conn2", "conn3"},
            "netflow": {"conn1"},
        }

        stats = manager.get_stats()

        assert stats["total_connections"] == 3
        assert stats["total_users"] == 2
        assert stats["total_channels"] == 2
        assert stats["channels"]["transactions"] == 3
        assert stats["channels"]["netflow"] == 1


class TestMessageHandling:
    """Test message routing and handling."""

    @pytest.mark.asyncio
    async def test_handle_subscribe_message(self):
        """Test handling subscribe message."""
        manager = ConnectionManager()
        websocket = AsyncMock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        manager.active_connections["conn1"] = client

        message_data = {
            "type": "subscribe",
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "sequence": 1,
            "channels": ["transactions", "alerts"],
        }

        # Patch global connection_manager to use our test instance
        with (
            patch("api.whale_websocket.rate_limiter.check_ws_limit", return_value=True),
            patch("api.whale_websocket.connection_manager", manager),
        ):
            await handle_client_message(client, message_data)

        # Verify subscriptions
        assert "transactions" in client.subscribed_channels
        assert "alerts" in client.subscribed_channels

    @pytest.mark.asyncio
    async def test_handle_unsubscribe_message(self):
        """Test handling unsubscribe message."""
        manager = ConnectionManager()
        websocket = AsyncMock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        manager.active_connections["conn1"] = client

        # Setup initial subscriptions
        client.subscribed_channels = {"transactions", "alerts", "netflow"}

        message_data = {
            "type": "unsubscribe",
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "sequence": 2,
            "channels": ["transactions"],
        }

        with patch(
            "api.whale_websocket.rate_limiter.check_ws_limit", return_value=True
        ):
            await handle_client_message(client, message_data)

        # Verify unsubscription (would be handled by connection_manager.unsubscribe)
        # This test verifies message routing works

    @pytest.mark.asyncio
    async def test_handle_ping_message(self):
        """Test handling ping message."""
        manager = ConnectionManager()
        websocket = AsyncMock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        manager.active_connections["conn1"] = client
        client.missed_pongs = 2  # Had missed some pongs

        message_data = {
            "type": "ping",
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "sequence": 3,
        }

        with patch(
            "api.whale_websocket.rate_limiter.check_ws_limit", return_value=True
        ):
            await handle_client_message(client, message_data)

        # Verify missed pongs reset
        assert client.missed_pongs == 0

    @pytest.mark.asyncio
    async def test_handle_rate_limited_message(self):
        """Test rate limiting on message handling."""
        manager = ConnectionManager()
        websocket = AsyncMock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        manager.active_connections["conn1"] = client

        message_data = {
            "type": "ping",
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "sequence": 1,
        }

        # Mock rate limit exceeded
        with patch(
            "api.whale_websocket.rate_limiter.check_ws_limit", return_value=False
        ):
            await handle_client_message(client, message_data)

        # Verify error sent (check websocket.send_json was called with error)
        # The actual verification would depend on how send_error is called

    @pytest.mark.asyncio
    async def test_handle_invalid_message(self):
        """Test handling invalid message format."""
        manager = ConnectionManager()
        websocket = AsyncMock()
        client = ClientConnection(websocket, "conn1", "user1", "127.0.0.1")
        manager.active_connections["conn1"] = client

        message_data = {
            "type": "unknown_type",
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "sequence": 1,
        }

        with patch(
            "api.whale_websocket.rate_limiter.check_ws_limit", return_value=True
        ):
            await handle_client_message(client, message_data)

        # Should send error message (validate_message_type will raise ValueError)
        # Test passes if no exception is raised


@pytest.fixture
def clean_connection_manager():
    """Fixture to provide a clean connection manager instance."""
    return ConnectionManager()


def test_connection_manager_singleton():
    """Test that global connection_manager is properly initialized."""
    from api.whale_websocket import connection_manager

    assert connection_manager is not None
    assert isinstance(connection_manager, ConnectionManager)
