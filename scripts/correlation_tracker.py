#!/usr/bin/env python3
"""
Correlation Tracker - Historical Prediction Accuracy Monitoring
Tasks: T038-T042 - Track prediction outcomes and calculate accuracy metrics

Features:
- Monitor blockchain for transaction confirmations
- Record prediction outcomes to DuckDB (prediction_outcomes table)
- Calculate accuracy metrics (timing, urgency, overall)
- Track false positives/negatives
- Aggregate statistics (daily/weekly/monthly)
- 90-day retention with automatic cleanup

Architecture:
- Async blockchain monitoring via Bitcoin Core RPC or mempool.space API
- Integration with PredictionOutcome data model
- DB operations with retry logic
- Periodic aggregation tasks
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any
import sys

# Add parent dirs to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.models.prediction_outcome import PredictionOutcome, OutcomeType
from scripts.config.mempool_config import get_config
from scripts.utils.db_retry import with_db_retry

import duckdb
import aiohttp

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CorrelationTracker:
    """
    Tracks whale transaction prediction accuracy over time

    Monitors blockchain for transaction confirmations and records outcomes
    for accuracy analysis. Integrates with PredictionOutcome data model.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        mempool_api_url: str = "http://localhost:8999",
        check_interval_seconds: int = 60,
        retention_days: int = 90,
    ):
        """
        Initialize correlation tracker

        Args:
            db_path: Path to DuckDB database (default: from config)
            mempool_api_url: Mempool.space API URL for blockchain queries
            check_interval_seconds: Interval between confirmation checks (default: 60s)
            retention_days: Days to retain historical outcomes (default: 90)
        """
        config = get_config()
        self.db_path = db_path or config.database.db_path
        self.mempool_api_url = mempool_api_url.rstrip("/")
        self.check_interval = check_interval_seconds
        self.retention_days = retention_days

        # Statistics tracking
        self.stats = {
            "total_tracked": 0,
            "confirmed": 0,
            "dropped": 0,
            "replaced": 0,
            "pending": 0,
            "accurate_predictions": 0,
            "false_positives": 0,
            "false_negatives": 0,
        }

        # Active tracking (prediction_id -> last_check_time)
        self.active_predictions: Dict[str, datetime] = {}

        # Background tasks
        self._monitor_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info("Correlation tracker initialized")
        logger.info(f"Database: {self.db_path}")
        logger.info(f"Check interval: {check_interval_seconds}s")
        logger.info(f"Retention: {retention_days} days")

    async def start(self):
        """Start correlation tracking background tasks"""
        if self._running:
            logger.warning("Correlation tracker already running")
            return

        self._running = True
        logger.info("🚀 Starting correlation tracker...")

        # Load pending predictions from database
        await self._load_pending_predictions()

        # Start background monitoring task
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("✅ Monitoring task started")

        # Start cleanup task (runs daily)
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("✅ Cleanup task started")

    async def stop(self):
        """Stop correlation tracking background tasks"""
        if not self._running:
            return

        logger.info("🛑 Stopping correlation tracker...")
        self._running = False

        # Cancel background tasks
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("✅ Correlation tracker stopped")

    @with_db_retry(max_attempts=3)
    async def _load_pending_predictions(self):
        """Load pending predictions from database on startup"""
        try:
            conn = duckdb.connect(self.db_path)

            # Load predictions without outcomes yet (not in prediction_outcomes table)
            query = """
                SELECT prediction_id, detection_timestamp
                FROM mempool_predictions
                WHERE prediction_id NOT IN (
                    SELECT prediction_id FROM prediction_outcomes
                )
                AND detection_timestamp >= ?
                ORDER BY detection_timestamp DESC
            """

            cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
            result = conn.execute(query, [cutoff]).fetchall()
            conn.close()

            # Add to active tracking
            for row in result:
                prediction_id = row[0]
                detection_time = row[1]
                self.active_predictions[prediction_id] = detection_time
                self.stats["pending"] += 1

            logger.info(
                f"✅ Loaded {len(self.active_predictions)} pending predictions for tracking"
            )

        except Exception as e:
            logger.error(f"Failed to load pending predictions: {e}", exc_info=True)
            raise

    async def track_prediction(self, prediction_id: str, transaction_id: str):
        """
        Add a new prediction to track

        Args:
            prediction_id: Unique prediction ID
            transaction_id: Bitcoin transaction ID (txid)
        """
        if prediction_id in self.active_predictions:
            logger.debug(f"Prediction {prediction_id[:8]}... already tracked")
            return

        self.active_predictions[prediction_id] = datetime.now(timezone.utc)
        self.stats["total_tracked"] += 1
        self.stats["pending"] += 1

        logger.info(
            f"📊 Tracking prediction {prediction_id[:8]}... (txid: {transaction_id[:8]}...)"
        )

    async def _monitor_loop(self):
        """Background loop to check transaction confirmations"""
        logger.info("🔍 Starting prediction monitoring loop...")

        while self._running:
            try:
                await asyncio.sleep(self.check_interval)

                if not self.active_predictions:
                    logger.debug("No predictions to monitor")
                    continue

                # Check confirmations for all active predictions
                await self._check_confirmations()

            except asyncio.CancelledError:
                logger.info("Monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
                await asyncio.sleep(10)  # Backoff on error

    async def _check_confirmations(self):
        """Check blockchain for transaction confirmations"""
        logger.debug(f"Checking {len(self.active_predictions)} active predictions...")

        # Get predictions with transaction IDs from database
        predictions_to_check = await self._get_predictions_with_txids(
            list(self.active_predictions.keys())
        )

        for prediction_id, transaction_id in predictions_to_check:
            try:
                # Query blockchain for transaction status
                status = await self._get_transaction_status(transaction_id)

                if status["confirmed"]:
                    # Transaction confirmed - record outcome
                    await self._record_confirmation(prediction_id, status)

                elif status["dropped"]:
                    # Transaction dropped from mempool
                    await self._record_drop(prediction_id)

                elif status["replaced"]:
                    # Transaction replaced via RBF
                    await self._record_replacement(
                        prediction_id, status["replacement_txid"]
                    )

                # else: still pending, keep monitoring

            except Exception as e:
                logger.error(f"Error checking prediction {prediction_id[:8]}...: {e}")
                continue

    @with_db_retry(max_attempts=3)
    async def _get_predictions_with_txids(
        self, prediction_ids: List[str]
    ) -> List[tuple]:
        """Get transaction IDs for predictions"""
        try:
            conn = duckdb.connect(self.db_path)

            placeholders = ", ".join(["?"] * len(prediction_ids))
            query = f"""
                SELECT prediction_id, transaction_id
                FROM mempool_predictions
                WHERE prediction_id IN ({placeholders})
            """

            result = conn.execute(query, prediction_ids).fetchall()
            conn.close()

            return result

        except Exception as e:
            logger.error(f"Failed to get predictions: {e}", exc_info=True)
            return []

    async def _get_transaction_status(self, transaction_id: str) -> Dict[str, Any]:
        """
        Query blockchain for transaction status

        Returns:
            Dict with status: {
                'confirmed': bool,
                'dropped': bool,
                'replaced': bool,
                'confirmation_block': Optional[int],
                'confirmation_time': Optional[datetime],
                'replacement_txid': Optional[str]
            }
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Query mempool.space API for transaction
                url = f"{self.mempool_api_url}/api/tx/{transaction_id}"

                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 404:
                        # Transaction not found - likely dropped
                        return {
                            "confirmed": False,
                            "dropped": True,
                            "replaced": False,
                            "confirmation_block": None,
                            "confirmation_time": None,
                            "replacement_txid": None,
                        }

                    response.raise_for_status()
                    data = await response.json()

                    # Check if confirmed (has block hash)
                    confirmed = "status" in data and data["status"].get(
                        "confirmed", False
                    )
                    confirmation_block = (
                        data["status"].get("block_height") if confirmed else None
                    )
                    confirmation_time = (
                        datetime.fromtimestamp(
                            data["status"].get("block_time"), tz=timezone.utc
                        )
                        if confirmed and "block_time" in data["status"]
                        else None
                    )

                    return {
                        "confirmed": confirmed,
                        "dropped": False,
                        "replaced": False,  # TODO: Check for RBF replacement
                        "confirmation_block": confirmation_block,
                        "confirmation_time": confirmation_time,
                        "replacement_txid": None,
                    }

        except aiohttp.ClientError as e:
            logger.error(f"Failed to query transaction {transaction_id[:8]}...: {e}")
            # Assume still pending on network error
            return {
                "confirmed": False,
                "dropped": False,
                "replaced": False,
                "confirmation_block": None,
                "confirmation_time": None,
                "replacement_txid": None,
            }

    async def _record_confirmation(self, prediction_id: str, status: Dict[str, Any]):
        """Record transaction confirmation outcome"""
        logger.info(
            f"✅ Transaction confirmed for prediction {prediction_id[:8]}... at block {status['confirmation_block']}"
        )

        # Get original prediction from database
        prediction = await self._get_prediction(prediction_id)
        if not prediction:
            logger.error(f"Prediction {prediction_id} not found in database")
            return

        # Create outcome record
        outcome = PredictionOutcome(
            outcome_id=str(uuid.uuid4()),
            prediction_id=prediction_id,
            transaction_id=prediction["transaction_id"],
            outcome_type=OutcomeType.CONFIRMED,
            detection_timestamp=prediction["detection_timestamp"],
            outcome_timestamp=status["confirmation_time"],
            predicted_confirmation_block=prediction["predicted_confirmation_block"],
            actual_confirmation_block=status["confirmation_block"],
        )

        # Record to database
        await self._persist_outcome(outcome)

        # Update statistics
        self.active_predictions.pop(prediction_id, None)
        self.stats["confirmed"] += 1
        self.stats["pending"] -= 1

        if outcome.was_accurate:
            self.stats["accurate_predictions"] += 1

    async def _record_drop(self, prediction_id: str):
        """Record transaction dropped from mempool"""
        logger.info(f"❌ Transaction dropped for prediction {prediction_id[:8]}...")

        prediction = await self._get_prediction(prediction_id)
        if not prediction:
            return

        outcome = PredictionOutcome(
            outcome_id=str(uuid.uuid4()),
            prediction_id=prediction_id,
            transaction_id=prediction["transaction_id"],
            outcome_type=OutcomeType.DROPPED,
            detection_timestamp=prediction["detection_timestamp"],
            outcome_timestamp=datetime.now(timezone.utc),
            predicted_confirmation_block=prediction["predicted_confirmation_block"],
            actual_confirmation_block=None,
        )

        await self._persist_outcome(outcome)

        self.active_predictions.pop(prediction_id, None)
        self.stats["dropped"] += 1
        self.stats["pending"] -= 1
        self.stats["false_positives"] += 1

    async def _record_replacement(self, prediction_id: str, replacement_txid: str):
        """Record RBF transaction replacement"""
        logger.info(
            f"🔄 Transaction replaced for prediction {prediction_id[:8]}... → {replacement_txid[:8]}..."
        )

        prediction = await self._get_prediction(prediction_id)
        if not prediction:
            return

        outcome = PredictionOutcome(
            outcome_id=str(uuid.uuid4()),
            prediction_id=prediction_id,
            transaction_id=prediction["transaction_id"],
            outcome_type=OutcomeType.REPLACED,
            detection_timestamp=prediction["detection_timestamp"],
            outcome_timestamp=datetime.now(timezone.utc),
            predicted_confirmation_block=prediction["predicted_confirmation_block"],
            actual_confirmation_block=None,
        )

        await self._persist_outcome(outcome)

        self.active_predictions.pop(prediction_id, None)
        self.stats["replaced"] += 1
        self.stats["pending"] -= 1

    @with_db_retry(max_attempts=3)
    async def _get_prediction(self, prediction_id: str) -> Optional[Dict[str, Any]]:
        """Get prediction details from database"""
        try:
            conn = duckdb.connect(self.db_path)

            query = """
                SELECT
                    prediction_id,
                    transaction_id,
                    detection_timestamp,
                    predicted_confirmation_block,
                    urgency_score
                FROM mempool_predictions
                WHERE prediction_id = ?
            """

            result = conn.execute(query, [prediction_id]).fetchone()
            conn.close()

            if not result:
                return None

            return {
                "prediction_id": result[0],
                "transaction_id": result[1],
                "detection_timestamp": result[2],
                "predicted_confirmation_block": result[3],
                "urgency_score": result[4],
            }

        except Exception as e:
            logger.error(
                f"Failed to get prediction {prediction_id}: {e}", exc_info=True
            )
            return None

    @with_db_retry(max_attempts=3)
    async def _persist_outcome(self, outcome: PredictionOutcome):
        """Persist outcome to database"""
        try:
            conn = duckdb.connect(self.db_path)

            insert_query = """
                INSERT INTO prediction_outcomes (
                    outcome_id,
                    prediction_id,
                    transaction_id,
                    outcome_type,
                    detection_timestamp,
                    outcome_timestamp,
                    predicted_confirmation_block,
                    actual_confirmation_block,
                    blocks_until_confirmation,
                    timing_score,
                    accuracy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            conn.execute(
                insert_query,
                [
                    outcome.outcome_id,
                    outcome.prediction_id,
                    outcome.transaction_id,
                    outcome.outcome_type.value,
                    outcome.detection_timestamp,
                    outcome.outcome_timestamp,
                    outcome.predicted_confirmation_block,
                    outcome.actual_confirmation_block,
                    outcome.blocks_until_confirmation,
                    outcome.timing_score,
                    outcome.accuracy,
                ],
            )

            conn.close()
            logger.debug(f"Persisted outcome {outcome.outcome_id[:8]}... to database")

        except Exception as e:
            logger.error(f"Failed to persist outcome: {e}", exc_info=True)
            raise

    async def _cleanup_loop(self):
        """Background loop to cleanup old data (runs daily)"""
        logger.info("🧹 Starting cleanup loop (daily)...")

        while self._running:
            try:
                # Wait 24 hours
                await asyncio.sleep(86400)

                # Cleanup old outcomes
                await self._cleanup_old_outcomes()

            except asyncio.CancelledError:
                logger.info("Cleanup loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}", exc_info=True)

    @with_db_retry(max_attempts=3)
    async def _cleanup_old_outcomes(self):
        """Delete outcomes older than retention period"""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)

            conn = duckdb.connect(self.db_path)

            delete_query = """
                DELETE FROM prediction_outcomes
                WHERE outcome_timestamp < ?
            """

            result = conn.execute(delete_query, [cutoff])
            deleted_count = result.fetchone()[0] if result else 0
            conn.close()

            if deleted_count > 0:
                logger.info(
                    f"🧹 Cleaned up {deleted_count} old outcomes (>{self.retention_days} days)"
                )

        except Exception as e:
            logger.error(f"Failed to cleanup old outcomes: {e}", exc_info=True)

    def get_stats(self) -> Dict[str, Any]:
        """Get current tracking statistics"""
        return {
            **self.stats,
            "active_tracking": len(self.active_predictions),
        }


# Example usage / entry point
async def main():
    """Main entry point for standalone execution"""
    tracker = CorrelationTracker()

    try:
        await tracker.start()

        # Run indefinitely
        while True:
            await asyncio.sleep(60)
            stats = tracker.get_stats()
            logger.info(f"Stats: {stats}")

    except KeyboardInterrupt:
        logger.info("\n🛑 Shutting down...")
        await tracker.stop()


if __name__ == "__main__":
    asyncio.run(main())
