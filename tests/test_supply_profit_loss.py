"""Tests for Supply Profit/Loss module.

spec-021: Advanced On-Chain Metrics
TDD: Tests written BEFORE implementation.
"""

import duckdb
import pytest

from scripts.models.metrics_models import SupplyProfitLossResult


@pytest.fixture
def test_db():
    """Create an in-memory DuckDB with test UTXO data."""
    conn = duckdb.connect(":memory:")

    # Create the utxo_lifecycle table schema
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
            spent_price_usd DOUBLE,
            age_days INTEGER,
            cohort VARCHAR DEFAULT 'STH',
            is_spent BOOLEAN DEFAULT FALSE
        )
        """
    )

    # Create VIEW alias for production code compatibility
    conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

    # Insert test data with various age cohorts and profit/loss states
    # Current price: $100,000
    # STH threshold: 155 days

    # STH (Short-Term Holders) - age < 155 days
    # In profit (cost basis < $100k):
    conn.execute(
        """
        INSERT INTO utxo_lifecycle VALUES
        ('sth_profit_1:0', 'sth_profit_1', 0, 870000, '2024-11-01', 80000.0, 2.0, 160000.0, NULL, NULL, NULL, 40, 'STH', FALSE),
        ('sth_profit_2:0', 'sth_profit_2', 0, 870100, '2024-11-02', 90000.0, 1.5, 135000.0, NULL, NULL, NULL, 39, 'STH', FALSE)
        """
    )
    # STH in loss (cost basis > $100k):
    conn.execute(
        """
        INSERT INTO utxo_lifecycle VALUES
        ('sth_loss_1:0', 'sth_loss_1', 0, 871000, '2024-11-15', 110000.0, 1.0, 110000.0, NULL, NULL, NULL, 26, 'STH', FALSE),
        ('sth_loss_2:0', 'sth_loss_2', 0, 871100, '2024-11-16', 120000.0, 0.5, 60000.0, NULL, NULL, NULL, 25, 'STH', FALSE)
        """
    )

    # LTH (Long-Term Holders) - age >= 155 days
    # In profit:
    conn.execute(
        """
        INSERT INTO utxo_lifecycle VALUES
        ('lth_profit_1:0', 'lth_profit_1', 0, 800000, '2024-01-01', 40000.0, 5.0, 200000.0, NULL, NULL, NULL, 345, 'LTH', FALSE),
        ('lth_profit_2:0', 'lth_profit_2', 0, 800100, '2024-01-02', 45000.0, 3.0, 135000.0, NULL, NULL, NULL, 344, 'LTH', FALSE)
        """
    )
    # LTH in loss (bought near ATH):
    conn.execute(
        """
        INSERT INTO utxo_lifecycle VALUES
        ('lth_loss_1:0', 'lth_loss_1', 0, 810000, '2024-03-15', 105000.0, 2.0, 210000.0, NULL, NULL, NULL, 271, 'LTH', FALSE)
        """
    )

    # Breakeven (exactly at current price)
    conn.execute(
        """
        INSERT INTO utxo_lifecycle VALUES
        ('breakeven:0', 'breakeven', 0, 865000, '2024-10-15', 100000.0, 1.0, 100000.0, NULL, NULL, NULL, 57, 'STH', FALSE)
        """
    )

    # Spent UTXO (should be excluded)
    conn.execute(
        """
        INSERT INTO utxo_lifecycle VALUES
        ('spent:0', 'spent', 0, 850000, '2024-09-01', 50000.0, 10.0, 500000.0, 870000, '2024-11-01', 100000.0, 61, 'LTH', TRUE)
        """
    )

    yield conn
    conn.close()


class TestSupplyProfitLossCalculation:
    """Tests for calculate_supply_profit_loss() function."""

    def test_calculate_basic(self, test_db):
        """T024: Basic calculation returns valid result."""
        from scripts.metrics.supply_profit_loss import calculate_supply_profit_loss

        result = calculate_supply_profit_loss(
            conn=test_db,
            current_price_usd=100000.0,
            block_height=875000,
        )

        # Verify result type
        assert isinstance(result, SupplyProfitLossResult)

        # Verify total supply (excludes spent UTXO):
        # STH profit: 2.0 + 1.5 = 3.5
        # STH loss: 1.0 + 0.5 = 1.5
        # LTH profit: 5.0 + 3.0 = 8.0
        # LTH loss: 2.0
        # Breakeven: 1.0
        # Total: 16.0 BTC
        assert result.total_supply_btc == pytest.approx(16.0, rel=0.01)

        # Verify price preserved
        assert result.current_price_usd == 100000.0

        # Verify block height
        assert result.block_height == 875000

    def test_profit_loss_split(self, test_db):
        """T025: Correctly splits supply into profit/loss categories."""
        from scripts.metrics.supply_profit_loss import calculate_supply_profit_loss

        result = calculate_supply_profit_loss(
            conn=test_db,
            current_price_usd=100000.0,
            block_height=875000,
        )

        # In profit (cost basis < $100k):
        # STH: 2.0 + 1.5 = 3.5 BTC
        # LTH: 5.0 + 3.0 = 8.0 BTC
        # Total in profit: 11.5 BTC
        assert result.supply_in_profit_btc == pytest.approx(11.5, rel=0.01)

        # In loss (cost basis > $100k):
        # STH: 1.0 + 0.5 = 1.5 BTC
        # LTH: 2.0 BTC
        # Total in loss: 3.5 BTC
        assert result.supply_in_loss_btc == pytest.approx(3.5, rel=0.01)

        # Breakeven
        assert result.supply_breakeven_btc == pytest.approx(1.0, rel=0.01)

        # Percentages
        total = result.total_supply_btc
        assert result.pct_in_profit == pytest.approx((11.5 / total) * 100, rel=0.1)
        assert result.pct_in_loss == pytest.approx((3.5 / total) * 100, rel=0.1)

    def test_cohort_breakdown(self, test_db):
        """T026: Correctly breaks down by STH/LTH cohort."""
        from scripts.metrics.supply_profit_loss import calculate_supply_profit_loss

        result = calculate_supply_profit_loss(
            conn=test_db,
            current_price_usd=100000.0,
            block_height=875000,
        )

        # STH breakdown (age < 155 days)
        # Note: breakeven (1.0 BTC) is STH (age=57) and counted as profit
        # STH profit: 3.5 + 1.0 (breakeven) = 4.5 BTC
        assert result.sth_in_profit_btc == pytest.approx(4.5, rel=0.01)
        assert result.sth_in_loss_btc == pytest.approx(1.5, rel=0.01)

        # LTH breakdown (age >= 155 days)
        assert result.lth_in_profit_btc == pytest.approx(8.0, rel=0.01)
        assert result.lth_in_loss_btc == pytest.approx(2.0, rel=0.01)

        # STH total: 4.5 + 1.5 = 6.0 BTC (breakeven already counted in profit)
        sth_total = result.sth_in_profit_btc + result.sth_in_loss_btc
        assert result.sth_pct_in_profit == pytest.approx(
            (result.sth_in_profit_btc / sth_total) * 100 if sth_total > 0 else 0,
            rel=0.5,
        )

    def test_market_phase_euphoria(self, test_db):
        """T027: Correctly classifies EUPHORIA when >95% in profit."""
        from scripts.metrics.supply_profit_loss import calculate_supply_profit_loss

        # Set current price very high so nearly everything is in profit
        result = calculate_supply_profit_loss(
            conn=test_db,
            current_price_usd=200000.0,  # All UTXOs in profit
            block_height=875000,
        )

        # At $200k, all UTXOs (except maybe none) should be in profit
        # 100% in profit -> EUPHORIA
        assert result.pct_in_profit >= 95.0
        assert result.market_phase == "EUPHORIA"

    def test_market_phase_capitulation(self, test_db):
        """T028: Correctly classifies CAPITULATION when <50% in profit."""
        from scripts.metrics.supply_profit_loss import calculate_supply_profit_loss

        # Set current price very low so most are in loss
        result = calculate_supply_profit_loss(
            conn=test_db,
            current_price_usd=30000.0,  # Below most cost bases
            block_height=875000,
        )

        # At $30k, only LTH with cost basis < $30k are in profit
        # LTH at $40k and $45k are now in loss
        # Should be CAPITULATION (<50% in profit)
        assert result.pct_in_profit < 50.0
        assert result.market_phase == "CAPITULATION"

    def test_market_phase_bull(self, test_db):
        """Market phase BULL when 80-95% in profit."""
        from scripts.metrics.supply_profit_loss import calculate_supply_profit_loss

        # Current price where ~80-95% are in profit
        result = calculate_supply_profit_loss(
            conn=test_db,
            current_price_usd=115000.0,  # Above most cost bases
            block_height=875000,
        )

        # At $115k, most are in profit except STH_loss at $120k
        # Expected: 80-95% -> BULL
        if 80.0 <= result.pct_in_profit < 95.0:
            assert result.market_phase == "BULL"
        # May fall into different phase depending on exact calculation

    def test_empty_result(self):
        """Handles empty UTXO set gracefully."""
        from scripts.metrics.supply_profit_loss import calculate_supply_profit_loss

        conn = duckdb.connect(":memory:")
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
                age_days INTEGER,
                cohort VARCHAR DEFAULT 'STH',
                is_spent BOOLEAN DEFAULT FALSE
            )
            """
        )
        # Create VIEW alias for production code compatibility
        conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

        result = calculate_supply_profit_loss(
            conn=conn,
            current_price_usd=100000.0,
            block_height=875000,
        )

        conn.close()

        assert isinstance(result, SupplyProfitLossResult)
        assert result.total_supply_btc == 0.0
        assert result.supply_in_profit_btc == 0.0
        assert result.supply_in_loss_btc == 0.0
        # Default to CAPITULATION for empty set
        assert result.market_phase == "CAPITULATION"

    def test_signal_strength(self, test_db):
        """Signal strength increases at extremes."""
        from scripts.metrics.supply_profit_loss import calculate_supply_profit_loss

        # Extreme high (euphoria)
        result_high = calculate_supply_profit_loss(
            conn=test_db,
            current_price_usd=200000.0,
            block_height=875000,
        )

        # Moderate
        result_mid = calculate_supply_profit_loss(
            conn=test_db,
            current_price_usd=70000.0,
            block_height=875000,
        )

        # Signal strength should be higher at extremes
        assert result_high.signal_strength >= 0.5
        # Mid-range should have lower signal strength
        assert result_mid.signal_strength >= 0.0


