"""
Tests for ZMQ Listener (Module 1)

TDD Phase: RED - All tests must FAIL initially

Tasks:
- T020 [P]: test_zmq_connect_to_bitcoin_core, test_zmq_connection_status
- T021 [P]: test_zmq_stream_transactions (yields RawTransaction)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from live.backend.zmq_listener import ZMQListener
from live.shared.models import RawTransaction


# =============================================================================
# T020: ZMQ Connection Tests
# =============================================================================


@pytest.mark.asyncio
async def test_zmq_connect_to_bitcoin_core():
    """
    Test that ZMQListener can connect to Bitcoin Core ZMQ endpoint.

    Requirements:
    - Listener must connect to tcp://127.0.0.1:28332 (rawtx topic)
    - Connection must be established before streaming begins
    - Must handle connection errors gracefully

    Contract: ZMQListener.connect() -> None (raises exception on failure)
    """
    # Arrange: Mock ZMQ context and socket
    with patch("zmq.asyncio.Context") as mock_context:
        mock_socket = MagicMock()
        mock_context.return_value.socket.return_value = mock_socket

        listener = ZMQListener(tx_endpoint="tcp://127.0.0.1:28332")

        # Act: Connect to Bitcoin Core
        await listener.connect()

        # Assert: Socket was created and connected
        mock_context.return_value.socket.assert_called_once()
        mock_socket.connect.assert_called_once_with("tcp://127.0.0.1:28332")
        mock_socket.subscribe.assert_called_once_with(b"rawtx")


@pytest.mark.asyncio
async def test_zmq_connection_status():
    """
    Test that ZMQListener tracks connection status correctly.

    Requirements:
    - is_connected property must return False before connect()
    - is_connected property must return True after connect()
    - is_connected property must return False after disconnect()

    Contract: ZMQListener.is_connected -> bool
    """
    # Arrange: Create listener
    with patch("zmq.asyncio.Context"):
        listener = ZMQListener(tx_endpoint="tcp://127.0.0.1:28332")

        # Assert: Not connected initially
        assert not listener.is_connected, "Listener should not be connected initially"

        # Act: Connect
        await listener.connect()

        # Assert: Connected after connect()
        assert listener.is_connected, "Listener should be connected after connect()"

        # Act: Disconnect
        await listener.disconnect()

        # Assert: Not connected after disconnect()
        assert not listener.is_connected, (
            "Listener should not be connected after disconnect()"
        )


@pytest.mark.asyncio
async def test_zmq_connection_error_handling():
    """
    Test that ZMQListener handles connection errors gracefully.

    Requirements:
    - Must raise ConnectionError if Bitcoin Core is unreachable
    - Error message must be descriptive

    Contract: ZMQListener.connect() raises ConnectionError on failure
    """
    # Arrange: Mock ZMQ to raise connection error
    with patch("zmq.asyncio.Context") as mock_context:
        mock_socket = MagicMock()
        mock_socket.connect.side_effect = Exception("Connection refused")
        mock_context.return_value.socket.return_value = mock_socket

        listener = ZMQListener(tx_endpoint="tcp://127.0.0.1:28332")

        # Act & Assert: Connection should raise ConnectionError
        with pytest.raises(ConnectionError) as exc_info:
            await listener.connect()

        assert (
            "Connection refused" in str(exc_info.value).lower()
            or "failed" in str(exc_info.value).lower()
        )


# =============================================================================
# T021: Transaction Streaming Test
# =============================================================================


@pytest.mark.asyncio
async def test_zmq_stream_transactions():
    """
    Test that ZMQListener streams raw transactions as RawTransaction objects.

    Requirements:
    - stream_transactions() must be async generator yielding RawTransaction
    - Each transaction must have raw_bytes, timestamp, and topic='rawtx'
    - Must continue streaming until stopped
    - Timestamp must be accurate (within 1 second of now)

    Contract:
        async def stream_transactions() -> AsyncGenerator[RawTransaction, None]
    """
    # Arrange: Mock ZMQ socket to yield sample transactions
    with patch("zmq.asyncio.Context") as mock_context:
        mock_socket = AsyncMock()

        # Sample raw transaction bytes (minimal valid transaction)
        sample_tx_bytes = bytes.fromhex(
            "02000000"  # version
            "01"  # 1 input
            "0000000000000000000000000000000000000000000000000000000000000000ffffffff"  # prev tx + index
            "00"  # script sig length
            "ffffffff"  # sequence
            "02"  # 2 outputs
            "40420f0000000000"  # 1,000,000 satoshis
            "00"  # script pubkey length
            "80969800000000"  # 10,000,000 satoshis
            "00"  # script pubkey length
            "00000000"  # locktime
        )

        # Mock recv_multipart to return topic + transaction
        mock_socket.recv_multipart = AsyncMock(
            side_effect=[
                [b"rawtx", sample_tx_bytes],
                [b"rawtx", sample_tx_bytes],
                [b"rawtx", sample_tx_bytes],
            ]
        )

        mock_context.return_value.socket.return_value = mock_socket

        listener = ZMQListener(tx_endpoint="tcp://127.0.0.1:28332")
        await listener.connect()

        # Act: Stream transactions
        import time

        start_time = time.time()
        transactions = []

        i = 0
        async for tx in listener.stream_transactions():
            transactions.append(tx)
            if i >= 2:  # Collect 3 transactions
                break
            i += 1

        # Assert: Got 3 RawTransaction objects
        assert len(transactions) == 3, "Should receive 3 transactions"

        for tx in transactions:
            # Must be RawTransaction instance
            assert isinstance(tx, RawTransaction), "Must yield RawTransaction objects"

            # Must have raw_bytes
            assert tx.raw_bytes == sample_tx_bytes, "raw_bytes must match received data"

            # Must have topic='rawtx'
            assert tx.topic == "rawtx", "topic must be 'rawtx'"

            # Timestamp must be recent (within 2 seconds of test start)
            assert abs(tx.timestamp - start_time) < 2.0, (
                "timestamp must be current time"
            )


@pytest.mark.asyncio
async def test_zmq_stream_handles_3_part_messages():
    """
    Test that ZMQListener handles 3-part ZMQ messages from Bitcoin Core.

    Requirements:
    - Bitcoin Core ZMQ sends 3-part messages: [topic, data, sequence_number]
    - Listener must accept both 2-part and 3-part messages
    - Sequence number should be ignored (not used for processing)
    - Must yield valid RawTransaction objects from 3-part messages

    Contract: stream_transactions() handles 3-part messages correctly
    """
    # Arrange: Mock socket with 3-part messages (as Bitcoin Core sends them)
    with patch("zmq.asyncio.Context") as mock_context:
        mock_socket = AsyncMock()

        valid_tx = bytes.fromhex(
            "020000000100ffffffff0002400420f000000000080969800000000000000000"
        )
        sequence_number = b"\x00\x00\x00\x01"  # Sequence counter from Bitcoin Core

        # 3-part messages: [topic, data, sequence]
        mock_socket.recv_multipart = AsyncMock(
            side_effect=[
                [
                    b"rawtx",
                    valid_tx,
                    sequence_number,
                ],  # 3-part message (real Bitcoin Core format)
                [b"rawtx", valid_tx, sequence_number],  # Another 3-part message
            ]
        )

        mock_context.return_value.socket.return_value = mock_socket

        listener = ZMQListener(tx_endpoint="tcp://127.0.0.1:28332")
        await listener.connect()

        # Act: Stream transactions
        transactions = []
        async for tx in listener.stream_transactions():
            transactions.append(tx)
            if len(transactions) >= 2:
                break

        # Assert: Should successfully process 3-part messages
        assert len(transactions) == 2, (
            "Should yield 2 transactions from 3-part messages"
        )

        for tx in transactions:
            assert isinstance(tx, RawTransaction)
            assert tx.raw_bytes == valid_tx
            assert tx.topic == "rawtx"


@pytest.mark.asyncio
async def test_zmq_stream_handles_malformed_messages():
    """
    Test that ZMQListener handles malformed ZMQ messages gracefully.

    Requirements:
    - Skip messages that don't have 2 or 3 parts
    - Skip messages with wrong topic
    - Log warnings for malformed messages
    - Continue streaming after encountering bad messages

    Contract: stream_transactions() skips invalid messages and continues
    """
    # Arrange: Mock socket with mix of valid and invalid messages
    with patch("zmq.asyncio.Context") as mock_context:
        mock_socket = AsyncMock()

        valid_tx = bytes.fromhex(
            "020000000100ffffffff0002400420f000000000080969800000000000000000"
        )

        # Mix of valid and invalid messages
        mock_socket.recv_multipart = AsyncMock(
            side_effect=[
                [b"rawtx"],  # Invalid: Only 1 part (should skip)
                [b"rawblock", valid_tx],  # Invalid: Wrong topic (should skip)
                [b"rawtx", valid_tx],  # Valid
                [b"rawtx", b""],  # Invalid: Empty transaction (should skip or raise)
                [b"rawtx", valid_tx],  # Valid
            ]
        )

        mock_context.return_value.socket.return_value = mock_socket

        listener = ZMQListener(tx_endpoint="tcp://127.0.0.1:28332")
        await listener.connect()

        # Act: Stream transactions
        transactions = []
        async for tx in listener.stream_transactions():
            transactions.append(tx)
            if len(transactions) >= 2:  # Should get 2 valid transactions
                break

        # Assert: Only valid transactions were yielded
        assert len(transactions) == 2, (
            "Should yield only 2 valid transactions (skipping 3 invalid)"
        )

        for tx in transactions:
            assert isinstance(tx, RawTransaction)
            assert tx.raw_bytes == valid_tx
            assert tx.topic == "rawtx"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_raw_transaction() -> bytes:
    """
    Sample raw transaction bytes for testing.

    This is a minimal valid Bitcoin transaction with:
    - 1 input
    - 2 outputs
    - Standard format (non-segwit for simplicity)
    """
    return bytes.fromhex(
        "02000000"  # version (4 bytes, little endian)
        "01"  # input count (1 byte)
        "0000000000000000000000000000000000000000000000000000000000000000"  # prev tx hash
        "ffffffff"  # prev output index
        "00"  # script sig length
        "ffffffff"  # sequence
        "02"  # output count (1 byte)
        "40420f0000000000"  # output 1 value (1,000,000 satoshis)
        "00"  # output 1 script length
        "8096980000000000"  # output 2 value (10,000,000 satoshis)
        "00"  # output 2 script length
        "00000000"  # locktime
    )
