"""
Tests for StockToFlowModel (spec-036 US3).

TDD: These tests MUST FAIL before implementation (RED phase).
Run: uv run pytest tests/test_models/test_stock_to_flow.py -v
"""

from datetime import date

import pandas as pd

from scripts.models.base import ModelPrediction, PriceModel


class TestStockToFlowModel:
    """Tests for Stock-to-Flow model."""

    def test_implements_price_model_interface(self):
        """StockToFlowModel implements PriceModel ABC."""
        from scripts.models.stock_to_flow import StockToFlowModel

        model = StockToFlowModel()
        assert isinstance(model, PriceModel)

    def test_name_property(self):
        """StockToFlowModel.name returns 'Stock-to-Flow'."""
        from scripts.models.stock_to_flow import StockToFlowModel

        model = StockToFlowModel()
        assert model.name == "Stock-to-Flow"

    def test_description_property(self):
        """StockToFlowModel.description describes the model."""
        from scripts.models.stock_to_flow import StockToFlowModel

        model = StockToFlowModel()
        assert (
            "stock" in model.description.lower() or "s2f" in model.description.lower()
        )

    def test_required_data_property(self):
        """StockToFlowModel.required_data includes block_heights."""
        from scripts.models.stock_to_flow import StockToFlowModel

        model = StockToFlowModel()
        assert "block_heights" in model.required_data

    def test_halving_schedule_constants(self):
        """StockToFlowModel has correct halving constants."""
        from scripts.models.stock_to_flow import StockToFlowModel

        assert StockToFlowModel.HALVING_BLOCKS == 210_000
        assert StockToFlowModel.INITIAL_REWARD == 50.0

    def test_calculate_supply_at_height(self):
        """StockToFlowModel calculates supply correctly."""
        from scripts.models.stock_to_flow import StockToFlowModel

        model = StockToFlowModel()

        # Before first halving (height < 210000)
        supply = model._calculate_supply(100_000)
        expected = 100_000 * 50  # 5,000,000 BTC
        assert abs(supply - expected) < 1

        # After first halving
        supply = model._calculate_supply(420_000)
        # 210,000 * 50 + 210,000 * 25 = 10.5M + 5.25M = 15.75M
        expected = 210_000 * 50 + 210_000 * 25
        assert abs(supply - expected) < 1

    def test_calculate_annual_issuance(self):
        """StockToFlowModel calculates annual issuance correctly."""
        from scripts.models.stock_to_flow import StockToFlowModel

        model = StockToFlowModel()

        # Before first halving: 50 BTC * 144 blocks/day * 365 days
        issuance = model._calculate_annual_issuance(100_000)
        expected = 50 * 144 * 365
        assert abs(issuance - expected) < 100  # Allow small variance

        # After second halving (420_000 > 2*210_000): 12.5 BTC * 144 * 365
        issuance = model._calculate_annual_issuance(420_000)
        expected = 12.5 * 144 * 365
        assert abs(issuance - expected) < 100

    def test_calculate_s2f(self):
        """StockToFlowModel calculates S2F ratio correctly."""
        from scripts.models.stock_to_flow import StockToFlowModel

        model = StockToFlowModel()

        # S2F = supply / annual_issuance
        s2f = model.calculate_s2f(100_000)
        assert s2f > 0

        # S2F should increase after halving
        s2f_before = model.calculate_s2f(200_000)
        s2f_after = model.calculate_s2f(220_000)
        assert s2f_after > s2f_before

    def test_predict_returns_model_prediction(self):
        """StockToFlowModel.predict() returns ModelPrediction."""
        from scripts.models.stock_to_flow import StockToFlowModel

        model = StockToFlowModel()
        prediction = model.predict(date(2025, 12, 27))

        assert isinstance(prediction, ModelPrediction)
        assert prediction.model_name == "Stock-to-Flow"
        assert prediction.date == date(2025, 12, 27)
        assert prediction.predicted_price > 0

    def test_predict_includes_s2f_metadata(self):
        """StockToFlowModel.predict() includes S2F in metadata."""
        from scripts.models.stock_to_flow import StockToFlowModel

        model = StockToFlowModel()
        prediction = model.predict(date(2025, 12, 27))

        assert "s2f" in prediction.metadata

    def test_is_fitted_without_fit(self):
        """StockToFlowModel.is_fitted() returns True (uses default coefficients)."""
        from scripts.models.stock_to_flow import StockToFlowModel

        model = StockToFlowModel()
        # Uses default PlanB coefficients
        assert model.is_fitted() is True

    def test_fit_calibrates_model(self):
        """StockToFlowModel.fit() calibrates coefficients."""
        from scripts.models.stock_to_flow import StockToFlowModel

        model = StockToFlowModel()

        # Create sample data with block heights
        dates = pd.date_range(start="2020-01-01", periods=400, freq="D")
        block_heights = [600_000 + i * 144 for i in range(400)]
        prices = [10000 + i * 10 for i in range(400)]
        historical_data = pd.DataFrame(
            {"block_height": block_heights, "price": prices}, index=dates
        )

        model.fit(historical_data)
        assert model.is_fitted() is True
