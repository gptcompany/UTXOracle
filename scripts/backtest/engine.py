"""Backtesting engine for UTXOracle signals.

Core backtest logic for validating on-chain metrics and fusion signals
against historical price data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    pass


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""

    start_date: datetime
    end_date: datetime
    signal_source: str  # "whale" | "utxo" | "fusion" | etc.
    buy_threshold: float = 0.3
    sell_threshold: float = -0.3
    position_size: float = 1.0  # 0.0 to 1.0
    transaction_cost: float = 0.001
    initial_capital: float = 10000.0


@dataclass
class Trade:
    """Single executed trade."""

    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    direction: str  # "LONG" | "SHORT"
    pnl: float  # Profit/loss in USD
    pnl_pct: float  # Profit/loss percentage
    signal_value: float  # Signal that triggered entry


@dataclass
class BacktestResult:
    """Complete backtest results."""

    config: BacktestConfig
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    timestamps: list[datetime] = field(default_factory=list)

    # Performance Metrics
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    num_trades: int = 0
    avg_trade_duration: float = 0.0  # hours


@dataclass
class ComparisonResult:
    """Multi-signal comparison results."""

    signals: list[str] = field(default_factory=list)
    results: dict[str, BacktestResult] = field(default_factory=dict)
    ranking: list[str] = field(default_factory=list)  # By Sharpe
    best_signal: str = ""
    best_sharpe: float = 0.0


def get_signal_action(
    signal_value: Optional[float],
    buy_threshold: float,
    sell_threshold: float,
) -> str:
    """Determine trade action from signal value.

    Args:
        signal_value: Signal value (typically -1 to +1)
        buy_threshold: Signal above this triggers BUY
        sell_threshold: Signal below this triggers SELL

    Returns:
        "BUY", "SELL", or "HOLD"
    """
    if signal_value is None:
        return "HOLD"
    if signal_value >= buy_threshold:
        return "BUY"
    if signal_value <= sell_threshold:
        return "SELL"
    return "HOLD"


def execute_trade(
    entry_time: datetime,
    entry_price: float,
    exit_time: datetime,
    exit_price: float,
    direction: str,
    position_size: float,
    transaction_cost: float,
    capital: float,
    signal_value: float,
) -> Trade:
    """Simulate trade execution and calculate P&L.

    Args:
        entry_time: Trade entry timestamp
        entry_price: Price at entry
        exit_time: Trade exit timestamp
        exit_price: Price at exit
        direction: "LONG" or "SHORT"
        position_size: Fraction of capital to use (0-1)
        transaction_cost: Cost per trade as fraction (e.g., 0.001 = 0.1%)
        capital: Current capital
        signal_value: Signal that triggered entry

    Returns:
        Trade object with calculated P&L
    """
    trade_capital = capital * position_size

    # Guard against division by zero
    if entry_price <= 0:
        # Invalid entry price - return zero P&L trade (no transaction costs applied)
        return Trade(
            entry_time=entry_time,
            exit_time=exit_time,
            entry_price=entry_price,
            exit_price=exit_price,
            direction=direction,
            pnl=0.0,
            pnl_pct=0.0,
            signal_value=signal_value,
        )

    if direction == "LONG":
        # Buy at entry, sell at exit
        pnl_pct = (exit_price - entry_price) / entry_price
    else:  # SHORT
        # Sell at entry, buy back at exit
        pnl_pct = (entry_price - exit_price) / entry_price

    # Apply transaction costs (entry + exit)
    pnl_pct -= 2 * transaction_cost

    pnl = trade_capital * pnl_pct

    return Trade(
        entry_time=entry_time,
        exit_time=exit_time,
        entry_price=entry_price,
        exit_price=exit_price,
        direction=direction,
        pnl=pnl,
        pnl_pct=pnl_pct,
        signal_value=signal_value,
    )


def calculate_pnl(
    trades: list[Trade], initial_capital: float
) -> tuple[float, list[float]]:
    """Calculate total P&L and equity curve from trades.

    Args:
        trades: List of executed trades
        initial_capital: Starting capital

    Returns:
        Tuple of (total_return_pct, equity_curve)
    """
    equity = initial_capital
    equity_curve = [equity]

    for trade in trades:
        equity += trade.pnl
        equity_curve.append(equity)

    # Guard against division by zero (only exactly 0, allow negative capital)
    if initial_capital == 0:
        total_return = 0.0
    else:
        total_return = (equity - initial_capital) / initial_capital
    return total_return, equity_curve


def run_backtest(
    config: BacktestConfig,
    prices: Optional[list] = None,  # List[PricePoint]
) -> BacktestResult:
    """Execute backtest simulation.

    Args:
        config: Backtest configuration
        prices: Optional list of PricePoint objects. If None, loads from data sources.

    Returns:
        BacktestResult with trades, metrics, and equity curve
    """
    # Load prices if not provided
    if prices is None:
        from scripts.backtest.data_loader import load_historical_data

        data = load_historical_data(config.start_date, config.end_date)
        prices = data.prices

    if not prices:
        return BacktestResult(config=config)

    # Sort prices by timestamp
    prices = sorted(prices, key=lambda p: p.timestamp)

    trades = []
    equity = config.initial_capital
    timestamps = []
    equity_curve = [equity]

    current_position: Optional[str] = None  # "LONG" | "SHORT" | None
    entry_time: Optional[datetime] = None
    entry_price: Optional[float] = None
    entry_signal: Optional[float] = None

    for i, price_point in enumerate(prices):
        signal = price_point.signal_value
        action = get_signal_action(signal, config.buy_threshold, config.sell_threshold)
        current_price = price_point.utxoracle_price
        timestamps.append(price_point.timestamp)

        # Close existing position if signal changes
        if current_position is not None:
            should_close = False

            if current_position == "LONG" and action == "SELL":
                should_close = True
            elif current_position == "SHORT" and action == "BUY":
                should_close = True
            elif action == "HOLD" and i == len(prices) - 1:
                # Close at end of backtest
                should_close = True
            elif i == len(prices) - 1:
                # Force close at end
                should_close = True

            if should_close and entry_time and entry_price is not None:
                trade = execute_trade(
                    entry_time=entry_time,
                    entry_price=entry_price,
                    exit_time=price_point.timestamp,
                    exit_price=current_price,
                    direction=current_position,
                    position_size=config.position_size,
                    transaction_cost=config.transaction_cost,
                    capital=equity,
                    signal_value=entry_signal or 0.0,
                )
                trades.append(trade)
                equity += trade.pnl
                equity_curve.append(equity)
                current_position = None
                entry_time = None
                entry_price = None
                entry_signal = None

        # Open new position
        if current_position is None and action in ("BUY", "SELL"):
            current_position = "LONG" if action == "BUY" else "SHORT"
            entry_time = price_point.timestamp
            entry_price = current_price
            entry_signal = signal

    # Calculate metrics
    total_return, _ = calculate_pnl(trades, config.initial_capital)

    win_rate = 0.0
    if trades:
        winning_trades = sum(1 for t in trades if t.pnl > 0)
        win_rate = winning_trades / len(trades)

    # Calculate average trade duration
    avg_duration = 0.0
    if trades:
        total_hours = sum(
            (t.exit_time - t.entry_time).total_seconds() / 3600 for t in trades
        )
        avg_duration = total_hours / len(trades)

    return BacktestResult(
        config=config,
        trades=trades,
        equity_curve=equity_curve,
        timestamps=timestamps,
        total_return=total_return,
        win_rate=win_rate,
        num_trades=len(trades),
        avg_trade_duration=avg_duration,
    )


def compare_signals(
    signals: dict[str, list[float]],
    prices: list,  # List[PricePoint]
    start_date: datetime,
    end_date: datetime,
    buy_threshold: float = 0.3,
    sell_threshold: float = -0.3,
    initial_capital: float = 10000.0,
    transaction_cost: float = 0.001,
) -> ComparisonResult:
    """Compare multiple signal sources side-by-side.

    Args:
        signals: Dictionary of signal_name -> list of signal values
        prices: List of PricePoint objects
        start_date: Start date for backtest
        end_date: End date for backtest
        buy_threshold: Signal threshold for buy
        sell_threshold: Signal threshold for sell
        initial_capital: Starting capital
        transaction_cost: Transaction cost per trade

    Returns:
        ComparisonResult with results for each signal, ranked by Sharpe
    """
    from scripts.backtest.metrics import calculate_returns, sharpe_ratio
    from scripts.backtest.data_loader import PricePoint

    results: dict[str, BacktestResult] = {}

    for signal_name, signal_values in signals.items():
        # Create price points with this signal's values
        signal_prices = []
        for i, price in enumerate(prices):
            if i < len(signal_values):
                signal_prices.append(
                    PricePoint(
                        timestamp=price.timestamp,
                        utxoracle_price=price.utxoracle_price,
                        exchange_price=price.exchange_price,
                        confidence=price.confidence,
                        signal_value=signal_values[i],
                    )
                )
            else:
                signal_prices.append(price)

        # Run backtest for this signal
        config = BacktestConfig(
            start_date=start_date,
            end_date=end_date,
            signal_source=signal_name,
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            initial_capital=initial_capital,
            transaction_cost=transaction_cost,
        )

        result = run_backtest(config, prices=signal_prices)

        # Calculate Sharpe for this result
        if result.equity_curve:
            returns = calculate_returns(result.equity_curve)
            result.sharpe_ratio = sharpe_ratio(returns)

        results[signal_name] = result

    # Rank by Sharpe ratio (descending)
    ranking = sorted(
        results.keys(),
        key=lambda s: results[s].sharpe_ratio,
        reverse=True,
    )

    best_signal = ranking[0] if ranking else ""
    best_sharpe = results[best_signal].sharpe_ratio if best_signal else 0.0

    return ComparisonResult(
        signals=list(signals.keys()),
        results=results,
        ranking=ranking,
        best_signal=best_signal,
        best_sharpe=best_sharpe,
    )
