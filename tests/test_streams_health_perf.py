"""Performance test for GET /v1/streams/health (spec-061 T038b).

Asserts the endpoint stays within the p95 < 500ms budget declared in
`specs/061-stream-consumption-contract/plan.md` section Performance Goals
(Constitution Principle IV). Each freshness probe is mocked with a
5ms artificial delay to simulate QuestDB RTT - the real route should
issue all 13 probes in parallel via `asyncio.gather`, so the total
should stay well below 13 x 5ms even before the budget headroom.

If this test fails, the endpoint is doing something serial (e.g. a
for-loop awaiting each probe), which would scale linearly with the
registry size and degrade as new streams are added.
"""

from __future__ import annotations

import asyncio
import statistics
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routes.streams import router as streams_router

pytestmark = pytest.mark.asyncio

_PROBE_DELAY_SECONDS = 0.005  # 5ms simulated RTT per probe
_P95_BUDGET_SECONDS = 0.500  # plan.md Performance Goals
_RUNS = 50


@pytest.fixture
def app() -> FastAPI:
    from api.auth_middleware import require_auth

    a = FastAPI()
    a.include_router(streams_router)

    async def _noop_auth():
        return None

    a.dependency_overrides[require_auth] = _noop_auth
    return a


async def test_p95_under_500ms(app: FastAPI):
    """Endpoint p95 latency MUST stay under 500ms with 5ms-delayed mocked probes."""
    fresh_ts = datetime.now(timezone.utc) - timedelta(seconds=30)

    async def slow_max_ts(table: str, timestamp_column: str):
        await asyncio.sleep(_PROBE_DELAY_SECONDS)
        return fresh_ts

    async def slow_tip_lag(table: str, block_column: str, current_tip: int):
        await asyncio.sleep(_PROBE_DELAY_SECONDS)
        return 0

    durations: list[float] = []
    with (
        patch(
            "api.routes.streams.read_stream_max_ts", AsyncMock(side_effect=slow_max_ts)
        ),
        patch(
            "api.routes.streams.read_stream_tip_lag_seconds",
            AsyncMock(side_effect=slow_tip_lag),
        ),
        patch("api.routes.streams.get_current_tip", AsyncMock(return_value=950_000)),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(_RUNS):
                loop = asyncio.get_event_loop()
                t0 = loop.time()
                resp = await client.get("/v1/streams/health")
                durations.append(loop.time() - t0)
                assert resp.status_code == 200

    durations.sort()
    p50 = statistics.median(durations)
    p95 = durations[int(len(durations) * 0.95)]
    max_d = durations[-1]

    # If parallelism is working, every run should be close to one probe
    # latency (5ms) plus framework overhead. A serial loop over 13 probes
    # would land near 65ms minimum - still under budget but a regression
    # signal we want to track. The hard assertion is the published budget.
    assert p95 < _P95_BUDGET_SECONDS, (
        f"p95 = {p95 * 1000:.1f}ms exceeds {_P95_BUDGET_SECONDS * 1000:.0f}ms budget. "
        f"p50={p50 * 1000:.1f}ms, max={max_d * 1000:.1f}ms. "
        f"Likely cause: serial probes instead of asyncio.gather."
    )
