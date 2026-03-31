from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.routes.charts import get_brk_client
from api.routes.live import get_live_snapshot_store
from scripts.live.models import LiveComparison, LiveFeatureSet, LiveSnapshot, SourceHealth


class InMemorySnapshotStore:
    def __init__(self, snapshots: list[LiveSnapshot] | None = None) -> None:
        self.snapshots = list(snapshots or [])

    async def get_latest(self, *, now: datetime | None = None) -> LiveSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None

    async def get_history(self, query=None, *, now: datetime | None = None) -> list[LiveSnapshot]:
        return list(self.snapshots)


def _build_snapshot(*, timestamp: datetime, block_height: int, price: float) -> LiveSnapshot:
    return LiveSnapshot(
        timestamp=timestamp,
        block_height=block_height,
        utxoracle_price=price,
        utxoracle_confidence=0.82,
        mempool_exchange_price=price + 25.0,
        hyperliquid_oracle_price=price + 10.0,
        hyperliquid_mark_price=price + 15.0,
        comparison=LiveComparison(
            utxo_vs_mempool_bps=-2.97,
            utxo_vs_hl_oracle_bps=-1.18,
            utxo_vs_hl_mark_bps=-1.77,
        ),
        features=LiveFeatureSet(
            brk_realized_price=54311.39,
            brk_liveliness=0.6380666186,
            brk_reserve_risk=4.100239e-06,
        ),
        source_health={
            "electrs": SourceHealth(status="healthy", last_success=timestamp, observed_height=block_height),
            "brk": SourceHealth(status="healthy", last_success=timestamp, observed_height=block_height),
            "hyperliquid": SourceHealth(status="healthy", last_success=timestamp, observed_height=block_height),
            "mempool_api": SourceHealth(status="healthy", last_success=timestamp, observed_height=block_height),
            "utxoracle": SourceHealth(status="healthy", last_success=timestamp, observed_height=block_height),
        },
        source_timestamps={
            "electrs": timestamp,
            "brk": timestamp,
            "hyperliquid": timestamp,
            "mempool_api": timestamp,
            "utxoracle": timestamp,
        },
    )


def _build_client(store: InMemorySnapshotStore, *, brk_client=None) -> TestClient:
    from api.apps.live import create_app

    app = create_app()
    app.dependency_overrides[get_live_snapshot_store] = lambda: store
    if brk_client is not None:
        app.dependency_overrides[get_brk_client] = lambda: brk_client
    return TestClient(app)


def test_chart_catalog_exposes_admitted_chart_families():
    store = InMemorySnapshotStore(
        [_build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=84211.52)]
    )

    with _build_client(store) as client:
        response = client.get("/api/v1/charts/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["charts"] == [
        {
            "chart_id": "live-price-comparison",
            "label": "Live Price Comparison",
            "default_window": "1h",
            "supported_windows": ["15m", "1h", "4h", "24h"],
            "overlay_ids": [],
            "series_ids": [
                "utxoracle_price",
                "mempool_exchange_price",
                "hyperliquid_oracle_price",
                "hyperliquid_mark_price",
            ],
        },
        {
            "chart_id": "realized-price-reference",
            "label": "Realized Price Reference",
            "default_window": "24h",
            "supported_windows": ["15m", "1h", "4h", "24h"],
            "overlay_ids": [],
            "series_ids": ["brk_realized_price"],
        },
    ]


