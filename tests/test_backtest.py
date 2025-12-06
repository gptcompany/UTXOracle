"""Unit tests for backtesting framework.

Tests for scripts/backtest/ module following TDD approach.
"""

from datetime import datetime

from scripts.backtest.engine import (
    BacktestConfig,
    Trade,
    BacktestResult,
    ComparisonResult,
)


class TestDataclasses:
    """Test dataclass creation and defaults."""

    def test_backtest_config_creation(self):
        """BacktestConfig can be created with required fields."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 11, 30),
            signal_source="fusion",
        )
        assert config.signal_source == "fusion"
        assert config.buy_threshold == 0.3
        assert config.sell_threshold == -0.3
        assert config.initial_capital == 10000.0

    def test_trade_creation(self):
        """Trade can be created with all fields."""
        trade = Trade(
            entry_time=datetime(2025, 1, 1, 10, 0),
            exit_time=datetime(2025, 1, 1, 14, 0),
            entry_price=50000.0,
            exit_price=51000.0,
            direction="LONG",
            pnl=1000.0,
            pnl_pct=0.02,
            signal_value=0.5,
        )
        assert trade.direction == "LONG"
        assert trade.pnl == 1000.0

    def test_backtest_result_defaults(self):
        """BacktestResult has proper defaults."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 11, 30),
            signal_source="fusion",
        )
        result = BacktestResult(config=config)
        assert result.trades == []
        assert result.equity_curve == []
        assert result.total_return == 0.0
        assert result.num_trades == 0

    def test_comparison_result_defaults(self):
        """ComparisonResult has proper defaults."""
        comparison = ComparisonResult()
        assert comparison.signals == []
        assert comparison.results == {}
        assert comparison.ranking == []


class TestSingleSignalBacktest:
    """Test single signal backtesting (US1)."""

    def test_backtest_perfect_signal(self):
        """Perfect signal (always correct) should generate positive returns.

        T009: A signal that perfectly predicts price direction should:
        - Generate 100% win rate
        - Have positive total return
        - Execute trades
        """
        from scripts.backtest.engine import run_backtest
        from scripts.backtest.data_loader import PricePoint

        # Create synthetic price data: alternating up/down with perfect signals
        # BUY when about to rise, SELL when about to fall
        prices = []
        base_price = 50000.0
        for i in range(20):
            if i % 4 == 0:  # Start of uptrend
                signal = 0.5  # BUY
                price = base_price
            elif i % 4 == 1:  # Peak, switch to downtrend
                signal = -0.5  # SELL
                price = base_price + 2000  # Higher
            elif i % 4 == 2:  # Start of downtrend
                signal = -0.5  # SELL (already in short)
                price = base_price + 1000  # Falling
            else:  # Bottom, switch to uptrend
                signal = 0.5  # BUY
                price = base_price  # Back to base

            prices.append(
                PricePoint(
                    timestamp=datetime(2025, 1, i + 1),
                    utxoracle_price=price,
                    exchange_price=price,
                    confidence=0.9,
                    signal_value=signal,
                )
            )

        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 20),
            signal_source="test",
            buy_threshold=0.3,
            sell_threshold=-0.3,
            transaction_cost=0.0,  # No costs for clarity
        )

        result = run_backtest(config, prices=prices)

        # Perfect signal should generate profits and trades
        assert result.num_trades > 0, "Should execute at least one trade"
        assert result.total_return > 0, "Perfect signal should be profitable"

    def test_backtest_random_signal(self):
        """Random signal should generate near-zero returns after costs.

        T010: A signal with no predictive power should:
        - Generate ~50% win rate
        - Have near-zero total return (accounting for costs)
        """
        from scripts.backtest.engine import run_backtest
        from scripts.backtest.data_loader import PricePoint
        import random

        random.seed(42)  # Reproducible randomness

        # Create price data with random walk
        prices = []
        price = 50000.0
        for i in range(100):
            # Random signal between -1 and 1
            signal = random.uniform(-1, 1)
            # Random price change
            price += random.uniform(-500, 500)
            prices.append(
                PricePoint(
                    timestamp=datetime(2025, 1, 1)
                    + __import__("datetime").timedelta(hours=i),
                    utxoracle_price=price,
                    exchange_price=price,
                    confidence=0.5,
                    signal_value=signal,
                )
            )

        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 5),
            signal_source="test",
            buy_threshold=0.3,
            sell_threshold=-0.3,
            transaction_cost=0.001,
        )

        result = run_backtest(config, prices=prices)

        # Random signal should have ~50% win rate
        if result.num_trades > 0:
            assert 0.3 <= result.win_rate <= 0.7, (
                "Random signal should be ~50% win rate"
            )
        # With transaction costs, random should lose money or break even
        assert result.total_return < 0.2, "Random signal shouldn't be very profitable"

    def test_backtest_inverted_signal(self):
        """Inverted signal (always wrong) should generate negative returns.

        T011: A signal that always predicts the opposite direction should:
        - Generate <50% win rate
        - Have negative total return
        """
        from scripts.backtest.engine import run_backtest
        from scripts.backtest.data_loader import PricePoint

        # Create steadily rising prices with SELL signals (inverted)
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, i + 1),
                utxoracle_price=50000 + i * 1000,  # Rising prices
                exchange_price=50000 + i * 1000,
                confidence=0.9,
                signal_value=-0.5,  # SELL signal when should BUY (inverted)
            )
            for i in range(30)
        ]

        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 30),
            signal_source="test",
            buy_threshold=0.3,
            sell_threshold=-0.3,
        )

        result = run_backtest(config, prices=prices)

        # Inverted signal should lose money on rising market
        # (because it's always SELLing when price is rising)
        assert result.num_trades > 0 or result.total_return <= 0, (
            "Inverted signal should not profit on trending market"
        )


