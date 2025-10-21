"""
Test graceful ZMQ reconnection on Bitcoin Core disconnection.

Tests T095 requirement: System must gracefully handle Bitcoin Core disconnects.
"""

import pytest
from live.backend.zmq_listener import ZMQListener


@pytest.mark.asyncio
async def test_zmq_connection_status_tracking():
    """
    Test that is_connected property tracks connection state correctly.

    Should be False initially, True after connect, False after disconnect.
    """
    listener = ZMQListener()

    # Initially not connected
    assert not listener.is_connected, "Should not be connected initially"

    # After connect, should be connected
    await listener.connect()
    assert listener.is_connected, "Should be connected after connect()"

    # After disconnect, should not be connected
    await listener.disconnect()
    assert not listener.is_connected, "Should not be connected after disconnect()"
