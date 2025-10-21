"""
Unit tests for shared data models

Tests validation rules, serialization, and edge cases for all models in live/shared/models.py

Target Coverage: >80%
"""

import json
import time

import pytest

from live.shared.models import (
    MempoolState,
    MempoolUpdateData,
    ProcessedTransaction,
    RawTransaction,
    SystemStats,
    TransactionPoint,
    WebSocketMessage,
    calculate_confidence,
)


# =============================================================================
# RawTransaction Tests (T011)
# =============================================================================


def test_raw_transaction_creation():
    """Test RawTransaction dataclass creation with valid data"""
    tx = RawTransaction(
        raw_bytes=b"\x01\x02\x03", timestamp=1678901234.567, topic="rawtx"
    )
    assert tx.topic == "rawtx"
    assert len(tx.raw_bytes) == 3
    assert tx.timestamp == 1678901234.567


def test_raw_transaction_empty_bytes():
    """Test RawTransaction rejects empty raw_bytes"""
    with pytest.raises(ValueError, match="raw_bytes must be non-empty"):
        RawTransaction(raw_bytes=b"", timestamp=1678901234.567, topic="rawtx")


def test_raw_transaction_invalid_timestamp():
    """Test RawTransaction rejects non-positive timestamp"""
    with pytest.raises(ValueError, match="timestamp must be positive"):
        RawTransaction(raw_bytes=b"\x01\x02\x03", timestamp=0, topic="rawtx")

    with pytest.raises(ValueError, match="timestamp must be positive"):
        RawTransaction(raw_bytes=b"\x01\x02\x03", timestamp=-1.5, topic="rawtx")


def test_raw_transaction_invalid_topic():
    """Test RawTransaction rejects invalid topic"""
    with pytest.raises(ValueError, match="topic must be 'rawtx'"):
        RawTransaction(
            raw_bytes=b"\x01\x02\x03", timestamp=1678901234.567, topic="invalid"
        )


def test_raw_transaction_realistic_size():
    """Test RawTransaction with realistic Bitcoin transaction size (250 bytes typical)"""
    realistic_tx = b"\x02\x00\x00\x00" + b"\x00" * 246  # Version + padding
    tx = RawTransaction(raw_bytes=realistic_tx, timestamp=time.time(), topic="rawtx")
    assert len(tx.raw_bytes) == 250


# =============================================================================
# ProcessedTransaction Tests (T012)
# =============================================================================


def test_processed_transaction_creation():
    """Test ProcessedTransaction with valid data"""
    tx = ProcessedTransaction(
        txid="a" * 64,
        amounts=[0.001, 0.002],
        timestamp=1678901234.567,
        input_count=2,
        output_count=2,
    )
    assert len(tx.amounts) == 2
    assert tx.input_count == 2
    assert tx.output_count == 2


def test_processed_transaction_with_fee_rate():
    """Test ProcessedTransaction with optional fee_rate"""
    tx = ProcessedTransaction(
        txid="a" * 64,
        amounts=[0.001, 0.002],
        timestamp=1678901234.567,
        fee_rate=25.5,
        input_count=2,
        output_count=2,
    )
    assert tx.fee_rate == 25.5


def test_processed_transaction_invalid_txid_length():
    """Test ProcessedTransaction rejects invalid txid length"""
    with pytest.raises(ValueError, match="txid must be 64-character hex string"):
        ProcessedTransaction(
            txid="abc",  # Too short
            amounts=[0.001, 0.002],
            timestamp=1678901234.567,
            input_count=2,
            output_count=2,
        )


def test_processed_transaction_invalid_txid_chars():
    """Test ProcessedTransaction rejects non-hex characters in txid"""
    with pytest.raises(ValueError, match="txid must be valid hex string"):
        ProcessedTransaction(
            txid="g" * 64,  # 'g' is not hex
            amounts=[0.001, 0.002],
            timestamp=1678901234.567,
            input_count=2,
            output_count=2,
        )


def test_processed_transaction_empty_amounts():
    """Test ProcessedTransaction rejects empty amounts list"""
    with pytest.raises(ValueError, match="amounts must be non-empty list"):
        ProcessedTransaction(
            txid="a" * 64,
            amounts=[],
            timestamp=1678901234.567,
            input_count=2,
            output_count=2,
        )


