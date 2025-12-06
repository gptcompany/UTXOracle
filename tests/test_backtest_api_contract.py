"""Round 6: API contract verification tests.

Verifies public API matches documentation and spec requirements.
"""

from datetime import datetime, timedelta
import pytest

from scripts.backtest import (
    # Engine exports
    BacktestConfig,
    BacktestResult,
    ComparisonResult,
    Trade,
    run_backtest,
    compare_signals,
    # Metrics exports
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    win_rate,
    profit_factor,
    calculate_all_metrics,
    calculate_returns,
    # Data exports
    PricePoint,
    HistoricalData,
    load_historical_data,
    load_from_duckdb,
    load_from_html,
    save_backtest_result,
    load_backtest_history,
    # Optimizer exports
    OptimizationResult,
    optimize_weights,
    walk_forward_validate,
)


class TestPublicAPIExports:
    """Verify all documented symbols are exported."""

    def test_engine_exports(self):
        """Engine module exports all documented symbols."""
        assert callable(run_backtest)
        assert callable(compare_signals)
        assert BacktestConfig is not None
        assert BacktestResult is not None
        assert ComparisonResult is not None
        assert Trade is not None

    def test_metrics_exports(self):
        """Metrics module exports all documented symbols."""
        assert callable(sharpe_ratio)
        assert callable(sortino_ratio)
        assert callable(max_drawdown)
        assert callable(win_rate)
        assert callable(profit_factor)
        assert callable(calculate_all_metrics)
        assert callable(calculate_returns)

    def test_data_exports(self):
        """Data module exports all documented symbols."""
        assert PricePoint is not None
        assert HistoricalData is not None
        assert callable(load_historical_data)
        assert callable(load_from_duckdb)
        assert callable(load_from_html)
        assert callable(save_backtest_result)
        assert callable(load_backtest_history)

    def test_optimizer_exports(self):
        """Optimizer module exports all documented symbols."""
        assert OptimizationResult is not None
        assert callable(optimize_weights)
        assert callable(walk_forward_validate)


