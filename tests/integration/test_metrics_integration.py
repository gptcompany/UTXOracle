"""
Integration Tests for On-Chain Metrics (spec-007).

Tests end-to-end flow from transaction data through metrics calculation
to API endpoint response.

Tasks:
- T031: Integration test for metrics pipeline

Run:
    uv run pytest tests/integration/test_metrics_integration.py -v
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch

from scripts.metrics import save_metrics_to_db, load_metrics_from_db, get_latest_metrics
from scripts.metrics.tx_volume import calculate_tx_volume
from scripts.metrics.active_addresses import count_active_addresses
from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion
from scripts.models.metrics_models import OnChainMetricsBundle


# =============================================================================
# T031: Metrics Pipeline Integration Test
# =============================================================================


class TestMetricsPipelineIntegration:
    """Test complete metrics calculation pipeline."""

    @pytest.fixture
    def sample_block_transactions(self):
        """Realistic block transactions for integration testing."""
        return [
            {
                "txid": f"tx{i:04d}",
                "vin": [
                    {
                        "prevout": {
                            "scriptpubkey_address": f"bc1qsender{i % 100:03d}",
                            "value": 100000000 + i * 1000000,  # 1.0+ BTC
                        }
                    }
                ],
                "vout": [
                    {
                        "scriptpubkey_address": f"bc1qreceiver{i:04d}",
                        "value": 90000000 + i * 900000,  # ~0.9 BTC (payment)
                    },
                    {
                        "scriptpubkey_address": f"bc1qchange{i:04d}",
                        "value": 9000000,  # 0.09 BTC (change <10%)
                    },
                ],
            }
            for i in range(100)  # 100 transactions
        ]

    @pytest.fixture
    def whale_signal(self):
        """Simulated whale accumulation signal."""
        return {"vote": 0.8, "confidence": 0.85}

    @pytest.fixture
    def utxo_signal(self):
        """Simulated UTXOracle price signal."""
        return {"vote": 0.6, "confidence": 0.90, "price": 95000.0}

    def test_full_metrics_calculation_pipeline(
        self, sample_block_transactions, whale_signal, utxo_signal
    ):
        """
        Test complete metrics calculation from transactions to bundle.

        Flow:
        1. Calculate TX Volume USD from transactions
        2. Count Active Addresses from transactions
        3. Run Monte Carlo fusion on signals
        4. Bundle all metrics together
        """
        timestamp = datetime.now(timezone.utc)

        # Step 1: TX Volume
        tx_volume = calculate_tx_volume(
            transactions=sample_block_transactions,
            utxoracle_price=utxo_signal["price"],
            confidence=utxo_signal["confidence"],
            timestamp=timestamp,
        )

        assert tx_volume.tx_count == 100
        assert tx_volume.tx_volume_btc > 0
        assert tx_volume.tx_volume_usd > 0
        assert tx_volume.low_confidence is False

        # Step 2: Active Addresses
        active_addresses = count_active_addresses(
            transactions=sample_block_transactions,
            block_height=870000,
            timestamp=timestamp,
        )

        assert active_addresses.unique_senders > 0
        assert active_addresses.unique_receivers > 0
        assert active_addresses.active_addresses_block > 0

        # Step 3: Monte Carlo Fusion
        mc_result = monte_carlo_fusion(
            whale_vote=whale_signal["vote"],
            whale_confidence=whale_signal["confidence"],
            utxo_vote=utxo_signal["vote"],
            utxo_confidence=utxo_signal["confidence"],
            n_samples=1000,
        )

        assert -1.0 <= mc_result.signal_mean <= 1.0
        assert mc_result.ci_lower <= mc_result.signal_mean <= mc_result.ci_upper
        assert mc_result.action in ["BUY", "SELL", "HOLD"]

        # Step 4: Bundle metrics
        bundle = OnChainMetricsBundle(
            timestamp=timestamp,
            monte_carlo=mc_result,
            active_addresses=active_addresses,
            tx_volume=tx_volume,
        )

        assert bundle.timestamp == timestamp
        assert bundle.monte_carlo is not None
        assert bundle.active_addresses is not None
        assert bundle.tx_volume is not None
        # block_height is in active_addresses, not bundle
        assert active_addresses.block_height == 870000


class TestMetricsDatabaseIntegration:
    """Test metrics database save/load cycle."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Temporary database path for testing."""
        db_path = str(tmp_path / "test_metrics.duckdb")
        # Initialize the database with the metrics table
        from scripts.init_metrics_db import init_metrics_db

        init_metrics_db(db_path)
        return db_path

    @pytest.fixture
    def sample_metrics(self):
        """Sample metrics for database testing."""
        timestamp = datetime.now(timezone.utc)
        return {
            "timestamp": timestamp,
            "monte_carlo": monte_carlo_fusion(0.8, 0.85, 0.6, 0.90),
            "active_addresses": count_active_addresses(
                [
                    {
                        "vin": [{"prevout": {"scriptpubkey_address": "bc1qsender"}}],
                        "vout": [{"scriptpubkey_address": "bc1qreceiver"}],
                    }
                ]
            ),
            "tx_volume": calculate_tx_volume(
                [{"vout": [{"value": 100000000}]}],
                utxoracle_price=95000.0,
                confidence=0.85,
            ),
        }

    def test_save_and_load_metrics(self, temp_db_path, sample_metrics):
        """Test metrics can be saved and loaded from database."""
        # Save metrics - pass .to_dict() for dataclass objects
        success = save_metrics_to_db(
            timestamp=sample_metrics["timestamp"],
            monte_carlo=sample_metrics["monte_carlo"].to_dict(),
            active_addresses=sample_metrics["active_addresses"].to_dict(),
            tx_volume=sample_metrics["tx_volume"].to_dict(),
            db_path=temp_db_path,
        )
        assert success is True

        # Load metrics
        loaded = load_metrics_from_db(limit=1, db_path=temp_db_path)
        assert len(loaded) == 1

        record = loaded[0]
        # Column names don't have prefixes in the DB
        assert record["signal_mean"] is not None
        assert record["active_addresses_block"] is not None
        assert record["tx_count"] is not None

    def test_get_latest_metrics(self, temp_db_path, sample_metrics):
        """Test retrieving latest metrics."""
        # Save metrics
        save_metrics_to_db(
            timestamp=sample_metrics["timestamp"],
            monte_carlo=sample_metrics["monte_carlo"].to_dict(),
            active_addresses=sample_metrics["active_addresses"].to_dict(),
            tx_volume=sample_metrics["tx_volume"].to_dict(),
            db_path=temp_db_path,
        )

        # Get latest
        latest = get_latest_metrics(db_path=temp_db_path)
        assert latest is not None
        # Column names in DB don't have prefixes
        assert "signal_mean" in latest
        assert "active_addresses_block" in latest
        assert "tx_volume_usd" in latest


