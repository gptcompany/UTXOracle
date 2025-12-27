"""
Thermocap Model (spec-036 US3)

Thermocap = cumulative miner revenue (block rewards * price at time of mining)
Fair value is estimated as Thermocap * average multiple (3-8x range).
"""

from datetime import date

import pandas as pd

from scripts.models.base import ModelPrediction, PriceModel

# Genesis date
GENESIS_DATE = date(2009, 1, 3)

# Average blocks per day
BLOCKS_PER_DAY = 144


class ThermocapModel(PriceModel):
    """Thermocap multiple valuation model."""

    # Thermocap multiple fair value range
    FAIR_MULTIPLE_LOW = 3.0
    FAIR_MULTIPLE_HIGH = 8.0

    # Default thermocap estimate (as of late 2025)
    # Approximation: ~19.5M BTC mined * ~$15K average price
    DEFAULT_THERMOCAP = 300_000_000_000  # $300B

    # Current supply approximation
    DEFAULT_SUPPLY = 19_500_000  # BTC

    def __init__(self):
        self._thermocap = self.DEFAULT_THERMOCAP
        self._current_supply = self.DEFAULT_SUPPLY
        self._fitted = True  # Uses default estimates

    @property
    def name(self) -> str:
        return "Thermocap"

    @property
    def description(self) -> str:
        return "Thermocap multiple valuation (miner revenue basis)"

    @property
    def required_data(self) -> list[str]:
        return ["thermocap", "market_cap"]

    def calculate_thermocap_multiple(
        self, market_cap: float, thermocap: float
    ) -> float:
        """Calculate thermocap multiple.

        Args:
            market_cap: Current market capitalization in USD
            thermocap: Cumulative miner revenue in USD

        Returns:
            Multiple (market_cap / thermocap)
        """
        if thermocap <= 0:
            return 0.0
        return market_cap / thermocap

    def fit(self, historical_data: pd.DataFrame) -> None:
        """Update thermocap estimate from data.

        Args:
            historical_data: DataFrame with 'thermocap' column

        Raises:
            ValueError: If thermocap value is non-positive
        """
        if "thermocap" in historical_data.columns:
            # Use latest thermocap value
            new_thermocap = historical_data["thermocap"].iloc[-1]
            # Check for NaN, Inf, or non-positive values
            if pd.isna(new_thermocap) or (
                isinstance(new_thermocap, float)
                and not __import__("math").isfinite(new_thermocap)
            ):
                raise ValueError(
                    f"Invalid thermocap value: {new_thermocap}. "
                    "Thermocap must be a finite positive number."
                )
            if new_thermocap <= 0:
                raise ValueError(
                    f"Invalid thermocap value: {new_thermocap}. "
                    "Thermocap must be positive."
                )
            self._thermocap = new_thermocap
        self._fitted = True

    def predict(self, target_date: date) -> ModelPrediction:
        """Generate thermocap-based fair value prediction.

        Args:
            target_date: Date to predict for

        Returns:
            ModelPrediction with fair value based on average multiple

        Raises:
            ValueError: If current supply or thermocap is zero/negative
        """
        # Guard against invalid values
        if self._current_supply <= 0:
            raise ValueError(
                f"Invalid current supply: {self._current_supply}. "
                "Supply must be positive for price calculation."
            )
        if self._thermocap <= 0:
            raise ValueError(
                f"Invalid thermocap: {self._thermocap}. "
                "Thermocap must be positive for price calculation."
            )

        # Fair value = thermocap * average_multiple
        avg_multiple = (self.FAIR_MULTIPLE_LOW + self.FAIR_MULTIPLE_HIGH) / 2
        fair_market_cap = self._thermocap * avg_multiple

        # Fair price = fair_market_cap / supply
        fair_price = fair_market_cap / self._current_supply

        # Confidence interval based on multiple range
        lower_price = (self._thermocap * self.FAIR_MULTIPLE_LOW) / self._current_supply
        upper_price = (self._thermocap * self.FAIR_MULTIPLE_HIGH) / self._current_supply

        # Current multiple (if we knew current price)
        # For now, use the average as the predicted price
        current_multiple = avg_multiple

        return ModelPrediction(
            model_name=self.name,
            date=target_date,
            predicted_price=float(fair_price),
            confidence_interval=(float(lower_price), float(upper_price)),
            confidence_level=0.90,  # Based on historical multiple range
            metadata={
                "thermocap_multiple": float(current_multiple),
                "thermocap": float(self._thermocap),
            },
        )
