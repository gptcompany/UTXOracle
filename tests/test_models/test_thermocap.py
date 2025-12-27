"""
Tests for ThermocapModel (spec-036 US3).

TDD: These tests MUST FAIL before implementation (RED phase).
Run: uv run pytest tests/test_models/test_thermocap.py -v
"""

from datetime import date

import pandas as pd

from scripts.models.base import ModelPrediction, PriceModel


class TestThermocapModel:
    """Tests for Thermocap valuation model."""

    def test_implements_price_model_interface(self):
        """ThermocapModel implements PriceModel ABC."""
        from scripts.models.thermocap import ThermocapModel

        model = ThermocapModel()
        assert isinstance(model, PriceModel)

    def test_name_property(self):
        """ThermocapModel.name returns 'Thermocap'."""
        from scripts.models.thermocap import ThermocapModel

        model = ThermocapModel()
        assert model.name == "Thermocap"

    def test_description_property(self):
        """ThermocapModel.description describes the model."""
        from scripts.models.thermocap import ThermocapModel

        model = ThermocapModel()
        assert (
            "thermocap" in model.description.lower()
            or "miner" in model.description.lower()
        )

    def test_required_data_property(self):
        """ThermocapModel.required_data includes thermocap data."""
        from scripts.models.thermocap import ThermocapModel

        model = ThermocapModel()
        # Needs thermocap or miner revenue data
        assert len(model.required_data) > 0

    def test_fair_multiple_range_constants(self):
        """ThermocapModel has fair multiple range constants."""
        from scripts.models.thermocap import ThermocapModel

        assert ThermocapModel.FAIR_MULTIPLE_LOW == 3.0
        assert ThermocapModel.FAIR_MULTIPLE_HIGH == 8.0

    def test_calculate_thermocap_multiple(self):
        """ThermocapModel calculates thermocap multiple."""
        from scripts.models.thermocap import ThermocapModel

        model = ThermocapModel()

        # Example: market_cap = 1.8T, thermocap = 300B
        # Multiple = 1.8T / 300B = 6
        market_cap = 1_800_000_000_000  # $1.8T
        thermocap = 300_000_000_000  # $300B

        multiple = model.calculate_thermocap_multiple(market_cap, thermocap)
        assert abs(multiple - 6.0) < 0.1

    def test_predict_returns_model_prediction(self):
        """ThermocapModel.predict() returns ModelPrediction."""
        from scripts.models.thermocap import ThermocapModel

        model = ThermocapModel()
        prediction = model.predict(date(2025, 12, 27))

        assert isinstance(prediction, ModelPrediction)
        assert prediction.model_name == "Thermocap"
        assert prediction.date == date(2025, 12, 27)
        assert prediction.predicted_price > 0

    def test_predict_fair_value_range(self):
        """ThermocapModel.predict() returns fair value within 3-8x range."""
        from scripts.models.thermocap import ThermocapModel

        model = ThermocapModel()
        prediction = model.predict(date(2025, 12, 27))

        # Confidence interval should reflect the 3-8x range
        lower = prediction.confidence_interval[0]
        upper = prediction.confidence_interval[1]
        assert lower < prediction.predicted_price < upper

    def test_predict_includes_multiple_metadata(self):
        """ThermocapModel.predict() includes thermocap multiple in metadata."""
        from scripts.models.thermocap import ThermocapModel

        model = ThermocapModel()
        prediction = model.predict(date(2025, 12, 27))

        assert (
            "thermocap_multiple" in prediction.metadata
            or "multiple" in prediction.metadata
        )

    def test_is_fitted(self):
        """ThermocapModel.is_fitted() returns True (simple calculation model)."""
        from scripts.models.thermocap import ThermocapModel

        model = ThermocapModel()
        # Thermocap model doesn't need fitting - it's a simple multiple calculation
        assert model.is_fitted() is True

    def test_fit_updates_thermocap_data(self):
        """ThermocapModel.fit() stores thermocap data for predictions."""
        from scripts.models.thermocap import ThermocapModel

        model = ThermocapModel()

        # Sample data
        dates = pd.date_range(start="2020-01-01", periods=100, freq="D")
        data = pd.DataFrame(
            {
                "thermocap": [300_000_000_000 + i * 1e9 for i in range(100)],
                "market_cap": [1_500_000_000_000 + i * 2e9 for i in range(100)],
            },
            index=dates,
        )

        model.fit(data)
        assert model.is_fitted() is True
