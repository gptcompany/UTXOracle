from __future__ import annotations

import asyncio
import csv
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

import httpx

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
            height = int(response.text.strip().replace(chr(34), ""))
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
            response = await client.get(
                f"{self.base_url}/api/metrics/bulk",
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
            if not isinstance(payload, list) or len(payload) != len(BRK_CURATED_METRICS):
                raise ValueError("unexpected BRK bulk metric payload")

            values: dict[str, float | None] = {}
            source_timestamp = None
            populated_fields = 0

            for (field_name, _metric_name), entry in zip(BRK_CURATED_METRICS, payload):
                data_points = entry.get("data") if isinstance(entry, dict) else None
                point_value = data_points[-1] if data_points else None
                values[field_name] = _coerce_float(point_value)
                if values[field_name] is not None:
                    populated_fields += 1
                if source_timestamp is None and isinstance(entry, dict):
                    source_timestamp = _extract_timestamp(entry)

            if populated_fields == 0:
                return SourceRead(
                    value=None,
                    health=SourceHealth(
                        status="unavailable",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        last_error="BRK returned no feature values",
                        details={"index": index},
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
                        "metrics": [name for name, _ in BRK_CURATED_METRICS],
                    },
                ),
                source_timestamp=source_timestamp or now,
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


class HyperliquidSnapshotClient(AsyncHttpSource):
    def __init__(
        self,
        base_url: str | None = None,
        *,
        snapshot_path: str | None = None,
        data_root: str | Path | None = None,
        symbol: str = "BTC",
        timeout_seconds: float = DEFAULT_SOURCE_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url or os.getenv("HYPERLIQUID_NODE_API_URL", "http://127.0.0.1:12345"),
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
                "HYPERLIQUID_DATA_ROOT", "/media/sam/1TB/hyperliquid-realtime-data"
            )
        )
        self.symbol = symbol.upper()

    async def fetch_snapshot(self) -> SourceRead[HyperliquidPriceSnapshot]:
        api_read = await self._fetch_from_node_api()
        if api_read.value is not None:
            return api_read

        file_read = await asyncio.to_thread(self._read_from_filesystem)
        if file_read.value is not None:
            fallback_health = file_read.health.model_copy(
                update={
                    "status": "degraded",
                    "details": {
                        **file_read.health.details,
                        "fallback_reason": api_read.health.last_error or "node API unavailable",
                    },
                }
            )
            return SourceRead(
                value=file_read.value,
                health=fallback_health,
                source_timestamp=file_read.source_timestamp,
            )

        return api_read

    async def _fetch_from_node_api(self) -> SourceRead[HyperliquidPriceSnapshot]:
        started = time.perf_counter()
        try:
            client = await self._get_client()
            target_url = self.base_url
            if self.snapshot_path:
                target_url = self.base_url + "/" + self.snapshot_path.removeprefix("/")
            response = await client.get(target_url, headers={"Accept": "application/json"})
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type.lower():
                raise ValueError(f"unexpected content-type: {content_type or 'missing'}")
            payload = response.json()
            snapshot = self._parse_node_payload(payload)
            if snapshot is None:
                raise ValueError("Hyperliquid node payload missing oracle/mark price fields")
            now = utc_now()
            return SourceRead(
                value=snapshot,
                health=SourceHealth(
                    status="healthy",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    last_success=now,
                ),
                source_timestamp=snapshot.timestamp,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return SourceRead(
                value=None,
                health=SourceHealth(
                    status="unavailable",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    last_error=str(exc),
                    details={
                        "base_url": self.base_url,
                        "snapshot_path": self.snapshot_path,
                    },
                ),
            )

    def _parse_node_payload(self, payload: Any) -> HyperliquidPriceSnapshot | None:
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
                    health=SourceHealth(
                        status="healthy",
                        last_success=utc_now(),
                        details={"backend": "sqlite", "path": str(db_files[0])},
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
                    health=SourceHealth(
                        status="healthy",
                        last_success=utc_now(),
                        details={"backend": "csv", "path": str(candidate_dir)},
                    ),
                    source_timestamp=snapshot.timestamp,
                )

        return SourceRead(
            value=None,
            health=SourceHealth(
                status="unavailable",
                last_error=(
                    f"no Hyperliquid fallback data found under {self.data_root} for symbol {self.symbol}"
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
    timestamp_keys = ("timestamp", "time", "ts", "updated_at", "updatedAt", "stamp")
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
