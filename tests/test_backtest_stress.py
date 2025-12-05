"""Stress tests for backtest framework - Bug hunting round 1.

Tests edge cases, extreme values, NaN/Inf handling, and boundary conditions.
"""

import math
from datetime import datetime, timedelta
import pytest

from scripts.backtest.engine import (
    BacktestConfig,
    Trade,
    get_signal_action,
    execute_trade,
    calculate_pnl,
    run_backtest,
)
from scripts.backtest.metrics import (
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    win_rate,
    profit_factor,
    calculate_returns,
)
from scripts.backtest.optimizer import (
    generate_weight_grid,
    combine_signals,
)
from scripts.backtest.data_loader import PricePoint


class TestEdgeCasesRound1:
    """Round 1: Edge case stress testing."""

    # ===================== SIGNAL ACTION EDGE CASES =====================

    def test_signal_action_nan(self):
        """NaN signal should return HOLD (or handle gracefully)."""
        result = get_signal_action(float("nan"), 0.3, -0.3)
        # NaN comparisons are always False, so should fall through to HOLD
        assert result == "HOLD"

    def test_signal_action_inf_positive(self):
        """Positive infinity signal should trigger BUY."""
        result = get_signal_action(float("inf"), 0.3, -0.3)
        assert result == "BUY"

    def test_signal_action_inf_negative(self):
        """Negative infinity signal should trigger SELL."""
        result = get_signal_action(float("-inf"), 0.3, -0.3)
        assert result == "SELL"

    def test_signal_action_threshold_boundary(self):
        """Signal exactly at threshold boundary."""
        # Exactly at buy threshold
        assert get_signal_action(0.3, 0.3, -0.3) == "BUY"
        # Exactly at sell threshold
        assert get_signal_action(-0.3, 0.3, -0.3) == "SELL"
        # Just inside HOLD zone
        assert get_signal_action(0.29999, 0.3, -0.3) == "HOLD"
        assert get_signal_action(-0.29999, 0.3, -0.3) == "HOLD"

    def test_signal_action_extreme_thresholds(self):
        """Extreme threshold values."""
        # Threshold at infinity (nothing triggers)
        assert get_signal_action(100, float("inf"), float("-inf")) == "HOLD"
        # Zero thresholds
        assert get_signal_action(0.001, 0.0, 0.0) == "BUY"
        assert get_signal_action(-0.001, 0.0, 0.0) == "SELL"
        assert get_signal_action(0.0, 0.0, 0.0) == "BUY"  # Exactly 0 >= 0

    # ===================== TRADE EXECUTION EDGE CASES =====================

    def test_execute_trade_zero_entry_price(self):
        """Zero entry price should not cause division by zero."""
        now = datetime.now()
        trade = execute_trade(
            entry_time=now,
            entry_price=0.0,
            exit_time=now + timedelta(hours=1),
            exit_price=100.0,
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.001,
            capital=10000.0,
            signal_value=0.5,
        )
        assert trade.pnl_pct == 0.0  # Guard kicks in

    def test_execute_trade_negative_entry_price(self):
        """Negative entry price (invalid but shouldn't crash)."""
        now = datetime.now()
        trade = execute_trade(
            entry_time=now,
            entry_price=-100.0,
            exit_time=now + timedelta(hours=1),
            exit_price=100.0,
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.001,
            capital=10000.0,
            signal_value=0.5,
        )
        # Should return 0 pnl_pct because entry_price <= 0
        assert trade.pnl_pct == 0.0

    def test_execute_trade_inf_prices(self):
        """Infinite prices should not crash."""
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
        # inf - inf = nan, nan / inf = nan
        assert math.isnan(trade.pnl_pct) or trade.pnl_pct == 0.0

    def test_execute_trade_zero_capital(self):
        """Zero capital should result in zero P&L."""
        now = datetime.now()
        trade = execute_trade(
            entry_time=now,
            entry_price=100.0,
            exit_time=now + timedelta(hours=1),
            exit_price=110.0,
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.001,
            capital=0.0,
            signal_value=0.5,
        )
        assert trade.pnl == 0.0

    def test_execute_trade_negative_capital(self):
        """Negative capital (debt) - edge case."""
        now = datetime.now()
        trade = execute_trade(
            entry_time=now,
            entry_price=100.0,
            exit_time=now + timedelta(hours=1),
            exit_price=110.0,
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.001,
            capital=-1000.0,
            signal_value=0.5,
        )
        # Negative capital * positive pnl_pct = negative pnl
        assert trade.pnl < 0

    # ===================== P&L CALCULATION EDGE CASES =====================

    def test_calculate_pnl_empty_trades(self):
        """Empty trade list should return initial capital."""
        total_return, equity_curve = calculate_pnl([], 10000.0)
        assert total_return == 0.0
        assert equity_curve == [10000.0]

    def test_calculate_pnl_zero_initial_capital(self):
        """Zero initial capital guard."""
        now = datetime.now()
        trades = [
            Trade(
                entry_time=now,
                exit_time=now,
                entry_price=100,
                exit_price=110,
                direction="LONG",
                pnl=100,
                pnl_pct=0.1,
                signal_value=0.5,
            )
        ]
        total_return, equity_curve = calculate_pnl(trades, 0.0)
        assert total_return == 0.0  # Guard against division by zero

    def test_calculate_pnl_negative_initial_capital(self):
        """Negative initial capital edge case (debt scenario)."""
        now = datetime.now()
        trades = [
            Trade(
                entry_time=now,
                exit_time=now,
                entry_price=100,
                exit_price=110,
                direction="LONG",
                pnl=100,
                pnl_pct=0.1,
                signal_value=0.5,
            )
        ]
        total_return, equity_curve = calculate_pnl(trades, -1000.0)
        # equity = -1000 + 100 = -900
        # total_return = (-900 - (-1000)) / -1000 = 100 / -1000 = -0.1
        # Mathematically correct: profit on debt = negative return
        assert total_return == pytest.approx(-0.1)

    # ===================== SHARPE RATIO EDGE CASES =====================

    def test_sharpe_ratio_empty_returns(self):
        """Empty returns should return 0."""
        assert sharpe_ratio([]) == 0.0

    def test_sharpe_ratio_single_return(self):
        """Single return (not enough data) should return 0."""
        assert sharpe_ratio([0.1]) == 0.0

    def test_sharpe_ratio_all_same_returns(self):
        """All same returns (zero variance) should return 0."""
        result = sharpe_ratio([0.01, 0.01, 0.01, 0.01])
        assert result == 0.0  # Zero std -> 0 Sharpe

    def test_sharpe_ratio_all_zero_returns(self):
        """All zero returns should return 0."""
        result = sharpe_ratio([0.0, 0.0, 0.0, 0.0])
        assert result == 0.0

    def test_sharpe_ratio_inf_returns(self):
        """Infinite returns should handle gracefully."""
        result = sharpe_ratio([float("inf"), 0.1, 0.2])
        # Mean will be inf, std will be inf, ratio is nan or 0
        assert math.isnan(result) or math.isinf(result) or result == 0.0

    def test_sharpe_ratio_nan_returns(self):
        """NaN in returns should propagate NaN or return 0."""
        result = sharpe_ratio([float("nan"), 0.1, 0.2])
        # NaN propagates through calculations
        assert math.isnan(result) or result == 0.0

    def test_sharpe_ratio_negative_annualization(self):
        """Negative annualization factor should return NaN (not crash)."""
        result = sharpe_ratio([0.01, 0.02, 0.03], annualization_factor=-252)
        # Should return NaN for invalid input
        assert math.isnan(result)

    # ===================== SORTINO RATIO EDGE CASES =====================

    def test_sortino_ratio_no_negative_returns(self):
        """All positive returns should return inf (or handle gracefully)."""
        result = sortino_ratio([0.1, 0.2, 0.3])
        assert result == float("inf") or result > 0

    def test_sortino_ratio_all_negative_returns(self):
        """All negative returns should produce negative Sortino."""
        result = sortino_ratio([-0.1, -0.2, -0.3])
        assert result < 0

    # ===================== MAX DRAWDOWN EDGE CASES =====================

    def test_max_drawdown_empty(self):
        """Empty equity curve should return 0."""
        assert max_drawdown([]) == 0.0

    def test_max_drawdown_single_value(self):
        """Single value should return 0."""
        assert max_drawdown([10000]) == 0.0

    def test_max_drawdown_monotonic_up(self):
        """Monotonically increasing equity should have 0 drawdown."""
        assert max_drawdown([100, 200, 300, 400]) == 0.0

    def test_max_drawdown_monotonic_down(self):
        """Monotonically decreasing equity should have high drawdown."""
        result = max_drawdown([400, 300, 200, 100])
        assert result == pytest.approx(0.75)  # (400-100)/400

    def test_max_drawdown_zero_peak(self):
        """Zero peak should not cause division by zero."""
        result = max_drawdown([0, -100, -200])
        assert result == 0.0  # Peak is 0, guard kicks in

    def test_max_drawdown_negative_equity(self):
        """Negative equity values (debt) should handle gracefully."""
        result = max_drawdown([-100, -200, -300])
        # Peak is -100, current -300
        # Drawdown = (-100 - (-300)) / -100 = 200 / -100 = -2.0
        # But this is negative, so max(0, -2) = 0 or actual logic differs
        assert result == 0.0 or result == pytest.approx(2.0)

    # ===================== WIN RATE EDGE CASES =====================

    def test_win_rate_empty_trades(self):
        """Empty trade list should return 0."""
        assert win_rate([]) == 0.0

    def test_win_rate_all_winners(self):
        """All winning trades should return 1.0."""
        now = datetime.now()
        trades = [
            Trade(now, now, 100, 110, "LONG", 10, 0.1, 0.5),
            Trade(now, now, 100, 110, "LONG", 20, 0.1, 0.5),
        ]
        assert win_rate(trades) == 1.0

    def test_win_rate_all_losers(self):
        """All losing trades should return 0.0."""
        now = datetime.now()
        trades = [
            Trade(now, now, 100, 90, "LONG", -10, -0.1, 0.5),
            Trade(now, now, 100, 90, "LONG", -20, -0.1, 0.5),
        ]
        assert win_rate(trades) == 0.0

    def test_win_rate_zero_pnl_trades(self):
        """Zero P&L trades should not count as wins."""
        now = datetime.now()
        trades = [
            Trade(now, now, 100, 100, "LONG", 0, 0.0, 0.5),
        ]
        assert win_rate(trades) == 0.0  # pnl > 0 required

    # ===================== PROFIT FACTOR EDGE CASES =====================

    def test_profit_factor_no_losses(self):
        """No losing trades should return inf."""
        now = datetime.now()
        trades = [
            Trade(now, now, 100, 110, "LONG", 10, 0.1, 0.5),
        ]
        assert profit_factor(trades) == float("inf")

    def test_profit_factor_no_wins(self):
        """No winning trades should return 0."""
        now = datetime.now()
        trades = [
            Trade(now, now, 100, 90, "LONG", -10, -0.1, 0.5),
        ]
        assert profit_factor(trades) == 0.0

    def test_profit_factor_breakeven(self):
        """Equal wins and losses should return 1.0."""
        now = datetime.now()
        trades = [
            Trade(now, now, 100, 110, "LONG", 10, 0.1, 0.5),
            Trade(now, now, 100, 90, "LONG", -10, -0.1, 0.5),
        ]
        assert profit_factor(trades) == 1.0

    # ===================== WEIGHT GRID EDGE CASES =====================

    def test_weight_grid_empty_signals(self):
        """No signals should return empty grid."""
        assert generate_weight_grid([]) == []

    def test_weight_grid_single_signal(self):
        """Single signal should get weight 1.0."""
        result = generate_weight_grid(["signal1"])
        assert len(result) == 1
        assert result[0]["signal1"] == 1.0

    def test_weight_grid_zero_step(self):
        """Zero step should return empty (avoid infinite loop)."""
        result = generate_weight_grid(["a", "b"], step=0.0)
        assert result == []

    def test_weight_grid_negative_step(self):
        """Negative step should return empty (invalid)."""
        result = generate_weight_grid(["a", "b"], step=-0.1)
        assert result == []

    def test_weight_grid_step_greater_than_one(self):
        """Step > 1 should work (produces minimal grid)."""
        result = generate_weight_grid(["a", "b"], step=1.5)
        # steps = int(1.0/1.5) + 1 = 0 + 1 = 1
        # Only weight value 0.0 -> combo (0.0,) -> remaining = 1.0
        assert len(result) >= 1

    def test_weight_grid_sum_to_one(self):
        """All weight combinations should sum to 1.0."""
        grid = generate_weight_grid(["a", "b", "c"], step=0.2)
        for weights in grid:
            total = sum(weights.values())
            assert total == pytest.approx(1.0, abs=0.001)

    # ===================== COMBINE SIGNALS EDGE CASES =====================

    def test_combine_signals_empty(self):
        """Empty signals should return empty list."""
        result = combine_signals({}, {"a": 0.5})
        assert result == []

    def test_combine_signals_mismatched_lengths(self):
        """Different length signals should handle gracefully."""
        signals = {
            "short": [0.1, 0.2],
            "long": [0.3, 0.4, 0.5, 0.6],
        }
        weights = {"short": 0.5, "long": 0.5}
        result = combine_signals(signals, weights)
        # Should use max length (4), shorter signal uses 0 after its length
        assert len(result) == 4
        # First two: 0.5*0.1 + 0.5*0.3 = 0.2, 0.5*0.2 + 0.5*0.4 = 0.3
        assert result[0] == pytest.approx(0.2)
        assert result[1] == pytest.approx(0.3)
        # Last two: 0.5*0 + 0.5*0.5 = 0.25, 0.5*0 + 0.5*0.6 = 0.3
        assert result[2] == pytest.approx(0.25)
        assert result[3] == pytest.approx(0.3)

    def test_combine_signals_missing_weight(self):
        """Signal without weight should use 0."""
        signals = {"a": [0.1, 0.2], "b": [0.3, 0.4]}
        weights = {"a": 1.0}  # b has no weight
        result = combine_signals(signals, weights)
        # a gets full weight, b gets 0
        assert result[0] == pytest.approx(0.1)
        assert result[1] == pytest.approx(0.2)

    # ===================== RUN BACKTEST EDGE CASES =====================

    def test_run_backtest_empty_prices(self):
        """Empty price list should return empty result."""
        config = BacktestConfig(
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=1),
            signal_source="test",
        )
        result = run_backtest(config, prices=[])
        assert result.num_trades == 0
        assert result.total_return == 0.0

    def test_run_backtest_single_price(self):
        """Single price point should work without trades."""
        config = BacktestConfig(
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=1),
            signal_source="test",
        )
        prices = [
            PricePoint(
                timestamp=datetime.now(),
                utxoracle_price=50000.0,
                exchange_price=50100.0,
                confidence=0.9,
                signal_value=0.5,
            )
        ]
        result = run_backtest(config, prices=prices)
        # With only one price point, no trade can complete
        assert result.num_trades == 0 or result.num_trades == 1

    def test_run_backtest_all_hold_signals(self):
        """All HOLD signals should produce no trades."""
        config = BacktestConfig(
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=1),
            signal_source="test",
            buy_threshold=0.9,  # Very high
            sell_threshold=-0.9,  # Very low
        )
        now = datetime.now()
        prices = [
            PricePoint(now, 50000.0, 50100.0, 0.9, 0.0),  # HOLD
            PricePoint(now + timedelta(hours=1), 51000.0, 51100.0, 0.9, 0.1),  # HOLD
            PricePoint(now + timedelta(hours=2), 52000.0, 52100.0, 0.9, -0.1),  # HOLD
        ]
        result = run_backtest(config, prices=prices)
        assert result.num_trades == 0


class TestCalculateReturnsEdgeCases:
    """Test calculate_returns edge cases."""

    def test_empty_equity(self):
        """Empty equity curve should return empty."""
        assert calculate_returns([]) == []

    def test_single_value(self):
        """Single value should return empty."""
        assert calculate_returns([100]) == []

    def test_zero_in_curve(self):
        """Zero in equity curve should return 0 for that period."""
        result = calculate_returns([100, 0, 50])
        # 100 -> 0: (0-100)/100 = -1.0
        # 0 -> 50: division by zero guard -> 0.0
        assert result[0] == pytest.approx(-1.0)
        assert result[1] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
