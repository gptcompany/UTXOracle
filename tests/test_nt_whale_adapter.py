from __future__ import annotations

import httpx
import pytest

from scripts.nautilus_live.nt_adapter import NTWhaleAdapter


def _json_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=payload)


@pytest.mark.asyncio
async def test_can_execute_accepts_trade_enabled_execution_status():
    transport = httpx.MockTransport(
        lambda request: _json_response(
            {
                "execution_mode": "trade_enabled",
                "compatibility_status": "STATUS_OK",
                "status_reason": "healthy",
            }
        )
    )
    adapter = NTWhaleAdapter(transport=transport)

    try:
        assert await adapter.can_execute() is True
    finally:
        await adapter.aclose()


@pytest.mark.asyncio
async def test_can_execute_rejects_non_trade_execution_mode():
    transport = httpx.MockTransport(
        lambda request: _json_response(
            {
                "execution_mode": "manage_only",
                "compatibility_status": "STATUS_LIQUIDATE_ONLY",
                "status_reason": "operator_stage_cap",
            }
        )
    )
    adapter = NTWhaleAdapter(transport=transport)

    try:
        assert await adapter.can_execute() is False
    finally:
        await adapter.aclose()


@pytest.mark.asyncio
async def test_can_execute_rejects_high_jitter_when_present():
    transport = httpx.MockTransport(
        lambda request: _json_response(
            {
                "execution_mode": "trade_enabled",
                "compatibility_status": "STATUS_OK",
                "status_reason": "healthy",
                "stats": {"last_jitter_ms": 750},
            }
        )
    )
    adapter = NTWhaleAdapter(transport=transport, max_jitter_ms=500)

    try:
        assert await adapter.can_execute() is False
    finally:
        await adapter.aclose()


@pytest.mark.asyncio
async def test_can_execute_rejects_non_200_gatekeeper_response():
    transport = httpx.MockTransport(lambda request: _json_response({}, status_code=503))
    adapter = NTWhaleAdapter(transport=transport)

    try:
        assert await adapter.can_execute() is False
    finally:
        await adapter.aclose()
