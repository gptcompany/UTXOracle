"""Tests for the post-mirror integrity check (spec-061 F1+F3 mitigation).

F1 in the 2026-06-02 code review:
    The mirror checkpoint advances at the block-batch boundary, not after
    each row INSERT. A crash mid-chunk after partial inserts → resume
    re-issues those inserts → duplicate `outpoint` rows in QuestDB.

F3 was the missing test gap that would expose F1 explicitly. This module:
    - simulates a "clean" mirror (no duplicates) and asserts the verify
      script reports OK,
    - simulates a "F1-materialised" mirror (duplicates present) and
      asserts the verify script flags it,
    - simulates --fix and asserts duplicates are removed.

Fully mocked — no live QuestDB required.
"""

from __future__ import annotations


class _FakeCursor:
    """Captures executed SQL and returns canned scalar results."""

    def __init__(self, scripted: list[int]):
        self._scripted = list(scripted)
        self.executed: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str):
        self.executed.append(query)

    def fetchone(self):
        value = self._scripted.pop(0) if self._scripted else 0
        return (value,)


class _FakeConnection:
    def __init__(self, scripted: list[int]):
        self.cursor_holder = _FakeCursor(scripted)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_holder


def test_verify_reports_clean(monkeypatch):
    """F3 baseline: 100M rows, 100M distinct outpoints → no duplicates."""
    from scripts.bootstrap import verify_utxo_lifecycle_mirror as module

    fake_conn = _FakeConnection([100_000_000, 100_000_000])

    def fake_open():
        return fake_conn

    monkeypatch.setattr(module, "_open_questdb_connection", fake_open)
    report = module.verify()
    assert report.total_rows == 100_000_000
    assert report.distinct_outpoints == 100_000_000
    assert report.duplicate_rows == 0
    assert report.is_clean is True


def test_verify_detects_duplicates_from_f1_materialised(monkeypatch):
    """F3 exposes F1: 100M+5k rows but only 100M distinct outpoints → 5k dups.

    This is exactly the residue of a mid-chunk crash + resume against a
    utxo_lifecycle table without DEDUP UPSERT KEYS. The verify script must
    surface the count loudly so the operator runs --fix before downstream
    consumers read stale-looking creation counts.
    """
    from scripts.bootstrap import verify_utxo_lifecycle_mirror as module

    fake_conn = _FakeConnection([100_005_000, 100_000_000])

    def fake_open():
        return fake_conn

    monkeypatch.setattr(module, "_open_questdb_connection", fake_open)
    report = module.verify()
    assert report.duplicate_rows == 5_000
    assert report.is_clean is False


def test_main_returns_nonzero_when_dups_and_no_fix(monkeypatch, capsys):
    """The CLI exit code must reflect the integrity state for CI scripts."""
    from scripts.bootstrap import verify_utxo_lifecycle_mirror as module

    fake_conn = _FakeConnection([100_005_000, 100_000_000])
    monkeypatch.setattr(module, "_open_questdb_connection", lambda: fake_conn)
    monkeypatch.setattr("sys.argv", ["verify_utxo_lifecycle_mirror"])

    code = module.main()
    assert code == 1


def test_main_clean_returns_zero(monkeypatch):
    from scripts.bootstrap import verify_utxo_lifecycle_mirror as module

    fake_conn = _FakeConnection([100_000_000, 100_000_000])
    monkeypatch.setattr(module, "_open_questdb_connection", lambda: fake_conn)
    monkeypatch.setattr("sys.argv", ["verify_utxo_lifecycle_mirror"])

    code = module.main()
    assert code == 0


def test_fix_pass_removes_duplicates(monkeypatch):
    """F3: when --fix is requested and dups exist, the dedup pass runs."""
    from scripts.bootstrap import verify_utxo_lifecycle_mirror as module

    # First two fetchone()s are for verify (5000 dups), then for fix:
    # count() before -> 100_005_000, count() after -> 100_000_000
    fake_conn = _FakeConnection(
        [100_005_000, 100_000_000, 100_005_000, 100_000_000]
    )
    monkeypatch.setattr(module, "_open_questdb_connection", lambda: fake_conn)
    monkeypatch.setattr("sys.argv", ["verify_utxo_lifecycle_mirror", "--fix"])

    code = module.main()
    assert code == 0
    # Confirm the dedup SQL was issued
    sql = " ".join(fake_conn.cursor_holder.executed).upper()
    assert "UTXO_LIFECYCLE_DEDUP" in sql
    assert "RENAME" in sql or "DROP" in sql


def test_main_returns_2_on_backend_error(monkeypatch):
    from scripts.bootstrap import verify_utxo_lifecycle_mirror as module

    def boom():
        raise ConnectionError("simulated QuestDB unreachable")

    monkeypatch.setattr(module, "_open_questdb_connection", boom)
    monkeypatch.setattr("sys.argv", ["verify_utxo_lifecycle_mirror"])

    code = module.main()
    assert code == 2
