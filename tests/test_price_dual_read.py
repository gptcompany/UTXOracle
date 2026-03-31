from __future__ import annotations

import json
from pathlib import Path

import duckdb

from api.main import _log_prices_historical_dual_read


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
                ("2026-03-29", 66100.0, 66090.0, -10.0, -0.02, 0.82, 125, True, None, None, None, None),
                ("2026-03-30", 66200.0, 66180.0, -20.0, -0.03, 0.83, 130, True, None, None, None, None),
            ],
        )
    finally:
        conn.close()


def test_log_prices_historical_dual_read_appends_dual_read_event(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "utxoracle.duckdb"
    log_path = tmp_path / "prices_dual_read.jsonl"
    _create_price_analysis_duckdb(db_path)
    monkeypatch.setenv("PRICES_HISTORICAL_DUAL_READ_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("PRICES_HISTORICAL_DUAL_READ_LOG_PATH", str(log_path))
    payload = [
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

    report = _log_prices_historical_dual_read(payload, days=2)

    assert report["status"] == "pass"
    event = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert event["route_id"] == "prices-historical"
    assert event["severity"] == "info"
    assert event["sample_count"] == 2
