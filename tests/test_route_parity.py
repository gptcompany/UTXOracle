from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.validation.route_parity import (
    append_dual_read_event,
    compare_payloads,
    load_prices_historical_baseline_from_duckdb,
    main,
    run_prices_historical_dual_read,
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


def _create_price_analysis_duckdb(db_path: Path) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE price_analysis (
                date DATE,
                exchange_price DOUBLE,
                utxoracle_price DOUBLE,
                price_difference DOUBLE,
                avg_pct_diff DOUBLE,
                confidence DOUBLE,
                tx_count INTEGER,
                is_valid BOOLEAN,
                whale_net_flow DOUBLE,
                whale_direction VARCHAR,
                action VARCHAR,
                combined_signal DOUBLE
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO price_analysis (
                date,
                exchange_price,
                utxoracle_price,
                price_difference,
                avg_pct_diff,
                confidence,
                tx_count,
                is_valid,
                whale_net_flow,
                whale_direction,
                action,
                combined_signal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-03-28", 66000.0, 65990.0, -10.0, -0.02, 0.81, 120, True, None, None, None, None),
                ("2026-03-29", 66100.0, 66090.0, -10.0, -0.02, 0.82, 125, True, None, None, None, None),
                ("2026-03-30", 66200.0, 66180.0, -20.0, -0.03, 0.83, 130, True, None, None, None, None),
            ],
        )
    finally:
        conn.close()


def test_load_prices_historical_baseline_from_duckdb_uses_latest_lookback_window(tmp_path: Path):
    db_path = tmp_path / "utxoracle.duckdb"
    _create_price_analysis_duckdb(db_path)

    rows = load_prices_historical_baseline_from_duckdb(db_path, days=2)

    assert [row["date"] for row in rows] == ["2026-03-29", "2026-03-30"]
    assert rows[0]["mempool_price"] == 66100.0
    assert rows[1]["utxoracle_price"] == 66180.0


def test_run_prices_historical_dual_read_compares_route_payload_against_duckdb_baseline(tmp_path: Path):
    db_path = tmp_path / "utxoracle.duckdb"
    log_path = tmp_path / "prices_dual_read.jsonl"
    _create_price_analysis_duckdb(db_path)
    questdb_payload = [
        {
            "timestamp": "2026-03-29T00:00:00+00:00",
            "utxoracle_price": 66095.0,
            "mempool_price": 66100.0,
            "confidence": 0.82,
            "diff_percent": -0.02,
            "is_valid": True,
        },
        {
            "timestamp": "2026-03-30T00:00:00+00:00",
            "utxoracle_price": 66185.0,
            "mempool_price": 66200.0,
            "confidence": 0.83,
            "diff_percent": -0.03,
            "is_valid": True,
        },
    ]

    report = run_prices_historical_dual_read(
        questdb_payload=questdb_payload,
        duckdb_path=db_path,
        lookback_days=2,
        dataset_id="prices-7d",
        divergence_log=log_path,
    )

    assert report["status"] == "pass"
    assert report["timestamp_field"] == "date"
    assert report["field_results"]["utxoracle_price"]["status"] == "pass"
    event = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert event["route_id"] == "prices-historical"
    assert event["severity"] == "info"


def test_main_supports_prices_historical_route_family_with_duckdb_baseline(tmp_path: Path):
    db_path = tmp_path / "utxoracle.duckdb"
    questdb_path = tmp_path / "questdb.json"
    report_path = tmp_path / "report.json"
    log_path = tmp_path / "prices_dual_read.jsonl"
    _create_price_analysis_duckdb(db_path)

    questdb_path.write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-03-29T00:00:00+00:00",
                    "utxoracle_price": 66095.0,
                    "mempool_price": 66100.0,
                    "confidence": 0.82,
                    "diff_percent": -0.02,
                    "is_valid": True,
                },
                {
                    "timestamp": "2026-03-30T00:00:00+00:00",
                    "utxoracle_price": 66185.0,
                    "mempool_price": 66200.0,
                    "confidence": 0.83,
                    "diff_percent": -0.03,
                    "is_valid": True,
                },
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--route-family",
            "prices-historical",
            "--questdb",
            str(questdb_path),
            "--baseline-duckdb",
            str(db_path),
            "--lookback-days",
            "2",
            "--dataset-id",
            "prices-7d",
            "--output",
            str(report_path),
            "--divergence-log",
            str(log_path),
        ]
    )

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "pass"
    assert report["timestamp_field"] == "date"
