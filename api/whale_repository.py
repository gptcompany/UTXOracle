"""
Repository pattern for whale dashboard data access.
Tasks T035-T037: Database repository with transaction and net flow storage.
"""

import duckdb
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path

from api.config import DUCKDB_PATH, setup_logging
from api.models.data import WhaleTransaction, NetFlowMetrics, Alert

# Set up module logger
logger = setup_logging(__name__)


class WhaleRepository:
    """
    Repository for whale dashboard data access.
    Task T035: Database repository pattern.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize repository with database connection.

        Args:
            db_path: Path to DuckDB database file (default from config)
        """
        self.db_path = db_path or DUCKDB_PATH

        # Ensure database directory exists
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized whale repository: {self.db_path}")

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Get database connection."""
        return duckdb.connect(self.db_path)

    # ========================================
    # Whale Transactions
    # Task T036: Transaction storage
    # ========================================

    def save_transaction(self, transaction: WhaleTransaction) -> bool:
        """
        Save whale transaction to database.

        Args:
            transaction: WhaleTransaction model instance

        Returns:
            True if successful, False otherwise
        """
        try:
            conn = self._get_connection()

            # Convert to database format
            data = transaction.to_db_dict()

            # Insert transaction (replace if exists)
            conn.execute(
                """
                INSERT OR REPLACE INTO whale_transactions (
                    transaction_id, block_height, timestamp, amount_btc, amount_usd,
                    direction, urgency_score, fee_rate, confidence, is_mempool, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    data["transaction_id"],
                    data["block_height"],
                    data["timestamp"],
                    data["amount_btc"],
                    data["amount_usd"],
                    data["direction"],
                    data["urgency_score"],
                    data["fee_rate"],
                    data["confidence"],
                    data["is_mempool"],
                    data["detected_at"],
                ],
            )

            conn.close()
            logger.debug(f"Saved transaction: {transaction.transaction_id}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to save transaction {transaction.transaction_id}: {e}"
            )
            return False

    def save_transactions_batch(self, transactions: List[WhaleTransaction]) -> int:
        """
        Batch save multiple transactions.

        Args:
            transactions: List of WhaleTransaction instances

        Returns:
            Number of successfully saved transactions
        """
        if not transactions:
            return 0

        success_count = 0

        try:
            conn = self._get_connection()

            # Prepare batch data
            values = [tx.to_db_dict() for tx in transactions]

            # Batch insert
            conn.executemany(
                """
                INSERT OR REPLACE INTO whale_transactions (
                    transaction_id, block_height, timestamp, amount_btc, amount_usd,
                    direction, urgency_score, fee_rate, confidence, is_mempool, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        v["transaction_id"],
                        v["block_height"],
                        v["timestamp"],
                        v["amount_btc"],
                        v["amount_usd"],
                        v["direction"],
                        v["urgency_score"],
                        v["fee_rate"],
                        v["confidence"],
                        v["is_mempool"],
                        v["detected_at"],
                    )
                    for v in values
                ],
            )

            success_count = len(transactions)
            conn.close()

            logger.info(f"Batch saved {success_count} transactions")

        except Exception as e:
            logger.error(f"Failed to batch save transactions: {e}")

        return success_count

    def get_transaction(self, transaction_id: str) -> Optional[WhaleTransaction]:
        """
        Retrieve transaction by ID.

        Args:
            transaction_id: Transaction hash

        Returns:
            WhaleTransaction instance or None if not found
        """
        try:
            conn = self._get_connection()

            result = conn.execute(
                "SELECT * FROM whale_transactions WHERE transaction_id = ?",
                [transaction_id],
            ).fetchone()

            conn.close()

            if result:
                return self._row_to_transaction(result)
            return None

        except Exception as e:
            logger.error(f"Failed to get transaction {transaction_id}: {e}")
            return None

    def get_recent_transactions(
        self, limit: int = 100, mempool_only: bool = False
    ) -> List[WhaleTransaction]:
        """
        Get recent whale transactions.

        Args:
            limit: Maximum number of transactions to return
            mempool_only: If True, return only mempool transactions

        Returns:
            List of WhaleTransaction instances
        """
        try:
            conn = self._get_connection()

            query = "SELECT * FROM whale_transactions"
            if mempool_only:
                query += " WHERE is_mempool = true"
            query += " ORDER BY timestamp DESC LIMIT ?"

            results = conn.execute(query, [limit]).fetchall()
            conn.close()

            return [self._row_to_transaction(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get recent transactions: {e}")
            return []

    def get_transactions_by_timerange(
        self, start: datetime, end: datetime
    ) -> List[WhaleTransaction]:
        """
        Get transactions within time range.

        Args:
            start: Start datetime
            end: End datetime

        Returns:
            List of WhaleTransaction instances
        """
        try:
            conn = self._get_connection()

            results = conn.execute(
                """
                SELECT * FROM whale_transactions
                WHERE timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp DESC
                """,
                [start.isoformat(), end.isoformat()],
            ).fetchall()

            conn.close()

            return [self._row_to_transaction(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get transactions by timerange: {e}")
            return []

    def cleanup_old_transactions(self, retention_days: int = 30) -> int:
        """
        Remove transactions older than retention period.

        Args:
            retention_days: Number of days to retain

        Returns:
            Number of deleted transactions
        """
        try:
            conn = self._get_connection()

            cutoff = datetime.utcnow() - timedelta(days=retention_days)

            result = conn.execute(
                "DELETE FROM whale_transactions WHERE timestamp < ?",
                [cutoff.isoformat()],
            )

            deleted = result.fetchone()[0] if result else 0
            conn.close()

            logger.info(f"Cleaned up {deleted} old transactions")
            return deleted

        except Exception as e:
            logger.error(f"Failed to cleanup transactions: {e}")
            return 0

    # ========================================
    # Net Flow Metrics
    # Task T037: Net flow storage
    # ========================================

    def save_net_flow(self, metrics: NetFlowMetrics) -> bool:
        """
        Save net flow metrics to database.

        Args:
            metrics: NetFlowMetrics model instance

        Returns:
            True if successful, False otherwise
        """
        try:
            conn = self._get_connection()

            data = metrics.to_db_dict()

            conn.execute(
                """
                INSERT OR REPLACE INTO net_flow_metrics (
                    period_start, period_end, interval, net_flow_btc, net_flow_usd,
                    total_buy_btc, total_sell_btc, transaction_count, direction,
                    strength, largest_tx_btc, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    data["period_start"],
                    data["period_end"],
                    data["interval"],
                    data["net_flow_btc"],
                    data["net_flow_usd"],
                    data["total_buy_btc"],
                    data["total_sell_btc"],
                    data["transaction_count"],
                    data["direction"],
                    data["strength"],
                    data["largest_tx_btc"],
                    data["created_at"],
                ],
            )

            conn.close()
            logger.debug(f"Saved net flow: {metrics.interval} @ {metrics.period_start}")
            return True

        except Exception as e:
            logger.error(f"Failed to save net flow metrics: {e}")
            return False

    def get_net_flow_latest(
        self, interval: str = "5m", limit: int = 100
    ) -> List[NetFlowMetrics]:
        """
        Get latest net flow metrics for interval.

        Args:
            interval: Aggregation interval (1m, 5m, 1h, 24h)
            limit: Maximum number of records

        Returns:
            List of NetFlowMetrics instances
        """
        try:
            conn = self._get_connection()

            results = conn.execute(
                """
                SELECT * FROM net_flow_metrics
                WHERE interval = ?
                ORDER BY period_start DESC
                LIMIT ?
                """,
                [interval, limit],
            ).fetchall()

            conn.close()

            return [self._row_to_netflow(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get net flow metrics: {e}")
            return []

    def get_net_flow_timerange(
        self, start: datetime, end: datetime, interval: str = "5m"
    ) -> List[NetFlowMetrics]:
        """
        Get net flow metrics for time range.

        Args:
            start: Start datetime
            end: End datetime
            interval: Aggregation interval

        Returns:
            List of NetFlowMetrics instances
        """
        try:
            conn = self._get_connection()

            results = conn.execute(
                """
                SELECT * FROM net_flow_metrics
                WHERE interval = ? AND period_start >= ? AND period_end <= ?
                ORDER BY period_start ASC
                """,
                [interval, start.isoformat(), end.isoformat()],
            ).fetchall()

            conn.close()

            return [self._row_to_netflow(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get net flow by timerange: {e}")
            return []

    # ========================================
    # Alerts
    # ========================================

    def save_alert(self, alert: Alert) -> bool:
        """Save alert to database."""
        try:
            conn = self._get_connection()

            data = alert.to_db_dict()

            conn.execute(
                """
                INSERT OR REPLACE INTO alerts (
                    alert_id, transaction_id, severity, trigger_type, threshold_value,
                    title, message, amount_btc, amount_usd, direction,
                    acknowledged, acknowledged_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    data["alert_id"],
                    data["transaction_id"],
                    data["severity"],
                    data["trigger_type"],
                    data["threshold_value"],
                    data["title"],
                    data["message"],
                    data["amount_btc"],
                    data["amount_usd"],
                    data["direction"],
                    data["acknowledged"],
                    data["acknowledged_at"],
                    data["created_at"],
                ],
            )

            conn.close()
            logger.debug(f"Saved alert: {alert.alert_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save alert: {e}")
            return False

    def get_unacknowledged_alerts(self, limit: int = 50) -> List[Alert]:
        """Get unacknowledged alerts ordered by severity and time."""
        try:
            conn = self._get_connection()

            results = conn.execute(
                """
                SELECT * FROM alerts
                WHERE acknowledged = false
                ORDER BY
                    CASE severity
                        WHEN 'CRITICAL' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3
                        WHEN 'LOW' THEN 4
                    END,
                    created_at DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()

            conn.close()

            return [self._row_to_alert(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get unacknowledged alerts: {e}")
            return []

    # ========================================
    # Utility Methods
    # ========================================

    def _row_to_transaction(self, row: tuple) -> WhaleTransaction:
        """Convert database row to WhaleTransaction model."""
        from decimal import Decimal

        return WhaleTransaction(
            transaction_id=row[0],
            block_height=row[1],
            timestamp=row[2],  # DuckDB returns datetime objects directly
            amount_btc=Decimal(str(row[3])),
            amount_usd=Decimal(str(row[4])),
            direction=row[5],
            urgency_score=row[6],
            fee_rate=row[7],
            confidence=row[8],
            is_mempool=row[9],
            detected_at=row[10],  # DuckDB returns datetime objects directly
        )

    def _row_to_netflow(self, row: tuple) -> NetFlowMetrics:
        """Convert database row to NetFlowMetrics model."""
        from decimal import Decimal

        return NetFlowMetrics(
            period_start=row[0],  # DuckDB returns datetime objects directly
            period_end=row[1],  # DuckDB returns datetime objects directly
            interval=row[2],
            net_flow_btc=Decimal(str(row[3])),
            net_flow_usd=Decimal(str(row[4])),
            total_buy_btc=Decimal(str(row[5])),
            total_sell_btc=Decimal(str(row[6])),
            transaction_count=row[7],
            direction=row[8],
            strength=row[9],
            largest_tx_btc=Decimal(str(row[10])) if row[10] else None,
            created_at=row[11],  # DuckDB returns datetime objects directly
        )

    def _row_to_alert(self, row: tuple) -> Alert:
        """Convert database row to Alert model."""
        from decimal import Decimal

        return Alert(
            alert_id=row[0],
            transaction_id=row[1],
            severity=row[2],
            trigger_type=row[3],
            threshold_value=Decimal(str(row[4])),
            title=row[5],
            message=row[6],
            amount_btc=Decimal(str(row[7])),
            amount_usd=Decimal(str(row[8])),
            direction=row[9],
            acknowledged=row[10],
            acknowledged_at=row[
                11
            ],  # DuckDB returns datetime objects directly (or None)
            created_at=row[12],  # DuckDB returns datetime objects directly
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            conn = self._get_connection()

            stats = {}

            # Transaction count
            stats["total_transactions"] = conn.execute(
                "SELECT COUNT(*) FROM whale_transactions"
            ).fetchone()[0]

            stats["mempool_transactions"] = conn.execute(
                "SELECT COUNT(*) FROM whale_transactions WHERE is_mempool = true"
            ).fetchone()[0]

            # Net flow records
            stats["total_netflow_records"] = conn.execute(
                "SELECT COUNT(*) FROM net_flow_metrics"
            ).fetchone()[0]

            # Alerts
            stats["total_alerts"] = conn.execute(
                "SELECT COUNT(*) FROM alerts"
            ).fetchone()[0]

            stats["unacknowledged_alerts"] = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE acknowledged = false"
            ).fetchone()[0]

            conn.close()

            return stats

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}


# Global repository instance
whale_repository = WhaleRepository()