def test_processed_transaction_amount_range_validation():
    """Test ProcessedTransaction enforces amount range [1e-5, 1e5] BTC"""
    # Valid range
    tx = ProcessedTransaction(
        txid="a" * 64,
        amounts=[1e-5, 1e5],  # Min and max bounds
        timestamp=1678901234.567,
        input_count=2,
        output_count=2,
    )
    assert tx.amounts == [1e-5, 1e5]

    # Too small
    with pytest.raises(ValueError, match="all amounts must be in range"):
        ProcessedTransaction(
            txid="a" * 64,
            amounts=[1e-6],  # Below minimum
            timestamp=1678901234.567,
            input_count=1,
            output_count=2,
        )

    # Too large
    with pytest.raises(ValueError, match="all amounts must be in range"):
        ProcessedTransaction(
            txid="a" * 64,
            amounts=[1e6],  # Above maximum
            timestamp=1678901234.567,
            input_count=1,
            output_count=2,
        )


def test_processed_transaction_input_count_validation():
    """Test ProcessedTransaction enforces input_count in [1, 5]"""
    # Valid range
    for count in [1, 2, 3, 4, 5]:
        tx = ProcessedTransaction(
            txid="a" * 64,
            amounts=[0.001, 0.002],
            timestamp=1678901234.567,
            input_count=count,
            output_count=2,
        )
        assert tx.input_count == count

    # Invalid: 0 inputs
    with pytest.raises(ValueError, match="input_count must be in range"):
        ProcessedTransaction(
            txid="a" * 64,
            amounts=[0.001, 0.002],
            timestamp=1678901234.567,
            input_count=0,
            output_count=2,
        )

    # Invalid: >5 inputs
    with pytest.raises(ValueError, match="input_count must be in range"):
        ProcessedTransaction(
            txid="a" * 64,
            amounts=[0.001, 0.002],
            timestamp=1678901234.567,
            input_count=6,
            output_count=2,
        )


def test_processed_transaction_output_count_validation():
    """Test ProcessedTransaction enforces exactly 2 outputs"""
    # Valid: 2 outputs
    tx = ProcessedTransaction(
        txid="a" * 64,
        amounts=[0.001, 0.002],
        timestamp=1678901234.567,
        input_count=2,
        output_count=2,
    )
    assert tx.output_count == 2

    # Invalid: 1 output
    with pytest.raises(ValueError, match="output_count must be exactly 2"):
        ProcessedTransaction(
            txid="a" * 64,
            amounts=[0.001],
            timestamp=1678901234.567,
            input_count=2,
            output_count=1,
        )

    # Invalid: 3 outputs
    with pytest.raises(ValueError, match="output_count must be exactly 2"):
        ProcessedTransaction(
            txid="a" * 64,
            amounts=[0.001, 0.002, 0.003],
            timestamp=1678901234.567,
            input_count=2,
            output_count=3,
        )


def test_processed_transaction_negative_fee_rate():
    """Test ProcessedTransaction rejects negative fee_rate"""
    with pytest.raises(ValueError, match="fee_rate must be positive"):
        ProcessedTransaction(
            txid="a" * 64,
            amounts=[0.001, 0.002],
            timestamp=1678901234.567,
            fee_rate=-10.0,
            input_count=2,
            output_count=2,
        )


# =============================================================================
# MempoolState Tests (T013)
# =============================================================================


def test_mempool_state_creation():
    """Test MempoolState with valid data"""
    state = MempoolState(
        price=113600.50,
        confidence=0.87,
        active_tx_count=4309,
        total_received=12543,
        total_filtered=8234,
        uptime_seconds=3600.5,
    )
    assert state.price == 113600.50
    assert state.confidence == 0.87
    assert state.active_tx_count == 4309


def test_mempool_state_invalid_price():
    """Test MempoolState rejects non-positive price"""
    with pytest.raises(ValueError, match="price must be positive"):
        MempoolState(
            price=0,
            confidence=0.87,
            active_tx_count=4309,
            total_received=12543,
            total_filtered=8234,
            uptime_seconds=3600.5,
        )

    with pytest.raises(ValueError, match="price must be positive"):
        MempoolState(
            price=-100.0,
            confidence=0.87,
            active_tx_count=4309,
            total_received=12543,
            total_filtered=8234,
            uptime_seconds=3600.5,
        )


