"""
Tests for EnsembleConfig and EnsembleModel (spec-036 US4).

TDD: These tests MUST FAIL before implementation (RED phase).
Run: uv run pytest tests/test_models/test_ensemble.py -v
"""

from datetime import date

import pytest

from scripts.models.base import ModelPrediction, PriceModel


class TestEnsembleConfig:
    """Tests for EnsembleConfig dataclass."""

    def test_create_valid_config(self):
        """EnsembleConfig can be created with valid data."""
        from scripts.models.ensemble import EnsembleConfig

        config = EnsembleConfig(
            models=["Power Law", "Stock-to-Flow"],
            weights=[0.6, 0.4],
            aggregation="weighted_avg",
        )

        assert config.models == ["Power Law", "Stock-to-Flow"]
        assert config.weights == [0.6, 0.4]
        assert config.aggregation == "weighted_avg"

    def test_weights_must_sum_to_one(self):
        """EnsembleConfig raises ValueError if weights don't sum to 1.0."""
        from scripts.models.ensemble import EnsembleConfig

        with pytest.raises(ValueError, match="sum to 1.0"):
            EnsembleConfig(
                models=["Power Law", "Stock-to-Flow"],
                weights=[0.5, 0.3],  # Sum = 0.8
                aggregation="weighted_avg",
            )

    def test_models_weights_length_match(self):
        """EnsembleConfig raises ValueError if models/weights length mismatch."""
        from scripts.models.ensemble import EnsembleConfig

        with pytest.raises(ValueError, match="same length"):
            EnsembleConfig(
                models=["Power Law", "Stock-to-Flow", "Thermocap"],
                weights=[0.5, 0.5],  # Only 2 weights for 3 models
                aggregation="weighted_avg",
            )

    def test_invalid_aggregation(self):
        """EnsembleConfig raises ValueError for unknown aggregation."""
        from scripts.models.ensemble import EnsembleConfig

        with pytest.raises(ValueError, match="aggregation"):
            EnsembleConfig(
                models=["Power Law", "Stock-to-Flow"],
                weights=[0.5, 0.5],
                aggregation="invalid_method",
            )


class TestEnsembleModel:
    """Tests for EnsembleModel class."""

    def test_implements_price_model_interface(self):
        """EnsembleModel implements PriceModel ABC."""
        from scripts.models.ensemble import EnsembleConfig, EnsembleModel

        config = EnsembleConfig(
            models=["Power Law", "Stock-to-Flow"],
            weights=[0.5, 0.5],
            aggregation="weighted_avg",
        )
        model = EnsembleModel(config)

        assert isinstance(model, PriceModel)

    def test_name_property(self):
        """EnsembleModel.name returns 'Ensemble'."""
        from scripts.models.ensemble import EnsembleConfig, EnsembleModel

        config = EnsembleConfig(
            models=["Power Law", "Stock-to-Flow"],
            weights=[0.5, 0.5],
            aggregation="weighted_avg",
        )
        model = EnsembleModel(config)

        assert model.name == "Ensemble"

    def test_weighted_avg_aggregation(self):
        """EnsembleModel aggregates predictions with weighted average."""
        from scripts.models.ensemble import EnsembleConfig, EnsembleModel

        config = EnsembleConfig(
            models=["Power Law", "Stock-to-Flow"],
            weights=[0.6, 0.4],
            aggregation="weighted_avg",
        )
        model = EnsembleModel(config)

        prediction = model.predict(date(2025, 12, 27))

        # Should return a valid prediction
        assert isinstance(prediction, ModelPrediction)
        assert prediction.model_name == "Ensemble"
        assert prediction.predicted_price > 0

    def test_median_aggregation(self):
        """EnsembleModel aggregates predictions with median."""
        from scripts.models.ensemble import EnsembleConfig, EnsembleModel

        config = EnsembleConfig(
            models=["Power Law", "Stock-to-Flow", "Thermocap"],
            weights=[0.33, 0.33, 0.34],
            aggregation="median",
        )
        model = EnsembleModel(config)

        prediction = model.predict(date(2025, 12, 27))

        assert isinstance(prediction, ModelPrediction)
        assert prediction.predicted_price > 0

    def test_min_aggregation(self):
        """EnsembleModel aggregates predictions with min."""
        from scripts.models.ensemble import EnsembleConfig, EnsembleModel

        config = EnsembleConfig(
            models=["Power Law", "Stock-to-Flow"],
            weights=[0.5, 0.5],
            aggregation="min",
        )
        model = EnsembleModel(config)

        prediction = model.predict(date(2025, 12, 27))

        assert isinstance(prediction, ModelPrediction)
        assert prediction.predicted_price > 0

    def test_max_aggregation(self):
        """EnsembleModel aggregates predictions with max."""
        from scripts.models.ensemble import EnsembleConfig, EnsembleModel

        config = EnsembleConfig(
            models=["Power Law", "Stock-to-Flow"],
            weights=[0.5, 0.5],
            aggregation="max",
        )
        model = EnsembleModel(config)

        prediction = model.predict(date(2025, 12, 27))

        assert isinstance(prediction, ModelPrediction)
        assert prediction.predicted_price > 0

    def test_confidence_interval_calculation(self):
        """EnsembleModel calculates combined confidence interval."""
        from scripts.models.ensemble import EnsembleConfig, EnsembleModel

        config = EnsembleConfig(
            models=["Power Law", "Stock-to-Flow"],
            weights=[0.5, 0.5],
            aggregation="weighted_avg",
        )
        model = EnsembleModel(config)

        prediction = model.predict(date(2025, 12, 27))

        # Confidence interval should bound the predicted price
        lower, upper = prediction.confidence_interval
        assert lower < prediction.predicted_price < upper

    def test_is_fitted(self):
        """EnsembleModel.is_fitted() returns True when all sub-models fitted."""
        from scripts.models.ensemble import EnsembleConfig, EnsembleModel

        config = EnsembleConfig(
            models=["Power Law", "Stock-to-Flow"],
            weights=[0.5, 0.5],
            aggregation="weighted_avg",
        )
        model = EnsembleModel(config)

        # Built-in models are pre-fitted
        assert model.is_fitted() is True

    def test_metadata_includes_sub_predictions(self):
        """EnsembleModel.predict() includes sub-model predictions in metadata."""
        from scripts.models.ensemble import EnsembleConfig, EnsembleModel

        config = EnsembleConfig(
            models=["Power Law", "Stock-to-Flow"],
            weights=[0.5, 0.5],
            aggregation="weighted_avg",
        )
        model = EnsembleModel(config)

        prediction = model.predict(date(2025, 12, 27))

        assert "sub_predictions" in prediction.metadata
        assert len(prediction.metadata["sub_predictions"]) == 2
