"""Integration test for backtesting pipeline.

Tests the full backtest workflow from data loading to result analysis.
"""

from datetime import datetime, timedelta


class TestBacktestPipeline:
    """End-to-end pipeline tests."""

    def test_full_backtest_pipeline(self):
        """Test complete backtest workflow."""
        from scripts.backtest import (
            BacktestConfig,
            run_backtest,
            calculate_all_metrics,
            PricePoint,
        )

        # Create synthetic data
        prices = []
        base = 50000.0
        for i in range(60):
            # Oscillating price with trend
            price = base + i * 50 + 500 * (i % 5)
            signal = 0.4 if i % 5 < 3 else -0.4
            prices.append(
                PricePoint(
                    timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                    utxoracle_price=price,
                    exchange_price=price,
                    confidence=0.9,
                    signal_value=signal,
                )
            )

        # Run backtest
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 3, 1),
            signal_source="test",
            initial_capital=10000.0,
        )

        result = run_backtest(config, prices=prices)

        # Verify result structure
        assert result.config == config
        assert isinstance(result.trades, list)
        assert isinstance(result.equity_curve, list)
        assert len(result.equity_curve) > 0

        # Calculate metrics
        if result.trades:
            metrics = calculate_all_metrics(result.trades, result.equity_curve)
            assert "sharpe_ratio" in metrics
            assert "win_rate" in metrics
            assert "max_drawdown" in metrics

    def test_compare_and_optimize_pipeline(self):
        """Test signal comparison and optimization workflow."""
        from scripts.backtest import (
            compare_signals,
            optimize_weights,
            PricePoint,
        )

        # Create price data
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

        # Define signals
        signals = {
            "trend": [0.5] * 50,  # Always bullish
            "contrarian": [-0.5] * 50,  # Always bearish
        }

        # Compare signals
        comparison = compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 2, 19),
        )

        assert len(comparison.results) == 2
        assert comparison.best_signal in ["trend", "contrarian"]

        # Optimize weights
        optimization = optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 2, 19),
            step=0.5,
        )

        assert optimization.best_weights is not None
        assert abs(sum(optimization.best_weights.values()) - 1.0) < 0.01

    def test_public_api_imports(self):
        """Test that public API can be imported from __init__."""
        from scripts.backtest import (
            # Engine
            run_backtest,
            compare_signals,
            # Metrics
            sharpe_ratio,
            optimize_weights,
        )

        # All imports should be callable or classes
        assert callable(run_backtest)
        assert callable(compare_signals)
        assert callable(sharpe_ratio)
        assert callable(optimize_weights)
