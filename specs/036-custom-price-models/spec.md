# Spec-036: Custom Price Models Framework

## Overview

Create a flexible framework for implementing and comparing custom Bitcoin price models. Enables experimentation with various valuation approaches beyond the reference UTXOracle algorithm.

## Problem Statement

UTXOracle uses a specific clustering-based price discovery algorithm. However:
1. Multiple valuation models exist (power law, S2F, thermocap, etc.)
2. Users may want to combine models for ensemble predictions
3. Research requires easy model experimentation
4. No framework exists for fair model comparison

## Technical Design

### Model Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional

@dataclass
class ModelPrediction:
    model_name: str
    date: date
    predicted_price: float
    confidence_interval: tuple[float, float]  # (lower, upper)
    confidence_level: float  # 0.0 - 1.0
    metadata: dict  # Model-specific additional data

class PriceModel(ABC):
    """Abstract base class for all price models."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable model name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Model description and methodology."""
        pass

    @property
    @abstractmethod
    def required_data(self) -> list[str]:
        """List of required data sources."""
        pass

    @abstractmethod
    def fit(self, historical_data: pd.DataFrame) -> None:
        """Train/calibrate model on historical data."""
        pass

    @abstractmethod
    def predict(self, target_date: date) -> ModelPrediction:
        """Generate prediction for target date."""
        pass

    @abstractmethod
    def backtest(
        self,
        start_date: date,
        end_date: date,
        actual_prices: pd.Series
    ) -> "BacktestResult":
        """Run backtest over date range."""
        pass
```

### Built-in Models

```python
class PowerLawModel(PriceModel):
    """See spec-034 for details."""
    name = "Power Law"
    required_data = ["daily_prices"]

class StockToFlowModel(PriceModel):
    """Stock-to-Flow: Price = f(scarcity)."""
    name = "Stock-to-Flow"
    required_data = ["total_supply", "annual_inflation"]

    def predict(self, target_date: date) -> ModelPrediction:
        # S2F = Stock / Flow = Total Supply / Annual Issuance
        supply = self.get_supply(target_date)
        flow = self.get_annual_issuance(target_date)
        s2f = supply / flow

        # Price = exp(intercept + slope * ln(S2F))
        predicted = math.exp(self.intercept + self.slope * math.log(s2f))
        return ModelPrediction(
            model_name=self.name,
            date=target_date,
            predicted_price=predicted,
            confidence_interval=(predicted * 0.5, predicted * 2.0),
            confidence_level=0.7,
            metadata={"s2f_ratio": s2f}
        )

class ThermocapModel(PriceModel):
    """Thermocap: Cumulative miner revenue valuation."""
    name = "Thermocap Multiple"
    required_data = ["miner_revenue", "market_cap"]

class UTXOracleModel(PriceModel):
    """Our clustering-based price discovery."""
    name = "UTXOracle"
    required_data = ["blockchain_transactions"]
```

### Model Registry

```python
class ModelRegistry:
    """Registry of available price models."""

    _models: dict[str, type[PriceModel]] = {}

    @classmethod
    def register(cls, model_class: type[PriceModel]) -> None:
        """Register a new model type."""
        cls._models[model_class.name] = model_class

    @classmethod
    def get(cls, name: str) -> type[PriceModel]:
        """Get model class by name."""
        return cls._models[name]

    @classmethod
    def list_models(cls) -> list[str]:
        """List all registered models."""
        return list(cls._models.keys())

    @classmethod
    def create(cls, name: str, **config) -> PriceModel:
        """Create model instance with configuration."""
        model_class = cls.get(name)
        return model_class(**config)

# Auto-register built-in models
ModelRegistry.register(PowerLawModel)
ModelRegistry.register(StockToFlowModel)
ModelRegistry.register(ThermocapModel)
ModelRegistry.register(UTXOracleModel)
```

### Ensemble Model

```python
@dataclass
class EnsembleConfig:
    models: list[str]           # Model names
    weights: list[float]        # Model weights (must sum to 1)
    aggregation: str            # "weighted_avg", "median", "min", "max"

class EnsembleModel(PriceModel):
    """Combine multiple models for ensemble prediction."""

    name = "Ensemble"

    def __init__(self, config: EnsembleConfig):
        self.config = config
        self.models = [
            ModelRegistry.create(name)
            for name in config.models
        ]

    def predict(self, target_date: date) -> ModelPrediction:
        predictions = [m.predict(target_date) for m in self.models]
        prices = [p.predicted_price for p in predictions]
        weights = self.config.weights

        if self.config.aggregation == "weighted_avg":
            ensemble_price = sum(p * w for p, w in zip(prices, weights))
        elif self.config.aggregation == "median":
            ensemble_price = np.median(prices)
        else:
            raise ValueError(f"Unknown aggregation: {self.config.aggregation}")

        return ModelPrediction(
            model_name=self.name,
            date=target_date,
            predicted_price=ensemble_price,
            confidence_interval=self._calculate_interval(predictions),
            confidence_level=0.85,
            metadata={"component_predictions": predictions}
        )
