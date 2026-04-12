from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest

from scripts.live import wave1_materializer_runtime as runtime


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_configure_live_questdb_defaults_sets_loopback_ports(monkeypatch):
    monkeypatch.delenv("QUESTDB_PG_HOST", raising=False)
    monkeypatch.delenv("QUESTDB_PG_PORT", raising=False)
    monkeypatch.delenv("QUESTDB_ILP_HOST", raising=False)
    monkeypatch.delenv("QUESTDB_ILP_PORT", raising=False)
    monkeypatch.delenv("QUESTDB_HTTP_HOST", raising=False)
    monkeypatch.delenv("QUESTDB_HTTP_PORT", raising=False)

    runtime._configure_live_questdb_defaults()

    assert os.environ["QUESTDB_PG_HOST"] == "127.0.0.1"
    assert os.environ["QUESTDB_PG_PORT"] == "9912"
    assert os.environ["QUESTDB_ILP_HOST"] == "127.0.0.1"
    assert os.environ["QUESTDB_ILP_PORT"] == "9909"
    assert os.environ["QUESTDB_HTTP_HOST"] == "127.0.0.1"
    assert os.environ["QUESTDB_HTTP_PORT"] == "9900"


@pytest.mark.asyncio
async def test_run_once_opens_duckdb_read_only_and_closes_connection(monkeypatch):
    fake_conn = _FakeConnection()
    connect_calls: list[tuple[str, bool]] = []

    def fake_connect(path: str, *, read_only: bool):
        connect_calls.append((path, read_only))
        return fake_conn

    monkeypatch.setattr(runtime.duckdb, "connect", fake_connect)
    monkeypatch.setattr(
        runtime,
        "run_materialization_pass",
        AsyncMock(return_value=True),
    )

    assert await runtime._run_once() is True
    assert connect_calls == [(runtime.DEFAULT_DUCKDB_PATH, True)]
    runtime.run_materialization_pass.assert_awaited_once_with(
        fake_conn,
        runtime.run_materialization_pass.await_args.args[1],
    )
    assert fake_conn.closed is True
