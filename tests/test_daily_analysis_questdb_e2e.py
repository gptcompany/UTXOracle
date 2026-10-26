"""F-419: daily_analysis.main() must leave rows in price_analysis AND metrics.

Runs main() in-process against the QuestDB named by QUESTDB_TEST_* (the CI service
container); skipped, without opening any connection, when they are not set. There is no
default host or port, and the live QuestDB (9900/9912/9909) and the host one (9000) are
refused, so a developer machine is never written to by accident.

Fixtures are SYNTHETIC (declared): bitcoind and mempool.space are replaced by a hand-made
price and a 2-transaction list in the mempool.space shape; no recording of real responses
exists in the repo for this path. The code under test (main, save_to_questdb,
save_metrics_to_db, the ILP sender and the QuestDB itself) is real.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
import os
import sys
import types
from pathlib import Path

import pytest

_TARGET_ENV = (
    "QUESTDB_TEST_HOST",
    "QUESTDB_TEST_PORT",
    "QUESTDB_TEST_HTTP_PORT",
    "QUESTDB_TEST_USER",
    "QUESTDB_TEST_PASSWORD",
)
_FORBIDDEN_PORTS = {9000, 9900, 9909, 9912}

SYNTHETIC_TRANSACTIONS = [
    {
        "vin": [{"prevout": {"scriptpubkey_address": "bc1qsynthsender0001"}}],
        "vout": [
            {"scriptpubkey_address": "bc1qsynthreceiver001", "value": 50_000_000},
            {"scriptpubkey_address": "bc1qsynthchange0001", "value": 1_000_000},
        ],
    },
    {
        "vin": [{"prevout": {"scriptpubkey_address": "bc1qsynthsender0002"}}],
        "vout": [{"scriptpubkey_address": "bc1qsynthreceiver002", "value": 10_000_000}],
    },
]


@pytest.fixture(autouse=True)
def _secrets_loader_stub(monkeypatch):
    """daily_analysis imports secrets_loader from a path that exists only on the Dell.

    Stubbed here, scoped to each test, so the result does not depend on test order.
    """
    stub = types.ModuleType("secrets_loader")
    stub.load_secrets = lambda _path=None: False
    monkeypatch.setitem(sys.modules, "secrets_loader", stub)
    # If scripts.daily_analysis was imported earlier (collection, another module) it already
    # holds the REAL load_secrets on a machine that has the loader (the Dell): that one reads
    # the machine's encrypted secrets into os.environ. Replace the bound name too.
    already_imported = sys.modules.get("scripts.daily_analysis")
    if already_imported is not None:
        monkeypatch.setattr(already_imported, "load_secrets", stub.load_secrets)


SCHEDULE_ENV = "UTXORACLE_DAILY_SCHEDULE_UTC"


@pytest.fixture(autouse=True)
def _restore_metrics_repo():
    """monkeypatch leaves bound methods as instance attributes on the shared metrics repo.

    Those would shadow class-level patches of later tests (order dependence): put the
    instance state back after every test.
    """
    import scripts.metrics as metrics

    before = dict(metrics._repo.__dict__)
    # No schedule unless a test sets one. Done without the monkeypatch fixture on purpose:
    # a fixture requesting monkeypatch here would be torn down before it, and the restore
    # of the repository state would run before monkeypatch re-adds its instance attributes.
    saved_schedule = os.environ.pop(SCHEDULE_ENV, None)
    yield
    metrics._repo.__dict__.clear()
    metrics._repo.__dict__.update(before)
    if saved_schedule is not None:
        os.environ[SCHEDULE_ENV] = saved_schedule


def _target() -> dict:
    missing = [name for name in _TARGET_ENV if not os.getenv(name)]
    if missing:
        pytest.skip(
            "explicit QuestDB test target required, not set: " + ", ".join(missing)
        )
    target = {
        "host": os.environ["QUESTDB_TEST_HOST"],
        "port": int(os.environ["QUESTDB_TEST_PORT"]),
        "http_port": int(os.environ["QUESTDB_TEST_HTTP_PORT"]),
        "user": os.environ["QUESTDB_TEST_USER"],
        "password": os.environ["QUESTDB_TEST_PASSWORD"],
        "database": os.getenv("QUESTDB_TEST_DATABASE", "qdb"),
    }
    forbidden = {target["port"]} & _FORBIDDEN_PORTS
    forbidden |= {target["http_port"]} & (_FORBIDDEN_PORTS - {9000})
    if target["http_port"] == 9000 and os.getenv("GITHUB_ACTIONS") != "true":
        forbidden.add(9000)  # the host QuestDB: accepted only on the CI service
    assert not forbidden, (
        f"QUESTDB_TEST_* points at a non-test QuestDB port: {forbidden}"
    )
    return target


def _connect_kwargs(target: dict) -> dict:
    return {
        "host": target["host"],
        "port": target["port"],
        "user": target["user"],
        "password": target["password"],
        "database": target["database"],
    }


async def _count(target: dict, table: str, where: str = "") -> int:
    """Row count; only "table does not exist" counts as 0, every other error is raised."""
    import asyncpg

    conn = await asyncpg.connect(**_connect_kwargs(target))
    try:
        return await conn.fetchval(f"SELECT count() FROM {table} {where}")
    except Exception as exc:
        if "does not exist" in str(exc).lower():  # ILP creates the table on first row
            return 0
        raise
    finally:
        await conn.close()


async def _wait_for_count(target: dict, table: str, where: str, expected: int) -> int:
    """ILP into a WAL table becomes visible asynchronously: poll briefly."""
    seen = -1
    for _ in range(30):
        seen = await _count(target, table, where)
        if seen == expected:
            break
        await asyncio.sleep(1)
    return seen


def _day_start_utc() -> datetime:
    """Row key of a run now: the analysed day, i.e. yesterday (UTC) at 00:00Z."""
    return (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _stub_inputs(monkeypatch, daily, *, dedup_check: bool = False) -> None:
    """Replace only bitcoind, mempool.space and the config checks (synthetic, see header).

    The dedup precheck reads tables() on a real QuestDB: it is stubbed to "all fine" unless
    dedup_check is True (the real-database test and the dedicated precheck tests).
    """
    # Tests that drive main() beyond its head test the machinery as it will work once F-432
    # computes the metrics in the same pass as the price: the fail-closed gate is lifted here
    # and only the tests of the gate itself leave it on.
    monkeypatch.setattr(daily, "HISTORICAL_DAY_IS_STREAMED", False)
    # No .env of the machine running the tests is ever read by the startup guard.
    monkeypatch.setattr(daily, "env_file_path", lambda: Path("/nonexistent/.env"))
    if not dedup_check:
        import api.questdb_repository as repository

        async def deduplicated(tables):
            return []

        async def no_row_yet(tables, day):
            return []

        monkeypatch.setattr(repository, "tables_without_dedup", deduplicated)
        monkeypatch.setattr(repository, "tables_with_day_row", no_row_yet)
    monkeypatch.setattr(daily, "validate_config", lambda config: None)
    monkeypatch.setattr(daily, "WhaleFlowDetector", None)
    monkeypatch.setattr(daily, "ADVANCED_METRICS_ENABLED", False)
    monkeypatch.setattr(
        daily, "fetch_mempool_price_at", lambda timestamp, url: 100_000.0
    )
    monkeypatch.setattr(
        daily,
        "calculate_utxoracle_price",
        lambda config, day=None: {
            "price_usd": 99_500.0,
            "confidence": 0.9,
            "tx_count": 2,
            "fetch_tier": 1,
            "block_height": 900_000,
            "transactions": SYNTHETIC_TRANSACTIONS,
        },
    )
    monkeypatch.setattr(sys, "argv", ["daily_analysis.py"])


def _record_rows(monkeypatch) -> list[tuple[str, object]]:
    import api.questdb_repository as repository

    sent: list[tuple[str, object]] = []

    def record(self, table, symbols, columns, at=None, flush=False):
        sent.append((table, at, columns))
        return True

    monkeypatch.setattr(repository.QuestDBRepository, "_send_row", record)
    return sent


def test_daily_analysis_sends_rows_for_both_tables_without_a_database(monkeypatch):
    """Always runs: the ILP rows main() queues, with no QuestDB involved."""
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)

    daily.main()

    tables = [row[0] for row in sent]
    assert "price_analysis" in tables
    assert "metrics" in tables
    metrics_columns = next(row[2] for row in sent if row[0] == "metrics")
    assert metrics_columns["active_addresses_block"] == 5
    assert metrics_columns["tx_count"] == 2


def test_both_tables_are_keyed_by_the_analysed_day_not_the_run_time(monkeypatch):
    """M1: ts is the analysed day at 00:00Z in both tables, so a rerun upserts the same row."""
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    day = _day_start_utc()

    daily.main()
    daily.main()

    stamps = {(table, at) for table, at, _ in sent}
    assert stamps == {("price_analysis", day), ("metrics", day)}


class _RecordingConnection:
    """The DDL connection: simple protocol only. QuestDB 7.x breaks a connection that runs a
    DDL after an extended-protocol query (asyncpg: 'NoneType' has no attribute 'decode')."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: str, *args) -> None:
        self.statements.append(" ".join(statement.split()))

    async def _extended(self, *args, **kwargs):
        raise AssertionError("the DDL connection received an extended-protocol query")

    fetch = fetchrow = fetchval = _extended

    async def close(self) -> None:
        return None


