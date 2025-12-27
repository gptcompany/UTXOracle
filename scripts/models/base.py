"""
Base classes for Custom Price Models Framework (spec-036 US1)

- ModelPrediction: Dataclass for unified prediction output
- PriceModel: Abstract base class for all price models
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd


@dataclass
class ModelPrediction:
    """Unified prediction output from any price model."""

    model_name: str
    date: date
    predicted_price: float
    confidence_interval: tuple[float, float]
    confidence_level: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert prediction to dictionary format for API responses."""
        return {
            "model_name": self.model_name,
            "date": self.date.isoformat(),
            "predicted_price": self.predicted_price,
            "confidence_interval": {
                "lower": self.confidence_interval[0],
                "upper": self.confidence_interval[1],
            },
            "confidence_level": self.confidence_level,
            "metadata": self.metadata,
        }


class PriceModel(ABC):
    """Abstract base class for all price models."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable model name (e.g., 'Power Law', 'Stock-to-Flow')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Model description and methodology."""
        ...

    @property
    @abstractmethod
    def required_data(self) -> list[str]:
        """List of required data sources (e.g., ['daily_prices', 'block_heights'])."""
        ...

    @abstractmethod
    def fit(self, historical_data: pd.DataFrame) -> None:
        """Train/calibrate model on historical data.

        Args:
            historical_data: DataFrame with 'date' index and columns per required_data
        """
        ...

    @abstractmethod
    def predict(self, target_date: date) -> ModelPrediction:
        """Generate prediction for target date.

        Args:
            target_date: Date to predict for

        Returns:
            ModelPrediction with price and confidence interval
        """
        ...

    def is_fitted(self) -> bool:
        """Check if model has been fitted.

        Subclasses should set self._fitted = True in fit() method.
        """
        return getattr(self, "_fitted", False)
