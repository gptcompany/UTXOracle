"""
PowerLawAdapter - Wraps spec-034 Power Law model (spec-036 US3)

Adapts existing price_power_law.py to PriceModel interface.
"""

from datetime import date

import pandas as pd

from scripts.models.base import ModelPrediction, PriceModel
from scripts.models.price_power_law import (
    DEFAULT_MODEL,
    fit_power_law,
    predict_price,
)


class PowerLawAdapter(PriceModel):
    """Adapts spec-034 Power Law to PriceModel interface."""

    def __init__(self):
        self._model = DEFAULT_MODEL
        self._fitted = True  # Default model is pre-fitted

    @property
    def name(self) -> str:
        return "Power Law"

    @property
    def description(self) -> str:
        return "Bitcoin price power law model (spec-034)"

    @property
    def required_data(self) -> list[str]:
        return ["daily_prices"]

    def fit(self, historical_data: pd.DataFrame) -> None:
        """Fit power law model from historical price data.

        Args:
            historical_data: DataFrame with 'price' column and date index
        """
        # Convert Timestamps to date objects
        dates = [
            d.date() if hasattr(d, "date") else d
            for d in historical_data.index.tolist()
        ]
        prices = historical_data["price"].tolist()

        self._model = fit_power_law(dates, prices)
        self._fitted = True

    def predict(self, target_date: date) -> ModelPrediction:
        """Generate prediction for target date.

        Args:
            target_date: Date to predict for

        Returns:
            ModelPrediction with fair value and confidence bands
        """
        result = predict_price(self._model, target_date)

        return ModelPrediction(
            model_name=self.name,
            date=target_date,
            predicted_price=result.fair_value,
            confidence_interval=(result.lower_band, result.upper_band),
            confidence_level=0.68,  # 1 sigma
            metadata={
                "zone": result.zone,
                "days_since_genesis": result.days_since_genesis,
            },
        )
