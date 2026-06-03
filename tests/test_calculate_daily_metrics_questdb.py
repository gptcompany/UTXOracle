"""Dual-write tests for calculate_daily_metrics (spec-061 US2 T017-T020).

These tests run RED until:
  - `api.questdb_repository.save_mvrv_daily`,
    `save_nupl_daily`, `save_realized_cap_daily` exist (T022)
  - `scripts.metrics.calculate_daily_metrics.persist_metrics` calls
    `_persist_to_questdb` after the DuckDB writes (T023)

The QuestDB layer is fully mocked - no live infrastructure required.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_metrics() -> dict:
    """Single-day metrics dict shaped like calculate_daily_metrics output."""
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
    """Minimal DuckDB connection stub used by the existing DuckDB writes."""
    conn = MagicMock()
    # mvrv_daily PRAGMA table_info shape (column index 1 is name)
    conn.execute.return_value.fetchall.return_value = [
        (0, "date"),
        (1, "mvrv"),
        (2, "mvrv_z"),
        (3, "market_cap"),
        (4, "realized_cap"),
    ]
    return conn


def _persist(metrics: dict, duckdb_conn: MagicMock):
    """Helper: import persist_metrics fresh and call it."""
    from scripts.metrics.calculate_daily_metrics import persist_metrics

    persist_metrics(metrics, duckdb_conn)


# T017: dual-write mvrv


def test_dual_write_mvrv(fake_metrics, duckdb_conn):
    """T017: persist_metrics MUST call save_mvrv_daily after DuckDB write."""
    with (
        patch(
            "scripts.metrics.calculate_daily_metrics.save_mvrv_daily",
            MagicMock(return_value=True),
        ) as save_mvrv,
        patch(
            "scripts.metrics.calculate_daily_metrics.save_nupl_daily",
            MagicMock(return_value=True),
        ),
        patch(
            "scripts.metrics.calculate_daily_metrics.save_realized_cap_daily",
            MagicMock(return_value=True),
        ),
    ):
        _persist(fake_metrics, duckdb_conn)

    save_mvrv.assert_called_once()
    kwargs = save_mvrv.call_args.kwargs or {}
    args = save_mvrv.call_args.args
    payload = {
        **dict(zip(["ts", "mvrv", "mvrv_z", "market_cap", "realized_cap"], args)),
        **kwargs,
    }
    assert payload.get("mvrv") == fake_metrics["mvrv"]


# T018: dual-write nupl


def test_dual_write_nupl(fake_metrics, duckdb_conn):
    """T018: persist_metrics MUST call save_nupl_daily after DuckDB write."""
    with (
        patch(
            "scripts.metrics.calculate_daily_metrics.save_mvrv_daily",
            MagicMock(return_value=True),
        ),
        patch(
            "scripts.metrics.calculate_daily_metrics.save_nupl_daily",
            MagicMock(return_value=True),
        ) as save_nupl,
        patch(
            "scripts.metrics.calculate_daily_metrics.save_realized_cap_daily",
            MagicMock(return_value=True),
        ),
    ):
        _persist(fake_metrics, duckdb_conn)

    save_nupl.assert_called_once()
    args = save_nupl.call_args.args
    kwargs = save_nupl.call_args.kwargs or {}
    payload = {
        **dict(zip(["ts", "nupl", "market_cap", "realized_cap"], args)),
        **kwargs,
    }
    assert payload.get("nupl") == fake_metrics["nupl"]


# T019: dual-write realized_cap


def test_dual_write_realized_cap(fake_metrics, duckdb_conn):
    """T019: persist_metrics MUST call save_realized_cap_daily after DuckDB write."""
    with (
        patch(
            "scripts.metrics.calculate_daily_metrics.save_mvrv_daily",
            MagicMock(return_value=True),
        ),
        patch(
            "scripts.metrics.calculate_daily_metrics.save_nupl_daily",
            MagicMock(return_value=True),
        ),
        patch(
            "scripts.metrics.calculate_daily_metrics.save_realized_cap_daily",
            MagicMock(return_value=True),
        ) as save_rc,
    ):
        _persist(fake_metrics, duckdb_conn)

    save_rc.assert_called_once()
    args = save_rc.call_args.args
    kwargs = save_rc.call_args.kwargs or {}
    payload = {**dict(zip(["ts", "realized_cap"], args)), **kwargs}
    assert payload.get("realized_cap") == fake_metrics["realized_cap"]


# T020: QuestDB failure does NOT block DuckDB


def test_questdb_failure_does_not_block_duckdb(fake_metrics, duckdb_conn, caplog):
    """T020: a QuestDB save raising MUST NOT roll back the DuckDB writes.

    The DuckDB execute calls must still happen, and the exception must be
    logged at ERROR (or WARNING) level rather than re-raised. Per
    research.md R5 strangler-fig.
    """

    def boom(*args, **kwargs):
        raise ConnectionError("simulated QuestDB pool failure")

    with (
        patch(
            "scripts.metrics.calculate_daily_metrics.save_mvrv_daily",
            MagicMock(side_effect=boom),
        ),
        patch(
            "scripts.metrics.calculate_daily_metrics.save_nupl_daily",
            MagicMock(side_effect=boom),
        ),
        patch(
            "scripts.metrics.calculate_daily_metrics.save_realized_cap_daily",
            MagicMock(side_effect=boom),
        ),
    ):
        # Should not raise.
        _persist(fake_metrics, duckdb_conn)

    # DuckDB must have received the INSERTs (at least one execute call).
    assert duckdb_conn.execute.called, (
        "DuckDB writes were skipped - strangler-fig violated"
    )
    assert "QuestDB save_mvrv_daily failed" in caplog.text
    assert "QuestDB save_nupl_daily failed" in caplog.text
    assert "QuestDB save_realized_cap_daily failed" in caplog.text


def test_questdb_only_skips_duckdb_writes(fake_metrics, duckdb_conn):
    """The systemd timer can mirror QuestDB rows while DuckDB is writer-locked."""
    from scripts.metrics.calculate_daily_metrics import persist_metrics_for_target

    with (
        patch(
            "scripts.metrics.calculate_daily_metrics._persist_to_questdb",
            MagicMock(return_value=None),
        ) as persist_qdb,
        patch(
            "scripts.metrics.calculate_daily_metrics.persist_metrics",
            MagicMock(side_effect=AssertionError("DuckDB write path used")),
        ) as persist_duckdb,
    ):
        persist_metrics_for_target(fake_metrics, duckdb_conn, questdb_only=True)

    persist_qdb.assert_called_once_with(fake_metrics)
    persist_duckdb.assert_not_called()
    duckdb_conn.execute.assert_not_called()