def test_live_price_comparison_latest_returns_normalized_chart_payload():
    store = InMemorySnapshotStore(
        [_build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=84211.52)]
    )

    with _build_client(store) as client:
        response = client.get("/api/v1/charts/live-price-comparison/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "v1"
    assert payload["chart_id"] == "live-price-comparison"
    assert payload["window"] == "latest"
    assert payload["is_downsampled"] is False
    assert payload["downsampling_strategy"] is None
    assert payload["metadata"]["status"] == "healthy"
    assert payload["metadata"]["freshness_seconds"] >= 0
    assert len(payload["ts"]) == 1
    assert [series["id"] for series in payload["series"]] == [
        "utxoracle_price",
        "mempool_exchange_price",
        "hyperliquid_oracle_price",
        "hyperliquid_mark_price",
    ]
    assert payload["overlays"] == []


def test_live_price_comparison_history_returns_normalized_series_payload():
    now = datetime.now(timezone.utc)
    store = InMemorySnapshotStore(
        [
            _build_snapshot(timestamp=now - timedelta(minutes=10), block_height=941450, price=84200.0),
            _build_snapshot(timestamp=now - timedelta(minutes=5), block_height=941453, price=84210.0),
            _build_snapshot(timestamp=now, block_height=941456, price=84211.52),
        ]
    )

    with _build_client(store) as client:
        response = client.get("/api/v1/charts/live-price-comparison/history", params={"minutes": 60})

    assert response.status_code == 200
    payload = response.json()
    assert payload["chart_id"] == "live-price-comparison"
    assert payload["window"] == "60m"
    assert payload["downsampling_strategy"] is None
    assert payload["metadata"]["status"] == "healthy"
    assert len(payload["ts"]) == 3
    assert all(len(series["data"]) == 3 for series in payload["series"])


def test_live_price_comparison_history_downsamples_long_windows_by_default():
    now = datetime.now(timezone.utc)
    snapshots = [
        _build_snapshot(
            timestamp=now - timedelta(minutes=1439 - idx),
            block_height=941456 + idx,
            price=84000.0 + idx,
        )
        for idx in range(1440)
    ]

    with _build_client(InMemorySnapshotStore(snapshots)) as client:
        response = client.get("/api/v1/charts/live-price-comparison/history", params={"minutes": 1440})

    assert response.status_code == 200
    payload = response.json()
    assert payload["window"] == "1440m"
    assert payload["is_downsampled"] is True
    assert payload["downsampling_strategy"] == "uniform_stride"
    assert len(payload["ts"]) == 240
    assert payload["ts"][0] == snapshots[0].timestamp.isoformat()
    assert payload["ts"][-1] == snapshots[-1].timestamp.isoformat()
    assert all(len(series["data"]) == 240 for series in payload["series"])


def test_live_price_comparison_history_allows_raw_long_window_reads_when_downsampling_disabled():
    now = datetime.now(timezone.utc)
    snapshots = [
        _build_snapshot(
            timestamp=now - timedelta(minutes=299 - idx),
            block_height=941456 + idx,
            price=84000.0 + idx,
        )
        for idx in range(300)
    ]

    with _build_client(InMemorySnapshotStore(snapshots)) as client:
        response = client.get(
            "/api/v1/charts/live-price-comparison/history",
            params={"minutes": 300, "downsample": "false"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_downsampled"] is False
    assert payload["downsampling_strategy"] is None
    assert len(payload["ts"]) == 300
    assert all(len(series["data"]) == 300 for series in payload["series"])


def test_live_price_comparison_latest_reports_stale_metadata_but_serves_payload():
    stale_timestamp = datetime.now(timezone.utc) - timedelta(seconds=61)
    store = InMemorySnapshotStore([_build_snapshot(timestamp=stale_timestamp, block_height=941456, price=84211.52)])

    with _build_client(store) as client:
        response = client.get("/api/v1/charts/live-price-comparison/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["status"] == "stale"
    assert payload["metadata"]["freshness_seconds"] >= 61


def test_chart_api_rejects_unknown_chart_ids():
    store = InMemorySnapshotStore(
        [_build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=84211.52)]
    )

    with _build_client(store) as client:
        response = client.get("/api/v1/charts/unknown/history", params={"minutes": 60})

    assert response.status_code == 404
    assert response.json()["detail"] == "chart_id not supported"


def test_live_price_comparison_returns_503_when_live_snapshot_is_unavailable():
    with _build_client(InMemorySnapshotStore()) as client:
        response = client.get("/api/v1/charts/live-price-comparison/latest")

    assert response.status_code == 503
    assert response.json()["detail"] == "live chart unavailable"


def test_live_price_comparison_compare_returns_numeric_comparison_payload():
    now = datetime.now(timezone.utc)
    store = InMemorySnapshotStore(
        [
            _build_snapshot(timestamp=now - timedelta(minutes=10), block_height=941450, price=84200.0),
            _build_snapshot(timestamp=now - timedelta(minutes=5), block_height=941453, price=84210.0),
            _build_snapshot(timestamp=now, block_height=941456, price=84211.52),
        ]
    )

    with _build_client(store) as client:
        response = client.get("/api/v1/charts/live-price-comparison/compare", params={"minutes": 60})

    assert response.status_code == 200
    payload = response.json()
    assert payload["chart_id"] == "live-price-comparison"
    assert payload["window"] == "60m"
    assert payload["base_series_id"] == "utxoracle_price"
    assert payload["summary"]["comparison_count"] == 3
    assert payload["summary"]["status"] in {"match", "minor_diff", "major_diff"}
    assert [item["reference_series_id"] for item in payload["comparisons"]] == [
        "mempool_exchange_price",
        "hyperliquid_oracle_price",
        "hyperliquid_mark_price",
    ]
    assert all(item["overlap_points"] == 3 for item in payload["comparisons"])
    assert all("mean_abs_diff" in item for item in payload["comparisons"])
    assert all("mean_relative_diff_pct" in item for item in payload["comparisons"])


def test_live_price_comparison_compare_reports_no_overlap_when_reference_is_missing():
    now = datetime.now(timezone.utc)
    snapshot = _build_snapshot(timestamp=now, block_height=941456, price=84211.52)
    snapshot = snapshot.model_copy(update={"mempool_exchange_price": None})
    store = InMemorySnapshotStore([snapshot])

    with _build_client(store) as client:
        response = client.get("/api/v1/charts/live-price-comparison/compare", params={"minutes": 60})

    assert response.status_code == 200
    payload = response.json()
    mempool = next(item for item in payload["comparisons"] if item["reference_series_id"] == "mempool_exchange_price")
    assert mempool["status"] == "no_overlap"
    assert mempool["overlap_points"] == 0


def test_live_price_comparison_compare_keeps_match_at_point_five_percent_boundary():
    snapshot = _build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=100.5)
    snapshot = snapshot.model_copy(
        update={
            "mempool_exchange_price": 100.0,
            "hyperliquid_oracle_price": 100.5,
            "hyperliquid_mark_price": 100.5,
        }
    )

    with _build_client(InMemorySnapshotStore([snapshot])) as client:
        response = client.get("/api/v1/charts/live-price-comparison/compare", params={"minutes": 60})

    assert response.status_code == 200
    payload = response.json()
    mempool = next(item for item in payload["comparisons"] if item["reference_series_id"] == "mempool_exchange_price")
    assert mempool["mean_relative_diff_pct"] == 0.5
    assert mempool["status"] == "match"


def test_live_price_comparison_compare_keeps_minor_diff_at_two_percent_boundary():
    snapshot = _build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=102.0)
    snapshot = snapshot.model_copy(
        update={
            "mempool_exchange_price": 100.0,
            "hyperliquid_oracle_price": 102.0,
            "hyperliquid_mark_price": 102.0,
        }
    )

    with _build_client(InMemorySnapshotStore([snapshot])) as client:
        response = client.get("/api/v1/charts/live-price-comparison/compare", params={"minutes": 60})

    assert response.status_code == 200
    payload = response.json()
    mempool = next(item for item in payload["comparisons"] if item["reference_series_id"] == "mempool_exchange_price")
    assert mempool["mean_relative_diff_pct"] == 2.0
    assert mempool["status"] == "minor_diff"


def test_live_price_comparison_compare_transitions_to_major_diff_above_two_percent():
    snapshot = _build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=102.01)
    snapshot = snapshot.model_copy(
        update={
            "mempool_exchange_price": 100.0,
            "hyperliquid_oracle_price": 102.01,
            "hyperliquid_mark_price": 102.01,
        }
    )

    with _build_client(InMemorySnapshotStore([snapshot])) as client:
        response = client.get("/api/v1/charts/live-price-comparison/compare", params={"minutes": 60})

    assert response.status_code == 200
    payload = response.json()
    mempool = next(item for item in payload["comparisons"] if item["reference_series_id"] == "mempool_exchange_price")
    assert mempool["mean_relative_diff_pct"] == 2.01
    assert mempool["status"] == "major_diff"


