# Data Model: Backtesting Framework

**Feature**: spec-012 | **Date**: 2025-12-04

## Entities

### BacktestConfig

```python
@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""
    start_date: datetime
    end_date: datetime
    signal_source: str            # "whale" | "utxo" | "fusion" | etc.
    buy_threshold: float = 0.3
    sell_threshold: float = -0.3
    position_size: float = 1.0    # 0.0 to 1.0
    transaction_cost: float = 0.001
    initial_capital: float = 10000.0
```

### Trade

```python
@dataclass
class Trade:
    """Single executed trade."""
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    direction: str                # "LONG" | "SHORT"
    pnl: float                    # Profit/loss in USD
    pnl_pct: float               # Profit/loss percentage
    signal_value: float          # Signal that triggered entry
```

### BacktestResult

```python
@dataclass
class BacktestResult:
    """Complete backtest results."""
    config: BacktestConfig
    trades: list[Trade]
    equity_curve: list[float]
    timestamps: list[datetime]

    # Performance Metrics
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate: float
    max_drawdown: float
    profit_factor: float
    num_trades: int
    avg_trade_duration: float     # hours
```

### ComparisonResult

```python
@dataclass
class ComparisonResult:
    """Multi-signal comparison results."""
    signals: list[str]
    results: dict[str, BacktestResult]
    ranking: list[str]            # By Sharpe
    best_signal: str
    best_sharpe: float
```

### OptimizationResult

```python
@dataclass
class OptimizationResult:
    """Weight optimization results."""
    best_weights: dict[str, float]
    best_sharpe: float
    baseline_sharpe: float
    improvement: float
    walk_forward_sharpe: float
    weight_grid: list[dict]
```

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY,
    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    signal_source VARCHAR NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    total_return DOUBLE,
    sharpe_ratio DOUBLE,
    sortino_ratio DOUBLE,
    win_rate DOUBLE,
    max_drawdown DOUBLE,
    profit_factor DOUBLE,
    num_trades INTEGER,
    config_json VARCHAR,
    trades_json VARCHAR
);
```

## Relationships

```
BacktestConfig ─────> BacktestResult
       │                    │
       └── signal_source    ├── trades: [Trade]
                           ├── equity_curve
                           └── metrics

ComparisonResult ───> {signal: BacktestResult, ...}

OptimizationResult ──> best_weights + walk_forward validation
```
