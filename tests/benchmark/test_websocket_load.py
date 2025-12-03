"""
WebSocket load test - verify server handles 100 concurrent clients.

Tests T097 requirement: System must handle 100 concurrent WebSocket connections.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock
from live.backend.api import DataStreamer
from live.shared.models import MempoolState


@pytest.mark.asyncio
@pytest.mark.slow
async def test_websocket_handles_100_concurrent_clients():
    """
    Test that DataStreamer handles 100 concurrent clients without crashes.

    REQUIREMENT: Server must support 100 concurrent connections with broadcast updates.

    Implementation: Tests DataStreamer broadcast logic directly without requiring
    a running server (faster, more reliable unit test).
    """
    num_clients = 100

    # Arrange: Create streamer and mock WebSocket clients
    streamer = DataStreamer(max_updates_per_second=0)  # Disable throttling

    # Create mock WebSocket connections
    mock_clients = []
    for i in range(num_clients):
        mock_ws = AsyncMock()
        mock_ws.send_text = AsyncMock()
        mock_clients.append(mock_ws)

    # Register all clients
    for mock_ws in mock_clients:
        await streamer.register_client(mock_ws)

    # Verify all clients registered
    assert streamer.get_client_count() == num_clients, (
        f"Expected {num_clients} clients registered"
    )

    # Act: Broadcast message to all clients
    state = MempoolState(
        price=113600.50,
        confidence=0.87,
        active_tx_count=1500,
        total_received=15000,
        total_filtered=10000,
        uptime_seconds=3600.0,
    )

    await streamer.broadcast(state)

    # Assert: All clients received the broadcast
    for i, mock_ws in enumerate(mock_clients):
        assert mock_ws.send_text.called, f"Client {i}: send_text not called"
        assert mock_ws.send_text.call_count == 1, f"Client {i}: Wrong call count"

        # Verify message structure
        call_args = mock_ws.send_text.call_args[0][0]
        assert isinstance(call_args, str), f"Client {i}: Message not a string"
        assert "type" in call_args, f"Client {i}: Missing 'type' field"
        assert "mempool_update" in call_args, f"Client {i}: Wrong message type"

    # Performance check: Broadcast should complete quickly
    # Even with 100 clients, should be <1 second
    start_time = asyncio.get_event_loop().time()
    await streamer.broadcast(state)
    elapsed = asyncio.get_event_loop().time() - start_time

    assert elapsed < 1.0, f"Broadcast took {elapsed:.2f}s (should be <1s)"


@pytest.mark.asyncio
async def test_websocket_load_with_disconnections():
    """
    Test that DataStreamer handles client disconnections gracefully during load.

    Simulates real-world scenario where some clients disconnect during operation.
    """
    num_clients = 50
    streamer = DataStreamer(max_updates_per_second=0)

    # Create mix of good and bad clients
    mock_clients = []
    for i in range(num_clients):
        mock_ws = AsyncMock()
        if i % 10 == 0:  # Every 10th client will fail
            mock_ws.send_text.side_effect = Exception("Connection lost")
        else:
            mock_ws.send_text = AsyncMock()
        mock_clients.append(mock_ws)
        await streamer.register_client(mock_ws)

    # Broadcast should not crash
    state = MempoolState(
        price=113600.50,
        confidence=0.87,
        active_tx_count=1500,
        total_received=15000,
        total_filtered=10000,
        uptime_seconds=3600.0,
    )

    await streamer.broadcast(state)

    # Failed clients should be removed
    expected_remaining = num_clients - (num_clients // 10)
    assert streamer.get_client_count() == expected_remaining, (
        f"Expected {expected_remaining} clients remaining after failures"
    )