class _StateConnection:
    """A short-lived read connection answering SELECT ... FROM tables()."""

    def __init__(
        self,
        states: dict[str, tuple[bool, bool]],
        columns: dict[str, set[str]] | None = None,
    ) -> None:
        self.states = states
        self.columns = columns or {}
        self.closed = False

    async def fetch(self, query: str, *args):
        assert "table_columns" in query
        table = query.split("table_columns('")[1].split("'")[0]
        return [{"column": name} for name in self.columns.get(table, set())]

    async def fetchrow(self, query: str, table: str):
        assert "tables()" in query
        if table not in self.states:
            return None
        wal, dedup = self.states[table]
        return {"walEnabled": wal, "dedup": dedup}

    async def close(self) -> None:
        self.closed = True


def _fake_questdb(
    monkeypatch, states=None, ddl=None, *, ddl_via_connect=True, columns=None
):
    """asyncpg stand-in. With ddl_via_connect the first connection is the DDL one; every other
    connection (or all, when the caller holds the DDL connection itself) is a state read."""
    import types as _types

    import api.questdb_repository as repository

    ddl = ddl or _RecordingConnection()
    reads: list[_StateConnection] = []
    pending_ddl = [ddl_via_connect]

    async def connect(**kwargs):
        if pending_ddl[0]:
            pending_ddl[0] = False
            return ddl
        conn = _StateConnection(states or {}, columns)
        reads.append(conn)
        return conn

    monkeypatch.setattr(repository, "asyncpg", _types.SimpleNamespace(connect=connect))
    return ddl, reads


def test_ddl_dedups_price_analysis_and_metrics_on_ts(monkeypatch):
    """M1: the schema makes the daily rerun idempotent (WAL table + DEDUP UPSERT KEYS(ts))."""
    import api.questdb_repository as repository

    states = {"price_analysis": (True, False), "metrics": (True, False)}
    conn, reads = _fake_questdb(monkeypatch, states)
    asyncio.run(repository.create_tables_if_not_exist())

    for table in ("price_analysis", "metrics"):
        create = next(
            s for s in conn.statements if f"CREATE TABLE IF NOT EXISTS {table} (" in s
        )
        assert "WAL" in create and "DEDUP UPSERT KEYS(ts)" in create, table
        # A WAL table without dedup gets it enabled; a schema conversion is never run.
        assert f"ALTER TABLE {table} DEDUP ENABLE UPSERT KEYS(ts)" in conn.statements
        assert f"ALTER TABLE {table} SET TYPE WAL" not in conn.statements
    # the state was read on connections of their own, all closed
    assert reads and all(c.closed for c in reads)


def test_count_treats_only_a_missing_table_as_zero(monkeypatch):
    """M3: a connection or any other error must surface, not read as an empty table."""
    import asyncpg

    class _Conn:
        def __init__(self, error: Exception) -> None:
            self.error = error

        async def fetchval(self, query):
            raise self.error

        async def close(self) -> None:
            return None

    target = {"host": "h", "port": 1, "user": "u", "password": "p", "database": "d"}

    def fake(error: Exception):
        async def connect(**kwargs):
            return _Conn(error)

        return connect

    monkeypatch.setattr(
        asyncpg, "connect", fake(RuntimeError("table does not exist [name=t]"))
    )
    assert asyncio.run(_count(target, "t")) == 0

    monkeypatch.setattr(asyncpg, "connect", fake(RuntimeError("permission denied")))
    with pytest.raises(RuntimeError, match="permission denied"):
        asyncio.run(_count(target, "t"))

    async def refused(**kwargs):
        raise ConnectionRefusedError("down")

    monkeypatch.setattr(asyncpg, "connect", refused)
    with pytest.raises(ConnectionRefusedError):
        asyncio.run(_count(target, "t"))


def test_daily_analysis_is_idempotent_on_a_real_questdb(monkeypatch):
    """M1 + M3: two runs on the same day leave ONE row per table; an unreachable target fails."""
    target = _target()  # skips only when QUESTDB_TEST_* are not set

    import api.questdb_repository as repository
    import scripts.daily_analysis as daily
    import scripts.metrics as metrics

    # Point both ILP writers (price_analysis via a new repository, metrics via the module
    # singleton) and the schema creation at the test target.
    monkeypatch.setattr(repository, "QUESTDB_HTTP_HOST", target["host"])
    monkeypatch.setattr(repository, "QUESTDB_HTTP_PORT", target["http_port"])
    for name, key in (
        ("QUESTDB_PG_HOST", "host"),
        ("QUESTDB_PG_PORT", "port"),
        ("QUESTDB_PG_USER", "user"),
        ("QUESTDB_PG_PASSWORD", "password"),
        ("QUESTDB_PG_DATABASE", "database"),
    ):
        monkeypatch.setattr(repository, name, target[key])

    # Fails (not skips) when the target is configured but down: an unreachable QuestDB must
    # not turn the gate green.
    asyncio.run(repository.create_tables_if_not_exist())

    _stub_inputs(monkeypatch, daily, dedup_check=True)
    daily.main()
    daily.main()

    where = f"WHERE ts = '{_day_start_utc().strftime('%Y-%m-%dT%H:%M:%S.%fZ')}'"
    for table in ("price_analysis", "metrics"):
        rows = asyncio.run(_wait_for_count(target, table, where, expected=1))
        assert rows == 1, f"{table}: {rows} rows for the analysed day after two runs"


def _set_destination(monkeypatch, *, http=("127.0.0.1", 9900), pg=("127.0.0.1", 9912)):
    import api.questdb_repository as repository

    monkeypatch.setattr(repository, "QUESTDB_HTTP_HOST", http[0])
    monkeypatch.setattr(repository, "QUESTDB_HTTP_PORT", http[1])
    monkeypatch.setattr(repository, "QUESTDB_PG_HOST", pg[0])
    monkeypatch.setattr(repository, "QUESTDB_PG_PORT", pg[1])


def _expect_destination(monkeypatch, *, http_port="9900", pg_port="9912"):
    monkeypatch.setenv("UTXORACLE_EXPECTED_QUESTDB_HTTP_HOST", "127.0.0.1")
    monkeypatch.setenv("UTXORACLE_EXPECTED_QUESTDB_HTTP_PORT", http_port)
    monkeypatch.setenv("UTXORACLE_EXPECTED_QUESTDB_PG_HOST", "127.0.0.1")
    monkeypatch.setenv("UTXORACLE_EXPECTED_QUESTDB_PG_PORT", pg_port)