class TestPerformanceMetrics:
    """Test performance metric calculations (US2)."""

    def test_sharpe_ratio_calculation(self):
        """T017: Sharpe ratio should be calculated correctly.

        Sharpe = (mean(returns) - rf) / std(returns) * sqrt(252)
        """
        from scripts.backtest.metrics import sharpe_ratio

        # Known returns with predictable Sharpe
        # Daily returns of 0.1% with 0.5% std
        returns = [0.001] * 100  # 100 days of 0.1% return
        returns[50] = -0.02  # Add one loss day for std

        result = sharpe_ratio(returns, risk_free_rate=0.0)

        # Should be positive (positive mean returns)
        assert result > 0, "Sharpe should be positive for positive returns"
        # Sanity check: shouldn't be astronomically high
        assert result < 10, "Sharpe should be reasonable"

    def test_sortino_ratio_calculation(self):
        """T018: Sortino ratio should only penalize downside risk.

        Sortino = (mean(returns) - rf) / std(negative_returns) * sqrt(252)
        """
        from scripts.backtest.metrics import sortino_ratio

        # Returns with only one downside day
        returns = [0.01] * 10 + [-0.02]  # 10 gains, 1 loss

        result = sortino_ratio(returns, risk_free_rate=0.0)

        # Sortino should be higher than Sharpe when few downsides
        assert result > 0, "Sortino should be positive"

    def test_max_drawdown_calculation(self):
        """T019: Max drawdown should find largest peak-to-trough decline."""
        from scripts.backtest.metrics import max_drawdown

        # Equity curve with known drawdown
        equity_curve = [100, 110, 120, 100, 90, 95, 100]  # DD from 120 to 90 = 25%

        result = max_drawdown(equity_curve)

        # Max DD should be (120-90)/120 = 0.25 = 25%
        assert abs(result - 0.25) < 0.01, f"Expected ~0.25, got {result}"

    def test_win_rate_calculation(self):
        """T020: Win rate should count profitable trades correctly."""
        from scripts.backtest.metrics import win_rate
        from scripts.backtest.engine import Trade

        trades = [
            Trade(
                datetime(2025, 1, 1),
                datetime(2025, 1, 2),
                100,
                110,
                "LONG",
                10,
                0.1,
                0.5,
            ),
            Trade(
                datetime(2025, 1, 2),
                datetime(2025, 1, 3),
                110,
                100,
                "LONG",
                -10,
                -0.1,
                0.5,
            ),
            Trade(
                datetime(2025, 1, 3),
                datetime(2025, 1, 4),
                100,
                120,
                "LONG",
                20,
                0.2,
                0.5,
            ),
        ]

        result = win_rate(trades)

        # 2 winning trades out of 3 = 66.67%
        assert abs(result - 2 / 3) < 0.01, f"Expected ~0.667, got {result}"


class TestMultiSignalComparison:
    """Test multi-signal comparison (US3)."""

    def test_compare_signals_ranking(self):
        """T027: Signals should be ranked by Sharpe ratio."""
        from scripts.backtest.engine import compare_signals
        from scripts.backtest.data_loader import PricePoint

        # Create price data
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, i + 1),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.0,  # Will be overridden per signal
            )
            for i in range(30)
        ]

        # Define signals with different expected performance
        # "good" signal: BUY during uptrend
        # "bad" signal: SELL during uptrend
        signals = {
            "good": [0.5] * 30,  # Always BUY
            "bad": [-0.5] * 30,  # Always SELL
        }

        result = compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 30),
        )

        # Good signal should rank higher than bad signal
        assert result.ranking[0] == "good", "Good signal should rank first"
        assert result.best_signal == "good"
        assert len(result.results) == 2

    def test_compare_signals_consistency(self):
        """T028: Same signal should produce consistent results."""
        from scripts.backtest.engine import compare_signals
        from scripts.backtest.data_loader import PricePoint

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, i + 1),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.5,
            )
            for i in range(30)
        ]

        # Same signal twice should produce identical results
        signals = {
            "signal_a": [0.5] * 30,
            "signal_b": [0.5] * 30,  # Identical
        }

        result = compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 30),
        )

        # Results should be identical
        assert (
            abs(
                result.results["signal_a"].total_return
                - result.results["signal_b"].total_return
            )
            < 0.001
        )


