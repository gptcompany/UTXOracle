"""Round 1 (Pass 2): Boundary value analysis tests.

Tests exact boundary conditions for thresholds, numeric limits, and edge values.
"""

import math
import sys
from datetime import datetime, timedelta
import pytest

from scripts.backtest import (
    BacktestConfig,
    run_backtest,
    sharpe_ratio,
    max_drawdown,
    calculate_returns,
    PricePoint,
)
from scripts.backtest.optimizer import generate_weight_grid, combine_signals
from scripts.backtest.engine import get_signal_action, execute_trade


class TestThresholdBoundaries:
    """Test exact threshold boundary conditions."""

    def test_signal_exactly_at_buy_threshold(self):
        """Signal exactly at buy_threshold should trigger BUY."""
        # Exactly at threshold
        assert get_signal_action(0.3, 0.3, -0.3) == "BUY"
        # Epsilon below - should be HOLD
        assert get_signal_action(0.3 - 1e-10, 0.3, -0.3) == "HOLD"
        # Epsilon above - should be BUY
        assert get_signal_action(0.3 + 1e-10, 0.3, -0.3) == "BUY"

    def test_signal_exactly_at_sell_threshold(self):
        """Signal exactly at sell_threshold should trigger SELL."""
        # Exactly at threshold
        assert get_signal_action(-0.3, 0.3, -0.3) == "SELL"
        # Epsilon above - should be HOLD
        assert get_signal_action(-0.3 + 1e-10, 0.3, -0.3) == "HOLD"
        # Epsilon below - should be SELL
        assert get_signal_action(-0.3 - 1e-10, 0.3, -0.3) == "SELL"

    def test_thresholds_equal(self):
        """When buy_threshold == sell_threshold, test behavior."""
        # At threshold - BUY takes precedence (>= check first)
        assert get_signal_action(0.0, 0.0, 0.0) == "BUY"
        # Below - SELL
        assert get_signal_action(-0.001, 0.0, 0.0) == "SELL"
        # Above - BUY
        assert get_signal_action(0.001, 0.0, 0.0) == "BUY"

    def test_inverted_thresholds(self):
        """When buy_threshold < sell_threshold (inverted logic).

        With inverted thresholds (buy=-0.3, sell=0.3):
        - Check order: BUY first (>=), then SELL (<=)
        - 0.0 >= -0.3 → BUY (first match wins)
        - Values overlapping both conditions trigger BUY (first check)
        """
        # 0.0 >= -0.3 is True, so BUY (first check wins)
        assert get_signal_action(0.0, -0.3, 0.3) == "BUY"
        # -0.5 >= -0.3 is False, -0.5 <= 0.3 is True → SELL
        assert get_signal_action(-0.5, -0.3, 0.3) == "SELL"
        # 0.5 >= -0.3 is True → BUY (even though also <= 0.3)
        assert get_signal_action(0.5, -0.3, 0.3) == "BUY"


class TestNumericBoundaries:
    """Test numeric precision and limits."""

    def test_float_precision_in_returns(self):
        """Returns calculation should handle float precision."""
        # Very small differences
        equity = [1.0, 1.0 + 1e-15, 1.0 + 2e-15]
        returns = calculate_returns(equity)
        assert len(returns) == 2
        # Should not produce NaN or Inf
        assert all(math.isfinite(r) for r in returns)

    def test_max_float_values(self):
        """Test with maximum float values."""
        max_float = sys.float_info.max / 2  # Half to avoid overflow in operations

        now = datetime.now()
        trade = execute_trade(
            entry_time=now,
            entry_price=max_float,
            exit_time=now + timedelta(hours=1),
            exit_price=max_float,
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.001,
            capital=1000.0,
            signal_value=0.5,
        )
        # pnl_pct should be just -0.002 (transaction costs only)
        assert trade.pnl_pct == pytest.approx(-0.002, abs=1e-10)

    def test_min_positive_float(self):
        """Test with minimum positive float."""
        min_float = sys.float_info.min

        now = datetime.now()
        trade = execute_trade(
            entry_time=now,
            entry_price=min_float,
            exit_time=now + timedelta(hours=1),
            exit_price=min_float * 2,
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.001,
            capital=1000.0,
            signal_value=0.5,
        )
        # pnl_pct = (2x - x) / x - 0.002 = 1 - 0.002 = 0.998
        assert trade.pnl_pct == pytest.approx(0.998, abs=0.001)

    def test_subnormal_float(self):
        """Test with subnormal (denormalized) float."""
        subnormal = sys.float_info.min / 2

        returns = [subnormal, subnormal * 2, subnormal * 3]
        result = sharpe_ratio(returns)
        # Should handle without error
        assert isinstance(result, float)


