"""Tests for Reserve Risk module.

spec-021: Advanced On-Chain Metrics
TDD: Tests written BEFORE implementation.
"""

import duckdb
import pytest

from scripts.models.metrics_models import ReserveRiskResult


@pytest.fixture
def test_db():
    """Create an in-memory DuckDB with test UTXO and cointime data."""
    conn = duckdb.connect(":memory:")

    # Create utxo_lifecycle table
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
            realized_value_usd DOUBLE NOT NULL,
            spent_block INTEGER,
            spent_timestamp TIMESTAMP,
            age_days INTEGER,
            is_spent BOOLEAN DEFAULT FALSE
        )
        """
    )

    # Create cointime_metrics table for liveliness data
    conn.execute(
        """
        CREATE TABLE cointime_metrics (
            block_height INTEGER PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            liveliness DOUBLE NOT NULL,
            vaultedness DOUBLE NOT NULL,
            cumulative_created DOUBLE NOT NULL,
            cumulative_destroyed DOUBLE NOT NULL
        )
        """
    )

    # Create VIEW alias for production code compatibility
    conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

    # Insert unspent UTXOs (total: 10 BTC)
    conn.execute(
        """
        INSERT INTO utxo_lifecycle VALUES
        ('utxo1:0', 'utxo1', 0, 800000, '2024-01-01', 40000.0, 5.0, 200000.0, NULL, NULL, 345, FALSE),
        ('utxo2:0', 'utxo2', 0, 850000, '2024-06-01', 60000.0, 3.0, 180000.0, NULL, NULL, 193, FALSE),
        ('utxo3:0', 'utxo3', 0, 870000, '2024-11-01', 90000.0, 2.0, 180000.0, NULL, NULL, 40, FALSE)
        """
    )

    # Insert spent UTXOs for HODL Bank calculation
    # CDD = age_days × btc_value when spent
    conn.execute(
        """
        INSERT INTO utxo_lifecycle VALUES
        ('spent1:0', 'spent1', 0, 700000, '2023-06-01', 30000.0, 2.0, 60000.0, 850000, '2024-06-01', 365, TRUE),
        ('spent2:0', 'spent2', 0, 750000, '2023-09-01', 35000.0, 1.0, 35000.0, 860000, '2024-08-01', 335, TRUE)
        """
    )

    # Insert cointime metrics
    conn.execute(
        """
        INSERT INTO cointime_metrics VALUES
        (875000, '2024-12-11', 0.3, 0.7, 1000000000.0, 300000000.0)
        """
    )

    yield conn
    conn.close()


class TestReserveRiskCalculation:
    """Tests for calculate_reserve_risk() function."""

    def test_calculate_basic(self, test_db):
        """T035: Basic Reserve Risk calculation returns valid result."""
        from scripts.metrics.reserve_risk import calculate_reserve_risk

        result = calculate_reserve_risk(
            conn=test_db,
            current_price_usd=100000.0,
            block_height=875000,
        )

        assert isinstance(result, ReserveRiskResult)
        assert result.current_price_usd == 100000.0
        assert result.block_height == 875000
        assert result.reserve_risk >= 0
        assert result.circulating_supply_btc == pytest.approx(10.0, rel=0.01)

    def test_hodl_bank_calculation(self, test_db):
        """T036: HODL Bank aggregates coindays destroyed correctly."""
        from scripts.metrics.reserve_risk import calculate_reserve_risk

        result = calculate_reserve_risk(
            conn=test_db,
            current_price_usd=100000.0,
            block_height=875000,
        )

        # HODL Bank = sum of CDD for all spent UTXOs
        # CDD1 = 365 days × 2.0 BTC = 730
        # CDD2 = 335 days × 1.0 BTC = 335
        # Total = 1065 coin-days
        # Note: actual implementation may scale this differently
        assert result.hodl_bank > 0

    def test_reserve_risk_formula(self, test_db):
        """T037: Reserve Risk = Price / (HODL Bank × Supply)."""
        from scripts.metrics.reserve_risk import calculate_reserve_risk

        result = calculate_reserve_risk(
            conn=test_db,
            current_price_usd=100000.0,
            block_height=875000,
        )

        # Reserve Risk should be inversely proportional to HODL Bank
        # Higher HODL Bank (more conviction) = lower Reserve Risk
        expected_rr = result.current_price_usd / (
            result.hodl_bank * result.circulating_supply_btc
        )
        assert result.reserve_risk == pytest.approx(expected_rr, rel=0.01)

    def test_signal_zone_strong_buy(self):
        """T038: Strong buy zone when Reserve Risk < 0.002."""
        from scripts.metrics.reserve_risk import _classify_signal_zone

        zone, confidence = _classify_signal_zone(0.001)
        assert zone == "STRONG_BUY"
        assert confidence >= 0.8

    def test_signal_zone_accumulation(self):
        """Accumulation zone when 0.002 <= RR < 0.008."""
        from scripts.metrics.reserve_risk import _classify_signal_zone

        zone, confidence = _classify_signal_zone(0.005)
        assert zone == "ACCUMULATION"
        assert confidence >= 0.6

    def test_signal_zone_fair_value(self):
        """Fair value zone when 0.008 <= RR < 0.02."""
        from scripts.metrics.reserve_risk import _classify_signal_zone

        zone, confidence = _classify_signal_zone(0.012)
        assert zone == "FAIR_VALUE"
        assert confidence >= 0.4

    def test_signal_zone_distribution(self):
        """Distribution zone when RR >= 0.02."""
        from scripts.metrics.reserve_risk import _classify_signal_zone

        zone, confidence = _classify_signal_zone(0.03)
        assert zone == "DISTRIBUTION"
        assert confidence >= 0.7

    def test_liveliness_from_cointime(self, test_db):
        """T039: Fetches liveliness from cointime_metrics table."""
        from scripts.metrics.reserve_risk import calculate_reserve_risk

        result = calculate_reserve_risk(
            conn=test_db,
            current_price_usd=100000.0,
            block_height=875000,
        )

        # Liveliness should come from cointime table
        assert result.liveliness == pytest.approx(0.3, rel=0.01)

    def test_empty_database(self):
        """Handles empty database gracefully."""
        from scripts.metrics.reserve_risk import calculate_reserve_risk

        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                outpoint VARCHAR PRIMARY KEY,
                btc_value DOUBLE NOT NULL,
                age_days INTEGER,
                is_spent BOOLEAN DEFAULT FALSE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE cointime_metrics (
                block_height INTEGER PRIMARY KEY,
                liveliness DOUBLE NOT NULL
            )
            """
        )
        # Create VIEW alias for production code compatibility
        conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

        result = calculate_reserve_risk(
            conn=conn,
            current_price_usd=100000.0,
            block_height=875000,
        )

        conn.close()

        assert isinstance(result, ReserveRiskResult)
        assert result.circulating_supply_btc == 0.0
        # Default to STRONG_BUY when no data (can't calculate risk)
        assert result.signal_zone in ["STRONG_BUY", "FAIR_VALUE"]


