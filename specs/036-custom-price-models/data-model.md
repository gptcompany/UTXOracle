# Data Model: Custom Price Models Framework

**Feature**: spec-036 | **Date**: 2025-12-27

## Entity Overview

| Entity | Purpose | Location |
|--------|---------|----------|
| ModelPrediction | Unified prediction output from any model | `scripts/models/base.py` |
| PriceModel | Abstract base class for all models | `scripts/models/base.py` |
| EnsembleConfig | Configuration for ensemble models | `scripts/models/ensemble.py` |
| ModelBacktestResult | Backtesting results for price models | `scripts/models/backtest/model_backtester.py` |
| ModelRegistry | Registry for model discovery | `scripts/models/registry.py` |

---

## Core Data Structures

### ModelPrediction

```python
@dataclass
class ModelPrediction:
    """Unified prediction output from any price model."""

    model_name: str                           # Human-readable model name
    date: date                                # Prediction target date
    predicted_price: float                    # Predicted BTC/USD price
    confidence_interval: tuple[float, float]  # (lower_bound, upper_bound)
    confidence_level: float                   # 0.0-1.0 (e.g., 0.95 for 95% CI)
    metadata: dict                            # Model-specific additional data

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "date": self.date.isoformat(),
            "predicted_price": self.predicted_price,
            "confidence_interval": {
                "lower": self.confidence_interval[0],
                "upper": self.confidence_interval[1]
            },
            "confidence_level": self.confidence_level,
            "metadata": self.metadata
        }
```

**Validation Rules**:
- `predicted_price` > 0
- `confidence_interval[0]` < `predicted_price` < `confidence_interval[1]`
- 0.0 ≤ `confidence_level` ≤ 1.0
- `date` ≥ 2009-01-03 (Bitcoin genesis)

### PriceModel (ABC)

```python
from abc import ABC, abstractmethod

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
        """Check if model has been fitted."""
        ...
```

**State transitions**:
- Unfitted → Fitted: via `fit()` call
- Fitted → Predictions available: `predict()` only works after `fit()`

### EnsembleConfig

```python
@dataclass
class EnsembleConfig:
    """Configuration for ensemble model."""

    models: list[str]        # Model names from registry
    weights: list[float]     # Must sum to 1.0
    aggregation: str         # "weighted_avg" | "median" | "min" | "max"

    def __post_init__(self):
        if len(self.models) != len(self.weights):
            raise ValueError("models and weights must have same length")
        if not np.isclose(sum(self.weights), 1.0):
            raise ValueError("weights must sum to 1.0")
        if self.aggregation not in ("weighted_avg", "median", "min", "max"):
            raise ValueError(f"Unknown aggregation: {self.aggregation}")
```

### ModelBacktestResult

```python
@dataclass
class ModelBacktestResult:
    """Backtesting results for a price model."""

    model_name: str
    start_date: date
    end_date: date
    predictions: int          # Number of predictions made
    mae: float                # Mean Absolute Error (USD)
    mape: float               # Mean Absolute Percentage Error (%)
    rmse: float               # Root Mean Square Error (USD)
    direction_accuracy: float # % of correct up/down predictions
    sharpe_ratio: float       # Risk-adjusted metric (if trading on signal)
    max_drawdown: float       # Worst peak-to-trough (%)
    daily_results: pd.DataFrame  # Columns: date, predicted, actual, error, error_pct

    def to_dict(self) -> dict:
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
                "max_drawdown": self.max_drawdown
            }
        }
```

---

## Pydantic API Models

### ModelPredictionResponse

```python
class ModelPredictionResponse(BaseModel):
    """API response for model prediction."""

    model_name: str = Field(..., description="Model that generated prediction")
    date: DateType = Field(..., description="Prediction target date")
    predicted_price: float = Field(..., gt=0, description="Predicted BTC/USD price")
    confidence_interval: dict = Field(..., description="Lower/upper bounds")
    confidence_level: float = Field(..., ge=0, le=1, description="Confidence level")
    metadata: dict = Field(default_factory=dict, description="Model-specific data")

    model_config = {
        "json_schema_extra": {
            "example": {
                "model_name": "Power Law",
                "date": "2025-12-27",
                "predicted_price": 98500.00,
                "confidence_interval": {"lower": 45000.00, "upper": 210000.00},
                "confidence_level": 0.68,
                "metadata": {"zone": "fair", "deviation_pct": 5.2}
            }
        }
    }
```

