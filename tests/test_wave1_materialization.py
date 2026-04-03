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
from scripts.metrics.materialize_wave1 import materialize_daily_snapshot

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
    repo.save_wallet_waves.return_value = True
    repo.save_absorption_rates.return_value = False
    repo.save_address_cohorts.return_value = True

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE utxo_lifecycle (creation_block INTEGER)")
    conn.execute("INSERT INTO utxo_lifecycle VALUES (840000)")
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
    repo.save_address_cohorts.assert_called_once_with(address_cohorts)
