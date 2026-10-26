"""Correction of metrics.tx_volume_* rows written before UTXOracle#62 (F-439).

Before #62 the daily_analysis fetchers stored vout values already in BTC and
estimate_real_volume divided them by 1e8 again: stored values are 1e-8 too small.
"""

from datetime import datetime

import duckdb
import pytest

from scripts.migrations.fix_tx_volume_scale import SCALE, fix_tx_volume_scale, main

CUTOFF = datetime(2026, 10, 1)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "fixture.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute(
        "CREATE TABLE metrics (timestamp TIMESTAMP PRIMARY KEY, tx_count INTEGER,"
        " tx_volume_btc DOUBLE, tx_volume_usd DOUBLE)"
    )
    conn.execute(
        "INSERT INTO metrics VALUES"
        " ('2026-09-01', 10, 2.5e-8, 2.5e-3),"  # before the cutoff, wrong
        " ('2026-09-02', 0, 0.0, 0.0),"  # before, zero
        " ('2026-09-03', 5, NULL, NULL),"  # before, no volume
        " ('2026-10-02', 7, 3.0, 300000.0)"  # after, already correct
    )
    conn.close()
    return path


def rows(path):
    conn = duckdb.connect(str(path))
    try:
        return conn.execute(
            "SELECT timestamp, tx_volume_btc, tx_volume_usd FROM metrics ORDER BY 1"
        ).fetchall()
    finally:
        conn.close()


def test_dry_run_writes_nothing(db_path):
    before = rows(db_path)
    result = fix_tx_volume_scale(db_path, CUTOFF, apply=False)
    assert result["found"] == 3 and result["to_change"] == 2 and result["changed"] == 0
    assert rows(db_path) == before
    conn = duckdb.connect(str(db_path))
    tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
    conn.close()
    assert "tx_volume_scale_fix" not in tables


def test_apply_rescales_only_rows_before_cutoff(db_path):
    result = fix_tx_volume_scale(db_path, CUTOFF, apply=True)
    assert result["changed"] == 2
    got = {r[0]: r for r in rows(db_path)}
    assert got[datetime(2026, 9, 1)][1] == pytest.approx(2.5e-8 * SCALE)
    assert got[datetime(2026, 9, 1)][2] == pytest.approx(2.5e-3 * SCALE)
    assert got[datetime(2026, 9, 3)][1:] == (None, None)
    assert got[datetime(2026, 10, 2)][1:] == (3.0, 300000.0)


def test_second_apply_changes_nothing(db_path):
    fix_tx_volume_scale(db_path, CUTOFF, apply=True)
    after_first = rows(db_path)
    result = fix_tx_volume_scale(db_path, CUTOFF, apply=True)
    assert result["to_change"] == 0 and result["changed"] == 0
    assert rows(db_path) == after_first


def test_cli_requires_explicit_cutoff(db_path):
    with pytest.raises(SystemExit):
        main(["--db", str(db_path)])


def test_cli_defaults_to_dry_run(db_path, caplog):
    before = rows(db_path)
    with caplog.at_level("INFO"):
        assert main(["--db", str(db_path), "--before", "2026-10-01"]) == 0
    assert rows(db_path) == before
    assert "dry-run" in caplog.text
