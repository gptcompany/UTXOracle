from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import scripts.mempool_whale_monitor as whale_monitor_module
from scripts.mempool_whale_monitor import MempoolWhaleMonitor


@pytest.mark.asyncio
async def test_reload_exchange_registry_rebuilds_cache(monkeypatch):
    snapshots = iter(
        [
            {"old_csv_addr": "OldCsv"},
            {"new_csv_addr": "NewCsv"},
        ]
    )
    monkeypatch.setattr(
        whale_monitor_module,
        "load_exchange_addresses",
        lambda _path: next(snapshots),
    )

    monitor = MempoolWhaleMonitor()
    monitor.repo = AsyncMock()

    assert monitor.registry_cache == {"old_csv_addr": "OldCsv"}

    await monitor.reload_exchange_registry()

    assert monitor.exchange_addresses == {"new_csv_addr": "NewCsv"}
    assert monitor.registry_cache == {"new_csv_addr": "NewCsv"}
    assert "old_csv_addr" not in monitor.registry_cache


@pytest.mark.asyncio
async def test_preload_is_csv_only_quiet_and_never_queries_the_db(monkeypatch, caplog):
    monkeypatch.setattr(
        whale_monitor_module,
        "load_exchange_addresses",
        lambda _p: {"a1": "Binance", "a2": "Binance", "a3": "Kraken"},
    )
    monitor = MempoolWhaleMonitor()
    monitor.repo = AsyncMock()

    with caplog.at_level("DEBUG"):
        await monitor._preload_registry()

    monitor.repo.fetch.assert_not_called()
    monitor.repo.fetchrow.assert_not_called()
    assert monitor.registry_cache == {"a1": "Binance", "a2": "Binance", "a3": "Kraken"}
    assert monitor.is_healthy
    assert not [r for r in caplog.records if r.levelname in ("WARNING", "ERROR")]
    info = [
        r.getMessage() for r in caplog.records if "Registry preloaded" in r.getMessage()
    ]
    assert len(info) == 1
    assert "3 rows" in info[0] and "2 distinct exchanges" in info[0]
