"""Tests for CDD/VDD (Coindays/Value Days Destroyed) module.

spec-021: Advanced On-Chain Metrics
TDD: Tests written BEFORE implementation.
"""

import duckdb
import pytest
from datetime import datetime, timedelta

from scripts.models.metrics_models import CoinDaysDestroyedResult


@pytest.fixture
def test_db():
    """Create an in-memory DuckDB with test spent UTXO data."""
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
            spent_block INTEGER,
            spent_timestamp TIMESTAMP,
            spent_price_usd DOUBLE,
            age_days INTEGER,
            is_spent BOOLEAN DEFAULT FALSE
        )
        """
    )

    # Use relative timestamps within the 30-day window
    now = datetime.utcnow()
    day_1 = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    day_5 = (now - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S")
    day_10 = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    day_8 = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    old_day = (now - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")

    # Insert spent UTXOs with various ages
    # CDD = age_days × btc_value
    conn.execute(
        f"""
        INSERT INTO utxo_lifecycle VALUES
        ('cdd1:0', 'cdd1', 0, 700000, '2023-06-01', 30000.0, 2.0, 874000, '{day_1}', 100000.0, 365, TRUE),
        ('cdd2:0', 'cdd2', 0, 750000, '2023-09-01', 35000.0, 1.0, 874500, '{day_5}', 105000.0, 274, TRUE),
        ('cdd3:0', 'cdd3', 0, 800000, '2024-01-01', 40000.0, 0.5, 875000, '{day_10}', 110000.0, 345, TRUE),
        ('cdd4:0', 'cdd4', 0, 860000, '2024-10-01', 65000.0, 3.0, 874800, '{day_8}', 102000.0, 68, TRUE)
        """
    )
    # CDD1: 365 × 2.0 = 730 coin-days
    # CDD2: 274 × 1.0 = 274 coin-days
    # CDD3: 345 × 0.5 = 172.5 coin-days
    # CDD4: 68 × 3.0 = 204 coin-days
    # Total CDD: 1380.5 coin-days

    # VDD = CDD × price
    # VDD1: 730 × 100000 = 73,000,000
    # VDD2: 274 × 105000 = 28,770,000
    # VDD3: 172.5 × 110000 = 18,975,000
    # VDD4: 204 × 102000 = 20,808,000
    # Total VDD: 141,553,000

    # Old spent UTXO (outside window)
    conn.execute(
        f"""
        INSERT INTO utxo_lifecycle VALUES
        ('old:0', 'old', 0, 600000, '2023-01-01', 20000.0, 10.0, 800000, '{old_day}', 45000.0, 380, TRUE)
        """
    )

    # Unspent UTXOs (should be excluded)
    conn.execute(
        """
        INSERT INTO utxo_lifecycle VALUES
        ('unspent:0', 'unspent', 0, 865000, '2024-10-01', 65000.0, 5.0, NULL, NULL, NULL, 71, FALSE)
        """
    )

    yield conn
    conn.close()


class TestCDDVDDCalculation:
    """Tests for calculate_cdd_vdd() function."""

    def test_calculate_basic(self, test_db):
        """T057: Basic CDD/VDD calculation returns valid result."""
        from scripts.metrics.cdd_vdd import calculate_cdd_vdd

        result = calculate_cdd_vdd(
            conn=test_db,
            current_price_usd=100000.0,
            block_height=875000,
            window_days=30,
        )

        assert isinstance(result, CoinDaysDestroyedResult)
        assert result.current_price_usd == 100000.0
        assert result.block_height == 875000
        assert result.window_days == 30
        assert result.cdd_total >= 0
        assert result.vdd_total >= 0

    def test_cdd_calculation(self, test_db):
        """T058: CDD = sum(age_days × btc_value) for spent UTXOs."""
        from scripts.metrics.cdd_vdd import calculate_cdd_vdd

        result = calculate_cdd_vdd(
            conn=test_db,
            current_price_usd=100000.0,
            block_height=875000,
            window_days=30,
        )

        # Expected CDD: 730 + 274 + 172.5 + 204 = 1380.5
        assert result.cdd_total == pytest.approx(1380.5, rel=0.01)

    def test_vdd_calculation(self, test_db):
        """T059: VDD = sum(CDD × spent_price) for spent UTXOs."""
        from scripts.metrics.cdd_vdd import calculate_cdd_vdd

        result = calculate_cdd_vdd(
            conn=test_db,
            current_price_usd=100000.0,
            block_height=875000,
            window_days=30,
        )

        # Expected VDD: 73M + 28.77M + 18.975M + 20.808M = 141.553M
        expected_vdd = 730 * 100000 + 274 * 105000 + 172.5 * 110000 + 204 * 102000
        assert result.vdd_total == pytest.approx(expected_vdd, rel=0.01)

    def test_daily_averages(self, test_db):
        """T060: Daily averages calculated correctly."""
        from scripts.metrics.cdd_vdd import calculate_cdd_vdd

        result = calculate_cdd_vdd(
            conn=test_db,
            current_price_usd=100000.0,
            block_height=875000,
            window_days=30,
        )

        # Daily averages = total / window_days
        expected_cdd_avg = result.cdd_total / 30
        expected_vdd_avg = result.vdd_total / 30

        assert result.cdd_daily_avg == pytest.approx(expected_cdd_avg, rel=0.01)
        assert result.vdd_daily_avg == pytest.approx(expected_vdd_avg, rel=0.01)

    def test_avg_utxo_age(self, test_db):
        """T061: Average UTXO age calculated correctly."""
        from scripts.metrics.cdd_vdd import calculate_cdd_vdd

        result = calculate_cdd_vdd(
            conn=test_db,
            current_price_usd=100000.0,
            block_height=875000,
            window_days=30,
        )

        # Average age = (365 + 274 + 345 + 68) / 4 = 263 days
        expected_avg_age = (365 + 274 + 345 + 68) / 4
        assert result.avg_utxo_age_days == pytest.approx(expected_avg_age, rel=0.01)

    def test_spent_utxo_count(self, test_db):
        """T062: Counts spent UTXOs in window."""
        from scripts.metrics.cdd_vdd import calculate_cdd_vdd

        result = calculate_cdd_vdd(
            conn=test_db,
            current_price_usd=100000.0,
            block_height=875000,
            window_days=30,
        )

        # 4 UTXOs spent in window
        assert result.spent_utxos_count == 4

    def test_signal_zone_low_activity(self):
        """Low activity zone when VDD multiple < 0.5."""
        from scripts.metrics.cdd_vdd import _classify_signal_zone

        zone, confidence = _classify_signal_zone(cdd_total=100, vdd_multiple=0.3)
        assert zone == "LOW_ACTIVITY"

    def test_signal_zone_normal(self):
        """Normal zone when activity moderate."""
        from scripts.metrics.cdd_vdd import _classify_signal_zone

        zone, confidence = _classify_signal_zone(cdd_total=1000, vdd_multiple=1.0)
        assert zone == "NORMAL"

    def test_signal_zone_elevated(self):
        """Elevated zone when activity above average."""
        from scripts.metrics.cdd_vdd import _classify_signal_zone

        zone, confidence = _classify_signal_zone(cdd_total=5000, vdd_multiple=1.5)
        assert zone == "ELEVATED"

    def test_signal_zone_spike(self):
        """Spike zone when VDD multiple > 2.0."""
        from scripts.metrics.cdd_vdd import _classify_signal_zone

        zone, confidence = _classify_signal_zone(cdd_total=10000, vdd_multiple=2.5)
        assert zone == "SPIKE"
        assert confidence >= 0.8

    def test_empty_window(self):
        """Handles empty window (no spent UTXOs)."""
        from scripts.metrics.cdd_vdd import calculate_cdd_vdd

        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                outpoint VARCHAR PRIMARY KEY,
                btc_value DOUBLE NOT NULL,
                spent_timestamp TIMESTAMP,
                spent_price_usd DOUBLE,
                age_days INTEGER,
                is_spent BOOLEAN DEFAULT FALSE
            )
            """
        )

        result = calculate_cdd_vdd(
            conn=conn,
            current_price_usd=100000.0,
            block_height=875000,
            window_days=30,
        )

        conn.close()

        assert result.cdd_total == 0.0
        assert result.vdd_total == 0.0
        assert result.spent_utxos_count == 0
        assert result.signal_zone == "LOW_ACTIVITY"


