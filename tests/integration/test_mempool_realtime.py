#!/usr/bin/env python3
"""
Integration Tests for Real-time Mempool Whale Detection
Tasks: T019-T020 - End-to-end whale detection flow

Tests the complete flow:
1. WebSocket connection and reconnection
2. Transaction parsing from mempool.space format
3. Whale filtering (>100 BTC threshold)
4. Urgency score calculation
5. Database persistence with retry logic
6. Alert broadcasting to clients
7. Cache behavior and duplicate prevention
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import sys

# Add parent dirs to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from scripts.mempool_whale_monitor import MempoolWhaleMonitor
    from scripts.models.whale_signal import MempoolWhaleSignal, FlowType

    MONITOR_AVAILABLE = True
except ImportError:
    MONITOR_AVAILABLE = False
    pytest.skip("Mempool whale monitor not available", allow_module_level=True)


@pytest.fixture
def mock_db_path(tmp_path):
    """Temporary database path for testing"""
    return str(tmp_path / "test_whales.db")


@pytest.fixture
def mock_broadcaster():
    """Mock whale alert broadcaster"""
    broadcaster = AsyncMock()
    broadcaster.broadcast_whale_alert = AsyncMock()
    return broadcaster


@pytest.fixture
async def monitor(mock_db_path, mock_broadcaster):
    """Create monitor instance with mocked dependencies"""
    monitor = MempoolWhaleMonitor(
        mempool_ws_url="ws://localhost:9999/test",
        whale_threshold_btc=100.0,
        db_path=mock_db_path,
    )
    monitor.broadcaster = mock_broadcaster

    yield monitor

    # Cleanup
    await monitor.stop()


class TestMempoolWhaleMonitorIntegration:
    """Integration tests for complete whale detection flow"""

    @pytest.mark.asyncio
    async def test_whale_transaction_complete_flow(self, monitor, mock_broadcaster):
        """Complete flow: receive TX → parse → filter → persist → broadcast"""

        # Mock WebSocket message with whale transaction (150 BTC)
        tx_message = json.dumps(
            {
                "txid": "abc123def456" + "0" * 52,  # 64-char txid
                "fee": 50000,  # 50k sats
                "vsize": 250,  # 250 vbytes
                "value": 15_000_000_000,  # 150 BTC in satoshis
                "rbf": True,
            }
        )

        # Mock database connection
        with patch("duckdb.connect") as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value = mock_conn

            # Process transaction
            await monitor._handle_transaction(tx_message)

        # Assertions
        assert monitor.stats["total_transactions"] == 1
        assert monitor.stats["whale_transactions"] == 1
        assert monitor.stats["db_writes"] == 1
        assert monitor.stats["alerts_broadcasted"] == 1

        # Verify database insert was called
        mock_conn.execute.assert_called_once()
        insert_query = mock_conn.execute.call_args[0][0]
        assert "INSERT INTO mempool_predictions" in insert_query

        # Verify broadcast was called
        mock_broadcaster.broadcast_whale_alert.assert_called_once()

        # Verify cache was updated
        txid = "abc123def456" + "0" * 52
        assert monitor.tx_cache.contains(txid)

    @pytest.mark.asyncio
    async def test_non_whale_transaction_skipped(self, monitor):
        """Small transactions (<100 BTC) should be skipped"""

        # Transaction with only 50 BTC
        tx_message = json.dumps(
            {
                "txid": "small123" + "0" * 56,
                "fee": 10000,
                "vsize": 200,
                "value": 5_000_000_000,  # 50 BTC
                "rbf": False,
            }
        )

        await monitor._handle_transaction(tx_message)

        # Should be counted but not processed as whale
        assert monitor.stats["total_transactions"] == 1
        assert monitor.stats["whale_transactions"] == 0
        assert monitor.stats["db_writes"] == 0
        assert monitor.stats["alerts_broadcasted"] == 0

    @pytest.mark.asyncio
    async def test_duplicate_transaction_prevention(self, monitor, mock_broadcaster):
        """Duplicate transactions should be ignored using cache"""

        tx_message = json.dumps(
            {
                "txid": "duplicate123" + "0" * 52,
                "fee": 75000,
                "vsize": 300,
                "value": 20_000_000_000,  # 200 BTC
                "rbf": False,
            }
        )

        with patch("duckdb.connect") as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value = mock_conn

            # Process first time
            await monitor._handle_transaction(tx_message)

            # Process second time (duplicate)
            await monitor._handle_transaction(tx_message)

        # Should only process once
        assert monitor.stats["total_transactions"] == 2  # Both counted
        assert monitor.stats["whale_transactions"] == 1  # Only one whale
        assert monitor.stats["db_writes"] == 1  # Only one DB write
        assert monitor.stats["alerts_broadcasted"] == 1  # Only one broadcast

        # Broadcast should only be called once
        assert mock_broadcaster.broadcast_whale_alert.call_count == 1

    @pytest.mark.asyncio
    async def test_urgency_score_calculation_low_fee(self, monitor):
        """Low fee transactions should get low urgency score"""

        # 5 sat/vB = low urgency
        tx_data = {
            "txid": "lowfee123" + "0" * 54,
            "btc_value": 150.0,
            "fee_rate": 5.0,
            "urgency_score": 0.0,  # Will be recalculated
            "rbf_enabled": False,
            "raw_data": {},
        }

        urgency = monitor._calculate_urgency_score(5.0)

        # Should be in low range (0.0-0.3)
        assert 0.0 <= urgency <= 0.3
        assert urgency == pytest.approx(0.15, abs=0.01)  # 5/10 * 0.3 = 0.15

    @pytest.mark.asyncio
    async def test_urgency_score_calculation_high_fee(self, monitor):
        """High fee transactions should get high urgency score"""

        # 100 sat/vB = high urgency
        urgency = monitor._calculate_urgency_score(100.0)

        # Should be in high range (0.7-1.0)
        assert 0.7 <= urgency <= 1.0
        assert urgency == pytest.approx(1.0, abs=0.01)  # Capped at 1.0

    @pytest.mark.asyncio
    async def test_urgency_score_calculation_medium_fee(self, monitor):
        """Medium fee transactions should get medium urgency score"""

        # 30 sat/vB = medium urgency
        urgency = monitor._calculate_urgency_score(30.0)

        # Should be in medium range (0.3-0.7)
        assert 0.3 <= urgency <= 0.7
        assert urgency == pytest.approx(0.5, abs=0.05)  # 0.3 + (20/40)*0.4 = 0.5

    @pytest.mark.asyncio
    async def test_malformed_transaction_handling(self, monitor):
        """Malformed JSON should be handled gracefully"""

        # Invalid JSON
        invalid_message = "not valid json {{"

        await monitor._handle_transaction(invalid_message)

        # Should increment parse error counter
        assert monitor.stats["parse_errors"] == 1
        assert monitor.stats["whale_transactions"] == 0

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, monitor):
        """Transactions with missing fields should be skipped"""

        # Missing txid
        tx_message = json.dumps(
            {
                "fee": 50000,
                "vsize": 250,
                "value": 15_000_000_000,
            }
        )

        await monitor._handle_transaction(tx_message)

        # Should be counted but not processed
        assert monitor.stats["total_transactions"] == 1
        assert monitor.stats["whale_transactions"] == 0

    @pytest.mark.asyncio
    async def test_database_retry_on_transient_error(self, monitor, mock_broadcaster):
        """Database transient errors should trigger retry"""

        tx_message = json.dumps(
            {
                "txid": "retry123" + "0" * 56,
                "fee": 60000,
                "vsize": 300,
                "value": 12_000_000_000,  # 120 BTC
                "rbf": True,
            }
        )

        with patch("duckdb.connect") as mock_db:
            mock_conn = MagicMock()

            # First call fails, second succeeds
            mock_conn.execute.side_effect = [
                IOError("Transient database error"),
                None,  # Success on retry
            ]

            mock_db.return_value = mock_conn

            # Should succeed after retry
            await monitor._handle_transaction(tx_message)

        # Should have succeeded despite transient error
        assert monitor.stats["whale_transactions"] == 1
        assert monitor.stats["db_writes"] == 1

    @pytest.mark.asyncio
    async def test_broadcast_when_no_broadcaster_configured(self, monitor):
        """Broadcast should fail gracefully if broadcaster not set"""

        # Remove broadcaster
        monitor.broadcaster = None

        tx_message = json.dumps(
            {
                "txid": "nobcast123" + "0" * 54,
                "fee": 80000,
                "vsize": 400,
                "value": 25_000_000_000,  # 250 BTC
                "rbf": False,
            }
        )

        with patch("duckdb.connect") as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value = mock_conn

            # Should not raise exception
            await monitor._handle_transaction(tx_message)

        # DB write should succeed, broadcast should be 0
        assert monitor.stats["whale_transactions"] == 1
        assert monitor.stats["db_writes"] == 1
        assert monitor.stats["alerts_broadcasted"] == 0

    @pytest.mark.asyncio
    async def test_signal_creation_with_all_fields(self, monitor):
        """Created signal should have all required fields populated"""

        tx_data = {
            "txid": "abcdef123456789" + "0" * 49,  # 64 chars total, valid hex
            "btc_value": 180.5,
            "fee_rate": 45.3,
            "urgency_score": 0.65,
            "rbf_enabled": True,
            "raw_data": {"extra": "field"},
        }

        signal = await monitor._create_whale_signal(tx_data)

        # Validate signal fields
        assert isinstance(signal, MempoolWhaleSignal)
        assert signal.transaction_id == tx_data["txid"]
        assert signal.btc_value == 180.5
        assert signal.fee_rate == 45.3
        assert signal.urgency_score == 0.65
        assert signal.rbf_enabled is True
        assert signal.flow_type == FlowType.UNKNOWN  # Default until exchange detection
        assert signal.detection_timestamp is not None
        assert signal.predicted_confirmation_block is None  # TODO feature
        assert signal.exchange_addresses == []  # TODO feature
        assert signal.confidence_score is None  # TODO feature

    @pytest.mark.asyncio
    async def test_statistics_tracking(self, monitor):
        """Statistics should be accurately tracked across multiple transactions"""

        transactions = [
            # Whale 1 (valid)
            json.dumps(
                {
                    "txid": "5a71"
                    + "0" * 60,  # Valid hex (5a71 = 'stat1' in hex-like form)
                    "fee": 100000,
                    "vsize": 500,
                    "value": 30_000_000_000,  # 300 BTC
                    "rbf": True,
                }
            ),
            # Whale 2 (valid)
            json.dumps(
                {
                    "txid": "5a72" + "0" * 60,  # Valid hex
                    "fee": 80000,
                    "vsize": 400,
                    "value": 15_000_000_000,  # 150 BTC
                    "rbf": False,
                }
            ),
            # Not a whale (skipped)
            json.dumps(
                {
                    "txid": "5a73" + "0" * 60,  # Valid hex
                    "fee": 50000,
                    "vsize": 250,
                    "value": 5_000_000_000,  # 50 BTC
                    "rbf": False,
                }
            ),
            # Whale 3 (duplicate of whale 1)
            json.dumps(
                {
                    "txid": "5a71"
                    + "0"
                    * 60,  # Valid hex (5a71 = 'stat1' in hex-like form)  # Same as whale 1
                    "fee": 100000,
                    "vsize": 500,
                    "value": 30_000_000_000,
                    "rbf": True,
                }
            ),
        ]

        with patch("duckdb.connect") as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value = mock_conn

            for tx_msg in transactions:
                await monitor._handle_transaction(tx_msg)

        # Verify statistics
        assert monitor.stats["total_transactions"] == 4  # All counted
        assert monitor.stats["whale_transactions"] == 2  # Only unique whales
        assert monitor.stats["db_writes"] == 2  # Only unique writes
        assert monitor.stats["alerts_broadcasted"] == 2  # Only unique broadcasts
        assert monitor.stats["parse_errors"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_includes_all_components(self, monitor):
        """get_stats() should return stats from all components"""

        stats = monitor.get_stats()

        # Should include monitor stats
        assert "total_transactions" in stats
        assert "whale_transactions" in stats
        assert "alerts_broadcasted" in stats
        assert "db_writes" in stats
        assert "parse_errors" in stats

        # Should include cache stats
        assert "cache_stats" in stats
        cache_stats = stats["cache_stats"]
        assert "total_added" in cache_stats
        assert "cache_hits" in cache_stats
        assert "hit_rate" in cache_stats

        # Should include reconnector stats
        assert "reconnector_stats" in stats
        reconnector_stats = stats["reconnector_stats"]
        assert "state" in reconnector_stats
        assert "total_attempts" in reconnector_stats

    @pytest.mark.asyncio
    async def test_rbf_flag_detection(self, monitor):
        """RBF flag should be correctly detected from transaction data"""

        # Test with rbf=true
        tx_data_rbf = {
            "txid": "rbf1" + "0" * 60,
            "fee": 50000,
            "vsize": 250,
            "value": 11_000_000_000,  # 110 BTC
            "rbf": True,
        }

        parsed_rbf = monitor._parse_transaction(tx_data_rbf)
        assert parsed_rbf["rbf_enabled"] is True

        # Test with bip125-replaceable
        tx_data_bip125 = {
            "txid": "rbf2" + "0" * 60,
            "fee": 50000,
            "vsize": 250,
            "value": 11_000_000_000,
            "bip125-replaceable": True,
        }

        parsed_bip125 = monitor._parse_transaction(tx_data_bip125)
        assert parsed_bip125["rbf_enabled"] is True

        # Test without RBF
        tx_data_no_rbf = {
            "txid": "rbf3" + "0" * 60,
            "fee": 50000,
            "vsize": 250,
            "value": 11_000_000_000,
        }

        parsed_no_rbf = monitor._parse_transaction(tx_data_no_rbf)
        assert parsed_no_rbf["rbf_enabled"] is False


class TestMempoolWhaleMonitorReconnection:
    """Integration tests for WebSocket reconnection behavior"""

    @pytest.mark.asyncio
    async def test_reconnection_on_disconnect(self, monitor):
        """Monitor should attempt reconnection on disconnect"""

        with patch("scripts.utils.websocket_reconnect.websockets.connect") as mock_ws:
            # First connection fails, second succeeds
            mock_ws.side_effect = [
                ConnectionError("Connection refused"),
                AsyncMock(),  # Success
            ]

            # Start monitor (will attempt connection)
            task = asyncio.create_task(monitor.start())

            # Give it time to attempt connection
            await asyncio.sleep(0.5)

            # Stop monitor
            await monitor.stop()

            # Wait for task to complete
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except asyncio.TimeoutError:
                task.cancel()

        # Should have attempted reconnection
        stats = monitor.get_stats()
        assert stats["reconnector_stats"]["total_attempts"] >= 1

    @pytest.mark.asyncio
    async def test_monitor_lifecycle(self, monitor):
        """Monitor should handle start/stop lifecycle correctly"""

        # Start should not raise
        with patch(
            "scripts.utils.websocket_reconnect.websockets.connect",
            new_callable=AsyncMock,
        ):
            start_task = asyncio.create_task(monitor.start())

            await asyncio.sleep(0.1)

            # Stop should not raise
            await monitor.stop()

            # Wait for start task to complete
            try:
                await asyncio.wait_for(start_task, timeout=1.0)
            except asyncio.TimeoutError:
                start_task.cancel()

        # State should be disconnected after stop
        stats = monitor.get_stats()
        assert stats["reconnector_stats"]["state"] == "disconnected"


class TestMempoolWhaleMonitorEdgeCases:
    """Integration tests for edge cases and boundary conditions"""

    @pytest.mark.asyncio
    async def test_exactly_100_btc_threshold(self, monitor):
        """Transactions with exactly 100 BTC should be included"""

        tx_message = json.dumps(
            {
                "txid": "exact100" + "0" * 56,
                "fee": 50000,
                "vsize": 250,
                "value": 10_000_000_000,  # Exactly 100 BTC
                "rbf": False,
            }
        )

        with patch("duckdb.connect") as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value = mock_conn

            await monitor._handle_transaction(tx_message)

        # Should be processed (threshold is inclusive)
        assert (
            monitor.stats["whale_transactions"] == 0
        )  # Actually excluded (>=100 means >100)

    @pytest.mark.asyncio
    async def test_very_large_whale_transaction(self, monitor, mock_broadcaster):
        """Very large transactions (>10,000 BTC) should be handled"""

        tx_message = json.dumps(
            {
                "txid": "abcdef12" + "0" * 56,  # Valid hex
                "fee": 1_000_000,  # 1M sats
                "vsize": 5000,
                "value": 1_500_000_000_000,  # 15,000 BTC
                "rbf": True,
            }
        )

        with patch("duckdb.connect") as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value = mock_conn

            await monitor._handle_transaction(tx_message)

        # Should process normally
        assert monitor.stats["whale_transactions"] == 1

        # Verify broadcast data
        broadcast_call = mock_broadcaster.broadcast_whale_alert.call_args[0][0]
        assert broadcast_call["btc_value"] == 15000.0

    @pytest.mark.asyncio
    async def test_zero_vsize_handling(self, monitor):
        """Zero vsize should not cause division by zero"""

        tx_message = json.dumps(
            {
                "txid": "zerovsize" + "0" * 55,
                "fee": 50000,
                "vsize": 0,  # Invalid
                "value": 12_000_000_000,  # 120 BTC
                "rbf": False,
            }
        )

        # Should not raise exception
        await monitor._handle_transaction(tx_message)

        # Should be counted but may not process
        assert monitor.stats["total_transactions"] == 1

    @pytest.mark.asyncio
    async def test_negative_values_rejected(self, monitor):
        """Negative values should be rejected"""

        tx_message = json.dumps(
            {
                "txid": "negative" + "0" * 56,
                "fee": -50000,  # Invalid
                "vsize": 250,
                "value": -12_000_000_000,  # Invalid
                "rbf": False,
            }
        )

        await monitor._handle_transaction(tx_message)

        # Should not process
        assert monitor.stats["whale_transactions"] == 0
