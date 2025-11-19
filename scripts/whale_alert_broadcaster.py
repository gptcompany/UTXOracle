#!/usr/bin/env python3
"""
Whale Alert Broadcaster with Authentication
WebSocket server that broadcasts whale alerts to authenticated clients

Part of Task T018b: Token validation middleware implementation
"""

import asyncio
import json
import logging
import websockets
from datetime import datetime, timezone
from typing import Set, Dict, Optional
from dataclasses import dataclass, asdict
import sys
from pathlib import Path

# Add auth module to path
sys.path.append(str(Path(__file__).parent))
from auth.websocket_auth import WebSocketAuthenticator, AuthToken

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class WhaleAlert:
    """Represents a whale movement alert"""

    transaction_id: str
    flow_type: str  # inflow, outflow, internal, unknown
    btc_value: float
    fee_rate: float
    urgency_score: float
    detection_timestamp: str
    exchange_addresses: list
    confidence_score: float
    rbf_enabled: bool = False
    predicted_confirmation_block: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class WhaleAlertBroadcaster:
    """WebSocket server for broadcasting whale alerts with authentication"""

    def __init__(
        self, host: str = "localhost", port: int = 8765, auth_enabled: bool = True
    ):
        """
        Initialize the broadcaster

        Args:
            host: Host to bind to
            port: Port to bind to
            auth_enabled: Whether to require authentication (can disable for development)
        """
        self.host = host
        self.port = port
        self.auth_enabled = auth_enabled
        self.authenticator = WebSocketAuthenticator() if auth_enabled else None

        # Track connected clients with their auth tokens
        self.authenticated_clients: Dict[
            websockets.WebSocketServerProtocol, AuthToken
        ] = {}
        self.unauthenticated_clients: Set[websockets.WebSocketServerProtocol] = set()

        # Statistics
        self.stats = {
            "total_connections": 0,
            "authenticated_connections": 0,
            "alerts_broadcast": 0,
            "auth_failures": 0,
        }

    async def register_client(self, websocket, auth_token: Optional[AuthToken] = None):
        """Register a new client connection"""
        if auth_token:
            self.authenticated_clients[websocket] = auth_token
            self.stats["authenticated_connections"] += 1
            logger.info(
                f"Registered authenticated client {auth_token.client_id} from {websocket.remote_address}"
            )
        else:
            self.unauthenticated_clients.add(websocket)
            logger.info(
                f"Registered unauthenticated client from {websocket.remote_address}"
            )

        self.stats["total_connections"] += 1

    async def unregister_client(self, websocket):
        """Unregister a client connection"""
        if websocket in self.authenticated_clients:
            auth_token = self.authenticated_clients[websocket]
            del self.authenticated_clients[websocket]
            logger.info(f"Unregistered authenticated client {auth_token.client_id}")
        elif websocket in self.unauthenticated_clients:
            self.unauthenticated_clients.remove(websocket)
            logger.info(
                f"Unregistered unauthenticated client from {websocket.remote_address}"
            )

    async def handle_client_with_auth(self, websocket, path):
        """Handle authenticated client connections"""
        auth_token = None

        try:
            # Authenticate the client
            if self.auth_enabled:
                auth_token = await self.authenticator.authenticate_websocket(
                    websocket, path
                )
                if not auth_token:
                    self.stats["auth_failures"] += 1
                    logger.warning(
                        f"Authentication failed for {websocket.remote_address}"
                    )
                    await websocket.close(code=1008, reason="Authentication required")
                    return

            # Register the client
            await self.register_client(websocket, auth_token)

            # Send welcome message
            welcome_msg = {
                "type": "welcome",
                "message": "Connected to whale alert broadcaster",
                "authenticated": auth_token is not None,
                "client_id": auth_token.client_id if auth_token else None,
                "permissions": list(auth_token.permissions) if auth_token else [],
                "server_time": datetime.now(timezone.utc).isoformat(),
            }
            await websocket.send(json.dumps(welcome_msg))

            # Keep connection alive and handle messages
            async for message in websocket:
                try:
                    data = json.loads(message)

                    # Handle different message types
                    if data.get("type") == "ping":
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "pong",
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }
                            )
                        )

                    elif data.get("type") == "subscribe":
                        # Check permission for subscription changes
                        if auth_token and "write" in auth_token.permissions:
                            # Handle subscription logic here
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "subscribed",
                                        "filters": data.get("filters", {}),
                                    }
                                )
                            )
                        else:
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "error",
                                        "message": "Insufficient permissions for subscription changes",
                                    }
                                )
                            )

                    elif data.get("type") == "stats":
                        # Send current statistics
                        await websocket.send(
                            json.dumps({"type": "stats", "data": self.stats})
                        )

                except json.JSONDecodeError:
                    await websocket.send(
                        json.dumps({"type": "error", "message": "Invalid JSON"})
                    )
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    await websocket.send(
                        json.dumps({"type": "error", "message": str(e)})
                    )

        except websockets.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            # Unregister the client
            await self.unregister_client(websocket)

    async def broadcast_alert(self, alert: WhaleAlert):
        """
        Broadcast a whale alert to all authenticated clients

        Args:
            alert: WhaleAlert object to broadcast
        """
        if not self.authenticated_clients and not self.unauthenticated_clients:
            logger.debug("No clients connected, skipping broadcast")
            return

        # Prepare the message
        message = json.dumps(
            {
                "type": "whale_alert",
                "data": alert.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Send to authenticated clients
        if self.authenticated_clients:
            # Filter clients based on permissions
            disconnected = []
            for websocket, auth_token in self.authenticated_clients.items():
                try:
                    # Check if client has read permission
                    if "read" in auth_token.permissions:
                        await websocket.send(message)
                except websockets.ConnectionClosed:
                    disconnected.append(websocket)
                except Exception as e:
                    logger.error(
                        f"Error broadcasting to client {auth_token.client_id}: {e}"
                    )
                    disconnected.append(websocket)

            # Clean up disconnected clients
            for websocket in disconnected:
                await self.unregister_client(websocket)

        # Send to unauthenticated clients if auth is disabled
        if not self.auth_enabled and self.unauthenticated_clients:
            disconnected = []
            for websocket in self.unauthenticated_clients.copy():
                try:
                    await websocket.send(message)
                except websockets.ConnectionClosed:
                    disconnected.append(websocket)
                except Exception as e:
                    logger.error(f"Error broadcasting to unauthenticated client: {e}")
                    disconnected.append(websocket)

            # Clean up disconnected clients
            for websocket in disconnected:
                await self.unregister_client(websocket)

        self.stats["alerts_broadcast"] += 1
        logger.info(
            f"Broadcast whale alert to {len(self.authenticated_clients)} authenticated and {len(self.unauthenticated_clients)} unauthenticated clients"
        )

    async def start_server(self):
        """Start the WebSocket server"""
        logger.info(f"Starting whale alert broadcaster on ws://{self.host}:{self.port}")
        logger.info(
            f"Authentication: {'ENABLED' if self.auth_enabled else 'DISABLED (Development Mode)'}"
        )

        async with websockets.serve(self.handle_client_with_auth, self.host, self.port):
            logger.info(
                f"Whale alert broadcaster ready on ws://{self.host}:{self.port}"
            )
            await asyncio.Future()  # Run forever

    async def broadcast_test_alert(self):
        """Broadcast a test alert for development"""
        test_alert = WhaleAlert(
            transaction_id="test_tx_123456",
            flow_type="inflow",
            btc_value=150.5,
            fee_rate=25.0,
            urgency_score=0.75,
            detection_timestamp=datetime.now(timezone.utc).isoformat(),
            exchange_addresses=["bc1qtest...", "3Test..."],
            confidence_score=0.85,
            rbf_enabled=False,
            predicted_confirmation_block=850000,
        )

        await self.broadcast_alert(test_alert)
        logger.info("Test alert broadcast completed")


async def run_with_test_alerts():
    """Run server with periodic test alerts for development"""
    broadcaster = WhaleAlertBroadcaster(auth_enabled=False)  # Disable auth for testing

    # Start server
    server_task = asyncio.create_task(broadcaster.start_server())

    # Wait a bit for server to start
    await asyncio.sleep(2)

    # Send test alerts periodically
    try:
        while True:
            await asyncio.sleep(10)  # Send test alert every 10 seconds
            await broadcaster.broadcast_test_alert()
    except KeyboardInterrupt:
        logger.info("Shutting down...")


async def run_production_server():
    """Run production server with authentication enabled"""
    broadcaster = WhaleAlertBroadcaster(auth_enabled=True)
    await broadcaster.start_server()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Whale Alert Broadcaster")
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind to")
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable authentication (development only)",
    )
    parser.add_argument("--test", action="store_true", help="Run with test alerts")

    args = parser.parse_args()

    if args.test:
        # Run with test alerts (development mode)
        asyncio.run(run_with_test_alerts())
    else:
        # Run production server
        broadcaster = WhaleAlertBroadcaster(
            host=args.host, port=args.port, auth_enabled=not args.no_auth
        )
        asyncio.run(broadcaster.start_server())
