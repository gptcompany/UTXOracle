"""
Integration Tests for Complete Pipeline

TDD Phase: RED - All tests must FAIL initially

Tasks:
- T027 [P]: test_end_to_end_zmq_to_websocket
"""

import pytest
import time
import json
from unittest.mock import AsyncMock, patch

from live.backend.zmq_listener import ZMQListener
from live.backend.tx_processor import TransactionProcessor
from live.backend.mempool_analyzer import MempoolAnalyzer
from live.backend.api import DataStreamer

from live.shared.models import (
    RawTransaction,
    ProcessedTransaction,
    MempoolState,
    WebSocketMessage,
)


# =============================================================================
# T027: End-to-End Integration Test
# =============================================================================


@pytest.mark.asyncio
async def test_end_to_end_zmq_to_websocket():
    """
    Test complete pipeline from ZMQ transaction receipt to WebSocket broadcast.

    Data Flow:
    1. ZMQ Listener receives raw transaction from Bitcoin Core
    2. Transaction Processor parses and filters transaction
    3. Mempool Analyzer updates histogram and estimates price
    4. Data Streamer broadcasts MempoolState via WebSocket
    5. Client receives WebSocketMessage with price update

    Requirements:
    - All modules integrate correctly via shared data models
    - No data loss between module boundaries
    - End-to-end latency < 100ms (from ZMQ receipt to WebSocket send)
    - Black box interfaces preserved (modules don't access each other's internals)

    Contract: Complete pipeline from bytes → WebSocket JSON
    """
    # =========================================================================
    # ARRANGE: Set up all modules with mocks
    # =========================================================================

    # Mock Bitcoin Core ZMQ
    with patch("zmq.asyncio.Context") as mock_zmq_context:
        # Sample transaction bytes (2 inputs, 2 outputs, valid amounts)
        sample_tx_bytes = bytes.fromhex(
            "02000000"  # version
            "02"  # 2 inputs
            + "00" * 32
            + "00000000"
            + "00"
            + "ffffffff"
            + "11" * 32
            + "00000000"
            + "00"
            + "ffffffff"
            + "02"  # 2 outputs
            + "a086010000000000"  # 0.001 BTC = 100,000 sats
            + "19"  # script length
            + "76a914"
            + "00" * 20
            + "88ac"  # P2PKH
            + "400d030000000000"  # 0.002 BTC = 200,000 sats
            + "19"
            + "76a914"
            + "11" * 20
            + "88ac"
            + "00000000"  # locktime
        )

        # Mock ZMQ socket to yield transaction
        mock_socket = AsyncMock()
        mock_socket.recv_multipart = AsyncMock(return_value=[b"rawtx", sample_tx_bytes])
        mock_zmq_context.return_value.socket.return_value = mock_socket

        # Create all modules
        zmq_listener = ZMQListener(tx_endpoint="tcp://127.0.0.1:28332")
        tx_processor = TransactionProcessor()
        mempool_analyzer = MempoolAnalyzer()
        data_streamer = DataStreamer()

        # Mock WebSocket client
        mock_ws_client = MockWebSocketClient()

        # =====================================================================
        # ACT: Run complete pipeline
        # =====================================================================

        start_time = time.time()

        # Step 1: ZMQ Listener receives transaction
        await zmq_listener.connect()

        raw_tx = None
        async for tx in zmq_listener.stream_transactions():
            raw_tx = tx
            break  # Get first transaction

        # Assert: RawTransaction received
        assert raw_tx is not None, "Should receive RawTransaction from ZMQ"
        assert isinstance(raw_tx, RawTransaction)
        assert raw_tx.topic == "rawtx"
        assert raw_tx.raw_bytes == sample_tx_bytes

        # Step 2: Transaction Processor parses and filters
        parsed_tx = tx_processor.parse_transaction(raw_tx.raw_bytes)

        # Assert: Parsed correctly
        assert parsed_tx.version == 2
        assert len(parsed_tx.inputs) == 2
        assert len(parsed_tx.outputs) == 2

        # Filter transaction
        should_process = tx_processor.filter_transaction(parsed_tx)
        assert should_process, "Transaction should pass UTXOracle filters"

        # Convert to ProcessedTransaction
        processed_tx = tx_processor.to_processed(parsed_tx, timestamp=raw_tx.timestamp)

        # Assert: ProcessedTransaction created
        assert isinstance(processed_tx, ProcessedTransaction)
        assert len(processed_tx.txid) == 64
        assert processed_tx.input_count == 2
        assert processed_tx.output_count == 2
        assert len(processed_tx.amounts) == 2
        assert processed_tx.amounts[0] == 0.001
        assert processed_tx.amounts[1] == 0.002

        # Step 3: Mempool Analyzer processes transaction
        mempool_analyzer.add_transaction(processed_tx)

        # Get mempool state
        mempool_state = mempool_analyzer.get_state()

        # Assert: MempoolState created
        assert isinstance(mempool_state, MempoolState)
        assert mempool_state.price > 0
        assert 0.0 <= mempool_state.confidence <= 1.0
        assert mempool_state.active_tx_count >= 1
        assert mempool_state.total_received >= 1

        # Step 4: Data Streamer broadcasts to WebSocket
        await data_streamer.register_client(mock_ws_client)
        await data_streamer.broadcast(mempool_state)

        # Assert: WebSocket client received message
        assert mock_ws_client.messages_received == 1, (
            "Client should receive 1 broadcast"
        )

        # Parse received message
        received_json = json.loads(mock_ws_client.last_message)

        # Assert: WebSocketMessage format
        ws_message = WebSocketMessage(**received_json)
        assert ws_message.type == "mempool_update"
        assert ws_message.data.price == mempool_state.price
        assert ws_message.data.confidence == mempool_state.confidence
        assert ws_message.data.stats.total_received == mempool_state.total_received

        # =====================================================================
        # ASSERT: End-to-end requirements
        # =====================================================================

        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000

        # Latency check (should be < 100ms for single transaction)
        assert latency_ms < 100, (
            f"Pipeline latency {latency_ms:.2f}ms exceeds 100ms threshold"
        )

        # Data integrity check (BTC amounts preserved through pipeline)
        original_amounts = [0.001, 0.002]
        assert processed_tx.amounts == original_amounts, (
            "BTC amounts should be preserved"
        )

        # Black box interface check (all data passed through defined models)
        assert isinstance(raw_tx, RawTransaction), "Module 1 output is RawTransaction"
        assert isinstance(processed_tx, ProcessedTransaction), (
            "Module 2 output is ProcessedTransaction"
        )
        assert isinstance(mempool_state, MempoolState), (
            "Module 3 output is MempoolState"
        )
        assert isinstance(ws_message, WebSocketMessage), (
            "Module 4 output is WebSocketMessage"
        )


