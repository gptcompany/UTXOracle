"""GET /v1/streams/health - consumer-facing freshness endpoint (spec-061).

Wire shape: contracts/streams_health.openapi.yaml.
Registry SSOT: docs/contracts/stream_registry.yaml.

The endpoint loads the registry once at import time, validates it against
its JSON Schema (fail-fast), and on each request issues 13 parallel
freshness probes - one per stream - dispatched by `freshness_strategy`:

- `max_ts`         -> `now() - max(timestamp_column)`
- `tip_lag_blocks` -> `(getblockcount() - max(block_column)) * 600`

There is no in-process cache for stream readings: research.md R1 +
spec FR-011 require the response to reflect reality, including recovery
from STALE -> OK without a TTL gate. The Bitcoin Core tip IS cached for
60s to bound RPC load (research.md R1 + R2).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from fastapi import APIRouter, Depends
from jsonschema import Draft7Validator

from api.auth_middleware import require_auth
from api.models.streams import (
    OverallStatus,
    StreamHealthReading,
    StreamsHealthResponse,
    StreamStatus,
)
from api.questdb_repository import (
    read_stream_max_ts,
    read_stream_tip_lag_seconds,
)

logger = logging.getLogger(__name__)

# Paths

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_REGISTRY_PATH = _REPO_ROOT / "docs" / "contracts" / "stream_registry.yaml"
_REGISTRY_SCHEMA_PATH = (
    _REPO_ROOT
    / "specs"
    / "061-stream-consumption-contract"
    / "contracts"
    / "stream_registry.schema.yaml"
)


# Registry loader (T014)


def _load_registry() -> List[Dict[str, Any]]:
    """Load + validate stream_registry.yaml. Raises on schema violation.

    Called once at module import - module state holds the parsed list.
    Fail-fast: if the YAML drifts from the schema, the API refuses to
    start instead of serving a malformed contract.
    """
    raw = yaml.safe_load(_REGISTRY_PATH.read_text())
    schema = yaml.safe_load(_REGISTRY_SCHEMA_PATH.read_text())
    errors = sorted(
        Draft7Validator(schema).iter_errors(raw),
        key=lambda e: list(e.absolute_path),
    )
    if errors:
        detail = "; ".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)
        raise RuntimeError(f"stream_registry.yaml fails schema validation: {detail}")
    return raw["streams"]


_REGISTRY: List[Dict[str, Any]] = _load_registry()


# Bitcoin Core tip getter (T011a)

_TIP_CACHE: Dict[str, Tuple[float, int]] = {}
_TIP_CACHE_TTL_SECONDS = 60


async def get_current_tip() -> int:
    """Return the current Bitcoin Core block height.

    Cached in module state for `_TIP_CACHE_TTL_SECONDS` to bound RPC load
    across many concurrent polls. Runs the synchronous `BitcoinRPC` client
    in a thread to avoid blocking the event loop. Raises on RPC failure;
    the caller maps that to status `MISSING` on tip_lag_blocks streams.
    """
    now = time.monotonic()
    cached = _TIP_CACHE.get("tip")
    if cached is not None and now - cached[0] < _TIP_CACHE_TTL_SECONDS:
        return cached[1]

    # Import lazily so test collection does not require a configured
    # Bitcoin Core endpoint.
    from scripts.sync_utxo_lifecycle import BitcoinRPC

    tip = await asyncio.to_thread(lambda: BitcoinRPC().getblockcount())
    _TIP_CACHE["tip"] = (now, int(tip))
    return int(tip)


# Per-stream probe


async def _probe_stream(
    entry: Dict[str, Any], current_tip: Optional[int], tip_error: Optional[str]
) -> StreamHealthReading:
    """Compute one stream's reading per its freshness_strategy.

    `current_tip` is the cached Bitcoin Core height; `tip_error` is the
    exception class name if the tip lookup failed. The two arguments are
    threaded through together so we make the RPC call exactly once per
    request.
    """
    name = entry["name"]
    table = entry["table"]
    sla = int(entry["sla_seconds"])
    schema_version = entry["schema_version"]
    strategy = entry["freshness_strategy"]

    last_row_ts: Optional[datetime] = None
    stale_seconds: Optional[int] = None
    error: Optional[str] = None

    try:
        if strategy == "max_ts":
            ts = await read_stream_max_ts(table, entry["timestamp_column"])
            if ts is None:
                status = StreamStatus.MISSING
            else:
                # asyncpg may return a naive UTC datetime; normalize.
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                last_row_ts = ts
                stale_seconds = max(
                    0,
                    int((datetime.now(timezone.utc) - ts).total_seconds()),
                )
                status = StreamStatus.OK if stale_seconds <= sla else StreamStatus.STALE
        elif strategy == "tip_lag_blocks":
            if tip_error is not None:
                status = StreamStatus.MISSING
                error = tip_error
            else:
                assert current_tip is not None  # guarded by tip_error
                block_columns = entry.get("block_columns") or [entry["block_column"]]
                lags = await asyncio.gather(
                    *(
                        read_stream_tip_lag_seconds(table, block_column, current_tip)
                        for block_column in block_columns
                    )
                )
                if any(lag is None for lag in lags):
                    status = StreamStatus.MISSING
                else:
                    stale_seconds = max(
                        0, *(int(lag) for lag in lags if lag is not None)
                    )
                    status = (
                        StreamStatus.OK if stale_seconds <= sla else StreamStatus.STALE
                    )
        else:
            # Schema validation should have rejected this; defensive.
            status = StreamStatus.MISSING
            error = f"unknown freshness_strategy: {strategy!r}"
    except Exception as exc:
        status = StreamStatus.MISSING
        error = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__

    return StreamHealthReading(
        name=name,
        last_row_ts=last_row_ts,
        stale_seconds=stale_seconds,
        sla_seconds=sla,
        schema_version=schema_version,
        status=status,
        error=error,
    )


# Route (T013)

router = APIRouter(prefix="/v1/streams", tags=["streams"])


@router.get(
    "/health",
    response_model=StreamsHealthResponse,
    summary="Freshness state of the 13 contractual onchain streams.",
)
async def streams_health(
    _auth: Any = Depends(require_auth),
) -> StreamsHealthResponse:
    """Poll the 13 streams in parallel and roll up the per-stream verdicts.

    Authentication is required (FR-004). The response shape is identical
    regardless of how many streams are STALE/MISSING - the consumer
    branches on `overall`, not on per-stream details.
    """
    as_of = datetime.now(timezone.utc)

    # Resolve the Bitcoin Core tip once per request. Only matters for
    # streams with freshness_strategy = tip_lag_blocks.
    needs_tip = any(e["freshness_strategy"] == "tip_lag_blocks" for e in _REGISTRY)
    current_tip: Optional[int] = None
    tip_error: Optional[str] = None
    if needs_tip:
        try:
            current_tip = await get_current_tip()
        except Exception as exc:
            tip_error = (
                f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            )

    readings = await asyncio.gather(
        *(_probe_stream(entry, current_tip, tip_error) for entry in _REGISTRY)
    )

    overall = (
        OverallStatus.OK
        if all(r.status == StreamStatus.OK.value for r in readings)
        else OverallStatus.DEGRADED
    )

    n_stale = sum(1 for r in readings if r.status == StreamStatus.STALE.value)
    n_missing = sum(1 for r in readings if r.status == StreamStatus.MISSING.value)
    logger.info(
        "streams_health.poll",
        extra={"overall": overall.value, "n_stale": n_stale, "n_missing": n_missing},
    )

    return StreamsHealthResponse(as_of=as_of, streams=readings, overall=overall)
