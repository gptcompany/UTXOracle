"""Backtesting framework for UTXOracle signals.

This module provides tools to validate on-chain metrics and fusion signals
against historical price data, calculate performance metrics, and optimize
signal weights.

Example usage:
    >>> from scripts.backtest import run_backtest, BacktestConfig
    >>> from datetime import datetime
    >>>
    >>> config = BacktestConfig(
    ...     start_date=datetime(2025, 1, 1),
    ...     end_date=datetime(2025, 11, 30),
    ...     signal_source="fusion",
    ... )
    >>> result = run_backtest(config)
    >>> print(f"Total Return: {result.total_return:.2%}")
"""

# Core backtest engine
from scripts.backtest.engine import (
    BacktestConfig,
    BacktestResult,
    ComparisonResult,
    Trade,
    run_backtest,
    compare_signals,
)

# Performance metrics
from scripts.backtest.metrics import (
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    win_rate,
    profit_factor,
    calculate_all_metrics,
    calculate_returns,
)

# Data loading
from scripts.backtest.data_loader import (
    PricePoint,
    HistoricalData,
    load_historical_data,
    load_from_duckdb,
    load_from_html,
    save_backtest_result,
    load_backtest_history,
)

# Weight optimization
from scripts.backtest.optimizer import (
    OptimizationResult,
    optimize_weights,
    walk_forward_validate,
)

__all__ = [
    # Engine
    "BacktestConfig",
    "BacktestResult",
    "ComparisonResult",
    "Trade",
    "run_backtest",
    "compare_signals",
    # Metrics
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "win_rate",
    "profit_factor",
    "calculate_all_metrics",
    "calculate_returns",
    # Data
    "PricePoint",
    "HistoricalData",
    "load_historical_data",
    "load_from_duckdb",
    "load_from_html",
    "save_backtest_result",
    "load_backtest_history",
    # Optimizer
    "OptimizationResult",
    "optimize_weights",
    "walk_forward_validate",
]