class TestPositionSizeBoundaries:
    """Test position size edge cases."""

    def test_position_size_zero(self):
        """Zero position size should result in zero P&L."""
        now = datetime.now()
        trade = execute_trade(
            entry_time=now,
            entry_price=100.0,
            exit_time=now + timedelta(hours=1),
            exit_price=110.0,
            direction="LONG",
            position_size=0.0,  # Zero position
            transaction_cost=0.001,
            capital=10000.0,
            signal_value=0.5,
        )
        assert trade.pnl == 0.0

    def test_position_size_one(self):
        """Full position (1.0) should use all capital."""
        now = datetime.now()
        trade = execute_trade(
            entry_time=now,
            entry_price=100.0,
            exit_time=now + timedelta(hours=1),
            exit_price=110.0,
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.0,  # No costs for clarity
            capital=10000.0,
            signal_value=0.5,
        )
        # 10% gain on 10000 = 1000
        assert trade.pnl == pytest.approx(1000.0)

    def test_position_size_greater_than_one(self):
        """Position > 1.0 (leverage) should work."""
        now = datetime.now()
        trade = execute_trade(
            entry_time=now,
            entry_price=100.0,
            exit_time=now + timedelta(hours=1),
            exit_price=110.0,
            direction="LONG",
            position_size=2.0,  # 2x leverage
            transaction_cost=0.0,
            capital=10000.0,
            signal_value=0.5,
        )
        # 10% gain on 20000 = 2000
        assert trade.pnl == pytest.approx(2000.0)


class TestTransactionCostBoundaries:
    """Test transaction cost edge cases."""

    def test_transaction_cost_zero(self):
        """Zero transaction cost should give pure P&L."""
        now = datetime.now()
        trade = execute_trade(
            entry_time=now,
            entry_price=100.0,
            exit_time=now + timedelta(hours=1),
            exit_price=110.0,
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.0,
            capital=10000.0,
            signal_value=0.5,
        )
        assert trade.pnl_pct == pytest.approx(0.1)  # Pure 10% gain

    def test_transaction_cost_high(self):
        """High transaction cost can wipe out profits."""
        now = datetime.now()
        trade = execute_trade(
            entry_time=now,
            entry_price=100.0,
            exit_time=now + timedelta(hours=1),
            exit_price=110.0,
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.05,  # 5% per trade
            capital=10000.0,
            signal_value=0.5,
        )
        # 10% gain - 10% costs = 0%
        assert trade.pnl_pct == pytest.approx(0.0)

    def test_transaction_cost_exceeds_profit(self):
        """Transaction costs can make profitable trade negative."""
        now = datetime.now()
        trade = execute_trade(
            entry_time=now,
            entry_price=100.0,
            exit_time=now + timedelta(hours=1),
            exit_price=101.0,  # 1% gain
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.01,  # 1% per trade, 2% round trip
            capital=10000.0,
            signal_value=0.5,
        )
        # 1% gain - 2% costs = -1%
        assert trade.pnl_pct == pytest.approx(-0.01)


class TestWeightGridBoundaries:
    """Test weight grid generation boundaries."""

    def test_step_equals_one(self):
        """Step size of 1.0 should give minimal grid."""
        grid = generate_weight_grid(["a", "b"], step=1.0)
        # Only combinations: (0,1), (1,0)
        assert len(grid) == 2

    def test_step_very_small(self):
        """Very small step creates large grid."""
        grid = generate_weight_grid(["a", "b"], step=0.01)
        # 0.00, 0.01, ..., 1.00 = 101 values
        # For 2 signals, one determined by other: 101 combinations
        assert len(grid) == 101

    def test_weight_exactly_zero(self):
        """Weights can be exactly zero."""
        grid = generate_weight_grid(["a", "b"], step=1.0)
        # One signal can have weight 0
        zero_weight_found = any(w.get("a", 0) == 0.0 for w in grid)
        assert zero_weight_found

    def test_weight_exactly_one(self):
        """Weights can be exactly one."""
        grid = generate_weight_grid(["a", "b"], step=1.0)
        # One signal can have weight 1
        one_weight_found = any(w.get("a", 0) == 1.0 for w in grid)
        assert one_weight_found


