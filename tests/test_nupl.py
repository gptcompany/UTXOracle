"""
Tests for NUPL Oscillator module (spec-022).

TDD RED phase: These tests must FAIL before implementation.

Test coverage:
- T003: test_classify_nupl_zone_capitulation()
- T004: test_classify_nupl_zone_hope_fear()
- T005: test_classify_nupl_zone_optimism()
- T006: test_classify_nupl_zone_belief()
- T007: test_classify_nupl_zone_euphoria()
- T008: test_nupl_result_validation()
- T009: test_calculate_nupl_signal_integration()
"""

import pytest
from datetime import datetime

from scripts.models.metrics_models import NUPLZone, NUPLResult


class TestClassifyNUPLZone:
    """Tests for zone classification function (T003-T007)."""

    def test_classify_nupl_zone_capitulation(self):
        """T003: NUPL < 0 should classify as CAPITULATION."""
        from scripts.metrics.nupl import classify_nupl_zone

        # Test various negative NUPL values
        assert classify_nupl_zone(-0.5) == NUPLZone.CAPITULATION
        assert classify_nupl_zone(-0.01) == NUPLZone.CAPITULATION
        assert classify_nupl_zone(-1.0) == NUPLZone.CAPITULATION

    def test_classify_nupl_zone_hope_fear(self):
        """T004: NUPL 0-0.25 should classify as HOPE_FEAR."""
        from scripts.metrics.nupl import classify_nupl_zone

        assert classify_nupl_zone(0.0) == NUPLZone.HOPE_FEAR
        assert classify_nupl_zone(0.1) == NUPLZone.HOPE_FEAR
        assert classify_nupl_zone(0.24) == NUPLZone.HOPE_FEAR
        # Edge case: exactly 0.25 should be OPTIMISM
        assert classify_nupl_zone(0.25) == NUPLZone.OPTIMISM

    def test_classify_nupl_zone_optimism(self):
        """T005: NUPL 0.25-0.5 should classify as OPTIMISM."""
        from scripts.metrics.nupl import classify_nupl_zone

        assert classify_nupl_zone(0.25) == NUPLZone.OPTIMISM
        assert classify_nupl_zone(0.35) == NUPLZone.OPTIMISM
        assert classify_nupl_zone(0.49) == NUPLZone.OPTIMISM
        # Edge case: exactly 0.5 should be BELIEF
        assert classify_nupl_zone(0.5) == NUPLZone.BELIEF

    def test_classify_nupl_zone_belief(self):
        """T006: NUPL 0.5-0.75 should classify as BELIEF."""
        from scripts.metrics.nupl import classify_nupl_zone

        assert classify_nupl_zone(0.5) == NUPLZone.BELIEF
        assert classify_nupl_zone(0.6) == NUPLZone.BELIEF
        assert classify_nupl_zone(0.74) == NUPLZone.BELIEF
        # Edge case: exactly 0.75 should be EUPHORIA
        assert classify_nupl_zone(0.75) == NUPLZone.EUPHORIA

    def test_classify_nupl_zone_euphoria(self):
        """T007: NUPL > 0.75 should classify as EUPHORIA."""
        from scripts.metrics.nupl import classify_nupl_zone

        assert classify_nupl_zone(0.75) == NUPLZone.EUPHORIA
        assert classify_nupl_zone(0.8) == NUPLZone.EUPHORIA
        assert classify_nupl_zone(0.95) == NUPLZone.EUPHORIA
        assert classify_nupl_zone(1.0) == NUPLZone.EUPHORIA