def test_mempool_state_confidence_range():
    """Test MempoolState enforces confidence in [0.0, 1.0]"""
    # Valid bounds
    state_min = MempoolState(
        price=113600.50,
        confidence=0.0,
        active_tx_count=0,
        total_received=0,
        total_filtered=0,
        uptime_seconds=1.0,
    )
    assert state_min.confidence == 0.0

    state_max = MempoolState(
        price=113600.50,
        confidence=1.0,
        active_tx_count=10000,
        total_received=20000,
        total_filtered=10000,
        uptime_seconds=3600.5,
    )
    assert state_max.confidence == 1.0

    # Below range
    with pytest.raises(ValueError, match="confidence must be in range"):
        MempoolState(
            price=113600.50,
            confidence=-0.1,
            active_tx_count=4309,
            total_received=12543,
            total_filtered=8234,
            uptime_seconds=3600.5,
        )

    # Above range
    with pytest.raises(ValueError, match="confidence must be in range"):
        MempoolState(
            price=113600.50,
            confidence=1.1,
            active_tx_count=4309,
            total_received=12543,
            total_filtered=8234,
            uptime_seconds=3600.5,
        )


def test_mempool_state_total_received_vs_filtered():
    """Test MempoolState enforces total_received >= total_filtered"""
    # Valid: received >= filtered
    state = MempoolState(
        price=113600.50,
        confidence=0.87,
        active_tx_count=4309,
        total_received=12543,
        total_filtered=8234,
        uptime_seconds=3600.5,
    )
    assert state.total_received >= state.total_filtered

    # Invalid: filtered > received
    with pytest.raises(ValueError, match="total_received must be >= total_filtered"):
        MempoolState(
            price=113600.50,
            confidence=0.87,
            active_tx_count=4309,
            total_received=8234,
            total_filtered=12543,
            uptime_seconds=3600.5,
        )


def test_mempool_state_negative_counts():
    """Test MempoolState rejects negative counts"""
    with pytest.raises(ValueError, match="active_tx_count must be non-negative"):
        MempoolState(
            price=113600.50,
            confidence=0.87,
            active_tx_count=-1,
            total_received=12543,
            total_filtered=8234,
            uptime_seconds=3600.5,
        )

    with pytest.raises(ValueError, match="total_received must be non-negative"):
        MempoolState(
            price=113600.50,
            confidence=0.87,
            active_tx_count=4309,
            total_received=-1,
            total_filtered=8234,
            uptime_seconds=3600.5,
        )

    with pytest.raises(ValueError, match="total_filtered must be non-negative"):
        MempoolState(
            price=113600.50,
            confidence=0.87,
            active_tx_count=4309,
            total_received=12543,
            total_filtered=-1,
            uptime_seconds=3600.5,
        )


# =============================================================================
# Confidence Calculation Tests
# =============================================================================


def test_confidence_score_low_range():
    """Test confidence calculation for low transaction count (0-100)"""
    assert calculate_confidence(0) == 0.0
    assert 0.0 <= calculate_confidence(50) <= 0.3
    assert calculate_confidence(100) == 0.3


def test_confidence_score_medium_range():
    """Test confidence calculation for medium transaction count (100-1000)"""
    assert 0.3 <= calculate_confidence(500) <= 0.8
    conf_at_1000 = calculate_confidence(1000)
    assert 0.79 <= conf_at_1000 <= 0.81  # Should be close to 0.8


def test_confidence_score_high_range():
    """Test confidence calculation for high transaction count (1000+)"""
    assert 0.8 <= calculate_confidence(2000) <= 1.0
    assert 0.8 <= calculate_confidence(5000) <= 1.0
    assert calculate_confidence(10000) <= 1.0  # Should cap at 1.0


def test_confidence_score_monotonic():
    """Test that confidence increases monotonically with transaction count"""
    counts = [0, 50, 100, 500, 1000, 2000, 5000]
    confidences = [calculate_confidence(c) for c in counts]

    for i in range(len(confidences) - 1):
        assert confidences[i] <= confidences[i + 1], (
            f"Non-monotonic at counts {counts[i]}, {counts[i + 1]}"
        )


# =============================================================================
# Pydantic Model Tests (T014)
# =============================================================================


