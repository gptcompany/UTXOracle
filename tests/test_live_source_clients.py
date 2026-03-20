from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import zstandard as zstd

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
async def test_hyperliquid_client_reads_filtered_oracle_updates_from_zst(tmp_path):
    stream_dir = tmp_path / "filtered" / "hip3_oracle_updates_by_block" / "hourly" / "20260320"
    stream_dir.mkdir(parents=True)
    zst_path = stream_dir / "17.zst"
    now = datetime.now(timezone.utc)
    mark_time = now.replace(microsecond=0)
    oracle_time = (mark_time - timedelta(seconds=1)).replace(microsecond=0)
    payload = {
        "local_time": now.isoformat().replace("+00:00", "Z"),
        "block_time": mark_time.isoformat().replace("+00:00", "Z"),
        "block_number": 929999999,
        "events": [
            {
                "oracle_pxs": {
                    "coin_to_mark_px": [["cash:BTC", {"px": "84310.8", "last_update_time": mark_time.isoformat().replace("+00:00", "Z")}]],
                    "coin_to_oracle_px": [["cash:BTC", {"px": "84295.4", "last_update_time": oracle_time.isoformat().replace("+00:00", "Z")}]],
                }
            }
        ],
    }
    compressor = zstd.ZstdCompressor()
    zst_path.write_bytes(compressor.compress((json.dumps(payload) + "\n").encode("utf-8")))

    async def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP API should not be queried when filtered data is available and fresh")

    client = HyperliquidSnapshotClient(
        base_url="http://hl.local/info",
        data_root=tmp_path,
        transport=httpx.MockTransport(handler),
    )
    result = await client.fetch_snapshot()
    await client.aclose()

    assert result.health.status == "healthy"
    assert result.value is not None
    assert result.value.source == "filesystem"
    assert result.value.oracle_price == pytest.approx(84295.4)
    assert result.value.mark_price == pytest.approx(84310.8)


@pytest.mark.asyncio
async def test_hyperliquid_client_parses_meta_and_asset_ctxs_when_filesystem_absent(tmp_path):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/info"
        assert json.loads(request.content.decode("utf-8")) == {"type": "metaAndAssetCtxs"}
        return httpx.Response(
            200,
            json=[
                {"universe": [{"name": "BTC", "szDecimals": 5}]},
                [{"oraclePx": "84295.4", "markPx": "84310.8", "time": 1774026840}],
            ],
        )

    client = HyperliquidSnapshotClient(
        base_url="http://hl.local/info",
        data_root=tmp_path / "missing",
        info_request_type="metaAndAssetCtxs",
        transport=httpx.MockTransport(handler),
    )
    result = await client.fetch_snapshot()
    await client.aclose()

    assert result.health.status == "healthy"
    assert result.value is not None
    assert result.value.source == "api"
    assert result.value.oracle_price == pytest.approx(84295.4)
    assert result.value.mark_price == pytest.approx(84310.8)


@pytest.mark.asyncio
async def test_hyperliquid_client_preserves_legacy_sqlite_fallback(tmp_path):
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

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "unsupported"})

    client = HyperliquidSnapshotClient(
        base_url="http://hl.local/info",
        data_root=tmp_path,
        transport=httpx.MockTransport(handler),
    )
    result = await client.fetch_snapshot()
    await client.aclose()

    assert result.value is not None
    assert result.value.source == "filesystem"
    assert result.value.oracle_price == pytest.approx(84295.4)
    assert result.value.mark_price == pytest.approx(84310.8)
