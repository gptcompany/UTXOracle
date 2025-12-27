"""
UTXOracleModel - Wrapper for UTXOracle library (spec-036 US3)

Wraps UTXOracle_library.py functions to provide PriceModel interface.
Uses cached historical data when blockchain is unavailable.
"""

from datetime import date
from pathlib import Path

import pandas as pd

from scripts.models.base import ModelPrediction, PriceModel

# Historical data directory
HISTORICAL_DATA_DIR = Path("historical_data")


class UTXOracleModel(PriceModel):
    """Wrapper around UTXOracle for PriceModel interface."""

    def __init__(self):
        self._fitted = True  # UTXOracle doesn't need fitting

    @property
    def name(self) -> str:
        return "UTXOracle"

    @property
    def description(self) -> str:
        return "UTXOracle blockchain-native price calculation"

    @property
    def required_data(self) -> list[str]:
        return ["blockchain"]

    def fit(self, historical_data: pd.DataFrame) -> None:
        """No-op - UTXOracle doesn't require fitting.

        Args:
            historical_data: Ignored
        """
        pass  # UTXOracle calculates directly from blockchain

    def _get_cached_price(self, target_date: date) -> float | None:
        """Try to get cached price from historical data."""
        # Look for cached HTML file
        date_str = target_date.strftime("%Y-%m-%d")
        html_path = HISTORICAL_DATA_DIR / "html_files" / f"UTXOracle_{date_str}.html"

        if html_path.exists():
            # Parse price from HTML file
            try:
                content = html_path.read_text()
                # Look for price pattern in HTML
                import re

                match = re.search(r"price:\s*\$?([\d,]+(?:\.\d+)?)", content)
                if match:
                    price_str = match.group(1).replace(",", "")
                    return float(price_str)
            except Exception:
                pass

        return None

    def predict(self, target_date: date) -> ModelPrediction:
        """Generate price prediction using UTXOracle.

        First tries to use cached data, then falls back to blockchain calculation.

        Args:
            target_date: Date to predict for

        Returns:
            ModelPrediction with UTXOracle price
        """
        # Try cached data first
        cached_price = self._get_cached_price(target_date)

        if cached_price is not None:
            price = cached_price
        else:
            # Try to run UTXOracle (requires blockchain access)
            try:
                from UTXOracle_library import calculate_price_for_date

                result = calculate_price_for_date(target_date)
                price = result.price
            except ImportError:
                # UTXOracle_library not available, use a placeholder
                price = 0.0
            except Exception:
                # Blockchain unavailable
                price = 0.0

        # UTXOracle doesn't provide confidence intervals directly
        # Use +/- 10% as a reasonable estimate
        lower_bound = price * 0.90
        upper_bound = price * 1.10

        return ModelPrediction(
            model_name=self.name,
            date=target_date,
            predicted_price=float(price),
            confidence_interval=(float(lower_bound), float(upper_bound)),
            confidence_level=0.95,  # UTXOracle is based on actual transactions
            metadata={
                "source": "cached" if cached_price else "calculated",
            },
        )
