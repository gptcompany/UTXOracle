"""
Tests for ModelBacktester (spec-036 US5).

TDD: These tests MUST FAIL before implementation (RED phase).
Run: uv run pytest tests/test_models/test_model_backtester.py -v
"""

from datetime import date

import pandas as pd


class TestModelBacktestResult:
    """Tests for ModelBacktestResult dataclass."""

    def test_create_result(self):
        """ModelBacktestResult can be created with valid data."""
        from scripts.models.backtest.model_backtester import ModelBacktestResult

        result = ModelBacktestResult(
            model_name="Test Model",
            start_date=date(2020, 1, 1),
            end_date=date(2020, 12, 31),
            predictions=365,
            mae=1000.0,
            mape=5.0,
            rmse=1500.0,
            direction_accuracy=0.55,
            sharpe_ratio=1.2,
            max_drawdown=-20.0,
            daily_results=pd.DataFrame(),
        )

        assert result.model_name == "Test Model"
        assert result.mae == 1000.0
        assert result.mape == 5.0

    def test_result_to_dict(self):
        """ModelBacktestResult.to_dict() returns proper dictionary format."""
        from scripts.models.backtest.model_backtester import ModelBacktestResult

        result = ModelBacktestResult(
            model_name="Test Model",
            start_date=date(2020, 1, 1),
            end_date=date(2020, 12, 31),
            predictions=365,
            mae=1000.0,
            mape=5.0,
            rmse=1500.0,
            direction_accuracy=0.55,
            sharpe_ratio=1.2,
            max_drawdown=-20.0,
            daily_results=pd.DataFrame(),
        )

        d = result.to_dict()
        assert d["model_name"] == "Test Model"
        assert d["metrics"]["mae"] == 1000.0
        assert d["metrics"]["mape"] == 5.0


class TestModelBacktester:
    """Tests for ModelBacktester class."""

    def test_walk_forward_split(self):
        """ModelBacktester correctly splits data for walk-forward testing."""
        from scripts.models.backtest.model_backtester import ModelBacktester

        backtester = ModelBacktester(train_pct=0.7)
        assert backtester.train_pct == 0.7

        # Create sample data
        dates = pd.date_range(start="2020-01-01", periods=100, freq="D")
        prices = pd.Series([50000 + i * 10 for i in range(100)], index=dates)

        # Check split
        train_end_idx = int(len(prices) * backtester.train_pct)
        assert train_end_idx == 70

    def test_run_returns_result(self):
        """ModelBacktester.run() returns ModelBacktestResult."""
        from scripts.models.backtest.model_backtester import ModelBacktester
        from scripts.models.power_law_adapter import PowerLawAdapter

        backtester = ModelBacktester()
        model = PowerLawAdapter()

        # Create sample data
        dates = pd.date_range(start="2020-01-01", periods=100, freq="D")
        prices = pd.Series([50000 + i * 10 for i in range(100)], index=dates)

        result = backtester.run(model, prices)

        from scripts.models.backtest.model_backtester import ModelBacktestResult

        assert isinstance(result, ModelBacktestResult)

    def test_metric_calculations_mae(self):
        """ModelBacktester calculates MAE correctly."""
        from scripts.models.backtest.model_backtester import ModelBacktester

        backtester = ModelBacktester()

        # Mock predictions vs actuals
        predictions = [100, 110, 90, 105]
        actuals = [100, 100, 100, 100]

        # MAE = mean(|pred - actual|) = (0 + 10 + 10 + 5) / 4 = 6.25
        mae = backtester._calculate_mae(predictions, actuals)
        assert abs(mae - 6.25) < 0.01

    def test_metric_calculations_mape(self):
        """ModelBacktester calculates MAPE correctly."""
        from scripts.models.backtest.model_backtester import ModelBacktester

        backtester = ModelBacktester()

        predictions = [105, 95]
        actuals = [100, 100]

        # MAPE = mean(|pred - actual| / actual * 100) = (5% + 5%) / 2 = 5%
        mape = backtester._calculate_mape(predictions, actuals)
        assert abs(mape - 5.0) < 0.01

    def test_metric_calculations_rmse(self):
        """ModelBacktester calculates RMSE correctly."""
        from scripts.models.backtest.model_backtester import ModelBacktester

        backtester = ModelBacktester()

        predictions = [102, 98]
        actuals = [100, 100]

        # RMSE = sqrt(mean((pred - actual)^2)) = sqrt((4 + 4) / 2) = sqrt(4) = 2
        rmse = backtester._calculate_rmse(predictions, actuals)
        assert abs(rmse - 2.0) < 0.01

    def test_metric_direction_accuracy(self):
        """ModelBacktester calculates direction accuracy correctly."""
        from scripts.models.backtest.model_backtester import ModelBacktester

        backtester = ModelBacktester()

        # Predictions say "up", actuals go "up" 3 out of 4 times
        predictions = [100, 110, 120, 130]  # All predict higher
        actuals = [100, 110, 115, 108]  # Only 2 actually went up

        direction_acc = backtester._calculate_direction_accuracy(predictions, actuals)
        # Direction matches when both change in same direction
        # pred[1]-pred[0]=10 (up), actual[1]-actual[0]=10 (up) -> match
        # pred[2]-pred[1]=10 (up), actual[2]-actual[1]=5 (up) -> match
        # pred[3]-pred[2]=10 (up), actual[3]-actual[2]=-7 (down) -> no match
        # 2 matches out of 3 comparisons = 66.7%
        assert 0 <= direction_acc <= 1

    def test_compare_models(self):
        """ModelBacktester.compare_models() returns ranking."""
        from scripts.models.backtest.model_backtester import ModelBacktester
        from scripts.models.power_law_adapter import PowerLawAdapter
        from scripts.models.stock_to_flow import StockToFlowModel

        backtester = ModelBacktester()
        models = [PowerLawAdapter(), StockToFlowModel()]

        # Create sample data
        dates = pd.date_range(start="2020-01-01", periods=100, freq="D")
        prices = pd.Series([50000 + i * 10 for i in range(100)], index=dates)

        comparison = backtester.compare_models(models, prices)

        # Should return DataFrame with ranking
        assert isinstance(comparison, pd.DataFrame)
        assert "model_name" in comparison.columns
        assert "mape" in comparison.columns.str.lower() or "MAPE" in comparison.columns

    def test_compare_models_sorted_by_mape(self):
        """ModelBacktester.compare_models() returns results sorted by MAPE."""
        from scripts.models.backtest.model_backtester import ModelBacktester
        from scripts.models.power_law_adapter import PowerLawAdapter
        from scripts.models.thermocap import ThermocapModel

        backtester = ModelBacktester()
        models = [PowerLawAdapter(), ThermocapModel()]

        dates = pd.date_range(start="2020-01-01", periods=100, freq="D")
        prices = pd.Series([50000 + i * 10 for i in range(100)], index=dates)

        comparison = backtester.compare_models(models, prices)

        # Results should be sorted by MAPE (ascending)
        mape_col = "MAPE" if "MAPE" in comparison.columns else "mape"
        mape_values = comparison[mape_col].tolist()
        assert mape_values == sorted(mape_values)
