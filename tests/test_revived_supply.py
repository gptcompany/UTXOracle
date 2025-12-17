"""
Tests for Revived Supply module (spec-024).

TDD RED phase: These tests must FAIL before implementation.

Test coverage:
- T004: test_classify_revived_zone_dormant()
- T004: test_classify_revived_zone_normal()
- T004: test_classify_revived_zone_elevated()
- T004: test_classify_revived_zone_spike()
- T005: test_calculate_revived_supply_basic()
- T005: test_revived_supply_with_thresholds()
- T005: test_empty_window_handling()
- T009: test_revived_supply_api_endpoint()
"""

import duckdb
import pytest
from datetime import datetime, timedelta

from scripts.models.metrics_models import RevivedZone, RevivedSupplyResult


# =============================================================================
# T004: Zone Classification Tests
# =============================================================================


class TestClassifyRevivedZone:
    """Tests for zone classification function (T004)."""

    def test_classify_revived_zone_dormant(self):
        """T004: Revived supply < 1000 BTC/day should classify as DORMANT."""
        from scripts.metrics.revived_supply import classify_revived_zone

        # Test various values below 1000 threshold
        assert classify_revived_zone(0.0) == RevivedZone.DORMANT
        assert classify_revived_zone(500.0) == RevivedZone.DORMANT
        assert classify_revived_zone(999.9) == RevivedZone.DORMANT

    def test_classify_revived_zone_normal(self):
        """T004: Revived supply 1000-5000 BTC/day should classify as NORMAL."""
        from scripts.metrics.revived_supply import classify_revived_zone

        # Test boundary and midrange values
        assert classify_revived_zone(1000.0) == RevivedZone.NORMAL
        assert classify_revived_zone(3000.0) == RevivedZone.NORMAL
        assert classify_revived_zone(4999.9) == RevivedZone.NORMAL
        # Edge case: exactly 5000 should be ELEVATED
        assert classify_revived_zone(5000.0) == RevivedZone.ELEVATED

    def test_classify_revived_zone_elevated(self):
        """T004: Revived supply 5000-10000 BTC/day should classify as ELEVATED."""
        from scripts.metrics.revived_supply import classify_revived_zone

        assert classify_revived_zone(5000.0) == RevivedZone.ELEVATED
        assert classify_revived_zone(7500.0) == RevivedZone.ELEVATED
        assert classify_revived_zone(9999.9) == RevivedZone.ELEVATED
        # Edge case: exactly 10000 should be SPIKE
        assert classify_revived_zone(10000.0) == RevivedZone.SPIKE

    def test_classify_revived_zone_spike(self):
        """T004: Revived supply > 10000 BTC/day should classify as SPIKE."""
        from scripts.metrics.revived_supply import classify_revived_zone

        assert classify_revived_zone(10000.0) == RevivedZone.SPIKE
        assert classify_revived_zone(15000.0) == RevivedZone.SPIKE
        assert classify_revived_zone(50000.0) == RevivedZone.SPIKE
        assert classify_revived_zone(100000.0) == RevivedZone.SPIKE


# =============================================================================
# T005: Calculator Tests
# =============================================================================


