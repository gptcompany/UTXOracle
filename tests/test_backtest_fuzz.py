"""Round 6 (Pass 2): Fuzz testing with random inputs.

Uses property-based testing with random data to find edge cases.
"""

import math
import random
from datetime import datetime, timedelta
import pytest

from scripts.backtest import (
    BacktestConfig,
    Trade,
    run_backtest,
    compare_signals,
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    win_rate,
    profit_factor,
    calculate_returns,
    PricePoint,
)
from scripts.backtest.optimizer import generate_weight_grid, combine_signals
from scripts.backtest.engine import get_signal_action, execute_trade


# Seed for reproducibility
random.seed(42)


class TestRandomizedInputs:
    """Test with randomized inputs."""

    @pytest.mark.parametrize("iteration", range(20))
    def test_random_returns_sharpe(self, iteration):
        """Sharpe ratio should handle any random returns."""
        n = random.randint(5, 100)
        returns = [random.uniform(-0.5, 0.5) for _ in range(n)]

        result = sharpe_ratio(returns)

        # Should always return a float (possibly NaN or Inf)
        assert isinstance(result, float)
        # If finite, should be reasonable range
        if math.isfinite(result):
            assert -100 < result < 100

    @pytest.mark.parametrize("iteration", range(20))
    def test_random_returns_sortino(self, iteration):
        """Sortino ratio should handle any random returns."""
        n = random.randint(5, 100)
        returns = [random.uniform(-0.5, 0.5) for _ in range(n)]

        result = sortino_ratio(returns)

        assert isinstance(result, float)
        if math.isfinite(result):
            assert -100 < result < 100

    @pytest.mark.parametrize("iteration", range(20))
    def test_random_equity_max_drawdown(self, iteration):
        """Max drawdown should handle any random equity curve."""
        n = random.randint(5, 100)
        # Random walk equity curve
        equity = [10000.0]
        for _ in range(n - 1):
            change = random.uniform(-0.1, 0.12)  # Slight upward bias
            equity.append(equity[-1] * (1 + change))

        result = max_drawdown(equity)

        assert isinstance(result, float)
        # Drawdown is between 0 and 1 (0% to 100%)
        if math.isfinite(result):
            assert 0.0 <= result <= 1.0

    @pytest.mark.parametrize("iteration", range(20))
    def test_random_equity_returns(self, iteration):
        """calculate_returns should handle any random equity curve."""
        n = random.randint(2, 50)
        equity = [random.uniform(100, 10000) for _ in range(n)]

        returns = calculate_returns(equity)

        assert len(returns) == n - 1
        for r in returns:
            assert isinstance(r, float)


class TestRandomizedTrades:
    """Test with randomized trade data."""

    @pytest.mark.parametrize("iteration", range(20))
    def test_random_trades_win_rate(self, iteration):
        """Win rate should handle random trades."""
        now = datetime.now()
        n = random.randint(1, 50)

        trades = []
        for _ in range(n):
            pnl = random.uniform(-1000, 1000)
            trades.append(
                Trade(
                    entry_time=now,
                    exit_time=now + timedelta(hours=1),
                    entry_price=random.uniform(10000, 100000),
                    exit_price=random.uniform(10000, 100000),
                    direction=random.choice(["LONG", "SHORT"]),
                    pnl=pnl,
                    pnl_pct=pnl / 10000,
                    signal_value=random.uniform(-1, 1),
                )
            )

        rate = win_rate(trades)

        assert 0.0 <= rate <= 1.0

    @pytest.mark.parametrize("iteration", range(20))
    def test_random_trades_profit_factor(self, iteration):
        """Profit factor should handle random trades."""
        now = datetime.now()
        n = random.randint(1, 50)

        trades = []
        for _ in range(n):
            pnl = random.uniform(-1000, 1000)
            trades.append(
                Trade(
                    entry_time=now,
                    exit_time=now + timedelta(hours=1),
                    entry_price=random.uniform(10000, 100000),
                    exit_price=random.uniform(10000, 100000),
                    direction=random.choice(["LONG", "SHORT"]),
                    pnl=pnl,
                    pnl_pct=pnl / 10000,
                    signal_value=random.uniform(-1, 1),
                )
            )

        pf = profit_factor(trades)

        assert isinstance(pf, float)
        assert pf >= 0.0


