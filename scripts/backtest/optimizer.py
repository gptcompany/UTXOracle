"""Weight optimization for backtesting.

Implements grid search and walk-forward validation for optimizing
signal fusion weights.
"""

from dataclasses import dataclass, field
from datetime import datetime
from itertools import product
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class OptimizationResult:
    """Weight optimization results."""

    best_weights: dict[str, float] = field(default_factory=dict)
    best_sharpe: float = 0.0
    baseline_sharpe: float = 0.0
    improvement: float = 0.0
    walk_forward_sharpe: float = 0.0
    weight_grid: list[dict] = field(default_factory=list)


def generate_weight_grid(
    signal_names: list[str],
    step: float = 0.1,
) -> list[dict[str, float]]:
    """Generate all weight combinations that sum to 1.0.

    Args:
        signal_names: List of signal names
        step: Step size for weights (e.g., 0.1 for 10% increments)

    Returns:
        List of weight dictionaries
    """
    n_signals = len(signal_names)
    if n_signals == 0:
        return []

    if n_signals == 1:
        return [{signal_names[0]: 1.0}]

    # Guard against invalid step values
    if step <= 0:
        return []

    # Generate all combinations for n-1 signals
    steps = int(1.0 / step) + 1
    weight_values = [i * step for i in range(steps)]

    grid = []
    for combo in product(weight_values, repeat=n_signals - 1):
        # Last weight is determined by constraint: sum = 1.0
        remaining = 1.0 - sum(combo)
        if remaining >= 0 and remaining <= 1.0:
            weights = {}
            for i, name in enumerate(signal_names[:-1]):
                weights[name] = combo[i]
            weights[signal_names[-1]] = remaining
            grid.append(weights)

    return grid


def combine_signals(
    signals: dict[str, list[float]],
    weights: dict[str, float],
) -> list[float]:
    """Combine multiple signals using weighted average.

    Args:
        signals: Dictionary of signal_name -> signal_values
        weights: Dictionary of signal_name -> weight

    Returns:
        Combined signal values
    """
    if not signals:
        return []

    # Find max length
    max_len = max(len(v) for v in signals.values())
    combined = []

    for i in range(max_len):
        weighted_sum = 0.0
        for name, signal_values in signals.items():
            if i < len(signal_values):
                weight = weights.get(name, 0.0)
                weighted_sum += signal_values[i] * weight
        combined.append(weighted_sum)

    return combined


def optimize_weights(
    signals: dict[str, list[float]],
    prices: list,  # List[PricePoint]
    start_date: datetime,
    end_date: datetime,
    step: float = 0.1,
    buy_threshold: float = 0.3,
    sell_threshold: float = -0.3,
) -> OptimizationResult:
    """Optimize signal weights via grid search.

    Args:
        signals: Dictionary of signal_name -> signal_values
        prices: List of PricePoint objects
        start_date: Start date for backtest
        end_date: End date for backtest
        step: Weight step size (e.g., 0.1 for 10% increments)
        buy_threshold: Signal threshold for buy
        sell_threshold: Signal threshold for sell

    Returns:
        OptimizationResult with best weights and Sharpe
    """
    from scripts.backtest.engine import run_backtest, BacktestConfig
    from scripts.backtest.metrics import calculate_returns, sharpe_ratio
    from scripts.backtest.data_loader import PricePoint

    signal_names = list(signals.keys())
    weight_grid = generate_weight_grid(signal_names, step)

    best_weights = None
    best_sharpe = float("-inf")
    grid_results = []

    for weights in weight_grid:
        # Combine signals with these weights
        combined = combine_signals(signals, weights)

        # Create prices with combined signal
        signal_prices = []
        for i, price in enumerate(prices):
            signal_value = combined[i] if i < len(combined) else 0.0
            signal_prices.append(
                PricePoint(
                    timestamp=price.timestamp,
                    utxoracle_price=price.utxoracle_price,
                    exchange_price=price.exchange_price,
                    confidence=price.confidence,
                    signal_value=signal_value,
                )
            )

        # Run backtest
        config = BacktestConfig(
            start_date=start_date,
            end_date=end_date,
            signal_source="optimized",
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
        )

        result = run_backtest(config, prices=signal_prices)

        # Calculate Sharpe
        if result.equity_curve:
            returns = calculate_returns(result.equity_curve)
            current_sharpe = sharpe_ratio(returns)
        else:
            current_sharpe = 0.0

        grid_results.append(
            {
                "weights": weights.copy(),
                "sharpe": current_sharpe,
            }
        )

        if current_sharpe > best_sharpe:
            best_sharpe = current_sharpe
            best_weights = weights.copy()

    # Calculate baseline (equal weights)
    equal_weight = 1.0 / len(signal_names) if signal_names else 0.0
    baseline_weights = {name: equal_weight for name in signal_names}
    baseline_combined = combine_signals(signals, baseline_weights)

    baseline_prices = []
    for i, price in enumerate(prices):
        signal_value = baseline_combined[i] if i < len(baseline_combined) else 0.0
        baseline_prices.append(
            PricePoint(
                timestamp=price.timestamp,
                utxoracle_price=price.utxoracle_price,
                exchange_price=price.exchange_price,
                confidence=price.confidence,
                signal_value=signal_value,
            )
        )

    baseline_config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        signal_source="baseline",
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
    )

    baseline_result = run_backtest(baseline_config, prices=baseline_prices)
    if baseline_result.equity_curve:
        baseline_returns = calculate_returns(baseline_result.equity_curve)
        baseline_sharpe = sharpe_ratio(baseline_returns)
    else:
        baseline_sharpe = 0.0

    improvement = (
        (best_sharpe - baseline_sharpe) / abs(baseline_sharpe)
        if baseline_sharpe != 0
        else 0.0
    )

    return OptimizationResult(
        best_weights=best_weights or {},
        best_sharpe=best_sharpe,
        baseline_sharpe=baseline_sharpe,
        improvement=improvement,
        walk_forward_sharpe=0.0,  # Set by walk_forward_validate
        weight_grid=grid_results,
    )


