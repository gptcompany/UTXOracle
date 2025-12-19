"""
Tests for P/L Ratio (Dominance) module (spec-029).

TDD tests - written BEFORE implementation.
These tests MUST FAIL until T007-T015 are implemented.

Test Coverage:
- T004: test_determine_zone_* (zone classification)
- T005: test_calculate_pl_ratio_* (ratio calculation)
- T006: test_edge_cases_* (edge cases)
- T012: test_get_pl_ratio_history_* (history)
"""

from datetime import datetime, date, timedelta
from typing import Generator

import duckdb
import pytest

from scripts.metrics.pl_ratio import (
    calculate_pl_ratio,
    get_pl_ratio_history,
    _determine_zone,
    _calculate_pl_dominance,
)
from scripts.models.metrics_models import (
    PLRatioResult,
    PLRatioHistoryPoint,
    PLDominanceZone,
)


# =============================================================================
# Fixtures (reused from test_net_realized_pnl.py pattern)
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
def db_with_extreme_profit(
    db_conn: duckdb.DuckDBPyConnection,
) -> duckdb.DuckDBPyConnection:
    """Insert test data with extreme profit (ratio > 5.0)."""
    now = datetime.now()
    hour_ago = now - timedelta(hours=1)

    # 10 BTC @ $20k -> $100k = $800k profit, 0 loss
    # Ratio = infinity (but clipped to 1e9)
    test_data = [
        (
            "extreme_p:0",
            "extreme_p",
            0,
            800000,
            hour_ago,
            20000.0,
            10.0,
            200000.0,
            800010,
            now,
            100000.0,
            "spend_ep",
            10,
            0,
            "STH",
            "1d",
            5.0,
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
def db_with_profit_zone(
    db_conn: duckdb.DuckDBPyConnection,
) -> duckdb.DuckDBPyConnection:
    """Insert test data with profit zone (ratio 1.5 - 5.0)."""
    now = datetime.now()
    hour_ago = now - timedelta(hours=1)

    # Profit: 2 BTC @ $50k -> $100k = $100k profit
    # Loss: 1 BTC @ $100k -> $60k = $40k loss
    # Ratio = 100k / 40k = 2.5 (PROFIT zone)
    test_data = [
        (
            "profit_z1:0",
            "profit_z1",
            0,
            800000,
            hour_ago,
            50000.0,
            2.0,
            100000.0,
            800010,
            now,
            100000.0,
            "spend_pz1",
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
            "loss_z1:0",
            "loss_z1",
            0,
            800000,
            hour_ago,
            100000.0,
            1.0,
            100000.0,
            800010,
            now,
            60000.0,
            "spend_lz1",
            10,
            0,
            "STH",
            "1d",
            0.6,
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
def db_with_neutral_zone(
    db_conn: duckdb.DuckDBPyConnection,
) -> duckdb.DuckDBPyConnection:
    """Insert test data with neutral zone (ratio 0.67 - 1.5)."""
    now = datetime.now()
    hour_ago = now - timedelta(hours=1)

    # Profit: 1 BTC @ $50k -> $100k = $50k profit
    # Loss: 1 BTC @ $100k -> $50k = $50k loss
    # Ratio = 1.0 (NEUTRAL zone)
    test_data = [
        (
            "neutral_p:0",
            "neutral_p",
            0,
            800000,
            hour_ago,
            50000.0,
            1.0,
            50000.0,
            800010,
            now,
            100000.0,
            "spend_np",
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
            "neutral_l:0",
            "neutral_l",
            0,
            800000,
            hour_ago,
            100000.0,
            1.0,
            100000.0,
            800010,
            now,
            50000.0,
            "spend_nl",
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
def db_with_loss_zone(
    db_conn: duckdb.DuckDBPyConnection,
) -> duckdb.DuckDBPyConnection:
    """Insert test data with loss zone (ratio 0.2 - 0.67)."""
    now = datetime.now()
    hour_ago = now - timedelta(hours=1)

    # Profit: 0.5 BTC @ $50k -> $100k = $25k profit
    # Loss: 2 BTC @ $100k -> $50k = $100k loss
    # Ratio = 25k / 100k = 0.25 (LOSS zone)
    test_data = [
        (
            "loss_zp:0",
            "loss_zp",
            0,
            800000,
            hour_ago,
            50000.0,
            0.5,
            25000.0,
            800010,
            now,
            100000.0,
            "spend_lzp",
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
            "loss_zl:0",
            "loss_zl",
            0,
            800000,
            hour_ago,
            100000.0,
            2.0,
            200000.0,
            800010,
            now,
            50000.0,
            "spend_lzl",
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
def db_with_extreme_loss(
    db_conn: duckdb.DuckDBPyConnection,
) -> duckdb.DuckDBPyConnection:
    """Insert test data with extreme loss (ratio < 0.2)."""
    now = datetime.now()
    hour_ago = now - timedelta(hours=1)

    # Profit: 0.1 BTC @ $50k -> $100k = $5k profit
    # Loss: 5 BTC @ $100k -> $50k = $250k loss
    # Ratio = 5k / 250k = 0.02 (EXTREME_LOSS zone)
    test_data = [
        (
            "ext_loss_p:0",
            "ext_loss_p",
            0,
            800000,
            hour_ago,
            50000.0,
            0.1,
            5000.0,
            800010,
            now,
            100000.0,
            "spend_elp",
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
            "ext_loss_l:0",
            "ext_loss_l",
            0,
            800000,
            hour_ago,
            100000.0,
            5.0,
            500000.0,
            800010,
            now,
            50000.0,
            "spend_ell",
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

        # Each day: varying profit/loss ratio
        profit_row = (
            f"hist_p{days_ago}:0",
            f"hist_p{days_ago}",
            0,
            800000,
            creation_ts,
            50000.0,
            float(days_ago),  # Increasing BTC per day
            50000.0 * days_ago,
            800010,
            spent_ts,
            100000.0,
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
            50000.0,
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
# T004: test_determine_zone_* (Zone Classification)
# =============================================================================


class TestDetermineZone:
    """T004: Zone classification tests using ratio thresholds."""

    def test_determine_zone_extreme_profit(self):
        """Test EXTREME_PROFIT zone (ratio > 5.0, dominance > 0.67)."""
        zone = _determine_zone(pl_ratio=6.0)
        assert zone == PLDominanceZone.EXTREME_PROFIT

    def test_determine_zone_profit(self):
        """Test PROFIT zone (ratio 1.5 - 5.0)."""
        zone = _determine_zone(pl_ratio=2.5)
        assert zone == PLDominanceZone.PROFIT

        # Edge cases - 1.5 is boundary (exclusive), so 1.51 is PROFIT
        zone_just_above = _determine_zone(pl_ratio=1.51)
        assert zone_just_above == PLDominanceZone.PROFIT

        zone_upper = _determine_zone(pl_ratio=5.0)
        assert zone_upper == PLDominanceZone.PROFIT

    def test_determine_zone_neutral(self):
        """Test NEUTRAL zone (ratio 0.67 - 1.5)."""
        zone = _determine_zone(pl_ratio=1.0)
        assert zone == PLDominanceZone.NEUTRAL

        # Edge cases - 0.67 is boundary for NEUTRAL
        zone_lower = _determine_zone(pl_ratio=0.67)
        assert zone_lower == PLDominanceZone.NEUTRAL

    def test_determine_zone_loss(self):
        """Test LOSS zone (ratio 0.2 - 0.67)."""
        zone = _determine_zone(pl_ratio=0.4)
        assert zone == PLDominanceZone.LOSS

        # Edge cases
        zone_lower = _determine_zone(pl_ratio=0.2)
        assert zone_lower == PLDominanceZone.LOSS

    def test_determine_zone_extreme_loss(self):
        """Test EXTREME_LOSS zone (ratio < 0.2)."""
        zone = _determine_zone(pl_ratio=0.1)
        assert zone == PLDominanceZone.EXTREME_LOSS

        zone_tiny = _determine_zone(pl_ratio=0.01)
        assert zone_tiny == PLDominanceZone.EXTREME_LOSS

    def test_determine_zone_zero_ratio(self):
        """Test zone when ratio is 0 (all loss, no profit)."""
        zone = _determine_zone(pl_ratio=0.0)
        assert zone == PLDominanceZone.EXTREME_LOSS

    def test_determine_zone_infinite_ratio(self):
        """Test zone when ratio is very large (all profit, no loss)."""
        zone = _determine_zone(pl_ratio=1e9)
        assert zone == PLDominanceZone.EXTREME_PROFIT


# =============================================================================
# T005: test_calculate_pl_ratio_* (Ratio Calculation)
# =============================================================================


class TestCalculatePLRatio:
    """T005: P/L ratio calculation tests."""

    def test_calculate_pl_ratio_extreme_profit(self, db_with_extreme_profit):
        """Test P/L ratio with extreme profit data."""
        result = calculate_pl_ratio(db_with_extreme_profit, window_hours=24)

        assert isinstance(result, PLRatioResult)
        assert result.pl_ratio >= 5.0 or result.pl_ratio == 1e9  # Infinity case
        assert result.pl_dominance > 0.67
        assert result.profit_dominant is True
        assert result.dominance_zone == PLDominanceZone.EXTREME_PROFIT
        assert result.window_hours == 24

    def test_calculate_pl_ratio_profit_zone(self, db_with_profit_zone):
        """Test P/L ratio in profit zone."""
        result = calculate_pl_ratio(db_with_profit_zone, window_hours=24)

        # Expected: ratio = 100k / 40k = 2.5
        assert result.pl_ratio == pytest.approx(2.5, rel=0.1)
        assert result.profit_dominant is True
        assert result.dominance_zone == PLDominanceZone.PROFIT

        # Dominance = (profit - loss) / (profit + loss) = (100k - 40k) / (100k + 40k) = 0.43
        assert result.pl_dominance == pytest.approx(0.43, rel=0.1)

    def test_calculate_pl_ratio_neutral_zone(self, db_with_neutral_zone):
        """Test P/L ratio in neutral zone (ratio ~1.0)."""
        result = calculate_pl_ratio(db_with_neutral_zone, window_hours=24)

        # Expected: ratio = 50k / 50k = 1.0
        assert result.pl_ratio == pytest.approx(1.0, rel=0.1)
        assert result.profit_dominant is False  # ratio must be > 1 for True
        assert result.dominance_zone == PLDominanceZone.NEUTRAL

        # Dominance = (profit - loss) / (profit + loss) = 0
        assert result.pl_dominance == pytest.approx(0.0, abs=0.1)

    def test_calculate_pl_ratio_loss_zone(self, db_with_loss_zone):
        """Test P/L ratio in loss zone."""
        result = calculate_pl_ratio(db_with_loss_zone, window_hours=24)

        # Expected: ratio = 25k / 100k = 0.25
        assert result.pl_ratio == pytest.approx(0.25, rel=0.1)
        assert result.profit_dominant is False
        assert result.dominance_zone == PLDominanceZone.LOSS

        # Dominance = (25k - 100k) / (25k + 100k) = -0.6
        assert result.pl_dominance == pytest.approx(-0.6, rel=0.1)

    def test_calculate_pl_ratio_extreme_loss(self, db_with_extreme_loss):
        """Test P/L ratio with extreme loss data."""
        result = calculate_pl_ratio(db_with_extreme_loss, window_hours=24)

        # Expected: ratio = 5k / 250k = 0.02
        assert result.pl_ratio < 0.2
        assert result.profit_dominant is False
        assert result.dominance_zone == PLDominanceZone.EXTREME_LOSS
        assert result.pl_dominance < -0.67


# =============================================================================
# T006: test_edge_cases_* (Edge Cases)
# =============================================================================


class TestEdgeCases:
    """T006: Edge case tests for P/L ratio calculation."""

    def test_zero_loss_ratio(self, db_with_extreme_profit):
        """Test ratio when loss = 0 (returns 1e9 for JSON safety)."""
        result = calculate_pl_ratio(db_with_extreme_profit, window_hours=24)

        # When loss = 0, ratio should be 1e9 (not infinity)
        assert result.pl_ratio == 1e9

    def test_zero_profit_plus_loss(self, db_conn):
        """Test dominance when profit + loss = 0 (no activity)."""
        result = calculate_pl_ratio(db_conn, window_hours=24)

        # With no data, dominance should be 0.0
        assert result.pl_dominance == 0.0
        assert result.pl_ratio == 0.0
        assert result.dominance_zone == PLDominanceZone.EXTREME_LOSS

    def test_invalid_window_hours_too_low(self, db_conn):
        """Test with window_hours < 1."""
        with pytest.raises(ValueError, match="window_hours"):
            calculate_pl_ratio(db_conn, window_hours=0)

    def test_invalid_window_hours_too_high(self, db_conn):
        """Test with window_hours > 720."""
        with pytest.raises(ValueError, match="window_hours"):
            calculate_pl_ratio(db_conn, window_hours=721)

    def test_pl_dominance_formula(self):
        """Test dominance formula: (P - L) / (P + L)."""
        # profit = 150, loss = 50 -> dominance = (150-50)/(150+50) = 0.5
        dominance = _calculate_pl_dominance(
            realized_profit_usd=150.0, realized_loss_usd=50.0
        )
        assert dominance == pytest.approx(0.5, rel=0.01)

        # profit = 50, loss = 150 -> dominance = (50-150)/(50+150) = -0.5
        dominance_neg = _calculate_pl_dominance(
            realized_profit_usd=50.0, realized_loss_usd=150.0
        )
        assert dominance_neg == pytest.approx(-0.5, rel=0.01)

        # profit = 100, loss = 100 -> dominance = 0
        dominance_zero = _calculate_pl_dominance(
            realized_profit_usd=100.0, realized_loss_usd=100.0
        )
        assert dominance_zero == 0.0

    def test_pl_dominance_zero_total(self):
        """Test dominance when profit + loss = 0."""
        dominance = _calculate_pl_dominance(
            realized_profit_usd=0.0, realized_loss_usd=0.0
        )
        assert dominance == 0.0


# =============================================================================
# T012: test_get_pl_ratio_history_* (History)
# =============================================================================


class TestGetPLRatioHistory:
    """T012: History retrieval tests."""

    def test_history_retrieval(self, db_with_history_data):
        """Test retrieving historical P/L ratio data."""
        history = get_pl_ratio_history(db_with_history_data, days=7)

        assert isinstance(history, list)
        assert len(history) >= 1

        for point in history:
            assert isinstance(point, PLRatioHistoryPoint)
            assert isinstance(point.date, date)
            assert point.pl_ratio >= 0
            assert -1.0 <= point.pl_dominance <= 1.0
            assert isinstance(point.dominance_zone, PLDominanceZone)

    def test_history_sorted_by_date(self, db_with_history_data):
        """Test that history is sorted by date (oldest first)."""
        history = get_pl_ratio_history(db_with_history_data, days=7)

        if len(history) >= 2:
            for i in range(len(history) - 1):
                assert history[i].date <= history[i + 1].date

    def test_history_empty_database(self, db_conn):
        """Test history with no data."""
        history = get_pl_ratio_history(db_conn, days=7)

        assert isinstance(history, list)
        assert len(history) == 0

    def test_history_invalid_days_too_low(self, db_conn):
        """Test with days < 1."""
        with pytest.raises(ValueError, match="days"):
            get_pl_ratio_history(db_conn, days=0)

    def test_history_invalid_days_too_high(self, db_conn):
        """Test with days > 365."""
        with pytest.raises(ValueError, match="days"):
            get_pl_ratio_history(db_conn, days=366)

    def test_history_days_parameter_respected(self, db_with_history_data):
        """Test that days parameter limits the history correctly."""
        history_7 = get_pl_ratio_history(db_with_history_data, days=7)
        history_1 = get_pl_ratio_history(db_with_history_data, days=1)

        # 7-day history should have more or equal data than 1-day
        assert len(history_7) >= len(history_1)


# =============================================================================
# Model Validation Tests
# =============================================================================


class TestPLRatioResultValidation:
    """Test PLRatioResult dataclass validation."""

    def test_valid_result(self):
        """Test creating a valid PLRatioResult."""
        result = PLRatioResult(
            pl_ratio=2.5,
            pl_dominance=0.43,
            profit_dominant=True,
            dominance_zone=PLDominanceZone.PROFIT,
            realized_profit_usd=100000.0,
            realized_loss_usd=40000.0,
            window_hours=24,
            timestamp=datetime.now(),
        )
        assert result.pl_ratio == 2.5
        assert result.dominance_zone == PLDominanceZone.PROFIT

    def test_invalid_pl_ratio_negative(self):
        """Test that negative pl_ratio raises ValueError."""
        with pytest.raises(ValueError, match="pl_ratio"):
            PLRatioResult(
                pl_ratio=-1.0,
                pl_dominance=0.0,
                profit_dominant=False,
                dominance_zone=PLDominanceZone.NEUTRAL,
                realized_profit_usd=0.0,
                realized_loss_usd=0.0,
                window_hours=24,
                timestamp=datetime.now(),
            )

    def test_invalid_pl_dominance_out_of_range(self):
        """Test that pl_dominance outside [-1, 1] raises ValueError."""
        with pytest.raises(ValueError, match="pl_dominance"):
            PLRatioResult(
                pl_ratio=1.0,
                pl_dominance=1.5,
                profit_dominant=False,
                dominance_zone=PLDominanceZone.NEUTRAL,
                realized_profit_usd=0.0,
                realized_loss_usd=0.0,
                window_hours=24,
                timestamp=datetime.now(),
            )

    def test_invalid_window_hours(self):
        """Test that window_hours outside [1, 720] raises ValueError."""
        with pytest.raises(ValueError, match="window_hours"):
            PLRatioResult(
                pl_ratio=1.0,
                pl_dominance=0.0,
                profit_dominant=False,
                dominance_zone=PLDominanceZone.NEUTRAL,
                realized_profit_usd=0.0,
                realized_loss_usd=0.0,
                window_hours=0,
                timestamp=datetime.now(),
            )

    def test_to_dict_serialization(self):
        """Test to_dict() produces correct JSON-serializable output."""
        now = datetime.now()
        result = PLRatioResult(
            pl_ratio=2.5,
            pl_dominance=0.43,
            profit_dominant=True,
            dominance_zone=PLDominanceZone.PROFIT,
            realized_profit_usd=100000.0,
            realized_loss_usd=40000.0,
            window_hours=24,
            timestamp=now,
        )

        d = result.to_dict()
        assert d["pl_ratio"] == 2.5
        assert d["pl_dominance"] == 0.43
        assert d["profit_dominant"] is True
        assert d["dominance_zone"] == "PROFIT"
        assert d["window_hours"] == 24


class TestPLRatioHistoryPointValidation:
    """Test PLRatioHistoryPoint dataclass validation."""

    def test_valid_history_point(self):
        """Test creating a valid PLRatioHistoryPoint."""
        point = PLRatioHistoryPoint(
            date=date(2025, 12, 19),
            pl_ratio=2.5,
            pl_dominance=0.43,
            dominance_zone=PLDominanceZone.PROFIT,
            realized_profit_usd=100000.0,
            realized_loss_usd=40000.0,
        )
        assert point.date == date(2025, 12, 19)
        assert point.dominance_zone == PLDominanceZone.PROFIT

    def test_to_dict_serialization(self):
        """Test to_dict() produces correct JSON-serializable output."""
        point = PLRatioHistoryPoint(
            date=date(2025, 12, 19),
            pl_ratio=2.5,
            pl_dominance=0.43,
            dominance_zone=PLDominanceZone.PROFIT,
            realized_profit_usd=100000.0,
            realized_loss_usd=40000.0,
        )

        d = point.to_dict()
        assert d["date"] == "2025-12-19"
        assert d["dominance_zone"] == "PROFIT"
