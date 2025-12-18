"""
Unit tests for Absorption Rates calculator (spec-025).

TDD RED Phase: These tests are written BEFORE implementation.
All tests should FAIL until implementation is complete.

Test Coverage:
- T012: calculate_mined_supply function tests
- T013: calculate_absorption_rates function tests
- T018: API integration tests (added after implementation)
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from scripts.models.metrics_models import (
    AbsorptionRatesResult,
    WalletBand,
    WalletBandMetrics,
    WalletWavesResult,
)


# =============================================================================
# T012: calculate_mined_supply function tests
# =============================================================================


class TestCalculateMinedSupply:
    """Tests for calculate_mined_supply function."""

    def test_mined_supply_7d(self):
        """Test mined supply calculation for 7-day window."""
        from scripts.metrics.absorption_rates import calculate_mined_supply

        # 3.125 BTC/block × 144 blocks/day × 7 days = 3150 BTC
        result = calculate_mined_supply(window_days=7)

        expected = 3.125 * 144 * 7  # 3150.0 BTC
        assert abs(result - expected) < 0.01

    def test_mined_supply_30d(self):
        """Test mined supply calculation for 30-day window."""
        from scripts.metrics.absorption_rates import calculate_mined_supply

        # 3.125 BTC/block × 144 blocks/day × 30 days = 13500 BTC
        result = calculate_mined_supply(window_days=30)

        expected = 3.125 * 144 * 30  # 13500.0 BTC
        assert abs(result - expected) < 0.01

    def test_mined_supply_90d(self):
        """Test mined supply calculation for 90-day window."""
        from scripts.metrics.absorption_rates import calculate_mined_supply

        # 3.125 BTC/block × 144 blocks/day × 90 days = 40500 BTC
        result = calculate_mined_supply(window_days=90)

        expected = 3.125 * 144 * 90  # 40500.0 BTC
        assert abs(result - expected) < 0.01

    def test_mined_supply_invalid_window(self):
        """Test that invalid window raises ValueError."""
        from scripts.metrics.absorption_rates import calculate_mined_supply

        with pytest.raises(ValueError, match="window_days must be positive"):
            calculate_mined_supply(window_days=0)

        with pytest.raises(ValueError, match="window_days must be positive"):
            calculate_mined_supply(window_days=-7)


# =============================================================================
# T013: calculate_absorption_rates function tests
# =============================================================================


class TestCalculateAbsorptionRates:
    """Tests for calculate_absorption_rates function."""

    def test_basic_absorption(
        self,
        mock_duckdb_connection,
        sample_wallet_waves_current,
        sample_wallet_waves_historical,
    ):
        """Test basic absorption rate calculation."""
        from scripts.metrics.absorption_rates import calculate_absorption_rates

        result = calculate_absorption_rates(
            conn=mock_duckdb_connection,
            current_snapshot=sample_wallet_waves_current,
            historical_snapshot=sample_wallet_waves_historical,
            window_days=30,
        )

        assert isinstance(result, AbsorptionRatesResult)
        assert result.window_days == 30
        assert len(result.bands) == 6
        assert result.has_historical_data is True

        # Verify mined supply calculation
        expected_mined = 3.125 * 144 * 30  # 13500 BTC
        assert abs(result.mined_supply_btc - expected_mined) < 0.01

    def test_no_historical_data(
        self, mock_duckdb_connection, sample_wallet_waves_current
    ):
        """Test handling when historical snapshot is unavailable."""
        from scripts.metrics.absorption_rates import calculate_absorption_rates

        result = calculate_absorption_rates(
            conn=mock_duckdb_connection,
            current_snapshot=sample_wallet_waves_current,
            historical_snapshot=None,
            window_days=30,
        )

        assert isinstance(result, AbsorptionRatesResult)
        assert result.has_historical_data is False

        # All absorption rates should be None
        for band_metric in result.bands:
            assert band_metric.absorption_rate is None

    def test_dominant_absorber_selection(
        self,
        mock_duckdb_connection,
        sample_wallet_waves_current,
        sample_wallet_waves_historical_whale_dominant,
    ):
        """Test correct identification of dominant absorber."""
        from scripts.metrics.absorption_rates import calculate_absorption_rates

        result = calculate_absorption_rates(
            conn=mock_duckdb_connection,
            current_snapshot=sample_wallet_waves_current,
            historical_snapshot=sample_wallet_waves_historical_whale_dominant,
            window_days=30,
        )

        # Whale band should have highest absorption (supply increased most)
        assert result.dominant_absorber == WalletBand.WHALE

    def test_retail_vs_institutional(
        self,
        mock_duckdb_connection,
        sample_wallet_waves_current,
        sample_wallet_waves_historical,
    ):
        """Test retail vs institutional absorption aggregation."""
        from scripts.metrics.absorption_rates import calculate_absorption_rates

        result = calculate_absorption_rates(
            conn=mock_duckdb_connection,
            current_snapshot=sample_wallet_waves_current,
            historical_snapshot=sample_wallet_waves_historical,
            window_days=30,
        )

        # Verify aggregation
        retail_bands = [WalletBand.SHRIMP, WalletBand.CRAB, WalletBand.FISH]
        institutional_bands = [WalletBand.SHARK, WalletBand.WHALE, WalletBand.HUMPBACK]

        # Calculate expected retail absorption
        retail_total = sum(
            b.supply_delta_btc for b in result.bands if b.band in retail_bands
        )
        institutional_total = sum(
            b.supply_delta_btc for b in result.bands if b.band in institutional_bands
        )

        # Verify the calculation method (absorption rate = delta / mined)
        mined = result.mined_supply_btc
        if mined > 0:
            expected_retail_rate = retail_total / mined
            expected_institutional_rate = institutional_total / mined

            assert abs(result.retail_absorption - expected_retail_rate) < 0.01
            assert (
                abs(result.institutional_absorption - expected_institutional_rate)
                < 0.01
            )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_duckdb_connection():
    """Create a mock DuckDB connection for testing."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.execute.return_value = mock_cursor
    return mock_conn


