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
