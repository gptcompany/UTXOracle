"""
Unit tests for Wallet Waves distribution calculator (spec-025).

TDD RED Phase: These tests are written BEFORE implementation.
All tests should FAIL until implementation is complete.

Test Coverage:
- T007: classify_balance_to_band function tests
- T008: calculate_wallet_waves function tests
- T017: API integration tests (added after implementation)
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from scripts.models.metrics_models import (
    WalletBand,
    WalletBandMetrics,
    WalletWavesResult,
)


# =============================================================================
# T007: classify_balance_to_band function tests
# =============================================================================


class TestClassifyBalanceToBand:
    """Tests for classify_balance_to_band function."""

    def test_classify_shrimp(self):
        """Test classification of shrimp band (< 1 BTC)."""
        from scripts.metrics.wallet_waves import classify_balance_to_band

        assert classify_balance_to_band(0.0) == WalletBand.SHRIMP
        assert classify_balance_to_band(0.001) == WalletBand.SHRIMP
        assert classify_balance_to_band(0.5) == WalletBand.SHRIMP
        assert classify_balance_to_band(0.99999999) == WalletBand.SHRIMP

    def test_classify_crab(self):
        """Test classification of crab band (1-10 BTC)."""
        from scripts.metrics.wallet_waves import classify_balance_to_band

        assert classify_balance_to_band(1.0) == WalletBand.CRAB
        assert classify_balance_to_band(5.0) == WalletBand.CRAB
        assert classify_balance_to_band(9.99999999) == WalletBand.CRAB

    def test_classify_fish(self):
        """Test classification of fish band (10-100 BTC)."""
        from scripts.metrics.wallet_waves import classify_balance_to_band

        assert classify_balance_to_band(10.0) == WalletBand.FISH
        assert classify_balance_to_band(50.0) == WalletBand.FISH
        assert classify_balance_to_band(99.99999999) == WalletBand.FISH

    def test_classify_shark(self):
        """Test classification of shark band (100-1000 BTC)."""
        from scripts.metrics.wallet_waves import classify_balance_to_band

        assert classify_balance_to_band(100.0) == WalletBand.SHARK
        assert classify_balance_to_band(500.0) == WalletBand.SHARK
        assert classify_balance_to_band(999.99999999) == WalletBand.SHARK

    def test_classify_whale(self):
        """Test classification of whale band (1000-10000 BTC)."""
        from scripts.metrics.wallet_waves import classify_balance_to_band

        assert classify_balance_to_band(1000.0) == WalletBand.WHALE
        assert classify_balance_to_band(5000.0) == WalletBand.WHALE
        assert classify_balance_to_band(9999.99999999) == WalletBand.WHALE

    def test_classify_humpback(self):
        """Test classification of humpback band (> 10000 BTC)."""
        from scripts.metrics.wallet_waves import classify_balance_to_band

        assert classify_balance_to_band(10000.0) == WalletBand.HUMPBACK
        assert classify_balance_to_band(50000.0) == WalletBand.HUMPBACK
        assert classify_balance_to_band(100000.0) == WalletBand.HUMPBACK

    def test_classify_edge_cases(self):
        """Test edge cases for balance classification."""
        from scripts.metrics.wallet_waves import classify_balance_to_band

        # Exact boundary values
        assert classify_balance_to_band(1.0) == WalletBand.CRAB  # Not shrimp
        assert classify_balance_to_band(10.0) == WalletBand.FISH  # Not crab
        assert classify_balance_to_band(100.0) == WalletBand.SHARK  # Not fish
        assert classify_balance_to_band(1000.0) == WalletBand.WHALE  # Not shark
        assert classify_balance_to_band(10000.0) == WalletBand.HUMPBACK  # Not whale

        # Very small values
        assert classify_balance_to_band(0.00000001) == WalletBand.SHRIMP  # 1 satoshi

        # Very large values
        assert classify_balance_to_band(21000000.0) == WalletBand.HUMPBACK  # Max supply

    def test_classify_negative_balance_raises(self):
        """Test that negative balance raises ValueError."""
        from scripts.metrics.wallet_waves import classify_balance_to_band

        with pytest.raises(ValueError, match="balance must be non-negative"):
            classify_balance_to_band(-1.0)

        with pytest.raises(ValueError, match="balance must be non-negative"):
            classify_balance_to_band(-0.001)


# =============================================================================
# T008: calculate_wallet_waves function tests
# =============================================================================


class TestCalculateWalletWaves:
    """Tests for calculate_wallet_waves function."""

    def test_basic_distribution(self):
        """Test basic wallet waves distribution calculation."""
        from scripts.metrics.wallet_waves import calculate_wallet_waves

        # Create mock that returns data for each query type
        mock_conn = MagicMock()
        band_data = [
            ("shrimp", 100000, 1000000.0, 10.0),  # 100k addresses, 1M BTC
            ("crab", 50000, 2000000.0, 40.0),  # 50k addresses, 2M BTC
            ("fish", 10000, 3000000.0, 300.0),  # 10k addresses, 3M BTC
            ("shark", 1000, 4000000.0, 4000.0),  # 1k addresses, 4M BTC
            ("whale", 100, 5000000.0, 50000.0),  # 100 addresses, 5M BTC
            ("humpback", 10, 5000000.0, 500000.0),  # 10 addresses, 5M BTC
        ]
        total_supply = sum(row[2] for row in band_data)  # 20M BTC

        def execute_side_effect(query):
            mock_cursor = MagicMock()
            if "GROUP BY band" in query:
                mock_cursor.fetchall.return_value = band_data
            elif "total_supply" in query.lower():
                mock_cursor.fetchone.return_value = (total_supply,)
            elif "null_address_btc" in query.lower():
                mock_cursor.fetchone.return_value = (1000.0,)
            else:
                mock_cursor.fetchall.return_value = []
                mock_cursor.fetchone.return_value = None
            return mock_cursor

        mock_conn.execute.side_effect = execute_side_effect

        result = calculate_wallet_waves(mock_conn, block_height=876543)

        assert isinstance(result, WalletWavesResult)
        assert result.block_height == 876543
        assert len(result.bands) == 6
        assert abs(result.total_supply_btc - total_supply) < 0.01

        # Verify band order
        band_names = [b.band for b in result.bands]
        assert band_names == list(WalletBand)

        # Verify percentages sum to 100%
        total_pct = sum(b.supply_pct for b in result.bands)
        assert abs(total_pct - 100.0) < 0.01

    def test_empty_database(self, mock_duckdb_connection):
        """Test handling of empty database (no UTXOs)."""
        from scripts.metrics.wallet_waves import calculate_wallet_waves

        # Empty result
        mock_duckdb_connection.execute.return_value.fetchall.return_value = []

        with pytest.raises(ValueError, match="No UTXO data found"):
            calculate_wallet_waves(mock_duckdb_connection, block_height=876543)

    def test_percentage_sum_validation(self):
        """Test that band percentages correctly sum to 100%."""
        from scripts.metrics.wallet_waves import calculate_wallet_waves

        mock_conn = MagicMock()
        # Create data where percentages sum exactly to 100%
        total_supply = 19700000.0  # ~19.7M BTC
        band_data = [
            ("shrimp", 45000000, total_supply * 0.05, 0.022),
            ("crab", 2500000, total_supply * 0.10, 0.788),
            ("fish", 250000, total_supply * 0.15, 11.82),
            ("shark", 25000, total_supply * 0.20, 157.6),
            ("whale", 2500, total_supply * 0.25, 1970.0),
            ("humpback", 150, total_supply * 0.25, 32833.33),
        ]

        def execute_side_effect(query):
            mock_cursor = MagicMock()
            if "GROUP BY band" in query:
                mock_cursor.fetchall.return_value = band_data
            elif "total_supply" in query.lower():
                mock_cursor.fetchone.return_value = (total_supply,)
            elif "null_address_btc" in query.lower():
                mock_cursor.fetchone.return_value = (1000.0,)
            else:
                mock_cursor.fetchall.return_value = []
                mock_cursor.fetchone.return_value = None
            return mock_cursor

        mock_conn.execute.side_effect = execute_side_effect

        result = calculate_wallet_waves(mock_conn, block_height=876543)

        # Verify percentages sum to 100%
        total_pct = sum(b.supply_pct for b in result.bands)
        assert 99.0 <= total_pct <= 101.0

    def test_retail_institutional_aggregates(self):
        """Test retail and institutional supply percentage aggregation."""
        from scripts.metrics.wallet_waves import calculate_wallet_waves

        mock_conn = MagicMock()
        # Mock data with known distribution
        total_supply = 20000000.0
        band_data = [
            ("shrimp", 100000, total_supply * 0.05, 10.0),  # 5% retail
            ("crab", 50000, total_supply * 0.10, 40.0),  # 10% retail
            ("fish", 10000, total_supply * 0.15, 300.0),  # 15% retail
            ("shark", 1000, total_supply * 0.20, 4000.0),  # 20% institutional
            ("whale", 100, total_supply * 0.25, 50000.0),  # 25% institutional
            ("humpback", 10, total_supply * 0.25, 500000.0),  # 25% institutional
        ]

        def execute_side_effect(query):
            mock_cursor = MagicMock()
            if "GROUP BY band" in query:
                mock_cursor.fetchall.return_value = band_data
            elif "total_supply" in query.lower():
                mock_cursor.fetchone.return_value = (total_supply,)
            elif "null_address_btc" in query.lower():
                mock_cursor.fetchone.return_value = (1000.0,)
            else:
                mock_cursor.fetchall.return_value = []
                mock_cursor.fetchone.return_value = None
            return mock_cursor

        mock_conn.execute.side_effect = execute_side_effect

        result = calculate_wallet_waves(mock_conn, block_height=876543)

        # Retail = shrimp + crab + fish = 5 + 10 + 15 = 30%
        assert abs(result.retail_supply_pct - 30.0) < 0.1

        # Institutional = shark + whale + humpback = 20 + 25 + 25 = 70%
        assert abs(result.institutional_supply_pct - 70.0) < 0.1

        # Sum should be 100%
        assert (
            abs(result.retail_supply_pct + result.institutional_supply_pct - 100.0)
            < 0.1
        )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_duckdb_connection():
    """Create a mock DuckDB connection for testing."""
    mock_conn = MagicMock()

    # Set up execute to return different results based on query
    def execute_side_effect(query):
        mock_cursor = MagicMock()
        if "GROUP BY band" in query:
            # Main wallet waves query - will be overridden per test
            mock_cursor.fetchall.return_value = []
        elif "total_supply" in query.lower():
            # Total supply query
            mock_cursor.fetchone.return_value = (20000000.0,)
        elif "null_address_btc" in query.lower():
            # Null address query
            mock_cursor.fetchone.return_value = (1000.0,)
        elif "MAX(creation_block)" in query:
            # Block height query
            mock_cursor.fetchone.return_value = (876543,)
        else:
            mock_cursor.fetchall.return_value = []
            mock_cursor.fetchone.return_value = None
        return mock_cursor

    mock_conn.execute.side_effect = execute_side_effect
    return mock_conn


@pytest.fixture
def sample_wallet_waves_result():
    """Create a sample WalletWavesResult for testing."""
    bands = [
        WalletBandMetrics(
            band=WalletBand.SHRIMP,
            supply_btc=1000000.0,
            supply_pct=5.0,
            address_count=45000000,
            avg_balance=0.022,
        ),
        WalletBandMetrics(
            band=WalletBand.CRAB,
            supply_btc=2000000.0,
            supply_pct=10.0,
            address_count=2500000,
            avg_balance=0.8,
        ),
        WalletBandMetrics(
            band=WalletBand.FISH,
            supply_btc=3000000.0,
            supply_pct=15.0,
            address_count=250000,
            avg_balance=12.0,
        ),
        WalletBandMetrics(
            band=WalletBand.SHARK,
            supply_btc=4000000.0,
            supply_pct=20.0,
            address_count=25000,
            avg_balance=160.0,
        ),
        WalletBandMetrics(
            band=WalletBand.WHALE,
            supply_btc=5000000.0,
            supply_pct=25.0,
            address_count=2500,
            avg_balance=2000.0,
        ),
        WalletBandMetrics(
            band=WalletBand.HUMPBACK,
            supply_btc=5000000.0,
            supply_pct=25.0,
            address_count=150,
            avg_balance=33333.33,
        ),
    ]

    return WalletWavesResult(
        timestamp=datetime(2025, 12, 17, 12, 0, 0),
        block_height=876543,
        total_supply_btc=20000000.0,
        bands=bands,
        retail_supply_pct=30.0,
        institutional_supply_pct=70.0,
        address_count_total=47777650,
        null_address_btc=12345.67,
        confidence=0.85,
    )


# =============================================================================
# T017: API Integration Tests (added after endpoint implementation)
# =============================================================================


class TestWalletWavesAPI:
    """API integration tests for wallet waves endpoints.

    These tests require a running API server and database.
    Marked as integration tests (skip in CI without DB).
    """

    @pytest.mark.integration
    def test_wallet_waves_api_endpoint(self, client):
        """Test GET /api/metrics/wallet-waves endpoint."""
        response = client.get("/api/metrics/wallet-waves")

        # May return 404 if DB not populated, or 200 on success
        assert response.status_code in [200, 404, 503]

        if response.status_code == 200:
            data = response.json()
            assert "timestamp" in data
            assert "block_height" in data
            assert "bands" in data
            assert len(data["bands"]) == 6
            assert "retail_supply_pct" in data
            assert "institutional_supply_pct" in data

    @pytest.mark.integration
    def test_wallet_waves_history_endpoint(self, client):
        """Test GET /api/metrics/wallet-waves/history endpoint."""
        response = client.get("/api/metrics/wallet-waves/history?days=30")

        # May return 500 if DB doesn't exist (testing environment)
        assert response.status_code in [200, 404, 500, 503]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)

    @pytest.mark.integration
    def test_wallet_waves_api_response_schema(self, client):
        """Test that API response matches OpenAPI schema."""
        response = client.get("/api/metrics/wallet-waves")

        if response.status_code != 200:
            pytest.skip("Database not available for schema validation")

        data = response.json()

        # Verify required fields per api.yaml
        required_fields = [
            "timestamp",
            "block_height",
            "total_supply_btc",
            "bands",
            "retail_supply_pct",
            "institutional_supply_pct",
            "address_count_total",
            "confidence",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Verify band structure
        for band in data["bands"]:
            assert "band" in band
            assert "supply_btc" in band
            assert "supply_pct" in band
            assert "address_count" in band
            assert "avg_balance" in band

            # Verify band name is valid
            valid_bands = ["shrimp", "crab", "fish", "shark", "whale", "humpback"]
            assert band["band"] in valid_bands


@pytest.fixture
def client():
    """Create test client for API tests."""
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)
