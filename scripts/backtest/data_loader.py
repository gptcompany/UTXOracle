"""Data loading utilities for backtesting.

Loads historical price and signal data from DuckDB and HTML fallback.
"""

import re
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional


@dataclass
class PricePoint:
    """Single price observation."""

    timestamp: datetime
    utxoracle_price: float
    exchange_price: Optional[float] = None
    confidence: float = 0.0
    signal_value: Optional[float] = None  # Combined/fusion signal


@dataclass
class HistoricalData:
    """Container for loaded historical data."""

    prices: list[PricePoint]
    start_date: datetime
    end_date: datetime
    source: str  # "duckdb" | "html" | "mixed"


# Default paths
DEFAULT_DB_PATH = "data/utxoracle.duckdb"
DEFAULT_HTML_DIR = "historical_data/html_files"


def load_from_duckdb(
    start_date: datetime,
    end_date: datetime,
    db_path: str = DEFAULT_DB_PATH,
) -> list[PricePoint]:
    """Load price data from DuckDB price_analysis table.

    Args:
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        db_path: Path to DuckDB database

    Returns:
        List of PricePoint objects sorted by timestamp
    """
    try:
        import duckdb
    except ImportError:
        return []

    if not Path(db_path).exists():
        return []

    conn = duckdb.connect(db_path, read_only=True)

    try:
        # Query price_analysis table (has date, not timestamp)
        query = """
            SELECT
                date,
                utxoracle_price,
                exchange_price,
                confidence,
                combined_signal
            FROM price_analysis
            WHERE date >= ? AND date <= ?
            ORDER BY date
        """
        result = conn.execute(
            query,
            [
                start_date.date() if isinstance(start_date, datetime) else start_date,
                end_date.date() if isinstance(end_date, datetime) else end_date,
            ],
        ).fetchall()

        prices = []
        for row in result:
            dt, utx_price, exch_price, conf, signal = row
            # Convert date to datetime at midnight
            if isinstance(dt, date) and not isinstance(dt, datetime):
                dt = datetime.combine(dt, datetime.min.time())
            prices.append(
                PricePoint(
                    timestamp=dt,
                    utxoracle_price=float(utx_price) if utx_price else 0.0,
                    exchange_price=float(exch_price) if exch_price else None,
                    confidence=float(conf) if conf else 0.0,
                    signal_value=float(signal) if signal else None,
                )
            )
        return prices
    finally:
        conn.close()


def load_from_html(
    start_date: datetime,
    end_date: datetime,
    html_dir: str = DEFAULT_HTML_DIR,
) -> list[PricePoint]:
    """Load price data from historical HTML files.

    Parses UTXOracle_YYYY-MM-DD.html files for price data.

    Args:
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        html_dir: Directory containing HTML files

    Returns:
        List of PricePoint objects sorted by timestamp
    """
    html_path = Path(html_dir)
    if not html_path.exists():
        return []

    prices = []
    current = start_date.date() if isinstance(start_date, datetime) else start_date
    end = end_date.date() if isinstance(end_date, datetime) else end_date

    while current <= end:
        filename = f"UTXOracle_{current.strftime('%Y-%m-%d')}.html"
        filepath = html_path / filename

        if filepath.exists():
            price_point = _parse_html_file(filepath, current)
            if price_point:
                prices.append(price_point)

        current = date(current.year, current.month, current.day)
        # Increment by one day
        from datetime import timedelta

        current = current + timedelta(days=1)

    return sorted(prices, key=lambda p: p.timestamp)


def _parse_html_file(filepath: Path, file_date: date) -> Optional[PricePoint]:
    """Parse a single HTML file for price data.

    Extracts UTXOracle price and confidence from HTML content.
    """
    try:
        content = filepath.read_text(encoding="utf-8")

        # Pattern for price: "price: $XXX,XXX" or similar
        price_pattern = r"price[:\s]+\$?([\d,]+(?:\.\d+)?)"
        price_match = re.search(price_pattern, content, re.IGNORECASE)

        # Pattern for confidence: "confidence: X.XX" or "conf: X.XX"
        conf_pattern = r"confidence[:\s]+([\d.]+)"
        conf_match = re.search(conf_pattern, content, re.IGNORECASE)

        if price_match:
            price_str = price_match.group(1).replace(",", "")
            price = float(price_str)

            confidence = 0.0
            if conf_match:
                confidence = float(conf_match.group(1))

            return PricePoint(
                timestamp=datetime.combine(file_date, datetime.min.time()),
                utxoracle_price=price,
                exchange_price=None,  # Not available in HTML
                confidence=confidence,
                signal_value=None,  # Not available in HTML
            )
    except (OSError, ValueError):
        pass  # Skip files that can't be parsed

    return None


