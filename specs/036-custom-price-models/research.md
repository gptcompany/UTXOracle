# Research: Custom Price Models Framework

**Feature**: spec-036 | **Date**: 2025-12-27

## Research Questions

1. What are the best practices for implementing Bitcoin valuation models (S2F, Thermocap)?
2. How should the model interface be designed for extensibility?
3. What backtesting patterns work best for price models?
4. How to integrate with existing spec-034 Power Law implementation?

---

## 1. Bitcoin Valuation Model Best Practices

### Stock-to-Flow (S2F) Model

**Decision**: Implement S2F with halving-aware flow calculation

**Rationale**:
- S2F = Stock / Flow, where Stock = total supply, Flow = annual issuance
- Bitcoin's emission schedule is deterministic (halving every 210,000 blocks)
- Pre-compute block reward schedule for efficiency
- Price = exp(intercept + slope * ln(S2F)) based on PlanB's original model

**Alternatives considered**:
1. **S2FX (cross-asset model)**: Rejected - requires gold/silver data, violates local-first principle
2. **Dynamic S2F**: Rejected - overly complex, YAGNI

**Implementation approach**:
```python
class StockToFlowModel(PriceModel):
    # Halving schedule
    HALVING_BLOCKS = 210_000
    INITIAL_REWARD = 50.0

    # Default coefficients (PlanB model)
    DEFAULT_INTERCEPT = -1.84
    DEFAULT_SLOPE = 3.36

    def calculate_s2f(self, block_height: int) -> float:
        supply = self._calculate_supply(block_height)
        annual_issuance = self._calculate_annual_issuance(block_height)
        return supply / annual_issuance
```

**Data requirements**:
- Block height for target date (from blockchain or height-to-date mapping)
- No external data needed - supply/flow calculated from Bitcoin protocol rules

### Thermocap Model

**Decision**: Implement as Thermocap Multiple = Market Cap / Cumulative Miner Revenue

**Rationale**:
- Thermocap = sum of all block rewards * price at time of mining
- Thermocap Multiple indicates market valuation relative to miner investment
- Historical average multiple ~3-8x indicates fair value range
- Requires cumulative miner revenue data (can be calculated from blockchain)

**Alternatives considered**:
1. **Real-time Thermocap**: Rejected - requires price at each block, too data-intensive
2. **Simplified Thermocap**: Accepted - use total mined BTC * average price as approximation

**Implementation approach**:
```python
class ThermocapModel(PriceModel):
    # Thermocap multiple ranges
    FAIR_MULTIPLE_LOW = 3.0
    FAIR_MULTIPLE_HIGH = 8.0

    def predict(self, target_date: date) -> ModelPrediction:
        # Thermocap = cumulative BTC mined * historical avg price
        # Fair value = Thermocap * average_multiple
        pass
```

**Data requirements**:
- Cumulative miner revenue (can approximate from supply * avg historical price)
- Current market cap

### UTXOracle Model Wrapper

**Decision**: Wrap existing `UTXOracle.py` as a PriceModel

**Rationale**:
- UTXOracle is the reference implementation - immutable per CLAUDE.md
- Wrapper calls UTXOracle.py via subprocess or imports library functions
- Maintains separation between framework and reference implementation

**Implementation approach**:
```python
class UTXOracleModel(PriceModel):
    def predict(self, target_date: date) -> ModelPrediction:
        # Option 1: Import UTXOracle_library.py functions
        # Option 2: Shell out to UTXOracle.py -d YYYY/MM/DD
        # Prefer Option 1 for performance
        pass
```

---

## 2. Model Interface Design

### Decision: Use ABC with dataclass outputs

**Rationale**:
- ABC enforces contract without runtime overhead
- Dataclasses provide type safety and serialization
- Match existing Pydantic pattern for API responses

**Key design choices**:

1. **Fit-then-predict pattern**: Models must be fit before prediction
2. **Stateless predictions**: fit() stores state, predict() uses it
3. **Confidence intervals**: All predictions include uncertainty bounds
4. **Metadata**: Model-specific data in dict for extensibility

**Interface contract**:
```python
class PriceModel(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def required_data(self) -> list[str]: ...

    @abstractmethod
    def fit(self, historical_data: pd.DataFrame) -> None: ...

    @abstractmethod
    def predict(self, target_date: date) -> ModelPrediction: ...
```

**Alternatives considered**:
1. **Protocol (structural typing)**: Rejected - less explicit than ABC
2. **Function-based interface**: Rejected - loses state management benefits

---

## 3. Backtesting Integration

### Decision: Extend existing `BacktestResult` dataclass, create `ModelBacktester` class

**Rationale**:
- Existing `scripts/backtest/engine.py` has trade-based backtesting
- Price models need different metrics (MAE, MAPE, direction accuracy)
- Create parallel backtester that uses same result patterns

