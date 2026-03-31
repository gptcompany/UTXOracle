from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any, AsyncIterator, Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.routes.live import get_live_snapshot_store
from scripts.live.models import LiveHistoryQuery, LiveSnapshot, utc_now
from scripts.live.source_clients import BrkClient
from scripts.live.storage import LiveSnapshotStore

router = APIRouter(prefix="/charts", tags=["charts"])

SUPPORTED_WINDOWS = ["15m", "1h", "4h", "24h"]
LONG_WINDOW_DOWNSAMPLE_MINUTES = 240
MAX_DOWNSAMPLED_POINTS = 240
PRICE_COMPARISON_SERIES: tuple[tuple[str, str, Callable[[LiveSnapshot], float | None]], ...] = (
    ("utxoracle_price", "UTXOracle", lambda snapshot: snapshot.utxoracle_price),
    ("mempool_exchange_price", "Mempool", lambda snapshot: snapshot.mempool_exchange_price),
    ("hyperliquid_oracle_price", "Hyperliquid Oracle", lambda snapshot: snapshot.hyperliquid_oracle_price),
    ("hyperliquid_mark_price", "Hyperliquid Mark", lambda snapshot: snapshot.hyperliquid_mark_price),
)
REALIZED_PRICE_SERIES: tuple[tuple[str, str, Callable[[LiveSnapshot], float | None]], ...] = (
    ("brk_realized_price", "BRK Realized Price", lambda snapshot: snapshot.features.brk_realized_price),
)


@dataclass(frozen=True)
class ChartDefinition:
    chart_id: str
    label: str
    default_window: str
    series_defs: tuple[tuple[str, str, Callable[[LiveSnapshot], float | None]], ...]
    source_dependencies: tuple[str, ...]
    compare_base_series_id: str | None = None


CHART_DEFINITIONS: tuple[ChartDefinition, ...] = (
    ChartDefinition(
        chart_id="live-price-comparison",
        label="Live Price Comparison",
        default_window="1h",
        series_defs=PRICE_COMPARISON_SERIES,
        source_dependencies=("electrs", "mempool_api", "utxoracle", "hyperliquid"),
        compare_base_series_id="utxoracle_price",
    ),
    ChartDefinition(
        chart_id="realized-price-reference",
        label="Realized Price Reference",
        default_window="24h",
        series_defs=REALIZED_PRICE_SERIES,
        source_dependencies=("brk",),
    ),
)
CHARTS_BY_ID = {definition.chart_id: definition for definition in CHART_DEFINITIONS}


class ChartCatalogEntry(BaseModel):
    chart_id: str
    label: str
    default_window: str
    supported_windows: list[str]
    overlay_ids: list[str]
    series_ids: list[str]


class ChartCatalogResponse(BaseModel):
    charts: list[ChartCatalogEntry]


class ChartSeries(BaseModel):
    id: str
    label: str
    unit: str
    data: list[float | None]


class ChartMetadata(BaseModel):
    freshness_seconds: float
    status: str


class ChartPayload(BaseModel):
    schema_version: str
    chart_id: str
    window: str
    is_downsampled: bool
    downsampling_strategy: str | None
    source_health_summary: str
    metadata: ChartMetadata
    ts: list[str]
    series: list[ChartSeries]
    overlays: list[dict[str, Any]]


class ChartComparison(BaseModel):
    reference_series_id: str
    overlap_points: int
    mean_abs_diff: float | None
    max_abs_diff: float | None
    mean_relative_diff_pct: float | None
    status: str


class ChartCompareSummary(BaseModel):
    comparison_count: int
    status: str


class ChartComparePayload(BaseModel):
    chart_id: str
    window: str
    base_series_id: str
    summary: ChartCompareSummary
    comparisons: list[ChartComparison]


@lru_cache(maxsize=1)
def get_chart_catalog() -> ChartCatalogResponse:
    return ChartCatalogResponse(
        charts=[
            ChartCatalogEntry(
                chart_id=definition.chart_id,
                label=definition.label,
                default_window=definition.default_window,
                supported_windows=SUPPORTED_WINDOWS,
                overlay_ids=[],
                series_ids=[series_id for series_id, _, _ in definition.series_defs],
            )
            for definition in CHART_DEFINITIONS
        ]
    )


async def get_brk_client() -> AsyncIterator[BrkClient]:
    client = BrkClient(timeout_seconds=2.0)
    try:
        yield client
    finally:
        await client.aclose()


async def _call_store(store: LiveSnapshotStore, method_name: str, *args, **kwargs):
    async_method = getattr(store, f"a{method_name}", None)
    if async_method is not None:
        return await async_method(*args, **kwargs)

    method = getattr(store, method_name)
    if inspect.iscoroutinefunction(method):
        return await method(*args, **kwargs)
    return await asyncio.to_thread(method, *args, **kwargs)


def _require_supported_chart(chart_id: str) -> ChartDefinition:
    definition = CHARTS_BY_ID.get(chart_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="chart_id not supported")
    return definition