class TestNUPLResultValidation:
    """Tests for NUPLResult dataclass validation (T008)."""

    def test_nupl_result_validation(self):
        """T008: Test NUPLResult dataclass field validation."""
        # Valid result
        result = NUPLResult(
            nupl=0.42,
            zone=NUPLZone.OPTIMISM,
            market_cap_usd=2_100_000_000_000.0,
            realized_cap_usd=1_218_000_000_000.0,
            unrealized_profit_usd=882_000_000_000.0,
            pct_supply_in_profit=75.3,
            block_height=872500,
        )
        assert result.nupl == 0.42
        assert result.zone == NUPLZone.OPTIMISM
        assert result.confidence == 0.85  # Default

    def test_nupl_result_negative_market_cap_raises(self):
        """Market cap must be >= 0."""
        with pytest.raises(ValueError, match="market_cap_usd must be >= 0"):
            NUPLResult(
                nupl=0.42,
                zone=NUPLZone.OPTIMISM,
                market_cap_usd=-1.0,
                realized_cap_usd=1_000_000.0,
                unrealized_profit_usd=0.0,
                pct_supply_in_profit=50.0,
                block_height=872500,
            )

    def test_nupl_result_negative_realized_cap_raises(self):
        """Realized cap must be >= 0."""
        with pytest.raises(ValueError, match="realized_cap_usd must be >= 0"):
            NUPLResult(
                nupl=0.42,
                zone=NUPLZone.OPTIMISM,
                market_cap_usd=1_000_000.0,
                realized_cap_usd=-1.0,
                unrealized_profit_usd=0.0,
                pct_supply_in_profit=50.0,
                block_height=872500,
            )

    def test_nupl_result_invalid_confidence_raises(self):
        """Confidence must be in [0, 1]."""
        with pytest.raises(ValueError, match="confidence must be in"):
            NUPLResult(
                nupl=0.42,
                zone=NUPLZone.OPTIMISM,
                market_cap_usd=1_000_000.0,
                realized_cap_usd=500_000.0,
                unrealized_profit_usd=500_000.0,
                pct_supply_in_profit=50.0,
                block_height=872500,
                confidence=1.5,
            )

    def test_nupl_result_invalid_zone_raises(self):
        """Zone must be NUPLZone enum."""
        with pytest.raises(ValueError, match="zone must be NUPLZone enum"):
            NUPLResult(
                nupl=0.42,
                zone="INVALID",  # type: ignore
                market_cap_usd=1_000_000.0,
                realized_cap_usd=500_000.0,
                unrealized_profit_usd=500_000.0,
                pct_supply_in_profit=50.0,
                block_height=872500,
            )

    def test_nupl_result_invalid_pct_supply_raises(self):
        """B1: pct_supply_in_profit must be in [0, 100]."""
        # Test negative value
        with pytest.raises(ValueError, match="pct_supply_in_profit must be in"):
            NUPLResult(
                nupl=0.42,
                zone=NUPLZone.OPTIMISM,
                market_cap_usd=1_000_000.0,
                realized_cap_usd=500_000.0,
                unrealized_profit_usd=500_000.0,
                pct_supply_in_profit=-10.0,
                block_height=872500,
            )
        # Test value > 100
        with pytest.raises(ValueError, match="pct_supply_in_profit must be in"):
            NUPLResult(
                nupl=0.42,
                zone=NUPLZone.OPTIMISM,
                market_cap_usd=1_000_000.0,
                realized_cap_usd=500_000.0,
                unrealized_profit_usd=500_000.0,
                pct_supply_in_profit=150.0,
                block_height=872500,
            )

    def test_nupl_result_invalid_block_height_raises(self):
        """B2: block_height must be >= 0."""
        with pytest.raises(ValueError, match="block_height must be >= 0"):
            NUPLResult(
                nupl=0.42,
                zone=NUPLZone.OPTIMISM,
                market_cap_usd=1_000_000.0,
                realized_cap_usd=500_000.0,
                unrealized_profit_usd=500_000.0,
                pct_supply_in_profit=50.0,
                block_height=-1,
            )

    def test_nupl_result_to_dict(self):
        """Test to_dict() serialization."""
        result = NUPLResult(
            nupl=0.42,
            zone=NUPLZone.OPTIMISM,
            market_cap_usd=2_100_000_000_000.0,
            realized_cap_usd=1_218_000_000_000.0,
            unrealized_profit_usd=882_000_000_000.0,
            pct_supply_in_profit=75.3,
            block_height=872500,
            timestamp=datetime(2025, 12, 16, 10, 30, 0),
        )
        d = result.to_dict()
        assert d["nupl"] == 0.42
        assert d["zone"] == "OPTIMISM"
        assert d["market_cap_usd"] == 2_100_000_000_000.0
        assert d["realized_cap_usd"] == 1_218_000_000_000.0
        assert d["unrealized_profit_usd"] == 882_000_000_000.0
        assert d["pct_supply_in_profit"] == 75.3
        assert d["block_height"] == 872500
        assert "timestamp" in d
        assert d["confidence"] == 0.85