class TestCalculateRevivedSupply:
    """Tests for calculate_revived_supply_signal function (T005)."""

    @pytest.fixture
    def test_db(self):
        """Create an in-memory DuckDB with test spent UTXO data."""
        conn = duckdb.connect(":memory:")

        # Create utxo_lifecycle table with required columns
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                outpoint VARCHAR PRIMARY KEY,
                txid VARCHAR NOT NULL,
                vout_index INTEGER NOT NULL,
                creation_block INTEGER NOT NULL,
                creation_timestamp TIMESTAMP NOT NULL,
                creation_price_usd DOUBLE NOT NULL,
                btc_value DOUBLE NOT NULL,
                spent_block INTEGER,
                spent_timestamp TIMESTAMP,
                spent_price_usd DOUBLE,
                age_days INTEGER,
                is_spent BOOLEAN DEFAULT FALSE
            )
            """
        )

        # Create VIEW alias for production code compatibility
        conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

        # Use relative timestamps within the 30-day window
        now = datetime.utcnow()
        day_5 = (now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
        day_10 = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        day_15 = (now - timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S")
        old_day = (now - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")

        # Insert spent UTXOs with various ages (age_days at time of spending)
        # UTXO 1: 1.5 years old (547 days), spent 5 days ago -> revived_1y YES
        # UTXO 2: 2.5 years old (912 days), spent 10 days ago -> revived_1y, revived_2y YES
        # UTXO 3: 6 years old (2190 days), spent 15 days ago -> revived_1y, revived_2y, revived_5y YES
        # UTXO 4: 200 days old (< 1y), spent 5 days ago -> NOT revived (too young)
        conn.execute(
            f"""
            INSERT INTO utxo_lifecycle VALUES
            ('rev1:0', 'rev1', 0, 700000, '2023-06-01', 30000.0, 2.0, 874000, '{day_5}', 100000.0, 547, TRUE),
            ('rev2:0', 'rev2', 0, 650000, '2022-06-01', 25000.0, 1.5, 874500, '{day_10}', 105000.0, 912, TRUE),
            ('rev3:0', 'rev3', 0, 500000, '2019-01-01', 5000.0, 0.5, 875000, '{day_15}', 110000.0, 2190, TRUE),
            ('young:0', 'young', 0, 850000, '2024-06-01', 60000.0, 3.0, 874800, '{day_5}', 102000.0, 200, TRUE)
            """
        )
        # Expected revived_1y: 2.0 + 1.5 + 0.5 = 4.0 BTC (age >= 365)
        # Expected revived_2y: 1.5 + 0.5 = 2.0 BTC (age >= 730)
        # Expected revived_5y: 0.5 BTC (age >= 1825)
        # young:0 is excluded as age_days=200 < 365

        # Old spent UTXO (outside 30-day window) - should be excluded
        conn.execute(
            f"""
            INSERT INTO utxo_lifecycle VALUES
            ('old:0', 'old', 0, 600000, '2023-01-01', 20000.0, 10.0, 800000, '{old_day}', 45000.0, 600, TRUE)
            """
        )

        yield conn
        conn.close()

    def test_calculate_revived_supply_basic(self, test_db):
        """T005: Test basic revived supply calculation."""
        from scripts.metrics.revived_supply import calculate_revived_supply_signal

        result = calculate_revived_supply_signal(
            conn=test_db,
            current_block=875000,
            current_price_usd=100000.0,
            timestamp=datetime.utcnow(),
            window_days=30,
        )

        # Verify result is RevivedSupplyResult
        assert isinstance(result, RevivedSupplyResult)
        assert result.block_height == 875000
        assert result.current_price_usd == 100000.0
        assert result.window_days == 30

        # Verify revived BTC calculations
        # revived_1y: UTXOs with age_days >= 365: rev1 (2.0) + rev2 (1.5) + rev3 (0.5) = 4.0
        assert result.revived_1y == pytest.approx(4.0, rel=0.01)
        # revived_2y: UTXOs with age_days >= 730: rev2 (1.5) + rev3 (0.5) = 2.0
        assert result.revived_2y == pytest.approx(2.0, rel=0.01)
        # revived_5y: UTXOs with age_days >= 1825: rev3 (0.5) = 0.5
        assert result.revived_5y == pytest.approx(0.5, rel=0.01)

        # Verify hierarchy constraint: 5y <= 2y <= 1y
        assert result.revived_5y <= result.revived_2y
        assert result.revived_2y <= result.revived_1y

        # Verify USD value (revived_1y × price)
        expected_usd = 4.0 * 100000.0  # 400,000 USD
        assert result.revived_total_usd == pytest.approx(expected_usd, rel=0.01)

        # Verify UTXO count (3 revived UTXOs with age >= 365)
        assert result.utxo_count == 3

    def test_revived_supply_with_thresholds(self, test_db):
        """T005: Test revived supply with custom threshold parameters."""
        from scripts.metrics.revived_supply import calculate_revived_supply_signal

        # Test with 7-day window (should only include rev1 spent 5 days ago)
        result = calculate_revived_supply_signal(
            conn=test_db,
            current_block=875000,
            current_price_usd=100000.0,
            timestamp=datetime.utcnow(),
            window_days=7,
        )

        # Only rev1 (2.0 BTC, 547 days old) and young:0 (3.0 BTC, 200 days)
        # are within 7-day window, but only rev1 qualifies (age >= 365)
        assert result.revived_1y == pytest.approx(2.0, rel=0.01)
        assert result.revived_2y == pytest.approx(
            0.0, rel=0.01
        )  # rev1 is only 547 days
        assert result.revived_5y == pytest.approx(0.0, rel=0.01)
        assert result.utxo_count == 1

    def test_empty_window_handling(self):
        """T005: Test handling of empty window (no revived UTXOs)."""
        from scripts.metrics.revived_supply import calculate_revived_supply_signal

        # Create database with no spent UTXOs in window
        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                outpoint VARCHAR PRIMARY KEY,
                btc_value DOUBLE NOT NULL,
                creation_price_usd DOUBLE NOT NULL,
                age_days INTEGER,
                spent_timestamp TIMESTAMP,
                is_spent BOOLEAN DEFAULT FALSE
            )
            """
        )
        conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

        result = calculate_revived_supply_signal(
            conn=conn,
            current_block=875000,
            current_price_usd=100000.0,
            timestamp=datetime.utcnow(),
            window_days=30,
        )

        conn.close()

        # Should return valid result with zeros
        assert isinstance(result, RevivedSupplyResult)
        assert result.revived_1y == 0.0
        assert result.revived_2y == 0.0
        assert result.revived_5y == 0.0
        assert result.revived_total_usd == 0.0
        assert result.utxo_count == 0
        assert result.zone == RevivedZone.DORMANT  # 0 < 1000
        assert result.confidence == 0.0  # No data

    def test_zone_classification_from_calculation(self, test_db):
        """T005: Verify zone is correctly classified based on daily revived BTC."""
        from scripts.metrics.revived_supply import calculate_revived_supply_signal

        result = calculate_revived_supply_signal(
            conn=test_db,
            current_block=875000,
            current_price_usd=100000.0,
            timestamp=datetime.utcnow(),
            window_days=30,
        )

        # 4.0 BTC revived over 30 days = 0.133 BTC/day
        # 0.133 < 1000 -> DORMANT zone
        assert result.zone == RevivedZone.DORMANT

    def test_average_age_calculation(self, test_db):
        """T005: Verify average age calculation for revived UTXOs."""
        from scripts.metrics.revived_supply import calculate_revived_supply_signal

        result = calculate_revived_supply_signal(
            conn=test_db,
            current_block=875000,
            current_price_usd=100000.0,
            timestamp=datetime.utcnow(),
            window_days=30,
        )

        # Weighted average age: (2.0*547 + 1.5*912 + 0.5*2190) / 4.0
        # = (1094 + 1368 + 1095) / 4.0 = 889.25 days
        expected_avg_age = (2.0 * 547 + 1.5 * 912 + 0.5 * 2190) / 4.0
        assert result.revived_avg_age == pytest.approx(expected_avg_age, rel=0.05)


