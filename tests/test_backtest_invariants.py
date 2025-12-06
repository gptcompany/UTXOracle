"""Round 4 (Pass 2): Data consistency and invariants tests.

Tests mathematical invariants and data consistency guarantees.
"""

from datetime import datetime, timedelta
import pytest

from scripts.backtest import (
    BacktestConfig,
    Trade,
    run_backtest,
    compare_signals,
    optimize_weights,
    max_drawdown,
    win_rate,
    profit_factor,
    calculate_returns,
    PricePoint,
)
from scripts.backtest.optimizer import generate_weight_grid, combine_signals


class TestWeightInvariants:
    """Test weight-related invariants."""

    @pytest.mark.parametrize("n_signals", [2, 3, 4, 5])
    def test_weights_sum_to_one(self, n_signals):
        """All weight combinations should sum to exactly 1.0."""
        signals = [f"s{i}" for i in range(n_signals)]
        grid = generate_weight_grid(signals, step=0.2)

        for weights in grid:
            total = sum(weights.values())
            assert total == pytest.approx(1.0, abs=1e-10), (
                f"Weights sum to {total}, not 1.0"
            )

    def test_weights_non_negative(self):
        """Generated weights should be non-negative."""
        signals = ["a", "b", "c"]
        grid = generate_weight_grid(signals, step=0.2)

        for weights in grid:
            for name, weight in weights.items():
                assert weight >= 0.0, f"Negative weight {weight} for {name}"

    def test_weights_at_most_one(self):
        """No single weight should exceed 1.0."""
        signals = ["a", "b", "c"]
        grid = generate_weight_grid(signals, step=0.2)

        for weights in grid:
            for name, weight in weights.items():
                assert weight <= 1.0, f"Weight {weight} > 1.0 for {name}"


class TestMetricBounds:
    """Test metric value bounds."""

    def test_win_rate_between_zero_and_one(self):
        """Win rate should always be between 0 and 1."""
        now = datetime.now()

        # Various trade combinations
        test_cases = [
            # All winners
            [Trade(now, now, 100, 110, "LONG", 10, 0.1, 0.5) for _ in range(5)],
            # All losers
            [Trade(now, now, 100, 90, "LONG", -10, -0.1, 0.5) for _ in range(5)],
            # Mixed
            [
                Trade(now, now, 100, 110, "LONG", 10, 0.1, 0.5),
                Trade(now, now, 100, 90, "LONG", -10, -0.1, 0.5),
                Trade(now, now, 100, 105, "LONG", 5, 0.05, 0.5),
            ],
        ]

        for trades in test_cases:
            rate = win_rate(trades)
            assert 0.0 <= rate <= 1.0, f"Win rate {rate} out of bounds"

    def test_max_drawdown_between_zero_and_one(self):
        """Max drawdown should be between 0 and 1."""
        test_curves = [
            [100, 110, 120, 130],  # Always up
            [100, 90, 80, 70],  # Always down
            [100, 120, 80, 150],  # Volatile
            [100, 100, 100],  # Flat
        ]

        for curve in test_curves:
            dd = max_drawdown(curve)
            assert 0.0 <= dd <= 1.0, f"Max drawdown {dd} out of bounds"

    def test_profit_factor_non_negative(self):
        """Profit factor should be non-negative."""
        now = datetime.now()

        test_cases = [
            [Trade(now, now, 100, 110, "LONG", 10, 0.1, 0.5)],
            [Trade(now, now, 100, 90, "LONG", -10, -0.1, 0.5)],
            [
                Trade(now, now, 100, 110, "LONG", 10, 0.1, 0.5),
                Trade(now, now, 100, 90, "LONG", -10, -0.1, 0.5),
            ],
        ]

        for trades in test_cases:
            pf = profit_factor(trades)
            assert pf >= 0.0, f"Profit factor {pf} is negative"


class TestEquityCurveConsistency:
    """Test equity curve consistency with trades."""

    def test_equity_curve_starts_at_initial_capital(self):
        """Equity curve should start at initial capital."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
            signal_source="test",
            initial_capital=50000.0,
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

        if result.equity_curve:
            assert result.equity_curve[0] == 50000.0

    def test_equity_changes_match_trade_pnl(self):
        """Changes in equity should match trade P&L."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 10),
            signal_source="test",
            initial_capital=10000.0,
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

        if result.trades and len(result.equity_curve) > 1:
            total_pnl = sum(t.pnl for t in result.trades)
            equity_change = result.equity_curve[-1] - result.equity_curve[0]
            assert total_pnl == pytest.approx(equity_change, rel=0.01)