def _create_wallet_waves_result(
    supply_by_band: dict[WalletBand, float],
) -> WalletWavesResult:
    """Helper to create WalletWavesResult from supply dict."""
    total = sum(supply_by_band.values())
    bands = []

    for band in WalletBand:
        supply = supply_by_band.get(band, 0.0)
        bands.append(
            WalletBandMetrics(
                band=band,
                supply_btc=supply,
                supply_pct=(supply / total * 100) if total > 0 else 0.0,
                address_count=int(supply / 10),  # Arbitrary for testing
                avg_balance=10.0,  # Arbitrary for testing
            )
        )

    retail_pct = sum(
        b.supply_pct
        for b in bands
        if b.band in [WalletBand.SHRIMP, WalletBand.CRAB, WalletBand.FISH]
    )
    institutional_pct = sum(
        b.supply_pct
        for b in bands
        if b.band in [WalletBand.SHARK, WalletBand.WHALE, WalletBand.HUMPBACK]
    )

    return WalletWavesResult(
        timestamp=datetime(2025, 12, 17, 12, 0, 0),
        block_height=876543,
        total_supply_btc=total,
        bands=bands,
        retail_supply_pct=retail_pct,
        institutional_supply_pct=institutional_pct,
        address_count_total=int(total / 10),
        null_address_btc=1000.0,
        confidence=0.85,
    )


@pytest.fixture
def sample_wallet_waves_current():
    """Create current snapshot for testing."""
    return _create_wallet_waves_result(
        {
            WalletBand.SHRIMP: 1010000.0,  # +10k from historical
            WalletBand.CRAB: 2005000.0,  # +5k from historical
            WalletBand.FISH: 3002000.0,  # +2k from historical
            WalletBand.SHARK: 4003000.0,  # +3k from historical
            WalletBand.WHALE: 5004000.0,  # +4k from historical
            WalletBand.HUMPBACK: 5003000.0,  # +3k from historical
        }
    )


@pytest.fixture
def sample_wallet_waves_historical():
    """Create historical snapshot (30 days ago) for testing."""
    return _create_wallet_waves_result(
        {
            WalletBand.SHRIMP: 1000000.0,
            WalletBand.CRAB: 2000000.0,
            WalletBand.FISH: 3000000.0,
            WalletBand.SHARK: 4000000.0,
            WalletBand.WHALE: 5000000.0,
            WalletBand.HUMPBACK: 5000000.0,
        }
    )


@pytest.fixture
def sample_wallet_waves_historical_whale_dominant():
    """Create historical snapshot where whale absorption will be dominant."""
    # Set up so whale band has biggest increase when compared to current
    return _create_wallet_waves_result(
        {
            WalletBand.SHRIMP: 1009000.0,  # Only +1k increase
            WalletBand.CRAB: 2004000.0,  # Only +1k increase
            WalletBand.FISH: 3001000.0,  # Only +1k increase
            WalletBand.SHARK: 4002000.0,  # Only +1k increase
            WalletBand.WHALE: 4984000.0,  # +20k increase (dominant)
            WalletBand.HUMPBACK: 5002000.0,  # Only +1k increase
        }
    )


# =============================================================================
# T018: API Integration Tests (added after endpoint implementation)
# =============================================================================


class TestAbsorptionRatesAPI:
    """API integration tests for absorption rates endpoints.

    These tests require a running API server and database.
    Marked as integration tests (skip in CI without DB).
    """

    @pytest.mark.integration
    def test_absorption_rates_api_endpoint(self, client):
        """Test GET /api/metrics/absorption-rates endpoint."""
        response = client.get("/api/metrics/absorption-rates")

        # May return 404 if DB not populated, or 200 on success
        assert response.status_code in [200, 404, 503]

        if response.status_code == 200:
            data = response.json()
            assert "timestamp" in data
            assert "block_height" in data
            assert "window_days" in data
            assert "bands" in data
            assert len(data["bands"]) == 6
            assert "dominant_absorber" in data
            assert "retail_absorption" in data
            assert "institutional_absorption" in data

    @pytest.mark.integration
    def test_absorption_rates_window_parameter(self, client):
        """Test window parameter validation."""
        # Valid windows
        for window in ["7d", "30d", "90d"]:
            response = client.get(f"/api/metrics/absorption-rates?window={window}")
            # May return 404 if DB not populated, or 200 on success
            assert response.status_code in [200, 404, 503]

        # Invalid window should return 422 (validation error)
        response = client.get("/api/metrics/absorption-rates?window=15d")
        assert response.status_code == 422


@pytest.fixture
def client():
    """Create test client for API tests."""
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)
