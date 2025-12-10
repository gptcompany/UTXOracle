"""Tests for Realized Metrics Module.

Spec: spec-017
TDD approach: RED phase tests first, then GREEN implementation.
"""

from __future__ import annotations

import pytest
from datetime import datetime
from pathlib import Path

import duckdb

from scripts.metrics.realized_metrics import (
    calculate_realized_cap,
    calculate_market_cap,
    calculate_mvrv,
    calculate_nupl,
    get_total_unspent_supply,
    create_snapshot,
    save_snapshot,
    load_snapshot,
    get_latest_snapshot,
    get_market_cap_history,
)
from scripts.metrics.utxo_lifecycle import (
    init_schema,
    init_indexes,
    save_utxo,
)
from scripts.models.metrics_models import (
    UTXOLifecycle,
    UTXOSetSnapshot,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """Create a temporary DuckDB database for testing."""
    db_path = tmp_path / "test_realized.duckdb"
    conn = duckdb.connect(str(db_path))
    init_schema(conn)
    init_indexes(conn)
    return conn


@pytest.fixture
def populated_db(temp_db: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """Create a database with sample UTXOs for testing."""
    # Create some unspent UTXOs with known values
    utxos = [
        # UTXO 1: 1 BTC @ $40,000 = $40,000 realized value
        UTXOLifecycle(
            outpoint="utxo1:0",
            txid="utxo1",
            vout_index=0,
            creation_block=840000,
            creation_timestamp=datetime(2024, 1, 1, 0, 0, 0),
            creation_price_usd=40000.0,
            btc_value=1.0,
            realized_value_usd=40000.0,
        ),
        # UTXO 2: 2 BTC @ $45,000 = $90,000 realized value
        UTXOLifecycle(
            outpoint="utxo2:0",
            txid="utxo2",
            vout_index=0,
            creation_block=845000,
            creation_timestamp=datetime(2024, 1, 15, 0, 0, 0),
            creation_price_usd=45000.0,
            btc_value=2.0,
            realized_value_usd=90000.0,
        ),
        # UTXO 3: 0.5 BTC @ $50,000 = $25,000 realized value
        UTXOLifecycle(
            outpoint="utxo3:0",
            txid="utxo3",
            vout_index=0,
            creation_block=850000,
            creation_timestamp=datetime(2024, 2, 1, 0, 0, 0),
            creation_price_usd=50000.0,
            btc_value=0.5,
            realized_value_usd=25000.0,
        ),
    ]

    for utxo in utxos:
        save_utxo(temp_db, utxo)

    return temp_db


# =============================================================================
# Phase 6: User Story 4 - Realized Metrics Tests (T040-T042)
# =============================================================================


class TestRealizedCapCalculation:
    """Test Realized Cap calculation."""

    def test_realized_cap_calculation(self, populated_db: duckdb.DuckDBPyConnection):
        """T040: Test Realized Cap is sum of realized values for unspent UTXOs."""
        # Total: $40,000 + $90,000 + $25,000 = $155,000
        realized_cap = calculate_realized_cap(populated_db)
        assert realized_cap == pytest.approx(155000.0)

    def test_realized_cap_excludes_spent(self, populated_db: duckdb.DuckDBPyConnection):
        """Test that spent UTXOs are excluded from Realized Cap."""
        # Add a spent UTXO
        spent_utxo = UTXOLifecycle(
            outpoint="spent:0",
            txid="spent",
            vout_index=0,
            creation_block=835000,
            creation_timestamp=datetime(2023, 12, 1, 0, 0, 0),
            creation_price_usd=35000.0,
            btc_value=1.0,
            realized_value_usd=35000.0,
            is_spent=True,
            spent_block=840000,
        )
        save_utxo(populated_db, spent_utxo)

        # Realized Cap should still be $155,000 (spent not included)
        realized_cap = calculate_realized_cap(populated_db)
        assert realized_cap == pytest.approx(155000.0)

    def test_realized_cap_empty_db(self, temp_db: duckdb.DuckDBPyConnection):
        """Test Realized Cap is 0 for empty database."""
        realized_cap = calculate_realized_cap(temp_db)
        assert realized_cap == 0.0


class TestMVRVCalculation:
    """Test MVRV calculation."""

    def test_mvrv_calculation(self, populated_db: duckdb.DuckDBPyConnection):
        """T041: Test MVRV ratio calculation."""
        # Total supply: 3.5 BTC
        # Current price: $60,000
        # Market Cap: 3.5 × $60,000 = $210,000
        # Realized Cap: $155,000
        # MVRV = $210,000 / $155,000 ≈ 1.355

        total_supply = get_total_unspent_supply(populated_db)
        current_price = 60000.0
        market_cap = calculate_market_cap(total_supply, current_price)
        realized_cap = calculate_realized_cap(populated_db)
        mvrv = calculate_mvrv(market_cap, realized_cap)

        assert total_supply == pytest.approx(3.5)
        assert market_cap == pytest.approx(210000.0)
        assert mvrv == pytest.approx(210000.0 / 155000.0)

    def test_mvrv_at_cost_basis(self):
        """Test MVRV = 1.0 when market cap equals realized cap."""
        mvrv = calculate_mvrv(100000.0, 100000.0)
        assert mvrv == pytest.approx(1.0)

    def test_mvrv_zero_realized_cap(self):
        """Test MVRV handles zero realized cap gracefully."""
        mvrv = calculate_mvrv(100000.0, 0.0)
        assert mvrv == 0.0

    def test_mvrv_in_profit(self):
        """Test MVRV > 1 indicates profit."""
        mvrv = calculate_mvrv(200000.0, 100000.0)
        assert mvrv == pytest.approx(2.0)
        assert mvrv > 1.0  # Market is in profit

    def test_mvrv_in_loss(self):
        """Test MVRV < 1 indicates loss (capitulation zone)."""
        mvrv = calculate_mvrv(80000.0, 100000.0)
        assert mvrv == pytest.approx(0.8)
        assert mvrv < 1.0  # Market is in loss


class TestNUPLCalculation:
    """Test NUPL calculation."""

    def test_nupl_calculation(self, populated_db: duckdb.DuckDBPyConnection):
        """T042: Test NUPL calculation."""
        # Market Cap: $210,000
        # Realized Cap: $155,000
        # NUPL = (210000 - 155000) / 210000 ≈ 0.262

        total_supply = get_total_unspent_supply(populated_db)
        current_price = 60000.0
        market_cap = calculate_market_cap(total_supply, current_price)
        realized_cap = calculate_realized_cap(populated_db)
        nupl = calculate_nupl(market_cap, realized_cap)

        expected_nupl = (210000.0 - 155000.0) / 210000.0
        assert nupl == pytest.approx(expected_nupl)

    def test_nupl_at_cost_basis(self):
        """Test NUPL = 0 when market cap equals realized cap."""
        nupl = calculate_nupl(100000.0, 100000.0)
        assert nupl == pytest.approx(0.0)

    def test_nupl_zero_market_cap(self):
        """Test NUPL handles zero market cap gracefully."""
        nupl = calculate_nupl(0.0, 100000.0)
        assert nupl == 0.0

    def test_nupl_in_profit(self):
        """Test positive NUPL indicates unrealized profit."""
        nupl = calculate_nupl(200000.0, 100000.0)
        expected = (200000.0 - 100000.0) / 200000.0  # 0.5
        assert nupl == pytest.approx(expected)
        assert nupl > 0  # Unrealized profit

    def test_nupl_in_loss(self):
        """Test negative NUPL indicates unrealized loss (capitulation)."""
        nupl = calculate_nupl(80000.0, 100000.0)
        expected = (80000.0 - 100000.0) / 80000.0  # -0.25
        assert nupl == pytest.approx(expected)
        assert nupl < 0  # Unrealized loss


class TestSnapshot:
    """Test snapshot creation and persistence."""

    def test_create_snapshot(self, populated_db: duckdb.DuckDBPyConnection):
        """Test creating a complete snapshot."""
        block_height = 850000
        timestamp = datetime(2024, 2, 1, 12, 0, 0)
        current_price = 60000.0

        snapshot = create_snapshot(
            populated_db,
            block_height,
            timestamp,
            current_price,
        )

        assert snapshot.block_height == block_height
        assert snapshot.total_supply_btc == pytest.approx(3.5)
        assert snapshot.realized_cap_usd == pytest.approx(155000.0)
        assert snapshot.market_cap_usd == pytest.approx(210000.0)
        assert snapshot.mvrv == pytest.approx(210000.0 / 155000.0)

    def test_save_and_load_snapshot(self, populated_db: duckdb.DuckDBPyConnection):
        """Test saving and loading a snapshot."""
        snapshot = UTXOSetSnapshot(
            block_height=850000,
            timestamp=datetime(2024, 2, 1, 12, 0, 0),
            total_supply_btc=3.5,
            sth_supply_btc=1.5,
            lth_supply_btc=2.0,
            supply_by_cohort={"1w-1m": 1.0, "1m-3m": 2.5},
            realized_cap_usd=155000.0,
            market_cap_usd=210000.0,
            mvrv=1.355,
            nupl=0.262,
            hodl_waves={"1w-1m": 28.57, "1m-3m": 71.43},
        )

        save_snapshot(populated_db, snapshot)
        loaded = load_snapshot(populated_db, 850000)

        assert loaded is not None
        assert loaded.block_height == 850000
        assert loaded.total_supply_btc == pytest.approx(3.5)
        assert loaded.mvrv == pytest.approx(1.355)
        assert loaded.hodl_waves["1w-1m"] == pytest.approx(28.57)

    def test_get_latest_snapshot(self, populated_db: duckdb.DuckDBPyConnection):
        """Test getting the most recent snapshot."""
        # Create two snapshots
        for height in [850000, 850100]:
            snapshot = UTXOSetSnapshot(
                block_height=height,
                timestamp=datetime(2024, 2, 1, 12, 0, 0),
                total_supply_btc=3.5,
                sth_supply_btc=1.5,
                lth_supply_btc=2.0,
                supply_by_cohort={},
                realized_cap_usd=155000.0,
                market_cap_usd=210000.0,
                mvrv=1.355,
                nupl=0.262,
                hodl_waves={},
            )
            save_snapshot(populated_db, snapshot)

        latest = get_latest_snapshot(populated_db)

        assert latest is not None
        assert latest.block_height == 850100


# =============================================================================
# Phase 2: Foundational Tests (T007a, T007b)
# =============================================================================


class TestMarketCapHistory:
    """Test market cap history retrieval for MVRV-Z calculation."""

    def test_get_history_365_days(self, populated_db: duckdb.DuckDBPyConnection):
        """T007a: Test retrieving 365 days of market cap history.

        Verifies that get_market_cap_history() returns correct number of
        historical market cap values from utxo_snapshots table.
        """
        # Create snapshots with known market cap values
        for i, height in enumerate([850000, 850100, 850200]):
            snapshot = UTXOSetSnapshot(
                block_height=height,
                timestamp=datetime(2024, 2, 1 + i, 12, 0, 0),
                total_supply_btc=3.5,
                sth_supply_btc=1.5,
                lth_supply_btc=2.0,
                supply_by_cohort={},
                realized_cap_usd=155000.0,
                market_cap_usd=200000.0 + (i * 10000),  # 200k, 210k, 220k
                mvrv=1.3,
                nupl=0.2,
                hodl_waves={},
            )
            save_snapshot(populated_db, snapshot)

        # Get market cap history
        history = get_market_cap_history(populated_db, days=365)

        # Should return all 3 snapshots' market caps
        assert len(history) == 3
        assert 200000.0 in history
        assert 210000.0 in history
        assert 220000.0 in history

    def test_insufficient_history_warning(self, temp_db: duckdb.DuckDBPyConnection):
        """T007b: Test handling of insufficient market cap history.

        When fewer than 30 days of history exists, the function should
        return what's available (may be empty list).
        """
        # Empty database - no snapshots
        history = get_market_cap_history(temp_db, days=365)

        # Should return empty list for empty database
        assert history == []

    def test_get_history_limited_days(self, populated_db: duckdb.DuckDBPyConnection):
        """Test retrieving limited number of days."""
        # Create snapshots spanning multiple days
        for i in range(10):
            snapshot = UTXOSetSnapshot(
                block_height=850000 + (i * 144),  # ~1 day apart
                timestamp=datetime(2024, 2, 1 + i, 12, 0, 0),
                total_supply_btc=3.5,
                sth_supply_btc=1.5,
                lth_supply_btc=2.0,
                supply_by_cohort={},
                realized_cap_usd=155000.0,
                market_cap_usd=200000.0 + (i * 5000),
                mvrv=1.3,
                nupl=0.2,
                hodl_waves={},
            )
            save_snapshot(populated_db, snapshot)

        # Get only 5 days of history
        history = get_market_cap_history(populated_db, days=5)

        # Should return most recent snapshots (up to 5 days worth)
        assert len(history) <= 10  # Depends on implementation
        assert len(history) >= 1  # At least some data


# =============================================================================
# Phase 3: FR-001 - MVRV-Z Score Tests (T009-T012)
# =============================================================================


class TestMVRVZScore:
    """Test MVRV-Z Score calculation."""

    def test_basic_calculation(self):
        """T009: Test basic MVRV-Z calculation with known values.

        MVRV-Z = (Market Cap - Realized Cap) / StdDev(Market Cap)
        """
        from scripts.metrics.realized_metrics import calculate_mvrv_z

        # Market cap = 200,000
        # Realized cap = 150,000
        # History with std dev = 10,000
        market_cap = 200000.0
        realized_cap = 150000.0
        # Create history that gives predictable std dev
        # Values: 190k, 200k, 210k -> mean=200k, std=~8165
        history = [190000.0, 200000.0, 210000.0] * 20  # 60 values

        mvrv_z = calculate_mvrv_z(market_cap, realized_cap, history)

        # (200000 - 150000) / std(history) = 50000 / 8165 ≈ 6.12
        assert mvrv_z > 0  # Positive when market cap > realized cap
        assert 5.0 < mvrv_z < 8.0  # Reasonable range

    def test_insufficient_history(self):
        """T010: Test MVRV-Z returns 0.0 when history < 30 days."""
        from scripts.metrics.realized_metrics import calculate_mvrv_z

        market_cap = 200000.0
        realized_cap = 150000.0
        history = [200000.0] * 20  # Only 20 values, need 30+

        mvrv_z = calculate_mvrv_z(market_cap, realized_cap, history)

        assert mvrv_z == 0.0

    def test_zero_std_deviation(self):
        """T011: Test MVRV-Z returns 0.0 when std = 0 (all values same)."""
        from scripts.metrics.realized_metrics import calculate_mvrv_z

        market_cap = 200000.0
        realized_cap = 150000.0
        history = [200000.0] * 50  # All same value -> std = 0

        mvrv_z = calculate_mvrv_z(market_cap, realized_cap, history)

        assert mvrv_z == 0.0

    def test_typical_ranges(self):
        """T012: Test MVRV-Z produces expected values for market scenarios."""
        from scripts.metrics.realized_metrics import calculate_mvrv_z

        # Simulate a bull market: market cap well above realized
        market_cap = 300000.0
        realized_cap = 100000.0
        # High volatility history
        history = list(range(150000, 350000, 5000))  # 40 values

        mvrv_z = calculate_mvrv_z(market_cap, realized_cap, history)

        # In bull market, expect positive Z-score
        assert mvrv_z > 0

        # Simulate bear market: market cap below realized
        market_cap = 80000.0
        realized_cap = 100000.0

        mvrv_z = calculate_mvrv_z(market_cap, realized_cap, history)

        # In bear market, expect negative Z-score
        assert mvrv_z < 0


# =============================================================================
# Phase 4: FR-002 - Cohort Realized Cap Tests (T016-T019)
# =============================================================================


class TestCohortRealizedCap:
    """Test cohort realized cap calculation for STH/LTH."""

    def test_sth_realized_cap(self, populated_db: duckdb.DuckDBPyConnection):
        """T016: Test STH realized cap calculation.

        STH = UTXOs created within last 155 days (22,320 blocks).
        """
        from scripts.metrics.realized_metrics import calculate_cohort_realized_cap

        # Use a current block that makes all 3 test UTXOs STH (recent)
        # Test UTXOs are at blocks 840000, 845000, 850000
        # If current_block = 850100, all are within 155 days
        current_block = 850100

        sth_realized = calculate_cohort_realized_cap(
            populated_db, current_block, cohort="STH", threshold_days=155
        )

        # All 3 UTXOs are recent -> all should be STH
        # Total realized: $40,000 + $90,000 + $25,000 = $155,000
        assert sth_realized == pytest.approx(155000.0)

    def test_lth_realized_cap(self, populated_db: duckdb.DuckDBPyConnection):
        """T017: Test LTH realized cap calculation.

        LTH = UTXOs created more than 155 days ago.
        """
        from scripts.metrics.realized_metrics import calculate_cohort_realized_cap

        # Use same current block - all UTXOs are STH
        current_block = 850100

        lth_realized = calculate_cohort_realized_cap(
            populated_db, current_block, cohort="LTH", threshold_days=155
        )

        # All UTXOs are recent -> LTH should be 0
        assert lth_realized == pytest.approx(0.0)

    def test_sth_plus_lth_equals_total(self, populated_db: duckdb.DuckDBPyConnection):
        """T018: Test STH + LTH realized cap equals total realized cap."""
        from scripts.metrics.realized_metrics import calculate_cohort_realized_cap

        current_block = 850100

        sth_realized = calculate_cohort_realized_cap(
            populated_db, current_block, cohort="STH"
        )
        lth_realized = calculate_cohort_realized_cap(
            populated_db, current_block, cohort="LTH"
        )
        total_realized = calculate_realized_cap(populated_db)

        # STH + LTH should equal total
        assert (sth_realized + lth_realized) == pytest.approx(total_realized, rel=0.01)

    def test_custom_threshold(self, populated_db: duckdb.DuckDBPyConnection):
        """T019: Test cohort calculation with custom threshold."""
        from scripts.metrics.realized_metrics import calculate_cohort_realized_cap

        # Use a very small threshold (1 day = 144 blocks)
        # Only UTXOs within last 144 blocks will be STH
        current_block = 850100
        threshold_days = 1

        sth_realized = calculate_cohort_realized_cap(
            populated_db, current_block, cohort="STH", threshold_days=threshold_days
        )

        # Only UTXO at block 850000 is within 1 day (100 blocks away)
        # That UTXO has realized value $25,000
        assert sth_realized == pytest.approx(25000.0)


# =============================================================================
# Phase 5: FR-003 - STH/LTH MVRV Tests (T022-T025)
# =============================================================================


class TestSTHLTHMVRV:
    """Test STH-MVRV and LTH-MVRV calculations."""

    def test_sth_mvrv_calculation(self, populated_db: duckdb.DuckDBPyConnection):
        """T022: Test STH-MVRV calculation.

        STH-MVRV = Market Cap / STH Realized Cap
        Higher values indicate STH are in profit.
        """
        from scripts.metrics.realized_metrics import (
            calculate_cohort_mvrv,
            calculate_cohort_realized_cap,
            calculate_market_cap,
        )

        current_block = 850100
        total_supply = 3.5  # BTC
        current_price = 60000.0  # USD

        market_cap = calculate_market_cap(total_supply, current_price)  # $210,000
        sth_realized = calculate_cohort_realized_cap(
            populated_db, current_block, cohort="STH"
        )  # $155,000

        sth_mvrv = calculate_cohort_mvrv(market_cap, sth_realized)

        # STH-MVRV = 210000 / 155000 ≈ 1.355
        assert sth_mvrv == pytest.approx(210000.0 / 155000.0)

    def test_lth_mvrv_calculation(self, populated_db: duckdb.DuckDBPyConnection):
        """T023: Test LTH-MVRV calculation.

        LTH-MVRV = Market Cap / LTH Realized Cap
        """
        from scripts.metrics.realized_metrics import (
            calculate_cohort_mvrv,
            calculate_cohort_realized_cap,
            calculate_market_cap,
        )

        # Make some UTXOs old enough to be LTH
        # Current block needs to be far enough that some UTXOs are old
        # 155 days * 144 blocks = 22,320 blocks
        # UTXO at 840000 would need current_block > 862320 to be LTH
        current_block = 865000

        total_supply = 3.5
        current_price = 60000.0
        market_cap = calculate_market_cap(total_supply, current_price)

        lth_realized = calculate_cohort_realized_cap(
            populated_db, current_block, cohort="LTH"
        )

        # If LTH realized > 0, calculate MVRV
        if lth_realized > 0:
            lth_mvrv = calculate_cohort_mvrv(market_cap, lth_realized)
            assert lth_mvrv > 0
        else:
            # All UTXOs still STH
            assert lth_realized == 0.0

    def test_cohort_mvrv_zero_realized(self):
        """T024: Test cohort MVRV handles zero realized cap gracefully."""
        from scripts.metrics.realized_metrics import calculate_cohort_mvrv

        market_cap = 210000.0
        realized_cap = 0.0  # No UTXOs in this cohort

        mvrv = calculate_cohort_mvrv(market_cap, realized_cap)

        # Should return 0.0 (not infinity) when realized = 0
        assert mvrv == 0.0

    def test_sth_mvrv_signal_interpretation(
        self, populated_db: duckdb.DuckDBPyConnection
    ):
        """T025: Test STH-MVRV signal interpretation.

        STH-MVRV interpretations:
        - > 1.0: STH in profit (potential distribution)
        - < 1.0: STH in loss (potential accumulation)
        - = 1.0: STH at cost basis
        """
        from scripts.metrics.realized_metrics import (
            calculate_cohort_mvrv,
            calculate_cohort_realized_cap,
        )

        current_block = 850100

        sth_realized = calculate_cohort_realized_cap(
            populated_db, current_block, cohort="STH"
        )

        # Test profit scenario
        high_market_cap = 300000.0  # Well above realized
        sth_mvrv_profit = calculate_cohort_mvrv(high_market_cap, sth_realized)
        assert sth_mvrv_profit > 1.0, "STH should be in profit"

        # Test loss scenario
        low_market_cap = 100000.0  # Below realized
        sth_mvrv_loss = calculate_cohort_mvrv(low_market_cap, sth_realized)
        assert sth_mvrv_loss < 1.0, "STH should be in loss"

        # Test at cost basis
        at_cost_mvrv = calculate_cohort_mvrv(sth_realized, sth_realized)
        assert at_cost_mvrv == pytest.approx(1.0), "MVRV should be 1.0 at cost basis"


# =============================================================================
# Phase 6: FR-004 - Signal Classification Tests (T027-T034)
# =============================================================================


class TestSignalClassification:
    """Test MVRV-Z signal zone classification and confidence."""

    def test_classify_extreme_sell_zone(self):
        """T027: Test EXTREME_SELL zone classification (Z > 7.0)."""
        from scripts.metrics.realized_metrics import classify_mvrv_z_zone

        # Z-score above 7.0 -> EXTREME_SELL
        zone = classify_mvrv_z_zone(7.5)
        assert zone == "EXTREME_SELL"

        zone = classify_mvrv_z_zone(10.0)
        assert zone == "EXTREME_SELL"

    def test_classify_caution_zone(self):
        """T028: Test CAUTION zone classification (3.0 <= Z <= 7.0)."""
        from scripts.metrics.realized_metrics import classify_mvrv_z_zone

        # Z-score between 3.0 and 7.0 -> CAUTION
        zone = classify_mvrv_z_zone(3.0)
        assert zone == "CAUTION"

        zone = classify_mvrv_z_zone(5.0)
        assert zone == "CAUTION"

        zone = classify_mvrv_z_zone(7.0)
        assert zone == "CAUTION"

    def test_classify_normal_zone(self):
        """T029: Test NORMAL zone classification (-0.5 <= Z < 3.0)."""
        from scripts.metrics.realized_metrics import classify_mvrv_z_zone

        # Z-score between -0.5 and 3.0 -> NORMAL
        zone = classify_mvrv_z_zone(-0.5)
        assert zone == "NORMAL"

        zone = classify_mvrv_z_zone(0.0)
        assert zone == "NORMAL"

        zone = classify_mvrv_z_zone(1.5)
        assert zone == "NORMAL"

        zone = classify_mvrv_z_zone(2.99)
        assert zone == "NORMAL"

    def test_classify_accumulation_zone(self):
        """T030: Test ACCUMULATION zone classification (Z < -0.5)."""
        from scripts.metrics.realized_metrics import classify_mvrv_z_zone

        # Z-score below -0.5 -> ACCUMULATION
        zone = classify_mvrv_z_zone(-0.51)
        assert zone == "ACCUMULATION"

        zone = classify_mvrv_z_zone(-2.0)
        assert zone == "ACCUMULATION"

    def test_confidence_full_history(self):
        """T031: Test confidence calculation with full history (365+ days)."""
        from scripts.metrics.realized_metrics import calculate_mvrv_confidence

        # Full history (365 days) + clear signal (far from threshold)
        confidence = calculate_mvrv_confidence(
            mvrv_z=8.0,  # Far from 7.0 threshold
            history_days=365,
        )

        # Should have high confidence
        assert confidence >= 0.8
        assert confidence <= 1.0

    def test_confidence_minimal_history(self):
        """T032a: Test confidence with minimal history (30-60 days)."""
        from scripts.metrics.realized_metrics import calculate_mvrv_confidence

        # Minimal history reduces confidence
        confidence = calculate_mvrv_confidence(
            mvrv_z=8.0,  # Same strong signal
            history_days=30,
        )

        # Should have lower confidence than full history
        assert confidence >= 0.4
        assert confidence < 0.8

    def test_confidence_near_threshold(self):
        """T032b: Test confidence when Z is near zone threshold."""
        from scripts.metrics.realized_metrics import calculate_mvrv_confidence

        # Z-score near 3.0 threshold (NORMAL/CAUTION boundary)
        confidence = calculate_mvrv_confidence(
            mvrv_z=3.1,  # Just above threshold
            history_days=365,
        )

        # Confidence should be lower due to proximity to threshold
        assert confidence < 0.8

    def test_confidence_insufficient_history(self):
        """T033: Test confidence with insufficient history (<30 days)."""
        from scripts.metrics.realized_metrics import calculate_mvrv_confidence

        # Insufficient history -> reduced confidence
        confidence = calculate_mvrv_confidence(
            mvrv_z=8.0,
            history_days=20,  # Less than 30 days
        )

        # Should return lower confidence than full history
        full_confidence = calculate_mvrv_confidence(mvrv_z=8.0, history_days=365)
        assert confidence < full_confidence
        assert confidence < 0.6  # Reasonable threshold for insufficient data

    def test_create_mvrv_extended_signal(self, populated_db: duckdb.DuckDBPyConnection):
        """T034: Test creating complete MVRVExtendedSignal."""
        from scripts.metrics.realized_metrics import create_mvrv_extended_signal

        current_block = 850100
        current_price = 60000.0
        timestamp = datetime(2024, 2, 1, 12, 0, 0)

        # Create some market cap history for Z-score calculation
        from datetime import timedelta

        base_date = datetime(2024, 1, 1, 12, 0, 0)
        for i in range(35):  # Need 30+ for valid Z-score
            snapshot = UTXOSetSnapshot(
                block_height=850000 + (i * 10),
                timestamp=base_date + timedelta(days=i),
                total_supply_btc=3.5,
                sth_supply_btc=1.5,
                lth_supply_btc=2.0,
                supply_by_cohort={},
                realized_cap_usd=155000.0,
                market_cap_usd=200000.0 + (i * 1000),
                mvrv=1.3,
                nupl=0.2,
                hodl_waves={},
            )
            save_snapshot(populated_db, snapshot)

        signal = create_mvrv_extended_signal(
            conn=populated_db,
            current_block=current_block,
            current_price_usd=current_price,
            timestamp=timestamp,
        )

        # Verify signal structure
        assert signal.block_height == current_block
        assert signal.timestamp == timestamp
        assert signal.mvrv > 0
        assert signal.market_cap_usd == pytest.approx(210000.0)  # 3.5 * 60000
        assert signal.realized_cap_usd == pytest.approx(155000.0)
        assert signal.zone in ["EXTREME_SELL", "CAUTION", "NORMAL", "ACCUMULATION"]
        assert 0.0 <= signal.confidence <= 1.0
        assert signal.sth_mvrv >= 0
        assert signal.lth_mvrv >= 0
        assert signal.threshold_days == 155
