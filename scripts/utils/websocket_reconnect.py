#!/usr/bin/env python3
"""
WebSocket Reconnection Utility with Exponential Backoff
Task: P1 - Resilience improvement

Features:
- Exponential backoff with configurable max delay
- Jitter to avoid thundering herd
- Connection state tracking
- Health monitoring
- Automatic recovery on connection restored

Usage:
    from scripts.utils.websocket_reconnect import WebSocketReconnector

    async def on_connect(ws):
        print("Connected!")
        # Your WebSocket handling logic here

    reconnector = WebSocketReconnector(
        url="ws://localhost:8999/ws",
        on_connect_callback=on_connect,
        max_retries=None,  # Infinite retries
        initial_delay=1.0,
        max_delay=30.0
    )

    await reconnector.start()
"""

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable, Awaitable

try:
    import websockets
    from websockets.exceptions import WebSocketException

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    logging.warning("websockets library not available - reconnection utility disabled")


logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    """WebSocket connection states"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass
class ReconnectionStats:
    """Statistics for reconnection attempts"""

    total_attempts: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    current_streak: int = 0  # Current consecutive failures
    max_streak: int = 0  # Max consecutive failures
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    total_uptime_seconds: float = 0.0
    connection_start: Optional[datetime] = None


class WebSocketReconnector:
    """
    WebSocket client with automatic reconnection and exponential backoff.

    Implements resilient connection management following Gemini recommendation.
    """

    def __init__(
        self,
        url: str,
        on_connect_callback: Callable[[any], Awaitable[None]],
        on_disconnect_callback: Optional[Callable[[], Awaitable[None]]] = None,
        max_retries: Optional[int] = None,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_multiplier: float = 2.0,
        jitter: bool = True,
    ):
        """
        Initialize WebSocket reconnector.

        Args:
            url: WebSocket URL to connect to
            on_connect_callback: Async function called when connection established
            on_disconnect_callback: Optional async function called on disconnect
            max_retries: Maximum retry attempts (None = infinite)
            initial_delay: Initial backoff delay in seconds
            max_delay: Maximum backoff delay in seconds
            backoff_multiplier: Exponential backoff multiplier
            jitter: Add random jitter to backoff delays
        """
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError("websockets library required for WebSocketReconnector")

        self.url = url
        self.on_connect_callback = on_connect_callback
        self.on_disconnect_callback = on_disconnect_callback
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter

        self.state = ConnectionState.DISCONNECTED
        self.stats = ReconnectionStats()
        self._stop_event = asyncio.Event()
        self._websocket: Optional[any] = None
        self._current_delay = initial_delay

    @property
    def is_connected(self) -> bool:
        """Check if currently connected"""
        return self.state == ConnectionState.CONNECTED

    @property
    def uptime_seconds(self) -> float:
        """Get current connection uptime"""
        if self.stats.connection_start and self.state == ConnectionState.CONNECTED:
            return (
                datetime.now(timezone.utc) - self.stats.connection_start
            ).total_seconds()
        return 0.0

    def _calculate_backoff_delay(self) -> float:
        """Calculate next backoff delay with exponential growth and optional jitter"""
        delay = min(self._current_delay, self.max_delay)

        if self.jitter:
            # Add ±20% random jitter to avoid thundering herd
            jitter_amount = delay * 0.2
            delay += random.uniform(-jitter_amount, jitter_amount)

        # Exponential growth for next attempt
        self._current_delay = min(
            self._current_delay * self.backoff_multiplier, self.max_delay
        )

        return max(0.0, delay)  # Ensure non-negative

    def _reset_backoff(self):
        """Reset backoff delay after successful connection"""
        self._current_delay = self.initial_delay
        self.stats.current_streak = 0

    async def _connect(self) -> bool:
        """
        Attempt to establish WebSocket connection.

        Returns:
            bool: True if connection successful, False otherwise
        """
        self.state = ConnectionState.CONNECTING
        self.stats.total_attempts += 1

        try:
            logger.info(
                f"Connecting to {self.url} (attempt {self.stats.total_attempts})"
            )

            self._websocket = await websockets.connect(
                self.url,
                ping_interval=20,  # Send ping every 20 seconds
                ping_timeout=10,  # Wait 10 seconds for pong
            )

            self.state = ConnectionState.CONNECTED
            self.stats.successful_connections += 1
            self.stats.last_success = datetime.now(timezone.utc)
            self.stats.connection_start = datetime.now(timezone.utc)
            self._reset_backoff()

            logger.info(f"✅ Connected to {self.url}")

            # Call user's on_connect callback
            if self.on_connect_callback:
                await self.on_connect_callback(self._websocket)

            return True

        except Exception as e:
            self.state = ConnectionState.DISCONNECTED
            self.stats.failed_connections += 1
            self.stats.last_failure = datetime.now(timezone.utc)
            self.stats.current_streak += 1
            self.stats.max_streak = max(
                self.stats.max_streak, self.stats.current_streak
            )

            logger.error(f"❌ Connection failed: {e}")
            return False

    async def _handle_disconnection(self):
        """Handle disconnection and update stats"""
        if self.stats.connection_start:
            uptime = (
                datetime.now(timezone.utc) - self.stats.connection_start
            ).total_seconds()
            self.stats.total_uptime_seconds += uptime
            self.stats.connection_start = None

        logger.warning(f"Disconnected from {self.url}")

        # Call user's on_disconnect callback
        if self.on_disconnect_callback:
            try:
                await self.on_disconnect_callback()
            except Exception as e:
                logger.error(f"Error in disconnect callback: {e}")

    async def start(self):
        """
        Start the reconnection loop.

        This will attempt to connect and automatically reconnect on failures.
        Runs until stop() is called or max_retries is exceeded.
        """
        attempt = 0

        while not self._stop_event.is_set():
            # Check max retries
            if self.max_retries is not None and attempt >= self.max_retries:
                self.state = ConnectionState.FAILED
                logger.error(f"❌ Max retries ({self.max_retries}) exceeded")
                break

            # Attempt connection
            success = await self._connect()

            if success:
                # Connection successful - reset attempt counter
                attempt = 0

                try:
                    # Wait for disconnection (blocks until connection lost)
                    await self._websocket.wait_closed()
                except Exception as e:
                    logger.error(f"WebSocket error: {e}")

                await self._handle_disconnection()

            if self._stop_event.is_set():
                break

            # Connection failed or disconnected - wait before retry
            self.state = ConnectionState.RECONNECTING
            delay = self._calculate_backoff_delay()

            logger.info(
                f"Reconnecting in {delay:.1f}s "
                f"(attempt {attempt + 1}, streak {self.stats.current_streak})"
            )

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                # If we reach here, stop was called
                break
            except asyncio.TimeoutError:
                # Timeout is expected - continue to next attempt
                pass

            attempt += 1

        logger.info("Reconnection loop stopped")

    async def stop(self):
        """Stop the reconnection loop and close connection"""
        logger.info("Stopping WebSocket reconnector...")
        self._stop_event.set()

        if self._websocket and self.state == ConnectionState.CONNECTED:
            try:
                await self._websocket.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")

        self.state = ConnectionState.DISCONNECTED

    def get_stats(self) -> dict:
        """Get reconnection statistics as dictionary"""
        return {
            "state": self.state.value,
            "total_attempts": self.stats.total_attempts,
            "successful_connections": self.stats.successful_connections,
            "failed_connections": self.stats.failed_connections,
            "current_failure_streak": self.stats.current_streak,
            "max_failure_streak": self.stats.max_streak,
            "last_success": self.stats.last_success.isoformat()
            if self.stats.last_success
            else None,
            "last_failure": self.stats.last_failure.isoformat()
            if self.stats.last_failure
            else None,
            "total_uptime_seconds": self.stats.total_uptime_seconds,
            "current_uptime_seconds": self.uptime_seconds,
            "success_rate": (
                self.stats.successful_connections / self.stats.total_attempts * 100
                if self.stats.total_attempts > 0
                else 0
            ),
        }


# Example usage
if __name__ == "__main__":

    async def handle_connection(ws):
        """Example connection handler"""
        print("✅ Connected! Waiting for messages...")
        try:
            async for message in ws:
                print(f"Received: {message[:100]}...")
        except Exception as e:
            print(f"Error receiving messages: {e}")

    async def handle_disconnection():
        """Example disconnection handler"""
        print("❌ Disconnected! Will retry...")

    async def main():
        reconnector = WebSocketReconnector(
            url="ws://localhost:8999/ws",
            on_connect_callback=handle_connection,
            on_disconnect_callback=handle_disconnection,
            max_retries=None,  # Infinite retries
            initial_delay=1.0,
            max_delay=30.0,
        )

        try:
            await reconnector.start()
        except KeyboardInterrupt:
            print("\nStopping...")
            await reconnector.stop()
            print("Stats:", reconnector.get_stats())

    asyncio.run(main())
