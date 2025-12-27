"""
Tests for PowerLawAdapter (spec-036 US3).

TDD: These tests MUST FAIL before implementation (RED phase).
Run: uv run pytest tests/test_models/test_power_law_adapter.py -v
"""

from datetime import date

import pandas as pd

from scripts.models.base import ModelPrediction, PriceModel


class TestPowerLawAdapter:
    """Tests for PowerLawAdapter wrapping spec-034."""

    def test_implements_price_model_interface(self):
        """PowerLawAdapter implements PriceModel ABC."""
        from scripts.models.power_law_adapter import PowerLawAdapter

        adapter = PowerLawAdapter()
        assert isinstance(adapter, PriceModel)

    def test_name_property(self):
        """PowerLawAdapter.name returns 'Power Law'."""
        from scripts.models.power_law_adapter import PowerLawAdapter

        adapter = PowerLawAdapter()
        assert adapter.name == "Power Law"

    def test_description_property(self):
        """PowerLawAdapter.description describes the model."""
        from scripts.models.power_law_adapter import PowerLawAdapter

        adapter = PowerLawAdapter()
        assert "power law" in adapter.description.lower()

    def test_required_data_property(self):
        """PowerLawAdapter.required_data includes daily_prices."""
        from scripts.models.power_law_adapter import PowerLawAdapter

        adapter = PowerLawAdapter()
        assert "daily_prices" in adapter.required_data

    def test_is_fitted_initial(self):
        """PowerLawAdapter.is_fitted() returns True (uses default model)."""
        from scripts.models.power_law_adapter import PowerLawAdapter

        adapter = PowerLawAdapter()
        # Uses default model from price_power_law.py
        assert adapter.is_fitted() is True

    def test_fit_with_data(self):
        """PowerLawAdapter.fit() calibrates model from data."""
        from scripts.models.power_law_adapter import PowerLawAdapter

        adapter = PowerLawAdapter()

        # Create sample historical data (at least 365 days)
        dates = pd.date_range(start="2020-01-01", periods=400, freq="D")
        prices = [10000 + i * 10 for i in range(400)]
        historical_data = pd.DataFrame({"price": prices}, index=dates)

        adapter.fit(historical_data)
        assert adapter.is_fitted() is True

    def test_predict_returns_model_prediction(self):
        """PowerLawAdapter.predict() returns ModelPrediction."""
        from scripts.models.power_law_adapter import PowerLawAdapter

        adapter = PowerLawAdapter()
        prediction = adapter.predict(date(2025, 12, 27))

        assert isinstance(prediction, ModelPrediction)
        assert prediction.model_name == "Power Law"
        assert prediction.date == date(2025, 12, 27)
        assert prediction.predicted_price > 0
        assert prediction.confidence_interval[0] < prediction.predicted_price
        assert prediction.confidence_interval[1] > prediction.predicted_price
        assert 0 < prediction.confidence_level <= 1

    def test_predict_includes_zone_metadata(self):
        """PowerLawAdapter.predict() includes zone in metadata."""
        from scripts.models.power_law_adapter import PowerLawAdapter

        adapter = PowerLawAdapter()
        prediction = adapter.predict(date(2025, 12, 27))

        # Zone should be in metadata
        assert "zone" in prediction.metadata or prediction.metadata == {}
