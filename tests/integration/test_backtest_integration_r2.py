"""Round 2: Integration pipeline verification tests.

Tests end-to-end data flows, edge cases in pipelines, and cross-module interactions.
"""

from datetime import datetime, timedelta
import pytest

from scripts.backtest import (
    BacktestConfig,
    BacktestResult,
    ComparisonResult,
    Trade,
    run_backtest,
    compare_signals,
    optimize_weights,
    walk_forward_validate,
    calculate_returns,
    calculate_all_metrics,
    PricePoint,
)


class TestDataFlowIntegration:
    """Test data flows through the pipeline."""

    def test_empty_data_propagates_correctly(self):
        """Empty data should propagate without crashes."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 31),
            signal_source="test",
        )

        result = run_backtest(config, prices=[])

        # Empty result, but valid structure
        assert result.num_trades == 0
        assert result.total_return == 0.0
        assert result.trades == []
        assert result.equity_curve == []

    def test_single_price_point_flow(self):
        """Single price point should work without errors."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 1),
            signal_source="test",
        )

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1),
                utxoracle_price=50000.0,
                exchange_price=50100.0,
                confidence=0.9,
                signal_value=0.5,  # BUY signal
            )
        ]

        result = run_backtest(config, prices=prices)

        # With only one price point, trade can open but not close properly
        # Result should still be valid
        assert isinstance(result, BacktestResult)
        assert result.config == config

    def test_compare_signals_empty_signals_dict(self):
        """Empty signals dict should return valid ComparisonResult."""
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.0,
            )
            for i in range(10)
        ]

        comparison = compare_signals(
            signals={},
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
        )

        assert isinstance(comparison, ComparisonResult)
        assert len(comparison.results) == 0
        assert comparison.best_signal == ""

    def test_optimize_weights_single_signal(self):
        """Single signal optimization should give weight 1.0."""
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.0,
            )
            for i in range(20)
        ]

        signals = {"only_signal": [0.5] * 20}

        result = optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 20),
        )

        assert "only_signal" in result.best_weights
        assert result.best_weights["only_signal"] == 1.0


class TestMetricsPipelineIntegration:
    """Test metrics calculations through the full pipeline."""

    def test_metrics_consistency_with_trades(self):
        """Metrics should be consistent with trade data."""
        now = datetime.now()
        trades = [
            Trade(now, now + timedelta(hours=1), 100, 110, "LONG", 10, 0.1, 0.5),
            Trade(
                now + timedelta(hours=2),
                now + timedelta(hours=3),
                110,
                100,
                "LONG",
                -10,
                -0.09,
                0.5,
            ),
            Trade(
                now + timedelta(hours=4),
                now + timedelta(hours=5),
                100,
                120,
                "LONG",
                20,
                0.2,
                0.5,
            ),
        ]

        equity_curve = [10000, 10010, 10000, 10020]

        metrics = calculate_all_metrics(trades, equity_curve)

        # Win rate: 2 winners / 3 trades = 0.666...
        assert metrics["win_rate"] == pytest.approx(2 / 3)

        # Profit factor: (10 + 20) / 10 = 3.0
        assert metrics["profit_factor"] == pytest.approx(3.0)

        # Max drawdown: peak 10010 to trough 10000 = 0.1%
        assert metrics["max_drawdown"] == pytest.approx(10 / 10010, rel=0.01)

    def test_metrics_with_no_trades(self):
        """Metrics should handle no trades gracefully."""
        metrics = calculate_all_metrics([], [10000])

        assert metrics["win_rate"] == 0.0
        assert metrics["profit_factor"] == 0.0

    def test_returns_calculation_accuracy(self):
        """Returns should be calculated correctly from equity curve."""
        equity_curve = [100, 110, 99, 120]

        returns = calculate_returns(equity_curve)

        assert len(returns) == 3
        assert returns[0] == pytest.approx(0.1)  # 110-100 / 100
        assert returns[1] == pytest.approx(-0.1)  # 99-110 / 110
        assert returns[2] == pytest.approx(0.2121, rel=0.01)  # 120-99 / 99


class TestWalkForwardIntegration:
    """Test walk-forward validation pipeline."""

    def test_walk_forward_basic(self):
        """Basic walk-forward should split data correctly."""
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.0,
            )
            for i in range(100)
        ]

        signals = {
            "trend": [0.5] * 100,
            "contrarian": [-0.5] * 100,
        }

        weights = {"trend": 0.7, "contrarian": 0.3}

        result = walk_forward_validate(
            weights=weights,
            signals=signals,
            prices=prices,
            train_ratio=0.7,
        )

        assert "train_sharpe" in result
        assert "test_sharpe" in result
        # Both should be numeric (may be 0 or NaN for edge cases)
        assert isinstance(result["train_sharpe"], float)
        assert isinstance(result["test_sharpe"], float)

    def test_walk_forward_empty_prices(self):
        """Walk-forward with empty prices should return zeros."""
        result = walk_forward_validate(
            weights={"a": 1.0},
            signals={"a": [0.5] * 10},
            prices=[],
        )

        assert result["train_sharpe"] == 0.0
        assert result["test_sharpe"] == 0.0


