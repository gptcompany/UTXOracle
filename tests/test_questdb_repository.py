from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
import re
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from api.questdb_repository import (
    ADDRESS_CLUSTERS_SCHEMA,
    ConcurrentRefreshError,
    CutoverSwapError,
    OldCopyCleanupError,
    QuestDBRepository,
)
from scripts.models.metrics_models import CostBasisResult, URPDFeaturesResult


class _FakeSender:
    def __init__(self, *, fail_with: Exception | None = None):
        self.fail_with = fail_with
        self.established = 0
        self.rows: list[tuple[str, dict, dict, object]] = []
        self.flushed = 0
        self.closed = 0

    def establish(self):
        self.established += 1

    def row(self, table, *, symbols, columns, at=None):
        if self.fail_with is not None:
            raise self.fail_with
        self.rows.append((table, symbols, columns, at))

    def flush(self):
        self.flushed += 1

    def close(self):
        self.closed += 1


def test_send_row_recreates_closed_sender_and_retries(monkeypatch):
    first = _FakeSender(fail_with=RuntimeError("Sender is closed"))
    second = _FakeSender()
    senders = iter([first, second])

    def fake_build_sender(self):
        return next(senders)

    monkeypatch.setattr(QuestDBRepository, "_build_sender", fake_build_sender)

    repo = QuestDBRepository()

    assert repo._send_row(
        "live_snapshots",
        symbols={"schema_version": "v1"},
        columns={"block_height": 1},
    )
    assert second.rows == [
        ("live_snapshots", {"schema_version": "v1"}, {"block_height": 1}, None)
    ]


def test_build_sender_establishes_transport(monkeypatch):
    sender = _FakeSender()

    def fake_sender_ctor(protocol, host, port):
        assert protocol == "tcp"
        assert host == "localhost"
        assert port == 9009
        return sender

    monkeypatch.setattr("api.questdb_repository.Sender", fake_sender_ctor)

    repo = QuestDBRepository()

    assert repo.sender is None
    repo._ensure_sender()
    assert repo.sender is sender
    assert sender.established == 1


def test_async_send_row_uses_sync_sender_without_executor(monkeypatch):
    repo = QuestDBRepository.__new__(QuestDBRepository)
    calls: list[tuple[str, dict, dict, object, bool]] = []

    def fake_send_row(table, symbols, columns, at=None, flush=False):
        calls.append((table, symbols, columns, at, flush))
        return True

    repo._send_row = fake_send_row  # type: ignore[attr-defined]

    result = asyncio.run(
        QuestDBRepository.async_send_row(
            repo,
            "live_snapshots",
            {"schema_version": "v1"},
            {"block_height": 1},
        )
    )

    assert result is True
    assert calls == [
        ("live_snapshots", {"schema_version": "v1"}, {"block_height": 1}, None, False)
    ]


def test_abort_ingestion_drops_buffer_and_prevents_flush_on_close():
    repo = QuestDBRepository()
    sender = _FakeSender()
    repo.sender = sender
    repo._unflushed_rows = 3

    repo.abort_ingestion()

    assert repo._ingestion_aborted is True
    assert repo._unflushed_rows == 0
    assert repo.sender is None
    assert sender.closed == 1
    assert repo.flush_ingestion() is False

    asyncio.run(repo.close())
    assert sender.flushed == 0


@pytest.fixture(autouse=True)
def _lock_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("ADDRESS_CLUSTERS_LOCK_DIR", str(tmp_path / "locks"))


class _FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds


def _wal(writer, seq, suspended=False, tag="", message=""):
    return {
        "suspended": suspended,
        "writerTxn": writer,
        "sequencerTxn": seq,
        "errorTag": tag,
        "errorMessage": message,
    }


class _FakeHttpSender:
    def __init__(self, flush_error=None):
        self.rows = []
        self.flushes = 0
        self.closed_with = None
        self.flush_error = flush_error

    def row(self, table, symbols=None, columns=None, at=None):
        self.rows.append((table, symbols, columns))

    def flush(self):
        if self.flush_error:
            raise self.flush_error
        self.flushes += 1

    def close(self, flush=True):
        self.closed_with = flush