def test_destination_mismatch_exits_before_any_write(monkeypatch, caplog):
    """M2: a wrong QuestDB (e.g. an override after load_secrets) must not receive rows."""
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _set_destination(
        monkeypatch, http=("127.0.0.1", 9000)
    )  # the host QuestDB, not the live
    _expect_destination(monkeypatch)

    with caplog.at_level("ERROR"), pytest.raises(SystemExit) as stop:
        daily.main()

    assert stop.value.code == 3
    assert sent == []
    assert "QuestDB destination mismatch" in caplog.text
    assert "9000" in caplog.text and "9900" in caplog.text


def test_destination_match_proceeds_and_logs_the_effective_target(monkeypatch, caplog):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _set_destination(monkeypatch)
    _expect_destination(monkeypatch)

    with caplog.at_level("INFO"):
        daily.main()

    assert {row[0] for row in sent} == {"price_analysis", "metrics"}
    assert (
        "QuestDB destination: ILP/HTTP 127.0.0.1:9900, PG 127.0.0.1:9912" in caplog.text
    )


def test_destination_without_expectation_logs_and_does_not_fail(monkeypatch, caplog):
    """Manual use and tests set no expectation: log the target, do not block."""
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _set_destination(monkeypatch, http=("db.invalid", 1111), pg=("db.invalid", 2222))
    for name in (
        "UTXORACLE_EXPECTED_QUESTDB_HTTP_HOST",
        "UTXORACLE_EXPECTED_QUESTDB_HTTP_PORT",
        "UTXORACLE_EXPECTED_QUESTDB_PG_HOST",
        "UTXORACLE_EXPECTED_QUESTDB_PG_PORT",
    ):
        monkeypatch.delenv(name, raising=False)

    with caplog.at_level("INFO"):
        daily.main()

    assert sent
    assert "no expected destination set" in caplog.text
    assert "ILP/HTTP db.invalid:1111" in caplog.text


# --- Write failures must end the process with a non-zero exit (F-419 audit) -------------


class _FlakySender:
    """ILP sender stand-in: rows are accepted, flush fails (broken connection)."""

    def row(self, *args, **kwargs) -> None:
        return None

    def flush(self) -> None:
        raise ConnectionResetError("flush failed (test)")

    def close(self) -> None:
        return None


def _exit_code(daily) -> int:
    with pytest.raises(SystemExit) as stop:
        daily.main()
    return stop.value.code


def test_price_analysis_row_refused_by_ilp_exits_non_zero(monkeypatch):
    """_send_row answers False on ILP errors; save_to_questdb used to ignore it."""
    import api.questdb_repository as repository
    import scripts.daily_analysis as daily
    import scripts.metrics as metrics

    monkeypatch.setattr(
        repository.QuestDBRepository, "_send_row", lambda self, *a, **k: False
    )
    # Isolate the first table: the metrics writer would succeed.
    monkeypatch.setattr(metrics._repo, "_send_row", lambda *a, **k: True)
    _stub_inputs(monkeypatch, daily)

    assert _exit_code(daily) == 2


def test_failed_flush_exits_non_zero_for_the_first_table(monkeypatch):
    import api.questdb_repository as repository
    import scripts.daily_analysis as daily
    import scripts.metrics as metrics

    monkeypatch.setattr(
        repository.QuestDBRepository, "_build_sender", lambda self: _FlakySender()
    )
    monkeypatch.setattr(metrics._repo, "_send_row", lambda *a, **k: True)
    _stub_inputs(monkeypatch, daily)

    assert _exit_code(daily) == 2


def test_metrics_row_refused_exits_non_zero(monkeypatch):
    import scripts.daily_analysis as daily
    import scripts.metrics as metrics

    _record_rows(monkeypatch)  # price_analysis succeeds
    monkeypatch.setattr(metrics._repo, "_send_row", lambda *a, **k: False)
    _stub_inputs(monkeypatch, daily)

    assert _exit_code(daily) == 2


def test_metrics_write_raising_exits_non_zero(monkeypatch):
    import scripts.daily_analysis as daily
    import scripts.metrics as metrics

    def boom(*args, **kwargs):
        raise ConnectionResetError("ilp down (test)")

    _record_rows(monkeypatch)
    monkeypatch.setattr(metrics._repo, "_send_row", boom)
    _stub_inputs(monkeypatch, daily)

    assert _exit_code(daily) == 2


def test_metrics_failed_flush_exits_non_zero(monkeypatch):
    import scripts.daily_analysis as daily
    import scripts.metrics as metrics

    # price_analysis succeeds; the real _send_row of the metrics repository meets a failing flush
    monkeypatch.setattr(daily, "save_to_questdb", lambda data: None)
    monkeypatch.setattr(metrics._repo, "_build_sender", lambda: _FlakySender())
    monkeypatch.setattr(metrics._repo, "sender", None)
    _stub_inputs(monkeypatch, daily)

    assert _exit_code(daily) == 2


# --- Schema migration: decided from tables(), never from an error message ---------------


class _AlterFails(_RecordingConnection):
    async def execute(self, statement: str, *args) -> None:
        if "DEDUP ENABLE" in statement:
            raise RuntimeError("alter failed (test)")
        await super().execute(statement, *args)


def _enable(monkeypatch, states, ddl=None, table: str = "price_analysis"):
    import api.questdb_repository as repository

    conn, reads = _fake_questdb(monkeypatch, states, ddl, ddl_via_connect=False)
    asyncio.run(repository._enable_daily_dedup(conn, table))
    return conn, reads


def test_dedup_already_active_is_info_and_runs_no_alter(monkeypatch, caplog):
    with caplog.at_level("INFO"):
        conn, _ = _enable(monkeypatch, {"price_analysis": (True, True)})

    assert conn.statements == []
    assert any(
        r.levelname == "INFO" and "price_analysis" in r.getMessage()
        for r in caplog.records
    )


def test_wal_table_without_dedup_gets_the_alter_and_its_failure_is_fatal(monkeypatch):
    conn, reads = _enable(monkeypatch, {"price_analysis": (True, False)})
    assert conn.statements == [
        "ALTER TABLE price_analysis DEDUP ENABLE UPSERT KEYS(ts)"
    ]
    assert reads and all(c.closed for c in reads)

    with pytest.raises(RuntimeError, match="alter failed"):
        _enable(monkeypatch, {"price_analysis": (True, False)}, ddl=_AlterFails())


def test_non_wal_table_is_an_error_log_without_alter_and_without_exception(
    monkeypatch, caplog
):
    with caplog.at_level("ERROR"):
        conn, _ = _enable(monkeypatch, {"metrics": (False, False)}, table="metrics")

    assert conn.statements == []  # no SET TYPE WAL: a conversion is not a startup step
    assert any(
        r.levelname == "ERROR"
        and "metrics" in r.getMessage()
        and "dedup non attivabile: tabella non WAL" in r.getMessage()
        for r in caplog.records
    )


def test_the_ddl_connection_never_runs_an_extended_protocol_query(monkeypatch):
    """QuestDB 7.x: a fetch on the DDL connection breaks the next DDL. Reads go elsewhere."""
    conn, _ = _enable(monkeypatch, {"price_analysis": (True, False)})

    with pytest.raises(AssertionError, match="extended-protocol"):
        asyncio.run(conn.fetchrow("SELECT 1"))  # the guard itself works
    assert conn.statements  # and the migration ran without tripping it


# --- The daily job refuses to write into a table without dedup -------------------------


def test_tables_without_dedup_reads_tables_and_reports_the_ones_not_deduplicating(
    monkeypatch,
):
    import types as _types

    import api.questdb_repository as repository

    conn = _StateConnection({"price_analysis": (True, True), "metrics": (True, False)})

    async def connect(**kwargs):
        return conn

    monkeypatch.setattr(repository, "asyncpg", _types.SimpleNamespace(connect=connect))

    missing = asyncio.run(
        repository.tables_without_dedup(("price_analysis", "metrics", "absent"))
    )

    assert missing == ["metrics", "absent"]


