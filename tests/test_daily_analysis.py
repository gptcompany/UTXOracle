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


class TestQuestDBSave:
    """T037: Test saving data to QuestDB"""

    def test_save_to_questdb(self):
        """Should insert price comparison data into QuestDB"""
        from scripts.daily_analysis import save_to_questdb

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

        with patch("scripts.daily_analysis.QuestDBRepository") as mock_repo_cls:
            mock_repo = Mock()
            mock_repo_cls.return_value = mock_repo
            
            save_to_questdb(data)
            
            assert mock_repo._send_row.called
            call_args = mock_repo._send_row.call_args
            assert call_args[0][0] == "price_analysis"
            assert call_args[1]["flush"] is True


class TestPriceValidation:
    """T042a, T103: Test price validation logic"""

    def test_validate_price_data_success(self):
        from scripts.daily_analysis import validate_price_data

        config = {
            "UTXORACLE_CONFIDENCE_THRESHOLD": 0.3,
            "MIN_PRICE_USD": 10000,
            "MAX_PRICE_USD": 500000,
            "MAX_PRICE_DIVERGENCE_PERCENT": 5.0,
        }
        data = {
            "utxoracle_price": 60000.0,
            "confidence": 0.9,
            "diff_percent": 1.0,
            "mempool_price": 60600.0,
        }

        assert validate_price_data(data, config) is True

    def test_validate_price_data_divergence_warning(self):
        """T103: Large divergence should trigger warning but return True (valid)"""
        from scripts.daily_analysis import validate_price_data
        import logging

        config = {
            "UTXORACLE_CONFIDENCE_THRESHOLD": 0.3,
            "MIN_PRICE_USD": 10000,
            "MAX_PRICE_USD": 500000,
            "MAX_PRICE_DIVERGENCE_PERCENT": 5.0,
        }
        data = {
            "utxoracle_price": 60000.0,
            "confidence": 0.9,
            "diff_percent": 10.0,  # 10% > 5%
            "mempool_price": 66000.0,
        }

        with patch("scripts.daily_analysis.logging.warning") as mock_warn:
            assert validate_price_data(data, config) is True
            assert mock_warn.called
            assert "Large price divergence detected" in mock_warn.call_args[0][0]


class TestFailureRecovery:
    """T102: Test system resilience and failure recovery"""

    def test_retry_with_backoff_retries_until_success(self):
        """Retry helper should retry transient failures and then succeed."""
        from scripts.daily_analysis import retry_with_backoff

        attempts = {"count": 0}

        def flaky_call():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ValueError("temporary failure")
            return "ok"

        with patch("time.sleep") as mock_sleep:
            result = retry_with_backoff(flaky_call, max_retries=3, delay=0.1)

        assert result == "ok"
        assert attempts["count"] == 3
        assert mock_sleep.call_count == 2

    def test_fetch_bitcoin_transactions_falls_back_to_public_api(self):
        """Tier 2 fallback should activate when Tier 1 fails and fallback is enabled."""
        from scripts.daily_analysis import fetch_bitcoin_transactions
        import requests

        config = {
            "MEMPOOL_API_URL": "http://localhost:8999",
            "MEMPOOL_FALLBACK_ENABLED": True,
            "MEMPOOL_FALLBACK_URL": "https://mempool.space",
            "BITCOIN_DATADIR": "~/.bitcoin",
        }

        with patch(
            "scripts.daily_analysis._fetch_from_mempool_local",
            side_effect=requests.RequestException("tier1 down"),
        ), patch(
            "scripts.daily_analysis._fetch_from_mempool_public",
            return_value=[{"txid": "abc"}],
        ) as mock_fallback:
            transactions, tier = fetch_bitcoin_transactions(config)

        assert transactions == [{"txid": "abc"}]
        assert tier == 2
        assert mock_fallback.called


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
