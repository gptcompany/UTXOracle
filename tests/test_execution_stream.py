from __future__ import annotations

import pytest

from api.routes.execution import ConnectionManager


class _FakeWebSocket:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[str] = []

    async def send_text(self, payload: str) -> None:
        if self.fail:
            raise RuntimeError("socket closed")
        self.messages.append(payload)


@pytest.mark.asyncio
async def test_connection_manager_broadcast_removes_failed_connections():
    manager = ConnectionManager()
    healthy = _FakeWebSocket()
    failing = _FakeWebSocket(fail=True)
    manager.active_connections = [healthy, failing]

    await manager.broadcast({"type": "whale_alert", "data": {"transaction_id": "abc"}})

    assert len(healthy.messages) == 1
    assert healthy in manager.active_connections
    assert failing not in manager.active_connections