class TestCDDVDDDataclass:
    """Tests for CoinDaysDestroyedResult dataclass validation."""

    def test_valid_result(self):
        """Valid result creation succeeds."""
        result = CoinDaysDestroyedResult(
            cdd_total=1000.0,
            cdd_daily_avg=33.33,
            vdd_total=100_000_000.0,
            vdd_daily_avg=3_333_333.0,
            vdd_multiple=1.5,
            window_days=30,
            spent_utxos_count=500,
            avg_utxo_age_days=200.0,
            max_single_day_cdd=500.0,
            max_single_day_date=datetime(2024, 12, 1),
            current_price_usd=100000.0,
            signal_zone="NORMAL",
            confidence=0.7,
            block_height=875000,
        )
        assert result.cdd_total == 1000.0

    def test_invalid_signal_zone_fails(self):
        """Invalid signal_zone raises ValueError."""
        with pytest.raises(ValueError, match="signal_zone must be one of"):
            CoinDaysDestroyedResult(
                cdd_total=1000.0,
                cdd_daily_avg=33.33,
                vdd_total=100_000_000.0,
                vdd_daily_avg=3_333_333.0,
                vdd_multiple=1.5,
                window_days=30,
                spent_utxos_count=500,
                avg_utxo_age_days=200.0,
                max_single_day_cdd=500.0,
                max_single_day_date=datetime(2024, 12, 1),
                current_price_usd=100000.0,
                signal_zone="INVALID",
                confidence=0.7,
                block_height=875000,
            )

    def test_negative_cdd_fails(self):
        """Negative cdd_total raises ValueError."""
        with pytest.raises(ValueError, match="cdd_total must be >= 0"):
            CoinDaysDestroyedResult(
                cdd_total=-100.0,
                cdd_daily_avg=33.33,
                vdd_total=100_000_000.0,
                vdd_daily_avg=3_333_333.0,
                vdd_multiple=1.5,
                window_days=30,
                spent_utxos_count=500,
                avg_utxo_age_days=200.0,
                max_single_day_cdd=500.0,
                max_single_day_date=datetime(2024, 12, 1),
                current_price_usd=100000.0,
                signal_zone="NORMAL",
                confidence=0.7,
                block_height=875000,
            )

    def test_to_dict(self):
        """to_dict() returns correct structure."""
        result = CoinDaysDestroyedResult(
            cdd_total=1000.0,
            cdd_daily_avg=33.33,
            vdd_total=100_000_000.0,
            vdd_daily_avg=3_333_333.0,
            vdd_multiple=1.5,
            window_days=30,
            spent_utxos_count=500,
            avg_utxo_age_days=200.0,
            max_single_day_cdd=500.0,
            max_single_day_date=datetime(2024, 12, 1),
            current_price_usd=100000.0,
            signal_zone="NORMAL",
            confidence=0.7,
            block_height=875000,
        )

        d = result.to_dict()
        assert d["cdd_total"] == 1000.0
        assert d["window_days"] == 30
        assert "timestamp" in d
