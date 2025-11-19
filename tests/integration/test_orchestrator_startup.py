#!/usr/bin/env python3
"""
Integration Test: Whale Detection Orchestrator Startup
Task: T018 - Verify orchestrator can coordinate all components

Tests:
- Component initialization
- Database setup
- Broadcaster startup
- Monitor creation
- Graceful shutdown
- Statistics reporting
"""

import asyncio
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import sys

# Add parent dirs to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.whale_detection_orchestrator import WhaleDetectionOrchestrator


class TestOrchestratorStartup:
    """Test orchestrator component coordination"""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def orchestrator(self, temp_db):
        """Create orchestrator instance for testing"""
        return WhaleDetectionOrchestrator(
            db_path=temp_db,
            ws_host="127.0.0.1",
            ws_port=18765,  # Test port to avoid conflicts
            mempool_ws_url="ws://test.mempool/track-tx",
            whale_threshold_btc=100.0,
        )

    def test_orchestrator_initialization(self, orchestrator, temp_db):
        """Orchestrator should initialize with correct configuration"""
        assert orchestrator.db_path == temp_db
        assert orchestrator.ws_host == "127.0.0.1"
        assert orchestrator.ws_port == 18765
        assert orchestrator.mempool_ws_url == "ws://test.mempool/track-tx"
        assert orchestrator.whale_threshold_btc == 100.0
        assert orchestrator.broadcaster is None  # Not started yet
        assert orchestrator.monitor is None  # Not started yet
        assert orchestrator.shutdown_requested is False

    @pytest.mark.asyncio
    async def test_database_initialization(self, orchestrator):
        """Database initialization should create schema"""
        with patch("scripts.whale_detection_orchestrator.init_database") as mock_init:
            mock_init.return_value = True

            result = await orchestrator.initialize_database()

            assert result is True
            mock_init.assert_called_once_with(orchestrator.db_path)

    @pytest.mark.asyncio
    async def test_database_initialization_failure(self, orchestrator):
        """Database initialization failure should be handled gracefully"""
        with patch("scripts.whale_detection_orchestrator.init_database") as mock_init:
            mock_init.return_value = False

            result = await orchestrator.initialize_database()

            assert result is False

    @pytest.mark.asyncio
    async def test_orchestrator_start_creates_components(self, orchestrator):
        """Starting orchestrator should create broadcaster and monitor"""
        with patch.object(
            orchestrator, "initialize_database", return_value=True
        ) as mock_db:
            with patch(
                "scripts.whale_detection_orchestrator.WhaleAlertBroadcaster"
            ) as MockBroadcaster:
                with patch(
                    "scripts.whale_detection_orchestrator.MempoolWhaleMonitor"
                ) as MockMonitor:
                    # Mock broadcaster and monitor start methods
                    mock_broadcaster_instance = AsyncMock()
                    mock_broadcaster_instance.start = AsyncMock(
                        side_effect=asyncio.CancelledError
                    )
                    MockBroadcaster.return_value = mock_broadcaster_instance

                    mock_monitor_instance = AsyncMock()
                    mock_monitor_instance.start = AsyncMock(
                        side_effect=asyncio.CancelledError
                    )
                    MockMonitor.return_value = mock_monitor_instance

                    # Start orchestrator (will be cancelled immediately by mocks)
                    try:
                        await orchestrator.start()
                    except asyncio.CancelledError:
                        pass

                    # Verify database was initialized
                    mock_db.assert_called_once()

                    # Verify broadcaster was created with correct config
                    MockBroadcaster.assert_called_once_with(
                        host="127.0.0.1", port=18765
                    )

                    # Verify monitor was created with correct config
                    MockMonitor.assert_called_once_with(
                        mempool_ws_url="ws://test.mempool/track-tx",
                        whale_threshold_btc=100.0,
                        db_path=orchestrator.db_path,
                    )

                    # Verify monitor was connected to broadcaster
                    assert orchestrator.monitor.broadcaster == orchestrator.broadcaster

    @pytest.mark.asyncio
    async def test_orchestrator_stop_gracefully_shuts_down(self, orchestrator):
        """Stopping orchestrator should gracefully shut down all components"""
        # Setup mock components
        orchestrator.monitor = AsyncMock()
        orchestrator.monitor.stop = AsyncMock()
        orchestrator.monitor.get_stats = Mock(
            return_value={
                "total_transactions": 1000,
                "whale_transactions": 50,
                "alerts_broadcasted": 45,
                "db_writes": 50,
                "parse_errors": 5,
                "cache_stats": {
                    "total_added": 50,
                    "cache_hits": 25,
                    "hit_rate": 50.0,
                },
            }
        )

        orchestrator.broadcaster = AsyncMock()
        orchestrator.broadcaster.stop = AsyncMock()
        orchestrator.broadcaster.get_stats = Mock(
            return_value={
                "total_connections": 10,
                "active_connections": 2,
                "authenticated_clients": 1,
                "messages_sent": 45,
                "auth_failures": 0,
            }
        )

        # Stop orchestrator
        await orchestrator.stop()

        # Verify shutdown sequence
        orchestrator.monitor.stop.assert_called_once()
        orchestrator.broadcaster.stop.assert_called_once()
        assert orchestrator.shutdown_requested is True

    @pytest.mark.asyncio
    async def test_orchestrator_stop_timeout_handling(self, orchestrator):
        """Stop should handle component timeout gracefully"""
        # Setup monitor that times out
        orchestrator.monitor = AsyncMock()
        orchestrator.monitor.stop = AsyncMock(side_effect=asyncio.TimeoutError())
        orchestrator.monitor.get_stats = Mock(return_value={})

        # Setup broadcaster that stops normally
        orchestrator.broadcaster = AsyncMock()
        orchestrator.broadcaster.stop = AsyncMock()
        orchestrator.broadcaster.get_stats = Mock(return_value={})

        # Should not raise exception
        await orchestrator.stop()

        # Verify both shutdown methods were called
        orchestrator.monitor.stop.assert_called_once()
        orchestrator.broadcaster.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_orchestrator_double_stop_ignored(self, orchestrator):
        """Calling stop twice should be handled gracefully"""
        orchestrator.monitor = AsyncMock()
        orchestrator.monitor.stop = AsyncMock()
        orchestrator.monitor.get_stats = Mock(return_value={})

        orchestrator.broadcaster = AsyncMock()
        orchestrator.broadcaster.stop = AsyncMock()
        orchestrator.broadcaster.get_stats = Mock(return_value={})

        # First stop
        await orchestrator.stop()
        assert orchestrator.shutdown_requested is True

        # Reset mocks
        orchestrator.monitor.stop.reset_mock()
        orchestrator.broadcaster.stop.reset_mock()

        # Second stop should be ignored
        await orchestrator.stop()

        # Verify components were NOT stopped again
        orchestrator.monitor.stop.assert_not_called()
        orchestrator.broadcaster.stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_orchestrator_start_aborts_on_db_failure(self, orchestrator):
        """Start should abort if database initialization fails"""
        with patch.object(
            orchestrator, "initialize_database", return_value=False
        ) as mock_db:
            await orchestrator.start()

            # Verify early return (no components created)
            assert orchestrator.broadcaster is None
            assert orchestrator.monitor is None

    @pytest.mark.asyncio
    async def test_statistics_reporting(self, orchestrator):
        """Statistics should be collected and reported correctly"""
        # Setup mock components with stats
        orchestrator.monitor = Mock()
        orchestrator.monitor.get_stats = Mock(
            return_value={
                "total_transactions": 5000,
                "whale_transactions": 125,
                "alerts_broadcasted": 120,
                "db_writes": 125,
                "parse_errors": 10,
                "cache_stats": {
                    "total_added": 125,
                    "cache_hits": 80,
                    "hit_rate": 64.0,
                },
            }
        )

        orchestrator.broadcaster = Mock()
        orchestrator.broadcaster.get_stats = Mock(
            return_value={
                "total_connections": 25,
                "active_connections": 5,
                "authenticated_clients": 3,
                "messages_sent": 120,
                "auth_failures": 2,
            }
        )

        # Print statistics (should not raise)
        await orchestrator.print_statistics()

        # Verify stats were retrieved
        orchestrator.monitor.get_stats.assert_called_once()
        orchestrator.broadcaster.get_stats.assert_called_once()

    def test_orchestrator_config_from_defaults(self):
        """Orchestrator should use config defaults when not specified"""
        with patch("scripts.whale_detection_orchestrator.get_config") as mock_config:
            mock_cfg = Mock()
            mock_cfg.database.db_path = "/default/path/to/db.duckdb"
            mock_config.return_value = mock_cfg

            orch = WhaleDetectionOrchestrator()

            assert orch.db_path == "/default/path/to/db.duckdb"
            assert orch.ws_host == "0.0.0.0"
            assert orch.ws_port == 8765
            assert orch.mempool_ws_url == "ws://localhost:8999/ws/track-mempool-tx"
            assert orch.whale_threshold_btc == 100.0

    def test_orchestrator_config_override(self, temp_db):
        """Orchestrator should allow config overrides"""
        orch = WhaleDetectionOrchestrator(
            db_path=temp_db,
            ws_host="192.168.1.10",
            ws_port=9999,
            mempool_ws_url="ws://custom.mempool/tx",
            whale_threshold_btc=200.0,
        )

        assert orch.db_path == temp_db
        assert orch.ws_host == "192.168.1.10"
        assert orch.ws_port == 9999
        assert orch.mempool_ws_url == "ws://custom.mempool/tx"
        assert orch.whale_threshold_btc == 200.0


