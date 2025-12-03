"""
WebSocket endpoint and connection manager for Whale Detection Dashboard.
Tasks T021-T025: WebSocket foundation with client tracking and message routing.
"""

import asyncio
import time
import uuid
from typing import Dict, Set, Optional, List, Any
from datetime import datetime, timezone
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect, Query
from fastapi.websockets import WebSocketState

from api.config import setup_logging
from api.whale_auth import validate_websocket_token
from api.whale_security import rate_limiter
from api.models.websocket import (
    SubscribeMessage,
    UnsubscribeMessage,
    PingMessage,
    HistoricalRequestMessage,
    ConnectionAck,
    ErrorMessage,
    ErrorData,
    PongMessage,
    validate_message_type,
)

# Set up module logger
logger = setup_logging(__name__)


class ClientConnection:
    """Represents a single WebSocket client connection."""

    def __init__(
        self,
        websocket: WebSocket,
        connection_id: str,
        user_id: str,
        client_ip: str,
    ):
        self.websocket = websocket
        self.connection_id = connection_id
        self.user_id = user_id
        self.client_ip = client_ip
        self.connected_at = datetime.now(timezone.utc)
        self.last_activity = time.time()
        self.subscribed_channels: Set[str] = set()
        self.filters: Dict[str, Any] = {}
        self.message_sequence = 0
        self.ping_count = 0
        self.missed_pongs = 0

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = time.time()

    def get_next_sequence(self) -> int:
        """Get next message sequence number."""
        self.message_sequence += 1
        return self.message_sequence

    def is_subscribed_to(self, channel: str) -> bool:
        """Check if client is subscribed to a channel."""
        return channel in self.subscribed_channels

    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection metadata."""
        return {
            "connection_id": self.connection_id,
            "user_id": self.user_id,
            "client_ip": self.client_ip,
            "connected_at": self.connected_at.isoformat(),
            "subscribed_channels": list(self.subscribed_channels),
            "message_count": self.message_sequence,
            "missed_pongs": self.missed_pongs,
        }


class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.
    Task T022: Connection manager with client tracking.
    """

    def __init__(self):
        # Active connections by connection_id
        self.active_connections: Dict[str, ClientConnection] = {}

        # Channel subscriptions (channel -> set of connection_ids)
        self.channel_subscriptions: Dict[str, Set[str]] = defaultdict(set)

        # User connections (user_id -> set of connection_ids)
        self.user_connections: Dict[str, Set[str]] = defaultdict(set)

        # Heartbeat task
        self.heartbeat_task: Optional[asyncio.Task] = None

        logger.info("Connection manager initialized")

    async def connect(
        self,
        websocket: WebSocket,
        token: str,
        client_ip: str,
    ) -> Optional[ClientConnection]:
        """
        Accept WebSocket connection with authentication.
        Task T021: WebSocket endpoint with token validation.

        Args:
            websocket: FastAPI WebSocket instance
            token: JWT token from query parameter
            client_ip: Client IP address

        Returns:
            ClientConnection if successful, None if rejected
        """
        # Validate token
        is_valid, user_data = await validate_websocket_token(websocket, token)
        if not is_valid:
            logger.warning(f"Connection rejected: invalid token from {client_ip}")
            return None

        # Accept connection
        await websocket.accept()

        # Create connection
        connection_id = str(uuid.uuid4())
        user_id = user_data.get("user_id", "unknown")

        client = ClientConnection(
            websocket=websocket,
            connection_id=connection_id,
            user_id=user_id,
            client_ip=client_ip,
        )

        # Register connection
        self.active_connections[connection_id] = client
        self.user_connections[user_id].add(connection_id)

        logger.info(
            f"Client connected: {connection_id} (user: {user_id}, ip: {client_ip})"
        )

        # Send connection acknowledgment
        await self.send_ack(client, subscribed_channels=[])

        return client

    async def disconnect(self, connection_id: str):
        """
        Handle client disconnection and cleanup.

        Args:
            connection_id: Connection identifier
        """
        client = self.active_connections.get(connection_id)
        if not client:
            return

        # Remove from all subscriptions
        for channel in list(client.subscribed_channels):
            self.channel_subscriptions[channel].discard(connection_id)
            if not self.channel_subscriptions[channel]:
                del self.channel_subscriptions[channel]

        # Remove from user connections
        self.user_connections[client.user_id].discard(connection_id)
        if not self.user_connections[client.user_id]:
            del self.user_connections[client.user_id]

        # Remove connection
        del self.active_connections[connection_id]

        logger.info(
            f"Client disconnected: {connection_id} "
            f"(duration: {time.time() - client.last_activity:.1f}s)"
        )

    async def subscribe(self, connection_id: str, channels: List[str]):
        """
        Subscribe client to channels.

        Args:
            connection_id: Connection identifier
            channels: List of channel names to subscribe
        """
        client = self.active_connections.get(connection_id)
        if not client:
            return

        for channel in channels:
            client.subscribed_channels.add(channel)
            self.channel_subscriptions[channel].add(connection_id)

        logger.info(f"Client {connection_id} subscribed to: {channels}")

        # Send acknowledgment
        await self.send_ack(client, list(client.subscribed_channels))

    async def unsubscribe(self, connection_id: str, channels: List[str]):
        """
        Unsubscribe client from channels.

        Args:
            connection_id: Connection identifier
            channels: List of channel names to unsubscribe
        """
        client = self.active_connections.get(connection_id)
        if not client:
            return

        for channel in channels:
            client.subscribed_channels.discard(channel)
            self.channel_subscriptions[channel].discard(connection_id)

            # Clean up empty channel subscriptions
            if not self.channel_subscriptions[channel]:
                del self.channel_subscriptions[channel]

        logger.info(f"Client {connection_id} unsubscribed from: {channels}")

        # Send acknowledgment
        await self.send_ack(client, list(client.subscribed_channels))

    async def send_personal_message(self, connection_id: str, message: Dict[str, Any]):
        """
        Send message to specific client.

        Args:
            connection_id: Connection identifier
            message: Message dictionary
        """
        client = self.active_connections.get(connection_id)
        if not client:
            return

        try:
            # Add sequence number
            message["sequence"] = client.get_next_sequence()
            message["timestamp"] = int(datetime.now(timezone.utc).timestamp() * 1000)

            await client.websocket.send_json(message)
            client.update_activity()

        except Exception as e:
            logger.error(f"Failed to send message to {connection_id}: {e}")
            await self.disconnect(connection_id)

    async def broadcast_to_channel(self, channel: str, message: Dict[str, Any]):
        """
        Broadcast message to all clients subscribed to a channel.

        Args:
            channel: Channel name
            message: Message dictionary
        """
        connection_ids = self.channel_subscriptions.get(channel, set())

        if not connection_ids:
            return

        logger.debug(
            f"Broadcasting to channel {channel}: {len(connection_ids)} clients"
        )

        # Send to all subscribers
        tasks = [
            self.send_personal_message(conn_id, message.copy())
            for conn_id in connection_ids
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def send_ack(self, client: ClientConnection, subscribed_channels: List[str]):
        """
        Send connection acknowledgment message.

        Args:
            client: Client connection
            subscribed_channels: List of subscribed channels
        """
        ack_message = ConnectionAck(
            type="ack",
            timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
            sequence=client.get_next_sequence(),
            request_sequence=0,
            status="success",
            subscribed_channels=subscribed_channels,
            server_time=int(time.time() * 1000),
        )

        await client.websocket.send_json(ack_message.model_dump())
        client.update_activity()

    async def send_error(
        self,
        client: ClientConnection,
        code: str,
        message: str,
        retry_after: Optional[int] = None,
    ):
        """
        Send error message to client.

        Args:
            client: Client connection
            code: Error code
            message: Error description
            retry_after: Optional retry delay in seconds
        """
        error_msg = ErrorMessage(
            type="error",
            timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
            sequence=client.get_next_sequence(),
            error=ErrorData(code=code, message=message, retry_after=retry_after),
        )

        await client.websocket.send_json(error_msg.model_dump())
        client.update_activity()

    async def send_pong(self, client: ClientConnection, ping_sequence: int):
        """
        Send pong response to ping.
        Task T024: Ping/pong heartbeat mechanism.

        Args:
            client: Client connection
            ping_sequence: Sequence number from ping message
        """
        pong_message = PongMessage(
            type="pong",
            timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
            sequence=client.get_next_sequence(),
            ping_sequence=ping_sequence,
            server_time=int(time.time() * 1000),
        )

        await client.websocket.send_json(pong_message.model_dump())
        client.update_activity()

    async def heartbeat_monitor(self):
        """
        Monitor connections with periodic ping checks.
        Task T024: Heartbeat mechanism (30s interval, 3 missed = disconnect).
        """
        logger.info("Heartbeat monitor started")

        while True:
            await asyncio.sleep(30)  # Check every 30 seconds

            disconnected = []

            for connection_id, client in list(self.active_connections.items()):
                # Check if client missed too many pongs
                if client.missed_pongs >= 3:
                    logger.warning(
                        f"Client {connection_id} missed 3 pongs, disconnecting"
                    )
                    disconnected.append(connection_id)
                    continue

                # Check last activity
                idle_time = time.time() - client.last_activity
                if idle_time > 90:  # 90 seconds without activity
                    logger.info(
                        f"Client {connection_id} idle for {idle_time:.1f}s, disconnecting"
                    )
                    disconnected.append(connection_id)

            # Disconnect idle/unresponsive clients
            for connection_id in disconnected:
                client = self.active_connections.get(connection_id)
                if client and client.websocket.client_state == WebSocketState.CONNECTED:
                    try:
                        await client.websocket.close(
                            code=1000, reason="Heartbeat timeout"
                        )
                    except Exception:
                        pass
                await self.disconnect(connection_id)

    def start_heartbeat_monitor(self):
        """Start the heartbeat monitoring task."""
        if not self.heartbeat_task:
            self.heartbeat_task = asyncio.create_task(self.heartbeat_monitor())
            logger.info("Heartbeat monitor task started")

    def get_stats(self) -> Dict[str, Any]:
        """Get connection manager statistics."""
        return {
            "total_connections": len(self.active_connections),
            "total_users": len(self.user_connections),
            "total_channels": len(self.channel_subscriptions),
            "channels": {
                channel: len(subs)
                for channel, subs in self.channel_subscriptions.items()
            },
        }


# Global connection manager instance
connection_manager = ConnectionManager()


async def handle_client_message(client: ClientConnection, data: Dict[str, Any]):
    """
    Route and handle incoming client messages.
    Task T025: Message router for client messages.

    Args:
        client: Client connection
        data: Raw message data
    """
    # Check rate limit
    if not await rate_limiter.check_ws_limit(client.connection_id):
        await connection_manager.send_error(
            client,
            code="RATE_LIMIT_EXCEEDED",
            message="Too many messages, please slow down",
            retry_after=5,
        )
        return

    try:
        # Validate message format
        message = validate_message_type(data)

        # Route message by type
        if isinstance(message, SubscribeMessage):
            await connection_manager.subscribe(client.connection_id, message.channels)

        elif isinstance(message, UnsubscribeMessage):
            await connection_manager.unsubscribe(client.connection_id, message.channels)

        elif isinstance(message, PingMessage):
            await connection_manager.send_pong(client, message.sequence)
            client.missed_pongs = 0  # Reset missed pong counter

        elif isinstance(message, HistoricalRequestMessage):
            # TODO: Implement historical data request handler (Phase 7)
            logger.info(
                f"Historical request from {client.connection_id}: {message.data_type}"
            )

        else:
            logger.warning(f"Unknown message type from {client.connection_id}")

        client.update_activity()

    except ValueError as e:
        logger.error(f"Invalid message from {client.connection_id}: {e}")
        await connection_manager.send_error(
            client, code="INVALID_MESSAGE", message=str(e)
        )

    except Exception as e:
        logger.error(f"Error handling message from {client.connection_id}: {e}")
        await connection_manager.send_error(
            client, code="INTERNAL_ERROR", message="Failed to process message"
        )


async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT authentication token"),
):
    """
    WebSocket endpoint for whale alerts.
    Task T021: FastAPI WebSocket endpoint /ws/whale-alerts.

    Connection URL: wss://host/ws/whale-alerts?token=<jwt_token>

    Args:
        websocket: FastAPI WebSocket connection
        token: JWT token from query parameter
    """
    # Get client IP
    client_ip = websocket.client.host if websocket.client else "unknown"

    # Check connection attempt rate limit
    if not rate_limiter.check_connection_attempt(client_ip):
        logger.warning(f"Connection attempt rate limit exceeded for {client_ip}")
        await websocket.close(code=1008, reason="Too many connection attempts")
        return

    # Establish connection
    client = await connection_manager.connect(websocket, token, client_ip)
    if not client:
        return  # Connection rejected (invalid token)

    try:
        # Message receive loop
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            # Handle message
            await handle_client_message(client, data)

    except WebSocketDisconnect:
        logger.info(f"Client {client.connection_id} disconnected normally")
        await connection_manager.disconnect(client.connection_id)

    except Exception as e:
        logger.error(f"WebSocket error for {client.connection_id}: {e}")
        await connection_manager.disconnect(client.connection_id)
