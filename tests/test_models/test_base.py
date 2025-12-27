"""
Contract tests for PriceModel ABC and ModelPrediction dataclass (spec-036 US1).

TDD: These tests MUST FAIL before implementation (RED phase).
Run: uv run pytest tests/test_models/test_base.py -v
"""

from abc import ABC
from datetime import date

import pytest


class TestModelPrediction:
    """Tests for ModelPrediction dataclass."""

    def test_create_valid_prediction(self):
        """ModelPrediction can be created with valid data."""
        from scripts.models.base import ModelPrediction

        prediction = ModelPrediction(
            model_name="Test Model",
            date=date(2025, 12, 27),
            predicted_price=100000.0,
            confidence_interval=(80000.0, 120000.0),
            confidence_level=0.68,
            metadata={"test": True},
        )

        assert prediction.model_name == "Test Model"
        assert prediction.date == date(2025, 12, 27)
        assert prediction.predicted_price == 100000.0
        assert prediction.confidence_interval == (80000.0, 120000.0)
        assert prediction.confidence_level == 0.68
        assert prediction.metadata == {"test": True}

    def test_prediction_to_dict(self):
        """ModelPrediction.to_dict() returns proper dictionary format."""
        from scripts.models.base import ModelPrediction

        prediction = ModelPrediction(
            model_name="Test Model",
            date=date(2025, 12, 27),
            predicted_price=100000.0,
            confidence_interval=(80000.0, 120000.0),
            confidence_level=0.68,
            metadata={"zone": "fair"},
        )

        result = prediction.to_dict()

        assert result["model_name"] == "Test Model"
        assert result["date"] == "2025-12-27"
        assert result["predicted_price"] == 100000.0
        assert result["confidence_interval"]["lower"] == 80000.0
        assert result["confidence_interval"]["upper"] == 120000.0
        assert result["confidence_level"] == 0.68
        assert result["metadata"]["zone"] == "fair"

    def test_prediction_default_metadata(self):
        """ModelPrediction defaults to empty metadata dict."""
        from scripts.models.base import ModelPrediction

        prediction = ModelPrediction(
            model_name="Test Model",
            date=date(2025, 12, 27),
            predicted_price=100000.0,
            confidence_interval=(80000.0, 120000.0),
            confidence_level=0.68,
        )

        assert prediction.metadata == {}


class TestPriceModelABC:
    """Tests for PriceModel abstract base class."""

    def test_pricemodel_is_abstract(self):
        """PriceModel cannot be instantiated directly."""
        from scripts.models.base import PriceModel

        assert issubclass(PriceModel, ABC)

        with pytest.raises(TypeError, match="abstract"):
            PriceModel()

    def test_concrete_implementation_required(self):
        """Concrete implementations must implement all abstract methods."""
        from scripts.models.base import PriceModel

        # Incomplete implementation (missing methods)
        class IncompletePriceModel(PriceModel):
            pass

        with pytest.raises(TypeError, match="abstract"):
            IncompletePriceModel()

    def test_complete_implementation_works(self):
        """Complete implementations can be instantiated."""
        from scripts.models.base import ModelPrediction, PriceModel

        class CompletePriceModel(PriceModel):
            @property
            def name(self) -> str:
                return "Test Model"

            @property
            def description(self) -> str:
                return "A test model"

            @property
            def required_data(self) -> list[str]:
                return ["daily_prices"]

            def fit(self, historical_data) -> None:
                self._fitted = True

            def predict(self, target_date: date) -> ModelPrediction:
                return ModelPrediction(
                    model_name=self.name,
                    date=target_date,
                    predicted_price=100000.0,
                    confidence_interval=(80000.0, 120000.0),
                    confidence_level=0.68,
                )

        model = CompletePriceModel()
        assert model.name == "Test Model"
        assert model.description == "A test model"
        assert model.required_data == ["daily_prices"]

    def test_is_fitted_before_fit(self):
        """is_fitted() returns False before fit() is called."""
        from scripts.models.base import ModelPrediction, PriceModel

        class TestModel(PriceModel):
            def __init__(self):
                self._fitted = False

            @property
            def name(self) -> str:
                return "Test"

            @property
            def description(self) -> str:
                return "Test"

            @property
            def required_data(self) -> list[str]:
                return []

            def fit(self, historical_data) -> None:
                self._fitted = True

            def predict(self, target_date: date) -> ModelPrediction:
                return ModelPrediction(
                    model_name=self.name,
                    date=target_date,
                    predicted_price=100000.0,
                    confidence_interval=(80000.0, 120000.0),
                    confidence_level=0.68,
                )

        model = TestModel()
        assert model.is_fitted() is False

    def test_is_fitted_after_fit(self):
        """is_fitted() returns True after fit() is called."""
        from scripts.models.base import ModelPrediction, PriceModel

        class TestModel(PriceModel):
            def __init__(self):
                self._fitted = False

            @property
            def name(self) -> str:
                return "Test"

            @property
            def description(self) -> str:
                return "Test"

            @property
            def required_data(self) -> list[str]:
                return []

            def fit(self, historical_data) -> None:
                self._fitted = True

            def predict(self, target_date: date) -> ModelPrediction:
                return ModelPrediction(
                    model_name=self.name,
                    date=target_date,
                    predicted_price=100000.0,
                    confidence_interval=(80000.0, 120000.0),
                    confidence_level=0.68,
                )

        model = TestModel()
        model.fit(None)  # Simulate fitting
        assert model.is_fitted() is True

    def test_abstract_properties(self):
        """PriceModel has abstract properties: name, description, required_data."""
        from scripts.models.base import PriceModel

        # Check abstract methods/properties exist
        abstract_methods = PriceModel.__abstractmethods__
        assert "name" in abstract_methods or hasattr(PriceModel.name, "fget")
        assert "description" in abstract_methods or hasattr(
            PriceModel.description, "fget"
        )
        assert "required_data" in abstract_methods or hasattr(
            PriceModel.required_data, "fget"
        )

    def test_abstract_methods(self):
        """PriceModel has abstract methods: fit, predict."""
        from scripts.models.base import PriceModel

        abstract_methods = PriceModel.__abstractmethods__
        assert "fit" in abstract_methods
        assert "predict" in abstract_methods
