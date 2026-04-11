from __future__ import annotations

import json
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
        assert request.url.params["metrics"] == "realized_price_usd,liveliness,reserve_risk,nupl_ratio,sopr_24h"
        return httpx.Response(
            200,
            json=[
                {"stamp": "2026-03-20T17:13:19Z", "data": [54311.39]},
                {"stamp": "2026-03-20T17:13:19Z", "data": [0.6380666186]},
                {"stamp": "2026-03-20T17:13:19Z", "data": [4.100239e-06]},
                {"stamp": "2026-03-20T17:13:19Z", "data": [0.55]},
                {"stamp": "2026-03-20T17:13:19Z", "data": [1.02]},
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
    assert result.value.brk_nupl == pytest.approx(0.55)
    assert result.value.brk_sopr == pytest.approx(1.02)

@pytest.mark.asyncio
async def test_brk_client_tolerates_partial_bulk_payload_with_metric_names():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "metric": "reserve_risk",
                    "stamp": "2026-03-20T17:13:19Z",
                    "data": [4.100239e-06],
                },
                {
                    "metric": "realized_price_usd",
                    "stamp": "2026-03-20T17:13:19Z",
                    "data": [54311.39],
                },
            ],
        )

    client = BrkClient(base_url="http://brk.local", transport=httpx.MockTransport(handler))
    result = await client.fetch_curated_features()
    await client.aclose()

    assert result.health.status == "degraded"
    assert result.value is not None
    assert result.value.brk_realized_price == pytest.approx(54311.39)
    assert result.value.brk_liveliness is None
    assert result.value.brk_reserve_risk == pytest.approx(4.100239e-06)
    assert result.health.details["missing_metrics"] == ["liveliness", "nupl_ratio", "sopr_24h"]


@pytest.mark.asyncio
async def test_brk_client_tolerates_partial_unnamed_bulk_payload():
    async def handler(_request: httpx.Request) -> httpx.Response:
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

    assert result.health.status == "degraded"
    assert result.value is not None
    assert result.value.brk_realized_price == pytest.approx(54311.39)
    assert result.value.brk_liveliness == pytest.approx(0.6380666186)
    assert result.value.brk_reserve_risk == pytest.approx(4.100239e-06)
    assert result.value.brk_nupl is None
    assert result.value.brk_sopr is None
    assert result.health.details["missing_metrics"] == ["nupl_ratio", "sopr_24h"]


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
async def test_hyperliquid_client_prefers_live_btc_namespace_over_cash_placeholder(tmp_path):
    stream_dir = tmp_path / "filtered" / "hip3_oracle_updates_by_block" / "hourly" / "20260331"
    stream_dir.mkdir(parents=True)
    zst_path = stream_dir / "13.zst"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    payload = {
        "local_time": now.isoformat().replace("+00:00", "Z"),
        "block_time": now.isoformat().replace("+00:00", "Z"),
        "block_number": 941261781,
        "events": [
            {
                "oracle_pxs": {
                    "coin_to_mark_px": [
                        ["cash:BTC", {"px": "70000.0", "last_update_time": now.isoformat().replace("+00:00", "Z")}],
                        ["hyna:BTC", {"px": "67271.0", "last_update_time": now.isoformat().replace("+00:00", "Z")}],
                    ],
                    "coin_to_oracle_px": [
                        ["cash:BTC", {"px": "70000.0", "last_update_time": now.isoformat().replace("+00:00", "Z")}],
                        ["hyna:BTC", {"px": "67253.0", "last_update_time": now.isoformat().replace("+00:00", "Z")}],
                    ],
                }
            }
        ],
    }
    compressor = zstd.ZstdCompressor()
    zst_path.write_bytes(compressor.compress((json.dumps(payload) + "\n").encode("utf-8")))

    client = HyperliquidSnapshotClient(base_url="http://hl.local/info", data_root=tmp_path)
    result = await client.fetch_snapshot()
    await client.aclose()

    assert result.health.status == "healthy"
    assert result.value is not None
    assert result.value.oracle_price == pytest.approx(67253.0)
    assert result.value.mark_price == pytest.approx(67271.0)


@pytest.mark.asyncio
async def test_hyperliquid_client_reads_filtered_oracle_updates_from_extensionless_json(tmp_path):
    stream_dir = tmp_path / "filtered" / "hip3_oracle_updates_by_block" / "hourly" / "20260401"
    stream_dir.mkdir(parents=True)
    json_path = stream_dir / "11"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    payload = {
        "local_time": now.isoformat().replace("+00:00", "Z"),
        "block_time": now.isoformat().replace("+00:00", "Z"),
        "block_number": 943207000,
        "events": [
            {
                "oracle_pxs": {
                    "coin_to_mark_px": [
                        ["cash:BTC", {"px": "68643.6", "last_update_time": now.isoformat().replace("+00:00", "Z")}],
                    ],
                    "coin_to_oracle_px": [
                        ["cash:BTC", {"px": "68667.0", "last_update_time": now.isoformat().replace("+00:00", "Z")}],
                    ],
                }
            }
        ],
    }
    json_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    async def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP API should not be queried when extensionless filtered data is fresh")

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
    assert result.value.oracle_price == pytest.approx(68667.0)
    assert result.value.mark_price == pytest.approx(68643.6)


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
