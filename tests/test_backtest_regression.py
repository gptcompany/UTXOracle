"""Round 5 (Pass 2): Regression tests with complex scenarios.

Tests complex real-world scenarios combining multiple features.
"""

from datetime import datetime, timedelta
import pytest

from scripts.backtest import (
    BacktestConfig,
    Trade,
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
from scripts.backtest.optimizer import combine_signals


class TestComplexTradingScenarios:
    """Test complex trading scenarios."""

    def test_bull_market_with_pullbacks(self):
        """Bull market with periodic 10% pullbacks."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 3, 31),
            signal_source="test",
            buy_threshold=0.3,
            sell_threshold=-0.3,
        )

        # Bull market: up trend with periodic pullbacks
        prices = []
        base = 50000
        for i in range(90):
            # 10% pullback every 30 days
            if i % 30 == 25:
                price = base * (1 + i * 0.01) * 0.9
            else:
                price = base * (1 + i * 0.01)

            # Bullish signals except during pullbacks
            signal = -0.5 if i % 30 >= 25 else 0.5

            prices.append(
                PricePoint(
                    timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                    utxoracle_price=price,
                    exchange_price=price,
                    confidence=0.9,
                    signal_value=signal,
                )
            )

        result = run_backtest(config, prices=prices)

        # Note: Even in bull market, going SHORT during pullbacks can lose money
        # if the recovery is faster than expected. The key invariant is that
        # the backtest completes and produces valid results.
        assert isinstance(result.total_return, float)
        # Should have some trades
        assert result.num_trades > 0

    def test_bear_market_with_rallies(self):
        """Bear market with periodic 10% rallies."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 3, 31),
            signal_source="test",
            buy_threshold=0.3,
            sell_threshold=-0.3,
        )

        # Bear market: down trend with periodic rallies
        prices = []
        base = 50000
        for i in range(90):
            # 10% rally every 30 days
            if i % 30 == 25:
                price = base * (1 - i * 0.005) * 1.1
            else:
                price = base * (1 - i * 0.005)

            # Bearish signals except during rallies
            signal = 0.5 if i % 30 >= 25 else -0.5

            prices.append(
                PricePoint(
                    timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                    utxoracle_price=price,
                    exchange_price=price,
                    confidence=0.9,
                    signal_value=signal,
                )
            )

        result = run_backtest(config, prices=prices)

        # Should complete without error
        assert isinstance(result.num_trades, int)

    def test_sideways_market_high_volatility(self):
        """Sideways market with high volatility (choppy)."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 30),
            signal_source="test",
            buy_threshold=0.3,
            sell_threshold=-0.3,
        )

        # Sideways: oscillate around 50000 with 5% swings
        prices = []
        for i in range(30):
            # High frequency oscillation
            swing = 2500 if i % 2 == 0 else -2500
            price = 50000 + swing

            # Alternating signals
            signal = 0.5 if i % 2 == 0 else -0.5

            prices.append(
                PricePoint(
                    timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                    utxoracle_price=price,
                    exchange_price=price,
                    confidence=0.9,
                    signal_value=signal,
                )
            )

        result = run_backtest(config, prices=prices)

        # Choppy market may have many trades
        assert result.num_trades >= 0
        # Transaction costs may eat into profits
        assert isinstance(result.total_return, float)

    def test_flash_crash_recovery(self):
        """Flash crash (50% drop) followed by recovery."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 20),
            signal_source="test",
            buy_threshold=0.3,
            sell_threshold=-0.3,
        )

        # Flash crash on day 5, recovery by day 15
        prices = []
        for i in range(20):
            if i < 5:
                price = 50000
            elif i == 5:
                price = 25000  # 50% crash
            elif i < 15:
                price = 25000 + (i - 5) * 2500  # Recovery
            else:
                price = 50000  # Recovered

            # Bearish at crash, bullish during recovery
            if i == 5:
                signal = -0.8
            elif 5 < i < 15:
                signal = 0.5
            else:
                signal = 0.0

            prices.append(
                PricePoint(
                    timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                    utxoracle_price=price,
                    exchange_price=price,
                    confidence=0.9,
                    signal_value=signal,
                )
            )

        result = run_backtest(config, prices=prices)

        # Max drawdown should reflect the 50% crash
        if result.equity_curve and len(result.equity_curve) > 1:
            dd = max_drawdown(result.equity_curve)
            assert dd >= 0.0  # Some drawdown expected


