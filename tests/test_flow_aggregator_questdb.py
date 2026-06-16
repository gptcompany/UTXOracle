"""Tests for spec-063 entity_flows_daily QuestDB producer pilot."""

from datetime import date as date_cls, datetime
import inspect
import logging
from pathlib import Path

import duckdb
import pytest


def _build_flow_fixture_db(path: Path) -> None:
    conn = duckdb.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE address_clusters (
                address VARCHAR,
                cluster_id VARCHAR,
                label VARCHAR,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO address_clusters VALUES
            ('addr_1', 'cluster_001', NULL, TIMESTAMP '2026-06-15 00:00:00', TIMESTAMP '2026-06-15 00:00:00'),
            ('addr_2', 'cluster_002', NULL, TIMESTAMP '2026-06-15 00:00:00', TIMESTAMP '2026-06-15 00:00:00'),
            ('addr_3', 'cluster_003', NULL, TIMESTAMP '2026-06-15 00:00:00', TIMESTAMP '2026-06-15 00:00:00')
            """
        )
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                txid VARCHAR,
                address VARCHAR,
                ts TIMESTAMP,
                btc_value DOUBLE,
                is_spent BOOLEAN
            )
            """
        )
        conn.execute(
            """
            INSERT INTO utxo_lifecycle VALUES
            ('tx_1', 'addr_1', TIMESTAMP '2026-06-15 01:00:00', 1.25, FALSE),
            ('tx_2', 'addr_2', TIMESTAMP '2026-06-15 02:00:00', 2.50, FALSE),
            ('tx_3', 'addr_3', TIMESTAMP '2026-06-15 03:00:00', 3.75, FALSE)
            """
        )
    finally:
        conn.close()


def _duckdb_entity_flow_rows(path: Path) -> list[dict[str, object]]:
    conn = duckdb.connect(str(path))
    try:
        rows = conn.execute(
            """
            SELECT entity_id, date, inflow_btc, outflow_btc, netflow_btc, is_exchange
            FROM entity_flows_daily
            ORDER BY date, entity_id
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "entity_id": row[0],
            "date": row[1],
            "inflow_btc": row[2],
            "outflow_btc": row[3],
            "netflow_btc": row[4],
            "is_exchange": row[5],
        }
        for row in rows
    ]


def test_placeholder():
    assert True


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (None, True),
        ("", True),
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("FALSE", False),
        ("False", False),
        ("  false  ", False),
        ("no", False),
        ("NO", False),
        ("No", False),
        ("disable", True),
        ("off", True),
        ("nope", True),
    ],
)
def test_should_write_questdb_parser_table(monkeypatch, raw_value, expected):
    from scripts.live.flow_aggregator import _should_write_questdb

    if raw_value is None:
        monkeypatch.delenv("SPEC063_QUESTDB_WRITE", raising=False)
    else:
        monkeypatch.setenv("SPEC063_QUESTDB_WRITE", raw_value)

    assert _should_write_questdb() is expected


def test_save_entity_flows_daily_signature():
    from api.questdb_repository import save_entity_flows_daily

    signature = inspect.signature(save_entity_flows_daily)
    assert list(signature.parameters) == [
        "entity_id",
        "date",
        "inflow_btc",
        "outflow_btc",
        "netflow_btc",
        "is_exchange",
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )
    assert signature.return_annotation is None


def test_dual_write_payload_byte_identity(tmp_path, monkeypatch):
    from scripts.live import flow_aggregator

    db_path = tmp_path / "entity_flows.duckdb"
    _build_flow_fixture_db(db_path)
    calls = []

    def record_save(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        flow_aggregator,
        "save_entity_flows_daily",
        record_save,
        raising=False,
    )

    flow_aggregator.aggregate_flows(db_path=str(db_path))

    assert calls == _duckdb_entity_flow_rows(db_path)


def test_cast_contract_matches_data_model(tmp_path, monkeypatch):
    from scripts.live import flow_aggregator

    db_path = tmp_path / "entity_flows.duckdb"
    _build_flow_fixture_db(db_path)
    calls = []

    def record_save(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        flow_aggregator,
        "save_entity_flows_daily",
        record_save,
        raising=False,
    )

    flow_aggregator.aggregate_flows(db_path=str(db_path))

    assert calls
    for call in calls:
        assert isinstance(call["entity_id"], str)
        assert isinstance(call["date"], date_cls)
        assert not isinstance(call["date"], datetime)
        assert isinstance(call["inflow_btc"], float)
        assert isinstance(call["outflow_btc"], float)
        assert isinstance(call["netflow_btc"], float)
        assert isinstance(call["is_exchange"], bool)


def test_disabled_state_emits_explicit_INFO_log(tmp_path, monkeypatch, caplog):
    """T014 [RED]: with SPEC063_QUESTDB_WRITE OFF, the producer MUST emit an
    INFO log declaring the disabled state (per quickstart.md Rollback Step 2)
    AND MUST NOT open a QuestDB connection AND MUST NOT emit the success log
    shape containing rows_written_questdb=.

    Three assertions:
      (a) regression guard for T012 gating — _open_pg_sync NOT invoked;
      (b) RED-state property — disabled-state INFO log line emitted exactly
          once with the canonical prefix;
      (c) negative property — success log shape NOT present in OFF mode.
    """
    from scripts.live import flow_aggregator

    db_path = tmp_path / "entity_flows.duckdb"
    _build_flow_fixture_db(db_path)

    def must_not_open(*args, **kwargs):
        raise AssertionError(
            "_open_pg_sync must not be called when SPEC063_QUESTDB_WRITE=0"
        )

    monkeypatch.setenv("SPEC063_QUESTDB_WRITE", "0")
    monkeypatch.setattr(
        flow_aggregator, "_open_pg_sync", must_not_open, raising=False
    )
    caplog.set_level(logging.INFO, logger="scripts.live.flow_aggregator")

    flow_aggregator.aggregate_flows(db_path=str(db_path))

    # (a) Connection guard — implicit (must_not_open would have raised)
    # (b) Disabled-state INFO log emitted exactly once
    disabled_prefix = (
        "spec-063 entity_flows_daily QuestDB write half disabled by "
        "SPEC063_QUESTDB_WRITE="
    )
    disabled_records = [
        r for r in caplog.records if r.getMessage().startswith(disabled_prefix)
    ]
    assert len(disabled_records) == 1, (
        f"expected exactly one disabled-state INFO log, got {len(disabled_records)}: "
        f"{[r.getMessage() for r in caplog.records]}"
    )
    # (c) No success-shape log in OFF mode
    for r in caplog.records:
        assert "rows_written_questdb=" not in r.getMessage(), (
            f"success log shape leaked into OFF mode: {r.getMessage()}"
        )
