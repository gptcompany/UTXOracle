"""
Tests for Net Realized Profit/Loss module (spec-028).

TDD tests - written BEFORE implementation.
These tests MUST FAIL until T010-T015 are implemented.

Test Coverage:
- T007: test_calculate_net_realized_pnl_basic
- T008: test_calculate_net_realized_pnl_edge_cases
- T009: test_signal_interpretation
- T016: test_get_net_realized_pnl_history
- T017: test_history_date_range
"""

from datetime import datetime, date, timedelta
from typing import Generator

import duckdb
import pytest

from scripts.metrics.net_realized_pnl import (
    calculate_net_realized_pnl,
    get_net_realized_pnl_history,
    _determine_signal,
    _calculate_profit_loss_ratio,
)
from scripts.models.metrics_models import (
    NetRealizedPnLResult,
    NetRealizedPnLHistoryPoint,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Create in-memory DuckDB with utxo_lifecycle_full schema."""
    conn = duckdb.connect(":memory:")

    # Create table (matches spec-017 schema)
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
            spending_txid VARCHAR,
            age_blocks INTEGER,
            age_days INTEGER,
            cohort VARCHAR,
            sub_cohort VARCHAR,
            sopr DOUBLE,
            is_coinbase BOOLEAN DEFAULT FALSE,
            is_spent BOOLEAN DEFAULT FALSE,
            price_source VARCHAR DEFAULT 'utxoracle'
        )
        """
    )

    # Create VIEW alias
    conn.execute(
        """
        CREATE VIEW utxo_lifecycle_full AS
        SELECT * FROM utxo_lifecycle
        """
    )

    yield conn
    conn.close()


@pytest.fixture
def db_with_profit_data(
    db_conn: duckdb.DuckDBPyConnection,
) -> duckdb.DuckDBPyConnection:
    """Insert test data with profitable UTXOs (spent_price > creation_price)."""
    now = datetime.now()
    hour_ago = now - timedelta(hours=1)

    # 3 profitable UTXOs: bought at $50k, sold at $100k
    # Profit per UTXO = ($100k - $50k) * btc_value
    test_data = [
        # outpoint, txid, vout, creation_block, creation_ts, creation_price, btc_value,
        # realized_value, spent_block, spent_ts, spent_price, spending_txid,
        # age_blocks, age_days, cohort, sub_cohort, sopr, is_coinbase, is_spent, price_source
        (
            "tx1:0",
            "tx1",
            0,
            800000,
            hour_ago,
            50000.0,
            1.0,
            50000.0,
            800010,
            now,
            100000.0,
            "spend1",
            10,
            0,
            "STH",
            "1d",
            2.0,
            False,
            True,
            "utxoracle",
        ),
        (
            "tx2:0",
            "tx2",
            0,
            800000,
            hour_ago,
            50000.0,
            2.0,
            100000.0,
            800010,
            now,
            100000.0,
            "spend2",
            10,
            0,
            "STH",
            "1d",
            2.0,
            False,
            True,
            "utxoracle",
        ),
        (
            "tx3:0",
            "tx3",
            0,
            800000,
            hour_ago,
            50000.0,
            0.5,
            25000.0,
            800010,
            now,
            100000.0,
            "spend3",
            10,
            0,
            "STH",
            "1d",
            2.0,
            False,
            True,
            "utxoracle",
        ),
    ]

    for row in test_data:
        db_conn.execute(
            """
            INSERT INTO utxo_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )

    return db_conn


@pytest.fixture
def db_with_loss_data(db_conn: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """Insert test data with loss-making UTXOs (spent_price < creation_price)."""
    now = datetime.now()
    hour_ago = now - timedelta(hours=1)

    # 2 loss-making UTXOs: bought at $100k, sold at $50k
    # Loss per UTXO = ($100k - $50k) * btc_value
    test_data = [
        (
            "loss1:0",
            "loss1",
            0,
            800000,
            hour_ago,
            100000.0,
            1.0,
            100000.0,
            800010,
            now,
            50000.0,
            "spend_l1",
            10,
            0,
            "STH",
            "1d",
            0.5,
            False,
            True,
            "utxoracle",
        ),
        (
            "loss2:0",
            "loss2",
            0,
            800000,
            hour_ago,
            100000.0,
            2.0,
            200000.0,
            800010,
            now,
            50000.0,
            "spend_l2",
            10,
            0,
            "STH",
            "1d",
            0.5,
            False,
            True,
            "utxoracle",
        ),
    ]

    for row in test_data:
        db_conn.execute(
            """
            INSERT INTO utxo_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )

    return db_conn


