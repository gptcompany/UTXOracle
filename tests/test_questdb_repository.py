from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from api.questdb_repository import QuestDBRepository
from scripts.models.metrics_models import CostBasisResult


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


def test_commit_address_clusters_refresh_runs_cutover_after_flush():
    repo = QuestDBRepository()
    repo.async_flush_ingestion = AsyncMock(return_value=True)
    repo.execute = AsyncMock(return_value="OK")

    assert asyncio.run(repo.commit_address_clusters_refresh()) is True

    calls = repo.execute.await_args_list
    assert calls[0].args == ("TRUNCATE TABLE address_clusters",)
    assert "INSERT INTO address_clusters" in calls[1].args[0]
    assert "FROM address_clusters_staging" in calls[1].args[0]
    assert calls[2].args == ("TRUNCATE TABLE address_clusters_staging",)


def test_commit_address_clusters_refresh_clears_tables_on_cutover_failure():
    repo = QuestDBRepository()
    repo.async_flush_ingestion = AsyncMock(return_value=True)
    repo.execute = AsyncMock(
        side_effect=["TRUNCATE", RuntimeError("boom"), "TRUNCATE", "TRUNCATE"]
    )

    assert asyncio.run(repo.commit_address_clusters_refresh()) is False

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

    assert row is expected
    repo.fetchrow.assert_awaited_once()
    query = repo.fetchrow.await_args.args[0]
    assert "FROM cost_basis_daily" in query
    assert "LATEST ON ts" in query
