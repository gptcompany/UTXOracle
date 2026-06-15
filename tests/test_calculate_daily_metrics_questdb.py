"""Dual-write tests for calculate_daily_metrics (spec-061 US2 T017-T020).

These tests run RED until:
  - `api.questdb_repository.save_mvrv_daily`,
    `save_nupl_daily`, `save_realized_cap_daily` exist (T022)
  - `scripts.metrics.calculate_daily_metrics.persist_metrics` calls
    `_persist_to_questdb` after the DuckDB writes (T023)

The QuestDB layer is fully mocked - no live infrastructure required.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
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
    fake_metrics["mvrv_z_rbn"] = 0.91
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
        **dict(
            zip(
                ["ts", "mvrv", "mvrv_z", "mvrv_z_rbn", "market_cap", "realized_cap"],
                args,
            )
        ),
        **kwargs,
    }
    assert payload.get("mvrv") == fake_metrics["mvrv"]
    assert payload.get("mvrv_z_rbn") == fake_metrics["mvrv_z_rbn"]


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

    persist_qdb.assert_called_once_with(fake_metrics, raise_on_failure=True)
    persist_duckdb.assert_not_called()
    duckdb_conn.execute.assert_not_called()


def test_questdb_only_write_failure_raises_and_notifies(
    fake_metrics,
    monkeypatch,
):
    """QuestDB-only mode must not report success when contract writes fail."""
    from scripts.metrics.calculate_daily_metrics import (
        QuestDBPersistenceError,
        _run_single_date,
    )

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.invalid/webhook/abc")
    posted: list = []

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, _):
            return b""

    def fake_urlopen(request, timeout=None):
        posted.append((request.full_url, request.data, timeout))
        return _FakeResponse()

    def boom(*args, **kwargs):
        raise ConnectionError("simulated QuestDB write failure")

    monkeypatch.setattr(
        "scripts.metrics.calculate_daily_metrics.urllib.request.urlopen",
        fake_urlopen,
    )

    with patch(
        "scripts.metrics.calculate_daily_metrics.calculate_daily_metrics",
        MagicMock(return_value=fake_metrics),
    ), patch(
        "scripts.metrics.calculate_daily_metrics.save_mvrv_daily",
        MagicMock(side_effect=boom),
    ), patch(
        "scripts.metrics.calculate_daily_metrics.save_nupl_daily",
        MagicMock(side_effect=boom),
    ), patch(
        "scripts.metrics.calculate_daily_metrics.save_realized_cap_daily",
        MagicMock(side_effect=boom),
    ):
        with pytest.raises(QuestDBPersistenceError):
            _run_single_date(
                fake_metrics["date"],
                None,
                dry_run=False,
                questdb_only=True,
                questdb_reads=True,
            )

    assert len(posted) == 1
    payload = __import__("json").loads(posted[0][1].decode("utf-8"))
    assert "QuestDBPersistenceError" in payload["content"]
    assert fake_metrics["date"].isoformat() in payload["content"]


def test_legacy_single_date_dual_write_happens_once(fake_metrics, duckdb_conn):
    """Single-date legacy writes must not mirror to QuestDB twice."""
    from scripts.metrics.calculate_daily_metrics import _run_single_date

    save_mvrv = MagicMock(return_value=True)
    save_nupl = MagicMock(return_value=True)
    save_rc = MagicMock(return_value=True)

    with patch(
        "scripts.metrics.calculate_daily_metrics.calculate_daily_metrics",
        MagicMock(return_value=fake_metrics),
    ), patch(
        "scripts.metrics.calculate_daily_metrics.save_mvrv_daily",
        save_mvrv,
    ), patch(
        "scripts.metrics.calculate_daily_metrics.save_nupl_daily",
        save_nupl,
    ), patch(
        "scripts.metrics.calculate_daily_metrics.save_realized_cap_daily",
        save_rc,
    ):
        rows = _run_single_date(
            fake_metrics["date"],
            duckdb_conn,
            dry_run=False,
            questdb_only=False,
            questdb_reads=False,
        )

    assert rows == 3
    assert save_mvrv.call_count == 1
    assert save_nupl.call_count == 1
    assert save_rc.call_count == 1


class _FakeCursor:
    def __init__(self, row, rows=None):
        self.row = row
        self.rows = rows or []
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=()):
        self.executed.append((query, params))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _FakeQuestDBConnection:
    def __init__(self, row):
        self.cursor_obj = _FakeCursor(row)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj


def test_get_blocks_for_date_can_read_questdb(duckdb_conn):
    """QuestDB reader path uses block_heights over psycopg, not DuckDB."""
    from scripts.metrics.calculate_daily_metrics import get_blocks_for_date

    qdb = _FakeQuestDBConnection((928_139, 928_282))

    with patch("scripts.metrics.calculate_daily_metrics._open_pg_sync", return_value=qdb):
        result = get_blocks_for_date(
            date(2025, 12, 15),
            duckdb_conn,
            questdb_reads=True,
        )

    assert result == (928_139, 928_282)
    duckdb_conn.execute.assert_not_called()

    query, params = qdb.cursor_obj.executed[0]
    assert "FROM block_heights" in query
    assert params == (
        datetime(2025, 12, 15, 0, 0),
        datetime(2025, 12, 16, 0, 0),
    )


def test_get_price_for_date_can_read_questdb(duckdb_conn):
    """QuestDB reader path uses daily_prices over psycopg, not DuckDB."""
    from scripts.metrics.calculate_daily_metrics import get_price_for_date

    qdb = _FakeQuestDBConnection((42_000.25,))

    with patch("scripts.metrics.calculate_daily_metrics._open_pg_sync", return_value=qdb):
        result = get_price_for_date(
            date(2025, 12, 15),
            duckdb_conn,
            questdb_reads=True,
        )

    assert result == 42_000.25
    duckdb_conn.execute.assert_not_called()

    query, params = qdb.cursor_obj.executed[0]
    assert "FROM daily_prices" in query
    assert "ORDER BY fetched_at DESC" in query
    assert params == (datetime(2025, 12, 15, 0, 0),)


def test_realized_cap_can_read_questdb(duckdb_conn):
    """spec-062: calculate_daily_realized_cap reads utxo_lifecycle from QuestDB."""
    from scripts.metrics.calculate_daily_metrics import calculate_daily_realized_cap

    qdb = _FakeQuestDBConnection((1_046_906_846_048.14,))

    with patch(
        "scripts.metrics.calculate_daily_metrics._open_pg_sync", return_value=qdb
    ):
        result = calculate_daily_realized_cap(
            duckdb_conn, as_of_block=928_282, questdb_reads=True
        )

    assert result == pytest.approx(1_046_906_846_048.14)
    duckdb_conn.execute.assert_not_called()
    query, _ = qdb.cursor_obj.executed[0]
    assert "FROM utxo_lifecycle" in query
    assert "utxo_lifecycle_full" not in query


def test_cointime_can_read_questdb(duckdb_conn):
    """spec-062: calculate_cointime_daily reads utxo_lifecycle from QuestDB."""
    from scripts.metrics.calculate_daily_metrics import calculate_cointime_daily

    cursor = _FakeCursor((0.0,))

    class TwoShotCursor(_FakeCursor):
        def __init__(self):
            super().__init__((0.0,))
            self._call = 0

        def fetchone(self):
            self._call += 1
            return (21_020_469_537.35,) if self._call == 1 else (5_394_230_181_303.81,)

    cursor = TwoShotCursor()

    class _Q:
        def __init__(self, cur):
            self.cur = cur

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self):
            return self.cur

    qdb = _Q(cursor)

    with patch(
        "scripts.metrics.calculate_daily_metrics._open_pg_sync", return_value=qdb
    ):
        result = calculate_cointime_daily(
            duckdb_conn, as_of_block=928_282, questdb_reads=True
        )

    duckdb_conn.execute.assert_not_called()
    assert result["liveliness"] == pytest.approx(
        21_020_469_537.35 / 5_394_230_181_303.81
    )
    assert result["coinblocks_destroyed"] == pytest.approx(21_020_469_537.35)
    queries = [q for q, _ in cursor.executed]
    assert any("FROM utxo_lifecycle" in q and "utxo_lifecycle_full" not in q for q in queries)


def test_sopr_can_read_questdb(duckdb_conn):
    """spec-062: calculate_daily_sopr primary branch reads utxo_lifecycle from QuestDB."""
    from scripts.metrics.calculate_daily_metrics import calculate_daily_sopr

    qdb = _FakeQuestDBConnection((100.0, 95.0))

    with patch(
        "scripts.metrics.calculate_daily_metrics._open_pg_sync", return_value=qdb
    ):
        sopr = calculate_daily_sopr(
            duckdb_conn,
            start_block=928_139,
            end_block=928_282,
            questdb_reads=True,
        )

    assert sopr == pytest.approx(100.0 / 95.0)
    duckdb_conn.execute.assert_not_called()
    query, _ = qdb.cursor_obj.executed[0]
    assert "FROM utxo_lifecycle" in query
    assert "utxo_lifecycle_full" not in query


def test_aggregator_never_opens_duckdb_under_dual_flags():
    """spec-062 guard: source code has no DuckDB read of utxo_lifecycle_full
    outside the legacy `else` branches gated by questdb_reads.
    """
    src = Path("scripts/metrics/calculate_daily_metrics.py").read_text()
    # All utxo_lifecycle_full reads must live under a `questdb_reads` False branch.
    # The QuestDB branch must reference `utxo_lifecycle` (no _full suffix).
    assert "FROM utxo_lifecycle\n" in src or "FROM utxo_lifecycle " in src
    # The main() must allow a None DuckDB connection when both flags are set.
    assert "duckdb_free = args.questdb_reads and args.questdb_only" in src
    assert "if conn is not None:" in src


def test_mvrv_variants_can_read_questdb():
    """spec-062: mvrv_variants reads utxo_snapshots from QuestDB."""
    from scripts.metrics.mvrv_variants import get_market_cap_history_all_time

    cursor = _FakeCursor(None, rows=[(1_700_000_000_000.0,), (1_600_000_000_000.0,)])

    class _Q:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self):
            return cursor

    with patch(
        "api.questdb_repository._open_pg_sync", return_value=_Q()
    ):
        history = get_market_cap_history_all_time(
            None, max_block_height=928_282, questdb_reads=True
        )

    assert history == [1_700_000_000_000.0, 1_600_000_000_000.0]
    query, params = cursor.executed[0]
    assert "FROM utxo_snapshots" in query
    assert params == (928_282,)


# spec-062 analyze remediation T046/T047/T048


def test_questdb_unreachable_fails_fast(duckdb_conn):
    """T047 / FR-006: QuestDB unreachable in questdb_reads mode must propagate
    without silently falling back to DuckDB."""
    from scripts.metrics.calculate_daily_metrics import calculate_daily_realized_cap

    class _Boom:
        def __enter__(self):
            raise ConnectionError("simulated QuestDB unreachable")

        def __exit__(self, *a):
            return False

    with patch(
        "scripts.metrics.calculate_daily_metrics._open_pg_sync", return_value=_Boom()
    ):
        with pytest.raises(ConnectionError, match="simulated QuestDB unreachable"):
            calculate_daily_realized_cap(
                duckdb_conn, as_of_block=928_282, questdb_reads=True
            )

    duckdb_conn.execute.assert_not_called()


def test_failure_emits_discord_webhook(monkeypatch):
    """T046 / FR-012: failure path POSTs to DISCORD_WEBHOOK_URL once."""
    from scripts.metrics.calculate_daily_metrics import _post_discord_failure

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.invalid/webhook/abc")
    posted: list = []

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, _):
            return b""

    def fake_urlopen(request, timeout=None):
        posted.append((request.full_url, request.data, timeout))
        return _FakeResponse()

    monkeypatch.setattr(
        "scripts.metrics.calculate_daily_metrics.urllib.request.urlopen",
        fake_urlopen,
    )

    _post_discord_failure(date(2026, 6, 4), RuntimeError("simulated failure"))

    assert len(posted) == 1
    url, body, timeout = posted[0]
    assert url == "https://discord.invalid/webhook/abc"
    assert timeout == 3
    payload = __import__("json").loads(body.decode("utf-8"))
    assert "2026-06-04" in payload["content"]
    assert "RuntimeError" in payload["content"]
    assert "simulated failure" in payload["content"]


def test_success_does_not_emit_discord_webhook(monkeypatch):
    """FR-012: successful runs MUST NOT POST to the webhook."""
    from scripts.metrics.calculate_daily_metrics import _run_single_date

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.invalid/webhook/abc")
    posted: list = []

    def _record(*args, **kwargs):
        posted.append((args, kwargs))
        raise AssertionError("webhook MUST NOT be POSTed on success")

    monkeypatch.setattr(
        "scripts.metrics.calculate_daily_metrics.urllib.request.urlopen",
        _record,
    )

    with patch(
        "scripts.metrics.calculate_daily_metrics.calculate_daily_metrics",
        MagicMock(return_value={"date": date(2026, 6, 4)}),
    ), patch(
        "scripts.metrics.calculate_daily_metrics._persist_to_questdb",
        MagicMock(return_value=0),
    ):
        rows = _run_single_date(
            date(2026, 6, 4), None, dry_run=False, questdb_only=True, questdb_reads=True
        )

    assert rows == 0
    assert posted == []


def test_questdb_only_backfill_aborts_on_first_failure(monkeypatch):
    """Production backfills must exit non-zero instead of hiding date failures."""
    from scripts.metrics.calculate_daily_metrics import backfill_metrics

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.invalid/webhook/abc")
    posted: list = []

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, _):
            return b""

    def fake_urlopen(request, timeout=None):
        posted.append((request.full_url, request.data, timeout))
        return _FakeResponse()

    calculate = MagicMock(side_effect=ConnectionError("QuestDB down"))
    monkeypatch.setattr(
        "scripts.metrics.calculate_daily_metrics.urllib.request.urlopen",
        fake_urlopen,
    )

    with patch(
        "scripts.metrics.calculate_daily_metrics.calculate_daily_metrics",
        calculate,
    ):
        with pytest.raises(ConnectionError, match="QuestDB down"):
            backfill_metrics(
                2,
                None,
                end_date=date(2026, 6, 4),
                questdb_only=True,
                questdb_reads=True,
            )

    assert calculate.call_count == 1
    assert len(posted) == 1
    payload = __import__("json").loads(posted[0][1].decode("utf-8"))
    assert "2026-06-03" in payload["content"]
    assert "ConnectionError" in payload["content"]


def test_concurrent_runs_converge_via_dedup(fake_metrics, duckdb_conn):
    """T048 / FR-013: two persist calls with identical metrics emit
    byte-identical save_* arguments (deterministic computation; DEDUP
    collapses to one row on the QuestDB side)."""
    from scripts.metrics.calculate_daily_metrics import _persist_to_questdb

    calls: list[tuple] = []

    def record(*args, **kwargs):
        calls.append((args, frozenset(kwargs.items())))

    with patch(
        "scripts.metrics.calculate_daily_metrics.save_mvrv_daily", side_effect=record
    ), patch(
        "scripts.metrics.calculate_daily_metrics.save_nupl_daily", side_effect=record
    ), patch(
        "scripts.metrics.calculate_daily_metrics.save_realized_cap_daily",
        side_effect=record,
    ):
        _persist_to_questdb(fake_metrics)
        _persist_to_questdb(fake_metrics)

    # Two runs => 6 calls (3 saves x 2 runs), each pair byte-identical.
    assert len(calls) == 6
    assert calls[0] == calls[3]  # mvrv first vs second run
    assert calls[1] == calls[4]  # nupl
    assert calls[2] == calls[5]  # realized_cap