@pytest.mark.asyncio
async def test_pipeline_with_multiple_transactions():
    """
    Test pipeline handles stream of multiple transactions correctly.

    Requirements:
    - Process multiple transactions in sequence
    - Histogram updates with each transaction
    - Price estimate improves with more data
    - WebSocket broadcasts reflect cumulative state

    Contract: Pipeline maintains state across multiple transactions
    """
    # =========================================================================
    # ARRANGE: Mock ZMQ to yield multiple transactions
    # =========================================================================

    with patch("zmq.asyncio.Context") as mock_zmq_context:
        # Create 10 different transactions
        transactions = []
        for i in range(10):
            tx_bytes = bytes.fromhex(
                "02000000"
                "01"  # 1 input
                + f"{i:02x}" * 32
                + "00000000"
                + "00"
                + "ffffffff"
                + "02"  # 2 outputs
                + f"{(100000 + i * 1000):016x}"  # Varying amounts
                + "00"
                + f"{(200000 + i * 2000):016x}"
                + "00"
                + "00000000"
            )
            transactions.append(tx_bytes)

        # Mock socket to yield transactions one by one
        mock_socket = AsyncMock()
        mock_socket.recv_multipart = AsyncMock(
            side_effect=[[b"rawtx", tx] for tx in transactions]
        )
        mock_zmq_context.return_value.socket.return_value = mock_socket

        # Create modules
        zmq_listener = ZMQListener(tx_endpoint="tcp://127.0.0.1:28332")
        tx_processor = TransactionProcessor()
        mempool_analyzer = MempoolAnalyzer()
        data_streamer = DataStreamer()

        mock_ws_client = MockWebSocketClient()
        await data_streamer.register_client(mock_ws_client)

        # =====================================================================
        # ACT: Process all transactions
        # =====================================================================

        await zmq_listener.connect()

        processed_count = 0
        async for raw_tx in zmq_listener.stream_transactions():
            # Parse and filter
            parsed = tx_processor.parse_transaction(raw_tx.raw_bytes)
            if tx_processor.filter_transaction(parsed):
                processed = tx_processor.to_processed(
                    parsed, timestamp=raw_tx.timestamp
                )

                # Add to analyzer
                mempool_analyzer.add_transaction(processed)
                processed_count += 1

                # Broadcast state
                state = mempool_analyzer.get_state()
                await data_streamer.broadcast(state)

            # Stop after processing all transactions
            if processed_count >= 10:
                break

        # =====================================================================
        # ASSERT: Pipeline state after multiple transactions
        # =====================================================================

        final_state = mempool_analyzer.get_state()

        # Assert: All transactions processed
        assert final_state.total_received == 10, "Should have received 10 transactions"
        assert final_state.active_tx_count == 10, "All 10 should be in window"

        # Assert: Client received 10 broadcasts
        assert mock_ws_client.messages_received == 10, (
            "Should receive 10 WebSocket messages"
        )

        # Assert: Final state has reasonable confidence
        # With 10 transactions, confidence should be low but non-zero
        assert 0.0 < final_state.confidence <= 0.3, (
            "Confidence should be in low range with 10 tx"
        )


