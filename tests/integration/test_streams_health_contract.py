"""Integration acceptance test for /v1/streams/health (spec-061 T010).

The CI gate for closing Issue #8. Asserts that the live endpoint:

1. responds with HTTP 200 through the authenticated route surface,
2. returns exactly 13 stream readings (the registry contract),
3. each reading conforms to the OpenAPI schema in
   `specs/061-stream-consumption-contract/contracts/streams_health.openapi.yaml`,
4. `overall == "OK"`.

Runs only with the `integration` marker and
`RUN_STREAMS_HEALTH_CONTRACT=1`. When explicitly enabled, QuestDB on
`:8812` must be reachable. Expected to be RED until the
`utxo_lifecycle` catch-up backfill (T036) completes and the daily
aggregator (T024/T025) has run at least once.
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
_OK = "OK"
_VALID_STATUSES = {"OK", "STALE", "MISSING"}
_RUN_ENV = "RUN_STREAMS_HEALTH_CONTRACT"


def _resolve_openapi_schema(node: Any, components: dict[str, Any]) -> Any:
    """Convert the OpenAPI response schema into JSON Schema for validation."""
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
                database=os.getenv("QUESTDB_PG_DATABASE", "main"),
            ),
            timeout=3,
        )
        await conn.close()
        return True
    except Exception:
        return False


@pytest.fixture
async def streams_app():
    """Mount streams_router on a minimal FastAPI app for the integration run.

    Auth is overridden so the test does not need a token in CI; the live
    deployment's `require_auth` is exercised by the unit test in
    `tests/test_streams_health.py::test_auth_required`. The acceptance
    gate is intentionally read-only: DDL/table provisioning is covered by
    `tests/test_create_tables_ddl.py`.
    """
    if os.getenv(_RUN_ENV) != "1":
        pytest.skip(f"set {_RUN_ENV}=1 to run the live streams health gate")

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


async def test_overall_ok_after_backfill(streams_app):
    """T010: live registry probe MUST report overall == OK.

    This is the CI gate for closing Issue #8. It is expected to be RED
    until:
      - `utxo_lifecycle` is within tip-72h of the live tip (T036)
      - the daily aggregator has run at least once (T024/T025/T026)
      - the backtest mirror has run at least once (T026a/T026c)

    Once those operational prerequisites complete, this test MUST stay
    green on every CI run. A drift back to DEGRADED is a contract
    regression and blocks merge until the offending stream returns to OK.
    """
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

    streams = body.get("streams")
    assert len(streams) == _EXPECTED_STREAM_COUNT, (
        f"contract requires {_EXPECTED_STREAM_COUNT} streams, got {len(streams)}"
    )

    for s in streams:
        assert s["status"] in _VALID_STATUSES, (
            f"{s['name']}: invalid status {s['status']!r}"
        )

    # Compare against the registry: every contract name MUST appear.
    registry = yaml.safe_load(_REGISTRY_PATH.read_text())
    expected_names = {e["name"] for e in registry["streams"]}
    actual_names = {s["name"] for s in streams}
    missing = expected_names - actual_names
    assert not missing, f"endpoint omitted contract streams: {sorted(missing)}"

    # The acceptance gate itself.
    assert body["overall"] == _OK, (
        f"overall = {body['overall']!r}; streams in non-OK state: "
        + ", ".join(
            f"{s['name']}[{s['status']}, stale={s['stale_seconds']}s, sla={s['sla_seconds']}s]"
            for s in streams
            if s["status"] != _OK
        )
    )
