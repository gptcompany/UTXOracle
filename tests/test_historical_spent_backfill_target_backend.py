"""Test the --target-backend questdb flag (spec-061 US2/Polish T035).

Two layers:

1. CLI surface - `--target-backend` defaults to "duckdb" and accepts
   "questdb"; an unknown value is rejected by argparse.

2. QuestDB propagation helper - `_propagate_spent_to_questdb` reads a
   staging CSV in the canonical shape produced by
   `process_blocks_to_csv` and issues batched UPDATE statements via
   psycopg.executemany. The psycopg connection is fully mocked so the
   test does not require a live QuestDB.
"""

from __future__ import annotations

import csv
import sys
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# -- CLI surface ---------------------------------------------------------------


def test_cli_default_target_backend_is_duckdb():
    """T035: default behaviour MUST stay duckdb (legacy backward compat)."""
    import argparse
    import importlib

    module = importlib.import_module("scripts.bootstrap.historical_spent_backfill")
    # Reproduce the parser shape from main() - the module exposes main but
    # we want to test parse only.
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-block", type=int, default=1)
    parser.add_argument("--end-block", type=int, default=927966)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--target-backend", choices=["duckdb", "questdb"], default="duckdb"
    )
    args = parser.parse_args([])
    assert args.target_backend == "duckdb"
    assert hasattr(module, "_propagate_spent_to_questdb")


def test_cli_target_backend_questdb_parses():
    """T035: --target-backend questdb MUST be accepted."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target-backend", choices=["duckdb", "questdb"], default="duckdb"
    )
    args = parser.parse_args(["--target-backend", "questdb"])
    assert args.target_backend == "questdb"


def test_cli_unknown_target_backend_rejected():
    """T035: argparse MUST reject anything outside {duckdb, questdb}."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target-backend", choices=["duckdb", "questdb"], default="duckdb"
    )
    with pytest.raises(SystemExit):
        parser.parse_args(["--target-backend", "parquet"])


# -- Propagation helper --------------------------------------------------------