```

### Backtesting Framework

```python
@dataclass
class BacktestResult:
    model_name: str
    start_date: date
    end_date: date
    predictions: int
    mae: float              # Mean Absolute Error
    mape: float             # Mean Absolute Percentage Error
    rmse: float             # Root Mean Square Error
    direction_accuracy: float  # % of correct up/down predictions
    sharpe_ratio: float     # Risk-adjusted returns if trading
    max_drawdown: float     # Worst peak-to-trough
    daily_results: pd.DataFrame

class Backtester:
    """Run backtests on price models."""

    def run(
        self,
        model: PriceModel,
        actual_prices: pd.Series,
        train_pct: float = 0.7
    ) -> BacktestResult:
        """
        Run walk-forward backtest.

        Args:
            model: Price model to test
            actual_prices: Series with date index
            train_pct: Fraction of data for initial training
        """
        train_size = int(len(actual_prices) * train_pct)
        train_data = actual_prices.iloc[:train_size]
        test_data = actual_prices.iloc[train_size:]

        model.fit(train_data.to_frame())

        results = []
        for target_date in test_data.index:
            pred = model.predict(target_date)
            actual = test_data.loc[target_date]
            results.append({
                "date": target_date,
                "predicted": pred.predicted_price,
                "actual": actual,
                "error": pred.predicted_price - actual,
                "error_pct": (pred.predicted_price - actual) / actual * 100
            })

        df = pd.DataFrame(results)
        return BacktestResult(
            model_name=model.name,
            start_date=test_data.index[0],
            end_date=test_data.index[-1],
            predictions=len(df),
            mae=df["error"].abs().mean(),
            mape=df["error_pct"].abs().mean(),
            rmse=np.sqrt((df["error"] ** 2).mean()),
            direction_accuracy=self._calc_direction_accuracy(df),
            sharpe_ratio=self._calc_sharpe(df),
            max_drawdown=self._calc_max_drawdown(df),
            daily_results=df
        )

    def compare_models(
        self,
        models: list[PriceModel],
        actual_prices: pd.Series
    ) -> pd.DataFrame:
        """Compare multiple models on same data."""
        results = [self.run(m, actual_prices) for m in models]
        return pd.DataFrame([
            {
                "model": r.model_name,
                "MAE": r.mae,
                "MAPE": r.mape,
                "RMSE": r.rmse,
                "Direction": r.direction_accuracy,
                "Sharpe": r.sharpe_ratio
            }
            for r in results
        ]).sort_values("MAPE")
```

## API Endpoints

```
GET /api/v1/models                    # List available models
GET /api/v1/models/{name}/predict     # Get prediction
POST /api/v1/models/ensemble          # Create ensemble
GET /api/v1/models/backtest/{name}    # Run backtest
GET /api/v1/models/compare            # Compare models
```

## Configuration

```yaml
# config/models.yaml
models:
  power_law:
    enabled: true
    auto_refit_days: 30

  stock_to_flow:
    enabled: true
    variant: "s2fx"  # or "classic"

  ensemble:
    enabled: true
    models: ["power_law", "utxoracle", "thermocap"]
    weights: [0.3, 0.5, 0.2]
    aggregation: "weighted_avg"

backtest:
  train_pct: 0.7
  walk_forward: true
  refit_frequency: "monthly"
```

## Implementation Files

```
scripts/models/
├── __init__.py
├── base.py                # PriceModel ABC, ModelPrediction dataclass
├── power_law_adapter.py   # Power law adapter (wraps spec-034)
├── stock_to_flow.py       # S2F implementation
├── thermocap.py           # Thermocap implementation
├── utxoracle_model.py     # Wrapper around UTXOracle.py
├── ensemble.py            # Ensemble combiner
├── registry.py            # Model registry
└── backtest/
    └── model_backtester.py  # Backtesting framework

api/routes/models.py       # API endpoints
tests/test_models/         # Test suite
config/models.yaml         # Configuration
```

## Validation Criteria

1. **Abstraction works**: New model implementation requires <50 LOC and zero changes to `base.py`, `registry.py`, or `ensemble.py`
2. **Backtest accuracy**: MAE/MAPE/RMSE calculations match manual spreadsheet verification within 0.01% tolerance
3. **Ensemble improves**: Ensemble MAPE ≤ min(individual model MAPEs) on test dataset
4. **No lookahead bias**: Walk-forward backtest uses only data available at prediction time (verified by date assertions in tests)
5. **Performance**: Single prediction <100ms, backtest <500ms per 1000 data points

## Estimated Effort

- Framework design: 2-3 hours
- Built-in models: 3-4 hours
- Backtesting: 2-3 hours
- Total: 8-10 hours

## Dependencies

- spec-034 (Power Law model)
- numpy, pandas
- Historical price data source

## Future Extensions

1. **ML models**: LSTM, Prophet, XGBoost
2. **Feature engineering**: On-chain metrics as inputs
3. **Auto-weighting**: Optimize ensemble weights via backtesting
4. **Real-time updates**: WebSocket for live predictions

## Status

**Draft** - Awaiting implementation approval
