"""
Integration Tests for daily_analysis.py (T034-T037)

Tests for the cron job that compares UTXOracle vs mempool.space prices.

Spec: 003-mempool-integration-refactor
Phase: 3 - Integration Service
Tasks: T034-T037 (TDD Red - tests should FAIL initially)
"""

import pytest
from unittest.mock import Mock, patch


class TestMempoolPriceFetch:
    """T034: Test fetching exchange prices from mempool.space API"""

    def test_fetch_mempool_price_returns_float(self):
        """Should fetch USD price from mempool.space API endpoint"""
        # Import function (will fail initially - module doesn't exist yet)
        from scripts.daily_analysis import fetch_mempool_price

        # Mock HTTP response
        with patch("scripts.daily_analysis.requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"USD": 67234.50}
            mock_get.return_value.status_code = 200

            price = fetch_mempool_price()

            # Should return float price
            assert isinstance(price, float)
            assert price == 67234.50

            # Should call correct endpoint
            mock_get.assert_called_once()
            call_args = mock_get.call_args[0][0]
            assert "api/v1/prices" in call_args

    def test_fetch_mempool_price_handles_network_error(self):
        """Should raise exception on network failure"""
        from scripts.daily_analysis import fetch_mempool_price
        import requests

        with patch("scripts.daily_analysis.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Connection timeout")

            with pytest.raises(requests.RequestException):
                fetch_mempool_price()


class TestUTXOraclePriceCalculation:
    """T035: Test calculating price using UTXOracle library"""

    def test_calculate_utxoracle_price(self):
        """Should calculate price from Bitcoin Core RPC transactions"""
        from scripts.daily_analysis import calculate_utxoracle_price

        # Mock Bitcoin Core RPC response
        mock_txs = [
            {"vout": [{"value": 0.001}], "vin": [{}]},
            {"vout": [{"value": 0.0009}], "vin": [{}]},
            {"vout": [{"value": 0.0011}], "vin": [{}]},
        ]

        with patch("scripts.daily_analysis.fetch_bitcoin_transactions") as mock_fetch:
            mock_fetch.return_value = mock_txs

            result = calculate_utxoracle_price("~/.bitcoin")

            # Should return dict with required fields
            assert isinstance(result, dict)
            assert "price_usd" in result
            assert "confidence" in result
            assert "tx_count" in result

            # Price should be reasonable (using library)
            assert result["price_usd"] is None or isinstance(
                result["price_usd"], (int, float)
            )
            assert 0.0 <= result["confidence"] <= 1.0

    def test_calculate_utxoracle_price_handles_no_transactions(self):
        """Should handle empty transaction list gracefully"""
        from scripts.daily_analysis import calculate_utxoracle_price

        with patch("scripts.daily_analysis.fetch_bitcoin_transactions") as mock_fetch:
            mock_fetch.return_value = []

            result = calculate_utxoracle_price("~/.bitcoin")

            assert result["price_usd"] is None or result["price_usd"] == 0
            assert result["tx_count"] == 0


class TestPriceComparison:
    """T036: Test price difference calculation"""

    def test_compare_prices_computes_difference(self):
        """Should calculate absolute and percentage difference"""
        from scripts.daily_analysis import compare_prices

        utx_price = 67000.0
        mem_price = 67500.0

        result = compare_prices(utx_price, mem_price)

        # Should return dict with diff fields
        assert isinstance(result, dict)
        assert "diff_amount" in result
        assert "diff_percent" in result

        # Should calculate correctly
        # diff_amount = mem_price - utx_price = 500
        # diff_percent = (500 / 67000) * 100 = 0.746%
        assert result["diff_amount"] == pytest.approx(500.0, rel=0.01)
        assert result["diff_percent"] == pytest.approx(0.746, rel=0.01)

    def test_compare_prices_handles_zero_utx_price(self):
        """Should handle edge case where UTXOracle price is None/zero"""
        from scripts.daily_analysis import compare_prices

        result = compare_prices(None, 67500.0)

        # Should return None or inf for percentage difference
        assert result["diff_amount"] is None or result["diff_percent"] is None


class TestDuckDBSave:
    """T037: Test saving data to DuckDB"""

    def test_save_to_duckdb(self):
        """Should insert price comparison data into DuckDB"""
        from scripts.daily_analysis import save_to_duckdb

        # Mock data
        data = {
            "timestamp": "2025-10-26 12:00:00",
            "utxoracle_price": 67000.0,
            "mempool_price": 67500.0,
            "confidence": 0.85,
            "tx_count": 1234,
            "diff_amount": 500.0,
            "diff_percent": 0.746,
            "is_valid": True,
        }

        # Use in-memory DuckDB for testing
        with patch("scripts.daily_analysis.duckdb.connect") as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            save_to_duckdb(data, ":memory:", "/tmp/backup.db")

            # Should execute INSERT statement
            assert mock_conn.execute.called
            call_args = mock_conn.execute.call_args[0][0]
            assert "INSERT" in call_args and "price_analysis" in call_args

    def test_save_to_duckdb_creates_table_if_not_exists(self):
        """Should auto-create table schema on first run"""
        from scripts.daily_analysis import init_database

        with patch("scripts.daily_analysis.duckdb.connect") as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            init_database(":memory:")

            # Should execute CREATE TABLE IF NOT EXISTS
            assert mock_conn.execute.called
            call_args = mock_conn.execute.call_args[0][0]
            assert "CREATE TABLE IF NOT EXISTS price_analysis" in call_args


# Summary comment for documentation
"""
INTEGRATION TESTS STATUS (T034-T037):

These tests are EXPECTED TO FAIL initially (TDD Red phase).

Next steps:
1. Run: pytest tests/test_daily_analysis.py -v (should show 8 failures)
2. Implement scripts/daily_analysis.py (T038-T047)
3. Run tests again (should pass - TDD Green phase)

Test Coverage:
✅ T034: Mempool price fetch (2 tests)
✅ T035: UTXOracle price calculation (2 tests)
✅ T036: Price comparison logic (2 tests)
✅ T037: DuckDB save operations (2 tests)

Total: 8 tests written (all should fail before implementation)
"""
