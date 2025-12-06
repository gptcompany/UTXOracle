"""Performance metrics for backtesting.

Implements standard quantitative finance metrics for evaluating
trading strategy performance.
"""

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def sharpe_ratio(
    returns: list[float],
    risk_free_rate: float = 0.0,
    annualization_factor: float = 252,
) -> float:
    """Calculate annualized Sharpe ratio.

    Sharpe = (mean(returns) - rf) / std(returns) * sqrt(annualization_factor)

    Args:
        returns: List of period returns (e.g., daily)
        risk_free_rate: Risk-free rate for the same period
        annualization_factor: Periods per year (252 for daily, 52 for weekly)

    Returns:
        Annualized Sharpe ratio
    """
    if not returns or len(returns) < 2:
        return 0.0

    n = len(returns)
    mean_return = sum(returns) / n
    excess_return = mean_return - risk_free_rate

    # Calculate standard deviation
    variance = sum((r - mean_return) ** 2 for r in returns) / (n - 1)
    std_return = math.sqrt(variance) if variance > 0 else 0.0

    if std_return == 0:
        return 0.0

    # Guard against negative annualization factor (sqrt of negative)
    if annualization_factor < 0:
        return float("nan")

    return (excess_return / std_return) * math.sqrt(annualization_factor)


def sortino_ratio(
    returns: list[float],
    risk_free_rate: float = 0.0,
    annualization_factor: float = 252,
) -> float:
    """Calculate annualized Sortino ratio.

    Sortino = (mean(returns) - rf) / std(negative_returns) * sqrt(annualization_factor)

    Only penalizes downside volatility, making it more appropriate for
    asymmetric return distributions.

    Args:
        returns: List of period returns
        risk_free_rate: Risk-free rate for the same period
        annualization_factor: Periods per year

    Returns:
        Annualized Sortino ratio
    """
    if not returns or len(returns) < 2:
        return 0.0

    n = len(returns)
    mean_return = sum(returns) / n
    excess_return = mean_return - risk_free_rate

    # Only consider negative returns (downside)
    negative_returns = [r for r in returns if r < 0]

    if not negative_returns:
        # No downside returns - perfect performance
        return float("inf") if excess_return > 0 else 0.0

    # Downside deviation
    downside_variance = sum(r**2 for r in negative_returns) / len(negative_returns)
    downside_std = math.sqrt(downside_variance) if downside_variance > 0 else 0.0

    if downside_std == 0:
        return 0.0

    return (excess_return / downside_std) * math.sqrt(annualization_factor)


def max_drawdown(equity_curve: list[float]) -> float:
    """Calculate maximum drawdown from equity curve.

    Max drawdown is the largest peak-to-trough decline.

    Args:
        equity_curve: List of equity values over time

    Returns:
        Maximum drawdown as a fraction (0.0 to 1.0)
    """
    if not equity_curve or len(equity_curve) < 2:
        return 0.0

    max_dd = 0.0
    peak = equity_curve[0]

    for value in equity_curve:
        if value > peak:
            peak = value
        else:
            drawdown = (peak - value) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, drawdown)

    return max_dd


def win_rate(trades: list) -> float:
    """Calculate win rate from trades.

    Win rate = count(profitable_trades) / count(all_trades)

    Args:
        trades: List of Trade objects

    Returns:
        Win rate as a fraction (0.0 to 1.0)
    """
    if not trades:
        return 0.0

    winning_trades = sum(1 for t in trades if t.pnl > 0)
    return winning_trades / len(trades)


def profit_factor(trades: list) -> float:
    """Calculate profit factor from trades.

    Profit factor = sum(positive_pnl) / abs(sum(negative_pnl))

    Values > 1.0 indicate overall profitability.

    Args:
        trades: List of Trade objects

    Returns:
        Profit factor (0.0 to inf, or 0.0 if no losing trades)
    """
    if not trades:
        return 0.0

    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))

    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0

    return gross_profit / gross_loss


def calculate_returns(equity_curve: list[float]) -> list[float]:
    """Calculate period returns from equity curve.

    Args:
        equity_curve: List of equity values

    Returns:
        List of period returns (one less than equity_curve length)
    """
    if len(equity_curve) < 2:
        return []

    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i - 1] != 0:
            ret = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
            returns.append(ret)
        else:
            returns.append(0.0)

    return returns


def calculate_all_metrics(
    trades: list,
    equity_curve: list[float],
    risk_free_rate: float = 0.0,
) -> dict[str, float]:
    """Calculate all performance metrics.

    Args:
        trades: List of Trade objects
        equity_curve: Equity values over time
        risk_free_rate: Risk-free rate for Sharpe/Sortino

    Returns:
        Dictionary with all metrics
    """
    returns = calculate_returns(equity_curve)

    return {
        "sharpe_ratio": sharpe_ratio(returns, risk_free_rate),
        "sortino_ratio": sortino_ratio(returns, risk_free_rate),
        "max_drawdown": max_drawdown(equity_curve),
        "win_rate": win_rate(trades),
        "profit_factor": profit_factor(trades),
    }