class _DedicatedConn:
    """DDL connection: execute/close only, so any fetch is an AttributeError."""

    def __init__(self, fail_on=()):
        self.executed = []
        self.closed = 0
        self.fail_on = fail_on

    async def execute(self, query, *args):
        query = " ".join(query.split())
        self.executed.append(query)
        if any(query.startswith(prefix) for prefix in self.fail_on):
            raise RuntimeError(f"boom: {query[:30]}")

    async def close(self):
        self.closed += 1


def _repo(
    monkeypatch,
    wal=None,
    count=5,
    columns=None,
    old_copies=(),
    sender=None,
    fail_on=(),
    live_exists=True,
):
    """Repo with fake clock, ILP/HTTP sender, wal_tables(), staging schema and count;
    wal and count may be callables of the fake time (wal "absent" = not a WAL table)."""
    import api.questdb_repository as qr

    clock = _FakeClock()
    monkeypatch.setattr(qr, "_monotonic", clock.monotonic)
    monkeypatch.setattr(qr, "_sleep", clock.sleep)
    wal = _wal(9, 9) if wal is None else wal
    columns = qr.ADDRESS_CLUSTERS_SCHEMA if columns is None else columns

    def at(value):
        return value(clock.now) if callable(value) else value

    async def fetch(query, *args):
        if "wal_tables" in query:
            current = at(wal)
            return [] if current == "absent" else [current]
        if "table_columns" in query:
            return list(columns)
        if "tables()" in query and "LIKE" in query:
            return [(name,) for name in old_copies]
        if "tables()" in query:
            return [("address_clusters",)] if live_exists else []
        raise AssertionError(query)

    repo = QuestDBRepository()
    repo.clock = clock
    repo.fetch = fetch
    repo._refresh_sender = sender
    repo._refresh_buffered = 1 if sender else 0
    repo.fetchrow = AsyncMock(side_effect=lambda q, *a: (at(count),))
    repo.execute = AsyncMock(side_effect=AssertionError("write on the pool"))
    repo.dedicated = _DedicatedConn(fail_on)
    repo._open_dedicated_connection = AsyncMock(return_value=repo.dedicated)
    return repo


def _errors(caplog):
    return [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]


def _ddl(repo):
    return repo.dedicated.executed


TRUNCATE_STAGING = "TRUNCATE TABLE address_clusters_staging"


def test_stage_address_cluster_uses_http_sender_and_flushes_in_batches(monkeypatch):
    import api.questdb_repository as qr

    monkeypatch.setattr(qr, "ADDRESS_CLUSTERS_FLUSH_ROWS", 2)
    sender = _FakeHttpSender()
    repo = QuestDBRepository()
    repo._build_refresh_sender = lambda: sender
    repo._build_sender = lambda: pytest.fail("TCP sender must not be used")

    results = [
        repo.stage_address_cluster({"address": f"a{i}", "cluster_id": "c"})
        for i in range(3)
    ]

    assert results == [True, True, True]
    assert len(sender.rows) == 3 and sender.flushes == 1
    assert all(t == "address_clusters_staging" for t, _, _ in sender.rows)


def test_stage_address_cluster_reports_a_server_rejection(monkeypatch, caplog):
    import api.questdb_repository as qr

    monkeypatch.setattr(qr, "ADDRESS_CLUSTERS_FLUSH_ROWS", 1)
    repo = QuestDBRepository()
    repo._refresh_sender = _FakeHttpSender(flush_error=RuntimeError("rejected"))

    with caplog.at_level("ERROR"):
        assert repo.stage_address_cluster({"address": "a", "cluster_id": "c"}) is False
    assert any("rejected" in m for m in _errors(caplog))


def test_cutover_swaps_with_rename_and_keeps_one_old_copy(monkeypatch, caplog):
    sender = _FakeHttpSender()
    repo = _repo(
        monkeypatch,
        wal=lambda t: _wal(8, 9) if t < 10 else _wal(9, 9),
        sender=sender,
    )

    with caplog.at_level("INFO"):
        assert asyncio.run(repo.commit_address_clusters_refresh(5)) is True

    assert sender.flushes == 1 and repo._refresh_sender is None
    ddl = _ddl(repo)
    assert re.fullmatch(
        r"RENAME TABLE address_clusters TO address_clusters_old_\d{8}T\d{6}Z", ddl[0]
    )
    assert ddl[1] == "RENAME TABLE address_clusters_staging TO address_clusters"
    assert ddl[2].startswith("CREATE TABLE IF NOT EXISTS address_clusters_staging")
    assert not any("INSERT" in q or "TRUNCATE" in q or "DROP" in q for q in ddl)
    assert any(
        "absent for" in r.getMessage() and " ms" in r.getMessage()
        for r in caplog.records
    )


