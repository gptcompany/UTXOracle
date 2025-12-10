"""Baseline generators for metric validation.

Provides benchmark comparisons:
- Random baseline: Shuffled signals (Monte Carlo)
- Buy-and-hold baseline: Simple market exposure

These baselines help determine if a metric provides
value beyond random chance or simple market participation.
"""

import random
from typing import TYPE_CHECKING

from scripts.backtest.metrics import sharpe_ratio, calculate_returns

if TYPE_CHECKING:
    pass


def random_baseline(
    signal_values: list[float],
    prices: list[float],
    n_trials: int = 1000,
    seed: int = 42,
) -> list[float]:
    """Generate random baseline by shuffling signals.

    Simulates what performance would look like if the signal
    had no predictive value (null hypothesis).

    Args:
        signal_values: Original signal values to shuffle
        prices: Corresponding price series
        n_trials: Number of random shuffles to perform
        seed: Random seed for reproducibility

    Returns:
        List of Sharpe ratios from shuffled trials
    """
    if not signal_values or not prices:
        return []

    random.seed(seed)
    sharpe_ratios = []

    for _ in range(n_trials):
        # Shuffle signals while keeping prices fixed
        shuffled = signal_values.copy()
        random.shuffle(shuffled)

        # Calculate returns as if trading based on shuffled signals
        returns = _simulate_signal_returns(shuffled, prices)
        if returns:
            sr = sharpe_ratio(returns)
            sharpe_ratios.append(sr)

    return sharpe_ratios


def _simulate_signal_returns(
    signals: list[float],
    prices: list[float],
    threshold: float = 0.1,  # Lower threshold for spec-009 metrics
) -> list[float]:
    """Simulate returns from signal-based trading.

    Simple strategy:
    - Signal > threshold: Long position (capture next return)
    - Signal < -threshold: Short position (capture negative return)
    - Otherwise: Flat (zero return)

    Note: Default threshold lowered to 0.1 to accommodate spec-009 metrics
    which produce smaller vote values (typically 0.0 to 0.25).

    Args:
        signals: Signal values
        prices: Price series (must have len(prices) >= len(signals) + 1)
        threshold: Signal threshold for entry

    Returns:
        List of simulated returns (length = min(len(signals), len(prices) - 1))
    """
    # We need prices[i+1] for signal[i], so max usable signals is len(prices) - 1
    n = min(len(signals), len(prices) - 1)
    if n < 1 or len(prices) < 2:
        return []

    returns = []
    for i in range(n):
        price_return = (prices[i + 1] - prices[i]) / prices[i] if prices[i] > 0 else 0.0
        signal = signals[i] if signals[i] is not None else 0.0

        if signal > threshold:
            # Long position
            returns.append(price_return)
        elif signal < -threshold:
            # Short position
            returns.append(-price_return)
        else:
            # Flat
            returns.append(0.0)

    return returns


def buyhold_baseline(prices: list[float]) -> float:
    """Calculate buy-and-hold Sharpe ratio.

    This represents the simplest possible strategy:
    buy at start, hold throughout the period.

    Args:
        prices: Price series

    Returns:
        Annualized Sharpe ratio of buy-and-hold
    """
    if len(prices) < 2:
        return 0.0

    # Calculate daily returns
    returns = calculate_returns(prices)
    return sharpe_ratio(returns)


def calculate_excess_return(
    actual_sharpe: float,
    baseline_sharpe: float,
) -> float:
    """Calculate excess Sharpe ratio over baseline.

    Args:
        actual_sharpe: Achieved Sharpe ratio
        baseline_sharpe: Baseline Sharpe ratio

    Returns:
        Excess Sharpe (positive = outperformance)
    """
    return actual_sharpe - baseline_sharpe


def calculate_signal_sharpe(
    signals: list[float],
    prices: list[float],
    threshold: float = 0.1,  # Lower threshold for spec-009 metrics
) -> float:
    """Calculate Sharpe ratio for a signal series.

    Args:
        signals: Signal values
        prices: Price series
        threshold: Signal threshold for entry

    Returns:
        Annualized Sharpe ratio
    """
    returns = _simulate_signal_returns(signals, prices, threshold)
    return sharpe_ratio(returns)


def calculate_win_rate(
    signals: list[float],
    prices: list[float],
    threshold: float = 0.1,  # Lower threshold for spec-009 metrics
) -> float:
    """Calculate win rate for signal-based trading.

    Args:
        signals: Signal values
        prices: Price series (must have len >= len(signals) + 1)
        threshold: Signal threshold for entry

    Returns:
        Win rate (0.0 to 1.0)
    """
    # We need prices[i+1] for signal[i]
    n = min(len(signals), len(prices) - 1)
    if n < 1 or len(prices) < 2:
        return 0.0

    wins = 0
    trades = 0

    for i in range(n):
        signal = signals[i] if signals[i] is not None else 0.0

        if abs(signal) > threshold:
            price_return = (
                (prices[i + 1] - prices[i]) / prices[i] if prices[i] > 0 else 0.0
            )
            trades += 1

            if signal > threshold and price_return > 0:
                wins += 1
            elif signal < -threshold and price_return < 0:
                wins += 1

    return wins / trades if trades > 0 else 0.0


def calculate_profit_factor(
    signals: list[float],
    prices: list[float],
    threshold: float = 0.1,  # Lower threshold for spec-009 metrics
) -> float:
    """Calculate profit factor for signal-based trading.

    Profit factor = gross profits / gross losses

    Args:
        signals: Signal values
        prices: Price series
        threshold: Signal threshold for entry

    Returns:
        Profit factor (>1 means profitable)
    """
    returns = _simulate_signal_returns(signals, prices, threshold)

    if not returns:
        return 0.0

    gross_profit = sum(r for r in returns if r > 0)
    gross_loss = abs(sum(r for r in returns if r < 0))

    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0

    return gross_profit / gross_loss
