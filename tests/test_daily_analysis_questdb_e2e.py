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
from datetime import datetime, timezone
import os
import sys
import types

import pytest

_TARGET_ENV = (
    "QUESTDB_TEST_HOST",
    "QUESTDB_TEST_PORT",
    "QUESTDB_TEST_ILP_PORT",
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
        "user": os.environ["QUESTDB_TEST_USER"],
        "password": os.environ["QUESTDB_TEST_PASSWORD"],
        "database": os.getenv("QUESTDB_TEST_DATABASE", "qdb"),
    }
    forbidden = {target["port"], target["ilp_port"]} & _FORBIDDEN_PORTS
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
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _stub_inputs(monkeypatch, daily) -> None:
    """Replace only bitcoind, mempool.space and the config checks (synthetic, see header)."""
    monkeypatch.setattr(daily, "validate_config", lambda config: None)
    monkeypatch.setattr(daily, "WhaleFlowDetector", None)
    monkeypatch.setattr(daily, "ADVANCED_METRICS_ENABLED", False)
    monkeypatch.setattr(daily, "fetch_mempool_price", lambda url: 100_000.0)
    monkeypatch.setattr(
        daily,
        "calculate_utxoracle_price",
        lambda config: {
            "price_usd": 99_500.0,
            "confidence": 0.9,
            "tx_count": 2,
            "fetch_tier": "synthetic",
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
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: str, *args) -> None:
        self.statements.append(" ".join(statement.split()))

    async def close(self) -> None:
        return None


def test_ddl_dedups_price_analysis_and_metrics_on_ts(monkeypatch):
    """M1: the schema makes the daily rerun idempotent (WAL table + DEDUP UPSERT KEYS(ts))."""
    import types as _types

    import api.questdb_repository as repository

    conn = _RecordingConnection()

    async def connect(**kwargs):
        return conn

    monkeypatch.setattr(repository, "asyncpg", _types.SimpleNamespace(connect=connect))
    asyncio.run(repository.create_tables_if_not_exist())

    for table in ("price_analysis", "metrics"):
        create = next(
            s for s in conn.statements if f"CREATE TABLE IF NOT EXISTS {table} (" in s
        )
        assert "WAL" in create and "DEDUP UPSERT KEYS(ts)" in create, table
        # Existing (non-WAL, non-dedup) tables are migrated by the same function.
        assert f"ALTER TABLE {table} SET TYPE WAL" in conn.statements
        assert f"ALTER TABLE {table} DEDUP ENABLE UPSERT KEYS(ts)" in conn.statements


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
    monkeypatch.setattr(repository, "QUESTDB_ILP_HOST", target["host"])
    monkeypatch.setattr(repository, "QUESTDB_ILP_PORT", target["ilp_port"])
    for name, key in (
        ("QUESTDB_PG_HOST", "host"),
        ("QUESTDB_PG_PORT", "port"),
        ("QUESTDB_PG_USER", "user"),
        ("QUESTDB_PG_PASSWORD", "password"),
        ("QUESTDB_PG_DATABASE", "database"),
    ):
        monkeypatch.setattr(repository, name, target[key])
    monkeypatch.setattr(metrics._repo, "ilp_host", target["host"])
    monkeypatch.setattr(metrics._repo, "ilp_port", target["ilp_port"])

    # Fails (not skips) when the target is configured but down: an unreachable QuestDB must
    # not turn the gate green.
    asyncio.run(repository.create_tables_if_not_exist())

    _stub_inputs(monkeypatch, daily)
    daily.main()
    daily.main()

    where = f"WHERE ts = '{_day_start_utc().strftime('%Y-%m-%dT%H:%M:%S.%fZ')}'"
    for table in ("price_analysis", "metrics"):
        rows = asyncio.run(_wait_for_count(target, table, where, expected=1))
        assert rows == 1, f"{table}: {rows} rows for the analysed day after two runs"


def _set_destination(monkeypatch, *, ilp=("127.0.0.1", 9909), pg=("127.0.0.1", 9912)):
    import api.questdb_repository as repository

    monkeypatch.setattr(repository, "QUESTDB_ILP_HOST", ilp[0])
    monkeypatch.setattr(repository, "QUESTDB_ILP_PORT", ilp[1])
    monkeypatch.setattr(repository, "QUESTDB_PG_HOST", pg[0])
    monkeypatch.setattr(repository, "QUESTDB_PG_PORT", pg[1])


def _expect_destination(monkeypatch, *, ilp_port="9909", pg_port="9912"):
    monkeypatch.setenv("UTXORACLE_EXPECTED_QUESTDB_ILP_HOST", "127.0.0.1")
    monkeypatch.setenv("UTXORACLE_EXPECTED_QUESTDB_ILP_PORT", ilp_port)
    monkeypatch.setenv("UTXORACLE_EXPECTED_QUESTDB_PG_HOST", "127.0.0.1")
    monkeypatch.setenv("UTXORACLE_EXPECTED_QUESTDB_PG_PORT", pg_port)


def test_destination_mismatch_exits_before_any_write(monkeypatch, caplog):
    """M2: a wrong QuestDB (e.g. an override after load_secrets) must not receive rows."""
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _set_destination(
        monkeypatch, ilp=("127.0.0.1", 9009)
    )  # the host QuestDB, not the live
    _expect_destination(monkeypatch)

    with caplog.at_level("ERROR"), pytest.raises(SystemExit) as stop:
        daily.main()

    assert stop.value.code == 3
    assert sent == []
    assert "QuestDB destination mismatch" in caplog.text
    assert "9009" in caplog.text and "9909" in caplog.text


def test_destination_match_proceeds_and_logs_the_effective_target(monkeypatch, caplog):
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _set_destination(monkeypatch)
    _expect_destination(monkeypatch)

    with caplog.at_level("INFO"):
        daily.main()

    assert {row[0] for row in sent} == {"price_analysis", "metrics"}
    assert "QuestDB destination: ILP 127.0.0.1:9909, PG 127.0.0.1:9912" in caplog.text


def test_destination_without_expectation_logs_and_does_not_fail(monkeypatch, caplog):
    """Manual use and tests set no expectation: log the target, do not block."""
    import scripts.daily_analysis as daily

    sent = _record_rows(monkeypatch)
    _stub_inputs(monkeypatch, daily)
    _set_destination(monkeypatch, ilp=("db.invalid", 1111), pg=("db.invalid", 2222))
    for name in (
        "UTXORACLE_EXPECTED_QUESTDB_ILP_HOST",
        "UTXORACLE_EXPECTED_QUESTDB_ILP_PORT",
        "UTXORACLE_EXPECTED_QUESTDB_PG_HOST",
        "UTXORACLE_EXPECTED_QUESTDB_PG_PORT",
    ):
        monkeypatch.delenv(name, raising=False)

    with caplog.at_level("INFO"):
        daily.main()

    assert sent
    assert "no expected destination set" in caplog.text
    assert "ILP db.invalid:1111" in caplog.text


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

    _record_rows(monkeypatch)
    monkeypatch.setattr(metrics._repo, "_build_sender", lambda: _FlakySender())
    monkeypatch.setattr(metrics._repo, "sender", None)
    _stub_inputs(monkeypatch, daily)

    assert _exit_code(daily) == 2


# --- Schema migration: no error may vanish ---------------------------------------------


class _AlterConnection(_RecordingConnection):
    """Fails the statements whose text contains a key of `failures`."""

    def __init__(self, failures: dict[str, str]) -> None:
        super().__init__()
        self.failures = failures

    async def execute(self, statement: str, *args) -> None:
        text = " ".join(statement.split())
        for needle, message in self.failures.items():
            if needle in text:
                raise RuntimeError(message)
        self.statements.append(text)


def _create_tables(monkeypatch, conn) -> None:
    import types as _types

    import api.questdb_repository as repository

    async def connect(**kwargs):
        return conn

    monkeypatch.setattr(repository, "asyncpg", _types.SimpleNamespace(connect=connect))
    asyncio.run(repository.create_tables_if_not_exist())


def test_unexpected_dedup_error_fails_the_table_creation(monkeypatch):
    """Without DEDUP the daily rerun would duplicate rows: the error must surface."""
    conn = _AlterConnection(
        {"price_analysis DEDUP ENABLE": "deduplication is possible only on WAL tables"}
    )
    with pytest.raises(RuntimeError, match="only on WAL"):
        _create_tables(monkeypatch, conn)


def test_dedup_already_enabled_is_logged_at_info_and_does_not_fail(monkeypatch, caplog):
    conn = _AlterConnection(
        {"metrics DEDUP ENABLE": "deduplication is already enabled on the table"}
    )
    with caplog.at_level("INFO"):
        _create_tables(monkeypatch, conn)

    assert any(
        r.levelname == "INFO"
        and "metrics" in r.getMessage()
        and "already" in r.getMessage()
        for r in caplog.records
    )


def test_unexpected_set_type_wal_error_is_logged_as_warning(monkeypatch, caplog):
    conn = _AlterConnection({"metrics SET TYPE WAL": "permission denied"})
    with caplog.at_level("WARNING"):
        _create_tables(monkeypatch, conn)

    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any(
        "metrics" in m and "SET TYPE WAL" in m and "permission denied" in m
        for m in warnings
    )