def _relevant_source_health(
    definition: ChartDefinition,
    snapshot: LiveSnapshot,
) -> dict[str, Any]:
    return {
        source_name: health
        for source_name, health in snapshot.source_health.items()
        if source_name in definition.source_dependencies
    }


def _build_status(
    definition: ChartDefinition,
    snapshot: LiveSnapshot,
) -> str:
    age_seconds = (utc_now() - snapshot.timestamp).total_seconds()
    if age_seconds > 60:
        return "stale"
    source_statuses = [
        health.status
        for health in _relevant_source_health(definition, snapshot).values()
    ]
    if source_statuses and all(status == "healthy" for status in source_statuses):
        return "healthy"
    return "degraded"


def _build_source_health_summary(
    definition: ChartDefinition,
    snapshot: LiveSnapshot,
) -> str:
    source_health = _relevant_source_health(definition, snapshot)
    if not source_health:
        return "sources:unavailable"
    return " | ".join(
        f"{source_name}:{health.status}"
        for source_name, health in sorted(source_health.items())
    )


def _build_chart_payload(
    *,
    definition: ChartDefinition,
    snapshots: list[LiveSnapshot],
    window: str,
    downsampling_strategy: str | None = None,
) -> ChartPayload:
    if not snapshots:
        raise HTTPException(status_code=503, detail="live chart unavailable")

    latest_snapshot = snapshots[-1]
    freshness_seconds = round((utc_now() - latest_snapshot.timestamp).total_seconds(), 1)

    return ChartPayload(
        schema_version="v1",
        chart_id=definition.chart_id,
        window=window,
        is_downsampled=downsampling_strategy is not None,
        downsampling_strategy=downsampling_strategy,
        source_health_summary=_build_source_health_summary(definition, latest_snapshot),
        metadata=ChartMetadata(
            freshness_seconds=freshness_seconds,
            status=_build_status(definition, latest_snapshot),
        ),
        ts=[snapshot.timestamp.isoformat() for snapshot in snapshots],
        series=[
            ChartSeries(
                id=series_id,
                label=label,
                unit="usd",
                data=[extractor(snapshot) for snapshot in snapshots],
            )
            for series_id, label, extractor in definition.series_defs
        ],
        overlays=[],
    )


def _downsample_snapshots(
    snapshots: list[LiveSnapshot],
    *,
    max_points: int = MAX_DOWNSAMPLED_POINTS,
) -> list[LiveSnapshot]:
    if len(snapshots) <= max_points:
        return snapshots

    last_index = len(snapshots) - 1
    target_last = max_points - 1
    sampled_indices = [
        (position * last_index) // target_last
        for position in range(max_points)
    ]
    return [snapshots[index] for index in sampled_indices]


def _maybe_downsample_snapshots(
    snapshots: list[LiveSnapshot],
    *,
    minutes: int,
    downsample: bool,
) -> tuple[list[LiveSnapshot], str | None]:
    if not downsample:
        return snapshots, None
    if minutes < LONG_WINDOW_DOWNSAMPLE_MINUTES:
        return snapshots, None
    if len(snapshots) <= MAX_DOWNSAMPLED_POINTS:
        return snapshots, None
    return _downsample_snapshots(snapshots), "uniform_stride"


def _comparison_status(mean_relative_diff_pct: float | None, overlap_points: int) -> str:
    if overlap_points == 0:
        return "no_overlap"
    assert mean_relative_diff_pct is not None
    if mean_relative_diff_pct <= 0.5:
        return "match"
    if mean_relative_diff_pct <= 2.0:
        return "minor_diff"
    return "major_diff"


def _overall_comparison_status(comparisons: list[ChartComparison]) -> str:
    statuses = [item.status for item in comparisons]
    if not statuses:
        return "no_overlap"
    if "major_diff" in statuses:
        return "major_diff"
    if "minor_diff" in statuses:
        return "minor_diff"
    if "match" in statuses:
        return "match"
    return "no_overlap"


def _build_single_comparison(
    *,
    reference_series_id: str,
    base_value: float | None,
    reference_value: float | None,
) -> ChartComparison:
    if base_value is None or reference_value is None:
        return ChartComparison(
            reference_series_id=reference_series_id,
            overlap_points=0,
            mean_abs_diff=None,
            max_abs_diff=None,
            mean_relative_diff_pct=None,
            status="no_overlap",
        )

    abs_diff = abs(base_value - reference_value)
    mean_relative_diff_pct = 0.0
    if reference_value != 0:
        mean_relative_diff_pct = round((abs_diff / abs(reference_value)) * 100.0, 6)

    mean_abs_diff = round(abs_diff, 6)
    return ChartComparison(
        reference_series_id=reference_series_id,
        overlap_points=1,
        mean_abs_diff=mean_abs_diff,
        max_abs_diff=mean_abs_diff,
        mean_relative_diff_pct=mean_relative_diff_pct,
        status=_comparison_status(mean_relative_diff_pct, 1),
    )


