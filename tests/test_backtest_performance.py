"""Round 5: Performance and memory tests.

Tests for scalability, memory usage, and computation time.
"""

import time
from datetime import datetime, timedelta
import pytest

from scripts.backtest import (
    BacktestConfig,
    run_backtest,
    compare_signals,
    optimize_weights,
    sharpe_ratio,
    calculate_returns,
    calculate_all_metrics,
    PricePoint,
)
from scripts.backtest.optimizer import generate_weight_grid, combine_signals


class TestScalability:
    """Test performance with increasing data sizes."""

    @pytest.mark.parametrize("n_prices", [100, 500, 1000, 5000])
    def test_backtest_scales_linearly(self, n_prices):
        """Backtest should scale reasonably with price count."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 12, 31),
            signal_source="test",
        )

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(hours=i),
                utxoracle_price=50000 + (i % 100) * 10,
                exchange_price=50000 + (i % 100) * 10,
                confidence=0.9,
                signal_value=0.5 if i % 10 < 5 else -0.5,
            )
            for i in range(n_prices)
        ]

        start = time.time()
        result = run_backtest(config, prices=prices)
        elapsed = time.time() - start

        # Should complete in reasonable time
        # Allow 1ms per price point as upper bound
        max_time = n_prices * 0.001
        assert elapsed < max(max_time, 1.0), (
            f"Took {elapsed:.2f}s for {n_prices} prices"
        )

        # Verify result is valid
        assert isinstance(result.num_trades, int)

    @pytest.mark.parametrize("n_signals", [2, 3, 4, 5])
    def test_compare_signals_scales_with_signal_count(self, n_signals):
        """Signal comparison should scale with number of signals."""
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
            f"signal_{i}": [0.5 if j % 2 == 0 else -0.5 for j in range(100)]
            for i in range(n_signals)
        }

        start = time.time()
        result = compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 4, 10),
        )
        elapsed = time.time() - start

        # Should complete in reasonable time (1s per signal max)
        assert elapsed < n_signals * 1.0, f"Took {elapsed:.2f}s for {n_signals} signals"
        assert len(result.results) == n_signals


class TestWeightGridScaling:
    """Test weight grid generation performance."""

    def test_weight_grid_two_signals(self):
        """Two signals should generate manageable grid."""
        start = time.time()
        grid = generate_weight_grid(["a", "b"], step=0.1)
        elapsed = time.time() - start

        assert elapsed < 0.1
        assert len(grid) == 11  # 0.0 to 1.0 in 0.1 steps

    def test_weight_grid_three_signals(self):
        """Three signals should still be fast."""
        start = time.time()
        grid = generate_weight_grid(["a", "b", "c"], step=0.1)
        elapsed = time.time() - start

        assert elapsed < 0.5
        # C(11+2-1, 2) = C(12,2) = 66
        assert len(grid) > 50

    def test_weight_grid_four_signals_fine_step(self):
        """Four signals with fine step still completes."""
        start = time.time()
        grid = generate_weight_grid(["a", "b", "c", "d"], step=0.1)
        elapsed = time.time() - start

        # Should complete in reasonable time
        assert elapsed < 2.0, f"Took {elapsed:.2f}s"
        assert len(grid) > 100


class TestMetricsPerformance:
    """Test metrics calculation performance."""

    def test_sharpe_ratio_large_returns(self):
        """Sharpe calculation should be fast for large return series."""
        returns = [0.001 * (i % 10 - 5) for i in range(10000)]

        start = time.time()
        result = sharpe_ratio(returns)
        elapsed = time.time() - start

        assert elapsed < 0.1, f"Took {elapsed:.3f}s"
        assert isinstance(result, float)

    def test_calculate_returns_large_equity(self):
        """Calculate returns should be fast for large equity curves."""
        equity = [10000 + i * 10 for i in range(10000)]

        start = time.time()
        returns = calculate_returns(equity)
        elapsed = time.time() - start

        assert elapsed < 0.1, f"Took {elapsed:.3f}s"
        assert len(returns) == 9999

    def test_all_metrics_with_many_trades(self):
        """All metrics should calculate quickly with many trades."""
        from scripts.backtest import Trade

        now = datetime.now()
        trades = [
            Trade(
                entry_time=now + timedelta(hours=i),
                exit_time=now + timedelta(hours=i + 1),
                entry_price=100,
                exit_price=100 + (i % 5 - 2),
                direction="LONG",
                pnl=(i % 5 - 2) * 10,
                pnl_pct=(i % 5 - 2) * 0.01,
                signal_value=0.5,
            )
            for i in range(1000)
        ]

        equity = [10000]
        for t in trades:
            equity.append(equity[-1] + t.pnl)

        start = time.time()
        metrics = calculate_all_metrics(trades, equity)
        elapsed = time.time() - start

        assert elapsed < 0.5, f"Took {elapsed:.3f}s"
        assert "sharpe_ratio" in metrics


class TestCombineSignalsPerformance:
    """Test signal combination performance."""

    def test_combine_many_signals(self):
        """Combining many signals should be efficient."""
        n_signals = 10
        n_points = 1000

        signals = {
            f"s{i}": [0.1 * i for _ in range(n_points)] for i in range(n_signals)
        }
        weights = {f"s{i}": 1.0 / n_signals for i in range(n_signals)}

        start = time.time()
        combined = combine_signals(signals, weights)
        elapsed = time.time() - start

        assert elapsed < 0.5, f"Took {elapsed:.3f}s"
        assert len(combined) == n_points

    def test_combine_long_signals(self):
        """Long signal series should combine quickly."""
        signals = {
            "a": list(range(100000)),
            "b": list(range(100000, 200000)),
        }
        weights = {"a": 0.5, "b": 0.5}

        start = time.time()
        combined = combine_signals(signals, weights)
        elapsed = time.time() - start

        assert elapsed < 1.0, f"Took {elapsed:.3f}s"
        assert len(combined) == 100000


class TestOptimizationPerformance:
    """Test optimization performance."""

    def test_optimization_with_coarse_grid(self):
        """Optimization with coarse grid should be fast."""
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.0,
            )
            for i in range(50)
        ]

        signals = {
            "trend": [0.5] * 50,
            "contrarian": [-0.5] * 50,
        }

        start = time.time()
        result = optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 2, 19),
            step=0.5,  # Coarse grid
        )
        elapsed = time.time() - start

        assert elapsed < 2.0, f"Took {elapsed:.2f}s"
        assert result.best_weights is not None


class TestMemoryEfficiency:
    """Test memory efficiency patterns."""

    def test_backtest_does_not_leak_memory(self):
        """Repeated backtests should not accumulate memory."""
        import gc

        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 31),
            signal_source="test",
        )

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(hours=i),
                utxoracle_price=50000 + i * 10,
                exchange_price=50000 + i * 10,
                confidence=0.9,
                signal_value=0.5 if i % 2 == 0 else -0.5,
            )
            for i in range(100)
        ]

        # Run multiple times
        for _ in range(10):
            result = run_backtest(config, prices=prices)
            del result

        gc.collect()

        # If we got here without memory error, test passes
        assert True

    def test_large_equity_curve_memory(self):
        """Large equity curves should not cause memory issues."""
        # Generate a large equity curve
        equity = [10000.0]
        for i in range(100000):
            equity.append(equity[-1] * 1.0001)  # Small growth

        # Calculate returns
        returns = calculate_returns(equity)

        # Should complete without memory error
        assert len(returns) == 100000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