class TestAPIEndpointIntegration:
    """Test API endpoint integration with metrics."""

    @pytest.fixture
    def test_db_with_data(self, tmp_path):
        """Create test database with sample metrics data."""
        from scripts.init_metrics_db import init_metrics_db

        db_path = str(tmp_path / "test_api_metrics.duckdb")
        init_metrics_db(db_path)

        # Insert test data
        timestamp = datetime.now(timezone.utc)
        mc = monte_carlo_fusion(0.8, 0.85, 0.6, 0.90)
        aa = count_active_addresses(
            [
                {
                    "vin": [{"prevout": {"scriptpubkey_address": "bc1qsender"}}],
                    "vout": [{"scriptpubkey_address": "bc1qreceiver"}],
                }
            ],
            block_height=870000,
        )
        tv = calculate_tx_volume(
            [{"vout": [{"value": 150050000000}]}],  # 1500.5 BTC
            utxoracle_price=95000.0,
            confidence=0.85,
        )

        save_metrics_to_db(
            timestamp,
            mc.to_dict(),
            aa.to_dict(),
            tv.to_dict(),
            db_path,
        )

        return db_path

    def test_metrics_latest_endpoint_structure(self, test_db_with_data):
        """Test /api/metrics/latest returns expected structure."""
        import os
        from fastapi.testclient import TestClient
        from api.main import app

        # Override the DB path env var
        with patch.dict(os.environ, {"DUCKDB_PATH": test_db_with_data}):
            client = TestClient(app)
            response = client.get("/api/metrics/latest")

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "monte_carlo" in data
        assert "active_addresses" in data
        assert "tx_volume" in data

        # Check Monte Carlo fields
        mc = data["monte_carlo"]
        assert "signal_mean" in mc
        assert mc["action"] in ["BUY", "SELL", "HOLD"]

        # Check Active Addresses fields
        aa = data["active_addresses"]
        assert aa["block_height"] == 870000
        assert aa["active_addresses_block"] > 0

        # Check TX Volume fields
        tv = data["tx_volume"]
        assert tv["tx_volume_btc"] > 0
        assert tv["tx_volume_usd"] > 0

    def test_metrics_latest_no_data(self, tmp_path):
        """Test /api/metrics/latest when no data available."""
        import os
        from fastapi.testclient import TestClient
        from api.main import app
        from scripts.init_metrics_db import init_metrics_db

        # Create empty database
        db_path = str(tmp_path / "test_empty_metrics.duckdb")
        init_metrics_db(db_path)

        with patch.dict(os.environ, {"DUCKDB_PATH": db_path}):
            client = TestClient(app)
            response = client.get("/api/metrics/latest")

        assert response.status_code == 404
        # The API returns "No metrics found"
        assert "No metrics" in response.json()["detail"]


class TestMetricsPerformanceIntegration:
    """Test metrics calculation performance."""

    @pytest.fixture
    def large_transaction_set(self):
        """Large transaction set for performance testing."""
        return [
            {
                "txid": f"tx{i}",
                "vin": [
                    {
                        "prevout": {
                            "scriptpubkey_address": f"bc1qsender{i}",
                            "value": 100000000,
                        }
                    }
                ],
                "vout": [
                    {"scriptpubkey_address": f"bc1qreceiver{i}", "value": 90000000},
                    {"scriptpubkey_address": f"bc1qchange{i}", "value": 9000000},
                ],
            }
            for i in range(1000)
        ]

    def test_full_pipeline_under_200ms(self, large_transaction_set):
        """Test full metrics pipeline completes under 200ms for 1000 txs."""
        import time

        start = time.time()

        # Calculate all metrics
        tx_volume = calculate_tx_volume(
            large_transaction_set, utxoracle_price=95000.0, confidence=0.85
        )
        active_addresses = count_active_addresses(large_transaction_set)
        mc_result = monte_carlo_fusion(0.8, 0.85, 0.6, 0.90, n_samples=1000)

        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 200, f"Pipeline took {elapsed_ms:.1f}ms, expected <200ms"
        assert tx_volume.tx_count == 1000
        assert active_addresses.active_addresses_block > 0
        assert mc_result.action in ["BUY", "SELL", "HOLD"]
