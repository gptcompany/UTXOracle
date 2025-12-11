"""Tests for Sell-side Risk module.

spec-021: Advanced On-Chain Metrics
TDD: Tests written BEFORE implementation.
"""

import duckdb
import pytest
from datetime import datetime, timedelta

from scripts.models.metrics_models import SellSideRiskResult


@pytest.fixture
def test_db():
    """Create an in-memory DuckDB with test spent UTXO data."""
    conn = duckdb.connect(":memory:")

    # Create utxo_lifecycle table with spent UTXOs
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
            is_spent BOOLEAN DEFAULT FALSE
        )
        """
    )

    # Use relative timestamps within the 30-day window
    now = datetime.utcnow()
    day_1 = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    day_5 = (now - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S")
    day_10 = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    day_3 = (now - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")
    day_8 = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    old_day = (now - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")

    # Profit scenarios (spent_price > creation_price)
    conn.execute(
        f"""
        INSERT INTO utxo_lifecycle VALUES
        ('profit1:0', 'profit1', 0, 800000, '2024-01-01', 40000.0, 2.0, 874000, '{day_1}', 100000.0, TRUE),
        ('profit2:0', 'profit2', 0, 810000, '2024-02-01', 50000.0, 1.5, 874500, '{day_5}', 105000.0, TRUE),
        ('profit3:0', 'profit3', 0, 820000, '2024-03-01', 60000.0, 1.0, 875000, '{day_10}', 110000.0, TRUE)
        """
    )
    # profit1: (100000-40000) × 2.0 = $120,000 profit
    # profit2: (105000-50000) × 1.5 = $82,500 profit
    # profit3: (110000-60000) × 1.0 = $50,000 profit
    # Total profit: $252,500

    # Loss scenarios (spent_price < creation_price)
    conn.execute(
        f"""
        INSERT INTO utxo_lifecycle VALUES
        ('loss1:0', 'loss1', 0, 870000, '2024-11-01', 115000.0, 0.5, 874200, '{day_3}', 98000.0, TRUE),
        ('loss2:0', 'loss2', 0, 871000, '2024-11-10', 120000.0, 0.3, 874800, '{day_8}', 102000.0, TRUE)
        """
    )
    # loss1: (98000-115000) × 0.5 = -$8,500 loss
    # loss2: (102000-120000) × 0.3 = -$5,400 loss
    # Total loss: $13,900

    # Old spent UTXO (outside 30-day window, should be excluded)
    conn.execute(
        f"""
        INSERT INTO utxo_lifecycle VALUES
        ('old:0', 'old', 0, 750000, '2024-05-01', 70000.0, 5.0, 860000, '{old_day}', 80000.0, TRUE)
        """
    )

    # Unspent UTXOs (should be excluded)
    conn.execute(
        """
        INSERT INTO utxo_lifecycle VALUES
        ('unspent:0', 'unspent', 0, 865000, '2024-10-01', 65000.0, 3.0, NULL, NULL, NULL, FALSE)
        """
    )

    yield conn
    conn.close()


class TestSellSideRiskCalculation:
    """Tests for calculate_sell_side_risk() function."""

    def test_calculate_basic(self, test_db):
        """T046: Basic Sell-side Risk calculation returns valid result."""
        from scripts.metrics.sell_side_risk import calculate_sell_side_risk

        result = calculate_sell_side_risk(
            conn=test_db,
            market_cap_usd=2_000_000_000_000.0,  # $2T market cap
            block_height=875000,
            window_days=30,
        )

        assert isinstance(result, SellSideRiskResult)
        assert result.market_cap_usd == 2_000_000_000_000.0
        assert result.block_height == 875000
        assert result.window_days == 30
        assert result.sell_side_risk >= 0

    def test_realized_profit_calculation(self, test_db):
        """T047: Correctly sums realized profit from spent UTXOs."""
        from scripts.metrics.sell_side_risk import calculate_sell_side_risk

        result = calculate_sell_side_risk(
            conn=test_db,
            market_cap_usd=2_000_000_000_000.0,
            block_height=875000,
            window_days=30,
        )

        # Expected profit: $120,000 + $82,500 + $50,000 = $252,500
        assert result.realized_profit_usd == pytest.approx(252500.0, rel=0.01)

    def test_realized_loss_calculation(self, test_db):
        """T048: Correctly sums realized loss from spent UTXOs."""
        from scripts.metrics.sell_side_risk import calculate_sell_side_risk

        result = calculate_sell_side_risk(
            conn=test_db,
            market_cap_usd=2_000_000_000_000.0,
            block_height=875000,
            window_days=30,
        )

        # Expected loss: $8,500 + $5,400 = $13,900
        assert result.realized_loss_usd == pytest.approx(13900.0, rel=0.01)

    def test_sell_side_risk_formula(self, test_db):
        """T049: Sell-side Risk = Realized Profit / Market Cap."""
        from scripts.metrics.sell_side_risk import calculate_sell_side_risk

        market_cap = 2_000_000_000_000.0  # $2T
        result = calculate_sell_side_risk(
            conn=test_db,
            market_cap_usd=market_cap,
            block_height=875000,
            window_days=30,
        )

        # Expected: $252,500 / $2T = 0.00000012625 = 0.000012625%
        expected_risk = result.realized_profit_usd / market_cap
        assert result.sell_side_risk == pytest.approx(expected_risk, rel=0.01)

        # Percentage conversion
        expected_pct = expected_risk * 100
        assert result.sell_side_risk_pct == pytest.approx(expected_pct, rel=0.01)

    def test_window_filtering(self, test_db):
        """T050: Only includes UTXOs spent within window."""
        from scripts.metrics.sell_side_risk import calculate_sell_side_risk

        result = calculate_sell_side_risk(
            conn=test_db,
            market_cap_usd=2_000_000_000_000.0,
            block_height=875000,
            window_days=30,
        )

        # Should have 5 spent UTXOs in window (3 profit + 2 loss)
        # Old UTXO (September) should be excluded
        assert result.spent_utxos_in_window == 5

    def test_signal_zone_low(self):
        """Low distribution zone when < 0.1%."""
        from scripts.metrics.sell_side_risk import _classify_signal_zone

        zone, confidence = _classify_signal_zone(0.0005)
        assert zone == "LOW"
        assert confidence >= 0.6

    def test_signal_zone_normal(self):
        """Normal zone when 0.1% - 0.3%."""
        from scripts.metrics.sell_side_risk import _classify_signal_zone

        # Note: _classify_signal_zone takes percentage value (0.2 = 0.2%)
        zone, confidence = _classify_signal_zone(0.2)
        assert zone == "NORMAL"
        assert confidence >= 0.5

    def test_signal_zone_elevated(self):
        """Elevated zone when 0.3% - 1.0%."""
        from scripts.metrics.sell_side_risk import _classify_signal_zone

        zone, confidence = _classify_signal_zone(0.5)
        assert zone == "ELEVATED"
        assert confidence >= 0.6

    def test_signal_zone_aggressive(self):
        """Aggressive zone when > 1.0%."""
        from scripts.metrics.sell_side_risk import _classify_signal_zone

        zone, confidence = _classify_signal_zone(1.5)
        assert zone == "AGGRESSIVE"
        assert confidence >= 0.8

    def test_empty_window(self):
        """Handles empty window (no spent UTXOs)."""
        from scripts.metrics.sell_side_risk import calculate_sell_side_risk

        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                outpoint VARCHAR PRIMARY KEY,
                btc_value DOUBLE NOT NULL,
                creation_price_usd DOUBLE NOT NULL,
                spent_timestamp TIMESTAMP,
                spent_price_usd DOUBLE,
                is_spent BOOLEAN DEFAULT FALSE
            )
            """
        )

        result = calculate_sell_side_risk(
            conn=conn,
            market_cap_usd=2_000_000_000_000.0,
            block_height=875000,
            window_days=30,
        )

        conn.close()

        assert result.realized_profit_usd == 0.0
        assert result.realized_loss_usd == 0.0
        assert result.sell_side_risk == 0.0
        assert result.signal_zone == "LOW"


