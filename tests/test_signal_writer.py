import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from scripts.live.signal_writer import SignalSnapshotWriter


def _bundle_row(bundle_id: str, sequence_id: int, payload: dict) -> dict:
    payload = {
        "metadata": {
            "schema_version": "v1",
            "bundle_id": bundle_id,
            "sequence_id": sequence_id,
            "produced_at": datetime(2026, 4, 7, 12, sequence_id, tzinfo=timezone.utc).isoformat(),
            "bundle_status": "healthy",
            "degraded_reasons": [],
        },
        **payload,
    }
    return {
        "payload_json": json.dumps(payload),
        "sequence_id": sequence_id,
        "produced_at": payload["metadata"]["produced_at"],
        "bundle_status": "healthy",
    }


def _run_writer_with_bundles(*, flow_payload: dict, cohort_payload: dict) -> dict:
    repo = AsyncMock()
    rows = {
        "btc_core_live.v1": _bundle_row(
            "btc_core_live.v1",
            10,
            {"live_snapshot": {"block_height": 840_000}, "metrics_latest": {}},
        ),
        "btc_flow.v1": _bundle_row("btc_flow.v1", 20, flow_payload),
        "btc_macro.v1": _bundle_row(
            "btc_macro.v1",
            30,
            {"macro_metrics": {"nupl": 0.0, "reserve_risk": 0.003}},
        ),
        "btc_cohort.v1": _bundle_row("btc_cohort.v1", 40, cohort_payload),
    }
    repo.get_latest_feature_bundle.side_effect = lambda bundle_id: rows[bundle_id]
    repo.get_latest_signal_snapshot.return_value = None

    writer = SignalSnapshotWriter(repo)
    asyncio.run(writer.write_signal_snapshot())

    repo.async_send_row.assert_awaited_once()
    _, _, columns, _ = repo.async_send_row.await_args.args
    return json.loads(columns["payload_json"])


def test_flow_score_uses_recent_window_and_absorption_context():
    payload = _run_writer_with_bundles(
        flow_payload={
            "whale_summary": {
                "total_transactions": 5,
                "total_btc_volume": 2_500.0,
                "avg_urgency_score": 0.8,
            },
            "recent_whale_window": {
                "net_flow_btc": 2_500.0,
                "last_event_timestamp": "2026-04-07T12:00:00+00:00",
            },
            "absorption_rates": {
                "institutional_absorption": 0.8,
                "retail_absorption": 0.2,
                "dominant_absorber": "whale",
                "confidence": 0.9,
            },
        },
        cohort_payload={"cost_basis": {"sth_mvrv": 1.0, "lth_mvrv": 1.0}},
    )

    assert payload["flow_score"] == pytest.approx(0.55)
    flow_components = payload["component_details"]["flow_components"]
    assert flow_components["net_flow_btc"] == 2_500.0
    assert flow_components["absorption_context"] == pytest.approx(1.6)


def test_flow_score_missing_absorption_is_neutral_not_bearish():
    writer = SignalSnapshotWriter(repo=AsyncMock())

    assert writer.calculate_flow_score({"net_flow_btc": 0.0}) == 0.0


def test_valuation_score_uses_admitted_sth_lth_mvrv_fields():
    payload = _run_writer_with_bundles(
        flow_payload={
            "whale_summary": {"total_transactions": 0},
            "recent_whale_window": {"net_flow_btc": 0.0},
            "absorption_rates": {"institutional_absorption": 0.5, "retail_absorption": 0.5},
        },
        cohort_payload={
            "cost_basis": {
                "sth_cost_basis": 65_000.0,
                "lth_cost_basis": 35_000.0,
                "total_cost_basis": 50_000.0,
                "sth_mvrv": 0.8,
                "lth_mvrv": 0.9,
                "current_price_usd": 55_000.0,
            }
        },
    )

    assert payload["valuation_score"] == pytest.approx(0.15)
    valuation_components = payload["component_details"]["valuation_components"]
    assert valuation_components["sth_mvrv"] == 0.8
    assert valuation_components["lth_mvrv"] == 0.9
    assert valuation_components["mvrv_used"] == pytest.approx(0.85)