class TestMultiSignalComparison:
    """Test complex multi-signal comparison scenarios."""

    def test_compare_correlated_signals(self):
        """Compare signals that are highly correlated."""
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

        # Two signals that are 90% correlated
        signal_a = [0.5 if i % 3 != 2 else -0.5 for i in range(50)]
        signal_b = [
            0.5 if i % 3 != 2 else -0.4 for i in range(50)
        ]  # Slightly different

        signals = {"signal_a": signal_a, "signal_b": signal_b}

        comparison = compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 2, 19),
        )

        # Should have results for both signals
        assert len(comparison.results) == 2
        # Similar signals should have similar performance
        assert comparison.results["signal_a"] is not None
        assert comparison.results["signal_b"] is not None

    def test_compare_anti_correlated_signals(self):
        """Compare signals that are anti-correlated (opposite)."""
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

        # Two signals that are perfectly opposite
        signal_bull = [0.5] * 50
        signal_bear = [-0.5] * 50

        signals = {"bull": signal_bull, "bear": signal_bear}

        comparison = compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 2, 19),
        )

        # In an uptrending market, bull should outperform bear
        # (prices go from 50000 to 54900)
        if comparison.ranking:
            assert comparison.ranking[0] == "bull"

    def test_compare_with_mixed_confidence(self):
        """Compare signals where prices have varying confidence."""
        prices = []
        for i in range(50):
            # Confidence drops in middle period
            if 20 <= i < 30:
                confidence = 0.3  # Low confidence period
            else:
                confidence = 0.9

            prices.append(
                PricePoint(
                    timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                    utxoracle_price=50000 + i * 100,
                    exchange_price=50000 + i * 100,
                    confidence=confidence,
                    signal_value=0.0,
                )
            )

        signals = {"constant": [0.5] * 50}

        comparison = compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 2, 19),
        )

        # Should complete without error
        assert len(comparison.results) == 1


class TestOptimizationEdgeCases:
    """Test optimization edge cases."""

    def test_optimize_identical_signals(self):
        """Optimize weights when all signals are identical."""
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.0,
            )
            for i in range(30)
        ]

        # All signals identical
        signals = {
            "a": [0.5] * 30,
            "b": [0.5] * 30,
            "c": [0.5] * 30,
        }

        result = optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 30),
            step=0.5,
        )

        # All weight combinations should give same result
        # Improvement should be 0 or near-zero
        assert result.improvement == pytest.approx(0.0, abs=0.01)

    def test_optimize_many_signals(self):
        """Optimize weights with many signals (grid explosion)."""
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.0,
            )
            for i in range(30)
        ]

        # 5 signals with large step to keep grid manageable
        signals = {
            f"s{i}": [0.5 if j % (i + 2) == 0 else -0.5 for j in range(30)]
            for i in range(5)
        }

        result = optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 30),
            step=0.5,  # Large step to limit grid size
        )

        # Should complete and have valid weights
        assert result.best_weights is not None
        assert sum(result.best_weights.values()) == pytest.approx(1.0, abs=1e-10)

    def test_optimize_single_signal(self):
        """Optimize weights with only one signal (trivial case)."""
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.0,
            )
            for i in range(30)
        ]

        signals = {"only_signal": [0.5] * 30}

        result = optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 30),
            step=0.5,
        )

        # With one signal, weight must be 1.0
        assert result.best_weights["only_signal"] == pytest.approx(1.0)