class TestSignalEdgeCases:
    """Test edge cases in signal processing."""

    def test_all_none_signals(self):
        """All None signals should result in no trades."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
            signal_source="test",
        )

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=None,  # All None signals
            )
            for i in range(10)
        ]

        result = run_backtest(config, prices=prices)

        assert result.num_trades == 0

    def test_alternating_buy_sell_signals(self):
        """Rapidly alternating signals should generate many trades."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 20),
            signal_source="test",
            buy_threshold=0.3,
            sell_threshold=-0.3,
        )

        prices = []
        for i in range(20):
            # Alternate between BUY and SELL signals
            signal = 0.5 if i % 2 == 0 else -0.5
            prices.append(
                PricePoint(
                    timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                    utxoracle_price=50000 + (i % 5) * 100,
                    exchange_price=50000 + (i % 5) * 100,
                    confidence=0.9,
                    signal_value=signal,
                )
            )

        result = run_backtest(config, prices=prices)

        # Should generate multiple trades from alternating signals
        assert result.num_trades > 0

    def test_extreme_signal_values(self):
        """Extreme signal values should be handled correctly."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 5),
            signal_source="test",
        )

        prices = [
            PricePoint(
                datetime(2025, 1, 1), 50000, 50000, 0.9, float("inf")
            ),  # Infinity
            PricePoint(datetime(2025, 1, 2), 51000, 51000, 0.9, -1000),  # Very negative
            PricePoint(datetime(2025, 1, 3), 52000, 52000, 0.9, 1000),  # Very positive
            PricePoint(datetime(2025, 1, 4), 53000, 53000, 0.9, 0),  # Zero
            PricePoint(
                datetime(2025, 1, 5), 54000, 54000, 0.9, float("-inf")
            ),  # Neg infinity
        ]

        result = run_backtest(config, prices=prices)

        # Should complete without error
        assert isinstance(result, BacktestResult)


class TestComparisonRanking:
    """Test signal comparison and ranking."""

    def test_ranking_order_by_sharpe(self):
        """Signals should be ranked by Sharpe ratio (descending)."""
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,  # Uptrending price
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.0,
            )
            for i in range(50)
        ]

        signals = {
            "always_buy": [0.5] * 50,  # Should profit in uptrend
            "always_sell": [-0.5] * 50,  # Should lose in uptrend
            "neutral": [0.0] * 50,  # No trades
        }

        comparison = compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 2, 19),
        )

        # In uptrend, always_buy should outperform always_sell
        # Ranking should reflect this
        assert len(comparison.ranking) == 3
        # First in ranking should have highest Sharpe
        first = comparison.ranking[0]
        last = comparison.ranking[-1]
        assert (
            comparison.results[first].sharpe_ratio
            >= comparison.results[last].sharpe_ratio
        )


class TestTransactionCostImpact:
    """Test transaction cost handling."""

    def test_high_transaction_costs_reduce_profits(self):
        """High transaction costs should significantly reduce profits."""
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 200,  # Strong uptrend
                exchange_price=50000 + i * 200,
                confidence=0.9,
                signal_value=0.5 if i == 0 else -0.5 if i == 10 else 0.0,
            )
            for i in range(20)
        ]

        config_low_cost = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 20),
            signal_source="test",
            transaction_cost=0.0001,  # 0.01%
        )

        config_high_cost = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 20),
            signal_source="test",
            transaction_cost=0.05,  # 5%
        )

        result_low = run_backtest(config_low_cost, prices=prices)
        result_high = run_backtest(config_high_cost, prices=prices)

        # High costs should result in lower or negative returns
        assert result_low.total_return >= result_high.total_return


class TestPricePointDataIntegrity:
    """Test PricePoint data handling."""

    def test_pricepoint_with_none_exchange_price(self):
        """PricePoint with None exchange_price should work."""
        pp = PricePoint(
            timestamp=datetime(2025, 1, 1),
            utxoracle_price=50000.0,
            exchange_price=None,
            confidence=0.9,
            signal_value=0.5,
        )

        assert pp.exchange_price is None
        assert pp.utxoracle_price == 50000.0

    def test_pricepoint_zero_confidence(self):
        """Zero confidence should still work in backtest."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 5),
            signal_source="test",
        )

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.0,  # Zero confidence
                signal_value=0.5,
            )
            for i in range(5)
        ]

        result = run_backtest(config, prices=prices)

        # Should still produce valid result
        assert isinstance(result, BacktestResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
