"""Tests for the DuckDB -> QuestDB utxo_lifecycle mirror.

The spent backfill updates QuestDB rows in place. These tests pin the
bootstrap mirror that makes that operational path meaningful when the
QuestDB target table is empty.
"""

from __future__ import annotations

from datetime import timezone
from pathlib import Path

import duckdb
import pytest


def test_row_mapping_preserves_contract_columns():
    from scripts.bootstrap.mirror_utxo_lifecycle_to_questdb import (
        _row_to_insert_params,
    )

    params = _row_to_insert_params(
        (
            "txid1",
            2,
            840_000,
            1_716_500_000,
            65_000.0,
            0.25,
            16_250.0,
            841_000,
            1_716_560_000,
            66_000.0,
            1_000,
            7,
            "sth",
            1.02,
            False,
            True,
        )
    )

    assert params[0] == "txid1:2"  # outpoint
    assert params[1] == "txid1"
    assert params[2] == 2  # vout_index
    assert params[3] == 840_000  # creation_block
    assert params[4].tzinfo == timezone.utc
    assert int(params[4].timestamp()) == 1_716_500_000
    assert params[5] == 65_000.0  # creation_price_usd
    assert params[6] == 0.25  # btc_value
    assert params[8] == 841_000  # spent_block
    assert int(params[9].timestamp()) == 1_716_560_000
    assert params[18] is True  # is_spent
    assert params[19] == "utxoracle"


class _FakeCursor:
    def __init__(self, owner):
        self.owner = owner
        self._fetchone = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str):
        self.owner.executes.append(query)
        if "count()" in query:
            self._fetchone = (self.owner.target_count,)
        return self

    def fetchone(self):
        return self._fetchone

    def executemany(self, query: str, params: list):
        self.owner.executemany_calls.append((query, list(params)))


class _FakeQuestDBConnection:
    def __init__(self, target_count: int = 0):
        self.target_count = target_count
        self.executes: list[str] = []
        self.executemany_calls: list[tuple[str, list]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self)


def _write_source_db(path: Path) -> None:
    conn = duckdb.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle_full (
                txid VARCHAR,
                vout INTEGER,
                creation_block INTEGER,
                creation_timestamp BIGINT,
                creation_price_usd DOUBLE,
                btc_value DOUBLE,
                realized_value_usd DOUBLE,
                spent_block INTEGER,
                spent_timestamp BIGINT,
                spent_price_usd DOUBLE,
                age_blocks INTEGER,
                age_days INTEGER,
                cohort VARCHAR,
                sopr DOUBLE,
                is_coinbase BOOLEAN,
                is_spent BOOLEAN
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO utxo_lifecycle_full VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "tx1",
                    0,
                    840_000,
                    1_716_500_000,
                    65_000.0,
                    0.1,
                    6_500.0,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    False,
                    False,
                ),
                (
                    "tx2",
                    1,
                    840_001,
                    1_716_500_600,
                    65_100.0,
                    0.2,
                    13_020.0,
                    840_010,
                    1_716_506_000,
                    66_000.0,
                    9,
                    0,
                    "sth",
                    1.01,
                    False,
                    True,
                ),
                (
                    "tx3",
                    0,
                    840_002,
                    1_716_501_200,
                    65_200.0,
                    0.3,
                    19_560.0,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    True,
                    False,
                ),
            ],
        )
    finally:
        conn.close()


def test_mirror_writes_batches(tmp_path, monkeypatch):
    import scripts.bootstrap.mirror_utxo_lifecycle_to_questdb as module

    duckdb_path = tmp_path / "source.duckdb"
    _write_source_db(duckdb_path)
    fake_target = _FakeQuestDBConnection(target_count=0)
    monkeypatch.setattr(module, "_open_questdb_connection", lambda: fake_target)

    stats = module.mirror(
        duckdb_path=duckdb_path,
        start_block=840_000,
        end_block=840_002,
        batch_size=2,
    )

    assert stats.source_rows == 3
    assert stats.mirrored_rows == 3
    assert len(fake_target.executemany_calls) == 2
    first_query, first_params = fake_target.executemany_calls[0]
    assert "INSERT INTO utxo_lifecycle" in first_query
    assert len(first_params) == 2
    assert first_params[0][0] == "tx1:0"
    assert first_params[1][8] == 840_010


def test_mirror_refuses_nonempty_target(tmp_path, monkeypatch):
    import scripts.bootstrap.mirror_utxo_lifecycle_to_questdb as module

    duckdb_path = tmp_path / "source.duckdb"
    _write_source_db(duckdb_path)
    fake_target = _FakeQuestDBConnection(target_count=1)
    monkeypatch.setattr(module, "_open_questdb_connection", lambda: fake_target)

    with pytest.raises(RuntimeError, match="non-empty"):
        module.mirror(
            duckdb_path=duckdb_path,
            start_block=840_000,
            end_block=840_002,
            batch_size=2,
        )

    assert fake_target.executemany_calls == []


def test_dry_run_counts_without_opening_questdb(tmp_path, monkeypatch):
    import scripts.bootstrap.mirror_utxo_lifecycle_to_questdb as module

    duckdb_path = tmp_path / "source.duckdb"
    _write_source_db(duckdb_path)
    monkeypatch.setattr(
        module,
        "_open_questdb_connection",
        lambda: pytest.fail("dry-run must not connect to QuestDB"),
    )

    stats = module.mirror(
        duckdb_path=duckdb_path,
        start_block=840_000,
        end_block=840_002,
        dry_run=True,
    )

    assert stats.source_rows == 3
    assert stats.mirrored_rows == 0
    assert stats.dry_run is True
