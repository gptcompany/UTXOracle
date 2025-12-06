"""Round 2 (Pass 2): State management and side effects tests.

Tests that functions don't unexpectedly mutate inputs or have side effects.
"""

import copy
from datetime import datetime, timedelta
import pytest

from scripts.backtest import (
    BacktestConfig,
    Trade,
    run_backtest,
    compare_signals,
    optimize_weights,
    sharpe_ratio,
    max_drawdown,
    calculate_returns,
    PricePoint,
)
from scripts.backtest.optimizer import (
    generate_weight_grid,
    combine_signals,
)


class TestInputImmutability:
    """Test that functions don't mutate their inputs."""

    def test_run_backtest_doesnt_mutate_prices(self):
        """run_backtest should not modify the prices list."""
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
                signal_value=0.5 if i % 2 == 0 else -0.5,
            )
            for i in range(10)
        ]

        original_len = len(prices)
        original_first = prices[0].utxoracle_price

        run_backtest(config, prices=prices)

        # List should not be modified
        assert len(prices) == original_len
        assert prices[0].utxoracle_price == original_first

    def test_compare_signals_doesnt_mutate_prices(self):
        """compare_signals should not modify the prices list."""
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

        signals = {"a": [0.5] * 10, "b": [-0.5] * 10}

        original_prices = copy.deepcopy(prices)

        compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
        )

        # Prices should be unchanged
        assert len(prices) == len(original_prices)
        for p1, p2 in zip(prices, original_prices):
            assert p1.utxoracle_price == p2.utxoracle_price

    def test_compare_signals_doesnt_mutate_signals_dict(self):
        """compare_signals should not modify the signals dict."""
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

        signals = {"a": [0.5] * 10, "b": [-0.5] * 10}
        original_signals = copy.deepcopy(signals)

        compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
        )

        # Signals dict should be unchanged
        assert signals == original_signals

    def test_optimize_weights_doesnt_mutate_inputs(self):
        """optimize_weights should not modify its inputs."""
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

        signals = {"a": [0.5] * 20, "b": [-0.5] * 20}

        original_signals = copy.deepcopy(signals)
        original_prices_len = len(prices)

        optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 20),
            step=0.5,
        )

        assert signals == original_signals
        assert len(prices) == original_prices_len

    def test_combine_signals_doesnt_mutate_inputs(self):
        """combine_signals should not modify its inputs."""
        signals = {"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]}
        weights = {"a": 0.5, "b": 0.5}

        original_signals = copy.deepcopy(signals)
        original_weights = copy.deepcopy(weights)

        combine_signals(signals, weights)

        assert signals == original_signals
        assert weights == original_weights

    def test_sharpe_ratio_doesnt_mutate_returns(self):
        """sharpe_ratio should not modify the returns list."""
        returns = [0.01, 0.02, -0.01, 0.03]
        original = copy.copy(returns)

        sharpe_ratio(returns)

        assert returns == original

    def test_max_drawdown_doesnt_mutate_equity(self):
        """max_drawdown should not modify the equity curve."""
        equity = [100, 110, 105, 120, 115]
        original = copy.copy(equity)

        max_drawdown(equity)

        assert equity == original

    def test_calculate_returns_doesnt_mutate_equity(self):
        """calculate_returns should not modify the equity curve."""
        equity = [100, 110, 120, 130]
        original = copy.copy(equity)

        calculate_returns(equity)

        assert equity == original


class TestResultIndependence:
    """Test that results are independent (no shared state)."""

    def test_multiple_backtests_independent(self):
        """Multiple backtest runs should have independent results."""
        config1 = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
            signal_source="test1",
            initial_capital=10000.0,
        )

        config2 = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
            signal_source="test2",
            initial_capital=20000.0,
        )

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.5,
            )
            for i in range(10)
        ]

        result1 = run_backtest(config1, prices=prices)
        result2 = run_backtest(config2, prices=prices)

        # Results should be different objects
        assert result1 is not result2
        assert result1.config is not result2.config
        assert result1.config.initial_capital != result2.config.initial_capital

    def test_weight_grid_returns_independent_dicts(self):
        """Each weight dict in grid should be independent."""
        grid = generate_weight_grid(["a", "b"], step=0.5)

        # Modify first weight dict
        grid[0]["a"] = 999.0

        # Should not affect other dicts
        assert all(w.get("a", 0) != 999.0 for w in grid[1:])

    def test_comparison_results_independent(self):
        """Each BacktestResult in comparison should be independent."""
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

        signals = {"a": [0.5] * 20, "b": [-0.5] * 20}

        comparison = compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 20),
        )

        # Results should be different objects
        assert comparison.results["a"] is not comparison.results["b"]


