import pytest
import duckdb
from datetime import date
from scripts.metrics.calculate_daily_metrics import calculate_daily_mvrv

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