class TestRandomizedBacktest:
    """Test backtest with randomized inputs."""

    @pytest.mark.parametrize("iteration", range(10))
    def test_random_prices_backtest(self, iteration):
        """Backtest should handle random price data."""
        n = random.randint(10, 50)
        base_price = random.uniform(10000, 100000)

        prices = []
        for i in range(n):
            # Random walk price
            price = base_price * (1 + random.uniform(-0.02, 0.02) * i)
            prices.append(
                PricePoint(
                    timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                    utxoracle_price=price,
                    exchange_price=price,
                    confidence=random.uniform(0.5, 1.0),
                    signal_value=random.uniform(-1, 1),
                )
            )

        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 1) + timedelta(days=n),
            signal_source="test",
            buy_threshold=random.uniform(0.1, 0.5),
            sell_threshold=random.uniform(-0.5, -0.1),
            position_size=random.uniform(0.1, 1.0),
            transaction_cost=random.uniform(0.0, 0.01),
            initial_capital=random.uniform(1000, 100000),
        )

        result = run_backtest(config, prices=prices)

        # Should always return valid result
        assert isinstance(result.num_trades, int)
        assert isinstance(result.total_return, float)
        assert isinstance(result.sharpe_ratio, float)

    @pytest.mark.parametrize("iteration", range(10))
    def test_random_signals_comparison(self, iteration):
        """Compare signals should handle random signal data."""
        n = random.randint(20, 50)

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + random.uniform(-1000, 1000),
                exchange_price=50000 + random.uniform(-1000, 1000),
                confidence=0.9,
                signal_value=0.0,
            )
            for i in range(n)
        ]

        num_signals = random.randint(2, 5)
        signals = {
            f"signal_{i}": [random.uniform(-1, 1) for _ in range(n)]
            for i in range(num_signals)
        }

        comparison = compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 1) + timedelta(days=n),
        )

        assert len(comparison.results) == num_signals
        assert comparison.best_signal in signals


class TestRandomizedWeights:
    """Test weight operations with random data."""

    @pytest.mark.parametrize("iteration", range(20))
    def test_random_weights_combine(self, iteration):
        """Combine signals should work with any random weights."""
        n_signals = random.randint(2, 5)
        length = random.randint(5, 30)

        signals = {
            f"s{i}": [random.uniform(-1, 1) for _ in range(length)]
            for i in range(n_signals)
        }

        # Random weights that sum to 1
        raw_weights = [random.random() for _ in range(n_signals)]
        total = sum(raw_weights)
        weights = {f"s{i}": w / total for i, w in enumerate(raw_weights)}

        combined = combine_signals(signals, weights)

        assert len(combined) == length
        for c in combined:
            assert isinstance(c, float)
            # Combined should be within signal range
            assert -1.0 <= c <= 1.0 or math.isclose(abs(c), 1.0, abs_tol=0.01)

    @pytest.mark.parametrize("n_signals", [2, 3, 4])
    def test_weight_grid_coverage(self, n_signals):
        """Weight grid should cover all valid combinations."""
        signals = [f"s{i}" for i in range(n_signals)]
        grid = generate_weight_grid(signals, step=0.5)

        # All weights should sum to 1
        for weights in grid:
            total = sum(weights.values())
            assert total == pytest.approx(1.0, abs=1e-10)

        # Should have enough combinations
        # With step=0.5: 3 values (0, 0.5, 1) per signal
        # But constrained to sum=1
        assert len(grid) >= n_signals  # At least pure weights


class TestRandomizedSignalActions:
    """Test signal action determination with random inputs."""

    @pytest.mark.parametrize("iteration", range(50))
    def test_random_signal_action(self, iteration):
        """get_signal_action should handle any signal values."""
        signal = random.uniform(-2, 2)
        buy_threshold = random.uniform(-0.5, 0.5)
        sell_threshold = random.uniform(-0.5, 0.5)

        action = get_signal_action(signal, buy_threshold, sell_threshold)

        # Should always return valid action
        assert action in ("BUY", "SELL", "HOLD")