def test_write_is_refused_when_a_table_has_no_dedup(monkeypatch, caplog):
    import api.questdb_repository as repository
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily, dedup_check=True)

    async def without_dedup(tables):
        return ["metrics"]

    monkeypatch.setattr(repository, "tables_without_dedup", without_dedup)

    with caplog.at_level("ERROR"), pytest.raises(SystemExit) as stop:
        daily.main()

    assert stop.value.code == 4
    assert sent == []
    assert "without dedup" in caplog.text and "metrics" in caplog.text


# --- Complete rows only: a failed metrics block writes nothing -------------------------


def test_failed_metrics_block_writes_nothing_and_exits_non_zero(monkeypatch, caplog):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)

    def boom(**kwargs):
        raise ValueError("active addresses broke (test)")

    monkeypatch.setattr(daily, "count_active_addresses", boom)

    with caplog.at_level("ERROR"):
        assert _exit_code(daily) == 2

    assert sent == []  # not even price_analysis: no half-written day
    assert "active_addresses" in caplog.text


def test_price_row_with_a_missing_value_is_not_written(monkeypatch, caplog):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    monkeypatch.setattr(
        daily,
        "compare_prices",
        lambda utx_price, mem_price: {"diff_amount": None, "diff_percent": 0.5},
    )

    with caplog.at_level("ERROR"):
        assert _exit_code(daily) == 2

    assert sent == []
    assert "diff_amount" in caplog.text


def test_calculate_utxoracle_price_hands_the_transactions_to_the_metrics(monkeypatch):
    """Without them active_addresses and tx_volume were never computed in production."""
    import scripts.daily_analysis as daily

    class _Calculator:
        def calculate_price_for_transactions(self, transactions):
            return {"price_usd": 99_500.0, "confidence": 0.9, "tx_count": 1500}

    monkeypatch.setattr(
        daily,
        "fetch_bitcoin_transactions",
        lambda config: (SYNTHETIC_TRANSACTIONS, 1),
    )
    monkeypatch.setattr(daily, "UTXOracleCalculator", _Calculator)

    result = daily.calculate_utxoracle_price({})

    assert result["transactions"] is SYNTHETIC_TRANSACTIONS


# --- First successful run of the day wins ----------------------------------------------


def _existing_rows(monkeypatch, tables: list[str]) -> list[tuple]:
    import api.questdb_repository as repository

    asked: list[tuple] = []

    async def existing(candidates, day):
        asked.append((tuple(candidates), day))
        return [t for t in candidates if t in tables]

    monkeypatch.setattr(repository, "tables_with_day_row", existing)
    return asked


def test_rerun_with_the_day_already_written_skips_with_info_and_exit_zero(
    monkeypatch, caplog
):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    asked = _existing_rows(monkeypatch, ["price_analysis", "metrics"])

    with caplog.at_level("INFO"):
        daily.main()  # returns normally: exit code 0

    assert sent == []
    assert asked and asked[0][1] == _day_start_utc()
    assert any(
        r.levelname == "INFO" and "already" in r.getMessage() for r in caplog.records
    )


def test_overwrite_writes_again_and_warns(monkeypatch, caplog):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _existing_rows(monkeypatch, ["price_analysis", "metrics"])
    monkeypatch.setattr(sys, "argv", ["daily_analysis.py", "--overwrite"])

    with caplog.at_level("WARNING"):
        daily.main()

    assert {row[0] for row in sent} == {"price_analysis", "metrics"}
    assert any(
        r.levelname == "WARNING" and "--overwrite" in r.getMessage()
        for r in caplog.records
    )


def test_tables_with_day_row_reports_the_tables_holding_the_day(monkeypatch):
    import types as _types

    import api.questdb_repository as repository

    class _Conn:
        async def fetchval(self, query):
            assert "2026-10-26T00:00:00.000000Z" in query
            return 1 if "price_analysis" in query else 0

        async def close(self) -> None:
            return None

    async def connect(**kwargs):
        return _Conn()

    monkeypatch.setattr(repository, "asyncpg", _types.SimpleNamespace(connect=connect))
    day = datetime(2026, 10, 26, tzinfo=timezone.utc)

    found = asyncio.run(
        repository.tables_with_day_row(("price_analysis", "metrics"), day)
    )

    assert found == ["price_analysis"]


# --- Row key = the analysed day (D-1 for the 01:30Z timer), clock injectable -------------


def test_analysis_day_is_yesterday_at_midnight_utc_for_any_time_of_the_run_day():
    import scripts.daily_analysis as daily

    expected = datetime(2026, 10, 26, tzinfo=timezone.utc)
    for run in (
        datetime(2026, 10, 27, 0, 0, 30, tzinfo=timezone.utc),  # just after midnight
        datetime(2026, 10, 27, 1, 30, tzinfo=timezone.utc),  # the timer
        datetime(2026, 10, 27, 23, 59, tzinfo=timezone.utc),  # just before midnight
        datetime(2026, 10, 27, 8, 30, tzinfo=timezone(timedelta(hours=7))),  # = 01:30Z
    ):
        assert daily.analysis_day_for(run) == expected, run
    assert daily.analysis_day_for(
        datetime(2026, 10, 28, 0, 0, 0, tzinfo=timezone.utc)
    ) == datetime(2026, 10, 27, tzinfo=timezone.utc)


def test_main_keys_both_rows_with_the_day_before_the_injected_run_time(monkeypatch):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    monkeypatch.setattr(
        daily, "utc_now", lambda: datetime(2026, 10, 27, 1, 30, tzinfo=timezone.utc)
    )

    daily.main()

    day = datetime(2026, 10, 26, tzinfo=timezone.utc)
    assert {(table, at) for table, at, _ in sent} == {
        ("price_analysis", day),
        ("metrics", day),
    }


# --- Every non-zero exit goes through the same path (log ERROR, then the code) -----------


def test_unreachable_questdb_in_the_dedup_check_is_an_error_exit_not_a_traceback(
    monkeypatch, caplog
):
    import api.questdb_repository as repository
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily, dedup_check=True)

    async def down(tables):
        raise ConnectionRefusedError("questdb down (test)")

    monkeypatch.setattr(repository, "tables_without_dedup", down)

    with caplog.at_level("ERROR"):
        assert _exit_code(daily) == 2

    assert sent == []
    assert "questdb down (test)" in caplog.text


def test_unreachable_questdb_in_the_day_row_check_is_an_error_exit(monkeypatch, caplog):
    import api.questdb_repository as repository
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)

    async def down(tables, day):
        raise ConnectionRefusedError("questdb down (test)")

    monkeypatch.setattr(repository, "tables_with_day_row", down)

    with caplog.at_level("ERROR"):
        assert _exit_code(daily) == 2

    assert sent == []
    assert "questdb down (test)" in caplog.text


def test_destination_and_dedup_exits_keep_their_codes_and_log_the_cause(
    monkeypatch, caplog
):
    import api.questdb_repository as repository
    import scripts.daily_analysis as daily

    _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily, dedup_check=True)
    _set_destination(monkeypatch, http=("127.0.0.1", 9000))
    _expect_destination(monkeypatch)
    with caplog.at_level("ERROR"):
        assert _exit_code(daily) == 3
    assert "QuestDB destination mismatch" in caplog.text

    caplog.clear()
    _set_destination(monkeypatch)

    async def without_dedup(tables):
        return ["metrics"]

    monkeypatch.setattr(repository, "tables_without_dedup", without_dedup)
    with caplog.at_level("ERROR"):
        assert _exit_code(daily) == 4
    assert "without dedup" in caplog.text


# --- Every persisted metrics block: a failure writes nothing, names the block ------------


class _FakeWhaleSignal:
    net_flow_btc = 12.0
    direction = "OUTFLOW"
    confidence = 0.8


class _FakeWhaleDetector:
    def __init__(self, csv_path) -> None:
        self.csv_path = csv_path

    def get_exchange_address_count(self) -> int:
        return 1

    async def analyze_latest_block(self):
        return _FakeWhaleSignal()