### ModelInfoResponse

```python
class ModelInfoResponse(BaseModel):
    """API response for model info."""

    name: str = Field(..., description="Model name")
    description: str = Field(..., description="Model methodology")
    required_data: list[str] = Field(..., description="Required data sources")
    is_fitted: bool = Field(..., description="Whether model is calibrated")
```

### BacktestResultResponse

```python
class BacktestResultResponse(BaseModel):
    """API response for backtest results."""

    model_name: str
    start_date: DateType
    end_date: DateType
    predictions: int
    metrics: dict = Field(..., description="Performance metrics (MAE, MAPE, etc.)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "model_name": "Power Law",
                "start_date": "2020-01-01",
                "end_date": "2025-12-27",
                "predictions": 2188,
                "metrics": {
                    "mae": 5234.50,
                    "mape": 12.3,
                    "rmse": 7891.20,
                    "direction_accuracy": 0.58,
                    "sharpe_ratio": 0.85,
                    "max_drawdown": -32.5
                }
            }
        }
    }
```

### ModelComparisonResponse

```python
class ModelComparisonResponse(BaseModel):
    """API response for model comparison."""

    models: list[str] = Field(..., description="Models compared")
    ranking: list[str] = Field(..., description="Models ranked by MAPE")
    best_model: str = Field(..., description="Best performing model")
    results: list[BacktestResultResponse] = Field(..., description="Results per model")
```

### EnsembleCreateRequest

```python
class EnsembleCreateRequest(BaseModel):
    """Request to create an ensemble model."""

    models: list[str] = Field(..., min_length=2, description="Models to combine")
    weights: list[float] = Field(..., description="Model weights (sum to 1.0)")
    aggregation: str = Field(default="weighted_avg", description="Aggregation method")

    @validator("weights")
    def weights_sum_to_one(cls, v):
        if not np.isclose(sum(v), 1.0):
            raise ValueError("weights must sum to 1.0")
        return v
```

---

## Relationships

```
ModelRegistry
    │
    ├── registers → PowerLawAdapter
    ├── registers → StockToFlowModel
    ├── registers → ThermocapModel
    ├── registers → UTXOracleModel
    └── registers → EnsembleModel (created dynamically)
                        │
                        └── contains → [PowerLawAdapter, StockToFlowModel, ...]

PriceModel (ABC)
    │
    ├── implements → PowerLawAdapter
    ├── implements → StockToFlowModel
    ├── implements → ThermocapModel
    ├── implements → UTXOracleModel
    └── implements → EnsembleModel

ModelBacktester
    │
    ├── uses → PriceModel.fit()
    ├── uses → PriceModel.predict()
    └── produces → ModelBacktestResult
```

---

## Storage

### Configuration File: `config/models.yaml`

```yaml
# Model configuration
models:
  power_law:
    enabled: true
    auto_refit_days: 30  # Refit monthly

  stock_to_flow:
    enabled: true
    variant: "classic"   # or "s2fx"

  thermocap:
    enabled: true
    fair_multiple_range: [3.0, 8.0]

  utxoracle:
    enabled: true
    # Uses UTXOracle.py defaults

# Default ensemble configuration
ensemble:
  enabled: true
  models: ["power_law", "stock_to_flow", "thermocap"]
  weights: [0.4, 0.3, 0.3]
  aggregation: "weighted_avg"

# Backtesting defaults
backtest:
  train_pct: 0.7
  walk_forward: true
  refit_frequency: "monthly"
```

### No Database Storage

- Models are stateless (coefficients held in memory)
- Historical data from existing `daily_prices` DuckDB table
- No new tables required
