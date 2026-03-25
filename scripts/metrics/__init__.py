"""
On-Chain Metrics Module (spec-007 + spec-009 + spec-010)

This module provides on-chain metrics for UTXOracle:

Spec-007 (Core Metrics):
1. Monte Carlo Signal Fusion - Bootstrap sampling with 95% CI
2. Active Addresses - Unique addresses per block/day
3. TX Volume USD - Transaction volume using UTXOracle price

Spec-009 (Advanced Analytics):
4. Symbolic Dynamics - Permutation entropy and pattern detection
5. Power Law - Regime detection via MLE + KS validation
6. Fractal Dimension - Box-counting structure analysis
7. Enhanced Fusion - 8-component weighted signal fusion

Spec-010 (Distribution Shift Detection):
8. Wasserstein Distance - Earth Mover's Distance for distribution shifts

Usage:
    from scripts.metrics import save_metrics_to_db, load_metrics_from_db
    from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion, enhanced_fusion
    from scripts.metrics.active_addresses import count_active_addresses
    from scripts.metrics.tx_volume import calculate_tx_volume
    from scripts.metrics.symbolic_dynamics import analyze as symbolic_analyze
    from scripts.metrics.power_law import fit as power_law_fit
    from scripts.metrics.fractal_dimension import analyze as fractal_analyze
    from scripts.metrics.wasserstein import rolling_wasserstein, wasserstein_vote
"""

from datetime import datetime
from typing import Optional, Any, Dict
import json
import logging

from api.questdb_repository import QuestDBRepository

logger = logging.getLogger(__name__)

# Initialize global repository instance for sync metrics operations
_repo = QuestDBRepository()


def save_metrics_to_db(
    timestamp: datetime,
    monte_carlo: Optional[dict] = None,
    active_addresses: Optional[dict] = None,
    tx_volume: Optional[dict] = None,
    wasserstein: Optional[dict] = None,
    db_path: Optional[str] = None,  # Obsolete, using QuestDB
) -> bool:
    """
    Save metrics bundle to QuestDB via ILP.

    Args:
        timestamp: Timestamp for the metrics
        monte_carlo: Monte Carlo fusion result dict (optional)
        active_addresses: Active addresses metric dict (optional)
        tx_volume: TX volume metric dict (optional)
        wasserstein: Wasserstein distance result dict (optional) - spec-010
        db_path: Path to database (Obsolete)

    Returns:
        True if successful, False otherwise
    """
    try:
        symbols = {}
        columns = {
            "created_at": datetime.utcnow()
        }

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
                    val = monte_carlo[col]
                    if col in ["action", "distribution_type"]:
                        symbols[col] = str(val)
                    else:
                        columns[col] = val

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
                    columns[col] = active_addresses[col]

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
                    columns[col] = tx_volume[col]

        # Wasserstein Distance columns (spec-010)
        if wasserstein:
            ws_cols = [
                ("mean_distance", "wasserstein_distance"),
                ("mean_normalized_distance", "wasserstein_normalized"),
                ("dominant_shift_direction", "wasserstein_shift_direction"),
                ("regime_status", "wasserstein_regime_status"),
                ("wasserstein_vote", "wasserstein_vote"),
                ("is_valid", "wasserstein_is_valid"),
            ]
            for src_col, db_col in ws_cols:
                if src_col in wasserstein:
                    val = wasserstein[src_col]
                    if db_col in ["wasserstein_shift_direction", "wasserstein_regime_status"]:
                        symbols[db_col] = str(val)
                    else:
                        columns[db_col] = val

        # Ingest via ILP
        # NOTE: ILP is append-only, no 'ON CONFLICT' equivalent.
        # Data points with same timestamp will be stored as separate rows.
        # QuestDB typically handles this with 'LATEST BY' queries.
        return _repo._send_row(
            "metrics",
            symbols=symbols,
            columns=columns,
            at=timestamp,
            flush=True # Flush metrics immediately for low-latency dashboards
        )

    except Exception as e:
        logger.error(f"Error saving metrics to QuestDB: {e}")
        return False


def load_metrics_from_db(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    db_path: Optional[str] = None,
) -> list[dict]:
    """
    Load metrics from QuestDB.
    Note: This is a synchronous wrapper around an async call. 
    In production environments, it is better to use the async repo methods directly.
    """
    import asyncio
    
    async def _async_load():
        if not _repo._pool:
            await _repo.initialize()
        
        query = "SELECT * FROM metrics"
        conditions = []
        params = []
        
        if start_date:
            conditions.append("ts >= $1")
            params.append(start_date)
            idx = 2
        else:
            idx = 1
            
        if end_date:
            conditions.append(f"ts <= ${idx}")
            params.append(end_date)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += f" ORDER BY ts DESC LIMIT {limit}"
        
        records = await _repo.fetch(query, *params)
        return [dict(r) for r in records]

    try:
        # Check if we are already in an event loop
        try:
            loop = asyncio.get_running_loop()
            # If in a loop, we can't block. This is a design conflict for sync metrics loading.
            # Fallback to a warning and empty list if called from within async.
            logger.warning("load_metrics_from_db called from async context, use repo.fetch directly.")
            return []
        except RuntimeError:
            return asyncio.run(_async_load())
    except Exception as e:
        logger.error(f"Error loading metrics from QuestDB: {e}")
        return []


def get_latest_metrics(db_path: Optional[str] = None) -> Optional[dict]:
    """
    Get the most recent metrics record.

    Args:
        db_path: Path to database (Obsolete)

    Returns:
        Latest metrics dict or None if not found
    """
    metrics = load_metrics_from_db(limit=1, db_path=db_path)
    return metrics[0] if metrics else None