def test_realized_price_reference_latest_returns_brk_realized_price_series():
    store = InMemorySnapshotStore(
        [_build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=84211.52)]
    )

    with _build_client(store) as client:
        response = client.get("/api/v1/charts/realized-price-reference/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["chart_id"] == "realized-price-reference"
    assert payload["window"] == "latest"
    assert [series["id"] for series in payload["series"]] == ["brk_realized_price"]
    assert payload["series"][0]["data"] == [54311.39]
    assert payload["metadata"]["status"] == "healthy"


def test_realized_price_reference_ignores_unrelated_hyperliquid_staleness():
    snapshot = _build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=84211.52)
    snapshot = snapshot.model_copy(
        update={
            "source_health": {
                **snapshot.source_health,
                "hyperliquid": SourceHealth(status="stale", last_success=snapshot.timestamp),
            }
        }
    )

    with _build_client(InMemorySnapshotStore([snapshot])) as client:
        response = client.get("/api/v1/charts/realized-price-reference/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["status"] == "healthy"
    assert payload["source_health_summary"] == "brk:healthy"


def test_realized_price_reference_history_returns_single_series_payload():
    now = datetime.now(timezone.utc)
    first = _build_snapshot(timestamp=now - timedelta(minutes=10), block_height=941450, price=84200.0)
    second = _build_snapshot(timestamp=now - timedelta(minutes=5), block_height=941453, price=84210.0)
    third = _build_snapshot(timestamp=now, block_height=941456, price=84211.52)
    second = second.model_copy(update={"features": second.features.model_copy(update={"brk_realized_price": 54312.00})})
    third = third.model_copy(update={"features": third.features.model_copy(update={"brk_realized_price": 54313.25})})
    store = InMemorySnapshotStore([first, second, third])

    with _build_client(store) as client:
        response = client.get("/api/v1/charts/realized-price-reference/history", params={"minutes": 60})

    assert response.status_code == 200
    payload = response.json()
    assert payload["chart_id"] == "realized-price-reference"
    assert payload["window"] == "60m"
    assert len(payload["ts"]) == 3
    assert payload["series"] == [
        {
            "id": "brk_realized_price",
            "label": "BRK Realized Price",
            "unit": "usd",
            "data": [54311.39, 54312.0, 54313.25],
        }
    ]


def test_realized_price_reference_compare_uses_live_brk_reference():
    snapshot = _build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=84211.52)
    fake_brk_client = SimpleNamespace(
        fetch_curated_features=lambda index="day1": _async_result(
            SimpleNamespace(
                value=LiveFeatureSet(brk_realized_price=54311.39, brk_liveliness=None, brk_reserve_risk=None),
                health=SourceHealth(status="healthy"),
                source_timestamp=snapshot.timestamp,
            )
        )
    )

    with _build_client(InMemorySnapshotStore([snapshot]), brk_client=fake_brk_client) as client:
        response = client.get("/api/v1/charts/realized-price-reference/compare", params={"minutes": 60})

    assert response.status_code == 200
    payload = response.json()
    assert payload["chart_id"] == "realized-price-reference"
    assert payload["base_series_id"] == "brk_realized_price"
    assert payload["summary"]["comparison_count"] == 1
    assert payload["summary"]["status"] == "match"
    assert payload["comparisons"] == [
        {
            "reference_series_id": "brk_api_realized_price",
            "overlap_points": 1,
            "mean_abs_diff": 0.0,
            "max_abs_diff": 0.0,
            "mean_relative_diff_pct": 0.0,
            "status": "match",
        }
    ]


