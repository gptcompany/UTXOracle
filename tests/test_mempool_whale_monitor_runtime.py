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


def _monitor(monkeypatch, fetch):
    monkeypatch.setattr(
        whale_monitor_module, "load_exchange_addresses", lambda _p: {"csv": "Csv"}
    )
    monitor = MempoolWhaleMonitor()
    monitor.repo = AsyncMock()
    monitor.repo.fetch = fetch
    return monitor


@pytest.mark.asyncio
async def test_preload_reads_address_clusters_with_exchange_filter(monkeypatch):
    queries = []

    async def fetch(query, *args):
        queries.append(query)
        if "active_exchange_registry" in query:
            raise RuntimeError("table does not exist")
        return [{"address": "db", "cluster_id": "Db"}]

    monitor = _monitor(monkeypatch, fetch)
    await monitor._preload_registry()

    assert "FROM address_clusters" in queries[0]
    assert "is_exchange_likely = true" in queries[0]
    assert monitor.registry_cache == {"db": "Db", "csv": "Csv"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["empty", "error"])
async def test_preload_falls_back_to_csv_with_warning(monkeypatch, caplog, failure):
    if failure == "empty":
        fetch = AsyncMock(return_value=[])
    else:
        fetch = AsyncMock(side_effect=RuntimeError("boom"))
    monitor = _monitor(monkeypatch, fetch)

    with caplog.at_level("INFO"):
        await monitor._preload_registry()

    assert monitor.registry_cache == {"csv": "Csv"}
    assert monitor.is_healthy
    levels = {r.levelname for r in caplog.records}
    assert "WARNING" in levels
    assert "ERROR" not in levels
