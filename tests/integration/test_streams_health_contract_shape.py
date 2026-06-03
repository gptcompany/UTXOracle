"""Contract-shape acceptance test (spec-061 T010 split, 2026-06-03).

Separates the spec-061 acceptance gate into two independently testable
slices:

- **Shape gate (this file)**: the response conforms to the OpenAPI
  contract, every registry stream appears, every status is one of the
  enum values, and the rollup behaviour holds (overall == OK iff every
  stream is OK). Runs against the live endpoint; passes even when
  upstream producers haven't populated their backing tables yet, because
  the contract is about the *shape*, not the data.

- **Data gate (test_streams_health_contract.py)**: asserts ``overall ==
  "OK"`` against live data. Requires every producer to be running and
  every backing table to be fresh. This is the operational gate.

Both gates use the ``integration`` marker plus the
``RUN_STREAMS_HEALTH_CONTRACT=1`` opt-in to stay out of the default
unit run.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from jsonschema import Draft7Validator

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_REGISTRY_PATH = _REPO_ROOT / "docs" / "contracts" / "stream_registry.yaml"
_OPENAPI_PATH = (
    _REPO_ROOT
    / "specs"
    / "061-stream-consumption-contract"
    / "contracts"
    / "streams_health.openapi.yaml"
)

_EXPECTED_STREAM_COUNT = 13
_VALID_STATUSES = {"OK", "STALE", "MISSING"}
_VALID_OVERALL = {"OK", "DEGRADED"}
_RUN_ENV = "RUN_STREAMS_HEALTH_CONTRACT"


def _resolve_openapi_schema(node: Any, components: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_resolve_openapi_schema(item, components) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        ref = node["$ref"]
        prefix = "#/components/schemas/"
        if not ref.startswith(prefix):
            raise AssertionError(f"unsupported OpenAPI ref: {ref}")
        target = components[ref.removeprefix(prefix)]
        merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
        return _resolve_openapi_schema(merged, components)
    converted = {
        key: _resolve_openapi_schema(value, components)
        for key, value in node.items()
        if key != "nullable"
    }
    if node.get("nullable") is True and "type" in converted:
        current_type = converted["type"]
        if isinstance(current_type, list):
            converted["type"] = [*current_type, "null"]
        else:
            converted["type"] = [current_type, "null"]
    return converted


def _streams_health_response_schema() -> dict[str, Any]:
    openapi = yaml.safe_load(_OPENAPI_PATH.read_text())
    components = openapi["components"]["schemas"]
    response_schema = openapi["paths"]["/v1/streams/health"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    return cast(dict[str, Any], _resolve_openapi_schema(response_schema, components))


async def _questdb_reachable() -> bool:
    try:
        import asyncpg

        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=os.getenv("QUESTDB_PG_HOST", "localhost"),
                port=int(os.getenv("QUESTDB_PG_PORT", 8812)),
                user=os.getenv("QUESTDB_PG_USER", "admin"),
                password=os.getenv("QUESTDB_PG_PASSWORD", "quest"),
                database=os.getenv("QUESTDB_PG_DATABASE", "qdb"),
            ),
            timeout=3,
        )
        await conn.close()
        return True
    except Exception:
        return False


@pytest.fixture
async def streams_app():
    if os.getenv(_RUN_ENV) != "1":
        pytest.skip(f"set {_RUN_ENV}=1 to run the live contract-shape gate")
    if not await _questdb_reachable():
        pytest.fail("QuestDB not reachable on :8812")

    from fastapi import FastAPI

    from api.auth_middleware import require_auth
    from api.routes.streams import router as streams_router

    app = FastAPI()
    app.include_router(streams_router)

    async def _noop_auth():
        return None

    app.dependency_overrides[require_auth] = _noop_auth
    return app


async def test_response_conforms_to_openapi_schema(streams_app):
    """The wire body MUST conform to streams_health.openapi.yaml — every
    field, every type, every nullable. Failing this assertion means the
    server-side model drifted from the published contract."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=streams_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/streams/health")

    assert resp.status_code == 200, f"unexpected status {resp.status_code}: {resp.text}"
    body = resp.json()
    schema = _streams_health_response_schema()
    errors = sorted(
        Draft7Validator(schema).iter_errors(body),
        key=lambda err: list(err.absolute_path),
    )
    assert not errors, "\n".join(
        f"{list(err.absolute_path)}: {err.message}" for err in errors
    )


