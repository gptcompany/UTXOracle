# Quickstart: Backtesting Framework

**Feature**: spec-012 | **Date**: 2025-12-04

## Basic Usage

### Single Signal Backtest

```python
from scripts.backtest import run_backtest, BacktestConfig
from datetime import datetime

config = BacktestConfig(
    start_date=datetime(2025, 1, 1),
    end_date=datetime(2025, 11, 30),
    signal_source="fusion",
    buy_threshold=0.3,
    sell_threshold=-0.3,
    position_size=1.0,
    transaction_cost=0.001,
    initial_capital=10000.0
)

result = run_backtest(config)

print(f"Total Return: {result.total_return:.2%}")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Win Rate: {result.win_rate:.2%}")
print(f"Max Drawdown: {result.max_drawdown:.2%}")
print(f"Trades: {result.num_trades}")
```

### Compare Multiple Signals

```python
from scripts.backtest import compare_signals, PricePoint
from datetime import datetime, timedelta

# Create or load price data
prices = [
    PricePoint(
        timestamp=datetime(2025, 1, 1) + timedelta(days=i),
        utxoracle_price=50000 + i * 100,
        exchange_price=50000 + i * 100,
        confidence=0.9,
        signal_value=0.0,
    )
    for i in range(100)
]

# Define signal values for each strategy
signals = {
    "whale": [0.5 if i % 3 == 0 else 0.0 for i in range(100)],
    "utxo": [-0.5 if i % 4 == 0 else 0.0 for i in range(100)],
    "symbolic": [0.3 if i % 5 == 0 else -0.3 for i in range(100)],
    "fusion": [0.4 if i % 2 == 0 else -0.4 for i in range(100)],
}

comparison = compare_signals(
    signals=signals,
    prices=prices,
    start_date=datetime(2025, 1, 1),
    end_date=datetime(2025, 4, 10),
)

print("Signal Ranking by Sharpe:")
for i, signal in enumerate(comparison.ranking, 1):
    result = comparison.results[signal]
    print(f"{i}. {signal}: Sharpe={result.sharpe_ratio:.2f}, WR={result.win_rate:.1%}")
```

### Optimize Weights

```python
from scripts.backtest import optimize_weights, PricePoint
from datetime import datetime, timedelta

# Create or load price data
prices = [
    PricePoint(
        timestamp=datetime(2025, 1, 1) + timedelta(days=i),
        utxoracle_price=50000 + i * 100,
        exchange_price=50000 + i * 100,
        confidence=0.9,
        signal_value=0.0,
    )
    for i in range(100)
]

# Define signal values for each strategy to optimize
signals = {
    "whale": [0.5 if i % 3 == 0 else 0.0 for i in range(100)],
    "utxo": [-0.5 if i % 4 == 0 else 0.0 for i in range(100)],
}

optimization = optimize_weights(
    signals=signals,
    prices=prices,
    start_date=datetime(2025, 1, 1),
    end_date=datetime(2025, 4, 10),
    step=0.1,  # 10% increments (0.05 = 5% creates large grid)
)

print(f"Best Weights: {optimization.best_weights}")
print(f"Best Sharpe: {optimization.best_sharpe:.2f}")
print(f"Improvement: {optimization.improvement:.1%}")
```

## Interpretation

### Sharpe Ratio
| Value | Meaning |
|-------|---------|
| < 0.5 | Poor |
| 0.5-1.0 | Below average |
| 1.0-2.0 | Good |
| > 2.0 | Excellent |

### Win Rate
| Value | Meaning |
|-------|---------|
| < 40% | Poor |
| 40-50% | Average |
| 50-60% | Good |
| > 60% | Excellent |

### Max Drawdown
| Value | Risk Level |
|-------|------------|
| < 10% | Low |
| 10-20% | Moderate |
| 20-30% | High |
| > 30% | Very High |
