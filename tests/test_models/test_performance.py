"""
Performance benchmark tests for Custom Price Models Framework (spec-036).

Validates spec validation criteria #5:
- Model prediction must execute in <100ms
- Backtest must execute in <500ms per 1000 days

Run: uv run pytest tests/test_models/test_performance.py -v
"""

import time
from datetime import date

import pandas as pd
import pytest


class TestModelPredictionPerformance:
    """Benchmark tests for model prediction speed."""

    @pytest.mark.slow
    def test_power_law_prediction_under_100ms(self):
        """PowerLawAdapter.predict() executes in <100ms."""
        from scripts.models.power_law_adapter import PowerLawAdapter

        model = PowerLawAdapter()
        target_date = date.today()

        # Warm-up call
        model.predict(target_date)

        # Benchmark 10 iterations
        start = time.perf_counter()
        iterations = 10
        for _ in range(iterations):
            model.predict(target_date)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 100, f"PowerLaw prediction took {avg_ms:.2f}ms (limit: 100ms)"

    @pytest.mark.slow
    def test_stock_to_flow_prediction_under_100ms(self):
        """StockToFlowModel.predict() executes in <100ms."""
        from scripts.models.stock_to_flow import StockToFlowModel

        model = StockToFlowModel()
        target_date = date.today()

        # Warm-up call
        model.predict(target_date)

        # Benchmark 10 iterations
        start = time.perf_counter()
        iterations = 10
        for _ in range(iterations):
            model.predict(target_date)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 100, f"S2F prediction took {avg_ms:.2f}ms (limit: 100ms)"

    @pytest.mark.slow
    def test_thermocap_prediction_under_100ms(self):
        """ThermocapModel.predict() executes in <100ms."""
        from scripts.models.thermocap import ThermocapModel

        model = ThermocapModel()
        target_date = date.today()

        # Warm-up call
        model.predict(target_date)

        # Benchmark 10 iterations
        start = time.perf_counter()
        iterations = 10
        for _ in range(iterations):
            model.predict(target_date)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 100, f"Thermocap prediction took {avg_ms:.2f}ms (limit: 100ms)"

    @pytest.mark.slow
    def test_ensemble_prediction_under_100ms(self):
        """EnsembleModel.predict() with 3 models executes in <100ms."""
        from scripts.models.ensemble import EnsembleConfig, EnsembleModel

        config = EnsembleConfig(
            models=["Power Law", "Stock-to-Flow", "Thermocap"],
            weights=[0.4, 0.3, 0.3],
            aggregation="weighted_avg",
        )
        ensemble = EnsembleModel(config)
        target_date = date.today()

        # Warm-up call
        ensemble.predict(target_date)

        # Benchmark 10 iterations
        start = time.perf_counter()
        iterations = 10
        for _ in range(iterations):
            ensemble.predict(target_date)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        # Ensemble has overhead, allow slightly more time but still under 100ms
        assert avg_ms < 100, f"Ensemble prediction took {avg_ms:.2f}ms (limit: 100ms)"


class TestBacktestPerformance:
    """Benchmark tests for backtest speed."""

    @pytest.fixture
    def sample_prices_1000_days(self) -> pd.Series:
        """Generate 1000 days of sample price data."""
        import numpy as np

        np.random.seed(42)
        dates = pd.date_range(start="2020-01-01", periods=1000, freq="D")
        # Simulated price with trend and volatility
        prices = 10000 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, len(dates))))
        return pd.Series(prices, index=dates)

    @pytest.mark.slow
    def test_backtest_power_law_under_500ms_per_1000_days(
        self, sample_prices_1000_days: pd.Series
    ):
        """ModelBacktester.run() on PowerLaw executes in <500ms for 1000 days."""
        from scripts.models.backtest.model_backtester import ModelBacktester
        from scripts.models.power_law_adapter import PowerLawAdapter

        backtester = ModelBacktester(train_pct=0.7)
        model = PowerLawAdapter()

        # Warm-up call
        backtester.run(model, sample_prices_1000_days)

        # Benchmark
        start = time.perf_counter()
        backtester.run(model, sample_prices_1000_days)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 500, (
            f"PowerLaw backtest took {elapsed_ms:.2f}ms for 1000 days (limit: 500ms)"
        )

    @pytest.mark.slow
    def test_backtest_stock_to_flow_under_500ms_per_1000_days(
        self, sample_prices_1000_days: pd.Series
    ):
        """ModelBacktester.run() on S2F executes in <500ms for 1000 days."""
        from scripts.models.backtest.model_backtester import ModelBacktester
        from scripts.models.stock_to_flow import StockToFlowModel

        backtester = ModelBacktester(train_pct=0.7)
        model = StockToFlowModel()

        # Warm-up call
        backtester.run(model, sample_prices_1000_days)

        # Benchmark
        start = time.perf_counter()
        backtester.run(model, sample_prices_1000_days)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 500, (
            f"S2F backtest took {elapsed_ms:.2f}ms for 1000 days (limit: 500ms)"
        )

    @pytest.mark.slow
    def test_backtest_thermocap_under_500ms_per_1000_days(
        self, sample_prices_1000_days: pd.Series
    ):
        """ModelBacktester.run() on Thermocap executes in <500ms for 1000 days."""
        from scripts.models.backtest.model_backtester import ModelBacktester
        from scripts.models.thermocap import ThermocapModel

        backtester = ModelBacktester(train_pct=0.7)
        model = ThermocapModel()

        # Warm-up call
        backtester.run(model, sample_prices_1000_days)

        # Benchmark
        start = time.perf_counter()
        backtester.run(model, sample_prices_1000_days)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 500, (
            f"Thermocap backtest took {elapsed_ms:.2f}ms for 1000 days (limit: 500ms)"
        )

    @pytest.mark.slow
    def test_compare_models_under_2s_for_3_models(
        self, sample_prices_1000_days: pd.Series
    ):
        """ModelBacktester.compare_models() with 3 models executes in <2s."""
        from scripts.models.backtest.model_backtester import ModelBacktester
        from scripts.models.power_law_adapter import PowerLawAdapter
        from scripts.models.stock_to_flow import StockToFlowModel
        from scripts.models.thermocap import ThermocapModel

        backtester = ModelBacktester(train_pct=0.7)
        models = [PowerLawAdapter(), StockToFlowModel(), ThermocapModel()]

        # Warm-up call
        backtester.compare_models(models, sample_prices_1000_days)

        # Benchmark
        start = time.perf_counter()
        backtester.compare_models(models, sample_prices_1000_days)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # 3 models × 500ms = 1500ms, allow 2000ms for overhead
        assert elapsed_ms < 2000, (
            f"Compare 3 models took {elapsed_ms:.2f}ms (limit: 2000ms)"
        )
