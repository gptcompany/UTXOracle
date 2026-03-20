from __future__ import annotations

import sqlite3
from datetime import timezone

import httpx
import pytest

from scripts.live.source_clients import (
    BrkClient,
    ElectrsClient,
    HyperliquidSnapshotClient,
    MempoolApiClient,
)


@pytest.mark.asyncio
async def test_electrs_client_reads_tip_height():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/blocks/tip/height"
        return httpx.Response(200, text="941453")

    client = ElectrsClient(base_url="http://electrs.local", transport=httpx.MockTransport(handler))
    result = await client.fetch_tip_height()
    await client.aclose()

    assert result.value == 941453
    assert result.health.status == "healthy"
    assert result.health.observed_height == 941453


@pytest.mark.asyncio
async def test_mempool_client_reads_usd_price():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/prices"
        return httpx.Response(200, json={"time": 1774026850, "USD": 69834})

    client = MempoolApiClient(base_url="http://mempool.local", transport=httpx.MockTransport(handler))
    result = await client.fetch_exchange_price()
    await client.aclose()

    assert result.value == 69834.0
    assert result.health.status == "healthy"
    assert result.source_timestamp.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_brk_client_fetches_curated_features_via_bulk_metrics():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/metrics/bulk"
        assert request.url.params["metrics"] == "realized_price_usd,liveliness,reserve_risk"
        return httpx.Response(
            200,
            json=[
                {"stamp": "2026-03-20T17:13:19Z", "data": [54311.39]},
                {"stamp": "2026-03-20T17:13:19Z", "data": [0.6380666186]},
                {"stamp": "2026-03-20T17:13:19Z", "data": [4.100239e-06]},
            ],
        )

    client = BrkClient(base_url="http://brk.local", transport=httpx.MockTransport(handler))
    result = await client.fetch_curated_features()
    await client.aclose()

    assert result.health.status == "healthy"
    assert result.value is not None
    assert result.value.brk_realized_price == pytest.approx(54311.39)
    assert result.value.brk_liveliness == pytest.approx(0.6380666186)
    assert result.value.brk_reserve_risk == pytest.approx(4.100239e-06)


@pytest.mark.asyncio
async def test_hyperliquid_client_falls_back_to_filesystem_when_node_api_is_invalid(tmp_path):
    data_dir = tmp_path / "data" / "BTC"
    data_dir.mkdir(parents=True)
    db_path = data_dir / "BTC_main_market_data.db"

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE asset_context (timestamp REAL, oracle_price REAL, funding_rate REAL, open_interest REAL)")
    conn.execute("CREATE TABLE candles (timestamp REAL, mark_price REAL)")
    conn.execute("INSERT INTO asset_context VALUES (1774026800, 84295.4, 0.0, 1.0)")
    conn.execute("INSERT INTO candles VALUES (1774026801, 84310.8)")
    conn.commit()
    conn.close()

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>Grafana Alloy</html>", headers={"content-type": "text/html"})

    client = HyperliquidSnapshotClient(
        base_url="http://hl.local",
        data_root=tmp_path,
        transport=httpx.MockTransport(handler),
    )
    result = await client.fetch_snapshot()
    await client.aclose()

    assert result.health.status == "degraded"
    assert result.value is not None
    assert result.value.source == "filesystem"
    assert result.value.oracle_price == pytest.approx(84295.4)
    assert result.value.mark_price == pytest.approx(84310.8)
