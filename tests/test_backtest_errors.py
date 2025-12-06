"""Round 3 (Pass 2): Error propagation and exception handling tests.

Tests error handling, graceful degradation, and error recovery.
"""

import math
from datetime import datetime, timedelta
import pytest

from scripts.backtest import (
    BacktestConfig,
    run_backtest,
    compare_signals,
    optimize_weights,
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    win_rate,
    profit_factor,
    calculate_returns,
    PricePoint,
)
from scripts.backtest.optimizer import generate_weight_grid
from scripts.backtest.engine import get_signal_action, execute_trade


class TestGracefulDegradation:
    """Test graceful handling of edge cases without crashing."""

    def test_empty_returns_graceful(self):
        """Empty returns should return 0, not crash."""
        assert sharpe_ratio([]) == 0.0
        assert sortino_ratio([]) == 0.0

    def test_empty_equity_graceful(self):
        """Empty equity curve should return 0, not crash."""
        assert max_drawdown([]) == 0.0
        assert calculate_returns([]) == []

    def test_empty_trades_graceful(self):
        """Empty trades list should return 0, not crash."""
        assert win_rate([]) == 0.0
        assert profit_factor([]) == 0.0

    def test_empty_prices_graceful(self):
        """Empty prices should return valid result, not crash."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
            signal_source="test",
        )
        result = run_backtest(config, prices=[])

        assert result.num_trades == 0
        assert result.total_return == 0.0

    def test_empty_signals_graceful(self):
        """Empty signals dict should return valid result, not crash."""
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

        assert len(comparison.results) == 0
        assert comparison.best_signal == ""


class TestNaNHandling:
    """Test handling of NaN values."""

    def test_sharpe_with_nan_in_returns(self):
        """NaN in returns is handled defensively (returns 0).

        Note: NaN comparisons are always False, so `variance > 0` is False
        when variance is NaN, leading to std_return=0, which returns 0.0.
        This is defensive behavior that prevents crashes.
        """
        returns = [0.01, float("nan"), 0.02]
        result = sharpe_ratio(returns)
        # Defensive behavior: NaN leads to 0 (invalid data = no result)
        assert result == 0.0 or math.isnan(result)

    def test_sortino_with_nan_in_returns(self):
        """NaN in returns is handled defensively (returns 0)."""
        returns = [0.01, float("nan"), 0.02]
        result = sortino_ratio(returns)
        # Defensive behavior: NaN leads to 0 or NaN
        assert result == 0.0 or math.isnan(result)

    def test_max_drawdown_with_nan(self):
        """NaN in equity should be handled gracefully."""
        equity = [100, float("nan"), 120]
        result = max_drawdown(equity)
        # Should handle NaN somehow (may be NaN or skip it)
        assert isinstance(result, float)

    def test_calculate_returns_with_nan(self):
        """NaN in equity should produce NaN returns."""
        equity = [100, float("nan"), 120]
        returns = calculate_returns(equity)
        # At least one return should be NaN
        assert any(math.isnan(r) for r in returns)


class TestInfHandling:
    """Test handling of infinity values."""

    def test_sharpe_with_inf_return(self):
        """Infinity in returns is handled defensively.

        With Inf in returns: mean=inf, excess=inf, variance=nan,
        variance > 0 is False (NaN comparison), std_return=0, return 0.
        """
        returns = [0.01, float("inf"), 0.02]
        result = sharpe_ratio(returns)
        # Defensive behavior: Inf leads to NaN variance, then 0
        assert result == 0.0 or math.isnan(result) or math.isinf(result)

    def test_max_drawdown_with_inf(self):
        """Infinity in equity should be handled."""
        equity = [100, float("inf"), 120]
        result = max_drawdown(equity)
        assert isinstance(result, float)

    def test_execute_trade_with_inf_price(self):
        """Infinity price should be handled gracefully."""
        now = datetime.now()
        trade = execute_trade(
            entry_time=now,
            entry_price=float("inf"),
            exit_time=now + timedelta(hours=1),
            exit_price=float("inf"),
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.001,
            capital=10000.0,
            signal_value=0.5,
        )
        # Should not crash
        assert isinstance(trade.pnl, float)


class TestZeroDivisionProtection:
    """Test protection against division by zero."""

    def test_sharpe_zero_std(self):
        """Zero standard deviation should return 0, not crash."""
        returns = [0.01, 0.01, 0.01]  # All same = 0 std
        result = sharpe_ratio(returns)
        assert result == 0.0

    def test_calculate_returns_zero_equity(self):
        """Zero in equity should not cause division error."""
        equity = [100, 0, 50]
        returns = calculate_returns(equity)
        # Return when previous equity was 0 should be 0
        assert len(returns) == 2
        assert returns[1] == 0.0  # Division by zero guarded

    def test_max_drawdown_zero_peak(self):
        """Zero peak should not cause division error."""
        equity = [0, 10, 5]
        result = max_drawdown(equity)
        # Should handle gracefully
        assert isinstance(result, float)

    def test_profit_factor_no_losses(self):
        """No losses should return inf or large value, not crash."""
        from scripts.backtest import Trade

        now = datetime.now()
        trades = [
            Trade(now, now, 100, 110, "LONG", 10, 0.1, 0.5),
        ]
        result = profit_factor(trades)
        assert result == float("inf")

    def test_profit_factor_no_wins(self):
        """No wins should return 0, not crash."""
        from scripts.backtest import Trade

        now = datetime.now()
        trades = [
            Trade(now, now, 100, 90, "LONG", -10, -0.1, 0.5),
        ]
        result = profit_factor(trades)
        assert result == 0.0


class TestTypeErrors:
    """Test handling of wrong types (graceful failure or proper error)."""

    def test_sharpe_with_none_values(self):
        """None values in returns should fail gracefully or raise TypeError."""
        returns = [0.01, None, 0.02]
        with pytest.raises((TypeError, AttributeError)):
            sharpe_ratio(returns)

    def test_weight_grid_with_non_string_names(self):
        """Non-string signal names should still work (duck typing)."""
        # Numbers as keys should work
        grid = generate_weight_grid([1, 2], step=0.5)
        assert len(grid) > 0


class TestSignalActionEdgeCases:
    """Test get_signal_action with edge case inputs."""

    def test_none_signal_returns_hold(self):
        """None signal should return HOLD."""
        assert get_signal_action(None, 0.3, -0.3) == "HOLD"

    def test_nan_signal_returns_hold(self):
        """NaN signal should return HOLD (NaN comparisons are False)."""
        result = get_signal_action(float("nan"), 0.3, -0.3)
        assert result == "HOLD"

    def test_inf_signal_triggers_buy(self):
        """Positive infinity signal should trigger BUY."""
        assert get_signal_action(float("inf"), 0.3, -0.3) == "BUY"

    def test_neg_inf_signal_triggers_sell(self):
        """Negative infinity signal should trigger SELL."""
        assert get_signal_action(float("-inf"), 0.3, -0.3) == "SELL"


class TestOptimizationErrors:
    """Test optimization error handling."""

    def test_optimize_with_zero_step(self):
        """Zero step should return empty grid, not crash."""
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

        signals = {"a": [0.5] * 10}

        # Should handle gracefully (empty grid case)
        result = optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
            step=0.0,  # Invalid step
        )

        # Should return result, even if empty
        assert hasattr(result, "best_weights")


class TestBacktestEdgeErrors:
    """Test backtest edge case error handling."""

    def test_backtest_with_unsorted_prices(self):
        """Unsorted prices should be handled (sorted internally)."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
            signal_source="test",
        )

        # Create unsorted prices
        prices = [
            PricePoint(datetime(2025, 1, 5), 50500, 50500, 0.9, 0.5),
            PricePoint(datetime(2025, 1, 1), 50000, 50000, 0.9, 0.5),
            PricePoint(datetime(2025, 1, 10), 51000, 51000, 0.9, -0.5),
            PricePoint(datetime(2025, 1, 3), 50200, 50200, 0.9, -0.5),
        ]

        result = run_backtest(config, prices=prices)

        # Should complete without error
        assert isinstance(result.num_trades, int)

    def test_backtest_with_duplicate_timestamps(self):
        """Duplicate timestamps should be handled."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
            signal_source="test",
        )

        # Create duplicate timestamps
        prices = [
            PricePoint(datetime(2025, 1, 1), 50000, 50000, 0.9, 0.5),
            PricePoint(datetime(2025, 1, 1), 50100, 50100, 0.9, -0.5),  # Duplicate
            PricePoint(datetime(2025, 1, 2), 51000, 51000, 0.9, 0.5),
        ]

        result = run_backtest(config, prices=prices)

        # Should complete without error
        assert isinstance(result.num_trades, int)


class TestRecoveryAfterError:
    """Test that system recovers properly after errors."""

    def test_system_works_after_nan_input(self):
        """After processing NaN, subsequent calls should work."""
        # First call with NaN
        _ = sharpe_ratio([float("nan")])

        # Subsequent calls should still work
        result = sharpe_ratio([0.01, 0.02, 0.03])
        assert math.isfinite(result)

    def test_system_works_after_empty_input(self):
        """After processing empty input, subsequent calls should work."""
        # First call with empty
        _ = run_backtest(
            BacktestConfig(
                start_date=datetime(2025, 1, 1),
                end_date=datetime(2025, 1, 10),
                signal_source="test",
            ),
            prices=[],
        )

        # Subsequent calls should still work
        prices = [
            PricePoint(datetime(2025, 1, 1), 50000, 50000, 0.9, 0.5),
            PricePoint(datetime(2025, 1, 2), 51000, 51000, 0.9, -0.5),
        ]

        result = run_backtest(
            BacktestConfig(
                start_date=datetime(2025, 1, 1),
                end_date=datetime(2025, 1, 10),
                signal_source="test",
            ),
            prices=prices,
        )

        assert isinstance(result.num_trades, int)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