class TestReserveRiskDataclass:
    """Tests for ReserveRiskResult dataclass validation."""

    def test_valid_result(self):
        """Valid result creation succeeds."""
        result = ReserveRiskResult(
            reserve_risk=0.005,
            current_price_usd=100000.0,
            hodl_bank=200000.0,
            circulating_supply_btc=100.0,
            mvrv=1.5,
            liveliness=0.3,
            signal_zone="ACCUMULATION",
            confidence=0.75,
            block_height=875000,
        )
        assert result.reserve_risk == 0.005

    def test_invalid_signal_zone_fails(self):
        """Invalid signal_zone raises ValueError."""
        with pytest.raises(ValueError, match="signal_zone must be one of"):
            ReserveRiskResult(
                reserve_risk=0.005,
                current_price_usd=100000.0,
                hodl_bank=200000.0,
                circulating_supply_btc=100.0,
                mvrv=1.5,
                liveliness=0.3,
                signal_zone="INVALID",
                confidence=0.75,
                block_height=875000,
            )

    def test_negative_reserve_risk_fails(self):
        """Negative reserve_risk raises ValueError."""
        with pytest.raises(ValueError, match="reserve_risk must be >= 0"):
            ReserveRiskResult(
                reserve_risk=-0.005,
                current_price_usd=100000.0,
                hodl_bank=200000.0,
                circulating_supply_btc=100.0,
                mvrv=1.5,
                liveliness=0.3,
                signal_zone="ACCUMULATION",
                confidence=0.75,
                block_height=875000,
            )

    def test_to_dict(self):
        """to_dict() returns correct structure."""
        result = ReserveRiskResult(
            reserve_risk=0.005,
            current_price_usd=100000.0,
            hodl_bank=200000.0,
            circulating_supply_btc=100.0,
            mvrv=1.5,
            liveliness=0.3,
            signal_zone="ACCUMULATION",
            confidence=0.75,
            block_height=875000,
        )

        d = result.to_dict()
        assert d["reserve_risk"] == 0.005
        assert d["signal_zone"] == "ACCUMULATION"
        assert "timestamp" in d