def align_timestamps(
    prices: list[PricePoint],
    signals: list[tuple[datetime, float]],
) -> list[tuple[PricePoint, float]]:
    """Align price data with signal data by timestamp.

    For each signal, finds the closest price observation.

    Args:
        prices: List of price points
        signals: List of (timestamp, signal_value) tuples

    Returns:
        List of (PricePoint, signal_value) tuples
    """
    if not prices or not signals:
        return []

    # Sort both by timestamp
    sorted_prices = sorted(prices, key=lambda p: p.timestamp)
    sorted_signals = sorted(signals, key=lambda s: s[0])

    aligned = []
    price_idx = 0

    for signal_time, signal_value in sorted_signals:
        # Find closest price (forward search)
        best_price = None
        best_diff = float("inf")

        for i in range(price_idx, len(sorted_prices)):
            price = sorted_prices[i]
            diff = abs((price.timestamp - signal_time).total_seconds())

            if diff < best_diff:
                best_diff = diff
                best_price = price
                price_idx = i
            elif diff > best_diff:
                # Past minimum, stop searching
                break

        if best_price:
            aligned.append((best_price, signal_value))

    return aligned


def load_historical_data(
    start_date: datetime,
    end_date: datetime,
    db_path: str = DEFAULT_DB_PATH,
    html_dir: str = DEFAULT_HTML_DIR,
    prefer_duckdb: bool = True,
) -> HistoricalData:
    """Load historical data with automatic fallback.

    Tries DuckDB first, falls back to HTML files for missing dates.

    Args:
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        db_path: Path to DuckDB database
        html_dir: Directory containing HTML files
        prefer_duckdb: If True, try DuckDB first

    Returns:
        HistoricalData container with loaded prices
    """
    prices = []
    source = "none"

    if prefer_duckdb:
        prices = load_from_duckdb(start_date, end_date, db_path)
        if prices:
            source = "duckdb"

    # Fall back to HTML if no DuckDB data
    if not prices:
        prices = load_from_html(start_date, end_date, html_dir)
        if prices:
            source = "html"

    # If DuckDB has gaps, fill from HTML
    if source == "duckdb" and prices:
        # Check for gaps and fill from HTML
        html_prices = load_from_html(start_date, end_date, html_dir)
        if html_prices:
            # Create date set from DuckDB prices
            db_dates = {p.timestamp.date() for p in prices}
            # Add HTML prices for missing dates
            for hp in html_prices:
                if hp.timestamp.date() not in db_dates:
                    prices.append(hp)
                    source = "mixed"

    # Sort by timestamp
    prices = sorted(prices, key=lambda p: p.timestamp)

    return HistoricalData(
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        source=source if prices else "none",
    )


def save_backtest_result(
    result,  # BacktestResult
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Save backtest result to DuckDB.

    Args:
        result: BacktestResult to save
        db_path: Path to DuckDB database

    Returns:
        True if successful, False otherwise
    """
    try:
        import duckdb
        import json
    except ImportError:
        return False

    if not Path(db_path).exists():
        return False

    conn = duckdb.connect(db_path)

    try:
        # Serialize config and trades to JSON
        config_json = json.dumps(
            {
                "start_date": result.config.start_date.isoformat(),
                "end_date": result.config.end_date.isoformat(),
                "signal_source": result.config.signal_source,
                "buy_threshold": result.config.buy_threshold,
                "sell_threshold": result.config.sell_threshold,
                "position_size": result.config.position_size,
                "transaction_cost": result.config.transaction_cost,
                "initial_capital": result.config.initial_capital,
            }
        )

        trades_json = json.dumps(
            [
                {
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "direction": t.direction,
                    "pnl": t.pnl,
                    "pnl_pct": t.pnl_pct,
                    "signal_value": t.signal_value,
                }
                for t in result.trades
            ]
        )

        # Insert into database
        conn.execute(
            """
            INSERT INTO backtest_results (
                signal_source, start_date, end_date,
                total_return, sharpe_ratio, sortino_ratio,
                win_rate, max_drawdown, profit_factor,
                num_trades, config_json, trades_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [
                result.config.signal_source,
                result.config.start_date.date(),
                result.config.end_date.date(),
                result.total_return,
                result.sharpe_ratio,
                result.sortino_ratio,
                result.win_rate,
                result.max_drawdown,
                result.profit_factor,
                result.num_trades,
                config_json,
                trades_json,
            ],
        )

        conn.close()
        return True
    except Exception:
        conn.close()
        return False


def load_backtest_history(
    signal_source: Optional[str] = None,
    limit: int = 100,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Load historical backtest results from DuckDB.

    Args:
        signal_source: Filter by signal source (optional)
        limit: Maximum number of results to return
        db_path: Path to DuckDB database

    Returns:
        List of backtest result dictionaries
    """
    try:
        import duckdb
    except ImportError:
        return []

    if not Path(db_path).exists():
        return []

    conn = duckdb.connect(db_path, read_only=True)

    try:
        if signal_source:
            query = """
                SELECT * FROM backtest_results
                WHERE signal_source = ?
                ORDER BY run_timestamp DESC
                LIMIT ?
            """
            result = conn.execute(query, [signal_source, limit]).fetchall()
        else:
            query = """
                SELECT * FROM backtest_results
                ORDER BY run_timestamp DESC
                LIMIT ?
            """
            result = conn.execute(query, [limit]).fetchall()

        # Get column names
        columns = [
            desc[0] for desc in conn.execute("DESCRIBE backtest_results").fetchall()
        ]

        conn.close()

        # Convert to list of dicts
        return [dict(zip(columns, row, strict=False)) for row in result]
    except Exception:
        conn.close()
        return []
