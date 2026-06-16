"""Tests for spec-063 entity_flows_daily QuestDB producer pilot."""

import inspect
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