def test_cutover_drops_only_the_older_old_copies(monkeypatch):
    repo = _repo(
        monkeypatch,
        old_copies=(
            "address_clusters_old_20260101T000000Z",
            "address_clusters_old_20260102T000000Z",
            "address_clusters_old_evil; DROP TABLE x",
        ),
    )

    assert asyncio.run(repo.commit_address_clusters_refresh(5)) is True

    drops = [q for q in _ddl(repo) if q.startswith("DROP")]
    assert drops == [
        "DROP TABLE address_clusters_old_20260101T000000Z",
        "DROP TABLE address_clusters_old_20260102T000000Z",
    ]
    new_old = _ddl(repo)[0].split(" TO ")[1]
    assert not any(new_old in q for q in drops)  # the copy just made is never dropped


def test_a_failing_cleanup_after_the_swap_keeps_the_new_live_and_is_retried_next_time(
    monkeypatch, caplog
):
    stale = "address_clusters_old_20260101T000000Z"
    first = _repo(monkeypatch, old_copies=(stale,), fail_on=("DROP",))

    with caplog.at_level("ERROR"), pytest.raises(OldCopyCleanupError) as exc:
        asyncio.run(first.commit_address_clusters_refresh(5))

    assert exc.value.names == [stale] and stale in str(exc.value)
    ddl = _ddl(first)
    assert (
        ddl[1] == "RENAME TABLE address_clusters_staging TO address_clusters"
    )  # swapped
    assert any(stale in m for m in _errors(caplog)) or any(
        stale in r.getMessage() for r in caplog.records
    )

    # next refresh: the leftover and the previous run's copy are dropped, the new one kept
    previous = "address_clusters_old_20260102T000000Z"
    second = _repo(monkeypatch, old_copies=(stale, previous))
    assert asyncio.run(second.commit_address_clusters_refresh(5)) is True
    drops = [q for q in _ddl(second) if q.startswith("DROP")]
    assert drops == [f"DROP TABLE {stale}", f"DROP TABLE {previous}"]


def test_without_a_live_table_the_staging_table_is_renamed_once(monkeypatch):
    repo = _repo(monkeypatch, live_exists=False)

    assert asyncio.run(repo.commit_address_clusters_refresh(5)) is True

    ddl = _ddl(repo)
    assert ddl[0] == "RENAME TABLE address_clusters_staging TO address_clusters"
    assert not any("_old_" in q and q.startswith("RENAME") for q in ddl)


def test_without_a_live_table_a_failed_rename_is_an_error(monkeypatch, caplog):
    repo = _repo(monkeypatch, live_exists=False, fail_on=("RENAME",))

    with caplog.at_level("ERROR"):
        assert asyncio.run(repo.commit_address_clusters_refresh(5)) is False

    assert len(_ddl(repo)) == 1
    assert "does not exist and RENAME" in " ".join(_errors(caplog))


def test_second_rename_failure_restores_the_live_table_at_once(monkeypatch, caplog):
    repo = _repo(monkeypatch, fail_on=("RENAME TABLE address_clusters_staging",))

    with caplog.at_level("ERROR"):
        ok = asyncio.run(repo.commit_address_clusters_refresh(5))

    assert ok is False
    ddl = _ddl(repo)
    assert len(ddl) == 3 and ddl[0].startswith("RENAME TABLE address_clusters TO ")
    old = ddl[0].split(" TO ")[1]
    assert ddl[2] == f"RENAME TABLE {old} TO address_clusters"  # undo, immediately
    assert any("restored" in m for m in _errors(caplog))


def test_failed_undo_raises_with_the_names_and_the_manual_command(monkeypatch, caplog):
    repo = _repo(
        monkeypatch,
        fail_on=(
            "RENAME TABLE address_clusters_staging",
            "RENAME TABLE address_clusters_old",
        ),
    )

    with caplog.at_level("ERROR"), pytest.raises(CutoverSwapError) as exc:
        asyncio.run(repo.commit_address_clusters_refresh(5))

    old = _ddl(repo)[0].split(" TO ")[1]
    assert exc.value.restored is False
    assert f"RENAME TABLE {old} TO address_clusters" in str(exc.value)
    assert any("ABSENT" in m for m in _errors(caplog))


