#!/usr/bin/env python3
"""
Reconnection Manager with Exponential Backoff
Task T010+: Automatic reconnection for external services

Provides production-ready reconnection logic with:
- Exponential backoff with jitter
- Maximum retry attempts
- Circuit breaker pattern
- Connection health tracking
- Graceful degradation
"""

import asyncio
import logging
import random
from typing import Optional, Callable, Any, Dict
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    """Connection state"""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"  # Circuit breaker open


@dataclass
class ConnectionStats:
    """Connection statistics for monitoring"""

    total_connections: int = 0
    total_disconnections: int = 0
    total_reconnections: int = 0
    failed_attempts: int = 0
    current_state: ConnectionState = ConnectionState.DISCONNECTED
    last_connected_at: Optional[datetime] = None
    last_disconnected_at: Optional[datetime] = None
    last_error: Optional[str] = None


class ReconnectionManager:
    """
    Manages automatic reconnection with exponential backoff

    Features:
    - Exponential backoff with jitter to prevent thundering herd
    - Circuit breaker pattern after max failures
    - Connection health tracking
    - Async-first design

    Example:
        async def connect_to_service():
            session = aiohttp.ClientSession()
            response = await session.get("http://localhost:3001/blocks/tip/height")
            return session

        manager = ReconnectionManager(
            name="electrs",
            connect_func=connect_to_service,
            max_attempts=10,
            base_delay=2.0,
            max_delay=60.0
        )

        connection = await manager.connect_with_retry()
    """

    def __init__(
        self,
        name: str,
        connect_func: Callable[[], Any],
        disconnect_func: Optional[Callable[[Any], None]] = None,
        max_attempts: int = 10,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        circuit_breaker_threshold: int = 5,
    ):
        """
        Initialize reconnection manager

        Args:
            name: Connection name (for logging)
            connect_func: Async function that establishes connection
            disconnect_func: Optional async function to clean up connection
            max_attempts: Maximum reconnection attempts (0 = infinite)
            base_delay: Base delay in seconds (exponentially increased)
            max_delay: Maximum delay in seconds
            jitter: Add random jitter to prevent thundering herd
            circuit_breaker_threshold: Consecutive failures before opening circuit
        """
        self.name = name
        self.connect_func = connect_func
        self.disconnect_func = disconnect_func
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.circuit_breaker_threshold = circuit_breaker_threshold

        # State
        self.stats = ConnectionStats()
        self.connection: Optional[Any] = None
        self.consecutive_failures = 0
        self._reconnect_task: Optional[asyncio.Task] = None

    def _calculate_backoff(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay with optional jitter

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff: base_delay * 2^attempt
        delay = min(self.base_delay * (2**attempt), self.max_delay)

        # Add jitter (±25% of delay)
        if self.jitter:
            jitter_amount = delay * 0.25
            delay += random.uniform(-jitter_amount, jitter_amount)

        return max(0.1, delay)  # Minimum 100ms

    async def connect_with_retry(self) -> Optional[Any]:
        """
        Attempt connection with exponential backoff retry

        Returns:
            Connection object if successful, None if all attempts failed
        """
        attempt = 0

        while True:
            # Check circuit breaker
            if self.consecutive_failures >= self.circuit_breaker_threshold:
                self.stats.current_state = ConnectionState.FAILED
                logger.error(
                    f"{self.name}: Circuit breaker open "
                    f"({self.consecutive_failures} consecutive failures)"
                )
                return None

            # Check max attempts
            if self.max_attempts > 0 and attempt >= self.max_attempts:
                logger.error(
                    f"{self.name}: Max reconnection attempts ({self.max_attempts}) reached"
                )
                self.stats.current_state = ConnectionState.FAILED
                return None

            try:
                # Update state
                self.stats.current_state = ConnectionState.RECONNECTING
                logger.info(
                    f"{self.name}: Connection attempt {attempt + 1}"
                    + (f"/{self.max_attempts}" if self.max_attempts > 0 else "")
                )

                # Attempt connection
                self.connection = await self.connect_func()

                # Success!
                self.stats.total_connections += 1
                self.stats.current_state = ConnectionState.CONNECTED
                self.stats.last_connected_at = datetime.now(timezone.utc)
                self.consecutive_failures = 0

                if attempt > 0:
                    self.stats.total_reconnections += 1
                    logger.info(f"{self.name}: Reconnected after {attempt} attempts")
                else:
                    logger.info(f"{self.name}: Connected successfully")

                return self.connection

            except Exception as e:
                # Connection failed
                self.consecutive_failures += 1
                self.stats.failed_attempts += 1
                self.stats.last_error = str(e)

                logger.warning(
                    f"{self.name}: Connection failed (attempt {attempt + 1}): {e}"
                )

                # Calculate backoff delay
                delay = self._calculate_backoff(attempt)

                # Check if we should retry
                if self.max_attempts > 0 and attempt + 1 >= self.max_attempts:
                    logger.error(f"{self.name}: Giving up after {attempt + 1} attempts")
                    break

                # Wait before retry
                logger.info(f"{self.name}: Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)

                attempt += 1

        # All attempts failed
        self.stats.current_state = ConnectionState.FAILED
        return None

    async def disconnect(self):
        """Gracefully disconnect from service"""
        if self.connection and self.disconnect_func:
            try:
                await self.disconnect_func(self.connection)
                logger.info(f"{self.name}: Disconnected")
            except Exception as e:
                logger.error(f"{self.name}: Error during disconnect: {e}")

        self.connection = None
        self.stats.current_state = ConnectionState.DISCONNECTED
        self.stats.total_disconnections += 1
        self.stats.last_disconnected_at = datetime.now(timezone.utc)

    async def maintain_connection(
        self,
        health_check_func: Optional[Callable[[Any], bool]] = None,
        health_check_interval: float = 30.0,
    ):
        """
        Maintain connection with automatic reconnection on failure

        This is a long-running task that monitors connection health
        and reconnects automatically if the connection is lost.

        Args:
            health_check_func: Optional async function to check connection health
            health_check_interval: Seconds between health checks

        Example:
            async def check_health(connection):
                try:
                    await connection.ping()
                    return True
                except:
                    return False

            await manager.maintain_connection(check_health, interval=30)
        """
        logger.info(
            f"{self.name}: Starting connection maintenance "
            f"(health check every {health_check_interval}s)"
        )

        while True:
            # Ensure connected
            if (
                not self.connection
                or self.stats.current_state != ConnectionState.CONNECTED
            ):
                logger.info(f"{self.name}: Connection lost, attempting reconnect...")
                await self.connect_with_retry()

                if not self.connection:
                    # Failed to reconnect - circuit breaker may be open
                    logger.error(
                        f"{self.name}: Unable to reconnect, waiting {self.max_delay}s..."
                    )
                    await asyncio.sleep(self.max_delay)
                    # Reset circuit breaker after cooldown
                    self.consecutive_failures = 0
                    continue

            # Perform health check
            if health_check_func:
                try:
                    is_healthy = await health_check_func(self.connection)
                    if not is_healthy:
                        logger.warning(f"{self.name}: Health check failed")
                        await self.disconnect()
                        continue
                except Exception as e:
                    logger.error(f"{self.name}: Health check error: {e}")
                    await self.disconnect()
                    continue

            # Wait before next check
            await asyncio.sleep(health_check_interval)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get connection statistics

        Returns:
            Dictionary with connection stats
        """
        uptime = None
        if self.stats.last_connected_at:
            uptime = (
                datetime.now(timezone.utc) - self.stats.last_connected_at
            ).total_seconds()

        return {
            "name": self.name,
            "state": self.stats.current_state,
            "total_connections": self.stats.total_connections,
            "total_disconnections": self.stats.total_disconnections,
            "total_reconnections": self.stats.total_reconnections,
            "failed_attempts": self.stats.failed_attempts,
            "consecutive_failures": self.consecutive_failures,
            "last_connected_at": self.stats.last_connected_at.isoformat()
            if self.stats.last_connected_at
            else None,
            "last_disconnected_at": self.stats.last_disconnected_at.isoformat()
            if self.stats.last_disconnected_at
            else None,
            "uptime_seconds": uptime,
            "last_error": self.stats.last_error,
            "circuit_breaker_open": self.consecutive_failures
            >= self.circuit_breaker_threshold,
        }

    def is_connected(self) -> bool:
        """Check if currently connected"""
        return self.stats.current_state == ConnectionState.CONNECTED

    def reset_circuit_breaker(self):
        """Manually reset circuit breaker"""
        logger.info(f"{self.name}: Circuit breaker reset")
        self.consecutive_failures = 0
        if self.stats.current_state == ConnectionState.FAILED:
            self.stats.current_state = ConnectionState.DISCONNECTED


# Example usage and testing
if __name__ == "__main__":
    import aiohttp

    async def test_reconnection_manager():
        print("🔄 Reconnection Manager Test Suite")
        print("=" * 60)

        # Test 1: Successful connection
        print("\n✅ Test 1: Successful connection to Electrs")

        async def connect_electrs():
            """Connect to local Electrs"""
            session = aiohttp.ClientSession()
            try:
                async with session.get(
                    "http://localhost:3001/blocks/tip/height",
                    timeout=aiohttp.ClientTimeout(total=5.0),
                ) as response:
                    if response.status == 200:
                        height = await response.text()
                        print(f"   Connected! Block height: {height.strip()}")
                        return session
                    else:
                        await session.close()
                        raise ConnectionError(f"HTTP {response.status}")
            except Exception as e:
                await session.close()
                raise e

        async def disconnect_electrs(session):
            """Disconnect from Electrs"""
            await session.close()

        manager = ReconnectionManager(
            name="electrs",
            connect_func=connect_electrs,
            disconnect_func=disconnect_electrs,
            max_attempts=3,
            base_delay=1.0,
            max_delay=5.0,
        )

        connection = await manager.connect_with_retry()
        if connection:
            print("   ✅ Connection established")
            stats = manager.get_stats()
            print(
                f"   Stats: {stats['state']}, {stats['total_connections']} connections"
            )
            await manager.disconnect()
        else:
            print("   ❌ Failed to connect")

        # Test 2: Failed connection with backoff
        print("\n❌ Test 2: Failed connection with exponential backoff")

        async def connect_fail():
            """Always fails"""
            print("   Attempting connection...")
            raise ConnectionError("Simulated connection failure")

        fail_manager = ReconnectionManager(
            name="failing-service",
            connect_func=connect_fail,
            max_attempts=4,
            base_delay=0.5,
            max_delay=5.0,
        )

        fail_connection = await fail_manager.connect_with_retry()
        if not fail_connection:
            print("   ✅ Correctly failed after max attempts")
            stats = fail_manager.get_stats()
            print(
                f"   Stats: {stats['state']}, {stats['failed_attempts']} failed attempts"
            )

        # Test 3: Circuit breaker
        print("\n⚡ Test 3: Circuit breaker after consecutive failures")

        attempt_count = 0

        async def connect_flaky():
            """Fails first few times"""
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 6:
                raise ConnectionError(f"Attempt {attempt_count} failed")
            return "connected"

        circuit_manager = ReconnectionManager(
            name="flaky-service",
            connect_func=connect_flaky,
            max_attempts=10,
            base_delay=0.2,
            circuit_breaker_threshold=5,
        )

        circuit_connection = await circuit_manager.connect_with_retry()
        stats = circuit_manager.get_stats()
        print(f"   Circuit breaker open: {stats['circuit_breaker_open']}")
        print(f"   Consecutive failures: {stats['consecutive_failures']}")
        if stats["circuit_breaker_open"]:
            print("   ✅ Circuit breaker correctly opened")

        # Test 4: Backoff calculation
        print("\n📊 Test 4: Exponential backoff calculation")
        test_manager = ReconnectionManager(
            name="test", connect_func=lambda: None, base_delay=2.0, max_delay=60.0
        )
        for i in range(6):
            delay = test_manager._calculate_backoff(i)
            print(f"   Attempt {i + 1}: {delay:.2f}s delay")

        print("\n✅ All reconnection manager tests completed!")

    # Run tests
    asyncio.run(test_reconnection_manager())