def test_transaction_point_creation():
    """Test TransactionPoint Pydantic model"""
    point = TransactionPoint(timestamp=1678901234.1, price=113500.0)
    assert point.timestamp == 1678901234.1
    assert point.price == 113500.0


def test_transaction_point_validation():
    """Test TransactionPoint field validation"""
    # Invalid: negative timestamp
    with pytest.raises(ValueError):
        TransactionPoint(timestamp=-1.0, price=113500.0)

    # Invalid: zero price
    with pytest.raises(ValueError):
        TransactionPoint(timestamp=1678901234.1, price=0.0)

    # Invalid: negative price
    with pytest.raises(ValueError):
        TransactionPoint(timestamp=1678901234.1, price=-100.0)


def test_system_stats_creation():
    """Test SystemStats Pydantic model"""
    stats = SystemStats(
        total_received=12543,
        total_filtered=8234,
        active_in_window=4309,
        uptime_seconds=3600.5,
    )
    assert stats.total_received == 12543
    assert stats.total_filtered == 8234
    assert stats.active_in_window == 4309
    assert stats.uptime_seconds == 3600.5


def test_system_stats_filtered_validation():
    """Test SystemStats enforces total_filtered <= total_received"""
    # Valid
    stats = SystemStats(
        total_received=12543,
        total_filtered=8234,
        active_in_window=4309,
        uptime_seconds=3600.5,
    )
    assert stats.total_filtered <= stats.total_received

    # Invalid: filtered > received
    with pytest.raises(ValueError, match="total_filtered cannot exceed total_received"):
        SystemStats(
            total_received=8234,
            total_filtered=12543,
            active_in_window=4309,
            uptime_seconds=3600.5,
        )


def test_mempool_update_data_creation():
    """Test MempoolUpdateData Pydantic model"""
    data = MempoolUpdateData(
        price=113600.50,
        confidence=0.87,
        transactions=[
            TransactionPoint(timestamp=1678901234.1, price=113500.0),
            TransactionPoint(timestamp=1678901234.2, price=113700.0),
        ],
        stats=SystemStats(
            total_received=12543,
            total_filtered=8234,
            active_in_window=4309,
            uptime_seconds=3600.5,
        ),
        timestamp=1678901234.567,
    )
    assert data.price == 113600.50
    assert len(data.transactions) == 2


def test_mempool_update_data_empty_transactions():
    """Test MempoolUpdateData allows empty transaction list"""
    data = MempoolUpdateData(
        price=113600.50,
        confidence=0.87,
        transactions=[],
        stats=SystemStats(
            total_received=12543,
            total_filtered=8234,
            active_in_window=4309,
            uptime_seconds=3600.5,
        ),
        timestamp=1678901234.567,
    )
    assert data.transactions == []


def test_websocket_message_creation():
    """Test WebSocketMessage Pydantic model"""
    msg = WebSocketMessage(
        data=MempoolUpdateData(
            price=113600.50,
            confidence=0.87,
            transactions=[],
            stats=SystemStats(
                total_received=12543,
                total_filtered=8234,
                active_in_window=4309,
                uptime_seconds=3600.5,
            ),
            timestamp=1678901234.567,
        )
    )
    assert msg.type == "mempool_update"
    assert msg.data.price == 113600.50


def test_websocket_message_serialization():
    """Test WebSocketMessage JSON serialization/deserialization"""
    msg = WebSocketMessage(
        data=MempoolUpdateData(
            price=113600.50,
            confidence=0.87,
            transactions=[
                TransactionPoint(timestamp=1678901234.1, price=113500.0),
                TransactionPoint(timestamp=1678901234.2, price=113700.0),
            ],
            stats=SystemStats(
                total_received=12543,
                total_filtered=8234,
                active_in_window=4309,
                uptime_seconds=3600.5,
            ),
            timestamp=1678901234.567,
        )
    )

    # Serialize to JSON
    json_str = msg.model_dump_json()
    assert isinstance(json_str, str)

    # Parse JSON
    json_data = json.loads(json_str)
    assert json_data["type"] == "mempool_update"
    assert json_data["data"]["price"] == 113600.50
    assert len(json_data["data"]["transactions"]) == 2

    # Deserialize from JSON
    msg2 = WebSocketMessage.model_validate_json(json_str)
    assert msg2.data.price == 113600.50
    assert msg2.data.confidence == 0.87
    assert len(msg2.data.transactions) == 2


