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

    def execute(self, query: str, params: tuple | None = None):
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


def test_verify_reports_clean_parity_path(monkeypatch):
    """Memory-safe verify (2026-06-03): when QuestDB count == DuckDB source,
    parity short-circuits the verdict to clean without count_distinct."""
    from scripts.bootstrap import verify_utxo_lifecycle_mirror as module

    # Only 1 fetchone() needed now (count(*)) before parity check fires
    fake_conn = _FakeConnection([100_000_000])
    monkeypatch.setattr(module, "_open_questdb_connection", lambda: fake_conn)
    monkeypatch.setattr(module, "_duckdb_source_count", lambda: 100_000_000)
    report = module.verify()
    assert report.total_rows == 100_000_000
    assert report.distinct_outpoints == 100_000_000
    assert report.duplicate_rows == 0
    assert report.is_clean is True


def test_verify_detects_duplicates_via_bucketed_distinct(monkeypatch):
    """When parity disagrees, falls back to bucketed distinct sum (256 buckets).

    Simulates: QuestDB has 100M+5k rows, DuckDB source has 100M,
    bucketed distinct returns 100M total (5k duplicates).
    """
    from scripts.bootstrap import verify_utxo_lifecycle_mirror as module

    # 1 fetchone() for count(*), then 256 fetchones for the buckets
    bucket_scripted = [100_000_000 // 256] * 256
    # Make first bucket carry the remainder so sum == 100_000_000
    bucket_scripted[0] = 100_000_000 - sum(bucket_scripted[1:])
    fake_conn = _FakeConnection([100_005_000, *bucket_scripted])
    monkeypatch.setattr(module, "_open_questdb_connection", lambda: fake_conn)
    monkeypatch.setattr(module, "_duckdb_source_count", lambda: 100_000_000)
    report = module.verify()
    assert report.total_rows == 100_005_000
    assert report.distinct_outpoints == 100_000_000
    assert report.duplicate_rows == 5_000
    assert report.is_clean is False


def test_verify_runs_bucketed_distinct_when_duckdb_unavailable(monkeypatch):
    """If DuckDB source count is unavailable (None), use bucketed distinct."""
    from scripts.bootstrap import verify_utxo_lifecycle_mirror as module

    bucket_scripted = [100_000_000 // 256] * 256
    bucket_scripted[0] = 100_000_000 - sum(bucket_scripted[1:])
    fake_conn = _FakeConnection([100_000_000, *bucket_scripted])
    monkeypatch.setattr(module, "_open_questdb_connection", lambda: fake_conn)
    monkeypatch.setattr(module, "_duckdb_source_count", lambda: None)
    report = module.verify()
    assert report.total_rows == 100_000_000
    assert report.distinct_outpoints == 100_000_000
    assert report.is_clean is True


def test_main_returns_nonzero_when_dups_and_no_fix(monkeypatch):
    """The CLI exit code must reflect the integrity state for CI scripts."""
    from scripts.bootstrap import verify_utxo_lifecycle_mirror as module

    bucket_scripted = [100_000_000 // 256] * 256
    bucket_scripted[0] = 100_000_000 - sum(bucket_scripted[1:])
    fake_conn = _FakeConnection([100_005_000, *bucket_scripted])
    monkeypatch.setattr(module, "_open_questdb_connection", lambda: fake_conn)
    monkeypatch.setattr(module, "_duckdb_source_count", lambda: 100_000_000)
    monkeypatch.setattr("sys.argv", ["verify_utxo_lifecycle_mirror"])

    code = module.main()
    assert code == 1


def test_main_clean_returns_zero(monkeypatch):
    from scripts.bootstrap import verify_utxo_lifecycle_mirror as module

    fake_conn = _FakeConnection([100_000_000])
    monkeypatch.setattr(module, "_open_questdb_connection", lambda: fake_conn)
    monkeypatch.setattr(module, "_duckdb_source_count", lambda: 100_000_000)
    monkeypatch.setattr("sys.argv", ["verify_utxo_lifecycle_mirror"])

    code = module.main()
    assert code == 0


def test_fix_pass_removes_duplicates(monkeypatch):
    """F3: when --fix is requested and dups exist, the dedup pass runs."""
    from scripts.bootstrap import verify_utxo_lifecycle_mirror as module

    # First fetchone() -> 100_005_000 (count); then 256 buckets summing to
    # 100M (5k duplicates); then fix pass: 100_005_000 before + 100M after.
    bucket_scripted = [100_000_000 // 256] * 256
    bucket_scripted[0] = 100_000_000 - sum(bucket_scripted[1:])
    fake_conn = _FakeConnection(
        [100_005_000, *bucket_scripted, 100_005_000, 100_000_000]
    )
    monkeypatch.setattr(module, "_open_questdb_connection", lambda: fake_conn)
    monkeypatch.setattr(module, "_duckdb_source_count", lambda: 100_000_000)
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