def _enable_all_persisted_blocks(monkeypatch, daily, tmp_path) -> None:
    """Whale signal (monte_carlo) and Wasserstein switched on, with enough synthetic outputs."""
    csv = tmp_path / "exchange.csv"
    csv.write_text("address\\n")
    real_load = daily.load_config
    monkeypatch.setattr(
        daily,
        "load_config",
        lambda: {**real_load(), "EXCHANGE_ADDRESSES_CSV": str(csv)},
    )
    monkeypatch.setattr(daily, "WhaleFlowDetector", _FakeWhaleDetector)
    monkeypatch.setattr(daily, "ADVANCED_METRICS_ENABLED", True)
    monkeypatch.setattr(daily, "WASSERSTEIN_ENABLED", True)
    many = [
        {
            "vin": [{"prevout": {"scriptpubkey_address": f"bc1qsender{i}"}}],
            "vout": [
                {"scriptpubkey_address": f"bc1qreceiver{i}", "value": 0.01 + i / 1e5}
            ],
        }
        for i in range(300)
    ]
    monkeypatch.setattr(
        daily,
        "calculate_utxoracle_price",
        lambda config, day=None: {
            "price_usd": 99_500.0,
            "confidence": 0.9,
            "tx_count": 300,
            "fetch_tier": 1,
            "transactions": many,
        },
    )
    # The other advanced analytics are not under test here; keep them light.
    ns = types.SimpleNamespace
    monkeypatch.setattr(
        daily,
        "power_law_fit",
        lambda v: ns(tau=2.0, regime="x", power_law_vote=0.0, is_valid=True),
    )
    monkeypatch.setattr(
        daily,
        "fractal_analyze",
        lambda v: ns(dimension=1.0, structure="x", fractal_vote=0.0, is_valid=True),
    )
    monkeypatch.setattr(
        daily,
        "symbolic_analyze",
        lambda v, order=5: ns(
            permutation_entropy=1.0,
            pattern_type="x",
            symbolic_vote=0.0,
            is_valid=True,
        ),
    )
    # No derivatives database, no SOPR: nothing outside the process may be read.
    monkeypatch.setattr(daily, "DERIVATIVES_ENABLED", False)
    monkeypatch.setattr(daily, "SOPR_ENABLED", False)


def _ok_wasserstein(**kwargs):
    import types as _t

    return _t.SimpleNamespace(
        is_valid=True,
        wasserstein_vote=0.0,
        mean_distance=0.1,
        regime_status="normal",
        to_dict=lambda: {"mean_distance": 0.1},
    )


@pytest.mark.parametrize(
    "block, target",
    [
        ("monte_carlo", "monte_carlo_fusion"),
        ("active_addresses", "count_active_addresses"),
        ("tx_volume", "calculate_tx_volume"),
        ("wasserstein", "rolling_wasserstein"),
    ],
)
def test_each_persisted_metrics_block_that_raises_writes_nothing(
    monkeypatch, tmp_path, caplog, block, target
):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _enable_all_persisted_blocks(monkeypatch, daily, tmp_path)

    def boom(*args, **kwargs):
        raise ValueError(f"{block} broke (test)")

    # the other blocks succeed so that only the one under test is at fault
    if target != "rolling_wasserstein":
        monkeypatch.setattr(daily, "rolling_wasserstein", _ok_wasserstein)
    monkeypatch.setattr(daily, target, boom)

    with caplog.at_level("ERROR"):
        assert _exit_code(daily) == 2

    assert sent == []
    assert any(
        r.levelname == "ERROR" and f"Metrics block {block} failed" in r.getMessage()
        for r in caplog.records
    )


def test_all_persisted_blocks_succeeding_still_writes_both_tables(
    monkeypatch, tmp_path
):
    """Guard for the parametrized test above: its setup, without a failure, writes."""
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _enable_all_persisted_blocks(monkeypatch, daily, tmp_path)
    monkeypatch.setattr(daily, "rolling_wasserstein", _ok_wasserstein)

    daily.main()

    assert {row[0] for row in sent} == {"price_analysis", "metrics"}
    metrics_columns = next(row[2] for row in sent if row[0] == "metrics")
    assert metrics_columns["wasserstein_distance"] == 0.1


# --- tx_volume units: sat -> BTC happens once, at the source (tiers 1 and 2) -------------
#
# Tiers 1 and 2 fetch satoshi from the APIs and _convert_satoshi_to_btc turns vout["value"]
# into BTC in place; tx_volume must therefore be told the values are BTC, not divide again.


def _block_of_txs(half_btc_in_sat: int = 50_000_000, n: int = 1000) -> list[dict]:
    """n transactions; one pays 0.5 BTC (in satoshi, as the APIs return it), the rest 0."""
    txs = [
        {
            "txid": f"{i:064x}",
            "vin": [{"prevout": {"scriptpubkey_address": f"bc1qin{i}"}}],
            "vout": [{"scriptpubkey_address": f"bc1qout{i}", "value": 0}],
        }
        for i in range(n)
    ]
    txs[0]["vout"][0]["value"] = half_btc_in_sat
    return txs


class _Response:
    def __init__(self, payload, text: str = "") -> None:
        self._payload = payload
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def _fake_requests_tier1(monkeypatch, daily, txs) -> None:
    by_id = {tx["txid"]: tx for tx in txs}

    def get(url, timeout=None):
        if url.endswith("/blocks/tip/hash"):
            return _Response(None, text='"' + "ab" * 32 + '"')
        if url.endswith("/txids"):
            return _Response(list(by_id))
        return _Response(by_id[url.rsplit("/", 1)[1]])

    monkeypatch.setattr(daily.requests, "get", get)


def _fake_requests_tier2(monkeypatch, daily, txs) -> None:
    def get(url, timeout=None):
        if "localhost:3002" in url:
            raise daily.requests.exceptions.ConnectionError("tier 1 down (test)")
        if url.endswith("/api/blocks/tip/hash"):
            return _Response(None, text="cd" * 32)
        if url.endswith(("cd" * 32)):
            return _Response({"tx_count": len(txs)})
        start = int(url.rsplit("/", 1)[1])
        return _Response(txs[start : start + 25])

    monkeypatch.setattr(daily.requests, "get", get)


def _tx_volume_btc_written_by_main(monkeypatch, daily, tier_setup, txs, tier) -> float:
    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    tier_setup(monkeypatch, daily, txs)
    config = {
        "MEMPOOL_API_URL": "http://localhost:8999",
        "MEMPOOL_FALLBACK_ENABLED": True,
        "MEMPOOL_FALLBACK_URL": "https://mempool.invalid",
    }

    def calculate(_config, day=None):
        fetched, used_tier = daily.fetch_bitcoin_transactions(config)
        assert used_tier == tier
        return {
            "price_usd": 100_000.0,
            "confidence": 0.9,
            "tx_count": len(fetched),
            "fetch_tier": used_tier,
            "transactions": fetched,
        }

    monkeypatch.setattr(daily, "calculate_utxoracle_price", calculate)

    daily.main()

    return next(row[2] for row in sent if row[0] == "metrics")["tx_volume_btc"]


def test_tier1_half_a_bitcoin_output_is_half_a_bitcoin_of_volume(monkeypatch):
    import scripts.daily_analysis as daily

    volume = _tx_volume_btc_written_by_main(
        monkeypatch, daily, _fake_requests_tier1, _block_of_txs(), tier=1
    )

    assert volume == pytest.approx(0.5)


def test_tier2_half_a_bitcoin_output_is_half_a_bitcoin_of_volume(monkeypatch):
    import scripts.daily_analysis as daily

    volume = _tx_volume_btc_written_by_main(
        monkeypatch, daily, _fake_requests_tier2, _block_of_txs(), tier=2
    )

    assert volume == pytest.approx(0.5)


