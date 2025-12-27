"""
ModelBacktester - Walk-forward backtesting for price models (spec-036 US5)

Provides:
- ModelBacktestResult dataclass with metrics
- ModelBacktester class for running backtests
- Metrics: MAE, MAPE, RMSE, direction accuracy, Sharpe ratio, max drawdown
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from scripts.models.base import PriceModel


@dataclass
class ModelBacktestResult:
    """Backtesting results for a price model."""

    model_name: str
    start_date: date
    end_date: date
    predictions: int  # Number of predictions made
    mae: float  # Mean Absolute Error (USD)
    mape: float  # Mean Absolute Percentage Error (%)
    rmse: float  # Root Mean Square Error (USD)
    direction_accuracy: float  # % of correct up/down predictions
    sharpe_ratio: float  # Risk-adjusted metric
    max_drawdown: float  # Worst peak-to-trough (%)
    daily_results: pd.DataFrame  # Columns: date, predicted, actual, error, error_pct

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "model_name": self.model_name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "predictions": self.predictions,
            "metrics": {
                "mae": self.mae,
                "mape": self.mape,
                "rmse": self.rmse,
                "direction_accuracy": self.direction_accuracy,
                "sharpe_ratio": self.sharpe_ratio,
                "max_drawdown": self.max_drawdown,
            },
        }


class ModelBacktester:
    """Walk-forward backtester for PriceModel instances."""

    def __init__(self, train_pct: float = 0.7):
        """Initialize backtester.

        Args:
            train_pct: Fraction of data to use for training (0.0-1.0)
        """
        self.train_pct = train_pct

    def _calculate_mae(self, predictions: list[float], actuals: list[float]) -> float:
        """Calculate Mean Absolute Error."""
        errors = [abs(p - a) for p, a in zip(predictions, actuals)]
        return sum(errors) / len(errors) if errors else 0.0

    def _calculate_mape(self, predictions: list[float], actuals: list[float]) -> float:
        """Calculate Mean Absolute Percentage Error (%)."""
        pct_errors = [
            abs(p - a) / a * 100 for p, a in zip(predictions, actuals) if a > 0
        ]
        return sum(pct_errors) / len(pct_errors) if pct_errors else 0.0

    def _calculate_rmse(self, predictions: list[float], actuals: list[float]) -> float:
        """Calculate Root Mean Square Error."""
        squared_errors = [(p - a) ** 2 for p, a in zip(predictions, actuals)]
        mse = sum(squared_errors) / len(squared_errors) if squared_errors else 0.0
        return float(np.sqrt(mse))

    def _calculate_direction_accuracy(
        self, predictions: list[float], actuals: list[float]
    ) -> float:
        """Calculate fraction of correct direction predictions."""
        if len(predictions) < 2:
            return 0.0

        correct = 0
        total = 0

        for i in range(1, len(predictions)):
            pred_direction = predictions[i] - predictions[i - 1]
            actual_direction = actuals[i] - actuals[i - 1]

            # Both up or both down
            if (pred_direction > 0 and actual_direction > 0) or (
                pred_direction < 0 and actual_direction < 0
            ):
                correct += 1
            total += 1

        return correct / total if total > 0 else 0.0

    def _calculate_sharpe_ratio(
        self, predictions: list[float], actuals: list[float]
    ) -> float:
        """Calculate Sharpe ratio of prediction errors."""
        if len(predictions) < 2:
            return 0.0

        # Calculate returns based on prediction errors
        errors = [(p - a) / a for p, a in zip(predictions, actuals) if a > 0]
        if len(errors) < 2:
            return 0.0

        mean_error = np.mean(errors)
        std_error = np.std(errors)

        if std_error == 0:
            return 0.0

        # Annualized Sharpe (assuming daily data)
        return float(mean_error / std_error * np.sqrt(252))

    def _calculate_max_drawdown(self, actuals: list[float]) -> float:
        """Calculate maximum drawdown from peak (%)."""
        if len(actuals) < 2:
            return 0.0

        peak = actuals[0]
        max_dd = 0.0

        for price in actuals:
            if price > peak:
                peak = price
            drawdown = (peak - price) / peak * 100
            if drawdown > max_dd:
                max_dd = drawdown

        return -max_dd  # Return as negative

    def run(
        self,
        model: PriceModel,
        actual_prices: pd.Series,
        refit: bool = False,
    ) -> ModelBacktestResult:
        """Run walk-forward backtest on model.

        Args:
            model: PriceModel to backtest
            actual_prices: Series with datetime index and price values
            refit: Whether to refit model periodically (not implemented yet)

        Returns:
            ModelBacktestResult with metrics
        """
        # Split data
        n = len(actual_prices)
        train_end = int(n * self.train_pct)

        # Get test period dates
        test_dates = actual_prices.index[train_end:]
        test_actuals = actual_prices.iloc[train_end:].tolist()

        # Generate predictions
        predictions_list = []
        dates_list = []

        for dt in test_dates:
            # Convert Timestamp to date
            target_date = dt.date() if hasattr(dt, "date") else dt

            try:
                prediction = model.predict(target_date)
                predictions_list.append(prediction.predicted_price)
                dates_list.append(target_date)
            except Exception:
                # Skip dates where prediction fails
                continue

        # Align actuals with successful predictions
        actuals_aligned = test_actuals[: len(predictions_list)]

        # Calculate metrics
        mae = self._calculate_mae(predictions_list, actuals_aligned)
        mape = self._calculate_mape(predictions_list, actuals_aligned)
        rmse = self._calculate_rmse(predictions_list, actuals_aligned)
        direction_acc = self._calculate_direction_accuracy(
            predictions_list, actuals_aligned
        )
        sharpe = self._calculate_sharpe_ratio(predictions_list, actuals_aligned)
        max_dd = self._calculate_max_drawdown(actuals_aligned)

        # Build daily results DataFrame
        daily_results = pd.DataFrame(
            {
                "date": dates_list,
                "predicted": predictions_list,
                "actual": actuals_aligned,
                "error": [p - a for p, a in zip(predictions_list, actuals_aligned)],
                "error_pct": [
                    (p - a) / a * 100 if a > 0 else 0
                    for p, a in zip(predictions_list, actuals_aligned)
                ],
            }
        )

        return ModelBacktestResult(
            model_name=model.name,
            start_date=dates_list[0] if dates_list else date.today(),
            end_date=dates_list[-1] if dates_list else date.today(),
            predictions=len(predictions_list),
            mae=mae,
            mape=mape,
            rmse=rmse,
            direction_accuracy=direction_acc,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            daily_results=daily_results,
        )

    def compare_models(
        self,
        models: list[PriceModel],
        actual_prices: pd.Series,
    ) -> pd.DataFrame:
        """Compare multiple models and return ranking.

        Args:
            models: List of PriceModel instances
            actual_prices: Series with datetime index and price values

        Returns:
            DataFrame with model results, sorted by MAPE
        """
        results = []

        for model in models:
            result = self.run(model, actual_prices)
            results.append(
                {
                    "model_name": result.model_name,
                    "MAE": result.mae,
                    "MAPE": result.mape,
                    "RMSE": result.rmse,
                    "direction_accuracy": result.direction_accuracy,
                    "sharpe_ratio": result.sharpe_ratio,
                    "max_drawdown": result.max_drawdown,
                }
            )

        df = pd.DataFrame(results)
        return df.sort_values("MAPE").reset_index(drop=True)