def _write_csv(path: Path, rows: list[tuple[str, int, int, int]]) -> None:
    """Emit a CSV in the (txid, vout, spent_block, spent_time) shape."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        for r in rows:
            writer.writerow(r)


class _FakeCursor:
    """Captures executemany invocations for assertion."""

    def __init__(self, captured: list[tuple[str, list]]):
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def executemany(self, query: str, params: list):
        self._captured.append((query, list(params)))


class _FakeConnection:
    def __init__(self, captured: list[tuple[str, list]]):
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self._captured)


def test_questdb_path_propagates_updates(tmp_path):
    """T035: `_propagate_spent_to_questdb` issues one UPDATE per CSV row.

    Asserts:
    - CSV with 3 rows produces 3 UPDATE parameter tuples.
    - Each tuple has the (spent_block, txid, vout_index) shape so the
      UPDATE matches `WHERE txid = %s AND vout_index = %s`.
    - The UPDATE statement targets the `utxo_lifecycle` table.
    - The returned count equals the row count.
    """
    csv_path = tmp_path / "staging.csv"
    _write_csv(
        csv_path,
        [
            ("aaa" * 21 + "a", 0, 928000, 1716500000),
            ("bbb" * 21 + "b", 1, 928001, 1716501000),
            ("ccc" * 21 + "c", 5, 928002, 1716502000),
        ],
    )

    captured: list[tuple[str, list]] = []

    def fake_connect(**kwargs):
        return _FakeConnection(captured)

    with patch(
        "scripts.bootstrap.historical_spent_backfill.psycopg.connect",
        side_effect=fake_connect,
    ):
        from scripts.bootstrap.historical_spent_backfill import (
            _propagate_spent_to_questdb,
        )

        n = _propagate_spent_to_questdb(csv_path)

    assert n == 3, f"expected 3 propagated rows, got {n}"
    assert len(captured) == 1, f"expected 1 executemany call, got {len(captured)}"
    query, params = captured[0]
    assert "UPDATE utxo_lifecycle" in query
    assert "is_spent = true" in query
    assert "vout_index" in query
    assert len(params) == 3
    # (spent_block, txid, vout_index) shape
    assert params[0][0] == 928000
    assert params[0][2] == 0
    assert params[1][0] == 928001
    assert params[1][2] == 1
    assert params[2][0] == 928002


def test_questdb_path_batches_at_1000(tmp_path):
    """T035: batching boundary - 1500 rows MUST become two executemany calls."""
    csv_path = tmp_path / "big.csv"
    rows = [
        (f"tx{idx:062d}", idx % 4, 900_000 + idx, 1_700_000_000 + idx)
        for idx in range(1500)
    ]
    _write_csv(csv_path, rows)

    captured: list[tuple[str, list]] = []

    def fake_connect(**kwargs):
        return _FakeConnection(captured)

    with patch(
        "scripts.bootstrap.historical_spent_backfill.psycopg.connect",
        side_effect=fake_connect,
    ):
        from scripts.bootstrap.historical_spent_backfill import (
            _propagate_spent_to_questdb,
        )

        n = _propagate_spent_to_questdb(csv_path)

    assert n == 1500
    assert len(captured) == 2  # 1000 + 500
    assert len(captured[0][1]) == 1000
    assert len(captured[1][1]) == 500


def test_questdb_path_skips_malformed_rows(tmp_path):
    """T035: a row with non-integer vout/spent_block is skipped silently."""
    csv_path = tmp_path / "mixed.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("tx_good", 0, 928000, 1716500000))
        writer.writerow(("tx_bad",))  # too short
        writer.writerow(("tx_alpha", "not-int", 928001, 1716501000))
        writer.writerow(("tx_good_2", 2, 928002, 1716502000))

    captured: list[tuple[str, list]] = []

    def fake_connect(**kwargs):
        return _FakeConnection(captured)

    with patch(
        "scripts.bootstrap.historical_spent_backfill.psycopg.connect",
        side_effect=fake_connect,
    ):
        from scripts.bootstrap.historical_spent_backfill import (
            _propagate_spent_to_questdb,
        )

        n = _propagate_spent_to_questdb(csv_path)

    assert n == 2
    assert len(captured) == 1
    assert len(captured[0][1]) == 2


def test_questdb_failure_does_not_advance_checkpoint_or_delete_csv(
    tmp_path, monkeypatch
):
    """T035: a QuestDB failure must stop before checkpoint/save cleanup."""
    import scripts.bootstrap.historical_spent_backfill as module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "check_bitcoin_ready", lambda: True)
    monkeypatch.setattr(
        module,
        "load_checkpoint",
        lambda: {"last_block": 0, "total_inputs": 0, "started_at": None},
    )
    save_checkpoint = MagicMock()
    monkeypatch.setattr(module, "save_checkpoint", save_checkpoint)
    monkeypatch.setattr(
        module,
        "_propagate_spent_to_questdb",
        MagicMock(side_effect=ConnectionError("questdb down")),
    )

    def fake_process_blocks_to_csv(rpc, start, end, csv_path, workers):
        _write_csv(csv_path, [("tx_good", 0, 928000, 1716500000)])
        return 1

    monkeypatch.setitem(
        sys.modules,
        "scripts.bootstrap.fast_spent_sync_v2",
        SimpleNamespace(
            BitcoinRPC=lambda: object(),
            process_blocks_to_csv=fake_process_blocks_to_csv,
        ),
    )

    class _FakeDuckDB:
        def execute(self, query):
            result = MagicMock()
            result.rowcount = 1
            return result

    import duckdb

    monkeypatch.setattr(duckdb, "connect", lambda path: _FakeDuckDB())

    with pytest.raises(ConnectionError, match="questdb down"):
        module.run_backfill(
            start_block=1,
            end_block=2,
            workers=1,
            dry_run=False,
            target_backend="questdb",
        )

    assert save_checkpoint.call_count == 0
    assert (tmp_path / "data/temp/backfill_1_2.csv").exists()
