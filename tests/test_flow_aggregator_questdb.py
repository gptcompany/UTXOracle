"""Tests for spec-063 entity_flows_daily QuestDB producer pilot."""

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