def test_first_rename_failure_changes_nothing(monkeypatch):
    repo = _repo(monkeypatch, fail_on=("RENAME TABLE address_clusters TO",))

    assert asyncio.run(repo.commit_address_clusters_refresh(5)) is False
    assert (
        _ddl(repo)
        == [s for s in _ddl(repo) if s.startswith("RENAME TABLE address_clusters TO ")]
        and len(_ddl(repo)) == 1
    )  # only the failed RENAME: live and staging untouched


def test_commit_raises_and_aborts_when_the_server_rejects_the_flush(
    monkeypatch, caplog
):
    repo = _repo(
        monkeypatch, sender=_FakeHttpSender(flush_error=RuntimeError("bad row"))
    )

    with caplog.at_level("ERROR"), pytest.raises(RuntimeError, match="bad row"):
        asyncio.run(repo.commit_address_clusters_refresh(5))

    assert _ddl(repo) == [TRUNCATE_STAGING]
    assert any(r.exc_info for r in caplog.records)


def test_commit_aborts_at_once_when_wal_is_suspended(monkeypatch, caplog):
    repo = _repo(
        monkeypatch,
        wal=lambda t: _wal(3, 8)
        if t < 10
        else _wal(3, 8, True, "DISK_FULL", "no space"),
        count=2,
    )

    with caplog.at_level("ERROR"):
        ok = asyncio.run(repo.commit_address_clusters_refresh(5))

    assert ok is False and _ddl(repo) == [TRUNCATE_STAGING]
    msg = _errors(caplog)[0]
    assert "suspended" in msg and "DISK_FULL" in msg and "no space" in msg
    assert repo.clock.now < 20


def test_commit_aborts_when_staging_is_not_a_wal_table(monkeypatch, caplog):
    repo = _repo(monkeypatch, wal="absent")

    with caplog.at_level("ERROR"):
        ok = asyncio.run(repo.commit_address_clusters_refresh(5))

    assert ok is False and _ddl(repo) == [TRUNCATE_STAGING]
    msg = _errors(caplog)[0]
    assert "not_wal" in msg and "address_clusters_staging" in msg
    assert "DROP TABLE address_clusters_staging" in msg
    assert "ALTER TABLE address_clusters_staging SET TYPE WAL" in msg


def test_commit_survives_one_big_transaction_without_progress(monkeypatch):
    repo = _repo(
        monkeypatch, wal=lambda t: _wal(8, 9) if t < 300 else _wal(9, 9), count=5
    )

    assert asyncio.run(repo.commit_address_clusters_refresh(5, max_wait_s=900)) is True
    assert repo.clock.now >= 300


def test_commit_aborts_at_ceiling(monkeypatch, caplog):
    repo = _repo(monkeypatch, wal=_wal(8, 9))

    with caplog.at_level("ERROR"):
        ok = asyncio.run(repo.commit_address_clusters_refresh(5, max_wait_s=120))

    assert ok is False and _ddl(repo) == [TRUNCATE_STAGING]
    assert "ceiling" in _errors(caplog)[0]
    assert 120 <= repo.clock.now < 130


def test_commit_aborts_at_once_on_count_mismatch(monkeypatch, caplog):
    repo = _repo(monkeypatch, wal=_wal(9, 9), count=3)

    with caplog.at_level("ERROR"):
        ok = asyncio.run(repo.commit_address_clusters_refresh(5))

    assert ok is False and _ddl(repo) == [TRUNCATE_STAGING]
    msg = _errors(caplog)[0]
    assert "count_mismatch" in msg and "expected 5" in msg and "observed 3" in msg
    assert repo.clock.now == 0


def test_commit_raises_and_aborts_when_the_count_query_fails(monkeypatch):
    repo = _repo(monkeypatch)
    repo.fetchrow = AsyncMock(side_effect=ConnectionError("pg down"))

    with pytest.raises(ConnectionError):
        asyncio.run(repo.commit_address_clusters_refresh(5))

    assert _ddl(repo) == [TRUNCATE_STAGING]


