from __future__ import annotations

import json
from pathlib import Path

from scripts.validation.route_parity import (
    append_dual_read_event,
    compare_payloads,
    main,
)


def test_compare_payloads_passes_within_tolerance_for_series():
    questdb_payload = [
        {"timestamp": "2026-03-30T10:00:00Z", "utxoracle_price": 66000.0},
        {"timestamp": "2026-03-30T10:05:00Z", "utxoracle_price": 66100.0},
    ]
    baseline_payload = [
        {"timestamp": "2026-03-30T10:00:00Z", "utxoracle_price": 66010.0},
        {"timestamp": "2026-03-30T10:05:00Z", "utxoracle_price": 66120.0},
    ]

    report = compare_payloads(
        route_id="live-price-history",
        questdb_payload=questdb_payload,
        baseline_payload=baseline_payload,
        field_tolerances_pct={"utxoracle_price": 0.1},
    )

    assert report["status"] == "pass"
    assert report["sample_count"] == 2
    assert report["failing_fields"] == []
    assert report["field_results"]["utxoracle_price"]["status"] == "pass"


def test_compare_payloads_fails_when_tolerance_is_exceeded():
    questdb_payload = [
        {"timestamp": "2026-03-30T10:00:00Z", "utxoracle_price": 66000.0},
    ]
    baseline_payload = [
        {"timestamp": "2026-03-30T10:00:00Z", "utxoracle_price": 68000.0},
    ]

    report = compare_payloads(
        route_id="live-price-history",
        questdb_payload=questdb_payload,
        baseline_payload=baseline_payload,
        field_tolerances_pct={"utxoracle_price": 0.1},
    )

    assert report["status"] == "fail"
    assert report["failing_fields"] == ["utxoracle_price"]
    assert report["field_results"]["utxoracle_price"]["status"] == "fail"


def test_compare_payloads_supports_nested_fields_and_single_objects():
    questdb_payload = {
        "timestamp": "2026-03-30T10:00:00Z",
        "comparison": {"utxo_vs_mempool_bps": -4.0},
    }
    baseline_payload = {
        "timestamp": "2026-03-30T10:00:00Z",
        "comparison": {"utxo_vs_mempool_bps": -4.003},
    }

    report = compare_payloads(
        route_id="live-comparison-latest",
        questdb_payload=questdb_payload,
        baseline_payload=baseline_payload,
        field_tolerances_pct={"comparison.utxo_vs_mempool_bps": 0.1},
    )

    assert report["status"] == "pass"
    assert report["sample_count"] == 1
    assert report["field_results"]["comparison.utxo_vs_mempool_bps"]["status"] == "pass"


def test_compare_payloads_can_skip_when_baseline_is_missing():
    report = compare_payloads(
        route_id="live-comparison-latest",
        questdb_payload={"timestamp": "2026-03-30T10:00:00Z", "utxoracle_price": 66000.0},
        baseline_payload=None,
        field_tolerances_pct={"utxoracle_price": 0.1},
        allow_missing_baseline=True,
    )

    assert report["status"] == "skipped"
    assert report["sample_count"] == 0
    assert report["notes"] == ["baseline_missing"]


def test_append_dual_read_event_writes_jsonl_record(tmp_path: Path):
    report = compare_payloads(
        route_id="live-price-history",
        questdb_payload=[{"timestamp": "2026-03-30T10:00:00Z", "utxoracle_price": 66000.0}],
        baseline_payload=[{"timestamp": "2026-03-30T10:00:00Z", "utxoracle_price": 68000.0}],
        field_tolerances_pct={"utxoracle_price": 0.1},
        dataset_id="btc-usd",
    )
    log_path = tmp_path / "dual_read.jsonl"

    append_dual_read_event(log_path, report)

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["route_id"] == "live-price-history"
    assert event["dataset_id"] == "btc-usd"
    assert event["severity"] == "error"
    assert event["status"] == "fail"
    assert event["failing_fields"] == ["utxoracle_price"]


def test_main_writes_report_and_divergence_log(tmp_path: Path):
    questdb_path = tmp_path / "questdb.json"
    baseline_path = tmp_path / "baseline.json"
    report_path = tmp_path / "report.json"
    log_path = tmp_path / "dual_read.jsonl"

    questdb_path.write_text(
        json.dumps([{"timestamp": "2026-03-30T10:00:00Z", "utxoracle_price": 66000.0}]),
        encoding="utf-8",
    )
    baseline_path.write_text(
        json.dumps([{"timestamp": "2026-03-30T10:00:00Z", "utxoracle_price": 66010.0}]),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--route-id",
            "live-price-history",
            "--questdb",
            str(questdb_path),
            "--baseline",
            str(baseline_path),
            "--field",
            "utxoracle_price=0.1",
            "--dataset-id",
            "btc-usd",
            "--output",
            str(report_path),
            "--divergence-log",
            str(log_path),
        ]
    )

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "pass"
    assert report["field_results"]["utxoracle_price"]["status"] == "pass"

    event = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert event["severity"] == "info"
    assert event["status"] == "pass"