def test_tx_volume_units_are_explicit_and_validated():
    from scripts.metrics.tx_volume import calculate_tx_volume, estimate_real_volume

    sat_tx = {"vout": [{"value": 50_000_000}]}
    btc_tx = {"vout": [{"value": 0.5}]}

    assert estimate_real_volume(sat_tx) == pytest.approx(0.5)  # default: satoshi
    assert estimate_real_volume(btc_tx, value_unit="btc") == pytest.approx(0.5)
    assert calculate_tx_volume(
        [btc_tx], utxoracle_price=100_000.0, confidence=0.9, value_unit="btc"
    ).tx_volume_usd == pytest.approx(50_000.0)
    with pytest.raises(ValueError, match="value_unit"):
        estimate_real_volume(btc_tx, value_unit="msat")


def test_failure_before_the_wasserstein_block_runs_still_fails_the_block(
    monkeypatch, tmp_path, caplog
):
    """Input extraction for the advanced analytics broke: Wasserstein never ran, so no write."""
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _enable_all_persisted_blocks(monkeypatch, daily, tmp_path)
    monkeypatch.setattr(daily, "rolling_wasserstein", _ok_wasserstein)
    broken = [{"vin": [], "vout": [{"value": None}]}] + SYNTHETIC_TRANSACTIONS
    monkeypatch.setattr(
        daily,
        "calculate_utxoracle_price",
        lambda config, day=None: {
            "price_usd": 99_500.0,
            "confidence": 0.9,
            "tx_count": 3,
            "fetch_tier": 1,
            "transactions": broken,
        },
    )

    with caplog.at_level("ERROR"):
        assert _exit_code(daily) == 2

    assert sent == []
    assert "Metrics block wasserstein failed" in caplog.text


# --- Run window: a late catch-up must not label the wrong day ------------------------------


def _run_at(monkeypatch, daily, when: datetime) -> None:
    monkeypatch.setattr(daily, "utc_now", lambda: when)


def test_run_inside_the_window_writes_with_the_analysed_day(monkeypatch):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    monkeypatch.setenv(SCHEDULE_ENV, "01:30")
    for when in (
        datetime(2026, 10, 27, 1, 30, 0, tzinfo=timezone.utc),  # the scheduled time
        datetime(2026, 10, 27, 3, 0, tzinfo=timezone.utc),  # a late catch-up, same day
        datetime(2026, 10, 27, 23, 59, 59, tzinfo=timezone.utc),  # last second
    ):
        sent.clear()
        _run_at(monkeypatch, daily, when)
        daily.main()
        assert {row[0] for row in sent} == {"price_analysis", "metrics"}, when
        assert {row[1] for row in sent} == {datetime(2026, 10, 26, tzinfo=timezone.utc)}


@pytest.mark.parametrize(
    "when",
    [
        datetime(2026, 10, 28, 0, 10, tzinfo=timezone.utc),  # catch-up after midnight
        datetime(2026, 10, 27, 1, 29, 59, tzinfo=timezone.utc),  # one second early
    ],
)
def test_run_outside_the_window_exits_5_and_writes_nothing(monkeypatch, caplog, when):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    monkeypatch.setenv(SCHEDULE_ENV, "01:30")
    _run_at(monkeypatch, daily, when)

    with caplog.at_level("ERROR"):
        assert _exit_code(daily) == 5

    assert sent == []
    assert "run fuori finestra" in caplog.text


def test_without_the_schedule_variable_the_window_is_not_checked(monkeypatch, caplog):
    """Manual use: no schedule known, so no block; the run is logged as unchecked."""
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _run_at(monkeypatch, daily, datetime(2026, 10, 28, 0, 10, tzinfo=timezone.utc))

    with caplog.at_level("INFO"):
        daily.main()

    assert {row[0] for row in sent} == {"price_analysis", "metrics"}
    assert "run window not checked" in caplog.text


def test_invalid_schedule_value_is_an_error_exit(monkeypatch, caplog):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    monkeypatch.setenv(SCHEDULE_ENV, "25:99")

    with caplog.at_level("ERROR"):
        assert _exit_code(daily) == 2

    assert sent == []
    assert SCHEDULE_ENV in caplog.text


# --- The skip needs BOTH rows of the day ---------------------------------------------------


def test_only_one_row_present_rewrites_both_with_a_warning(monkeypatch, caplog):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _existing_rows(monkeypatch, ["price_analysis"])

    with caplog.at_level("WARNING"):
        daily.main()

    assert {row[0] for row in sent} == {"price_analysis", "metrics"}
    assert any(
        r.levelname == "WARNING" and "only one" in r.getMessage()
        for r in caplog.records
    )


# --- .env must not redefine the destination (exit 3, key NAMES only) ----------------------

SECRET_LOOKING_VALUE = "value-that-must-never-be-logged-4711"


def _env_file(monkeypatch, daily, tmp_path, content: str | None) -> None:
    path = tmp_path / ".env"
    if content is not None:
        path.write_text(content)
    monkeypatch.setattr(daily, "env_file_path", lambda: path)


@pytest.mark.parametrize(
    "key",
    ["QUESTDB_HTTP_PORT", "QUESTDB_PG_HOST", "UTXORACLE_EXPECTED_QUESTDB_PG_PORT"],
)
def test_env_file_defining_the_destination_exits_3_naming_only_the_keys(
    monkeypatch, tmp_path, caplog, key
):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _env_file(
        monkeypatch,
        daily,
        tmp_path,
        f"HARMLESS=1\n{key}={SECRET_LOOKING_VALUE}\nEXPORTED=also\n",
    )

    with caplog.at_level("INFO"):
        assert _exit_code(daily) == 3

    assert sent == []
    assert key in caplog.text
    assert "HARMLESS" not in caplog.text
    assert SECRET_LOOKING_VALUE not in caplog.text


def test_env_file_lists_every_offending_key_sorted(monkeypatch, tmp_path, caplog):
    import scripts.daily_analysis as daily

    _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _env_file(
        monkeypatch,
        daily,
        tmp_path,
        f"QUESTDB_PG_PORT={SECRET_LOOKING_VALUE}\nUTXORACLE_EXPECTED_X=1\nQUESTDB_HTTP_HOST=2\n",
    )

    with caplog.at_level("ERROR"):
        assert _exit_code(daily) == 3

    assert "QUESTDB_HTTP_HOST, QUESTDB_PG_PORT, UTXORACLE_EXPECTED_X" in caplog.text
    assert SECRET_LOOKING_VALUE not in caplog.text


def test_clean_env_file_does_not_block(monkeypatch, tmp_path):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _env_file(
        monkeypatch, daily, tmp_path, "BITCOIN_DATADIR=/somewhere\nLOG_LEVEL=INFO\n"
    )

    daily.main()

    assert {row[0] for row in sent} == {"price_analysis", "metrics"}


def test_missing_env_file_is_info_and_does_not_block(monkeypatch, tmp_path, caplog):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _env_file(monkeypatch, daily, tmp_path, None)

    with caplog.at_level("INFO"):
        daily.main()

    assert sent
    assert any(
        r.levelname == "INFO"
        and ".env" in r.getMessage()
        and "not found" in r.getMessage()
        for r in caplog.records
    )


# --- F-438: the analysed day is defined by block timestamps, not by the run time ---------
#
# SYNTHETIC chain (declared): the FakeChain of test_historical_block_selection (a fake
# rpc_client, mediantime monotone, 144 blocks for D = 2026-10-26, heights 500..643). The price
# library is replaced by a spy that records which transactions it received. A streamed day
# cannot feed the spec-007 metrics (same pass: F-432), so the tests that look at the row use
# --dry-run with the metrics modules off; the guard tests run the real flow.

from tests.test_historical_block_selection import FIRST as CHAIN_FIRST  # noqa: E402
from tests.test_historical_block_selection import FakeChain  # noqa: E402

DAY = datetime(2026, 10, 26, tzinfo=timezone.utc)  # D: the analysed day


class _MempoolShapedChain(FakeChain):
    """Same chain, transactions in the shape the metrics read (mempool.space/electrs)."""

    def call(self, method, params=None):
        out = super().call(method, params)
        if method == "getblock":
            for tx in out["tx"]:
                tx["vin"] = [{"prevout": {"scriptpubkey_address": "bc1qin"}}]
                tx["vout"] = [{"scriptpubkey_address": "bc1qout", "value": 0.5}]
        return out