@pytest.mark.parametrize(
    "columns",
    [
        ADDRESS_CLUSTERS_SCHEMA[:-1],  # confidence missing
        [*ADDRESS_CLUSTERS_SCHEMA[:-1], ("confidence", "FLOAT")],  # wrong type
        [*ADDRESS_CLUSTERS_SCHEMA, ("extra", "LONG")],
    ],
)
def test_staging_schema_mismatch_aborts_without_touching_the_live_table(
    monkeypatch, caplog, columns
):
    repo = _repo(monkeypatch, columns=columns)

    with caplog.at_level("ERROR"):
        ok = asyncio.run(repo.commit_address_clusters_refresh(5))

    assert ok is False and _ddl(repo) == [TRUNCATE_STAGING]
    assert "schema_mismatch" in _errors(caplog)[0]


def test_a_failing_truncate_raises_on_abort_and_on_prepare(monkeypatch, caplog):
    repo = _repo(monkeypatch, fail_on=("TRUNCATE",))

    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(repo.abort_address_clusters_refresh())
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(repo.prepare_address_clusters_refresh())
    assert any("DDL failed" in m for m in _errors(caplog))


def test_prepare_recreates_and_empties_staging_on_the_dedicated_connection(monkeypatch):
    repo = _repo(monkeypatch)

    assert asyncio.run(repo.prepare_address_clusters_refresh()) is True

    ddl = _ddl(repo)
    assert ddl[0].startswith("CREATE TABLE IF NOT EXISTS address_clusters_staging")
    assert ddl[1] == TRUNCATE_STAGING


@contextlib.contextmanager
def _foreign_holder(lock_dir):
    """Hold the lock file the way another process would (own descriptor)."""
    lock_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_dir / "address_clusters.lock", os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        yield
    finally:
        os.close(fd)


