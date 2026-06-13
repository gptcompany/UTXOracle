"""Tests for MetricLoader QuestDB backend (spec-060 backtest integration)."""

import json
from datetime import date
from io import BytesIO
from unittest.mock import patch

import pytest

from scripts.integrations.metric_loader import MetricLoader


def _fake_questdb_response(dataset):
    """Build a fake HTTP response matching QuestDB /exec JSON format."""
    body = json.dumps({"dataset": dataset}).encode()
    resp = BytesIO(body)
    resp.read_orig = resp.read
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda s, *a: None
    return resp


URPD_METRICS = [
    "supply_below_price_pct",
    "supply_above_price_pct",
    "top_bucket_concentration",
    "dominant_bucket_distance_pct",
    "distribution_entropy",
]


@pytest.mark.parametrize("metric_id", URPD_METRICS)
def test_urpd_metrics_are_registered(metric_id):
    loader = MetricLoader()
    assert metric_id in loader.list_available_metrics()


def test_load_from_questdb_parses_response():
    loader = MetricLoader()
    dataset = [
        ["2026-04-15T00:00:00.000000Z", 71.3],
        ["2026-04-16T00:00:00.000000Z", 72.1],
        ["2026-04-17T00:00:00.000000Z", 73.0],
    ]

    with patch(
        "scripts.integrations.metric_loader.urlopen",
        return_value=_fake_questdb_response(dataset),
    ):
        result = loader.load_metric(
            "supply_below_price_pct",
            start_date=date(2026, 4, 15),
            end_date=date(2026, 4, 17),
            source="questdb",
        )

    assert result.source == "questdb"
    assert len(result.data) == 3
    assert result.data[0].date == date(2026, 4, 15)
    assert result.data[0].value == pytest.approx(71.3)
    assert result.data[2].value == pytest.approx(73.0)


def test_load_from_questdb_handles_empty_response():
    loader = MetricLoader()

    with patch(
        "scripts.integrations.metric_loader.urlopen",
        return_value=_fake_questdb_response([]),
    ):
        result = loader.load_metric(
            "distribution_entropy",
            start_date=date(2026, 4, 15),
            end_date=date(2026, 4, 17),
            source="questdb",
        )

    assert result.source == "questdb"
    assert len(result.data) == 0


def test_load_from_questdb_skips_null_values():
    loader = MetricLoader()
    dataset = [
        ["2026-04-15T00:00:00.000000Z", 40.0],
        ["2026-04-16T00:00:00.000000Z", None],
        ["2026-04-17T00:00:00.000000Z", 42.5],
    ]

    with patch(
        "scripts.integrations.metric_loader.urlopen",
        return_value=_fake_questdb_response(dataset),
    ):
        result = loader.load_metric(
            "top_bucket_concentration",
            start_date=date(2026, 4, 15),
            end_date=date(2026, 4, 17),
            source="questdb",
        )

    assert len(result.data) == 2
    assert result.data[0].value == pytest.approx(40.0)
    assert result.data[1].value == pytest.approx(42.5)


def test_load_from_questdb_dedupes_same_day_to_latest_value():
    loader = MetricLoader()
    dataset = [
        ["2026-04-17T00:00:00.000000Z", 71.3],
        ["2026-04-17T12:34:56.000000Z", 72.1],
        ["2026-04-18T00:00:00.000000Z", 73.0],
    ]

    with patch(
        "scripts.integrations.metric_loader.urlopen",
        return_value=_fake_questdb_response(dataset),
    ):
        result = loader.load_metric(
            "supply_below_price_pct",
            start_date=date(2026, 4, 17),
            end_date=date(2026, 4, 18),
            source="questdb",
        )

    assert result.source == "questdb"
    assert len(result.data) == 2
    assert result.data[0].date == date(2026, 4, 17)
    assert result.data[0].value == pytest.approx(72.1)
    assert result.data[1].date == date(2026, 4, 18)
    assert result.data[1].value == pytest.approx(73.0)


def test_load_from_questdb_falls_back_on_connection_error():
    loader = MetricLoader()

    with patch(
        "scripts.integrations.metric_loader.urlopen",
        side_effect=OSError("Connection refused"),
    ):
        result = loader.load_metric(
            "supply_above_price_pct",
            start_date=date(2026, 4, 15),
            end_date=date(2026, 4, 17),
            source="questdb",
        )

    # Falls back to golden, which won't have data either
    assert len(result.data) == 0


def test_auto_source_routes_urpd_to_questdb():
    """auto source should route urpd metrics to questdb, not duckdb."""
    loader = MetricLoader()
    dataset = [["2026-04-17T00:00:00.000000Z", 0.88]]

    with patch(
        "scripts.integrations.metric_loader.urlopen",
        return_value=_fake_questdb_response(dataset),
    ) as mock_urlopen:
        result = loader.load_metric(
            "distribution_entropy",
            start_date=date(2026, 4, 17),
            end_date=date(2026, 4, 17),
        )

    mock_urlopen.assert_called_once()
    assert result.source == "questdb"
    assert len(result.data) == 1
    assert result.data[0].value == pytest.approx(0.88)