def _window_run(monkeypatch, daily, run_at: datetime, chain=None, argv=()):
    """Run main() at run_at over the fake chain; returns (txids seen, prices asked, rows)."""
    real_calculate = daily.calculate_utxoracle_price
    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    chain = chain or FakeChain(tip=700)
    seen: list[list[str]] = []
    asked: list[int] = []

    class _Calculator:
        def calculate_price_for_transactions(self, transactions):
            seen.append([tx["txid"] for tx in transactions])
            return {"price_usd": 99_500.0, "confidence": 0.9, "tx_count": 1500}

    def price_at(timestamp, url):
        asked.append(timestamp)
        return 100_000.0

    monkeypatch.setattr(daily, "rpc_client", lambda config=None, timeout=60: chain)
    monkeypatch.setattr(daily, "UTXOracleCalculator", _Calculator)
    monkeypatch.setattr(daily, "calculate_utxoracle_price", real_calculate)
    monkeypatch.setattr(daily, "fetch_mempool_price_at", price_at)
    monkeypatch.setattr(daily, "utc_now", lambda: run_at)
    monkeypatch.setattr(sys, "argv", ["daily_analysis.py", *argv])
    daily.main()
    return seen, asked, sent


def _dry_run_data(monkeypatch, caplog, daily, run_at):
    """The row main() would write, from the --dry-run log, plus what the spy saw."""
    monkeypatch.setattr(daily, "METRICS_ENABLED", False)
    with caplog.at_level("INFO"):
        seen, asked, _ = _window_run(monkeypatch, daily, run_at, argv=("--dry-run",))
    record = next(r for r in caplog.records if r.getMessage().startswith("{"))
    return seen, asked, json.loads(record.getMessage())


def test_runs_at_00_30_and_23_30_of_the_same_utc_day_pick_the_same_blocks_and_row(
    monkeypatch, caplog
):
    import scripts.daily_analysis as daily

    early = _dry_run_data(
        monkeypatch, caplog, daily, datetime(2026, 10, 27, 0, 30, tzinfo=timezone.utc)
    )
    caplog.clear()
    late = _dry_run_data(
        monkeypatch, caplog, daily, datetime(2026, 10, 27, 23, 30, tzinfo=timezone.utc)
    )

    assert early[0] == late[0] and len(early[0][0]) == 144  # same 144 blocks of D
    assert early[0][0][0] == f"tx{CHAIN_FIRST}"
    for _, _, data in (early, late):
        assert data["timestamp"] == DAY.isoformat()  # key: the analysed day D
        assert data["window_end_ts"] == str(DAY + timedelta(days=1))
    assert early[2]["window_end_ts"] == late[2]["window_end_ts"]


def test_reference_price_is_asked_for_the_end_of_the_analysed_day_not_for_now(
    monkeypatch, caplog
):
    import scripts.daily_analysis as daily

    _, asked, _ = _dry_run_data(
        monkeypatch, caplog, daily, datetime(2026, 10, 27, 15, 45, tzinfo=timezone.utc)
    )

    assert asked == [int((DAY + timedelta(days=1)).timestamp())]


def test_rpc_shaped_transactions_fail_with_the_missing_fields_and_write_nothing(
    monkeypatch, caplog
):
    """getblock verbosity 2 has no prevout and scriptPubKey.address: addresses would be 0."""
    import scripts.daily_analysis as daily

    # Until F-432 the day is refused at the head of main(); the format guard is what protects
    # the metrics once that gate is lifted, so the gate is lifted here to exercise it.
    monkeypatch.setattr(daily, "HISTORICAL_DAY_IS_STREAMED", False)
    with caplog.at_level("ERROR"), pytest.raises(SystemExit) as stop:
        _window_run(
            monkeypatch, daily, datetime(2026, 10, 27, 1, 30, tzinfo=timezone.utc)
        )

    assert stop.value.code == 2
    assert "vin[].prevout.scriptpubkey_address" in caplog.text
    assert "vout[].scriptpubkey_address" in caplog.text
    assert "vout[].value" not in caplog.text  # present in both shapes


def test_a_streamed_day_cannot_feed_the_metrics_yet_so_nothing_is_written(
    monkeypatch, caplog
):
    """Even with data in the shape the metrics read: they need the same pass (F-432)."""
    import api.questdb_repository as repository
    import scripts.daily_analysis as daily

    real_calculate = daily.calculate_utxoracle_price  # before _stub_inputs replaces it
    rows = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    monkeypatch.setattr(
        daily, "utc_now", lambda: datetime(2026, 10, 27, 1, 30, tzinfo=timezone.utc)
    )
    monkeypatch.setattr(
        daily, "fetch_mempool_price_at", lambda timestamp, url: 100_000.0
    )
    monkeypatch.setattr(daily, "calculate_utxoracle_price", real_calculate)
    chain = _MempoolShapedChain(tip=700)
    monkeypatch.setattr(daily, "rpc_client", lambda config=None, timeout=60: chain)

    class _Calculator:
        def calculate_price_for_transactions(self, transactions):
            return {
                "price_usd": 99_500.0,
                "confidence": 0.9,
                "tx_count": sum(1 for _ in transactions),
            }

    monkeypatch.setattr(daily, "UTXOracleCalculator", _Calculator)
    assert repository  # (QuestDBRepository._send_row is recorded by _record_rows)

    with caplog.at_level("ERROR"), pytest.raises(SystemExit) as stop:
        daily.main()

    assert stop.value.code == 2
    assert rows == []
    assert "no transactions available" in caplog.text


# --- B3 decisions on #64: fail closed, narrow except, coinbase-safe format guard ---------


def _real_calculate(monkeypatch, daily, chain, run_at=None):
    """The REAL calculate_utxoracle_price over a fake chain; only the price library is a spy."""
    seen: list[list[str]] = []

    class _Calculator:
        def calculate_price_for_transactions(self, transactions):
            seen.append([tx["txid"] for tx in transactions])
            return {"price_usd": 99_500.0, "confidence": 0.9, "tx_count": 1500}

    monkeypatch.setattr(daily, "rpc_client", lambda config=None, timeout=60: chain)
    monkeypatch.setattr(daily, "UTXOracleCalculator", _Calculator)
    return seen


def test_a_streamed_day_fails_closed_with_the_explicit_message_and_zero_writes(
    monkeypatch, caplog
):
    """B3: no price row without metrics, no partial write; real main(), both tables checked."""
    import scripts.daily_analysis as daily

    real_calculate = daily.calculate_utxoracle_price
    rows = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    monkeypatch.setattr(
        daily, "HISTORICAL_DAY_IS_STREAMED", True
    )  # the production value
    monkeypatch.setattr(daily, "calculate_utxoracle_price", real_calculate)
    monkeypatch.setattr(
        daily, "utc_now", lambda: datetime(2026, 10, 27, 1, 30, tzinfo=timezone.utc)
    )
    chain = _MempoolShapedChain(tip=700)
    _real_calculate(monkeypatch, daily, chain)

    with caplog.at_level("ERROR"), pytest.raises(SystemExit) as stop:
        daily.main()

    assert stop.value.code == 2
    assert (
        chain.calls == []
    )  # refused at the head of main(): the node got no call at all
    assert rows == []  # neither price_analysis nor metrics
    assert (
        "metriche non calcolabili dallo stream fino a F-432: nessuna scrittura"
        in caplog.text
    )