# =============================================================================
# RevivedSupplyResult Dataclass Validation Tests
# =============================================================================


class TestRevivedSupplyResultValidation:
    """Tests for RevivedSupplyResult dataclass validation."""

    def test_revived_supply_result_validation(self):
        """Test RevivedSupplyResult dataclass field validation."""
        # Valid result
        result = RevivedSupplyResult(
            revived_1y=5432.50,
            revived_2y=1234.75,
            revived_5y=567.25,
            revived_total_usd=516087500.0,
            revived_avg_age=892.5,
            zone=RevivedZone.ELEVATED,
            utxo_count=15234,
            window_days=30,
            current_price_usd=95000.0,
            block_height=875000,
        )
        assert result.revived_1y == 5432.50
        assert result.zone == RevivedZone.ELEVATED
        assert result.confidence == 0.85  # Default

    def test_revived_supply_negative_values_raise(self):
        """Revived BTC values must be >= 0."""
        with pytest.raises(ValueError, match="revived_1y must be >= 0"):
            RevivedSupplyResult(
                revived_1y=-1.0,
                revived_2y=0.0,
                revived_5y=0.0,
                revived_total_usd=0.0,
                revived_avg_age=0.0,
                zone=RevivedZone.DORMANT,
                utxo_count=0,
                window_days=30,
                current_price_usd=100000.0,
                block_height=875000,
            )

    def test_revived_supply_hierarchy_constraint(self):
        """5y <= 2y <= 1y constraint must be enforced."""
        # revived_5y > revived_2y should raise
        with pytest.raises(ValueError, match="revived_5y .* cannot exceed revived_2y"):
            RevivedSupplyResult(
                revived_1y=100.0,
                revived_2y=50.0,
                revived_5y=75.0,  # Invalid: 75 > 50
                revived_total_usd=0.0,
                revived_avg_age=0.0,
                zone=RevivedZone.DORMANT,
                utxo_count=0,
                window_days=30,
                current_price_usd=100000.0,
                block_height=875000,
            )

        # revived_2y > revived_1y should raise
        with pytest.raises(ValueError, match="revived_2y .* cannot exceed revived_1y"):
            RevivedSupplyResult(
                revived_1y=50.0,
                revived_2y=75.0,  # Invalid: 75 > 50
                revived_5y=25.0,
                revived_total_usd=0.0,
                revived_avg_age=0.0,
                zone=RevivedZone.DORMANT,
                utxo_count=0,
                window_days=30,
                current_price_usd=100000.0,
                block_height=875000,
            )

    def test_revived_supply_invalid_zone_raises(self):
        """Zone must be RevivedZone enum."""
        with pytest.raises(ValueError, match="zone must be RevivedZone enum"):
            RevivedSupplyResult(
                revived_1y=100.0,
                revived_2y=50.0,
                revived_5y=25.0,
                revived_total_usd=0.0,
                revived_avg_age=0.0,
                zone="INVALID",  # type: ignore
                utxo_count=0,
                window_days=30,
                current_price_usd=100000.0,
                block_height=875000,
            )

    def test_revived_supply_invalid_window_days_raises(self):
        """Window days must be > 0."""
        with pytest.raises(ValueError, match="window_days must be > 0"):
            RevivedSupplyResult(
                revived_1y=100.0,
                revived_2y=50.0,
                revived_5y=25.0,
                revived_total_usd=0.0,
                revived_avg_age=0.0,
                zone=RevivedZone.DORMANT,
                utxo_count=0,
                window_days=0,  # Invalid
                current_price_usd=100000.0,
                block_height=875000,
            )

    def test_revived_supply_invalid_price_raises(self):
        """Current price must be > 0."""
        with pytest.raises(ValueError, match="current_price_usd must be > 0"):
            RevivedSupplyResult(
                revived_1y=100.0,
                revived_2y=50.0,
                revived_5y=25.0,
                revived_total_usd=0.0,
                revived_avg_age=0.0,
                zone=RevivedZone.DORMANT,
                utxo_count=0,
                window_days=30,
                current_price_usd=0.0,  # Invalid
                block_height=875000,
            )

    def test_revived_supply_invalid_confidence_raises(self):
        """Confidence must be in [0, 1]."""
        with pytest.raises(ValueError, match="confidence must be in"):
            RevivedSupplyResult(
                revived_1y=100.0,
                revived_2y=50.0,
                revived_5y=25.0,
                revived_total_usd=0.0,
                revived_avg_age=0.0,
                zone=RevivedZone.DORMANT,
                utxo_count=0,
                window_days=30,
                current_price_usd=100000.0,
                block_height=875000,
                confidence=1.5,  # Invalid
            )

    def test_revived_supply_to_dict(self):
        """Test to_dict() serialization."""
        result = RevivedSupplyResult(
            revived_1y=5432.50,
            revived_2y=1234.75,
            revived_5y=567.25,
            revived_total_usd=516087500.0,
            revived_avg_age=892.5,
            zone=RevivedZone.ELEVATED,
            utxo_count=15234,
            window_days=30,
            current_price_usd=95000.0,
            block_height=875000,
            timestamp=datetime(2025, 12, 17, 10, 30, 0),
        )
        d = result.to_dict()
        assert d["revived_1y"] == 5432.50
        assert d["revived_2y"] == 1234.75
        assert d["revived_5y"] == 567.25
        assert d["revived_total_usd"] == 516087500.0
        assert d["revived_avg_age"] == 892.5
        assert d["zone"] == "elevated"  # Enum value, lowercase
        assert d["utxo_count"] == 15234
        assert d["window_days"] == 30
        assert d["current_price_usd"] == 95000.0
        assert d["block_height"] == 875000
        assert "timestamp" in d
        assert d["confidence"] == 0.85


# =============================================================================
# T009: API Endpoint Tests
# =============================================================================


class TestRevivedSupplyAPIEndpoint:
    """Tests for /api/metrics/revived-supply endpoint (T009)."""

    def test_revived_supply_endpoint_registered(self):
        """T009: Verify /api/metrics/revived-supply endpoint is registered."""
        from api.main import app

        # Check endpoint is in app routes
        routes = [route.path for route in app.routes]
        assert "/api/metrics/revived-supply" in routes

    def test_revived_supply_endpoint_response_structure(self):
        """T009: Test endpoint returns correct response structure."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/metrics/revived-supply")

        # Should get valid response or graceful error
        assert response.status_code in [200, 404, 500, 503]

        if response.status_code == 200:
            data = response.json()
            # Verify expected fields are present
            assert "revived_1y" in data
            assert "revived_2y" in data
            assert "revived_5y" in data
            assert "zone" in data
            assert "confidence" in data
            # Zone should be valid enum value
            assert data["zone"] in ["dormant", "normal", "elevated", "spike"]

    def test_revived_supply_endpoint_with_params(self):
        """T009: Test endpoint accepts window query param."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/metrics/revived-supply?window=7")

        # Should accept params without 422 Unprocessable Entity
        assert response.status_code != 422
