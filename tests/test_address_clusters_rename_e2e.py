"""F-424 gate: the RENAME swap of a WAL table, against a real QuestDB (CI service).

Proves four things on tables owned by this test (never address_clusters):
 1. RENAME of a WAL table with a reader running in parallel: the reader sees no error
    other than "table does not exist" inside the measured window between the two RENAMEs;
 2. afterwards the live name holds exactly the staged rows and a later ILP/HTTP write is
    applied (writerTxn advances, not suspended);
 3. rollback: a second RENAME that fails by construction restores the live table;
 4. the _old copy stays readable.

Target: QUESTDB_TEST_HOST/PORT(PG)/USER/PASSWORD and QUESTDB_TEST_HTTP_PORT; skipped,
without opening any connection, when they are not all set.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from api.questdb_repository import QuestDBRepository, fetch_address_clusters

pytestmark = pytest.mark.asyncio

_ENV = (
    "QUESTDB_TEST_HOST",
    "QUESTDB_TEST_PORT",
    "QUESTDB_TEST_USER",
    "QUESTDB_TEST_PASSWORD",
    "QUESTDB_TEST_HTTP_PORT",
)


def _target() -> dict:
    missing = [n for n in _ENV if not os.getenv(n)]
    if missing:
        pytest.skip(
            "explicit QuestDB test target required, not set: " + ", ".join(missing)
        )
    return {
        "host": os.environ["QUESTDB_TEST_HOST"],
        "port": int(os.environ["QUESTDB_TEST_PORT"]),
        "user": os.environ["QUESTDB_TEST_USER"],
        "password": os.environ["QUESTDB_TEST_PASSWORD"],
        "database": os.getenv("QUESTDB_TEST_DATABASE", "qdb"),
    }


_DDL = "CREATE TABLE {} (n LONG, ts TIMESTAMP) timestamp(ts) PARTITION BY DAY WAL"


def _ingest(rows: int, table: str, first: int = 0) -> None:
    from datetime import datetime, timezone

    from questdb.ingress import Sender

    with Sender(
        "http",
        os.environ["QUESTDB_TEST_HOST"],
        int(os.environ["QUESTDB_TEST_HTTP_PORT"]),
        auto_flush=False,
    ) as sender:
        for i in range(first, first + rows):
            sender.row(table, columns={"n": i}, at=datetime.now(timezone.utc))
        sender.flush()  # HTTP: returns after the commit, raises if rejected


async def _wal_state(conn, table: str):
    rows = await conn.fetch(
        'SELECT suspended, "writerTxn", "sequencerTxn" FROM wal_tables() WHERE name = $1',
        table,
    )
    return rows[0] if rows else None


async def _wait_applied(reader, table: str, expected: int) -> None:
    for _ in range(100):
        state = await _wal_state(reader, table)
        assert state is not None and not state["suspended"]
        if state["writerTxn"] >= state["sequencerTxn"]:
            count = (await reader.fetch(f"SELECT count(*) FROM {table}"))[0][0]
            if count == expected:
                return
        await asyncio.sleep(0.2)
    raise AssertionError(f"{table} never reached {expected} rows")


async def test_rename_swap_of_wal_tables_with_a_live_reader():
    import asyncpg

    target = _target()
    suffix = uuid.uuid4().hex[:8]
    live, staging = f"f424_live_{suffix}", f"f424_staging_{suffix}"
    old = f"{live}_old_20260101T000000Z"
    old2 = f"{live}_old_20260102T000000Z"
    ddl = await asyncpg.connect(**target)  # DDL connection: execute only
    reader = await asyncpg.connect(**target)  # reads only
    watcher = await asyncpg.connect(**target)  # the parallel reader under test
    repo = QuestDBRepository()
    repo.fetch = reader.fetch  # tables() listing on a read-only connection
    repo._open_dedicated_connection = lambda: _async_value(_KeepOpen(ddl))
    try:
        await ddl.execute(_DDL.format(live))
        await ddl.execute(_DDL.format(staging))
        _ingest(3, live)
        _ingest(5, staging)
        await _wait_applied(reader, live, 3)
        await _wait_applied(reader, staging, 5)

        errors: list[str] = []
        reads = 0
        stop = asyncio.Event()

        async def read_loop():
            nonlocal reads
            while not stop.is_set():
                try:
                    await watcher.fetch(f"SELECT count(*) FROM {live}")
                    reads += 1
                except Exception as e:  # noqa: BLE001 - classified below
                    errors.append(str(e))
                await asyncio.sleep(0)

        reader_task = asyncio.create_task(read_loop())
        await asyncio.sleep(0.3)
        window_ms = await repo._swap_tables(ddl, live, staging, old)
        await asyncio.sleep(0.3)
        stop.set()
        await reader_task

        summary = (
            f"F-424 RENAME window between the two RENAMEs: {window_ms:.1f} ms "
            f"({reads} reads, {len(errors)} reader errors)"
        )
        print(summary)
        if os.getenv("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
                f.write(summary + "\n")
        # (1) the only tolerated reader error is the absent table inside the window
        assert all("does not exist" in e for e in errors), errors
        assert reads > 0

        # (2) the live name holds exactly the staged rows, and a new ILP/HTTP write lands
        assert (await reader.fetch(f"SELECT count(*) FROM {live}"))[0][0] == 5
        before = await _wal_state(reader, live)
        _ingest(1, live, first=100)
        await _wait_applied(reader, live, 6)
        after = await _wal_state(reader, live)
        assert after["writerTxn"] > before["writerTxn"] and not after["suspended"]

        # (4) the previous live table is still readable as the rollback copy
        assert (await reader.fetch(f"SELECT count(*) FROM {old}"))[0][0] == 3

        # (3) rollback: the second RENAME fails by construction (no such staging table);
        # the live table is put back by the reconcile of the OBSERVED tables
        missing = f"f424_missing_{suffix}"
        assert await repo._swap_or_reconcile(ddl, live, missing, old2) is None
        assert (await reader.fetch(f"SELECT count(*) FROM {live}"))[0][0] == 6
    finally:
        for name in (live, staging, old, old2):
            try:
                await ddl.execute(f"DROP TABLE IF EXISTS {name}")
            except Exception:  # noqa: BLE001 - best-effort cleanup of test-owned tables
                pass
        for conn in (ddl, reader, watcher):
            await conn.close()


class _GatedConn:
    """DDL connection that holds the RENAME of `staging` until the gate opens."""

    def __init__(self, conn, staging: str):
        self.conn, self.staging = conn, staging
        self.gate, self.started = asyncio.Event(), asyncio.Event()

    async def execute(self, query, *args):
        if query.startswith(f"RENAME TABLE {self.staging} TO"):
            self.started.set()
            await self.gate.wait()
        return await self.conn.execute(query, *args)


class _KeepOpen:
    """Lends one DDL connection to code that opens and closes its own."""

    def __init__(self, conn):
        self.conn = conn

    async def execute(self, query, *args):
        return await self.conn.execute(query, *args)

    async def close(self):
        return None


async def test_cancel_between_the_renames_leaves_the_new_live_table():
    import asyncpg

    target = _target()
    suffix = uuid.uuid4().hex[:8]
    live, staging = f"f424_live_{suffix}", f"f424_staging_{suffix}"
    old = f"{live}_old_20260101T000000Z"
    ddl = await asyncpg.connect(**target)
    reader = await asyncpg.connect(**target)
    repo = QuestDBRepository()
    try:
        await ddl.execute(_DDL.format(live))
        await ddl.execute(_DDL.format(staging))
        _ingest(3, live)
        _ingest(5, staging)
        await _wait_applied(reader, live, 3)
        await _wait_applied(reader, staging, 5)

        gated = _GatedConn(ddl, staging)
        task = asyncio.create_task(repo._guarded_swap(gated, live, staging, old))
        await asyncio.wait_for(
            gated.started.wait(), 10
        )  # first RENAME done, second held
        task.cancel()
        await asyncio.sleep(0)
        gated.gate.set()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert (await reader.fetch(f"SELECT count(*) FROM {live}"))[0][0] == 5
        assert (await reader.fetch(f"SELECT count(*) FROM {old}"))[0][0] == 3
    finally:
        for name in (live, staging, old):
            try:
                await ddl.execute(f"DROP TABLE IF EXISTS {name}")
            except Exception:  # noqa: BLE001 - best-effort cleanup of test-owned tables
                pass
        for conn in (ddl, reader):
            await conn.close()


async def test_reconcile_restores_the_live_table_from_the_old_copy():
    import asyncpg

    target = _target()
    suffix = uuid.uuid4().hex[:8]
    live = f"f424_live_{suffix}"
    old = f"{live}_old_20260101T000000Z"
    ddl = await asyncpg.connect(**target)
    reader = await asyncpg.connect(**target)
    repo = QuestDBRepository()
    repo.fetch = reader.fetch  # tables() listing on a read-only connection
    repo._open_dedicated_connection = lambda: _async_value(_KeepOpen(ddl))
    try:
        await ddl.execute(_DDL.format(live))
        _ingest(3, live)
        await _wait_applied(reader, live, 3)
        await ddl.execute(f"RENAME TABLE {live} TO {old}")  # what a killed swap leaves

        await repo._reconcile_tables(live, f"{live}")

        assert (await reader.fetch(f"SELECT count(*) FROM {live}"))[0][0] == 3
    finally:
        for name in (live, old):
            try:
                await ddl.execute(f"DROP TABLE IF EXISTS {name}")
            except Exception:  # noqa: BLE001 - best-effort cleanup of test-owned tables
                pass
        for conn in (ddl, reader):
            await conn.close()


async def _async_value(value):
    return value


class _AckLostConn:
    """Client-side injection: the statement is applied, then the answer is lost."""

    def __init__(self, conn, prefix: str):
        self.conn, self.prefix, self.fired = conn, prefix, False

    async def execute(self, query, *args):
        result = await self.conn.execute(query, *args)
        if query.startswith(self.prefix) and not self.fired:
            self.fired = True
            raise ConnectionError("connection lost before the acknowledgement")
        return result


async def _two_tables(ddl, reader, live: str, staging: str):
    await ddl.execute(_DDL.format(live))
    await ddl.execute(_DDL.format(staging))
    _ingest(3, live)
    _ingest(5, staging)
    await _wait_applied(reader, live, 3)
    await _wait_applied(reader, staging, 5)


async def _drop(ddl, *names: str):
    for name in names:
        try:
            await ddl.execute(f"DROP TABLE IF EXISTS {name}")
        except Exception:  # noqa: BLE001 - best-effort cleanup of test-owned tables
            pass


async def test_lost_ack_of_the_first_rename_is_recovered_on_an_independent_connection():
    import asyncpg

    target = _target()
    suffix = uuid.uuid4().hex[:8]
    live, staging = f"f424_live_{suffix}", f"f424_staging_{suffix}"
    old = f"{live}_old_20260101T000000Z"
    ddl = await asyncpg.connect(**target)
    reader = await asyncpg.connect(**target)  # the independent observer
    repo = QuestDBRepository()
    repo.fetch = reader.fetch
    repo._open_dedicated_connection = lambda: _async_value(_KeepOpen(ddl))
    try:
        await _two_tables(ddl, reader, live, staging)
        lossy = _AckLostConn(ddl, f"RENAME TABLE {live} TO")

        assert await repo._swap_or_reconcile(lossy, live, staging, old) is None

        assert lossy.fired
        assert (await reader.fetch(f"SELECT count(*) FROM {live}"))[0][0] == 3
    finally:
        await _drop(ddl, live, staging, old)
        for conn in (ddl, reader):
            await conn.close()


async def test_sigkill_between_the_renames_is_recovered_by_the_next_process():
    """A separate process runs the production swap and is SIGKILLed between the RENAMEs."""
    import subprocess
    import sys
    from pathlib import Path

    import asyncpg

    target = _target()
    suffix = uuid.uuid4().hex[:8]
    live, staging = f"f424_live_{suffix}", f"f424_staging_{suffix}"
    old = f"{live}_old_20260101T000000Z"
    ddl = await asyncpg.connect(**target)
    reader = await asyncpg.connect(**target)
    repo = QuestDBRepository()
    repo.fetch = reader.fetch
    repo._open_dedicated_connection = lambda: _async_value(_KeepOpen(ddl))
    script = (
        "import asyncio, os, asyncpg\n"
        "from api.questdb_repository import QuestDBRepository\n"
        "live, staging, old = os.environ['F424_NAMES'].split(',')\n"
        "class Hold:\n"
        "    def __init__(self, conn): self.conn = conn\n"
        "    async def execute(self, q, *a):\n"
        "        r = await self.conn.execute(q, *a)\n"
        "        if q.startswith('RENAME TABLE ' + live + ' TO'):\n"
        "            print('READY', flush=True)\n"
        "            await asyncio.sleep(3600)\n"
        "        return r\n"
        "async def main():\n"
        "    conn = await asyncpg.connect(host=os.environ['QUESTDB_TEST_HOST'],\n"
        "        port=int(os.environ['QUESTDB_TEST_PORT']), user=os.environ['QUESTDB_TEST_USER'],\n"
        "        password=os.environ['QUESTDB_TEST_PASSWORD'],\n"
        "        database=os.getenv('QUESTDB_TEST_DATABASE', 'qdb'))\n"
        "    await QuestDBRepository()._swap_tables(Hold(conn), live, staging, old)\n"
        "asyncio.run(main())\n"
    )
    try:
        await _two_tables(ddl, reader, live, staging)
        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "F424_NAMES": f"{live},{staging},{old}"},
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            line = await asyncio.wait_for(asyncio.to_thread(proc.stdout.readline), 60)
            assert line.strip() == "READY"  # first RENAME applied, second never sent
            proc.kill()  # SIGKILL
        finally:
            proc.kill()
            proc.wait(timeout=30)
        assert not await reader.fetch(
            f"SELECT 1 FROM tables() WHERE table_name = '{live}'"
        )

        await repo._reconcile_tables(live, live)  # what the next refresh does first

        assert (await reader.fetch(f"SELECT count(*) FROM {live}"))[0][0] == 3
    finally:
        await _drop(ddl, live, staging, old)
        for conn in (ddl, reader):
            await conn.close()


class _Fetcher:
    def __init__(self, conn):
        self.fetch = conn.fetch


async def test_production_read_helper_rides_out_a_transient_absence_and_exposes_a_persistent_one():
    import asyncpg

    target = _target()
    suffix = uuid.uuid4().hex[:8]
    live, staging = f"f424_live_{suffix}", f"f424_staging_{suffix}"
    old = f"{live}_old_20260101T000000Z"
    ddl = await asyncpg.connect(**target)
    reader = await asyncpg.connect(**target)
    watcher = await asyncpg.connect(**target)
    repo = QuestDBRepository()
    query = f"SELECT count(*) FROM {live}"
    try:
        await _two_tables(ddl, reader, live, staging)

        # transient: the live name is back before the helper's retry (300 ms) fires
        gated = _GatedConn(ddl, staging)
        swap = asyncio.create_task(repo._swap_tables(gated, live, staging, old))
        await asyncio.wait_for(gated.started.wait(), 10)
        read = asyncio.create_task(fetch_address_clusters(_Fetcher(watcher), query))
        await asyncio.sleep(0.1)
        gated.gate.set()
        await swap
        assert (await read)[0][0] == 5

        # persistent: still absent after the three attempts of the helper
        await ddl.execute(f"RENAME TABLE {live} TO {staging}")  # live absent again
        with pytest.raises(Exception, match="does not exist"):
            await fetch_address_clusters(_Fetcher(watcher), query)
    finally:
        await _drop(ddl, live, staging, old)
        for conn in (ddl, reader, watcher):
            await conn.close()
