import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb

from api.questdb_repository import QuestDBRepository
from scripts.models.metrics_models import (
    WalletBand,
    WalletBandMetrics,
    WalletWavesResult,
    AbsorptionRateMetrics,
    AbsorptionRatesResult
)
from scripts.metrics.materialize_wave1 import (
    _resolve_current_price,
    main,
    materialize_daily_snapshot,
)

@pytest.fixture
def mock_repo():
    repo = QuestDBRepository()
    repo._send_row = MagicMock(return_value=True)
    repo.sender = MagicMock()
    return repo

def test_save_wallet_waves(mock_repo):
    """Verify that save_wallet_waves calls _send_row for all 6 bands."""
    # Ensure they sum to 100%
    bands = [
        WalletBandMetrics(band=band, supply_btc=100.0, supply_pct=100.0/6.0, address_count=10, avg_balance=10.0)
        for band in WalletBand
    ]
    result = WalletWavesResult(
        timestamp=datetime.now(timezone.utc),
        block_height=800000,
        total_supply_btc=600.0,
        bands=bands,
        retail_supply_pct=50.0,
        institutional_supply_pct=50.0,
        address_count_total=60,
        null_address_btc=0.0,
        confidence=1.0
    )
    
    success = mock_repo.save_wallet_waves(result)
    assert success is True
    assert mock_repo._send_row.call_count == 6
    
    # Check first call details
    args, kwargs = mock_repo._send_row.call_args_list[0]
    assert args[0] == "wallet_waves_daily"
    assert kwargs["symbols"]["band"] == bands[0].band.value
    assert kwargs["columns"]["block_height"] == 800000

def test_save_absorption_rates(mock_repo):
    """Verify that save_absorption_rates calls _send_row for all 6 bands."""
    bands = [
        AbsorptionRateMetrics(
            band=band, absorption_rate=0.5, supply_delta_btc=10.0, 
            supply_start_btc=90.0, supply_end_btc=100.0
        )
        for band in WalletBand
    ]
    result = AbsorptionRatesResult(
        timestamp=datetime.now(timezone.utc),
        block_height=800000,
        window_days=30,
        mined_supply_btc=20.0,
        bands=bands,
        dominant_absorber=WalletBand.SHRIMP,
        retail_absorption=0.5,
        institutional_absorption=0.5,
        confidence=1.0,
        has_historical_data=True
    )
    
    success = mock_repo.save_absorption_rates(result)
    assert success is True
    assert mock_repo._send_row.call_count == 6
    
    # Check details
    args, kwargs = mock_repo._send_row.call_args_list[0]
    assert args[0] == "absorption_rates_daily"
    assert kwargs["columns"]["window_days"] == 30
    assert kwargs["symbols"]["dominant_absorber"] == WalletBand.SHRIMP.value


@pytest.mark.asyncio
async def test_materialize_daily_snapshot_returns_false_on_partial_write_failure():
    """The orchestration layer must fail if any QuestDB write returns False."""
    repo = MagicMock()
    repo.get_latest_price_analysis = AsyncMock(return_value={"utxoracle_price": 85000.0})
    repo.abort_ingestion = MagicMock()
    repo.save_wallet_waves.return_value = True
    repo.save_absorption_rates.return_value = False
    repo.save_address_cohorts.return_value = True

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE utxo_lifecycle (creation_block INTEGER, is_spent BOOLEAN, creation_price_usd DOUBLE, realized_value_usd DOUBLE, btc_value DOUBLE)")
    conn.execute("INSERT INTO utxo_lifecycle VALUES (840000, FALSE, 1000.0, 1000.0, 1.0)")
    conn.execute("CREATE VIEW utxo_lifecycle_full AS SELECT * FROM utxo_lifecycle")

    wallet_waves = MagicMock()
    absorption = MagicMock()
    address_cohorts = MagicMock()

    target_date = datetime.now(timezone.utc)

    with patch(
        "scripts.metrics.materialize_wave1.calculate_wallet_waves",
        return_value=wallet_waves,
    ), patch(
        "scripts.metrics.materialize_wave1.calculate_absorption_rates",
        return_value=absorption,
    ), patch(
        "scripts.metrics.materialize_wave1.calculate_address_cohorts",
        return_value=address_cohorts,
    ):
        success = await materialize_daily_snapshot(repo, conn, target_date)

    conn.close()

    assert success is False
    repo.save_wallet_waves.assert_called_once_with(wallet_waves)
    repo.save_absorption_rates.assert_called_once_with(absorption)
    repo.save_address_cohorts.assert_not_called()
    repo.abort_ingestion.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_current_price_falls_back_to_live_snapshot_field():
    repo = MagicMock()
    repo.get_latest_price_analysis = AsyncMock(return_value=None)
    repo.get_latest_live_snapshot_row = AsyncMock(
        return_value={"utxoracle_price": 87654.32}
    )

    price, source = await _resolve_current_price(repo)

    assert price == pytest.approx(87654.32)
    assert source == "live_snapshots"


@pytest.mark.asyncio
async def test_resolve_current_price_falls_back_to_snapshot_json():
    repo = MagicMock()
    repo.get_latest_price_analysis = AsyncMock(return_value=None)
    repo.get_latest_live_snapshot_row = AsyncMock(
        return_value={"snapshot_json": '{"utxoracle_price": 76543.21}'}
    )

    price, source = await _resolve_current_price(repo)

    assert price == pytest.approx(76543.21)
    assert source == "live_snapshots.snapshot_json"


@pytest.mark.asyncio
async def test_main_uses_fresh_repo_for_backfill_retry(monkeypatch):
    """Backfill should run with a new repository even after an earlier write abort."""
    first_repo = MagicMock()
    first_repo.initialize = AsyncMock()
    first_repo.async_flush_ingestion = AsyncMock(return_value=True)
    first_repo.close = AsyncMock()

    second_repo = MagicMock()
    second_repo.initialize = AsyncMock()
    second_repo.async_flush_ingestion = AsyncMock(return_value=True)
    second_repo.close = AsyncMock()

    repo_factory = MagicMock(side_effect=[first_repo, second_repo])
    fake_conn = MagicMock()

    monkeypatch.setattr("scripts.metrics.materialize_wave1.QuestDBRepository", repo_factory)
    monkeypatch.setattr("scripts.metrics.materialize_wave1.os.path.exists", MagicMock(return_value=True))
    monkeypatch.setattr("scripts.metrics.materialize_wave1.duckdb.connect", MagicMock(return_value=fake_conn))
    monkeypatch.setattr(
        "scripts.metrics.materialize_wave1.materialize_daily_snapshot",
        AsyncMock(side_effect=[False, True]),
    )
    monkeypatch.setattr(
        "scripts.metrics.materialize_wave1.sys.argv",
        ["materialize_wave1.py", "--backfill"],
    )

    await main()

    assert repo_factory.call_count == 2
    first_repo.initialize.assert_awaited_once()
    first_repo.async_flush_ingestion.assert_not_awaited()
    first_repo.close.assert_awaited_once()

    second_repo.initialize.assert_awaited_once()
    second_repo.async_flush_ingestion.assert_awaited_once()
    second_repo.close.assert_awaited_once()
    fake_conn.close.assert_called_once()
