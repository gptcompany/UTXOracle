"""Tests for spec-063 entity_flows_daily QuestDB producer pilot."""

import inspect

import pytest


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
