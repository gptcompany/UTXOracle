"""
Pytest configuration and shared fixtures

Add global fixtures here that are used across multiple test modules.
"""

import os

import duckdb
import pytest
from fastapi.testclient import TestClient

# Register plugins for fixtures from separate files (spec-016)
pytest_plugins = ["tests.fixtures.sopr_fixtures"]

if not os.getenv("JWT_SECRET"):
    os.environ["JWT_SECRET"] = "test-secret"


@pytest.fixture
def client():
    """
    FastAPI test client fixture.

    Imports the app and creates a TestClient for making HTTP requests.
    This fixture is used across all API tests.

    Yields:
        TestClient: Configured FastAPI test client
    """
    from api.main import app

    with TestClient(app) as test_client:
        yield test_client


def _populate_wave1_duckdb(db_path, *, base_block: int, delta_block: int) -> None:
    """Create a small DuckDB fixture covering Wave 1 metrics."""
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE utxo_lifecycle (
            txid VARCHAR,
            vout_index INTEGER,
            address VARCHAR,
            creation_block INTEGER,
            btc_value DOUBLE,
            creation_price_usd DOUBLE,
            realized_value_usd DOUBLE,
            is_spent BOOLEAN,
            spent_block INTEGER
        )
        """
    )
    conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")
    conn.execute(
        """
        INSERT INTO utxo_lifecycle VALUES
        ('shrimp_base', 0, 'addr_shrimp', ?, 0.5, 40000.0, 20000.0, FALSE, NULL),
        ('crab_base', 0, 'addr_crab', ?, 5.0, 35000.0, 175000.0, FALSE, NULL),
        ('fish_base', 0, 'addr_fish', ?, 50.0, 30000.0, 1500000.0, FALSE, NULL),
        ('shark_base', 0, 'addr_shark', ?, 500.0, 25000.0, 12500000.0, FALSE, NULL),
        ('whale_base', 0, 'addr_whale', ?, 5000.0, 20000.0, 100000000.0, FALSE, NULL),
        ('humpback_base', 0, 'addr_humpback', ?, 20000.0, 15000.0, 300000000.0, FALSE, NULL),
        ('shrimp_delta', 0, 'addr_shrimp', ?, 0.1, 80000.0, 8000.0, FALSE, NULL),
        ('crab_delta', 0, 'addr_crab', ?, 1.0, 82000.0, 82000.0, FALSE, NULL),
        ('fish_delta', 0, 'addr_fish', ?, 10.0, 84000.0, 840000.0, FALSE, NULL),
        ('shark_delta', 0, 'addr_shark', ?, 100.0, 86000.0, 8600000.0, FALSE, NULL),
        ('whale_delta', 0, 'addr_whale', ?, 1000.0, 88000.0, 88000000.0, FALSE, NULL),
        ('humpback_delta', 0, 'addr_humpback', ?, 2000.0, 90000.0, 180000000.0, FALSE, NULL),
        ('crab_spent_hist', 0, 'addr_crab_spent', ?, 3.0, 33000.0, 99000.0, TRUE, ?),
        ('null_address', 0, NULL, ?, 25.0, 30000.0, 750000.0, FALSE, NULL)
        """,
        [
            base_block,
            base_block,
            base_block,
            base_block,
            base_block,
            base_block,
            delta_block,
            delta_block,
            delta_block,
            delta_block,
            delta_block,
            delta_block,
            base_block + 200,
            delta_block - 500,
            base_block,
        ],
    )
    conn.close()


@pytest.fixture
def wave1_duckdb_path(tmp_path):
    """DuckDB fixture with enough block depth for historical baseline tests."""
    db_path = tmp_path / "wave1.duckdb"
    _populate_wave1_duckdb(db_path, base_block=5000, delta_block=10000)
    return db_path


@pytest.fixture
def wave1_low_history_duckdb_path(tmp_path):
    """DuckDB fixture without enough block depth for 30d historical baseline."""
    db_path = tmp_path / "wave1_low_history.duckdb"
    _populate_wave1_duckdb(db_path, base_block=500, delta_block=1100)
    return db_path


@pytest.fixture
def wave1_client(monkeypatch, wave1_duckdb_path):
    """FastAPI client bound to the Wave 1 DuckDB fixture."""
    from api.main import app
    import api.main

    monkeypatch.setattr(api.main, "UTXO_DB_PATH", str(wave1_duckdb_path))

    test_client = TestClient(app)
    yield test_client
    test_client.close()


@pytest.fixture
def wave1_low_history_client(monkeypatch, wave1_low_history_duckdb_path):
    """FastAPI client bound to a DuckDB fixture without enough history."""
    from api.main import app
    import api.main

    monkeypatch.setattr(api.main, "UTXO_DB_PATH", str(wave1_low_history_duckdb_path))

    test_client = TestClient(app)
    yield test_client
    test_client.close()