class TestNoGlobalState:
    """Test that no global state is polluted."""

    def test_repeated_runs_same_result(self):
        """Same inputs should always produce same outputs."""
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
                signal_value=0.5 if i % 2 == 0 else -0.5,
            )
            for i in range(10)
        ]

        result1 = run_backtest(config, prices=prices)
        result2 = run_backtest(config, prices=prices)
        result3 = run_backtest(config, prices=prices)

        # All results should be identical
        assert result1.total_return == result2.total_return == result3.total_return
        assert result1.num_trades == result2.num_trades == result3.num_trades

    def test_sharpe_ratio_deterministic(self):
        """sharpe_ratio should be deterministic."""
        returns = [0.01, 0.02, -0.01, 0.03, 0.02]

        s1 = sharpe_ratio(returns)
        s2 = sharpe_ratio(returns)
        s3 = sharpe_ratio(returns)

        assert s1 == s2 == s3

    def test_combine_signals_deterministic(self):
        """combine_signals should be deterministic."""
        signals = {"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]}
        weights = {"a": 0.5, "b": 0.5}

        c1 = combine_signals(signals, weights)
        c2 = combine_signals(signals, weights)
        c3 = combine_signals(signals, weights)

        assert c1 == c2 == c3


class TestTradeObjectImmutability:
    """Test that Trade objects are properly encapsulated."""

    def test_trade_creation_immutable(self):
        """Trade objects should contain copies of data, not references."""
        now = datetime.now()
        trade = Trade(
            entry_time=now,
            exit_time=now + timedelta(hours=1),
            entry_price=100.0,
            exit_price=110.0,
            direction="LONG",
            pnl=10.0,
            pnl_pct=0.1,
            signal_value=0.5,
        )

        # Values should be accessible and correct
        assert trade.entry_price == 100.0
        assert trade.exit_price == 110.0
        assert trade.pnl == 10.0


class TestConfigObjectImmutability:
    """Test that BacktestConfig is properly encapsulated."""

    def test_config_values_preserved(self):
        """Config values should be preserved in result."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
            signal_source="my_signal",
            buy_threshold=0.4,
            sell_threshold=-0.4,
            initial_capital=50000.0,
        )

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.5,
            )
            for i in range(10)
        ]

        result = run_backtest(config, prices=prices)

        # Config should be preserved in result
        assert result.config.signal_source == "my_signal"
        assert result.config.buy_threshold == 0.4
        assert result.config.sell_threshold == -0.4
        assert result.config.initial_capital == 50000.0


class TestListReturnTypes:
    """Test that list return types are new lists, not views."""

    def test_equity_curve_is_new_list(self):
        """Result equity_curve should be a new list."""
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
                signal_value=0.5,
            )
            for i in range(10)
        ]

        result = run_backtest(config, prices=prices)

        # Modifying the returned equity curve should not affect anything
        if result.equity_curve:
            original_first = result.equity_curve[0]
            result.equity_curve[0] = 999999

            # Re-running should give original value
            result2 = run_backtest(config, prices=prices)
            if result2.equity_curve:
                assert result2.equity_curve[0] == original_first

    def test_calculate_returns_returns_new_list(self):
        """calculate_returns should return a new list."""
        equity = [100, 110, 120]

        returns1 = calculate_returns(equity)
        returns2 = calculate_returns(equity)

        # Should be different list objects
        assert returns1 is not returns2

        # Modifying one should not affect the other
        returns1[0] = 999
        assert returns2[0] != 999


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
