"""Mirror script test (spec-061 US2 T026b).

The producer `scripts/whale_flow_backtest.py` writes a DuckDB table with
`timestamp BIGINT`. The QuestDB consumption surface needs `ts TIMESTAMP`.
The mirror script `scripts/metrics/mirror_backtest_whale_signals.py`
copies rows from DuckDB to QuestDB, converting BIGINT to TIMESTAMP and
preserving the pinned columns.

Fully mocked - no live DuckDB or QuestDB required.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_duckdb_to_questdb_roundtrip(tmp_path):
    """T026b: mirror writes one QuestDB row per DuckDB row, with TS converted.

    The mirror script must:
    - Read all rows from DuckDB `backtest_whale_signals`.
    - Convert `timestamp` (BIGINT seconds since epoch) to UTC datetime.
    - Call the QuestDB save method for each row with identical pinned columns.
    - Be idempotent (same source -> same target).
    """
    # Two fake DuckDB rows (timestamp BIGINT seconds, plus pinned columns)
    duckdb_rows = [
        (
            1_716_500_000,  # timestamp BIGINT
            0.5,            # net_flow_btc
            0.8,            # confidence
            65_000.0,       # btc_price
            10.0,           # inflow_btc
            9.5,            # outflow_btc
            42,             # tx_count_relevant
        ),
        (
            1_716_600_000,
            -0.3,
            0.7,
            66_000.0,
            5.0,
            5.3,
            33,
        ),
    ]

    fake_duckdb_conn = MagicMock()
    fake_duckdb_conn.execute.return_value.fetchall.return_value = duckdb_rows

    save_calls = []

    def fake_save(**kwargs):
        save_calls.append(kwargs)
        return True

    with patch(
        "scripts.metrics.mirror_backtest_whale_signals.duckdb.connect",
        return_value=fake_duckdb_conn,
    ), patch(
        "scripts.metrics.mirror_backtest_whale_signals.save_backtest_whale_signal_row",
        side_effect=fake_save,
    ):
        from scripts.metrics.mirror_backtest_whale_signals import mirror

        mirror(duckdb_path=str(tmp_path / "fake.duckdb"))

    assert len(save_calls) == 2
    fake_duckdb_conn.close.assert_called_once()

    # First row was forwarded with BIGINT converted to a datetime
    import datetime as dt

    first = save_calls[0]
    assert isinstance(first["ts"], dt.datetime)
    assert first["ts"].tzinfo is not None  # UTC-aware
    assert int(first["ts"].timestamp()) == 1_716_500_000
    assert first["net_flow_btc"] == 0.5
    assert first["tx_count_relevant"] == 42

    second = save_calls[1]
    assert int(second["ts"].timestamp()) == 1_716_600_000
    assert second["confidence"] == 0.7