class _CoinbaseFirstChain(FakeChain):
    """Each block starts with a coinbase, then a normal transaction."""

    def __init__(self, *args, shape="mempool", **kwargs):
        super().__init__(*args, **kwargs)
        self.shape = shape

    def call(self, method, params=None):
        out = super().call(method, params)
        if method == "getblock":
            txid = out["tx"][0]["txid"]
            if self.shape == "mempool":
                coinbase = {
                    "txid": f"cb{txid}",
                    "vin": [{"prevout": None, "is_coinbase": True}],
                    "vout": [{"scriptpubkey_address": "bc1qminer", "value": 3.0}],
                }
                normal = {
                    "txid": txid,
                    "vin": [{"prevout": {"scriptpubkey_address": "bc1qin"}}],
                    "vout": [{"scriptpubkey_address": "bc1qout", "value": 0.5}],
                }
            else:  # Core, verbosity 2
                coinbase = {
                    "txid": f"cb{txid}",
                    "vin": [{"coinbase": "03aa"}],
                    "vout": [{"scriptPubKey": {"address": "bc1qminer"}, "value": 3.0}],
                }
                normal = {
                    "txid": txid,
                    "vin": [{"txid": "x", "vout": 0}],
                    "vout": [{"scriptPubKey": {"address": "bc1qout"}, "value": 0.5}],
                }
            out["tx"] = [coinbase, normal]
        return out


def test_the_format_guard_looks_at_the_first_non_coinbase_transaction(monkeypatch):
    import scripts.daily_analysis as daily

    seen = _real_calculate(monkeypatch, daily, _CoinbaseFirstChain(tip=700))

    result = daily.calculate_utxoracle_price({}, DAY)

    sample = result["format_sample"]
    assert sample["txid"] == f"tx{CHAIN_FIRST}"  # not the coinbase "cbtx500"
    assert daily.missing_metric_fields([sample]) == []
    assert (
        seen[0][0] == f"cbtx{CHAIN_FIRST}"
    )  # nothing lost: the coinbase is still first
    assert seen[0][1] == f"tx{CHAIN_FIRST}" and len(seen[0]) == 288  # once, in order


def test_the_format_guard_reports_only_the_real_gaps_for_a_core_shaped_day(monkeypatch):
    import scripts.daily_analysis as daily

    _real_calculate(monkeypatch, daily, _CoinbaseFirstChain(tip=700, shape="core"))

    sample = daily.calculate_utxoracle_price({}, DAY)["format_sample"]

    assert sample["txid"] == f"tx{CHAIN_FIRST}"
    assert daily.missing_metric_fields([sample]) == [
        "vin[].prevout.scriptpubkey_address",
        "vout[].scriptpubkey_address",
    ]


def test_errors_of_the_historical_day_keep_their_own_cause_and_exit_code(
    monkeypatch, caplog
):
    """The calculation must not turn a stream/RPC failure into 'no price' (exit 2, cause lost)."""
    import scripts.daily_analysis as daily

    chain = FakeChain(tip=700)
    chain.fail_block = CHAIN_FIRST + 20  # an RPC error in the middle of the stream
    _real_calculate(monkeypatch, daily, chain)
    monkeypatch.setattr(
        daily,
        "UTXOracleCalculator",
        type(
            "C",
            (),
            {
                "calculate_price_for_transactions": lambda self, t: {
                    "price_usd": 1.0,
                    "confidence": 1.0,
                    "tx_count": sum(1 for _ in t),
                }
            },
        ),
    )

    with pytest.raises(RuntimeError, match="rpc block down"):
        daily.calculate_utxoracle_price({}, DAY)


@pytest.mark.parametrize(
    "env, tip, code",
    [
        ({"MIN_CONFIRMATIONS": "0"}, 700, 6),  # bad value: exit 6, name only
        ({}, 643, 7),  # the day is still open: exit 7
    ],
)
def test_real_main_keeps_the_exit_codes_of_the_selection(
    monkeypatch, caplog, env, tip, code
):
    import scripts.daily_analysis as daily

    for name, value in env.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(SystemExit) as stop:
        _window_run(
            monkeypatch,
            daily,
            datetime(2026, 10, 27, 1, 30, tzinfo=timezone.utc),
            chain=FakeChain(tip=tip),
        )

    assert stop.value.code == code


_DONE = {"price_analysis": (True, True), "metrics": (True, True)}


def test_window_end_column_already_present_runs_no_alter(monkeypatch):
    """On a WAL table ADD COLUMN IF NOT EXISTS of an existing column is a rejected no-op."""
    import api.questdb_repository as repository

    conn, reads = _fake_questdb(
        monkeypatch, _DONE, columns={"price_analysis": {"ts", "window_end_ts"}}
    )
    asyncio.run(repository.create_tables_if_not_exist())

    create = next(
        s for s in conn.statements if "CREATE TABLE IF NOT EXISTS price_analysis (" in s
    )
    assert "window_end_ts TIMESTAMP" in create
    assert not any("ADD COLUMN" in s and "window_end_ts" in s for s in conn.statements)
    assert reads and all(
        c.closed for c in reads
    )  # columns read on connections of their own


def test_window_end_column_missing_is_added_by_one_plain_alter(monkeypatch):
    import api.questdb_repository as repository

    conn, _ = _fake_questdb(
        monkeypatch, _DONE, columns={"price_analysis": {"ts", "exchange_price"}}
    )
    asyncio.run(repository.create_tables_if_not_exist())

    alters = [s for s in conn.statements if "ADD COLUMN" in s and "window_end_ts" in s]
    assert alters == ["ALTER TABLE price_analysis ADD COLUMN window_end_ts TIMESTAMP"]


def test_a_failed_window_end_alter_is_an_error_not_a_swallowed_exception(monkeypatch):
    import api.questdb_repository as repository

    class _AlterRefused(_RecordingConnection):
        async def execute(self, statement: str, *args) -> None:
            if "ADD COLUMN" in statement and "window_end_ts" in statement:
                raise RuntimeError("alter refused (test)")
            await super().execute(statement, *args)

    _fake_questdb(
        monkeypatch, _DONE, _AlterRefused(), columns={"price_analysis": {"ts"}}
    )

    with pytest.raises(RuntimeError, match="alter refused"):
        asyncio.run(repository.create_tables_if_not_exist())


class _CorruptChain(FakeChain):
    """A node answering one block with garbage (json.JSONDecodeError in the client)."""

    def call(self, method, params=None):
        if method == "getblock" and params[0] == f"hash{CHAIN_FIRST + 20}":
            raise json.JSONDecodeError("Expecting value", "<html>502</html>", 0)
        return super().call(method, params)


def test_a_corrupt_rpc_response_is_not_turned_into_no_price(monkeypatch):
    import scripts.daily_analysis as daily

    _real_calculate(monkeypatch, daily, _CorruptChain(tip=700))

    with pytest.raises(json.JSONDecodeError):
        daily.calculate_utxoracle_price({}, DAY)


def test_a_corrupt_rpc_response_ends_main_with_exit_2_and_its_own_cause(
    monkeypatch, caplog
):
    import scripts.daily_analysis as daily

    monkeypatch.setattr(daily, "METRICS_ENABLED", False)  # dry run: the price path only
    with caplog.at_level("ERROR"), pytest.raises(SystemExit) as stop:
        _window_run(
            monkeypatch,
            daily,
            datetime(2026, 10, 27, 1, 30, tzinfo=timezone.utc),
            chain=_CorruptChain(tip=700),
            argv=("--dry-run",),
        )

    assert stop.value.code == 2
    assert "Expecting value" in caplog.text  # the cause, not "no price"
    assert "row incomplete" not in caplog.text


def test_a_failed_price_validation_of_the_day_is_still_no_price(monkeypatch):
    """Only the validation of the day's price becomes "no price" (PriceValidationError)."""
    import scripts.daily_analysis as daily

    _real_calculate(monkeypatch, daily, FakeChain(tip=700))

    class _Weak:
        def calculate_price_for_transactions(self, transactions):
            sum(1 for _ in transactions)
            return {"price_usd": 99_500.0, "confidence": 0.9, "tx_count": 5}  # < 1000

    monkeypatch.setattr(daily, "UTXOracleCalculator", _Weak)

    result = daily.calculate_utxoracle_price({}, DAY)

    assert result["price_usd"] is None
    assert issubclass(daily.PriceValidationError, ValueError)
