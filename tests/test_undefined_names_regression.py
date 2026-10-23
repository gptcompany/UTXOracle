"""
Regression tests for undefined names (ruff F821) that raised NameError at runtime.

- scripts.daily_analysis.backfill_gap called save_to_duckdb, removed when the
  database layer converged on QuestDB; the NameError was swallowed and every
  backfill returned False.
- examples/whale-flow-references used `sys` without importing it and JSON
  literals `true`/`false` inside a Python dict.
- /api/metrics/nupl is covered by tests/test_nupl.py (helpers restored in api.main).
"""

import runpy
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "whale-flow-references"


class TestBackfillGapSavesToQuestDB:
    def test_backfill_gap_saves_through_questdb(self):
        from scripts.daily_analysis import backfill_gap

        with (
            patch("scripts.daily_analysis.UTXOracleCalculator") as calc,
            patch("scripts.daily_analysis.fetch_mempool_price", return_value=100500.0),
            patch(
                "scripts.daily_analysis.fetch_historical_transactions",
                return_value=[{"txid": "x"}],
            ),
            patch("scripts.daily_analysis.save_to_questdb") as save,
        ):
            calc.return_value.calculate_price_for_transactions.return_value = {
                "price_usd": 100000.0,
                "confidence": 0.9,
                "tx_count": 5000,
            }
            assert backfill_gap("2026-01-15", {}) is True

        save.assert_called_once()
        data = save.call_args[0][0]
        # save_to_questdb parses the timestamp with datetime.fromisoformat
        assert data["timestamp"] == "2026-01-15T00:00:00"
        assert data["utxoracle_price"] == 100000.0
        assert data["is_valid"] is True


class TestWhaleFlowExamples:
    def test_bitcoinlib_example_mock_tx_is_valid_python(self):
        ns = runpy.run_path(str(EXAMPLES / "bitcoinlib-address-parsing.py"))
        tx = ns["MOCK_TX_DATA"]
        assert tx["vin"][0]["is_coinbase"] is False
        assert tx["status"]["confirmed"] is True
        inputs, outputs = ns["parse_addresses_from_transaction"](tx)
        assert inputs

    def test_electrs_example_exits_with_status_1_when_api_is_down(self):
        with patch(
            "requests.get", side_effect=requests.exceptions.ConnectionError("down")
        ):
            with pytest.raises(SystemExit) as excinfo:
                runpy.run_path(
                    str(EXAMPLES / "electrs-api-example.py"), run_name="__main__"
                )
        assert excinfo.value.code == 1