class TestBacktestConfigContract:
    """Verify BacktestConfig matches documented interface."""

    def test_required_fields(self):
        """BacktestConfig requires start_date, end_date, signal_source."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 11, 30),
            signal_source="fusion",
        )
        assert config.start_date == datetime(2025, 1, 1)
        assert config.end_date == datetime(2025, 11, 30)
        assert config.signal_source == "fusion"

    def test_default_values(self):
        """BacktestConfig has documented default values."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 11, 30),
            signal_source="test",
        )
        # Defaults from quickstart.md
        assert config.buy_threshold == 0.3
        assert config.sell_threshold == -0.3
        assert config.position_size == 1.0
        assert config.transaction_cost == 0.001
        assert config.initial_capital == 10000.0

    def test_all_fields_configurable(self):
        """All documented fields can be customized."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 11, 30),
            signal_source="fusion",
            buy_threshold=0.5,
            sell_threshold=-0.5,
            position_size=0.5,
            transaction_cost=0.002,
            initial_capital=50000.0,
        )
        assert config.buy_threshold == 0.5
        assert config.sell_threshold == -0.5
        assert config.position_size == 0.5
        assert config.transaction_cost == 0.002
        assert config.initial_capital == 50000.0


class TestBacktestResultContract:
    """Verify BacktestResult matches documented interface."""

    def test_result_has_documented_fields(self):
        """BacktestResult has all documented fields from quickstart."""
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

        result = run_backtest(config, prices=prices)

        # Documented fields from quickstart.md
        assert hasattr(result, "total_return")
        assert hasattr(result, "sharpe_ratio")
        assert hasattr(result, "win_rate")
        assert hasattr(result, "max_drawdown")
        assert hasattr(result, "num_trades")

        # Type verification
        assert isinstance(result.total_return, float)
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.win_rate, float)
        assert isinstance(result.max_drawdown, float)
        assert isinstance(result.num_trades, int)


class TestComparisonResultContract:
    """Verify ComparisonResult matches documented interface."""

    def test_comparison_has_ranking(self):
        """ComparisonResult has ranking list."""
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

        signals = {
            "whale": [0.5] * 20,
            "utxo": [-0.5] * 20,
        }

        comparison = compare_signals(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 20),
        )

        # Documented fields
        assert hasattr(comparison, "ranking")
        assert hasattr(comparison, "results")
        assert isinstance(comparison.ranking, list)
        assert isinstance(comparison.results, dict)

        # Each result should be a BacktestResult
        for signal_name, result in comparison.results.items():
            assert isinstance(result, BacktestResult)
            assert hasattr(result, "sharpe_ratio")
            assert hasattr(result, "win_rate")


class TestOptimizationResultContract:
    """Verify OptimizationResult matches documented interface."""

    def test_optimization_has_documented_fields(self):
        """OptimizationResult has best_weights, best_sharpe, improvement."""
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
            "trend": [0.5] * 30,
            "contrarian": [-0.5] * 30,
        }

        optimization = optimize_weights(
            signals=signals,
            prices=prices,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 30),
            step=0.5,
        )

        # Documented fields from quickstart.md
        assert hasattr(optimization, "best_weights")
        assert hasattr(optimization, "best_sharpe")
        assert hasattr(optimization, "improvement")

        # Type verification
        assert isinstance(optimization.best_weights, dict)
        assert isinstance(optimization.best_sharpe, float)
        assert isinstance(optimization.improvement, float)


class TestPricePointContract:
    """Verify PricePoint data class interface."""

    def test_pricepoint_fields(self):
        """PricePoint has all required fields."""
        pp = PricePoint(
            timestamp=datetime(2025, 1, 1),
            utxoracle_price=50000.0,
            exchange_price=50100.0,
            confidence=0.9,
            signal_value=0.5,
        )

        assert pp.timestamp == datetime(2025, 1, 1)
        assert pp.utxoracle_price == 50000.0
        assert pp.exchange_price == 50100.0
        assert pp.confidence == 0.9
        assert pp.signal_value == 0.5

    def test_pricepoint_optional_fields(self):
        """PricePoint optional fields have defaults."""
        pp = PricePoint(
            timestamp=datetime(2025, 1, 1),
            utxoracle_price=50000.0,
        )

        assert pp.exchange_price is None
        assert pp.confidence == 0.0
        assert pp.signal_value is None


class TestTradeContract:
    """Verify Trade data class interface."""

    def test_trade_fields(self):
        """Trade has all documented fields."""
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

        assert trade.entry_time == now
        assert trade.exit_time == now + timedelta(hours=1)
        assert trade.entry_price == 100.0
        assert trade.exit_price == 110.0
        assert trade.direction == "LONG"
        assert trade.pnl == 10.0
        assert trade.pnl_pct == 0.1
        assert trade.signal_value == 0.5


class TestMetricsFunctionContracts:
    """Verify metrics function signatures and behavior."""

    def test_sharpe_ratio_accepts_list(self):
        """sharpe_ratio accepts list of returns."""
        result = sharpe_ratio([0.01, 0.02, -0.01, 0.03])
        assert isinstance(result, float)

    def test_sortino_ratio_accepts_list(self):
        """sortino_ratio accepts list of returns."""
        result = sortino_ratio([0.01, 0.02, -0.01, 0.03])
        assert isinstance(result, float)

    def test_max_drawdown_accepts_equity_curve(self):
        """max_drawdown accepts equity curve list."""
        result = max_drawdown([100, 110, 105, 120])
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_win_rate_accepts_trades(self):
        """win_rate accepts list of Trade objects."""
        now = datetime.now()
        trades = [
            Trade(now, now, 100, 110, "LONG", 10, 0.1, 0.5),
            Trade(now, now, 100, 90, "LONG", -10, -0.1, 0.5),
        ]
        result = win_rate(trades)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_profit_factor_accepts_trades(self):
        """profit_factor accepts list of Trade objects."""
        now = datetime.now()
        trades = [
            Trade(now, now, 100, 110, "LONG", 10, 0.1, 0.5),
            Trade(now, now, 100, 90, "LONG", -10, -0.1, 0.5),
        ]
        result = profit_factor(trades)
        assert isinstance(result, float)

    def test_calculate_returns_returns_list(self):
        """calculate_returns returns list of floats."""
        result = calculate_returns([100, 110, 120])
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(r, float) for r in result)


class TestDataLoaderContracts:
    """Verify data loader function signatures."""

    def test_load_historical_data_returns_historicaldata(self):
        """load_historical_data returns HistoricalData object."""
        result = load_historical_data(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 5),
        )
        assert isinstance(result, HistoricalData)
        assert hasattr(result, "prices")
        assert hasattr(result, "start_date")
        assert hasattr(result, "end_date")
        assert hasattr(result, "source")

    def test_load_from_duckdb_returns_list(self):
        """load_from_duckdb returns list of PricePoint."""
        result = load_from_duckdb(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 5),
        )
        assert isinstance(result, list)

    def test_load_from_html_returns_list(self):
        """load_from_html returns list of PricePoint."""
        result = load_from_html(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 5),
        )
        assert isinstance(result, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