def _build_compare_payload(*, chart_payload: ChartPayload) -> ChartComparePayload:
    definition = CHARTS_BY_ID[chart_payload.chart_id]
    if definition.compare_base_series_id is None:
        raise HTTPException(status_code=404, detail="compare mode not supported for chart_id")
    base_series = next(series for series in chart_payload.series if series.id == definition.compare_base_series_id)
    comparisons: list[ChartComparison] = []

    for reference_series in chart_payload.series:
        if reference_series.id == base_series.id:
            continue

        diffs: list[float] = []
        relative_diffs: list[float] = []
        for base_value, reference_value in zip(base_series.data, reference_series.data, strict=False):
            if base_value is None or reference_value is None:
                continue
            abs_diff = abs(base_value - reference_value)
            diffs.append(abs_diff)
            if reference_value != 0:
                relative_diffs.append((abs_diff / abs(reference_value)) * 100.0)

        overlap_points = len(diffs)
        mean_abs_diff = round(sum(diffs) / overlap_points, 6) if overlap_points else None
        max_abs_diff = round(max(diffs), 6) if overlap_points else None
        mean_relative_diff_pct = (
            round(sum(relative_diffs) / len(relative_diffs), 6)
            if relative_diffs
            else None
        )

        comparisons.append(
            ChartComparison(
                reference_series_id=reference_series.id,
                overlap_points=overlap_points,
                mean_abs_diff=mean_abs_diff,
                max_abs_diff=max_abs_diff,
                mean_relative_diff_pct=mean_relative_diff_pct,
                status=_comparison_status(mean_relative_diff_pct, overlap_points),
            )
        )

    return ChartComparePayload(
        chart_id=chart_payload.chart_id,
        window=chart_payload.window,
        base_series_id=base_series.id,
        summary=ChartCompareSummary(
            comparison_count=len(comparisons),
            status=_overall_comparison_status(comparisons),
        ),
        comparisons=comparisons,
    )


async def _build_realized_price_reference_compare_payload(
    *,
    chart_payload: ChartPayload,
    brk_client: BrkClient,
) -> ChartComparePayload:
    base_series = next(series for series in chart_payload.series if series.id == "brk_realized_price")
    base_value = next((value for value in reversed(base_series.data) if value is not None), None)
    try:
        brk_read = await brk_client.fetch_curated_features()
    except Exception:
        brk_read = None
    reference_value = None if brk_read is None or brk_read.value is None else brk_read.value.brk_realized_price

    comparison = _build_single_comparison(
        reference_series_id="brk_api_realized_price",
        base_value=base_value,
        reference_value=reference_value,
    )
    return ChartComparePayload(
        chart_id=chart_payload.chart_id,
        window=chart_payload.window,
        base_series_id=base_series.id,
        summary=ChartCompareSummary(
            comparison_count=1,
            status=comparison.status,
        ),
        comparisons=[comparison],
    )


@router.get("/catalog", response_model=ChartCatalogResponse)
async def get_chart_catalog_endpoint() -> ChartCatalogResponse:
    return get_chart_catalog()


@router.get("/{chart_id}/latest", response_model=ChartPayload)
async def get_chart_latest(
    chart_id: str,
    store: Annotated[LiveSnapshotStore, Depends(get_live_snapshot_store)],
) -> ChartPayload:
    definition = _require_supported_chart(chart_id)
    snapshot = await _call_store(store, "get_latest")
    if snapshot is None:
        raise HTTPException(status_code=503, detail="live chart unavailable")
    return _build_chart_payload(definition=definition, snapshots=[snapshot], window="latest")


@router.get("/{chart_id}/history", response_model=ChartPayload)
async def get_chart_history(
    chart_id: str,
    store: Annotated[LiveSnapshotStore, Depends(get_live_snapshot_store)],
    minutes: Annotated[int, Query(ge=1, le=24 * 60)] = 60,
    downsample: bool = True,
) -> ChartPayload:
    definition = _require_supported_chart(chart_id)
    snapshots = list(await _call_store(store, "get_history", LiveHistoryQuery(minutes=minutes)))
    snapshots, downsampling_strategy = _maybe_downsample_snapshots(
        snapshots,
        minutes=minutes,
        downsample=downsample,
    )
    return _build_chart_payload(
        definition=definition,
        snapshots=snapshots,
        window=f"{minutes}m",
        downsampling_strategy=downsampling_strategy,
    )


@router.get("/{chart_id}/compare", response_model=ChartComparePayload)
async def get_chart_compare(
    chart_id: str,
    store: Annotated[LiveSnapshotStore, Depends(get_live_snapshot_store)],
    brk_client: Annotated[BrkClient, Depends(get_brk_client)],
    minutes: Annotated[int, Query(ge=1, le=24 * 60)] = 60,
) -> ChartComparePayload:
    definition = _require_supported_chart(chart_id)
    snapshots = await _call_store(store, "get_history", LiveHistoryQuery(minutes=minutes))
    chart_payload = _build_chart_payload(definition=definition, snapshots=list(snapshots), window=f"{minutes}m")
    if chart_id == "realized-price-reference":
        return await _build_realized_price_reference_compare_payload(
            chart_payload=chart_payload,
            brk_client=brk_client,
        )
    return _build_compare_payload(chart_payload=chart_payload)
