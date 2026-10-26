from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from api.questdb_repository import QuestDBRepository
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


def _repo_with_staging_count(counts, execute=None):
    repo = QuestDBRepository()
    repo.async_flush_ingestion = AsyncMock(return_value=True)
    repo.fetchrow = AsyncMock(side_effect=[(c,) for c in counts] + [(counts[-1],)] * 50)
    repo.execute = execute or AsyncMock(return_value="OK")
    return repo


def test_commit_address_clusters_refresh_runs_cutover_after_flush():
    repo = _repo_with_staging_count([2, 5])

    assert asyncio.run(repo.commit_address_clusters_refresh(5, poll_s=0)) is True

    calls = [call.args[0] for call in repo.execute.await_args_list]
    assert calls[0] == "TRUNCATE TABLE address_clusters"
    insert = " ".join(calls[1].split())
    assert insert.startswith(
        "INSERT INTO address_clusters (address, cluster_id, ts, last_seen, "
        "is_exchange_likely, label, confidence) SELECT address, cluster_id, ts, "
        "last_seen, is_exchange_likely, label, confidence FROM address_clusters_staging"
    )
    assert calls[2] == "TRUNCATE TABLE address_clusters_staging"


def test_commit_address_clusters_refresh_aborts_without_touching_live_when_staging_short(
    caplog,
):
    repo = _repo_with_staging_count([3])

    with caplog.at_level("ERROR"):
        ok = asyncio.run(
            repo.commit_address_clusters_refresh(5, timeout_s=0.05, poll_s=0.01)
        )

    assert ok is False
    calls = [call.args[0] for call in repo.execute.await_args_list]
    assert calls == ["TRUNCATE TABLE address_clusters_staging"]
    assert not any("INSERT" in q for q in calls)
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert any("expected 5" in m and "observed 3" in m for m in errors)


def test_commit_address_clusters_refresh_clears_tables_on_cutover_failure():
    repo = _repo_with_staging_count(
        [5],
        AsyncMock(
            side_effect=["TRUNCATE", RuntimeError("boom"), "TRUNCATE", "TRUNCATE"]
        ),
    )

    assert asyncio.run(repo.commit_address_clusters_refresh(5, poll_s=0)) is False

    calls = [call.args[0] for call in repo.execute.await_args_list]
    assert calls[0] == "TRUNCATE TABLE address_clusters"
    assert "INSERT INTO address_clusters" in calls[1]
    assert calls[2] == "TRUNCATE TABLE address_clusters_staging"
    assert calls[3] == "TRUNCATE TABLE address_clusters"


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
