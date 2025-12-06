"""
On-Chain Metrics Module (spec-007 + spec-009)

This module provides on-chain metrics for UTXOracle:

Spec-007 (Core Metrics):
1. Monte Carlo Signal Fusion - Bootstrap sampling with 95% CI
2. Active Addresses - Unique addresses per block/day
3. TX Volume USD - Transaction volume using UTXOracle price

Spec-009 (Advanced Analytics):
4. Symbolic Dynamics - Permutation entropy and pattern detection
5. Power Law - Regime detection via MLE + KS validation
6. Fractal Dimension - Box-counting structure analysis
7. Enhanced Fusion - 7-component weighted signal fusion

Usage:
    from scripts.metrics import save_metrics_to_db, load_metrics_from_db
    from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion, enhanced_fusion
    from scripts.metrics.active_addresses import count_active_addresses
    from scripts.metrics.tx_volume import calculate_tx_volume
    from scripts.metrics.symbolic_dynamics import analyze as symbolic_analyze
    from scripts.metrics.power_law import fit as power_law_fit
    from scripts.metrics.fractal_dimension import analyze as fractal_analyze
"""

from datetime import datetime
from typing import Optional
import duckdb

# Database path (same as daily_analysis.py)
DEFAULT_DB_PATH = "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"


def save_metrics_to_db(
    timestamp: datetime,
    monte_carlo: Optional[dict] = None,
    active_addresses: Optional[dict] = None,
    tx_volume: Optional[dict] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """
    Save metrics bundle to DuckDB.

    Args:
        timestamp: Timestamp for the metrics
        monte_carlo: Monte Carlo fusion result dict (optional)
        active_addresses: Active addresses metric dict (optional)
        tx_volume: TX volume metric dict (optional)
        db_path: Path to DuckDB database

    Returns:
        True if successful, False otherwise
    """
    try:
        conn = duckdb.connect(db_path)

        # Build INSERT statement with all columns
        columns = ["timestamp"]
        values = [timestamp]

        if monte_carlo:
            mc_cols = [
                "signal_mean",
                "signal_std",
                "ci_lower",
                "ci_upper",
                "action",
                "action_confidence",
                "n_samples",
                "distribution_type",
            ]
            for col in mc_cols:
                if col in monte_carlo:
                    columns.append(col)
                    values.append(monte_carlo[col])

        if active_addresses:
            aa_cols = [
                "block_height",
                "active_addresses_block",
                "active_addresses_24h",
                "unique_senders",
                "unique_receivers",
                "is_anomaly",
            ]
            for col in aa_cols:
                if col in active_addresses:
                    columns.append(col)
                    values.append(active_addresses[col])

        if tx_volume:
            tv_cols = [
                "tx_count",
                "tx_volume_btc",
                "tx_volume_usd",
                "utxoracle_price_used",
                "low_confidence",
            ]
            for col in tv_cols:
                if col in tx_volume:
                    columns.append(col)
                    values.append(tx_volume[col])

        placeholders = ", ".join(["?" for _ in values])
        col_str = ", ".join(columns)

        # Use INSERT with ON CONFLICT for upsert behavior
        # Specify timestamp as the conflict target since id is auto-generated
        conn.execute(
            f"""INSERT INTO metrics ({col_str}) VALUES ({placeholders})
                ON CONFLICT (timestamp) DO UPDATE SET {
                ", ".join([f"{c} = EXCLUDED.{c}" for c in columns if c != "timestamp"])
            }""",
            values,
        )
        conn.close()
        return True

    except Exception as e:
        print(f"Error saving metrics to DB: {e}")
        return False


def load_metrics_from_db(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    """
    Load metrics from DuckDB.

    Args:
        start_date: Optional start timestamp filter
        end_date: Optional end timestamp filter
        limit: Maximum number of records to return
        db_path: Path to DuckDB database

    Returns:
        List of metric dictionaries ordered by timestamp DESC
    """
    try:
        conn = duckdb.connect(db_path, read_only=True)

        query = "SELECT * FROM metrics"
        conditions = []
        params = []

        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += f" ORDER BY timestamp DESC LIMIT {limit}"

        result = conn.execute(query, params).fetchall()
        columns = [desc[0] for desc in conn.description]
        conn.close()

        return [dict(zip(columns, row)) for row in result]

    except Exception as e:
        print(f"Error loading metrics from DB: {e}")
        return []


def get_latest_metrics(db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    """
    Get the most recent metrics record.

    Args:
        db_path: Path to DuckDB database

    Returns:
        Latest metrics dict or None if not found
    """
    metrics = load_metrics_from_db(limit=1, db_path=db_path)
    return metrics[0] if metrics else None