def walk_forward_validate(
    weights: dict[str, float],
    signals: dict[str, list[float]],
    prices: list,  # List[PricePoint]
    train_ratio: float = 0.7,
    buy_threshold: float = 0.3,
    sell_threshold: float = -0.3,
) -> dict[str, float]:
    """Validate weights using walk-forward analysis.

    Trains on first portion of data, tests on remainder.

    Args:
        weights: Signal weights to validate
        signals: Dictionary of signal_name -> signal_values
        prices: List of PricePoint objects
        train_ratio: Fraction of data for training (e.g., 0.7 = 70%)
        buy_threshold: Signal threshold for buy
        sell_threshold: Signal threshold for sell

    Returns:
        Dictionary with train_sharpe and test_sharpe
    """
    from scripts.backtest.engine import run_backtest, BacktestConfig
    from scripts.backtest.metrics import calculate_returns, sharpe_ratio
    from scripts.backtest.data_loader import PricePoint

    if not prices:
        return {"train_sharpe": 0.0, "test_sharpe": 0.0}

    # Split data
    split_idx = int(len(prices) * train_ratio)
    train_prices = prices[:split_idx]
    test_prices = prices[split_idx:]

    # Combine signals
    combined = combine_signals(signals, weights)

    def run_with_combined(price_subset, combined_signals, start_idx):
        signal_prices = []
        for i, price in enumerate(price_subset):
            signal_idx = start_idx + i
            signal_value = (
                combined_signals[signal_idx]
                if signal_idx < len(combined_signals)
                else 0.0
            )
            signal_prices.append(
                PricePoint(
                    timestamp=price.timestamp,
                    utxoracle_price=price.utxoracle_price,
                    exchange_price=price.exchange_price,
                    confidence=price.confidence,
                    signal_value=signal_value,
                )
            )

        if not signal_prices:
            return 0.0

        config = BacktestConfig(
            start_date=signal_prices[0].timestamp,
            end_date=signal_prices[-1].timestamp,
            signal_source="walk_forward",
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
        )

        result = run_backtest(config, prices=signal_prices)
        if result.equity_curve:
            returns = calculate_returns(result.equity_curve)
            return sharpe_ratio(returns)
        return 0.0

    train_sharpe = run_with_combined(train_prices, combined, 0)
    test_sharpe = run_with_combined(test_prices, combined, split_idx)

    return {
        "train_sharpe": train_sharpe,
        "test_sharpe": test_sharpe,
    }
