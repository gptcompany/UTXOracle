"""Unit tests for GET /v1/streams/health (spec-061 US1).

Tests T005-T009 (max_ts strategy) + T011b (tip_lag_blocks strategy).
All tests fully mock the QuestDB repository — no live infrastructure
required. These run RED until api.routes.streams + api.models.streams
exist; that's the expected TDD cycle.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# These imports will fail RED until T011/T012/T013 land:
from api.routes.streams import router as streams_router  # noqa: E402
from api.models.streams import StreamStatus, OverallStatus  # noqa: E402


pytestmark = pytest.mark.asyncio


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def app() -> FastAPI:
    """Minimal FastAPI app wiring only the streams router.

    Auth dependency is overridden to a no-op so the tests focus on the
    route's freshness logic. Auth-specific behaviour is asserted by
    test_auth_required against an app WITHOUT the override.
    """
    from api.auth_middleware import require_auth

    app = FastAPI()
    app.include_router(streams_router)

    async def _noop_auth():
        return None

    app.dependency_overrides[require_auth] = _noop_auth
    return app


@pytest.fixture
def client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── T005: all OK ──────────────────────────────────────────────────────────────


async def test_all_ok(client: AsyncClient):
    """T005: every stream within SLA → overall OK."""
    fresh_ts = _now() - timedelta(seconds=30)

    async def fake_max_ts(table: str, timestamp_column: str):
        return fresh_ts

    async def fake_tip_lag(table: str, block_column: str, current_tip: int):
        # 0 lag → fresh
        return 0

    with (
        patch(
            "api.routes.streams.read_stream_max_ts", AsyncMock(side_effect=fake_max_ts)
        ),
        patch(
            "api.routes.streams.read_stream_tip_lag_seconds",
            AsyncMock(side_effect=fake_tip_lag),
        ),
        patch("api.routes.streams.get_current_tip", AsyncMock(return_value=950_000)),
    ):
        resp = await client.get("/v1/streams/health")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["streams"]) == 13
    assert body["overall"] == OverallStatus.OK.value
    for s in body["streams"]:
        assert s["status"] == StreamStatus.OK.value, f"{s['name']} not OK: {s}"
        assert s.get("error") is None


# ── T006: one stale → overall DEGRADED ────────────────────────────────────────


async def test_one_stale(client: AsyncClient):
    """T006: one stream past SLA → status STALE, overall DEGRADED."""
    fresh_ts = _now() - timedelta(seconds=30)
    very_old = _now() - timedelta(days=30)

    async def fake_max_ts(table: str, timestamp_column: str):
        # net_flow_metrics is past its 6h SLA → STALE
        if table == "net_flow_metrics":
            return very_old
        return fresh_ts

    async def fake_tip_lag(*args, **kwargs):
        return 0

    with (
        patch(
            "api.routes.streams.read_stream_max_ts", AsyncMock(side_effect=fake_max_ts)
        ),
        patch(
            "api.routes.streams.read_stream_tip_lag_seconds",
            AsyncMock(side_effect=fake_tip_lag),
        ),
        patch("api.routes.streams.get_current_tip", AsyncMock(return_value=950_000)),
    ):
        resp = await client.get("/v1/streams/health")

    assert resp.status_code == 200
    body = resp.json()
    by_name = {s["name"]: s for s in body["streams"]}
    assert by_name["net_flow_metrics"]["status"] == StreamStatus.STALE.value
    assert by_name["net_flow_metrics"]["stale_seconds"] > 21600  # 6h SLA
    assert body["overall"] == OverallStatus.DEGRADED.value
    # The other 12 must still be OK
    others_ok = [s for n, s in by_name.items() if n != "net_flow_metrics"]
    assert all(s["status"] == StreamStatus.OK.value for s in others_ok)


# ── T007: empty table → MISSING (no error) ────────────────────────────────────


async def test_table_empty(client: AsyncClient):
    """T007: max(ts) returns None → status MISSING, no error field set."""
    fresh_ts = _now() - timedelta(seconds=30)

    async def fake_max_ts(table: str, timestamp_column: str):
        if table == "utxo_snapshots":
            return None
        return fresh_ts

    async def fake_tip_lag(*args, **kwargs):
        return 0

    with (
        patch(
            "api.routes.streams.read_stream_max_ts", AsyncMock(side_effect=fake_max_ts)
        ),
        patch(
            "api.routes.streams.read_stream_tip_lag_seconds",
            AsyncMock(side_effect=fake_tip_lag),
        ),
        patch("api.routes.streams.get_current_tip", AsyncMock(return_value=950_000)),
    ):
        resp = await client.get("/v1/streams/health")

    assert resp.status_code == 200
    body = resp.json()
    by_name = {s["name"]: s for s in body["streams"]}
    snap = by_name["utxo_snapshots"]
    assert snap["status"] == StreamStatus.MISSING.value
    assert snap["last_row_ts"] is None
    assert snap["stale_seconds"] is None
    assert snap.get("error") is None  # empty != failure
    assert body["overall"] == OverallStatus.DEGRADED.value


# ── T008: backend unreachable → MISSING with error ────────────────────────────


async def test_backend_unreachable(client: AsyncClient):
    """T008: max(ts) raises asyncpg exception → status MISSING + error."""
    import asyncpg

    fresh_ts = _now() - timedelta(seconds=30)

    async def fake_max_ts(table: str, timestamp_column: str):
        if table == "whale_transactions":
            raise asyncpg.exceptions.ConnectionDoesNotExistError("pool closed")
        return fresh_ts

    async def fake_tip_lag(*args, **kwargs):
        return 0

    with (
        patch(
            "api.routes.streams.read_stream_max_ts", AsyncMock(side_effect=fake_max_ts)
        ),
        patch(
            "api.routes.streams.read_stream_tip_lag_seconds",
            AsyncMock(side_effect=fake_tip_lag),
        ),
        patch("api.routes.streams.get_current_tip", AsyncMock(return_value=950_000)),
    ):
        resp = await client.get("/v1/streams/health")

    assert resp.status_code == 200
    body = resp.json()
    by_name = {s["name"]: s for s in body["streams"]}
    whale = by_name["whale_transactions"]
    assert whale["status"] == StreamStatus.MISSING.value
    assert whale["last_row_ts"] is None
    assert whale.get("error") is not None
    assert "ConnectionDoesNotExistError" in whale["error"]
    assert body["overall"] == OverallStatus.DEGRADED.value


# ── T009: auth required ───────────────────────────────────────────────────────


async def test_auth_required(monkeypatch: pytest.MonkeyPatch):
    """T009: no token → 401, no stream data leaked.

    Uses an app WITHOUT the dependency override so the real require_auth
    runs against the missing bearer. Auth is forced on so this does not
    silently pass through the development-mode bypass.
    """
    from api import auth_middleware
    from scripts.config import mempool_config

    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("WEBSOCKET_SECRET_KEY", "test-secret-key")
    monkeypatch.setattr(auth_middleware, "_auth_instance", None)
    monkeypatch.setattr(mempool_config, "_config", None)

    app = FastAPI()
    app.include_router(streams_router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon:
        resp = await anon.get("/v1/streams/health")

    assert resp.status_code == 401
    # Body MUST NOT contain stream-level data
    text = resp.text.lower()
    assert "live_snapshots" not in text
    assert "utxo_lifecycle_full" not in text


# ── T028: schema_version echoed in response ──────────────────────────────────


async def test_schema_version_echoed_in_response(client: AsyncClient):
    """T028: every StreamHealthReading MUST echo the registry schema_version.

    The consumer pins schema_version at connect time per FR-009; the
    endpoint MUST return the version actually backing each stream so the
    pin check succeeds at the wire.
    """
    fresh_ts = _now() - timedelta(seconds=30)

    async def fake_max_ts(table: str, timestamp_column: str):
        return fresh_ts

    async def fake_tip_lag(*args, **kwargs):
        return 0

    with (
        patch(
            "api.routes.streams.read_stream_max_ts", AsyncMock(side_effect=fake_max_ts)
        ),
        patch(
            "api.routes.streams.read_stream_tip_lag_seconds",
            AsyncMock(side_effect=fake_tip_lag),
        ),
        patch("api.routes.streams.get_current_tip", AsyncMock(return_value=950_000)),
    ):
        resp = await client.get("/v1/streams/health")

    body = resp.json()
    # All 13 streams in the v1.0.0 registry carry "1.0.0"
    for s in body["streams"]:
        assert s["schema_version"] == "1.0.0", (
            f"{s['name']}: expected schema_version 1.0.0, got {s['schema_version']!r}"
        )


async def test_deprecated_at_field_optional(client: AsyncClient):
    """T029: deprecated_at marks soft-deprecation; it must not disable probing."""
    fresh_ts = _now() - timedelta(seconds=30)
    deprecated_registry = [
        {
            "name": "legacy_metric",
            "table": "legacy_metric_table",
            "freshness_strategy": "max_ts",
            "timestamp_column": "ts",
            "schema_version": "1.0.0",
            "sla_seconds": 3600,
            "source_spec": "specs/test",
            "pinned_columns": ["ts", "value"],
            "deprecated_at": "2026-05-31",
        }
    ]
    max_ts = AsyncMock(return_value=fresh_ts)

    with (
        patch("api.routes.streams._REGISTRY", deprecated_registry),
        patch("api.routes.streams.read_stream_max_ts", max_ts),
    ):
        resp = await client.get("/v1/streams/health")

    assert resp.status_code == 200
    max_ts.assert_awaited_once_with("legacy_metric_table", "ts")
    body = resp.json()
    stream = body["streams"][0]
    assert body["overall"] == OverallStatus.OK.value
    assert stream["name"] == "legacy_metric"
    assert stream["last_row_ts"] is not None
    assert stream["stale_seconds"] <= 120
    assert stream["sla_seconds"] == 3600
    assert stream["schema_version"] == "1.0.0"
    assert stream["status"] == StreamStatus.OK.value
    assert stream["error"] is None


# ── T011b: tip_lag_blocks strategy ────────────────────────────────────────────


async def test_tip_lag_blocks_strategy(client: AsyncClient):
    """T011b: utxo_lifecycle_full uses tip_lag_blocks.

    Four sub-cases:
    1. lag = 100 blocks → 60_000s < 259_200 (72h SLA) → OK
    2. lag = 500 blocks → 300_000s > 259_200 → STALE
    3. no max(block_column) → MISSING with no error
    4. get_current_tip raises → MISSING with error
    """
    fresh_ts = _now() - timedelta(seconds=30)

    async def fake_max_ts(table: str, timestamp_column: str):
        return fresh_ts

    # Sub-case 1: OK
    async def lag_ok(table: str, block_column: str, current_tip: int):
        return 100 * 600  # 60_000 seconds

    with (
        patch(
            "api.routes.streams.read_stream_max_ts", AsyncMock(side_effect=fake_max_ts)
        ),
        patch(
            "api.routes.streams.read_stream_tip_lag_seconds",
            AsyncMock(side_effect=lag_ok),
        ),
        patch("api.routes.streams.get_current_tip", AsyncMock(return_value=950_000)),
    ):
        resp = await client.get("/v1/streams/health")
    body = resp.json()
    utxo_lc = next(s for s in body["streams"] if s["name"] == "utxo_lifecycle_full")
    assert utxo_lc["status"] == StreamStatus.OK.value
    assert utxo_lc["last_row_ts"] is None
    assert utxo_lc["stale_seconds"] == 60_000

    # Sub-case 2: STALE
    async def lag_stale(*args, **kwargs):
        return 500 * 600  # 300_000 seconds > 259_200 SLA

    with (
        patch(
            "api.routes.streams.read_stream_max_ts", AsyncMock(side_effect=fake_max_ts)
        ),
        patch(
            "api.routes.streams.read_stream_tip_lag_seconds",
            AsyncMock(side_effect=lag_stale),
        ),
        patch("api.routes.streams.get_current_tip", AsyncMock(return_value=950_000)),
    ):
        resp = await client.get("/v1/streams/health")
    body = resp.json()
    utxo_lc = next(s for s in body["streams"] if s["name"] == "utxo_lifecycle_full")
    assert utxo_lc["status"] == StreamStatus.STALE.value
    assert utxo_lc["last_row_ts"] is None
    assert utxo_lc["stale_seconds"] == 300_000

    # Sub-case 3: empty table → MISSING without error
    async def lag_missing(*args, **kwargs):
        return None

    with (
        patch(
            "api.routes.streams.read_stream_max_ts", AsyncMock(side_effect=fake_max_ts)
        ),
        patch(
            "api.routes.streams.read_stream_tip_lag_seconds",
            AsyncMock(side_effect=lag_missing),
        ),
        patch("api.routes.streams.get_current_tip", AsyncMock(return_value=950_000)),
    ):
        resp = await client.get("/v1/streams/health")
    body = resp.json()
    utxo_lc = next(s for s in body["streams"] if s["name"] == "utxo_lifecycle_full")
    assert utxo_lc["status"] == StreamStatus.MISSING.value
    assert utxo_lc["last_row_ts"] is None
    assert utxo_lc["stale_seconds"] is None
    assert utxo_lc.get("error") is None

    # Sub-case 4: tip RPC fails → MISSING with error
    async def tip_fails():
        raise RuntimeError("bitcoind RPC unreachable")

    with (
        patch(
            "api.routes.streams.read_stream_max_ts", AsyncMock(side_effect=fake_max_ts)
        ),
        patch(
            "api.routes.streams.read_stream_tip_lag_seconds",
            AsyncMock(side_effect=lag_ok),
        ),
        patch("api.routes.streams.get_current_tip", AsyncMock(side_effect=tip_fails)),
    ):
        resp = await client.get("/v1/streams/health")
    body = resp.json()
    utxo_lc = next(s for s in body["streams"] if s["name"] == "utxo_lifecycle_full")
    assert utxo_lc["status"] == StreamStatus.MISSING.value
    assert utxo_lc["last_row_ts"] is None
    assert utxo_lc.get("error") is not None
    assert "bitcoind" in utxo_lc["error"] or "RuntimeError" in utxo_lc["error"]