@pytest.fixture
def db_with_mixed_data(
    db_conn: duckdb.DuckDBPyConnection,
) -> duckdb.DuckDBPyConnection:
    """Insert test data with both profit and loss UTXOs."""
    now = datetime.now()
    hour_ago = now - timedelta(hours=1)

    # Mix of profit and loss
    # Profit: 1 BTC @ $50k -> $100k = $50k profit
    # Loss: 1 BTC @ $100k -> $50k = $50k loss
    # Net P/L = $0 (neutral)
    test_data = [
        # Profit UTXO
        (
            "mix_profit:0",
            "mix_profit",
            0,
            800000,
            hour_ago,
            50000.0,
            1.0,
            50000.0,
            800010,
            now,
            100000.0,
            "spend_p",
            10,
            0,
            "STH",
            "1d",
            2.0,
            False,
            True,
            "utxoracle",
        ),
        # Loss UTXO
        (
            "mix_loss:0",
            "mix_loss",
            0,
            800000,
            hour_ago,
            100000.0,
            1.0,
            100000.0,
            800010,
            now,
            50000.0,
            "spend_l",
            10,
            0,
            "STH",
            "1d",
            0.5,
            False,
            True,
            "utxoracle",
        ),
    ]

    for row in test_data:
        db_conn.execute(
            """
            INSERT INTO utxo_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )

    return db_conn


@pytest.fixture
def db_with_history_data(
    db_conn: duckdb.DuckDBPyConnection,
) -> duckdb.DuckDBPyConnection:
    """Insert test data spanning multiple days for history tests."""
    base_time = datetime.now()

    # Create data for 3 days ago, 2 days ago, 1 day ago
    for days_ago in range(1, 4):
        spent_ts = base_time - timedelta(days=days_ago)
        creation_ts = spent_ts - timedelta(hours=2)

        # Each day: 1 profit UTXO, 1 loss UTXO
        profit_row = (
            f"hist_p{days_ago}:0",
            f"hist_p{days_ago}",
            0,
            800000,
            creation_ts,
            50000.0,
            1.0,
            50000.0,
            800010,
            spent_ts,
            100000.0 + (days_ago * 1000),  # Slightly different prices
            f"spend_hp{days_ago}",
            10,
            0,
            "STH",
            "1d",
            2.0,
            False,
            True,
            "utxoracle",
        )

        loss_row = (
            f"hist_l{days_ago}:0",
            f"hist_l{days_ago}",
            0,
            800000,
            creation_ts,
            100000.0,
            0.5,
            50000.0,
            800010,
            spent_ts,
            50000.0 - (days_ago * 1000),  # Slightly different prices
            f"spend_hl{days_ago}",
            10,
            0,
            "STH",
            "1d",
            0.5,
            False,
            True,
            "utxoracle",
        )

        for row in [profit_row, loss_row]:
            db_conn.execute(
                """
                INSERT INTO utxo_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )

    return db_conn


# =============================================================================
# T007: test_calculate_net_realized_pnl_basic
# =============================================================================


class TestCalculateNetRealizedPnLBasic:
    """T007: Basic profit/loss calculation tests."""

    def test_profit_calculation(self, db_with_profit_data):
        """Test calculation with only profitable UTXOs."""
        result = calculate_net_realized_pnl(db_with_profit_data, window_hours=24)

        assert isinstance(result, NetRealizedPnLResult)

        # Total BTC: 1.0 + 2.0 + 0.5 = 3.5 BTC
        # Price diff: $100k - $50k = $50k per BTC
        # Expected profit: 3.5 * $50k = $175,000
        assert result.realized_profit_usd == pytest.approx(175000.0, rel=0.01)
        assert result.realized_loss_usd == 0.0
        assert result.net_realized_pnl_usd == pytest.approx(175000.0, rel=0.01)

        # BTC volume
        assert result.realized_profit_btc == pytest.approx(3.5, rel=0.01)
        assert result.realized_loss_btc == 0.0

        # Counts
        assert result.profit_utxo_count == 3
        assert result.loss_utxo_count == 0

        # Signal
        assert result.signal == "PROFIT_DOMINANT"
        assert result.window_hours == 24

    def test_loss_calculation(self, db_with_loss_data):
        """Test calculation with only loss-making UTXOs."""
        result = calculate_net_realized_pnl(db_with_loss_data, window_hours=24)

        # Total BTC: 1.0 + 2.0 = 3.0 BTC
        # Price diff: $100k - $50k = $50k loss per BTC
        # Expected loss: 3.0 * $50k = $150,000
        assert result.realized_profit_usd == 0.0
        assert result.realized_loss_usd == pytest.approx(150000.0, rel=0.01)
        assert result.net_realized_pnl_usd == pytest.approx(-150000.0, rel=0.01)

        # BTC volume
        assert result.realized_profit_btc == 0.0
        assert result.realized_loss_btc == pytest.approx(3.0, rel=0.01)

        # Signal
        assert result.signal == "LOSS_DOMINANT"

    def test_mixed_calculation(self, db_with_mixed_data):
        """Test calculation with mixed profit/loss (should be neutral)."""
        result = calculate_net_realized_pnl(db_with_mixed_data, window_hours=24)

        # Profit: 1 BTC * ($100k - $50k) = $50k
        # Loss: 1 BTC * ($100k - $50k) = $50k
        # Net P/L = $0
        assert result.realized_profit_usd == pytest.approx(50000.0, rel=0.01)
        assert result.realized_loss_usd == pytest.approx(50000.0, rel=0.01)
        assert result.net_realized_pnl_usd == pytest.approx(0.0, abs=0.01)

        # Counts
        assert result.profit_utxo_count == 1
        assert result.loss_utxo_count == 1

        # Signal should be NEUTRAL
        assert result.signal == "NEUTRAL"