@pytest.mark.asyncio
async def test_pipeline_filters_invalid_transactions():
    """
    Test that pipeline correctly filters out transactions that don't meet UTXOracle criteria.

    Requirements:
    - Transactions with >5 inputs are filtered out
    - Transactions with ≠2 outputs are filtered out
    - Filtered transactions don't reach Mempool Analyzer
    - total_filtered count is accurate

    Contract: Only valid transactions propagate through pipeline
    """
    # =========================================================================
    # ARRANGE: Mix of valid and invalid transactions
    # =========================================================================

    with patch("zmq.asyncio.Context") as mock_zmq_context:
        # Invalid: 6 inputs (too many)
        invalid_tx_1 = bytes.fromhex(
            "01000000"
            "06"  # 6 inputs
            + ("00" * 32 + "00000000" + "00" + "ffffffff") * 6
            + "02"
            + "a086010000000000"
            + "00"
            + "400d030000000000"
            + "00"
            + "00000000"
        )

        # Valid: 2 inputs, 2 outputs
        valid_tx = bytes.fromhex(
            "02000000"
            "02"
            + "00" * 32
            + "00000000"
            + "00"
            + "ffffffff"
            + "11" * 32
            + "00000000"
            + "00"
            + "ffffffff"
            + "02"
            + "a086010000000000"
            + "19"
            + "76a914"
            + "00" * 20
            + "88ac"
            + "400d030000000000"
            + "19"
            + "76a914"
            + "11" * 20
            + "88ac"
            + "00000000"
        )

        # Invalid: 1 output (wrong count)
        invalid_tx_2 = bytes.fromhex(
            "01000000"
            "01"
            + "00" * 32
            + "00000000"
            + "00"
            + "ffffffff"
            + "01"  # Only 1 output
            + "a086010000000000"
            + "00"
            + "00000000"
        )

        # Mock socket
        mock_socket = AsyncMock()
        mock_socket.recv_multipart = AsyncMock(
            side_effect=[
                [b"rawtx", invalid_tx_1],
                [b"rawtx", valid_tx],
                [b"rawtx", invalid_tx_2],
            ]
        )
        mock_zmq_context.return_value.socket.return_value = mock_socket

        # Create modules
        zmq_listener = ZMQListener(tx_endpoint="tcp://127.0.0.1:28332")
        tx_processor = TransactionProcessor()
        mempool_analyzer = MempoolAnalyzer()

        # =====================================================================
        # ACT: Process transactions
        # =====================================================================

        await zmq_listener.connect()

        valid_count = 0
        filtered_count = 0

        async for raw_tx in zmq_listener.stream_transactions():
            parsed = tx_processor.parse_transaction(raw_tx.raw_bytes)

            if tx_processor.filter_transaction(parsed):
                processed = tx_processor.to_processed(
                    parsed, timestamp=raw_tx.timestamp
                )
                mempool_analyzer.add_transaction(processed)
                valid_count += 1
            else:
                filtered_count += 1

            # Stop after 3 transactions
            if (valid_count + filtered_count) >= 3:
                break

        # =====================================================================
        # ASSERT: Filtering worked correctly
        # =====================================================================

        assert valid_count == 1, "Should have 1 valid transaction"
        assert filtered_count == 2, "Should have filtered out 2 transactions"

        # Assert: Analyzer only received valid transaction
        state = mempool_analyzer.get_state()
        assert state.total_received == 1, (
            "Analyzer should only receive valid transactions"
        )


# =============================================================================
# Mock WebSocket Client
# =============================================================================


class MockWebSocketClient:
    """Mock WebSocket client for integration testing"""

    def __init__(self):
        self.messages_received = 0
        self.last_message = None
        self._connected = True

    async def send_text(self, message: str):
        """Simulate receiving message from server"""
        if not self._connected:
            raise RuntimeError("WebSocket disconnected")

        self.messages_received += 1
        self.last_message = message

    @property
    def is_connected(self):
        return self._connected


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def valid_transaction_bytes() -> bytes:
    """Valid transaction that passes all UTXOracle filters"""
    return bytes.fromhex(
        "02000000"  # version
        "02"  # 2 inputs
        + "00" * 32
        + "00000000"
        + "00"
        + "ffffffff"
        + "11" * 32
        + "00000000"
        + "00"
        + "ffffffff"
        + "02"  # 2 outputs
        + "a086010000000000"
        + "19"
        + "76a914"
        + "00" * 20
        + "88ac"  # 0.001 BTC
        + "400d030000000000"
        + "19"
        + "76a914"
        + "11" * 20
        + "88ac"  # 0.002 BTC
        + "00000000"  # locktime
    )
