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
    monitor.repo.fetch = AsyncMock(
        return_value=[{"address": "db_addr", "cluster_id": "DbCluster"}]
    )

    assert monitor.registry_cache == {"old_csv_addr": "OldCsv"}

    await monitor.reload_exchange_registry()

    assert monitor.exchange_addresses == {"new_csv_addr": "NewCsv"}
    assert monitor.registry_cache == {
        "db_addr": "DbCluster",
        "new_csv_addr": "NewCsv",
    }
    assert "old_csv_addr" not in monitor.registry_cache