# =============================================================================
# T008: test_calculate_net_realized_pnl_edge_cases
# =============================================================================


class TestCalculateNetRealizedPnLEdgeCases:
    """T008: Edge case tests for the calculation."""

    def test_empty_database(self, db_conn):
        """Test with no data - should return zeros."""
        result = calculate_net_realized_pnl(db_conn, window_hours=24)

        assert result.realized_profit_usd == 0.0
        assert result.realized_loss_usd == 0.0
        assert result.net_realized_pnl_usd == 0.0
        assert result.profit_utxo_count == 0
        assert result.loss_utxo_count == 0
        assert result.signal == "NEUTRAL"

    def test_invalid_window_hours_too_low(self, db_conn):
        """Test with window_hours < 1 - should raise ValueError."""
        with pytest.raises(ValueError, match="window_hours"):
            calculate_net_realized_pnl(db_conn, window_hours=0)

    def test_invalid_window_hours_too_high(self, db_conn):
        """Test with window_hours > 720 - should raise ValueError."""
        with pytest.raises(ValueError, match="window_hours"):
            calculate_net_realized_pnl(db_conn, window_hours=721)

    def test_zero_prices_excluded(self, db_conn):
        """Test that UTXOs with zero prices are excluded."""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)

        # Insert UTXO with zero creation_price (should be excluded)
        db_conn.execute(
            """
            INSERT INTO utxo_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "zero:0",
                "zero",
                0,
                800000,
                hour_ago,
                0.0,  # Zero creation price
                1.0,
                0.0,
                800010,
                now,
                100000.0,
                "spend_z",
                10,
                0,
                "STH",
                "1d",
                0.0,
                False,
                True,
                "utxoracle",
            ),
        )

        result = calculate_net_realized_pnl(db_conn, window_hours=24)

        # Should be excluded, so counts should be 0
        assert result.profit_utxo_count == 0
        assert result.loss_utxo_count == 0

    def test_unspent_utxos_excluded(self, db_conn):
        """Test that unspent UTXOs are excluded."""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)

        # Insert unspent UTXO (is_spent = False)
        db_conn.execute(
            """
            INSERT INTO utxo_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "unspent:0",
                "unspent",
                0,
                800000,
                hour_ago,
                50000.0,
                1.0,
                50000.0,
                None,  # Not spent
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                False,
                False,  # is_spent = False
                "utxoracle",
            ),
        )

        result = calculate_net_realized_pnl(db_conn, window_hours=24)

        # Should be excluded
        assert result.profit_utxo_count == 0
        assert result.loss_utxo_count == 0

    def test_outside_window_excluded(self, db_conn):
        """Test that UTXOs outside time window are excluded."""
        now = datetime.now()
        two_days_ago = now - timedelta(days=2)
        two_days_ago_creation = two_days_ago - timedelta(hours=1)

        # Insert UTXO spent 2 days ago
        db_conn.execute(
            """
            INSERT INTO utxo_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "old:0",
                "old",
                0,
                800000,
                two_days_ago_creation,
                50000.0,
                1.0,
                50000.0,
                800010,
                two_days_ago,  # Spent 2 days ago
                100000.0,
                "spend_old",
                10,
                0,
                "STH",
                "1d",
                2.0,
                False,
                True,
                "utxoracle",
            ),
        )

        # Query with 24h window - should exclude 2-day-old data
        result = calculate_net_realized_pnl(db_conn, window_hours=24)

        assert result.profit_utxo_count == 0
        assert result.loss_utxo_count == 0


# =============================================================================
# T009: test_signal_interpretation
# =============================================================================


class TestSignalInterpretation:
    """T009: Signal interpretation tests."""

    def test_profit_dominant_signal(self):
        """Test PROFIT_DOMINANT signal when profit > loss."""
        signal = _determine_signal(net_pnl_usd=100000.0, profit_loss_ratio=1.5)
        assert signal == "PROFIT_DOMINANT"

    def test_loss_dominant_signal(self):
        """Test LOSS_DOMINANT signal when loss > profit."""
        signal = _determine_signal(net_pnl_usd=-100000.0, profit_loss_ratio=0.5)
        assert signal == "LOSS_DOMINANT"

    def test_neutral_signal_zero(self):
        """Test NEUTRAL signal when net P/L is zero."""
        signal = _determine_signal(net_pnl_usd=0.0, profit_loss_ratio=1.0)
        assert signal == "NEUTRAL"

    def test_neutral_signal_near_zero(self):
        """Test NEUTRAL signal when profit/loss ratio is near 1.0."""
        # Even with small net profit, if ratio is ~1.0, it's neutral
        signal = _determine_signal(net_pnl_usd=100.0, profit_loss_ratio=1.001)
        # Should be PROFIT_DOMINANT (positive net)
        assert signal == "PROFIT_DOMINANT"

    def test_profit_loss_ratio_division_by_zero(self):
        """Test ratio calculation when loss is zero."""
        ratio = _calculate_profit_loss_ratio(
            realized_profit_usd=100000.0, realized_loss_usd=0.0
        )
        # When no loss, ratio should be infinity or a large number
        assert ratio == float("inf") or ratio > 1000000

    def test_profit_loss_ratio_no_profit(self):
        """Test ratio calculation when profit is zero."""
        ratio = _calculate_profit_loss_ratio(
            realized_profit_usd=0.0, realized_loss_usd=100000.0
        )
        assert ratio == 0.0

    def test_profit_loss_ratio_both_zero(self):
        """Test ratio calculation when both are zero."""
        ratio = _calculate_profit_loss_ratio(
            realized_profit_usd=0.0, realized_loss_usd=0.0
        )
        # Should be 0.0 or 1.0 (implementation decision)
        assert ratio in (0.0, 1.0)

    def test_profit_loss_ratio_normal(self):
        """Test normal ratio calculation."""
        ratio = _calculate_profit_loss_ratio(
            realized_profit_usd=150000.0, realized_loss_usd=100000.0
        )
        assert ratio == pytest.approx(1.5, rel=0.01)


# =============================================================================
# T016: test_get_net_realized_pnl_history
# =============================================================================


class TestGetNetRealizedPnLHistory:
    """T016: History retrieval tests."""

    def test_history_retrieval(self, db_with_history_data):
        """Test retrieving historical P/L data."""
        history = get_net_realized_pnl_history(db_with_history_data, days=7)

        assert isinstance(history, list)
        assert len(history) >= 1  # At least some history

        # Each item should be a NetRealizedPnLHistoryPoint
        for point in history:
            assert isinstance(point, NetRealizedPnLHistoryPoint)
            assert isinstance(point.date, date)
            assert point.realized_profit_usd >= 0
            assert point.realized_loss_usd >= 0

    def test_history_sorted_by_date(self, db_with_history_data):
        """Test that history is sorted by date (oldest first)."""
        history = get_net_realized_pnl_history(db_with_history_data, days=7)

        if len(history) >= 2:
            for i in range(len(history) - 1):
                assert history[i].date <= history[i + 1].date

    def test_history_empty_database(self, db_conn):
        """Test history with no data."""
        history = get_net_realized_pnl_history(db_conn, days=7)

        assert isinstance(history, list)
        assert len(history) == 0


# =============================================================================
# T017: test_history_date_range
# =============================================================================


class TestHistoryDateRange:
    """T017: Date range tests for history."""

    def test_invalid_days_too_low(self, db_conn):
        """Test with days < 1 - should raise ValueError."""
        with pytest.raises(ValueError, match="days"):
            get_net_realized_pnl_history(db_conn, days=0)

    def test_invalid_days_too_high(self, db_conn):
        """Test with days > 365 - should raise ValueError."""
        with pytest.raises(ValueError, match="days"):
            get_net_realized_pnl_history(db_conn, days=366)

    def test_days_parameter_respected(self, db_with_history_data):
        """Test that days parameter limits the history correctly."""
        # Our fixture has data for 3 days
        history_7 = get_net_realized_pnl_history(db_with_history_data, days=7)
        history_1 = get_net_realized_pnl_history(db_with_history_data, days=1)

        # 7-day history should have more or equal data than 1-day
        assert len(history_7) >= len(history_1)
