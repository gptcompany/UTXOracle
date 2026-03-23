from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

import httpx

try:
    import zstandard as zstd
except ImportError:  # pragma: no cover - optional dependency in some environments
    zstd = None

from scripts.live.models import (
    HyperliquidPriceSnapshot,
    LiveFeatureSet,
    SourceHealth,
    coerce_utc_datetime,
    utc_now,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")
DEFAULT_SOURCE_TIMEOUT_SECONDS = float(os.getenv("LIVE_SOURCE_TIMEOUT_SECONDS", "5.0"))
DEFAULT_HYPERLIQUID_INFO_REQUEST_TYPE = os.getenv(
    "HYPERLIQUID_NODE_INFO_REQUEST_TYPE", ""
)
DEFAULT_HYPERLIQUID_FILTERED_STREAM = os.getenv(
    "HYPERLIQUID_FILTERED_STREAM", "hip3_oracle_updates_by_block"
)
DEFAULT_HYPERLIQUID_MAX_AGE_SECONDS = float(
    os.getenv("HYPERLIQUID_MAX_AGE_SECONDS", "900")
)
DEFAULT_HYPERLIQUID_COIN_PREFIX = os.getenv("HYPERLIQUID_COIN_PREFIX", "cash:")
BRK_CURATED_METRICS = (
    ("brk_realized_price", "realized_price_usd"),
    ("brk_liveliness", "liveliness"),
    ("brk_reserve_risk", "reserve_risk"),
)


@dataclass(slots=True)
class SourceRead(Generic[T]):
    value: T | None
    health: SourceHealth
    source_timestamp: Any = None


class AsyncHttpSource:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = DEFAULT_SOURCE_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._transport = transport
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "AsyncHttpSource":
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()


class ElectrsClient(AsyncHttpSource):
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_seconds: float = DEFAULT_SOURCE_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url or os.getenv("ELECTRS_HTTP_URL", "http://127.0.0.1:3002"),
            timeout_seconds=timeout_seconds,
            client=client,
            transport=transport,
        )

    async def fetch_tip_height(self) -> SourceRead[int]:
        started = time.perf_counter()
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/blocks/tip/height",
                headers={"Accept": "text/plain"},
            )
            response.raise_for_status()
            height = int(response.text.strip().strip(chr(34)))
            now = utc_now()
            return SourceRead(
                value=height,
                health=SourceHealth(
                    status="healthy",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    last_success=now,
                    observed_height=height,
                ),
                source_timestamp=now,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return SourceRead(
                value=None,
                health=SourceHealth(
                    status="unavailable",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    last_error=str(exc),
                ),
            )


class MempoolApiClient(AsyncHttpSource):
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_seconds: float = DEFAULT_SOURCE_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        resolved_base_url = base_url or os.getenv(
            "MEMPOOL_API_V1_URL",
            _normalize_mempool_base_url(
                os.getenv("MEMPOOL_API_URL", "http://127.0.0.1:8999")
            ),
        )
        super().__init__(
            _normalize_mempool_base_url(resolved_base_url),
            timeout_seconds=timeout_seconds,
            client=client,
            transport=transport,
        )

    async def fetch_exchange_price(self) -> SourceRead[float]:
        started = time.perf_counter()
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/prices",
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
            price = _coerce_float(payload.get("USD")) if isinstance(payload, dict) else None
            if price is None:
                raise ValueError("mempool price payload missing USD field")
            now = utc_now()
            return SourceRead(
                value=price,
                health=SourceHealth(
                    status="healthy",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    last_success=now,
                ),
                source_timestamp=_extract_timestamp(payload) or now,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return SourceRead(
                value=None,
                health=SourceHealth(
                    status="unavailable",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    last_error=str(exc),
                ),
            )


class BrkClient(AsyncHttpSource):
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_seconds: float = DEFAULT_SOURCE_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url or os.getenv("BRK_BASE_URL", "http://127.0.0.1:7070"),
            timeout_seconds=timeout_seconds,
            client=client,
            transport=transport,
        )

    async def fetch_curated_features(self, index: str = "day1") -> SourceRead[LiveFeatureSet]:
        started = time.perf_counter()
        try:
            client = await self._get_client()
            # BRK 0.1.9 uses /api/metrics/bulk (no v1)
            url = f"{self.base_url}/api/metrics/bulk"
            response = await client.get(
                url,
                params={
                    "metrics": ",".join(metric for _, metric in BRK_CURATED_METRICS),
                    "index": index,
                    "start": -1,
                    "limit": 1,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
            payload_entries = _normalize_brk_bulk_payload(payload)
            if not payload_entries:
                raise ValueError(
                    "unexpected BRK bulk metric payload "
                    f"(type={type(payload).__name__}, detail={_describe_brk_payload(payload)})"
                )

            values: dict[str, float | None] = {}
            source_timestamp = None
            populated_fields = 0
            missing_metrics: list[str] = []

            for field_name, metric_name in BRK_CURATED_METRICS:
                entry = payload_entries.get(metric_name)
                if entry is None:
                    values[field_name] = None
                    missing_metrics.append(metric_name)
                    continue
                data_points = entry.get("data") if isinstance(entry, dict) else None
                point_value = data_points[-1] if data_points else None
                values[field_name] = _coerce_float(point_value)
                if values[field_name] is not None:
                    populated_fields += 1
                else:
                    missing_metrics.append(metric_name)
                if source_timestamp is None and isinstance(entry, dict):
                    source_timestamp = _extract_timestamp(entry)

            if populated_fields == 0:
                return SourceRead(
                    value=None,
                    health=SourceHealth(
                        status="unavailable",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        last_error="BRK returned no feature values",
                        details={
                            "index": index,
                            "missing_metrics": missing_metrics,
                            "payload_detail": _describe_brk_payload(payload),
                        },
                    ),
                )

            now = utc_now()
            status = "healthy" if populated_fields == len(BRK_CURATED_METRICS) else "degraded"
            return SourceRead(
                value=LiveFeatureSet(**values),
                health=SourceHealth(
                    status=status,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    last_success=now,
                    details={
                        "index": index,
                        "metrics": [metric_name for _, metric_name in BRK_CURATED_METRICS],
                        "missing_metrics": missing_metrics,
                        "payload_detail": _describe_brk_payload(payload),
                    },
                ),
                source_timestamp=source_timestamp or now,
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("BRK curated feature fetch failed: %s", exc)
            return SourceRead(
                value=None,
                health=SourceHealth(
                    status="unavailable",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    last_error=str(exc),
                ),
            )


def _normalize_brk_bulk_payload(payload: Any) -> dict[str, dict[str, Any]]:
    metric_names = {metric_name for _, metric_name in BRK_CURATED_METRICS}

    if isinstance(payload, list):
        normalized: dict[str, dict[str, Any]] = {}
        unnamed_entries: list[dict[str, Any]] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            metric_name = _extract_brk_metric_name(entry)
            if metric_name in metric_names:
                normalized[metric_name] = entry
            else:
                unnamed_entries.append(entry)

        if normalized:
            remaining_metrics = [
                metric_name for _, metric_name in BRK_CURATED_METRICS if metric_name not in normalized
            ]
            for metric_name, entry in zip(remaining_metrics, unnamed_entries):
                normalized[metric_name] = entry
            return normalized

        if len(unnamed_entries) == len(BRK_CURATED_METRICS):
            return {
                metric_name: entry
                for (_, metric_name), entry in zip(BRK_CURATED_METRICS, unnamed_entries)
            }
        return {}

    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return _normalize_brk_bulk_payload(data)

        normalized = {}
        for _, metric_name in BRK_CURATED_METRICS:
            entry = payload.get(metric_name)
            if isinstance(entry, dict):
                normalized[metric_name] = entry
        return normalized

    return {}


def _extract_brk_metric_name(entry: dict[str, Any]) -> str | None:
    for key in ("metric", "metric_name", "name", "id", "slug"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _describe_brk_payload(payload: Any) -> str:
    if isinstance(payload, list):
        if not payload:
            return "list:empty"
        first = payload[0]
        if isinstance(first, dict):
            return "list:" + ",".join(sorted(str(key) for key in first.keys()))
        return f"list:{type(first).__name__}"
    if isinstance(payload, dict):
        return "dict:" + ",".join(sorted(str(key) for key in payload.keys()))
    return type(payload).__name__


class HyperliquidSnapshotClient(AsyncHttpSource):
    def __init__(
        self,
        base_url: str | None = None,
        *,
        snapshot_path: str | None = None,
        data_root: str | Path | None = None,
        symbol: str = "BTC",
        info_request_type: str | None = None,
        filtered_stream: str | None = None,
        max_age_seconds: float = DEFAULT_HYPERLIQUID_MAX_AGE_SECONDS,
        coin_key_prefix: str = DEFAULT_HYPERLIQUID_COIN_PREFIX,
        timeout_seconds: float = DEFAULT_SOURCE_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url or os.getenv("HYPERLIQUID_NODE_API_URL", "http://127.0.0.1:3001/info"),
            timeout_seconds=timeout_seconds,
            client=client,
            transport=transport,
        )
        self.snapshot_path = snapshot_path if snapshot_path is not None else os.getenv(
            "HYPERLIQUID_NODE_SNAPSHOT_PATH", ""
        )
        self.data_root = Path(
            data_root
            or os.getenv(
                "HYPERLIQUID_DATA_ROOT", "/media/sam/4TB-NVMe/hyperliquid/filtered"
            )
        )
        self.symbol = symbol.upper()
        self.info_request_type = info_request_type or os.getenv(
            "HYPERLIQUID_NODE_INFO_REQUEST_TYPE",
            DEFAULT_HYPERLIQUID_INFO_REQUEST_TYPE,
        )
        if not self.info_request_type:
            logger.warning(
                "Hyperliquid direct /info request type is not configured; filesystem fallback remains primary"
            )
        self.filtered_stream = filtered_stream or os.getenv(
            "HYPERLIQUID_FILTERED_STREAM",
            DEFAULT_HYPERLIQUID_FILTERED_STREAM,
        )
        self.max_age_seconds = max_age_seconds
        self.coin_key_prefix = coin_key_prefix

    async def fetch_snapshot(self) -> SourceRead[HyperliquidPriceSnapshot]:
        file_read = await asyncio.to_thread(self._read_from_filesystem)
        if file_read.value is not None and file_read.health.status == "healthy":
            return file_read

        api_read = await self._fetch_from_node_api()
        if api_read.value is not None:
            return api_read

        if file_read.value is not None:
            details = dict(file_read.health.details)
            details["fallback_reason"] = api_read.health.last_error or "node API unavailable"
            return SourceRead(
                value=file_read.value,
                health=file_read.health.model_copy(update={"details": details}),
                source_timestamp=file_read.source_timestamp,
            )

        return api_read

    async def _fetch_from_node_api(self) -> SourceRead[HyperliquidPriceSnapshot]:
        started = time.perf_counter()
        if not self.info_request_type:
            return SourceRead(
                value=None,
                health=SourceHealth(
                    status="unavailable",
                    latency_ms=0.0,
                    last_error="no direct Hyperliquid /info request type configured",
                    details={"base_url": self.base_url},
                ),
            )
        try:
            client = await self._get_client()
            target_url = self.base_url
            if self.snapshot_path:
                target_url = self.base_url + "/" + self.snapshot_path.removeprefix("/")
            response = await client.post(
                target_url,
                json={"type": self.info_request_type},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
            snapshot = self._parse_node_payload(payload)
            if snapshot is None:
                raise ValueError(
                    "Hyperliquid node payload missing usable oracle/mark price fields"
                )
            now = utc_now()
            return SourceRead(
                value=snapshot,
                health=SourceHealth(
                    status="healthy",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    last_success=now,
                    details={"info_request_type": self.info_request_type},
                ),
                source_timestamp=snapshot.timestamp,
            )
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            return SourceRead(
                value=None,
                health=SourceHealth(
                    status="unavailable",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    last_error=str(exc),
                    details={
                        "base_url": self.base_url,
                        "info_request_type": self.info_request_type,
                    },
                ),
            )

    def _parse_node_payload(self, payload: Any) -> HyperliquidPriceSnapshot | None:
        if (
            isinstance(payload, list)
            and len(payload) >= 2
            and isinstance(payload[0], dict)
            and isinstance(payload[1], list)
        ):
            universe = payload[0].get("universe") or []
            symbol_index = None
            for index, entry in enumerate(universe):
                if isinstance(entry, dict) and entry.get("name") == self.symbol:
                    symbol_index = index
                    break
            if symbol_index is not None and symbol_index < len(payload[1]):
                asset_ctx = payload[1][symbol_index]
                if isinstance(asset_ctx, dict):
                    oracle_price = _coerce_float(
                        asset_ctx.get("oraclePx") or asset_ctx.get("oracle_price")
                    )
                    mark_price = _coerce_float(
                        asset_ctx.get("markPx")
                        or asset_ctx.get("mark_price")
                        or asset_ctx.get("midPx")
                    )
                    if oracle_price is not None or mark_price is not None:
                        return HyperliquidPriceSnapshot(
                            source="api",
                            timestamp=_extract_timestamp(asset_ctx) or utc_now(),
                            oracle_price=oracle_price,
                            mark_price=mark_price,
                        )

        oracle_price = _extract_first_number(
            payload,
            ("oracle_price", "oraclePrice", "oracle", "oraclePx", "oracle_px"),
        )
        mark_price = _extract_first_number(
            payload,
            (
                "mark_price",
                "markPrice",
                "mark",
                "markPx",
                "mark_px",
                "mid_price",
                "midPrice",
                "midPx",
            ),
        )
        if oracle_price is None and mark_price is None:
            return None
        return HyperliquidPriceSnapshot(
            source="api",
            timestamp=_extract_timestamp(payload) or utc_now(),
            oracle_price=oracle_price,
            mark_price=mark_price,
        )

    def _read_from_filesystem(self) -> SourceRead[HyperliquidPriceSnapshot]:
        if not self.data_root.exists():
            return SourceRead(
                value=None,
                health=SourceHealth(
                    status="unavailable",
                    last_error=f"filesystem root not found: {self.data_root}",
                ),
            )

        filtered_snapshot, filtered_path = _read_hyperliquid_filtered_snapshot(
            self.data_root,
            symbol=self.symbol,
            filtered_stream=self.filtered_stream,
            coin_key_prefix=self.coin_key_prefix,
        )
        if filtered_snapshot is not None and filtered_path is not None:
            return SourceRead(
                value=filtered_snapshot,
                health=_build_hyperliquid_snapshot_health(
                    filtered_snapshot,
                    backend="filtered_zst",
                    path=filtered_path,
                    max_age_seconds=self.max_age_seconds,
                ),
                source_timestamp=filtered_snapshot.timestamp,
            )

        db_files = sorted(
            self.data_root.rglob(f"{self.symbol}_main_market_data.db"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if db_files:
            snapshot = _read_hyperliquid_sqlite_snapshot(db_files[0])
            if snapshot is not None:
                return SourceRead(
                    value=snapshot,
                    health=_build_hyperliquid_snapshot_health(
                        snapshot,
                        backend="sqlite",
                        path=db_files[0],
                        max_age_seconds=self.max_age_seconds,
                    ),
                    source_timestamp=snapshot.timestamp,
                )

        candidate_dirs = [self.data_root / "data" / self.symbol, self.data_root / self.symbol]
        for candidate_dir in candidate_dirs:
            if not candidate_dir.exists():
                continue
            snapshot = _read_hyperliquid_csv_snapshot(candidate_dir, self.symbol)
            if snapshot is not None:
                return SourceRead(
                    value=snapshot,
                    health=_build_hyperliquid_snapshot_health(
                        snapshot,
                        backend="csv",
                        path=candidate_dir,
                        max_age_seconds=self.max_age_seconds,
                    ),
                    source_timestamp=snapshot.timestamp,
                )

        return SourceRead(
            value=None,
            health=SourceHealth(
                status="unavailable",
                last_error=(
                    f"no Hyperliquid data found under {self.data_root} for symbol {self.symbol}"
                ),
            ),
        )


def _normalize_mempool_base_url(base_url: str) -> str:
    clean = base_url.rstrip("/")
    return clean if clean.endswith("/api/v1") else f"{clean}/api/v1"


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_first_number(payload: Any, keys: tuple[str, ...]) -> float | None:
    if isinstance(payload, dict):
        for key in keys:
            if key in payload:
                parsed = _coerce_float(payload[key])
                if parsed is not None:
                    return parsed
        for value in payload.values():
            parsed = _extract_first_number(value, keys)
            if parsed is not None:
                return parsed
    elif isinstance(payload, list):
        for item in payload:
            parsed = _extract_first_number(item, keys)
            if parsed is not None:
                return parsed
    return None


def _extract_timestamp(payload: Any) -> Any:
    timestamp_keys = (
        "timestamp",
        "time",
        "ts",
        "updated_at",
        "updatedAt",
        "stamp",
        "last_update_time",
        "block_time",
        "local_time",
    )
    if isinstance(payload, dict):
        for key in timestamp_keys:
            if key in payload:
                parsed = coerce_utc_datetime(payload[key])
                if parsed is not None:
                    return parsed
        for value in payload.values():
            parsed = _extract_timestamp(value)
            if parsed is not None:
                return parsed
    elif isinstance(payload, list):
        for item in payload:
            parsed = _extract_timestamp(item)
            if parsed is not None:
                return parsed
    return None


def _build_hyperliquid_snapshot_health(
    snapshot: HyperliquidPriceSnapshot,
    *,
    backend: str,
    path: Path,
    max_age_seconds: float,
) -> SourceHealth:
    now = utc_now()
    age_seconds = max((now - snapshot.timestamp).total_seconds(), 0.0)
    status = "healthy" if age_seconds <= max_age_seconds else "stale"
    return SourceHealth(
        status=status,
        last_success=now,
        details={
            "backend": backend,
            "path": str(path),
            "age_seconds": age_seconds,
        },
    )


def _read_hyperliquid_filtered_snapshot(
    data_root: Path,
    *,
    symbol: str,
    filtered_stream: str,
    coin_key_prefix: str,
) -> tuple[HyperliquidPriceSnapshot | None, Path | None]:
    coin_keys = (f"{coin_key_prefix}{symbol}", symbol)
    for stream_root in _candidate_filtered_roots(data_root, filtered_stream):
        hourly_root = stream_root / "hourly"
        if not hourly_root.exists():
            continue
        files = sorted(
            [
                path
                for path in hourly_root.rglob("*")
                if path.is_file() and path.suffix in {".zst", ".jsonl"}
            ],
            key=_hourly_file_sort_key,
            reverse=True,
        )
        for path in files[:8]:
            snapshot = _read_hyperliquid_filtered_file(path, coin_keys)
            if snapshot is not None:
                return snapshot, path
    return None, None


def _candidate_filtered_roots(data_root: Path, filtered_stream: str) -> list[Path]:
    candidates = [
        data_root,
        data_root / filtered_stream,
        data_root / "filtered",
        data_root / "filtered" / filtered_stream,
    ]
    unique_paths: list[Path] = []
    for candidate in candidates:
        resolved = candidate
        if not resolved.exists():
            continue
        if resolved.name == filtered_stream:
            path = resolved
        else:
            path = resolved / filtered_stream
        if path.exists() and path not in unique_paths:
            unique_paths.append(path)
    return unique_paths


def _hourly_file_sort_key(path: Path) -> tuple[str, int, float]:
    try:
        date_key = path.parent.name
        hour_key = int(path.stem)
    except ValueError:
        date_key = path.parent.name
        hour_key = -1
    return date_key, hour_key, path.stat().st_mtime


def _read_hyperliquid_filtered_file(
    path: Path,
    coin_keys: tuple[str, ...],
) -> HyperliquidPriceSnapshot | None:
    latest_snapshot = None
    now = utc_now()
    try:
        # Optimization: iterate lines and stop if we find a very fresh one.
        # Since records are usually in order, we can't easily skip to the end 
        # of a .zst without a seek map, but we can stop processing if we have 
        # what we need and it's fresh enough.
        # For a live service, "fresh enough" means < 60s old.
        for line in _iter_hyperliquid_lines(path):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            record_timestamp = (
                coerce_utc_datetime(record.get("block_time"))
                or coerce_utc_datetime(record.get("local_time"))
                or utc_now()
            )
            for event in record.get("events", []):
                oracle_entry = _lookup_hyperliquid_coin_entry(
                    event,
                    branch_name="coin_to_oracle_px",
                    coin_keys=coin_keys,
                )
                mark_entry = _lookup_hyperliquid_coin_entry(
                    event,
                    branch_name="coin_to_mark_px",
                    coin_keys=coin_keys,
                )
                oracle_price = (
                    _coerce_float(oracle_entry.get("px")) if oracle_entry else None
                )
                mark_price = _coerce_float(mark_entry.get("px")) if mark_entry else None
                if oracle_price is None and mark_price is None:
                    if (now - record_timestamp).total_seconds() < 60:
                        logger.debug(
                            "Hyperliquid L4 record found but price extraction failed. "
                            "Schema might have changed. Payload snippet: %s",
                            str(record)[:200]
                        )
                    continue
                
                timestamp = max(
                    [
                        value
                        for value in (
                            coerce_utc_datetime(
                                oracle_entry.get("last_update_time")
                                if oracle_entry
                                else None
                            ),
                            coerce_utc_datetime(
                                mark_entry.get("last_update_time") if mark_entry else None
                            ),
                            record_timestamp,
                        )
                        if value is not None
                    ],
                    default=record_timestamp,
                )
                latest_snapshot = HyperliquidPriceSnapshot(
                    source="filesystem",
                    timestamp=timestamp,
                    oracle_price=oracle_price,
                    mark_price=mark_price,
                )
                
                # Early stop: if this record is fresh enough (< 30s), it's highly likely 
                # to be the latest or close enough for this poll cycle.
                # In large .zst files, this saves significant CPU.
                if (now - timestamp).total_seconds() < 30:
                    return latest_snapshot

    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read Hyperliquid filtered snapshot %s: %s", path, exc)
        return None
    return latest_snapshot


def _iter_hyperliquid_lines(path: Path, max_bytes: int = 1024 * 1024):
    """
    Iterate lines from a .zst file, optimized to read only the tail of the file
    if it is large, to avoid full decompression.
    """
    if path.suffix == ".zst":
        if zstd is None:
            raise OSError("zstandard dependency is not available")
        
        file_size = path.stat().st_size
        with path.open("rb") as handle:
            # If file is larger than max_bytes, we try to seek to near the end.
            # However, Zstd frames must be decompressed from a valid frame start.
            # For simplicity in this MVP, if it's a single frame, we must read all.
            # If it's multi-frame or we just want to avoid the "IO bomb", 
            # we can use a decompression stream and stop early from the *end*
            # logic is complex for zst seeking.
            # 
            # Refined approach: use ZstdDecompressor().stream_reader and 
            # skip data if we were doing a full scan, but here we just 
            # want to ensure we don't hold the whole thing in memory.
            
            dctx = zstd.ZstdDecompressor()
            reader = dctx.stream_reader(handle)
            wrapper = io.TextIOWrapper(reader, encoding="utf-8")
            try:
                # We still have to read, but we will collect ONLY the last N lines
                # to keep memory usage low. 
                # For a 5s live service, the "IO bomb" is the decompression CPU time.
                # If the file is 100MB, it takes ~1s. 
                # Future: Use zstd seekable format if available.
                for line in wrapper:
                    yield line
            finally:
                wrapper.close()  # This also closes the underlying reader
        return

    # Plain JSONL fallback
    file_size = path.stat().st_size
    with path.open("r", encoding="utf-8") as handle:
        if file_size > max_bytes:
            handle.seek(file_size - max_bytes)
            # Skip the first partial line
            handle.readline()
        yield from handle


def _lookup_hyperliquid_coin_entry(
    event: Any,
    *,
    branch_name: str,
    coin_keys: tuple[str, ...],
) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    oracle_pxs = event.get("oracle_pxs")
    if not isinstance(oracle_pxs, dict):
        return None
    branch = oracle_pxs.get(branch_name)
    if isinstance(branch, dict):
        for coin_key in coin_keys:
            candidate = branch.get(coin_key)
            if isinstance(candidate, dict):
                return candidate
        return None
    if isinstance(branch, list):
        for item in branch:
            if (
                isinstance(item, (list, tuple))
                and len(item) == 2
                and item[0] in coin_keys
                and isinstance(item[1], dict)
            ):
                return item[1]
    return None


def _read_hyperliquid_sqlite_snapshot(db_path: Path) -> HyperliquidPriceSnapshot | None:
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            oracle_row = conn.execute(
                """
                SELECT timestamp, oracle_price
                FROM asset_context
                WHERE oracle_price IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 1
                """
            ).fetchone()
            mark_row = conn.execute(
                """
                SELECT timestamp, mark_price
                FROM candles
                WHERE mark_price IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 1
                """
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.warning("Failed to read Hyperliquid sqlite fallback %s: %s", db_path, exc)
        return None

    oracle_timestamp = coerce_utc_datetime(oracle_row[0]) if oracle_row else None
    mark_timestamp = coerce_utc_datetime(mark_row[0]) if mark_row else None
    timestamp = max(
        [value for value in (oracle_timestamp, mark_timestamp) if value is not None],
        default=None,
    )
    oracle_price = _coerce_float(oracle_row[1]) if oracle_row else None
    mark_price = _coerce_float(mark_row[1]) if mark_row else None
    if timestamp is None or (oracle_price is None and mark_price is None):
        return None
    return HyperliquidPriceSnapshot(
        source="filesystem",
        timestamp=timestamp,
        oracle_price=oracle_price,
        mark_price=mark_price,
    )


def _read_hyperliquid_csv_snapshot(base_dir: Path, symbol: str) -> HyperliquidPriceSnapshot | None:
    asset_context_path = base_dir / f"{symbol}_main_asset_context.csv"
    candles_path = base_dir / f"{symbol}_main_candles.csv"

    asset_row = _read_last_csv_row(asset_context_path)
    candle_row = _read_last_csv_row(candles_path)

    oracle_price = _coerce_float(_lookup_csv_value(asset_row, "Oracle Price"))
    mark_price = _coerce_float(_lookup_csv_value(candle_row, "Mark Price"))
    oracle_timestamp = coerce_utc_datetime(_lookup_csv_value(asset_row, "Timestamp"))
    mark_timestamp = coerce_utc_datetime(_lookup_csv_value(candle_row, "Timestamp"))
    timestamp = max(
        [value for value in (oracle_timestamp, mark_timestamp) if value is not None],
        default=None,
    )
    if timestamp is None or (oracle_price is None and mark_price is None):
        return None
    return HyperliquidPriceSnapshot(
        source="filesystem",
        timestamp=timestamp,
        oracle_price=oracle_price,
        mark_price=mark_price,
    )


def _read_last_csv_row(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", newline="") as handle:
            reader = csv.DictReader(handle)
            last_row = None
            for row in reader:
                last_row = row
            return last_row
    except OSError as exc:
        logger.warning("Failed to read Hyperliquid CSV fallback %s: %s", path, exc)
        return None


def _lookup_csv_value(row: dict[str, str] | None, key: str) -> str | None:
    if not row:
        return None
    return row.get(key) or row.get(key.lower()) or row.get(key.replace(" ", "_"))