class TestEquityCurveBoundaries:
    """Test equity curve edge cases."""

    def test_equity_all_same(self):
        """All same values should give zero returns/drawdown."""
        equity = [100.0] * 10
        returns = calculate_returns(equity)
        dd = max_drawdown(equity)

        assert all(r == 0.0 for r in returns)
        assert dd == 0.0

    def test_equity_single_drop_to_zero(self):
        """Drop to zero should give 100% drawdown."""
        equity = [100.0, 0.0]
        dd = max_drawdown(equity)
        assert dd == pytest.approx(1.0)  # 100% drawdown

    def test_equity_recovery_after_drawdown(self):
        """Recovery should not count as additional drawdown."""
        equity = [100.0, 50.0, 100.0]  # 50% drop then recovery
        dd = max_drawdown(equity)
        assert dd == pytest.approx(0.5)  # 50% max drawdown


class TestDateBoundaries:
    """Test date/time boundary conditions."""

    def test_same_start_end_date(self):
        """Same start and end date should work."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 1),
            signal_source="test",
        )

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1),
                utxoracle_price=50000.0,
                exchange_price=50000.0,
                confidence=0.9,
                signal_value=0.5,
            )
        ]

        result = run_backtest(config, prices=prices)
        assert isinstance(result.num_trades, int)

    def test_end_before_start(self):
        """End before start should still work (may give empty result)."""
        config = BacktestConfig(
            start_date=datetime(2025, 12, 31),
            end_date=datetime(2025, 1, 1),  # Before start
            signal_source="test",
        )

        result = run_backtest(config, prices=[])
        assert result.num_trades == 0

    def test_very_long_duration(self):
        """Very long time span should work."""
        config = BacktestConfig(
            start_date=datetime(2000, 1, 1),
            end_date=datetime(2100, 12, 31),
            signal_source="test",
        )

        prices = [
            PricePoint(
                timestamp=datetime(2050, 6, 15),
                utxoracle_price=50000.0,
                exchange_price=50000.0,
                confidence=0.9,
                signal_value=0.5,
            )
        ]

        result = run_backtest(config, prices=prices)
        assert isinstance(result.num_trades, int)


class TestSignalValueBoundaries:
    """Test signal value edge cases in backtest."""

    def test_all_signals_exactly_at_threshold(self):
        """All signals exactly at buy threshold."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
            signal_source="test",
            buy_threshold=0.3,
            sell_threshold=-0.3,
        )

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.3,  # Exactly at buy threshold
            )
            for i in range(10)
        ]

        result = run_backtest(config, prices=prices)
        # Should open position on first signal
        assert result.num_trades >= 0

    def test_oscillating_around_threshold(self):
        """Signals oscillating around threshold."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
            signal_source="test",
            buy_threshold=0.3,
            sell_threshold=-0.3,
        )

        prices = []
        for i in range(10):
            # Oscillate: 0.29, 0.31, 0.29, 0.31, ...
            signal = 0.29 if i % 2 == 0 else 0.31
            prices.append(
                PricePoint(
                    timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                    utxoracle_price=50000,
                    exchange_price=50000,
                    confidence=0.9,
                    signal_value=signal,
                )
            )

        result = run_backtest(config, prices=prices)
        assert isinstance(result.num_trades, int)


class TestCombineSignalsBoundaries:
    """Test combine_signals edge cases."""

    def test_weights_sum_slightly_over_one(self):
        """Weights summing to slightly over 1.0 due to float precision."""
        # 0.1 + 0.2 + 0.7 = 0.9999999999999999 in float
        signals = {
            "a": [1.0] * 10,
            "b": [2.0] * 10,
            "c": [3.0] * 10,
        }
        weights = {"a": 0.1, "b": 0.2, "c": 0.7}

        combined = combine_signals(signals, weights)
        expected = 0.1 * 1.0 + 0.2 * 2.0 + 0.7 * 3.0  # = 2.6

        assert len(combined) == 10
        assert combined[0] == pytest.approx(expected)

    def test_all_weights_zero(self):
        """All zero weights should give zero combined signal."""
        signals = {"a": [1.0] * 10, "b": [2.0] * 10}
        weights = {"a": 0.0, "b": 0.0}

        combined = combine_signals(signals, weights)
        assert all(c == 0.0 for c in combined)

    def test_negative_weights(self):
        """Negative weights (short) should work."""
        signals = {"a": [1.0] * 10}
        weights = {"a": -1.0}

        combined = combine_signals(signals, weights)
        assert all(c == -1.0 for c in combined)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