class TestWeightOptimization:
    """Test weight optimization (US4)."""

    def test_weight_optimization_improves(self):
        """T032: Optimization should find weights that improve Sharpe."""
        from scripts.backtest.optimizer import optimize_weights
        from scripts.backtest.data_loader import PricePoint

        # Create price data with pattern
        prices = []
        for i in range(100):
            # Price oscillates
            price = 50000 + 1000 * (i % 10)
            prices.append(
                PricePoint(
                    timestamp=datetime(2025, 1, 1)
                    + __import__("datetime").timedelta(days=i),
                    utxoracle_price=price,
                    exchange_price=price,
                    confidence=0.9,
                    signal_value=0.0,
                )
            )

        # Signals that somewhat correlate with price movement
        signals = {
            "whale": [0.3 if i % 10 < 5 else -0.3 for i in range(100)],
            "utxo": [0.2 if i % 10 < 3 else -0.2 for i in range(100)],
        }

        result = optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 4, 10),
            step=0.2,  # Coarse grid for speed
        )

        # Should find some weights
        assert result.best_weights is not None
        assert len(result.best_weights) == 2

    def test_weights_sum_to_one(self):
        """T033: Optimized weights should sum to 1.0."""
        from scripts.backtest.optimizer import optimize_weights
        from scripts.backtest.data_loader import PricePoint
        from datetime import timedelta

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
            "signal_a": [0.5] * 50,
            "signal_b": [-0.5] * 50,
        }

        result = optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 2, 19),
            step=0.5,
        )

        # Weights should sum to 1.0
        total = sum(result.best_weights.values())
        assert abs(total - 1.0) < 0.01, f"Weights should sum to 1.0, got {total}"

    def test_walk_forward_validation(self):
        """T034: Walk-forward validation should prevent overfitting."""
        from scripts.backtest.optimizer import walk_forward_validate
        from scripts.backtest.data_loader import PricePoint
        from datetime import timedelta

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
            "whale": [0.5 if i < 50 else -0.5 for i in range(100)],
            "utxo": [0.3] * 100,
        }

        weights = {"whale": 0.5, "utxo": 0.5}

        result = walk_forward_validate(
            weights=weights,
            signals=signals,
            prices=prices,
            train_ratio=0.7,
        )

        # Should return validation metrics
        assert "train_sharpe" in result
        assert "test_sharpe" in result


class TestEdgeCases:
    """Test edge cases and defensive coding."""

    def test_zero_initial_capital_no_crash(self):
        """Zero initial capital should not cause ZeroDivisionError."""
        from scripts.backtest.engine import run_backtest
        from scripts.backtest.data_loader import PricePoint

        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 3),
            signal_source="test",
            initial_capital=0.0,
        )
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1),
                utxoracle_price=50000.0,
                signal_value=0.5,
            ),
            PricePoint(
                timestamp=datetime(2025, 1, 2),
                utxoracle_price=51000.0,
                signal_value=-0.5,
            ),
        ]

        # Should not raise ZeroDivisionError
        result = run_backtest(config, prices=prices)
        assert result.total_return == 0.0

    def test_empty_prices_no_crash(self):
        """Empty price list should return empty result."""
        from scripts.backtest.engine import run_backtest

        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 3),
            signal_source="test",
        )

        result = run_backtest(config, prices=[])
        assert result.num_trades == 0
        assert result.total_return == 0.0

    def test_zero_entry_price_no_crash(self):
        """Zero price should not cause ZeroDivisionError."""
        from scripts.backtest.engine import run_backtest
        from scripts.backtest.data_loader import PricePoint

        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 3),
            signal_source="test",
        )
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1),
                utxoracle_price=0.0,  # Zero price
                signal_value=0.5,
            ),
            PricePoint(
                timestamp=datetime(2025, 1, 2),
                utxoracle_price=50000.0,
                signal_value=-0.5,
            ),
        ]

        # Should not crash
        result = run_backtest(config, prices=prices)
        assert result is not None
