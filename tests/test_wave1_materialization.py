import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from api.questdb_repository import QuestDBRepository
from scripts.models.metrics_models import (
    WalletBand,
    WalletBandMetrics,
    WalletWavesResult,
    AbsorptionRateMetrics,
    AbsorptionRatesResult
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