async def test_response_lists_every_registry_stream(streams_app):
    """Every stream named in ``stream_registry.yaml`` MUST appear in the
    response, regardless of freshness state. A missing entry is a
    contract violation, even if its backing table is empty."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=streams_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/streams/health")

    body = resp.json()
    streams = body["streams"]
    assert len(streams) == _EXPECTED_STREAM_COUNT, (
        f"contract requires {_EXPECTED_STREAM_COUNT} streams, got {len(streams)}"
    )

    registry = yaml.safe_load(_REGISTRY_PATH.read_text())
    expected_names = {e["name"] for e in registry["streams"]}
    actual_names = {s["name"] for s in streams}
    missing = expected_names - actual_names
    extra = actual_names - expected_names
    assert not missing, f"endpoint omitted contract streams: {sorted(missing)}"
    assert not extra, f"endpoint returned unknown streams: {sorted(extra)}"


async def test_per_stream_status_is_in_enum(streams_app):
    """Every per-stream status MUST be one of OK / STALE / MISSING."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=streams_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/streams/health")

    body = resp.json()
    bad = [
        (s["name"], s["status"])
        for s in body["streams"]
        if s["status"] not in _VALID_STATUSES
    ]
    assert not bad, f"invalid statuses: {bad}"


async def test_overall_consistency_with_per_stream(streams_app):
    """``overall == "OK"`` iff every stream is OK. ``DEGRADED`` iff at
    least one stream is not OK. This is the FR-003 rollup rule, and the
    most consumer-visible invariant in the entire contract."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=streams_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/streams/health")

    body = resp.json()
    assert body["overall"] in _VALID_OVERALL
    all_ok = all(s["status"] == "OK" for s in body["streams"])
    if all_ok:
        assert body["overall"] == "OK", (
            "rollup must be OK when every stream is OK"
        )
    else:
        assert body["overall"] == "DEGRADED", (
            "rollup must be DEGRADED when at least one stream is non-OK; "
            f"not-OK streams: "
            f"{[(s['name'], s['status']) for s in body['streams'] if s['status'] != 'OK']}"
        )


async def test_deprecated_at_is_optional_and_echoed_when_present(streams_app):
    """``deprecated_at`` MUST be optional. When present in the registry
    it MUST be echoed back in the response so the consumer can plan
    migration without a separate registry fetch."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=streams_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/streams/health")

    body = resp.json()
    registry = yaml.safe_load(_REGISTRY_PATH.read_text())
    expected_deprecation = {
        e["name"]: e.get("deprecated_at") for e in registry["streams"]
    }
    for s in body["streams"]:
        expected = expected_deprecation.get(s["name"])
        actual = s.get("deprecated_at")
        if expected is None:
            assert actual is None, (
                f"{s['name']}: response has deprecated_at={actual} but "
                f"registry has no deprecation"
            )
        else:
            assert actual == expected, (
                f"{s['name']}: response deprecated_at={actual} != "
                f"registry deprecated_at={expected}"
            )


async def test_sla_seconds_matches_registry(streams_app):
    """Per-stream ``sla_seconds`` MUST mirror the registry, so a consumer
    that bypasses the registry can still trust the endpoint's SLA values."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=streams_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/streams/health")

    body = resp.json()
    registry = yaml.safe_load(_REGISTRY_PATH.read_text())
    expected_sla = {e["name"]: e["sla_seconds"] for e in registry["streams"]}
    for s in body["streams"]:
        expected = expected_sla.get(s["name"])
        assert s["sla_seconds"] == expected, (
            f"{s['name']}: response sla_seconds={s['sla_seconds']} != "
            f"registry sla_seconds={expected}"
        )