def test_websocket_message_validation():
    """Test WebSocketMessage enforces nested validation"""
    # Invalid: negative price in nested data
    with pytest.raises(ValueError):
        WebSocketMessage(
            data=MempoolUpdateData(
                price=-100.0,  # Invalid
                confidence=0.87,
                transactions=[],
                stats=SystemStats(
                    total_received=12543,
                    total_filtered=8234,
                    active_in_window=4309,
                    uptime_seconds=3600.5,
                ),
                timestamp=1678901234.567,
            )
        )

    # Invalid: confidence out of range
    with pytest.raises(ValueError):
        WebSocketMessage(
            data=MempoolUpdateData(
                price=113600.50,
                confidence=1.5,  # Invalid
                transactions=[],
                stats=SystemStats(
                    total_received=12543,
                    total_filtered=8234,
                    active_in_window=4309,
                    uptime_seconds=3600.5,
                ),
                timestamp=1678901234.567,
            )
        )


# =============================================================================
# Integration Tests
# =============================================================================


def test_baseline_data_validation():
    """Test BaselineData Pydantic model (T106)"""
    from live.shared.models import BaselineData

    baseline = BaselineData(
        price=113600.0,
        price_min=113000.0,
        price_max=114200.0,
        confidence=0.95,
        timestamp=time.time(),
        block_height=800000,
    )

    assert baseline.price == 113600.0
    assert baseline.price_min < baseline.price < baseline.price_max
    assert baseline.confidence == 0.95
    assert baseline.block_height == 800000


def test_websocket_message_with_baseline():
    """Test WebSocketMessage includes baseline data (T106)"""
    from live.shared.models import BaselineData

    msg = WebSocketMessage(
        data=MempoolUpdateData(
            price=113700.0,
            confidence=0.85,
            transactions=[],
            stats=SystemStats(
                total_received=100,
                total_filtered=50,
                active_in_window=50,
                uptime_seconds=60.0,
            ),
            timestamp=time.time(),
            baseline=BaselineData(
                price=113600.0,
                price_min=113000.0,
                price_max=114200.0,
                confidence=0.95,
                timestamp=time.time(),
                block_height=800000,
            ),
        )
    )

    assert msg.data.baseline is not None
    assert msg.data.baseline.price == 113600.0


def test_full_pipeline_data_flow():
    """Test complete data flow from RawTransaction to WebSocketMessage"""
    # Step 1: ZMQ Listener produces RawTransaction
    raw_tx = RawTransaction(
        raw_bytes=b"\x02\x00\x00\x00" + b"\x00" * 250,
        timestamp=time.time(),
        topic="rawtx",
    )

    # Step 2: TX Processor produces ProcessedTransaction
    processed_tx = ProcessedTransaction(
        txid="a" * 64,
        amounts=[0.00123456, 0.00654321],
        timestamp=raw_tx.timestamp,
        fee_rate=25.5,
        input_count=2,
        output_count=2,
    )

    # Step 3: Mempool Analyzer produces MempoolState
    mempool_state = MempoolState(
        price=113600.50,
        confidence=0.87,
        active_tx_count=4309,
        total_received=12543,
        total_filtered=8234,
        uptime_seconds=3600.5,
    )

    # Step 4: Data Streamer produces WebSocketMessage
    ws_msg = WebSocketMessage(
        data=MempoolUpdateData(
            price=mempool_state.price,
            confidence=mempool_state.confidence,
            transactions=[
                TransactionPoint(
                    timestamp=processed_tx.timestamp, price=mempool_state.price
                )
            ],
            stats=SystemStats(
                total_received=mempool_state.total_received,
                total_filtered=mempool_state.total_filtered,
                active_in_window=mempool_state.active_tx_count,
                uptime_seconds=mempool_state.uptime_seconds,
            ),
            timestamp=time.time(),
        )
    )

    # Validate complete pipeline
    assert ws_msg.data.price == mempool_state.price
    assert ws_msg.data.confidence == mempool_state.confidence
    assert len(ws_msg.data.transactions) == 1
    assert ws_msg.data.transactions[0].timestamp == processed_tx.timestamp

    # Verify serialization works
    json_str = ws_msg.model_dump_json()
    assert "mempool_update" in json_str
    assert "113600.5" in json_str
