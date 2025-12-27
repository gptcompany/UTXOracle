"""
Stock-to-Flow Model (spec-036 US3)

Implements S2F valuation based on Bitcoin's scarcity (supply/flow ratio).
Uses PlanB's original S2F model coefficients by default.
"""

from datetime import date

import numpy as np
import pandas as pd

from scripts.models.base import ModelPrediction, PriceModel

# Genesis date for block height calculations
GENESIS_DATE = date(2009, 1, 3)

# Average blocks per day (10 min per block)
BLOCKS_PER_DAY = 144


class StockToFlowModel(PriceModel):
    """Stock-to-Flow scarcity model for Bitcoin valuation."""

    # Bitcoin halving schedule
    HALVING_BLOCKS = 210_000
    INITIAL_REWARD = 50.0

    # PlanB's original S2F model coefficients
    # Price = exp(intercept + slope * ln(S2F))
    DEFAULT_INTERCEPT = -1.84
    DEFAULT_SLOPE = 3.36

    def __init__(self):
        self._intercept = self.DEFAULT_INTERCEPT
        self._slope = self.DEFAULT_SLOPE
        self._fitted = True  # Uses default coefficients

    @property
    def name(self) -> str:
        return "Stock-to-Flow"

    @property
    def description(self) -> str:
        return "Stock-to-Flow scarcity model (S2F)"

    @property
    def required_data(self) -> list[str]:
        return ["block_heights", "daily_prices"]

    def _get_block_reward(self, block_height: int) -> float:
        """Get block reward for given height."""
        halvings = block_height // self.HALVING_BLOCKS
        return self.INITIAL_REWARD / (2**halvings)

    def _calculate_supply(self, block_height: int) -> float:
        """Calculate total Bitcoin supply at given block height."""
        supply = 0.0
        remaining_blocks = block_height

        reward = self.INITIAL_REWARD
        while remaining_blocks > 0:
            blocks_in_era = min(remaining_blocks, self.HALVING_BLOCKS)
            era_start = block_height - remaining_blocks

            # How many blocks left until next halving?
            blocks_to_halving = self.HALVING_BLOCKS - (era_start % self.HALVING_BLOCKS)
            blocks_in_this_era = min(blocks_in_era, blocks_to_halving)

            supply += blocks_in_this_era * reward
            remaining_blocks -= blocks_in_this_era

            # Update reward for next iteration
            if remaining_blocks > 0:
                current_era = (block_height - remaining_blocks) // self.HALVING_BLOCKS
                reward = self.INITIAL_REWARD / (2**current_era)

        return supply

    def _calculate_annual_issuance(self, block_height: int) -> float:
        """Calculate annual Bitcoin issuance at given block height."""
        reward = self._get_block_reward(block_height)
        # 144 blocks per day * 365 days
        return reward * BLOCKS_PER_DAY * 365

    def calculate_s2f(self, block_height: int) -> float:
        """Calculate Stock-to-Flow ratio at given block height."""
        supply = self._calculate_supply(block_height)
        annual_issuance = self._calculate_annual_issuance(block_height)

        if annual_issuance == 0:
            return float("inf")  # After all BTC mined

        return supply / annual_issuance

    def _date_to_block_height(self, target_date: date) -> int:
        """Estimate block height for a given date.

        Args:
            target_date: Target date (can be date or pd.Timestamp)

        Returns:
            Estimated block height
        """
        # Handle pandas Timestamp by converting to date
        if hasattr(target_date, "date"):
            target_date = target_date.date()
        days_since_genesis = (target_date - GENESIS_DATE).days
        return days_since_genesis * BLOCKS_PER_DAY

    def fit(self, historical_data: pd.DataFrame) -> None:
        """Fit S2F model from historical data.

        Args:
            historical_data: DataFrame with 'block_height' and 'price' columns
        """
        if "block_height" not in historical_data.columns:
            # Estimate block heights from dates
            heights = [self._date_to_block_height(d) for d in historical_data.index]
        else:
            heights = historical_data["block_height"].tolist()

        prices = historical_data["price"].tolist()

        # Calculate S2F for each height
        s2f_values = [self.calculate_s2f(h) for h in heights]

        # Log-linear regression: ln(price) = intercept + slope * ln(S2F)
        valid_data = [(s, p) for s, p in zip(s2f_values, prices) if s > 0 and p > 0]
        if len(valid_data) < 10:
            # Not enough data, keep defaults
            return

        log_s2f = np.log([d[0] for d in valid_data])
        log_price = np.log([d[1] for d in valid_data])

        # Simple linear regression
        n = len(log_s2f)
        sum_x = np.sum(log_s2f)
        sum_y = np.sum(log_price)
        sum_xy = np.sum(log_s2f * log_price)
        sum_x2 = np.sum(log_s2f**2)

        denominator = n * sum_x2 - sum_x**2
        if abs(denominator) < 1e-9:
            return  # Can't fit

        self._slope = (n * sum_xy - sum_x * sum_y) / denominator
        self._intercept = (sum_y - self._slope * sum_x) / n
        self._fitted = True

    def predict(self, target_date: date) -> ModelPrediction:
        """Generate S2F-based price prediction.

        Args:
            target_date: Date to predict for

        Returns:
            ModelPrediction with S2F fair value

        Raises:
            ValueError: If target date is before Bitcoin genesis (2009-01-03)
        """
        block_height = self._date_to_block_height(target_date)

        # Validate date is after genesis
        if block_height <= 0:
            raise ValueError(
                f"Target date {target_date} is before Bitcoin genesis "
                f"(2009-01-03). Cannot calculate S2F for pre-genesis dates."
            )

        s2f = self.calculate_s2f(block_height)

        # Guard against log(0) - should not happen if block_height > 0
        if s2f <= 0:
            raise ValueError(
                f"Invalid S2F ratio {s2f} at block height {block_height}. "
                "S2F must be positive for price calculation."
            )

        # Price = exp(intercept + slope * ln(S2F))
        log_price = self._intercept + self._slope * np.log(s2f)
        fair_value = np.exp(log_price)

        # Confidence interval based on historical model fit (~0.5 in log space)
        log_std = 0.5
        lower_band = np.exp(log_price - log_std)
        upper_band = np.exp(log_price + log_std)

        return ModelPrediction(
            model_name=self.name,
            date=target_date,
            predicted_price=float(fair_value),
            confidence_interval=(float(lower_band), float(upper_band)),
            confidence_level=0.68,
            metadata={
                "s2f": float(s2f),
                "block_height": block_height,
            },
        )
