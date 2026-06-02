"""Idempotency test for the dual-write path (spec-061 US2 T023b, FR-010).

A same-day re-run MUST produce identical rows in mvrv_daily, nupl_daily,
realized_cap_daily - no row-count drift, no semantic mutation. Fully
mocked: we drive persist_metrics twice for the same date with identical
inputs and assert the QuestDB save calls receive identical payloads each
time (the producer's job is to be deterministic; the storage layer's
dedup contract is exercised by T022a + DDL DEDUP UPSERT KEYS).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def metrics() -> dict:
    return {
        "date": date(2026, 5, 30),
        "sopr": 1.02,
        "nupl": 0.45,
        "mvrv": 2.1,
        "mvrv_z": 1.8,
        "mvrv_z_rbn": None,
        "market_cap": 1_900_000_000_000.0,
        "realized_cap": 900_000_000_000.0,
        "total_supply": 19_700_000.0,
        "liveliness": 0.6,
        "vaultedness": 0.4,
        "activity_to_vaultedness_ratio": 1.5,
    }


@pytest.fixture
def duckdb_conn() -> MagicMock:
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        (0, "date"),
        (1, "mvrv"),
        (2, "mvrv_z"),
        (3, "market_cap"),
        (4, "realized_cap"),
    ]
    return conn


def test_same_day_double_run(metrics, duckdb_conn):
    """T023b: persist_metrics called twice for the same date must emit identical save calls."""
    from scripts.metrics.calculate_daily_metrics import persist_metrics

    save_mvrv = MagicMock(return_value=True)
    save_nupl = MagicMock(return_value=True)
    save_rc = MagicMock(return_value=True)

    with (
        patch("scripts.metrics.calculate_daily_metrics.save_mvrv_daily", save_mvrv),
        patch("scripts.metrics.calculate_daily_metrics.save_nupl_daily", save_nupl),
        patch(
            "scripts.metrics.calculate_daily_metrics.save_realized_cap_daily", save_rc
        ),
    ):
        persist_metrics(dict(metrics), duckdb_conn)
        persist_metrics(dict(metrics), duckdb_conn)

    # Each save was called exactly twice
    assert save_mvrv.call_count == 2
    assert save_nupl.call_count == 2
    assert save_rc.call_count == 2

    # Both calls must be byte-identical (deterministic producer per FR-010)
    assert save_mvrv.call_args_list[0] == save_mvrv.call_args_list[1]
    assert save_nupl.call_args_list[0] == save_nupl.call_args_list[1]
    assert save_rc.call_args_list[0] == save_rc.call_args_list[1]


class _FakeCursor:
    def __init__(self, captured: list[tuple[str, tuple]]):
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str, params: tuple):
        self._captured.append((query, params))


class _FakeConnection:
    def __init__(self, captured: list[tuple[str, tuple]]):
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self._captured)


def test_sync_save_methods_use_deterministic_created_at(monkeypatch):
    """T023b/FR-010: same input row must produce identical QuestDB INSERT params."""
    from datetime import datetime, timezone

    import api.questdb_repository as repo

    captured: list[tuple[str, tuple]] = []

    def fake_open_pg_sync():
        return _FakeConnection(captured)

    monkeypatch.setattr(repo, "_open_pg_sync", fake_open_pg_sync)
    ts = datetime(2026, 5, 30, tzinfo=timezone.utc)

    repo.save_mvrv_daily(ts, 2.1, mvrv_z=1.8, market_cap=100.0, realized_cap=50.0)
    repo.save_mvrv_daily(ts, 2.1, mvrv_z=1.8, market_cap=100.0, realized_cap=50.0)
    repo.save_backtest_whale_signal_row(ts, net_flow_btc=0.5, confidence=0.8)
    repo.save_backtest_whale_signal_row(ts, net_flow_btc=0.5, confidence=0.8)

    assert captured[0][1] == captured[1][1]
    assert captured[2][1] == captured[3][1]
    assert captured[0][1][-1] == ts
    assert captured[2][1][-1] == ts
