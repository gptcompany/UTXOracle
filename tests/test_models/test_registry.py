"""
Tests for ModelRegistry (spec-036 US2).

TDD: These tests MUST FAIL before implementation (RED phase).
Run: uv run pytest tests/test_models/test_registry.py -v
"""

from datetime import date

import pytest

from scripts.models.base import ModelPrediction, PriceModel


# Create a test model class for registry testing
class DummyModel(PriceModel):
    """A dummy model for testing the registry."""

    @property
    def name(self) -> str:
        return "Dummy Model"

    @property
    def description(self) -> str:
        return "A dummy model for testing"

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


class TestModelRegistry:
    """Tests for ModelRegistry class."""

    def test_register_decorator(self):
        """ModelRegistry.register() decorator adds model to registry."""
        from scripts.models.registry import ModelRegistry

        # Clear any existing registrations
        ModelRegistry._models.clear()

        @ModelRegistry.register
        class TestModel(PriceModel):
            @property
            def name(self) -> str:
                return "Test Model"

            @property
            def description(self) -> str:
                return "Test"

            @property
            def required_data(self) -> list[str]:
                return []

            def fit(self, historical_data) -> None:
                pass

            def predict(self, target_date: date) -> ModelPrediction:
                return ModelPrediction(
                    model_name=self.name,
                    date=target_date,
                    predicted_price=100000.0,
                    confidence_interval=(80000.0, 120000.0),
                    confidence_level=0.68,
                )

        assert "Test Model" in ModelRegistry.list_models()

    def test_get_by_name(self):
        """ModelRegistry.get() returns model class by name."""
        from scripts.models.registry import ModelRegistry

        # Clear and register
        ModelRegistry._models.clear()
        ModelRegistry._models["Dummy Model"] = DummyModel

        model_class = ModelRegistry.get("Dummy Model")
        assert model_class is DummyModel

    def test_get_unknown_model_raises(self):
        """ModelRegistry.get() raises KeyError for unknown model."""
        from scripts.models.registry import ModelRegistry

        ModelRegistry._models.clear()

        with pytest.raises(KeyError, match="Unknown model"):
            ModelRegistry.get("NonexistentModel")

    def test_list_models(self):
        """ModelRegistry.list_models() returns list of registered names."""
        from scripts.models.registry import ModelRegistry

        ModelRegistry._models.clear()
        ModelRegistry._models["Model A"] = DummyModel
        ModelRegistry._models["Model B"] = DummyModel

        models = ModelRegistry.list_models()
        assert "Model A" in models
        assert "Model B" in models
        assert len(models) == 2

    def test_create_factory_method(self):
        """ModelRegistry.create() instantiates model with config."""
        from scripts.models.registry import ModelRegistry

        ModelRegistry._models.clear()
        ModelRegistry._models["Dummy Model"] = DummyModel

        model = ModelRegistry.create("Dummy Model")
        assert isinstance(model, DummyModel)
        assert model.name == "Dummy Model"

    def test_create_with_config(self):
        """ModelRegistry.create() passes config kwargs to model."""
        from scripts.models.registry import ModelRegistry

        class ConfigurableModel(PriceModel):
            def __init__(self, multiplier: float = 1.0):
                self.multiplier = multiplier
                self._fitted = False

            @property
            def name(self) -> str:
                return "Configurable"

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
                    predicted_price=100000.0 * self.multiplier,
                    confidence_interval=(80000.0, 120000.0),
                    confidence_level=0.68,
                )

        ModelRegistry._models.clear()
        ModelRegistry._models["Configurable"] = ConfigurableModel

        model = ModelRegistry.create("Configurable", multiplier=2.0)
        assert model.multiplier == 2.0

    def test_create_unknown_model_raises(self):
        """ModelRegistry.create() raises KeyError for unknown model."""
        from scripts.models.registry import ModelRegistry

        ModelRegistry._models.clear()

        with pytest.raises(KeyError, match="Unknown model"):
            ModelRegistry.create("NonexistentModel")