class TestSellSideRiskDataclass:
    """Tests for SellSideRiskResult dataclass validation."""

    def test_valid_result(self):
        """Valid result creation succeeds."""
        result = SellSideRiskResult(
            sell_side_risk=0.001,
            sell_side_risk_pct=0.1,
            realized_profit_usd=1_000_000.0,
            realized_loss_usd=100_000.0,
            net_realized_pnl_usd=900_000.0,
            market_cap_usd=1_000_000_000_000.0,
            window_days=30,
            spent_utxos_in_window=1000,
            signal_zone="NORMAL",
            confidence=0.7,
            block_height=875000,
        )
        assert result.sell_side_risk == 0.001

    def test_invalid_signal_zone_fails(self):
        """Invalid signal_zone raises ValueError."""
        with pytest.raises(ValueError, match="signal_zone must be one of"):
            SellSideRiskResult(
                sell_side_risk=0.001,
                sell_side_risk_pct=0.1,
                realized_profit_usd=1_000_000.0,
                realized_loss_usd=100_000.0,
                net_realized_pnl_usd=900_000.0,
                market_cap_usd=1_000_000_000_000.0,
                window_days=30,
                spent_utxos_in_window=1000,
                signal_zone="INVALID",
                confidence=0.7,
                block_height=875000,
            )

    def test_invalid_window_days_fails(self):
        """window_days <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="window_days must be > 0"):
            SellSideRiskResult(
                sell_side_risk=0.001,
                sell_side_risk_pct=0.1,
                realized_profit_usd=1_000_000.0,
                realized_loss_usd=100_000.0,
                net_realized_pnl_usd=900_000.0,
                market_cap_usd=1_000_000_000_000.0,
                window_days=0,
                spent_utxos_in_window=1000,
                signal_zone="NORMAL",
                confidence=0.7,
                block_height=875000,
            )

    def test_to_dict(self):
        """to_dict() returns correct structure."""
        result = SellSideRiskResult(
            sell_side_risk=0.001,
            sell_side_risk_pct=0.1,
            realized_profit_usd=1_000_000.0,
            realized_loss_usd=100_000.0,
            net_realized_pnl_usd=900_000.0,
            market_cap_usd=1_000_000_000_000.0,
            window_days=30,
            spent_utxos_in_window=1000,
            signal_zone="NORMAL",
            confidence=0.7,
            block_height=875000,
        )

        d = result.to_dict()
        assert d["sell_side_risk"] == 0.001
        assert d["window_days"] == 30
        assert "timestamp" in d
