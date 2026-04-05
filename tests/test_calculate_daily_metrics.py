import duckdb
import pytest
from datetime import date
from statistics import stdev

from scripts.metrics.calculate_daily_metrics import calculate_daily_mvrv, persist_metrics

def test_calculate_daily_mvrv_success():
    # Setup mock duckdb
    conn = duckdb.connect(':memory:')
    conn.execute('''
        CREATE TABLE utxo_snapshots (
            block_height INTEGER,
            market_cap_usd DOUBLE,
            realized_cap_usd DOUBLE
        )
    ''')
    # Insert some dummy history to satisfy stdev calculation (requires at least 30 items)
    for i in range(40):
        conn.execute(f"INSERT INTO utxo_snapshots VALUES ({i}, {1000 + i * 10}, 800)")

    market_cap = 1500.0
    realized_cap = 1000.0

    mvrv, mvrv_z, mvrv_z_rbn = calculate_daily_mvrv(conn, market_cap, realized_cap)

    assert mvrv == 1.5
    assert mvrv_z is not None
    assert mvrv_z > 0
    assert mvrv_z_rbn is not None
    assert mvrv_z_rbn > 0

def test_calculate_daily_mvrv_insufficient_history():
    conn = duckdb.connect(':memory:')
    conn.execute('''
        CREATE TABLE utxo_snapshots (
            block_height INTEGER,
            market_cap_usd DOUBLE,
            realized_cap_usd DOUBLE
        )
    ''')
    market_cap = 1500.0
    realized_cap = 1000.0

    mvrv, mvrv_z, mvrv_z_rbn = calculate_daily_mvrv(conn, market_cap, realized_cap)

    assert mvrv == 1.5
    assert mvrv_z is not None
    assert mvrv_z_rbn is None

def test_calculate_daily_mvrv_zero_realized_cap():
    conn = duckdb.connect(':memory:')
    market_cap = 1500.0
    realized_cap = 0.0

    mvrv, mvrv_z, mvrv_z_rbn = calculate_daily_mvrv(conn, market_cap, realized_cap)

    assert mvrv is None
    assert mvrv_z is None
    assert mvrv_z_rbn is None


def test_calculate_daily_mvrv_rbn_uses_historical_cutoff():
    conn = duckdb.connect(':memory:')
    conn.execute(
        '''
        CREATE TABLE utxo_snapshots (
            block_height INTEGER,
            market_cap_usd DOUBLE,
            realized_cap_usd DOUBLE
        )
        '''
    )

    # Historical window up to block 40 should determine the score.
    for height in range(1, 41):
        conn.execute(
            "INSERT INTO utxo_snapshots VALUES (?, ?, ?)",
            [height, 1000.0 + (height * 10.0), 800.0],
        )

    # Future rows would distort all-time stdev if they leak into the backfill day.
    for height in range(41, 61):
        conn.execute(
            "INSERT INTO utxo_snapshots VALUES (?, ?, ?)",
            [height, 50_000.0 + height, 800.0],
        )

    market_cap = 1_500.0
    realized_cap = 1_000.0

    _, _, mvrv_z_rbn = calculate_daily_mvrv(
        conn, market_cap, realized_cap, as_of_block=40
    )

    expected_history = [1000.0 + (height * 10.0) for height in range(1, 41)]
    expected = (market_cap - realized_cap) / stdev(expected_history)

    assert mvrv_z_rbn == pytest.approx(expected)


def test_calculate_daily_mvrv_rbn_requires_history_by_backfill_day():
    conn = duckdb.connect(':memory:')
    conn.execute(
        '''
        CREATE TABLE utxo_snapshots (
            block_height INTEGER,
            market_cap_usd DOUBLE,
            realized_cap_usd DOUBLE
        )
        '''
    )

    for height in range(1, 61):
        conn.execute(
            "INSERT INTO utxo_snapshots VALUES (?, ?, ?)",
            [height, 1000.0 + (height * 10.0), 800.0],
        )

    _, _, mvrv_z_rbn = calculate_daily_mvrv(
        conn, 1_500.0, 1_000.0, as_of_block=20
    )

    # Only 20 historical points existed at block 20, so RBN-compatible score
    # should remain unavailable even if later snapshots exist.
    assert mvrv_z_rbn is None


def test_persist_metrics_works_with_legacy_mvrv_daily_schema():
    conn = duckdb.connect(':memory:')
    conn.execute(
        """
        CREATE TABLE mvrv_daily (
            date DATE PRIMARY KEY,
            mvrv DOUBLE,
            mvrv_z DOUBLE,
            market_cap DOUBLE,
            realized_cap DOUBLE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE realized_cap_daily (
            date DATE PRIMARY KEY,
            realized_cap DOUBLE,
            total_supply DOUBLE
        )
        """
    )

    persist_metrics(
        {
            "date": date(2024, 1, 1),
            "mvrv": 1.5,
            "mvrv_z": 0.9,
            "mvrv_z_rbn": 0.7,
            "market_cap": 1500.0,
            "realized_cap": 1000.0,
        },
        conn,
    )

    result = conn.execute(
        "SELECT date, mvrv, mvrv_z, market_cap, realized_cap FROM mvrv_daily"
    ).fetchone()
    assert result == (date(2024, 1, 1), 1.5, 0.9, 1500.0, 1000.0)


def test_persist_metrics_stores_mvrv_z_rbn_when_column_exists():
    conn = duckdb.connect(':memory:')
    conn.execute(
        """
        CREATE TABLE mvrv_daily (
            date DATE PRIMARY KEY,
            mvrv DOUBLE,
            mvrv_z DOUBLE,
            mvrv_z_rbn DOUBLE,
            market_cap DOUBLE,
            realized_cap DOUBLE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE realized_cap_daily (
            date DATE PRIMARY KEY,
            realized_cap DOUBLE,
            total_supply DOUBLE
        )
        """
    )

    persist_metrics(
        {
            "date": date(2024, 1, 2),
            "mvrv": 1.6,
            "mvrv_z": 1.0,
            "mvrv_z_rbn": 0.8,
            "market_cap": 1600.0,
            "realized_cap": 1000.0,
        },
        conn,
    )

    result = conn.execute(
        "SELECT date, mvrv, mvrv_z, mvrv_z_rbn, market_cap, realized_cap FROM mvrv_daily"
    ).fetchone()
    assert result == (date(2024, 1, 2), 1.6, 1.0, 0.8, 1600.0, 1000.0)