def test_realized_price_reference_compare_degrades_when_brk_reference_is_unavailable():
    snapshot = _build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=84211.52)
    fake_brk_client = SimpleNamespace(
        fetch_curated_features=lambda index="day1": _async_result(
            SimpleNamespace(
                value=None,
                health=SourceHealth(status="unavailable", last_error="timeout"),
                source_timestamp=None,
            )
        )
    )

    with _build_client(InMemorySnapshotStore([snapshot]), brk_client=fake_brk_client) as client:
        response = client.get("/api/v1/charts/realized-price-reference/compare", params={"minutes": 60})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "no_overlap"
    assert payload["comparisons"][0]["reference_series_id"] == "brk_api_realized_price"
    assert payload["comparisons"][0]["status"] == "no_overlap"
    assert payload["comparisons"][0]["overlap_points"] == 0


def test_realized_price_reference_compare_degrades_when_brk_client_raises():
    snapshot = _build_snapshot(timestamp=datetime.now(timezone.utc), block_height=941456, price=84211.52)

    async def _raise_timeout(index="day1"):
        raise asyncio.TimeoutError("brk timeout")

    fake_brk_client = SimpleNamespace(fetch_curated_features=_raise_timeout)

    with _build_client(InMemorySnapshotStore([snapshot]), brk_client=fake_brk_client) as client:
        response = client.get("/api/v1/charts/realized-price-reference/compare", params={"minutes": 60})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "no_overlap"
    assert payload["comparisons"][0]["reference_series_id"] == "brk_api_realized_price"
    assert payload["comparisons"][0]["status"] == "no_overlap"
    assert payload["comparisons"][0]["overlap_points"] == 0


async def _async_result(value):
    return value