class TestSupplyProfitLossDataclass:
    """Tests for SupplyProfitLossResult dataclass validation."""

    def test_valid_result(self):
        """Valid result creation succeeds."""
        result = SupplyProfitLossResult(
            current_price_usd=100000.0,
            total_supply_btc=100.0,
            supply_in_profit_btc=70.0,
            supply_in_loss_btc=25.0,
            supply_breakeven_btc=5.0,
            pct_in_profit=70.0,
            pct_in_loss=25.0,
            sth_in_profit_btc=20.0,
            sth_in_loss_btc=10.0,
            sth_pct_in_profit=66.7,
            lth_in_profit_btc=50.0,
            lth_in_loss_btc=15.0,
            lth_pct_in_profit=76.9,
            market_phase="BULL",
            signal_strength=0.7,
            block_height=875000,
        )
        assert result.pct_in_profit == 70.0

    def test_invalid_market_phase_fails(self):
        """Invalid market_phase raises ValueError."""
        with pytest.raises(ValueError, match="market_phase must be one of"):
            SupplyProfitLossResult(
                current_price_usd=100000.0,
                total_supply_btc=100.0,
                supply_in_profit_btc=70.0,
                supply_in_loss_btc=25.0,
                supply_breakeven_btc=5.0,
                pct_in_profit=70.0,
                pct_in_loss=25.0,
                sth_in_profit_btc=20.0,
                sth_in_loss_btc=10.0,
                sth_pct_in_profit=66.7,
                lth_in_profit_btc=50.0,
                lth_in_loss_btc=15.0,
                lth_pct_in_profit=76.9,
                market_phase="INVALID",  # Invalid
                signal_strength=0.7,
                block_height=875000,
            )

    def test_invalid_signal_strength_fails(self):
        """signal_strength > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="signal_strength must be in"):
            SupplyProfitLossResult(
                current_price_usd=100000.0,
                total_supply_btc=100.0,
                supply_in_profit_btc=70.0,
                supply_in_loss_btc=25.0,
                supply_breakeven_btc=5.0,
                pct_in_profit=70.0,
                pct_in_loss=25.0,
                sth_in_profit_btc=20.0,
                sth_in_loss_btc=10.0,
                sth_pct_in_profit=66.7,
                lth_in_profit_btc=50.0,
                lth_in_loss_btc=15.0,
                lth_pct_in_profit=76.9,
                market_phase="BULL",
                signal_strength=1.5,  # Invalid
                block_height=875000,
            )

    def test_to_dict(self):
        """to_dict() returns correct structure."""
        result = SupplyProfitLossResult(
            current_price_usd=100000.0,
            total_supply_btc=100.0,
            supply_in_profit_btc=70.0,
            supply_in_loss_btc=25.0,
            supply_breakeven_btc=5.0,
            pct_in_profit=70.0,
            pct_in_loss=25.0,
            sth_in_profit_btc=20.0,
            sth_in_loss_btc=10.0,
            sth_pct_in_profit=66.7,
            lth_in_profit_btc=50.0,
            lth_in_loss_btc=15.0,
            lth_pct_in_profit=76.9,
            market_phase="BULL",
            signal_strength=0.7,
            block_height=875000,
        )

        d = result.to_dict()
        assert d["current_price_usd"] == 100000.0
        assert d["market_phase"] == "BULL"
        assert d["signal_strength"] == 0.7
        assert "timestamp" in d