class TestOrchestratorCLI:
    """Test orchestrator command-line interface"""

    @pytest.mark.asyncio
    async def test_main_creates_orchestrator_with_args(self):
        """Main function should parse CLI args and create orchestrator"""
        test_args = [
            "whale_detection_orchestrator.py",
            "--db-path",
            "/custom/db.duckdb",
            "--ws-host",
            "0.0.0.0",
            "--ws-port",
            "7777",
            "--mempool-url",
            "ws://custom.mempool/track",
            "--whale-threshold",
            "250.0",
        ]

        with patch("sys.argv", test_args):
            with patch(
                "scripts.whale_detection_orchestrator.WhaleDetectionOrchestrator"
            ) as MockOrch:
                mock_orch_instance = AsyncMock()
                mock_orch_instance.start = AsyncMock(side_effect=KeyboardInterrupt())
                mock_orch_instance.stop = AsyncMock()
                mock_orch_instance.shutdown_requested = False
                MockOrch.return_value = mock_orch_instance

                # Import and run main
                from scripts.whale_detection_orchestrator import main

                try:
                    await main()
                except KeyboardInterrupt:
                    pass

                # Verify orchestrator was created with CLI args
                MockOrch.assert_called_once_with(
                    db_path="/custom/db.duckdb",
                    ws_host="0.0.0.0",
                    ws_port=7777,
                    mempool_ws_url="ws://custom.mempool/track",
                    whale_threshold_btc=250.0,
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
