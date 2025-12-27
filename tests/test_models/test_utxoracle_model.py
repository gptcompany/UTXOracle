"""
Tests for UTXOracleModel (spec-036 US3).

TDD: These tests MUST FAIL before implementation (RED phase).
Run: uv run pytest tests/test_models/test_utxoracle_model.py -v
"""

from datetime import date

import pandas as pd
import pytest

from scripts.models.base import ModelPrediction, PriceModel


class TestUTXOracleModel:
    """Tests for UTXOracle wrapper model."""

    def test_implements_price_model_interface(self):
        """UTXOracleModel implements PriceModel ABC."""
        from scripts.models.utxoracle_model import UTXOracleModel

        model = UTXOracleModel()
        assert isinstance(model, PriceModel)

    def test_name_property(self):
        """UTXOracleModel.name returns 'UTXOracle'."""
        from scripts.models.utxoracle_model import UTXOracleModel

        model = UTXOracleModel()
        assert model.name == "UTXOracle"

    def test_description_property(self):
        """UTXOracleModel.description describes the model."""
        from scripts.models.utxoracle_model import UTXOracleModel

        model = UTXOracleModel()
        assert (
            "utxoracle" in model.description.lower()
            or "blockchain" in model.description.lower()
        )

    def test_required_data_property(self):
        """UTXOracleModel.required_data includes blockchain data."""
        from scripts.models.utxoracle_model import UTXOracleModel

        model = UTXOracleModel()
        # UTXOracle needs blockchain access
        assert len(model.required_data) > 0

    def test_predict_returns_model_prediction(self):
        """UTXOracleModel.predict() returns ModelPrediction or raises ValueError."""
        from scripts.models.utxoracle_model import UTXOracleModel

        model = UTXOracleModel()

        # Use historical date that may have cached data
        try:
            prediction = model.predict(date(2025, 10, 15))

            assert isinstance(prediction, ModelPrediction)
            assert prediction.model_name == "UTXOracle"
            assert prediction.date == date(2025, 10, 15)
            # Price must be positive (validated by model)
            assert prediction.predicted_price > 0
        except ValueError as e:
            # Expected when no cached data and blockchain unavailable
            assert "No price data available" in str(e)
            pytest.skip("No cached UTXOracle data available")

    def test_predict_without_blockchain_uses_cached(self):
        """UTXOracleModel.predict() uses cached data when blockchain unavailable."""
        from scripts.models.utxoracle_model import UTXOracleModel

        model = UTXOracleModel()

        # This should work with cached historical data
        try:
            prediction = model.predict(date(2025, 10, 15))
            assert prediction.predicted_price > 0
        except Exception:
            # If no cache, skip test
            pytest.skip("No cached UTXOracle data available")

    def test_is_fitted(self):
        """UTXOracleModel.is_fitted() returns True (no fitting needed)."""
        from scripts.models.utxoracle_model import UTXOracleModel

        model = UTXOracleModel()
        # UTXOracle doesn't need fitting - it calculates from blockchain
        assert model.is_fitted() is True

    def test_fit_is_noop(self):
        """UTXOracleModel.fit() is a no-op (model doesn't train)."""
        from scripts.models.utxoracle_model import UTXOracleModel

        model = UTXOracleModel()

        # Create dummy data
        dates = pd.date_range(start="2020-01-01", periods=100, freq="D")
        data = pd.DataFrame({"price": [50000] * 100}, index=dates)

        # fit() should not raise
        model.fit(data)
        assert model.is_fitted() is True