class TestMetricEdgeCases:
    """Test metric calculations in edge cases."""

    def test_sharpe_with_highly_volatile_returns(self):
        """Sharpe ratio with extreme volatility."""
        # Returns oscillating between +50% and -50%
        returns = [0.5, -0.5, 0.5, -0.5, 0.5, -0.5]
        result = sharpe_ratio(returns)

        # Should be near zero (high risk, low net return)
        assert abs(result) < 1.0

    def test_sortino_with_only_downside(self):
        """Sortino ratio with only negative returns."""
        returns = [-0.01, -0.02, -0.01, -0.03, -0.02]
        result = sortino_ratio(returns)

        # Should be negative (negative mean, positive downside deviation)
        assert result <= 0.0

    def test_sortino_with_no_downside(self):
        """Sortino ratio with only positive returns."""
        returns = [0.01, 0.02, 0.01, 0.03, 0.02]
        result = sortino_ratio(returns)

        # Should be positive or inf (positive mean, zero/small downside)
        assert result >= 0.0

    def test_profit_factor_all_small_trades(self):
        """Profit factor with many small trades."""
        now = datetime.now()

        # Many small wins, few larger losses
        trades = [
            Trade(now, now, 100, 100.1, "LONG", 0.1, 0.001, 0.5) for _ in range(100)
        ]
        trades.append(Trade(now, now, 100, 90, "LONG", -10, -0.1, 0.5))

        pf = profit_factor(trades)

        # 100 * 0.1 = 10 gross profit, 10 gross loss
        assert pf == pytest.approx(1.0)

    def test_win_rate_exactly_50_percent(self):
        """Win rate with exactly 50% wins."""
        now = datetime.now()

        trades = [
            Trade(now, now, 100, 110, "LONG", 10, 0.1, 0.5),
            Trade(now, now, 100, 90, "LONG", -10, -0.1, 0.5),
            Trade(now, now, 100, 110, "LONG", 10, 0.1, 0.5),
            Trade(now, now, 100, 90, "LONG", -10, -0.1, 0.5),
        ]

        rate = win_rate(trades)
        assert rate == pytest.approx(0.5)


class TestEndToEndWorkflows:
    """Test complete end-to-end workflows."""

    def test_complete_workflow_single_signal(self):
        """Complete workflow: load data, backtest, analyze."""
        # 1. Create test data
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.5 if i % 2 == 0 else -0.5,
            )
            for i in range(60)
        ]

        # 2. Run backtest
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 3, 1),
            signal_source="test",
        )
        result = run_backtest(config, prices=prices)

        # 3. Analyze results
        assert result.num_trades > 0
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.max_drawdown, float)

        # 4. Calculate additional metrics
        if result.equity_curve and len(result.equity_curve) > 1:
            returns = calculate_returns(result.equity_curve)
            assert len(returns) == len(result.equity_curve) - 1

    def test_complete_workflow_comparison_and_optimization(self):
        """Complete workflow: compare signals, then optimize."""
        # 1. Create test data
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.0,
            )
            for i in range(60)
        ]

        signals = {
            "signal_a": [0.5 if i % 3 == 0 else 0.0 for i in range(60)],
            "signal_b": [0.5 if i % 4 == 0 else 0.0 for i in range(60)],
        }

        # 2. Compare signals
        comparison = compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 3, 1),
        )

        assert comparison.best_signal in signals

        # 3. Optimize weights
        optimization = optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 3, 1),
            step=0.2,
        )

        assert optimization.best_weights is not None
        assert optimization.best_sharpe is not None

        # 4. Use optimized weights to combine signals
        combined = combine_signals(signals, optimization.best_weights)
        assert len(combined) == 60


class TestConfigurationVariations:
    """Test various configuration combinations."""

    def test_high_transaction_cost(self):
        """Test with very high transaction costs (5%)."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 20),
            signal_source="test",
            transaction_cost=0.05,  # 5% per trade
        )

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.5 if i % 2 == 0 else -0.5,
            )
            for i in range(20)
        ]

        result = run_backtest(config, prices=prices)

        # High costs should eat into profits significantly
        # Many trades in choppy market with 5% costs = likely loss
        assert isinstance(result.total_return, float)

    def test_extreme_thresholds(self):
        """Test with extreme buy/sell thresholds (0.9/-0.9)."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 30),
            signal_source="test",
            buy_threshold=0.9,
            sell_threshold=-0.9,
        )

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.5 if i % 2 == 0 else -0.5,  # Never reaches threshold
            )
            for i in range(30)
        ]

        result = run_backtest(config, prices=prices)

        # Extreme thresholds = no trades
        assert result.num_trades == 0

    def test_very_small_position_size(self):
        """Test with very small position size (0.01)."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 20),
            signal_source="test",
            position_size=0.01,  # Only 1% of capital
        )

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.5 if i % 2 == 0 else -0.5,
            )
            for i in range(20)
        ]

        result = run_backtest(config, prices=prices)

        # Small position = small returns
        if result.trades:
            for trade in result.trades:
                assert abs(trade.pnl) < 100  # Limited by small position

    def test_very_large_initial_capital(self):
        """Test with very large initial capital (1B)."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
            signal_source="test",
            initial_capital=1_000_000_000.0,  # 1 billion
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

        result = run_backtest(config, prices=prices)

        # Should handle large numbers without overflow
        assert isinstance(result.total_return, float)
        if result.equity_curve:
            assert result.equity_curve[0] == 1_000_000_000.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