**Implementation approach**:
```python
@dataclass
class ModelBacktestResult:
    model_name: str
    start_date: date
    end_date: date
    predictions: int
    mae: float      # Mean Absolute Error
    mape: float     # Mean Absolute Percentage Error
    rmse: float     # Root Mean Square Error
    direction_accuracy: float  # % correct up/down
    daily_results: pd.DataFrame

class ModelBacktester:
    def run(self, model: PriceModel, actual_prices: pd.Series) -> ModelBacktestResult: ...
    def compare_models(self, models: list[PriceModel], prices: pd.Series) -> pd.DataFrame: ...
```

**Alternatives considered**:
1. **Modify existing engine.py**: Rejected - would break existing signal backtests
2. **Inherit from BacktestResult**: Rejected - different metrics, not a true subtype

---

## 4. Integration with Spec-034 Power Law

### Decision: Create `PowerLawAdapter` that wraps existing implementation

**Rationale**:
- `scripts/models/price_power_law.py` already implements the algorithm
- Don't duplicate code - wrap existing functions in ABC interface
- Preserves existing API endpoints unchanged

**Implementation approach**:
```python
class PowerLawAdapter(PriceModel):
    """Adapts spec-034 Power Law to PriceModel interface."""

    name = "Power Law"
    description = "Bitcoin price power law model (spec-034)"
    required_data = ["daily_prices"]

    def __init__(self):
        from scripts.models.price_power_law import DEFAULT_MODEL
        self._model = DEFAULT_MODEL

    def fit(self, historical_data: pd.DataFrame) -> None:
        from scripts.models.price_power_law import fit_power_law
        self._model = fit_power_law(
            historical_data.index.tolist(),
            historical_data["price"].tolist()
        )

    def predict(self, target_date: date) -> ModelPrediction:
        from scripts.models.price_power_law import predict_price
        result = predict_price(self._model, target_date)
        return ModelPrediction(
            model_name=self.name,
            date=target_date,
            predicted_price=result.fair_value,
            confidence_interval=(result.lower_band, result.upper_band),
            confidence_level=0.68,  # 1 sigma
            metadata={"zone": result.zone, "deviation_pct": result.deviation_pct}
        )
```

---

## 5. Model Registry Pattern

### Decision: Class-based registry with decorator registration

**Rationale**:
- Allows models to self-register on import
- Factory pattern for creating model instances
- Enumerable for API listing

**Implementation approach**:
```python
class ModelRegistry:
    _models: dict[str, type[PriceModel]] = {}

    @classmethod
    def register(cls, model_class: type[PriceModel]) -> type[PriceModel]:
        """Decorator to register a model class."""
        cls._models[model_class.name] = model_class
        return model_class

    @classmethod
    def get(cls, name: str) -> type[PriceModel]:
        if name not in cls._models:
            raise KeyError(f"Unknown model: {name}")
        return cls._models[name]

    @classmethod
    def list_models(cls) -> list[str]:
        return list(cls._models.keys())

    @classmethod
    def create(cls, name: str, **config) -> PriceModel:
        return cls.get(name)(**config)

# Usage:
@ModelRegistry.register
class StockToFlowModel(PriceModel):
    name = "Stock-to-Flow"
    ...
```

---

## 6. Ensemble Aggregation

### Decision: Simple weighted average with pluggable aggregation methods

**Rationale**:
- Start with weighted average (most common)
- Support median for outlier robustness
- Keep it simple - avoid complex ensemble methods (YAGNI)

**Implementation approach**:
```python
class EnsembleModel(PriceModel):
    name = "Ensemble"

    AGGREGATIONS = {
        "weighted_avg": lambda prices, weights: sum(p * w for p, w in zip(prices, weights)),
        "median": lambda prices, _: np.median(prices),
        "min": lambda prices, _: min(prices),
        "max": lambda prices, _: max(prices),
    }

    def __init__(self, models: list[str], weights: list[float], aggregation: str = "weighted_avg"):
        if not np.isclose(sum(weights), 1.0):
            raise ValueError("Weights must sum to 1.0")
        self.models = [ModelRegistry.create(name) for name in models]
        self.weights = weights
        self.aggregation = self.AGGREGATIONS[aggregation]
```

---

## Research Summary

| Topic | Decision | Key Rationale |
|-------|----------|---------------|
| S2F Model | Halving-aware calculation | No external data needed |
| Thermocap | Simplified multiple approach | Avoid data-intensive real-time calc |
| UTXOracle | Wrapper via library import | Preserve immutable reference impl |
| Interface | ABC with dataclass outputs | Type safety, matches existing patterns |
| Backtesting | Separate ModelBacktester class | Different metrics than trade backtests |
| Power Law | Adapter pattern | Code reuse, no duplication |
| Registry | Decorator-based registration | Simple, self-documenting |
| Ensemble | Weighted avg + alternatives | Start simple, extend as needed |

## Open Items

None - all research questions resolved.
