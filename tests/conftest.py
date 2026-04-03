"""
Pytest configuration and shared fixtures

Add global fixtures here that are used across multiple test modules.
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import duckdb
import pytest
from fastapi.testclient import TestClient

from api.questdb_repository import QuestDBRepository

# Register plugins for fixtures from separate files (spec-016)
pytest_plugins = ["tests.fixtures.sopr_fixtures"]

if not os.getenv("JWT_SECRET"):
    os.environ["JWT_SECRET"] = "test-secret"


@pytest.fixture
def questdb_repo_mock(monkeypatch):
    """Shared QuestDB repository mock for FastAPI lifespan."""
    # Import here to avoid circular imports at module load time
    import api.main
    from api.apps import live as live_app

    mock = MagicMock(spec=QuestDBRepository)
    mock.initialize = AsyncMock()
    mock.close = AsyncMock()

    ts = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)

    mock.get_latest_price_analysis = AsyncMock(
        return_value={
            "ts": ts,
            "utxoracle_price": 85000.0,
            "exchange_price": 85100.0,
            "confidence": 0.92,
            "tx_count": 1800,
            "price_difference": -100.0,
            "avg_pct_diff": -0.12,
            "is_valid": True,
        }
    )

    mock.get_latest_metrics = AsyncMock(
        return_value={
            "ts": ts,
            "signal_mean": 0.15,
            "signal_std": 0.05,
            "ci_lower": 0.05,
            "ci_upper": 0.25,
            "action": "BUY",
            "action_confidence": 0.85,
            "n_samples": 1000,
            "distribution_type": "unimodal",
            "block_height": 840000,
            "active_addresses_block": 15000,
            "active_addresses_24h": 850000,
            "unique_senders": 8000,
            "unique_receivers": 7000,
            "is_anomaly": False,
            "tx_count": 450000,
            "tx_volume_btc": 12000.5,
            "tx_volume_usd": 1_020_042_500.0,
            "utxoracle_price_used": 85000.0,
            "low_confidence": False,
        }
    )

    cohorts = []
    for cohort, supply, pct in [
        ("retail", 5.0, 0.25),
        ("mid_tier", 65.0, 3.0),
        ("whale", 1700.0, 80.0),
    ]:
        cohorts.append(
            {
                "block_height": 840000,
                "cohort": cohort,
                "ts": ts,
                "cost_basis": 45000.0,
                "supply_btc": supply,
                "supply_pct": pct,
                "mvrv": 1.0,
                "address_count": 1,
                "current_price_usd": 85000.0,
                "whale_retail_spread": 1.0,
                "whale_retail_mvrv_ratio": 1.0,
                "total_supply_btc": 1770.0,
                "total_addresses": 3,
            }
        )

    wallet_bands = []
    for band, block_height in zip(
        ["shrimp", "crab", "fish", "shark", "whale", "humpback"],
        [10000, 10000, 10000, 10000, 10000, 10000],
    ):
        wallet_bands.append(
            {
                "block_height": block_height,
                "band": band,
                "ts": ts,
                "supply_btc": 1.0,
                "supply_pct": 1.0,
                "address_count": 1,
                "avg_balance": 1.0,
                "total_supply_btc": 6.0,
                "retail_supply_pct": 50.0,
                "institutional_supply_pct": 50.0,
                "address_count_total": 6,
                "null_address_btc": 0.0,
                "confidence": 0.9,
            }
        )

    absorption_bands = []
    for band in ["shrimp", "crab", "fish", "shark", "whale", "humpback"]:
        absorption_bands.append(
            {
                "block_height": 840000,
                "band": band,
                "ts": ts,
                "absorption_rate": 0.45,
                "supply_delta_btc": 1.0,
                "supply_start_btc": 0.5,
                "supply_end_btc": 1.5,
                "window_days": 30,
                "mined_supply_btc": 10.0,
                "dominant_absorber": "whale",
                "retail_absorption": 0.5,
                "institutional_absorption": 0.5,
                "confidence": 0.9,
                "has_historical_data": True,
            }
        )

    mock.get_address_cohorts_latest = AsyncMock(return_value=cohorts)
    mock.get_wallet_waves_latest = AsyncMock(return_value=wallet_bands)
    mock.get_absorption_rates_latest = AsyncMock(return_value=absorption_bands)

    monkeypatch.setattr(api.main, "QuestDBRepository", lambda: mock)
    monkeypatch.setattr(live_app, "QuestDBRepository", lambda: mock)

    main_previous = getattr(api.main.app.state, "questdb_repo", None)
    live_previous = getattr(live_app.app.state, "questdb_repo", None)

    try:
        yield mock
    finally:
        if main_previous is None and hasattr(api.main.app.state, "questdb_repo"):
            delattr(api.main.app.state, "questdb_repo")
        elif main_previous is not None:
            api.main.app.state.questdb_repo = main_previous

        if live_previous is None and hasattr(live_app.app.state, "questdb_repo"):
            delattr(live_app.app.state, "questdb_repo")
        elif live_previous is not None:
            live_app.app.state.questdb_repo = live_previous


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


def _populate_wave2_duckdb(db_path, *, with_unspent: bool = True) -> None:
    """Create a small DuckDB fixture covering NUPL and cost-basis routes."""
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE utxo_lifecycle (
            txid VARCHAR,
            vout_index INTEGER,
            creation_block INTEGER,
            btc_value DOUBLE,
            creation_price_usd DOUBLE,
            realized_value_usd DOUBLE,
            is_spent BOOLEAN
        )
        """
    )
    conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

    if with_unspent:
        conn.execute(
            """
            INSERT INTO utxo_lifecycle VALUES
            ('sth_1', 0, 870000, 1.0, 60000.0, 60000.0, FALSE),
            ('sth_2', 0, 865000, 2.0, 70000.0, 140000.0, FALSE),
            ('lth_1', 0, 800000, 5.0, 30000.0, 150000.0, FALSE),
            ('lth_2', 0, 750000, 10.0, 25000.0, 250000.0, FALSE),
            ('spent_1', 0, 850000, 3.0, 50000.0, 150000.0, TRUE)
            """
        )
    else:
        conn.execute(
            """
            INSERT INTO utxo_lifecycle VALUES
            ('spent_only', 0, 850000, 3.0, 50000.0, 150000.0, TRUE)
            """
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
def wave1_client(monkeypatch, wave1_duckdb_path, questdb_repo_mock):
    """FastAPI client bound to the Wave 1 DuckDB fixture."""
    from api.main import app
    import api.main

    monkeypatch.setattr(api.main, "UTXO_DB_PATH", str(wave1_duckdb_path))

    test_client = TestClient(app)
    test_client.app.state.questdb_repo = questdb_repo_mock
    try:
        yield test_client
    finally:
        if hasattr(test_client.app.state, "questdb_repo"):
            delattr(test_client.app.state, "questdb_repo")
        test_client.close()


@pytest.fixture
def wave1_low_history_client(
    monkeypatch, wave1_low_history_duckdb_path, questdb_repo_mock
):
    """FastAPI client bound to a DuckDB fixture without enough history."""
    from api.main import app
    import api.main

    monkeypatch.setattr(api.main, "UTXO_DB_PATH", str(wave1_low_history_duckdb_path))

    test_client = TestClient(app)
    test_client.app.state.questdb_repo = questdb_repo_mock
    try:
        yield test_client
    finally:
        if hasattr(test_client.app.state, "questdb_repo"):
            delattr(test_client.app.state, "questdb_repo")
        test_client.close()


@pytest.fixture
def wave2_duckdb_path(tmp_path):
    """DuckDB fixture with enough data for NUPL and cost-basis serving tests."""
    db_path = tmp_path / "wave2.duckdb"
    _populate_wave2_duckdb(db_path, with_unspent=True)
    return db_path


@pytest.fixture
def wave2_empty_snapshot_duckdb_path(tmp_path):
    """DuckDB fixture with schema present but no usable unspent snapshot."""
    db_path = tmp_path / "wave2_empty.duckdb"
    _populate_wave2_duckdb(db_path, with_unspent=False)
    return db_path


@pytest.fixture
def wave2_client(monkeypatch, wave2_duckdb_path):
    """FastAPI client bound to the Wave 2 DuckDB fixture."""
    from api.main import app
    import api.main

    monkeypatch.setattr(api.main, "UTXO_DB_PATH", str(wave2_duckdb_path))

    test_client = TestClient(app)
    yield test_client
    test_client.close()


@pytest.fixture
def wave2_empty_snapshot_client(monkeypatch, wave2_empty_snapshot_duckdb_path):
    """FastAPI client bound to a Wave 2 DuckDB fixture without usable data."""
    from api.main import app
    import api.main

    monkeypatch.setattr(api.main, "UTXO_DB_PATH", str(wave2_empty_snapshot_duckdb_path))

    test_client = TestClient(app)
    yield test_client
    test_client.close()