class TestCalculateNUPLSignal:
    """Integration tests for calculate_nupl_signal() (T009)."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock DuckDB connection with test data.

        The calculate_nupl_signal function makes two separate queries:
        1. calculate_realized_cap() - returns realized_cap_usd
        2. get_total_unspent_supply() - returns total_supply_btc

        We use side_effect to return different values for each call.
        """
        from unittest.mock import MagicMock

        mock = MagicMock()

        # Default values: realized_cap=1.218T, supply=20M BTC
        # Each execute().fetchone() returns a tuple with single value
        mock.execute.return_value.fetchone.side_effect = [
            (1_218_000_000_000.0,),  # realized_cap_usd (first query)
            (20_000_000.0,),  # total_supply_btc (second query)
        ]
        return mock

    def test_calculate_nupl_signal_integration(self, mock_conn):
        """T009: Test full NUPL calculation with mocked database."""
        from scripts.metrics.nupl import calculate_nupl_signal

        # Current price of $105,000
        current_price = 105_000.0
        block_height = 872500

        result = calculate_nupl_signal(
            conn=mock_conn,
            block_height=block_height,
            current_price_usd=current_price,
        )

        # Verify result is NUPLResult
        assert isinstance(result, NUPLResult)
        assert result.block_height == block_height

        # Market cap = supply × price = 20M × 105k = 2.1T
        expected_market_cap = 20_000_000.0 * 105_000.0
        assert result.market_cap_usd == expected_market_cap

        # Realized cap from mock
        assert result.realized_cap_usd == 1_218_000_000_000.0

        # NUPL = (Market Cap - Realized Cap) / Market Cap
        # = (2.1T - 1.218T) / 2.1T = 0.42 (OPTIMISM zone)
        assert 0.4 <= result.nupl <= 0.45  # Allow small floating point variance
        assert result.zone == NUPLZone.OPTIMISM

    def test_calculate_nupl_signal_capitulation_zone(self, mock_conn):
        """Test NUPL calculation resulting in CAPITULATION zone."""
        from scripts.metrics.nupl import calculate_nupl_signal

        # Set realized cap higher than market cap -> negative NUPL
        # Reset the side_effect for this test
        mock_conn.execute.return_value.fetchone.side_effect = [
            (3_000_000_000_000.0,),  # realized_cap_usd (higher than market cap)
            (20_000_000.0,),  # total_supply_btc
        ]

        result = calculate_nupl_signal(
            conn=mock_conn,
            block_height=872500,
            current_price_usd=100_000.0,  # Market cap = 2T < Realized cap 3T
        )

        assert result.nupl < 0
        assert result.zone == NUPLZone.CAPITULATION

    def test_calculate_nupl_signal_euphoria_zone(self, mock_conn):
        """Test NUPL calculation resulting in EUPHORIA zone."""
        from scripts.metrics.nupl import calculate_nupl_signal

        # Set realized cap low relative to market cap -> high NUPL
        mock_conn.execute.return_value.fetchone.side_effect = [
            (500_000_000_000.0,),  # realized_cap_usd (low)
            (20_000_000.0,),  # total_supply_btc
        ]

        result = calculate_nupl_signal(
            conn=mock_conn,
            block_height=872500,
            current_price_usd=100_000.0,  # Market cap = 2T >> Realized cap 0.5T
        )

        # NUPL = (2T - 0.5T) / 2T = 0.75 -> EUPHORIA
        assert result.nupl >= 0.75
        assert result.zone == NUPLZone.EUPHORIA

    def test_calculate_nupl_signal_zero_market_cap_handling(self, mock_conn):
        """Test graceful handling of zero market cap edge case."""
        from scripts.metrics.nupl import calculate_nupl_signal

        mock_conn.execute.return_value.fetchone.side_effect = [
            (0.0,),  # realized_cap_usd
            (0.0,),  # total_supply_btc (edge case: no supply)
        ]

        result = calculate_nupl_signal(
            conn=mock_conn,
            block_height=872500,
            current_price_usd=100_000.0,
        )

        # Should return a valid result with NUPL=0 in edge case
        assert isinstance(result, NUPLResult)
        assert result.nupl == 0.0
        assert result.zone == NUPLZone.HOPE_FEAR  # Default for 0.0


class TestNUPLAPIEndpoint:
    """Tests for /api/metrics/nupl endpoint (T016)."""

    def test_nupl_endpoint_response_model(self):
        """T016: Verify NUPLResponse Pydantic model is correctly defined."""
        from api.main import NUPLResponse
        from pydantic import ValidationError

        # Test valid response
        response = NUPLResponse(
            nupl=0.42,
            zone="OPTIMISM",
            market_cap_usd=2_100_000_000_000.0,
            realized_cap_usd=1_218_000_000_000.0,
            unrealized_profit_usd=882_000_000_000.0,
            pct_supply_in_profit=75.3,
            confidence=0.85,
            block_height=872500,
            timestamp="2025-12-16T10:30:00",
        )
        assert response.nupl == 0.42
        assert response.zone == "OPTIMISM"

        # Test missing required field raises error
        with pytest.raises(ValidationError):
            NUPLResponse(
                nupl=0.42,
                # Missing zone and other required fields
            )

    def test_nupl_endpoint_registered(self):
        """T016: Verify /api/metrics/nupl endpoint is registered in the app."""
        from fastapi.testclient import TestClient
        from api.main import app

        # Check endpoint is in app routes
        routes = [route.path for route in app.routes]
        assert "/api/metrics/nupl" in routes

        # Check endpoint returns expected error (503) when DB not available
        # This verifies the endpoint exists and handles errors correctly
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/metrics/nupl?current_price=105000")

        # Should get 503 (DB not available) or 404 (table not found)
        # rather than 404 (endpoint not found)
        assert response.status_code in [200, 404, 500, 503]
        # Verify it's not a "not found" error for the endpoint itself
        if response.status_code == 404:
            data = response.json()
            # Should be about table/schema, not about endpoint
            assert "UTXO" in data.get("detail", "") or "lifecycle" in data.get(
                "detail", ""
            )