class TestRandomizedTradeExecution:
    """Test trade execution with random inputs."""

    @pytest.mark.parametrize("iteration", range(30))
    def test_random_trade_execution(self, iteration):
        """execute_trade should handle random inputs."""
        now = datetime.now()

        entry_price = random.uniform(100, 100000)
        exit_price = random.uniform(100, 100000)
        direction = random.choice(["LONG", "SHORT"])
        position_size = random.uniform(0.1, 2.0)
        transaction_cost = random.uniform(0, 0.01)
        capital = random.uniform(1000, 1000000)
        signal_value = random.uniform(-1, 1)

        trade = execute_trade(
            entry_time=now,
            entry_price=entry_price,
            exit_time=now + timedelta(hours=random.randint(1, 100)),
            exit_price=exit_price,
            direction=direction,
            position_size=position_size,
            transaction_cost=transaction_cost,
            capital=capital,
            signal_value=signal_value,
        )

        assert isinstance(trade.pnl, float)
        assert isinstance(trade.pnl_pct, float)
        assert trade.direction in ("LONG", "SHORT")


class TestEdgeCaseFuzzing:
    """Fuzz test known edge cases."""

    @pytest.mark.parametrize("iteration", range(20))
    def test_near_zero_prices(self, iteration):
        """Test with prices near zero."""
        now = datetime.now()
        small_price = random.uniform(0.001, 1.0)

        trade = execute_trade(
            entry_time=now,
            entry_price=small_price,
            exit_time=now + timedelta(hours=1),
            exit_price=small_price * random.uniform(0.9, 1.1),
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.001,
            capital=1000.0,
            signal_value=0.5,
        )

        assert isinstance(trade.pnl, float)

    @pytest.mark.parametrize("iteration", range(20))
    def test_very_large_prices(self, iteration):
        """Test with very large prices."""
        now = datetime.now()
        large_price = random.uniform(1e10, 1e15)

        trade = execute_trade(
            entry_time=now,
            entry_price=large_price,
            exit_time=now + timedelta(hours=1),
            exit_price=large_price * random.uniform(0.99, 1.01),
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.001,
            capital=1000.0,
            signal_value=0.5,
        )

        assert isinstance(trade.pnl, float)

    @pytest.mark.parametrize("iteration", range(20))
    def test_oscillating_signals(self, iteration):
        """Test rapidly oscillating signals."""
        n = random.randint(20, 50)

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(hours=i),
                utxoracle_price=50000 + random.uniform(-100, 100),
                exchange_price=50000 + random.uniform(-100, 100),
                confidence=0.9,
                # Rapidly oscillating signal
                signal_value=1.0 if i % 2 == 0 else -1.0,
            )
            for i in range(n)
        ]

        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 1) + timedelta(hours=n),
            signal_source="test",
            buy_threshold=0.5,
            sell_threshold=-0.5,
        )

        result = run_backtest(config, prices=prices)

        # Should handle rapid oscillation without error
        assert isinstance(result.num_trades, int)


class TestDeterminism:
    """Verify deterministic behavior with same seed."""

    def test_same_seed_same_results(self):
        """Same random seed should produce same results."""
        results = []

        for _ in range(3):
            random.seed(12345)

            prices = [
                PricePoint(
                    timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                    utxoracle_price=50000 + random.uniform(-1000, 1000),
                    exchange_price=50000 + random.uniform(-1000, 1000),
                    confidence=0.9,
                    signal_value=random.uniform(-1, 1),
                )
                for i in range(30)
            ]

            config = BacktestConfig(
                start_date=datetime(2025, 1, 1),
                end_date=datetime(2025, 1, 30),
                signal_source="test",
            )

            result = run_backtest(config, prices=prices)
            results.append(result.total_return)

        # All runs should produce identical results
        assert results[0] == results[1] == results[2]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