def test_refresh_lock_refuses_another_process_and_is_reentrant_for_its_owner(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setenv("ADDRESS_CLUSTERS_LOCK_DIR", str(tmp_path))
    repo = QuestDBRepository()

    with repo.refresh_lock(), repo.refresh_lock():  # re-entrant in the same task
        pass
    with _foreign_holder(tmp_path):
        with caplog.at_level("ERROR"), pytest.raises(ConcurrentRefreshError):
            with repo.refresh_lock():
                pytest.fail("the lock must be refused")
        assert any("concurrent_refresh" in m for m in _errors(caplog))

    with repo.refresh_lock():  # free again once the other holder leaves
        pass


def test_a_second_coroutine_on_the_same_repository_is_refused(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setenv("ADDRESS_CLUSTERS_LOCK_DIR", str(tmp_path))
    repo = QuestDBRepository()
    entered = asyncio.Event()
    release = asyncio.Event()
    outcomes = {}

    async def owner():
        with repo.refresh_lock():
            with repo.refresh_lock():  # same task: re-entrant
                entered.set()
                await release.wait()
        outcomes["owner"] = "done"

    async def intruder():
        await entered.wait()
        try:
            with repo.refresh_lock():
                outcomes["intruder"] = "got the lock"
        except ConcurrentRefreshError:
            outcomes["intruder"] = "refused"
        release.set()

    async def run():
        await asyncio.gather(owner(), intruder())

    with caplog.at_level("ERROR"):
        asyncio.run(run())

    assert outcomes == {"owner": "done", "intruder": "refused"}
    assert any("concurrent_refresh" in m for m in _errors(caplog))


def test_refresh_is_refused_while_another_process_holds_the_lock(monkeypatch, tmp_path):
    monkeypatch.setenv("ADDRESS_CLUSTERS_LOCK_DIR", str(tmp_path))
    repo = _repo(monkeypatch)

    with _foreign_holder(tmp_path):
        with pytest.raises(ConcurrentRefreshError):
            asyncio.run(repo.commit_address_clusters_refresh(5))
        with pytest.raises(ConcurrentRefreshError):
            asyncio.run(repo.save_address_clusters_bulk([]))

    assert _ddl(repo) == []  # nothing touched


def test_create_tables_declares_the_staging_table_as_wal(monkeypatch):
    import api.questdb_repository as qr

    statements = []

    class _Conn:
        async def execute(self, query, *args):
            statements.append(" ".join(query.split()))

        async def close(self):
            return None

    async def connect(**kwargs):
        return _Conn()

    monkeypatch.setattr(qr.asyncpg, "connect", connect)
    asyncio.run(qr.create_tables_if_not_exist())

    staging = [
        q
        for q in statements
        if q.startswith("CREATE TABLE IF NOT EXISTS address_clusters_staging")
    ]
    assert len(staging) == 1 and staging[0].endswith("PARTITION BY YEAR WAL")


def test_save_cost_basis_passes_empty_symbols():
    repo = QuestDBRepository()
    calls: list[tuple[str, dict, dict, object]] = []

    def fake_send_row(table, symbols, columns, at=None, flush=False):
        calls.append((table, symbols, columns, at))
        return True

    repo._send_row = fake_send_row  # type: ignore[attr-defined]
    timestamp = datetime(2026, 1, 2, tzinfo=timezone.utc)
    result = CostBasisResult(
        sth_cost_basis=65000.0,
        lth_cost_basis=30000.0,
        total_cost_basis=42000.0,
        sth_mvrv=1.2,
        lth_mvrv=2.6,
        sth_supply_btc=3.5,
        lth_supply_btc=15.0,
        current_price_usd=78000.0,
        block_height=900000,
        timestamp=timestamp,
        confidence=0.85,
    )

    assert repo.save_cost_basis(result) is True

    assert len(calls) == 1
    table, symbols, columns, at = calls[0]
    assert table == "cost_basis_daily"
    assert symbols == {}
    assert columns["sth_cost_basis"] == 65000.0
    assert columns["lth_cost_basis"] == 30000.0
    assert columns["total_cost_basis"] == 42000.0
    assert at is timestamp


def test_get_cost_basis_latest_uses_fetchrow():
    repo = QuestDBRepository()
    expected = {"block_height": 900000}
    repo.fetchrow = AsyncMock(return_value=expected)  # type: ignore[method-assign]

    row = asyncio.run(repo.get_cost_basis_latest())

    assert row == expected
    repo.fetchrow.assert_awaited_once()
    query = repo.fetchrow.await_args.args[0]
    assert "FROM cost_basis_daily" in query
    assert "ORDER BY ts DESC" in query
    assert "LIMIT 1" in query
    assert "LATEST ON ts" not in query


def test_save_urpd_features_persists_schema_version_and_health():
    repo = QuestDBRepository()
    calls: list[tuple[str, dict, dict, object]] = []

    def fake_send_row(table, symbols, columns, at=None, flush=False):
        calls.append((table, symbols, columns, at))
        return True

    repo._send_row = fake_send_row  # type: ignore[attr-defined]
    timestamp = datetime(2026, 1, 2, tzinfo=timezone.utc)
    result = URPDFeaturesResult(
        supply_below_price_pct=72.0,
        supply_above_price_pct=28.0,
        top_bucket_concentration=14.5,
        dominant_bucket_distance_pct=-8.2,
        distribution_entropy=0.84,
        current_price_usd=78000.0,
        bucket_size_usd=5000.0,
        total_supply_btc=18.5,
        block_height=900000,
        timestamp=timestamp,
        availability_timestamp=timestamp,
        confidence=0.85,
        source_health={"status": "healthy", "source_freshness_seconds": 42.0},
    )

    assert repo.save_urpd_features(result) is True

    assert len(calls) == 1
    table, symbols, columns, at = calls[0]
    assert table == "urpd_features_daily"
    assert symbols == {"schema_version": "urpd_features_daily.v1"}
    assert columns["supply_below_price_pct"] == 72.0
    assert columns["top_bucket_concentration"] == 14.5
    assert columns["distribution_entropy"] == 0.84
    assert columns["availability_timestamp"] is timestamp
    assert columns["source_freshness_seconds"] == 42.0
    assert '"status": "healthy"' in columns["source_health_json"]
    assert at is timestamp


def test_save_urpd_features_refuses_a_row_without_availability_timestamp(caplog):
    repo = QuestDBRepository()
    calls: list[tuple] = []
    repo._send_row = lambda *args, **kwargs: calls.append((args, kwargs)) or True  # type: ignore[attr-defined]
    result = URPDFeaturesResult(
        supply_below_price_pct=72.0,
        supply_above_price_pct=28.0,
        top_bucket_concentration=14.5,
        dominant_bucket_distance_pct=-8.2,
        distribution_entropy=0.84,
        current_price_usd=78000.0,
        bucket_size_usd=5000.0,
        total_supply_btc=18.5,
        block_height=900000,
        timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    assert result.availability_timestamp is None
    with (
        caplog.at_level("ERROR"),
        pytest.raises(ValueError, match="availability_timestamp"),
    ):
        repo.save_urpd_features(result)

    assert calls == []
    assert "availability_timestamp" in caplog.text


def test_get_urpd_features_latest_uses_fetchrow():
    repo = QuestDBRepository()
    expected = {"block_height": 900000}
    repo.fetchrow = AsyncMock(return_value=expected)  # type: ignore[method-assign]

    row = asyncio.run(repo.get_urpd_features_latest())

    assert row == expected
    repo.fetchrow.assert_awaited_once()
    query = repo.fetchrow.await_args.args[0]
    assert "FROM urpd_features_daily" in query
    assert "ORDER BY ts DESC" in query
    assert "LIMIT 1" in query
    assert "LATEST ON ts" not in query


def test_get_feature_bundle_history_pages_oldest_first():
    repo = QuestDBRepository()
    repo.fetch = AsyncMock(return_value=[{"sequence_id": 101}])  # type: ignore[method-assign]

    rows = asyncio.run(
        repo.get_feature_bundle_history(
            "btc_core_live.v1",
            limit=51,
            after_sequence_id=100,
        )
    )

    assert rows == [{"sequence_id": 101}]
    repo.fetch.assert_awaited_once()
    query = repo.fetch.await_args.args[0]
    assert "bundle_id = 'btc_core_live.v1'" in query
    assert "AND sequence_id > 100" in query
    assert "ORDER BY sequence_id ASC, produced_at ASC" in query
    assert "LIMIT 51" in query


def test_get_latest_feature_bundle_uses_order_by_limit_not_latest_on():
    repo = QuestDBRepository()
    expected = {"sequence_id": 102}
    repo.fetchrow = AsyncMock(return_value=expected)  # type: ignore[method-assign]

    row = asyncio.run(repo.get_latest_feature_bundle("btc_core_live.v1"))

    assert row == expected
    repo.fetchrow.assert_awaited_once()
    query = repo.fetchrow.await_args.args[0]
    assert "FROM btc_feature_bundles" in query
    assert "bundle_id = 'btc_core_live.v1'" in query
    assert "ORDER BY sequence_id DESC, produced_at DESC" in query
    assert "LIMIT 1" in query
    assert "LATEST ON ts" not in query


def test_get_recent_feature_bundle_sequence_pages_newest_first():
    repo = QuestDBRepository()
    repo.fetch = AsyncMock(return_value=[{"sequence_id": 102}, {"sequence_id": 101}])  # type: ignore[method-assign]

    rows = asyncio.run(
        repo.get_recent_feature_bundle_sequence("btc_core_live.v1", limit=2)
    )

    assert rows == [{"sequence_id": 102}, {"sequence_id": 101}]
    repo.fetch.assert_awaited_once()
    query = repo.fetch.await_args.args[0]
    assert "bundle_id = 'btc_core_live.v1'" in query
    assert "ORDER BY sequence_id DESC, produced_at DESC" in query
    assert "LIMIT 2" in query


def test_get_latest_signal_snapshot_uses_order_by_limit_not_latest_on():
    repo = QuestDBRepository()
    expected = {"sequence_id": 8}
    repo.fetchrow = AsyncMock(return_value=expected)  # type: ignore[method-assign]

    row = asyncio.run(repo.get_latest_signal_snapshot())

    assert row == expected
    repo.fetchrow.assert_awaited_once()
    query = repo.fetchrow.await_args.args[0]
    assert "FROM btc_signal_snapshots" in query
    assert "WHERE schema_version = 'v1'" in query
    assert "ORDER BY sequence_id DESC, produced_at DESC" in query
    assert "LIMIT 1" in query
    assert "LATEST ON ts" not in query


def test_get_recent_signal_sequence_pages_newest_first():
    repo = QuestDBRepository()
    repo.fetch = AsyncMock(return_value=[{"sequence_id": 8}, {"sequence_id": 7}])  # type: ignore[method-assign]

    rows = asyncio.run(repo.get_recent_signal_sequence(limit=2))

    assert rows == [{"sequence_id": 8}, {"sequence_id": 7}]
    repo.fetch.assert_awaited_once()
    query = repo.fetch.await_args.args[0]
    assert "FROM btc_signal_snapshots" in query
    assert "WHERE schema_version = 'v1'" in query
    assert "ORDER BY sequence_id DESC, produced_at DESC" in query
    assert "LIMIT 2" in query


class _FakePool:
    """Stands in for an asyncpg pool; `closed` counts close() calls per pool."""

    def __init__(self) -> None:
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


def _stub_pool_creation(monkeypatch, pools: list[_FakePool]) -> None:
    """Replace everything initialize() would send to a real QuestDB; create_pool yields once."""
    import types

    import api.questdb_repository as repository

    async def no_tables() -> None:
        return None

    async def create_pool(**_kwargs) -> _FakePool:
        await asyncio.sleep(0)  # the await between the None check and the assignment
        pool = _FakePool()
        pools.append(pool)
        return pool

    monkeypatch.setattr(repository, "create_tables_if_not_exist", no_tables)
    monkeypatch.setattr(
        repository, "asyncpg", types.SimpleNamespace(create_pool=create_pool)
    )
    monkeypatch.setattr(QuestDBRepository, "_ensure_sender", lambda self: None)
    monkeypatch.setattr(QuestDBRepository, "_pool", None, raising=False)


def test_concurrent_initialize_creates_a_single_pool(monkeypatch):
    """F-399 M2: the None check and the assignment of the class pool are separated by an await."""
    pools: list[_FakePool] = []
    _stub_pool_creation(monkeypatch, pools)
    first, second = QuestDBRepository(), QuestDBRepository()

    async def scenario() -> None:
        await asyncio.gather(first.initialize(), second.initialize())

    asyncio.run(scenario())

    assert len(pools) == 1
    assert QuestDBRepository._pool is pools[0]


def test_initialize_from_two_event_loops_in_sequence_does_not_raise(monkeypatch):
    """The pool lock is bound to the running loop: a later loop (sync store callers) gets its own."""
    pools: list[_FakePool] = []
    _stub_pool_creation(monkeypatch, pools)

    asyncio.run(QuestDBRepository().initialize())
    monkeypatch.setattr(
        QuestDBRepository, "_pool", None, raising=False
    )  # as after a close()
    asyncio.run(QuestDBRepository().initialize())

    assert len(pools) == 2


def test_same_loop_stays_excluded_while_another_loop_takes_its_own_lock(monkeypatch):
    """A second loop (a thread running asyncio.run) must not replace the main loop's lock (F-399)."""
    import threading

    import types

    import api.questdb_repository as repository

    main_calls = 0
    thread_in_pool = threading.Event()
    release_thread = threading.Event()

    async def no_tables() -> None:
        return None

    async def scenario() -> int:
        nonlocal main_calls
        main_loop = asyncio.get_running_loop()
        a_in_pool = asyncio.Event()
        main_gate = asyncio.Event()

        async def create_pool(**_kwargs) -> _FakePool:
            nonlocal main_calls
            loop = asyncio.get_running_loop()
            if loop is main_loop:
                main_calls += 1
                a_in_pool.set()
                await main_gate.wait()
            else:
                thread_in_pool.set()
                await loop.run_in_executor(None, release_thread.wait)
            return _FakePool()

        monkeypatch.setattr(repository, "create_tables_if_not_exist", no_tables)
        monkeypatch.setattr(
            repository, "asyncpg", types.SimpleNamespace(create_pool=create_pool)
        )
        monkeypatch.setattr(QuestDBRepository, "_ensure_sender", lambda self: None)
        monkeypatch.setattr(QuestDBRepository, "_pool", None, raising=False)

        first = asyncio.create_task(QuestDBRepository().initialize())
        await a_in_pool.wait()  # the main loop's lock is held, inside create_pool

        other = threading.Thread(
            target=lambda: asyncio.run(QuestDBRepository().initialize())
        )
        other.start()
        await main_loop.run_in_executor(
            None, thread_in_pool.wait
        )  # other loop has its lock

        second = asyncio.create_task(QuestDBRepository().initialize())
        for _ in range(10):  # let the second caller reach the lock
            await asyncio.sleep(0)
        seen_while_blocked = main_calls

        main_gate.set()
        release_thread.set()
        await asyncio.gather(first, second)
        other.join()
        return seen_while_blocked

    seen_while_blocked = asyncio.run(scenario())

    assert seen_while_blocked == 1  # the second main-loop caller was still excluded
    assert main_calls == 1
