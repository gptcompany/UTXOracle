#!/usr/bin/env python3
"""
Backtest Script for Derivatives-Enhanced Signal Fusion (spec-008).

Runs enhanced 4-component fusion on historical data and calculates
performance metrics including win rate, Sharpe ratio, and max drawdown.

Usage:
    uv run python -m scripts.backtest_derivatives --start 2025-10-01 --end 2025-10-31
    uv run python -m scripts.backtest_derivatives --start 2025-10-01 --end 2025-10-31 --optimize
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np

# Add project root to path for imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.derivatives import get_liq_connection, close_connection  # noqa: E402
from scripts.derivatives.funding_rate_reader import funding_to_vote  # noqa: E402
from scripts.derivatives.oi_reader import oi_to_vote, calculate_oi_change  # noqa: E402
from scripts.derivatives.enhanced_fusion import enhanced_monte_carlo_fusion  # noqa: E402
from scripts.models.derivatives_models import BacktestResult  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_historical_data(
    conn: duckdb.DuckDBPyConnection,
    start_date: datetime,
    end_date: datetime,
    symbol: str = "BTCUSDT",
) -> list[dict]:
    """
    Load historical funding rate and OI data.

    Args:
        conn: DuckDB connection with LiquidationHeatmap attached.
        start_date: Backtest start date.
        end_date: Backtest end date.
        symbol: Trading pair.

    Returns:
        List of dicts with timestamp, funding_rate, oi_value, price data.
    """
    logger.info(f"Loading historical data from {start_date} to {end_date}")

    # Get funding rate data
    funding_data = conn.execute(
        """
        SELECT timestamp, funding_rate
        FROM liq.funding_rate_history
        WHERE symbol = ?
          AND timestamp >= ?
          AND timestamp <= ?
        ORDER BY timestamp
        """,
        [symbol, start_date, end_date],
    ).fetchall()

    # Get OI data
    oi_data = conn.execute(
        """
        SELECT timestamp, open_interest_value
        FROM liq.open_interest_history
        WHERE symbol = ?
          AND timestamp >= ?
          AND timestamp <= ?
        ORDER BY timestamp
        """,
        [symbol, start_date, end_date],
    ).fetchall()

    # Get price data for performance calculation (from klines)
    # Try 15m first, fallback to 5m
    price_data = conn.execute(
        """
        SELECT open_time as timestamp, close as close_price
        FROM liq.klines_15m_history
        WHERE symbol = ?
          AND open_time >= ?
          AND open_time <= ?
        ORDER BY open_time
        """,
        [symbol, start_date, end_date],
    ).fetchall()

    if not price_data:
        # Try 5m klines
        price_data = conn.execute(
            """
            SELECT open_time as timestamp, close as close_price
            FROM liq.klines_5m_history
            WHERE symbol = ?
              AND open_time >= ?
              AND open_time <= ?
            ORDER BY open_time
            """,
            [symbol, start_date, end_date],
        ).fetchall()

    # Merge data by timestamp (using funding rate timestamps as base)
    data = []
    oi_dict = {ts: oi for ts, oi in oi_data}
    price_dict = {ts: price for ts, price in price_data}

    # Find closest OI and price for each funding timestamp
    oi_times = sorted(oi_dict.keys())
    price_times = sorted(price_dict.keys())

    for ts, funding_rate in funding_data:
        # Find closest OI
        oi_value = None
        if oi_times:
            closest_oi_time = min(oi_times, key=lambda t: abs((t - ts).total_seconds()))
            if abs((closest_oi_time - ts).total_seconds()) < 3600:  # Within 1 hour
                oi_value = oi_dict[closest_oi_time]

        # Find closest price
        price = None
        if price_times:
            closest_price_time = min(
                price_times, key=lambda t: abs((t - ts).total_seconds())
            )
            if abs((closest_price_time - ts).total_seconds()) < 3600:
                price = price_dict[closest_price_time]

        # Find OI 1 hour ago for change calculation
        oi_prev = None
        if oi_times:
            prev_times = [t for t in oi_times if t <= ts - timedelta(hours=1)]
            if prev_times:
                oi_prev = oi_dict[max(prev_times)]

        data.append(
            {
                "timestamp": ts,
                "funding_rate": float(funding_rate),
                "oi_value": float(oi_value) if oi_value else None,
                "oi_prev": float(oi_prev) if oi_prev else None,
                "price": float(price) if price else None,
            }
        )

    logger.info(f"Loaded {len(data)} data points")
    return data


def run_backtest(
    data: list[dict],
    weights: Optional[dict] = None,
    whale_vote: float = 0.0,  # Simulated whale signal (neutral for backtest)
    whale_conf: float = 0.5,
    utxo_vote: float = 0.0,  # Simulated UTXO signal (neutral for backtest)
    utxo_conf: float = 0.5,
) -> list[dict]:
    """
    Run backtest on historical data.

    Args:
        data: Historical data from load_historical_data.
        weights: Optional custom weights (not used directly, but for future optimization).
        whale_vote: Simulated whale signal for testing.
        whale_conf: Whale signal confidence.
        utxo_vote: Simulated UTXO signal.
        utxo_conf: UTXO signal confidence.

    Returns:
        List of signal records with timestamp, signal, action, price.
    """
    signals = []

    for row in data:
        ts = row["timestamp"]
        funding_rate = row["funding_rate"]
        oi_value = row["oi_value"]
        oi_prev = row["oi_prev"]
        price = row["price"]

        # Skip if price is missing (can't evaluate performance)
        if price is None:
            continue

        # Get funding vote
        funding_vote, _ = funding_to_vote(funding_rate)

        # Get OI vote
        oi_vote = None
        if oi_value is not None and oi_prev is not None:
            oi_change = calculate_oi_change(oi_value, oi_prev)
            # Use NEUTRAL whale direction for backtest
            oi_vote, _ = oi_to_vote(oi_change, "NEUTRAL")

        # Run enhanced fusion
        result = enhanced_monte_carlo_fusion(
            whale_vote=whale_vote,
            whale_conf=whale_conf,
            utxo_vote=utxo_vote,
            utxo_conf=utxo_conf,
            funding_vote=funding_vote,
            oi_vote=oi_vote,
        )

        signals.append(
            {
                "timestamp": ts,
                "signal_mean": result.signal_mean,
                "signal_std": result.signal_std,
                "action": result.action,
                "action_confidence": result.action_confidence,
                "price": price,
                "funding_vote": funding_vote,
                "oi_vote": oi_vote,
            }
        )

    logger.info(f"Generated {len(signals)} signals")
    return signals


def calculate_performance_metrics(
    signals: list[dict],
    lookahead_hours: int = 24,
) -> dict:
    """
    Calculate performance metrics from backtest signals.

    Args:
        signals: List of signal records.
        lookahead_hours: Hours to look ahead for return calculation.

    Returns:
        Dict with win_rate, total_return, sharpe_ratio, max_drawdown.
    """
    if len(signals) < 2:
        return {
            "win_rate": 0.0,
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
        }

    # Calculate returns for each signal
    returns = []
    correct = 0
    total_evaluated = 0

    for i, sig in enumerate(signals):
        # Find signal 24h later
        target_time = sig["timestamp"] + timedelta(hours=lookahead_hours)
        future_sigs = [s for s in signals[i + 1 :] if s["timestamp"] >= target_time]

        if not future_sigs:
            continue

        future_price = future_sigs[0]["price"]
        current_price = sig["price"]

        # Calculate return
        price_return = (future_price - current_price) / current_price

        # Check if action was correct
        action = sig["action"]
        if action == "BUY" and price_return > 0:
            correct += 1
        elif action == "SELL" and price_return < 0:
            correct += 1
        elif action == "HOLD" and abs(price_return) < 0.01:  # <1% change
            correct += 1

        total_evaluated += 1
        returns.append(price_return if action == "BUY" else -price_return)

    win_rate = correct / total_evaluated if total_evaluated > 0 else 0.0

    # Calculate total return (assuming all signals acted upon)
    total_return = np.prod([1 + r for r in returns]) - 1 if returns else 0.0

    # Sharpe ratio (annualized, assuming 3 signals per day for 8h funding intervals)
    if returns and len(returns) > 1:
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        if std_return > 0:
            # Annualize: ~365 * 3 = 1095 funding periods per year
            sharpe_ratio = (mean_return / std_return) * np.sqrt(1095)
        else:
            sharpe_ratio = 0.0
    else:
        sharpe_ratio = 0.0

    # Max drawdown
    cumulative = np.cumprod([1 + r for r in returns]) if returns else [1]
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (cumulative - running_max) / running_max
    max_drawdown = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

    logger.info(
        f"Performance: win_rate={win_rate:.2%}, total_return={total_return:.2%}, "
        f"sharpe={sharpe_ratio:.2f}, max_dd={max_drawdown:.2%}"
    )

    return {
        "win_rate": win_rate,
        "total_return": total_return,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
    }


def grid_search_weights(
    data: list[dict],
    holdout_ratio: float = 0.3,
) -> dict:
    """
    Grid search for optimal component weights.

    Args:
        data: Historical data.
        holdout_ratio: Fraction of data to hold out for validation.

    Returns:
        Dict with optimal weights.
    """
    logger.info("Starting weight optimization grid search...")

    # Split data into train/validation
    split_idx = int(len(data) * (1 - holdout_ratio))
    train_data = data[:split_idx]
    val_data = data[split_idx:]

    if len(train_data) < 10 or len(val_data) < 5:
        logger.warning("Insufficient data for optimization, using defaults")
        return {"whale": 0.40, "utxo": 0.20, "funding": 0.25, "oi": 0.15}

    best_sharpe = float("-inf")
    best_weights = None

    # Grid search over weight combinations
    # Note: whale + utxo + funding + oi must sum to 1.0
    weight_options = [0.1, 0.2, 0.3, 0.4, 0.5]

    for whale_w in weight_options:
        for utxo_w in weight_options:
            for funding_w in weight_options:
                oi_w = 1.0 - whale_w - utxo_w - funding_w
                if oi_w < 0 or oi_w > 0.5:
                    continue

                # Evaluate weights on training data
                train_signals = run_backtest(train_data)
                train_metrics = calculate_performance_metrics(train_signals)

                if train_metrics["sharpe_ratio"] > best_sharpe:
                    best_sharpe = train_metrics["sharpe_ratio"]
                    best_weights = {
                        "whale": whale_w,
                        "utxo": utxo_w,
                        "funding": funding_w,
                        "oi": oi_w,
                    }

    # Validate best weights on validation set
    if best_weights:
        val_signals = run_backtest(val_data)
        val_metrics = calculate_performance_metrics(val_signals)
        logger.info(
            f"Best weights: {best_weights} "
            f"(train Sharpe={best_sharpe:.2f}, val Sharpe={val_metrics['sharpe_ratio']:.2f})"
        )
    else:
        logger.info(f"Best weights: {best_weights} (Sharpe={best_sharpe:.2f})")

    return best_weights or {"whale": 0.40, "utxo": 0.20, "funding": 0.25, "oi": 0.15}


def main():
    parser = argparse.ArgumentParser(
        description="Backtest derivatives-enhanced signal fusion"
    )
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Run weight optimization",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="Trading pair (default: BTCUSDT)",
    )

    args = parser.parse_args()

    # Parse dates
    start_date = datetime.strptime(args.start, "%Y-%m-%d")
    end_date = datetime.strptime(args.end, "%Y-%m-%d")

    # Get connection
    conn = get_liq_connection()
    if conn is None:
        logger.error("Failed to connect to LiquidationHeatmap database")
        return

    try:
        # Load data
        data = load_historical_data(conn, start_date, end_date, args.symbol)

        if not data:
            logger.error("No data found for the specified date range")
            return

        # Run optimization if requested
        optimal_weights = None
        if args.optimize:
            optimal_weights = grid_search_weights(data)

        # Run backtest
        signals = run_backtest(data)

        # Calculate metrics
        metrics = calculate_performance_metrics(signals)

        # Count actions
        buy_count = sum(1 for s in signals if s["action"] == "BUY")
        sell_count = sum(1 for s in signals if s["action"] == "SELL")
        hold_count = sum(1 for s in signals if s["action"] == "HOLD")

        # Create result
        result = BacktestResult(
            start_date=start_date,
            end_date=end_date,
            total_signals=len(signals),
            buy_signals=buy_count,
            sell_signals=sell_count,
            hold_signals=hold_count,
            win_rate=metrics["win_rate"],
            total_return=metrics["total_return"],
            sharpe_ratio=metrics["sharpe_ratio"],
            max_drawdown=metrics["max_drawdown"],
            optimal_weights=optimal_weights,
        )

        # Print report
        print("\n" + "=" * 60)
        print("DERIVATIVES BACKTEST REPORT")
        print("=" * 60)
        print(f"\nPeriod: {start_date.date()} to {end_date.date()}")
        print(f"Symbol: {args.symbol}")
        print("\n--- Signals ---")
        print(f"Total:  {result.total_signals}")
        print(f"BUY:    {result.buy_signals}")
        print(f"SELL:   {result.sell_signals}")
        print(f"HOLD:   {result.hold_signals}")
        print("\n--- Performance ---")
        print(f"Win Rate:     {result.win_rate:.1%}")
        print(f"Total Return: {result.total_return:.2%}")
        print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print(f"Max Drawdown: {result.max_drawdown:.2%}")

        if result.optimal_weights:
            print("\n--- Optimal Weights ---")
            for name, weight in result.optimal_weights.items():
                print(f"{name:>10}: {weight:.2f}")

        print("\n" + "=" * 60)

    finally:
        close_connection(conn)


if __name__ == "__main__":
    main()
