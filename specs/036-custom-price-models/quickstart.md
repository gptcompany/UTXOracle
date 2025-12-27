# Quickstart: Custom Price Models Framework

**Feature**: spec-036 | **Date**: 2025-12-27

## Prerequisites

- Python 3.11+
- UTXOracle repository cloned
- Dependencies installed: `uv sync`

## Quick Examples

### 1. List Available Models

```python
from scripts.models.registry import ModelRegistry

# List all registered models
models = ModelRegistry.list_models()
print(models)  # ['Power Law', 'Stock-to-Flow', 'Thermocap', 'UTXOracle']
```

### 2. Get a Prediction

```python
from datetime import date
from scripts.models.registry import ModelRegistry

# Create and use a model
model = ModelRegistry.create("Power Law")
prediction = model.predict(date.today())

print(f"Fair Value: ${prediction.predicted_price:,.2f}")
print(f"Range: ${prediction.confidence_interval[0]:,.2f} - ${prediction.confidence_interval[1]:,.2f}")
```

### 3. Create an Ensemble

```python
from scripts.models.ensemble import EnsembleModel, EnsembleConfig

config = EnsembleConfig(
    models=["Power Law", "Stock-to-Flow", "Thermocap"],
    weights=[0.4, 0.3, 0.3],
    aggregation="weighted_avg"
)

ensemble = EnsembleModel(config)
prediction = ensemble.predict(date.today())
print(f"Ensemble Price: ${prediction.predicted_price:,.2f}")
```

### 4. Backtest a Model

```python
import pandas as pd
from scripts.models.registry import ModelRegistry
from scripts.models.backtest.model_backtester import ModelBacktester

# Load historical prices
prices = pd.read_csv("data/daily_prices.csv", index_col="date", parse_dates=True)

# Backtest
model = ModelRegistry.create("Power Law")
backtester = ModelBacktester()
result = backtester.run(model, prices["close"])

print(f"MAPE: {result.mape:.2f}%")
print(f"Direction Accuracy: {result.direction_accuracy:.2%}")
```

### 5. Compare Models

```python
from scripts.models.registry import ModelRegistry
from scripts.models.backtest.model_backtester import ModelBacktester

models = [
    ModelRegistry.create("Power Law"),
    ModelRegistry.create("Stock-to-Flow"),
    ModelRegistry.create("Thermocap"),
]

backtester = ModelBacktester()
comparison = backtester.compare_models(models, prices["close"])
print(comparison.sort_values("MAPE"))
```

## API Usage

### List Models
```bash
curl http://localhost:8000/api/v1/models
```

### Get Prediction
```bash
curl "http://localhost:8000/api/v1/models/power-law/predict?date=2025-12-27"
```

### Create Ensemble
```bash
curl -X POST http://localhost:8000/api/v1/models/ensemble \
  -H "Content-Type: application/json" \
  -d '{
    "models": ["power-law", "stock-to-flow"],
    "weights": [0.6, 0.4],
    "aggregation": "weighted_avg"
  }'
```

### Run Backtest
```bash
curl "http://localhost:8000/api/v1/models/backtest/power-law?start_date=2020-01-01"
```

### Compare Models
```bash
curl "http://localhost:8000/api/v1/models/compare?models=power-law,stock-to-flow,thermocap"
```

## Adding a New Model

1. Create model file in `scripts/models/`:

```python
# scripts/models/my_model.py
from scripts.models.base import PriceModel, ModelPrediction
from scripts.models.registry import ModelRegistry

@ModelRegistry.register
class MyModel(PriceModel):
    name = "My Model"
    description = "My custom valuation model"
    required_data = ["daily_prices"]

    def fit(self, historical_data):
        # Train model
        pass

    def predict(self, target_date):
        return ModelPrediction(
            model_name=self.name,
            date=target_date,
            predicted_price=100000.0,
            confidence_interval=(80000.0, 120000.0),
            confidence_level=0.68,
            metadata={}
        )
```

2. Import in `scripts/models/__init__.py`:

```python
from scripts.models.my_model import MyModel
```

3. Model is now available via registry and API!

## Configuration

Edit `config/models.yaml`:

```yaml
models:
  my_model:
    enabled: true
    # Custom settings...

ensemble:
  models: ["power-law", "my-model"]
  weights: [0.5, 0.5]
```

## Running Tests

```bash
# All model tests
uv run pytest tests/test_models/ -v

# Specific model
uv run pytest tests/test_models/test_stock_to_flow.py -v

# With coverage
uv run pytest tests/test_models/ --cov=scripts/models --cov-report=term-missing
```