class TestReturnsConsistency:
    """Test returns calculation consistency."""

    def test_returns_length(self):
        """Returns should have length n-1 for equity curve of length n."""
        test_curves = [
            [100, 110],
            [100, 110, 120],
            [100, 110, 120, 130, 140],
        ]

        for curve in test_curves:
            returns = calculate_returns(curve)
            assert len(returns) == len(curve) - 1

    def test_returns_reconstruct_equity(self):
        """Returns should reconstruct equity curve."""
        equity = [100.0, 110.0, 99.0, 120.0]
        returns = calculate_returns(equity)

        # Reconstruct from returns
        reconstructed = [equity[0]]
        for r in returns:
            reconstructed.append(reconstructed[-1] * (1 + r))

        for e1, e2 in zip(equity, reconstructed):
            assert e1 == pytest.approx(e2, rel=1e-10)


class TestComparisonRankingConsistency:
    """Test signal comparison ranking consistency."""

    def test_ranking_matches_sharpe_order(self):
        """Ranking should be ordered by Sharpe ratio (descending)."""
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

        signals = {
            "strong_buy": [0.5] * 30,
            "weak_buy": [0.35] * 30,
            "sell": [-0.5] * 30,
        }

        comparison = compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 30),
        )

        # Check ranking is sorted by Sharpe
        sharpes = [comparison.results[s].sharpe_ratio for s in comparison.ranking]
        for i in range(len(sharpes) - 1):
            assert sharpes[i] >= sharpes[i + 1], "Ranking not sorted by Sharpe"

    def test_best_signal_is_first_in_ranking(self):
        """best_signal should be the first in ranking."""
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

        if comparison.ranking:
            assert comparison.best_signal == comparison.ranking[0]

    def test_best_sharpe_matches_best_signal(self):
        """best_sharpe should match Sharpe of best_signal."""
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

        if comparison.best_signal:
            assert (
                comparison.best_sharpe
                == comparison.results[comparison.best_signal].sharpe_ratio
            )


class TestOptimizationConsistency:
    """Test optimization result consistency."""

    def test_optimized_weights_sum_to_one(self):
        """Optimized weights should sum to 1.0."""
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

        signals = {"a": [0.5] * 30, "b": [-0.5] * 30}

        result = optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 30),
            step=0.5,
        )

        if result.best_weights:
            total = sum(result.best_weights.values())
            assert total == pytest.approx(1.0, abs=1e-10)

    def test_improvement_matches_sharpe_difference(self):
        """Improvement should match (best - baseline) / |baseline|."""
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

        signals = {"a": [0.5] * 30, "b": [0.3] * 30}

        result = optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 30),
            step=0.5,
        )

        if result.baseline_sharpe != 0:
            expected_improvement = (result.best_sharpe - result.baseline_sharpe) / abs(
                result.baseline_sharpe
            )
            assert result.improvement == pytest.approx(expected_improvement, rel=0.01)


class TestCombineSignalsConsistency:
    """Test combined signals consistency."""

    def test_combined_signal_weighted_average(self):
        """Combined signal should be weighted average."""
        signals = {"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]}
        weights = {"a": 0.3, "b": 0.7}

        combined = combine_signals(signals, weights)

        for i in range(3):
            expected = 0.3 * signals["a"][i] + 0.7 * signals["b"][i]
            assert combined[i] == pytest.approx(expected)

    def test_equal_weights_is_average(self):
        """Equal weights should give simple average."""
        signals = {"a": [10.0] * 5, "b": [20.0] * 5}
        weights = {"a": 0.5, "b": 0.5}

        combined = combine_signals(signals, weights)

        for c in combined:
            assert c == pytest.approx(15.0)  # (10 + 20) / 2


class TestTradeConsistency:
    """Test trade data consistency."""

    def test_long_profit_when_price_rises(self):
        """LONG trade should profit when exit > entry."""
        now = datetime.now()

        from scripts.backtest.engine import execute_trade

        trade = execute_trade(
            entry_time=now,
            entry_price=100.0,
            exit_time=now + timedelta(hours=1),
            exit_price=110.0,  # 10% increase
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.0,
            capital=10000.0,
            signal_value=0.5,
        )

        assert trade.pnl > 0
        assert trade.pnl_pct > 0

    def test_short_profit_when_price_falls(self):
        """SHORT trade should profit when exit < entry."""
        now = datetime.now()

        from scripts.backtest.engine import execute_trade

        trade = execute_trade(
            entry_time=now,
            entry_price=100.0,
            exit_time=now + timedelta(hours=1),
            exit_price=90.0,  # 10% decrease
            direction="SHORT",
            position_size=1.0,
            transaction_cost=0.0,
            capital=10000.0,
            signal_value=-0.5,
        )

        assert trade.pnl > 0
        assert trade.pnl_pct > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
