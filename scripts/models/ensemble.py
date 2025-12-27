"""
EnsembleModel - Combines multiple models for ensemble predictions (spec-036 US4)

Supports multiple aggregation methods:
- weighted_avg: Weighted average of predictions
- median: Median of predictions
- min: Minimum prediction (conservative)
- max: Maximum prediction (optimistic)
"""

from dataclasses import dataclass
from datetime import date
from typing import Callable

import numpy as np
import pandas as pd

from scripts.models.base import ModelPrediction, PriceModel
from scripts.models.registry import ModelRegistry


@dataclass
class EnsembleConfig:
    """Configuration for ensemble model."""

    models: list[str]  # Model names from registry
    weights: list[float]  # Must sum to 1.0
    aggregation: str  # "weighted_avg" | "median" | "min" | "max"

    def __post_init__(self):
        # Validate models and weights have same length
        if len(self.models) != len(self.weights):
            raise ValueError(
                f"models and weights must have same length: "
                f"{len(self.models)} models vs {len(self.weights)} weights"
            )

        # Validate weights sum to 1.0
        if not np.isclose(sum(self.weights), 1.0):
            raise ValueError(f"weights must sum to 1.0, got {sum(self.weights)}")

        # Validate aggregation method
        valid_aggregations = {"weighted_avg", "median", "min", "max"}
        if self.aggregation not in valid_aggregations:
            raise ValueError(
                f"Unknown aggregation: {self.aggregation}. "
                f"Valid options: {valid_aggregations}"
            )


class EnsembleModel(PriceModel):
    """Combines multiple models for ensemble predictions."""

    # Aggregation functions
    AGGREGATIONS: dict[str, Callable[[list[float], list[float]], float]] = {
        "weighted_avg": lambda prices, weights: sum(
            p * w for p, w in zip(prices, weights)
        ),
        "median": lambda prices, _: float(np.median(prices)),
        "min": lambda prices, _: min(prices),
        "max": lambda prices, _: max(prices),
    }

    def __init__(self, config: EnsembleConfig):
        """Initialize ensemble with configuration.

        Args:
            config: EnsembleConfig specifying models, weights, and aggregation
        """
        self._config = config
        self._sub_models: list[PriceModel] = []

        # Create sub-model instances from registry
        for model_name in config.models:
            model = ModelRegistry.create(model_name)
            self._sub_models.append(model)

        self._aggregation_fn = self.AGGREGATIONS[config.aggregation]
        self._fitted = True  # Sub-models handle fitting

    @property
    def name(self) -> str:
        return "Ensemble"

    @property
    def description(self) -> str:
        models_str = ", ".join(self._config.models)
        return f"Ensemble of {models_str} ({self._config.aggregation})"

    @property
    def required_data(self) -> list[str]:
        # Combine required data from all sub-models
        required = set()
        for model in self._sub_models:
            required.update(model.required_data)
        return list(required)

    def fit(self, historical_data: pd.DataFrame) -> None:
        """Fit all sub-models on historical data.

        Args:
            historical_data: DataFrame with data for all sub-models
        """
        for model in self._sub_models:
            model.fit(historical_data)
        self._fitted = True

    def is_fitted(self) -> bool:
        """Check if all sub-models are fitted."""
        return all(model.is_fitted() for model in self._sub_models)

    def predict(self, target_date: date) -> ModelPrediction:
        """Generate ensemble prediction for target date.

        Args:
            target_date: Date to predict for

        Returns:
            ModelPrediction with aggregated price
        """
        # Get predictions from all sub-models
        sub_predictions: list[ModelPrediction] = []
        prices: list[float] = []

        for model in self._sub_models:
            pred = model.predict(target_date)
            sub_predictions.append(pred)
            prices.append(pred.predicted_price)

        # Aggregate prices
        aggregated_price = self._aggregation_fn(prices, self._config.weights)

        # Calculate confidence interval from sub-model intervals
        all_lowers = [p.confidence_interval[0] for p in sub_predictions]
        all_uppers = [p.confidence_interval[1] for p in sub_predictions]

        # Use weighted average for bounds or min/max depending on aggregation
        if self._config.aggregation == "weighted_avg":
            lower = self._aggregation_fn(all_lowers, self._config.weights)
            upper = self._aggregation_fn(all_uppers, self._config.weights)
        elif self._config.aggregation == "min":
            lower = min(all_lowers)
            upper = min(all_uppers)
        elif self._config.aggregation == "max":
            lower = max(all_lowers)
            upper = max(all_uppers)
        else:  # median
            lower = float(np.median(all_lowers))
            upper = float(np.median(all_uppers))

        # Average confidence level
        avg_confidence = sum(p.confidence_level for p in sub_predictions) / len(
            sub_predictions
        )

        return ModelPrediction(
            model_name=self.name,
            date=target_date,
            predicted_price=float(aggregated_price),
            confidence_interval=(float(lower), float(upper)),
            confidence_level=avg_confidence,
            metadata={
                "aggregation": self._config.aggregation,
                "sub_predictions": {
                    p.model_name: p.predicted_price for p in sub_predictions
                },
            },
        )
