"""F-434: a row whose value has the wrong type for an existing column must not vanish.

Over ILP/TCP QuestDB drops such a row server-side and the client never learns of it.
Over ILP/HTTP the flush is confirmed, so the rejection reaches the writer. Runs against the
QuestDB named by QUESTDB_TEST_* (the CI service container); skipped, without opening any
connection, when it is not set. No default host or port: a developer machine is never
written to by accident.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest

_TARGET_ENV = (
    "QUESTDB_TEST_HOST",
    "QUESTDB_TEST_PORT",
    "QUESTDB_TEST_ILP_PORT",
    "QUESTDB_TEST_HTTP_PORT",
    "QUESTDB_TEST_USER",
    "QUESTDB_TEST_PASSWORD",
)
_LIVE_PORTS = {9900, 9909, 9912}


def _target() -> dict:
    missing = [name for name in _TARGET_ENV if not os.getenv(name)]
    if missing:
        pytest.skip(
            "explicit QuestDB test target required, not set: " + ", ".join(missing)
        )
    target = {
        "host": os.environ["QUESTDB_TEST_HOST"],
        "port": int(os.environ["QUESTDB_TEST_PORT"]),
        "ilp_port": int(os.environ["QUESTDB_TEST_ILP_PORT"]),
        "http_port": int(os.environ["QUESTDB_TEST_HTTP_PORT"]),
        "user": os.environ["QUESTDB_TEST_USER"],
        "password": os.environ["QUESTDB_TEST_PASSWORD"],
        "database": os.getenv("QUESTDB_TEST_DATABASE", "qdb"),
    }
    forbidden = {target["port"], target["ilp_port"], target["http_port"]} & _LIVE_PORTS
    assert not forbidden, f"QUESTDB_TEST_* points at a live QuestDB port: {forbidden}"
    # 9000 is the host QuestDB of a developer machine: accepted only on the CI service.
    if 9000 in (target["port"], target["http_port"]):
        assert os.getenv("GITHUB_ACTIONS") == "true", "port 9000 only on the CI service"
    return target


async def _pg(target: dict, sql: str, *, fetch: bool = False):
    import asyncpg

    conn = await asyncpg.connect(
        host=target["host"],
        port=target["port"],
        user=target["user"],
        password=target["password"],
        database=target["database"],
    )
    try:
        return await (conn.fetchval(sql) if fetch else conn.execute(sql))
    finally:
        await conn.close()


async def _wait_count(target: dict, table: str, expected: int) -> int:
    seen = -1
    for _ in range(15):
        seen = await _pg(target, f"SELECT count() FROM {table}", fetch=True)
        if seen == expected:
            break
        await asyncio.sleep(1)
    return seen


@pytest.fixture
def probe(monkeypatch):
    """A repository bound to the test target and a WAL table with a DOUBLE column."""
    import api.questdb_repository as repository

    target = _target()
    table = f"f434_probe_{uuid.uuid4().hex[:8]}"
    for name, value in (
        ("QUESTDB_ILP_HOST", target["host"]),
        ("QUESTDB_ILP_PORT", target["ilp_port"]),
        ("QUESTDB_HTTP_HOST", target["host"]),
        ("QUESTDB_HTTP_PORT", target["http_port"]),
    ):
        # The ILP names disappear with the correction: raising=False keeps this file valid
        # both before and after it.
        monkeypatch.setattr(repository, name, value, raising=False)
    asyncio.run(
        _pg(
            target,
            f"CREATE TABLE {table} (ts TIMESTAMP, v DOUBLE) "
            "TIMESTAMP(ts) PARTITION BY DAY WAL",
        )
    )
    repo = repository.QuestDBRepository()
    monkeypatch.setattr(repo, "ilp_host", target["host"], raising=False)
    monkeypatch.setattr(repo, "ilp_port", target["ilp_port"], raising=False)
    yield target, table, repo
    asyncio.run(_pg(target, f"DROP TABLE IF EXISTS {table}"))


def test_a_valid_row_is_persisted(probe):
    target, table, repo = probe
    sent = repo._send_row(
        table, symbols={}, columns={"v": 1.5}, at=datetime.now(timezone.utc), flush=True
    )
    assert sent is True
    assert asyncio.run(_wait_count(target, table, 1)) == 1


def test_a_row_with_the_wrong_type_is_reported_not_silently_lost(probe):
    target, table, repo = probe
    sent = repo._send_row(
        table,
        symbols={},
        columns={"v": "not-a-number"},
        at=datetime.now(timezone.utc),
        flush=True,
    )
    assert sent is False, "the rejected row was reported as written"
    assert asyncio.run(_wait_count(target, table, 0)) == 0


def test_the_sender_flush_raises_ingress_error_on_the_wrong_type(probe):
    from questdb.ingress import IngressError

    _, table, repo = probe
    sender = repo._build_sender()
    sender.row(table, columns={"v": "not-a-number"}, at=datetime.now(timezone.utc))
    with pytest.raises(IngressError):
        sender.flush()
    sender.close(flush=False)
