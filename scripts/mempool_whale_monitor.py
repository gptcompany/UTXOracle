#!/usr/bin/env python3
"""
Mempool Whale Monitor - Real-time Detection
Tasks: T011-T016 - Core whale detection implementation

Features:
- WebSocket connection to mempool.space with auto-reconnection
- Real-time transaction stream parsing
- >100 BTC whale filtering
- Fee-based urgency scoring
- Database persistence (DuckDB)
- Alert broadcasting to clients

Architecture:
- Uses WebSocketReconnector for resilience
- Integrates MempoolWhaleSignal data model
- Calculates urgency scores based on fee rates
- Persists predictions to database
- Broadcasts alerts via WhaleAlertBroadcaster
"""

import asyncio
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent dirs to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.models.whale_signal import MempoolWhaleSignal, FlowType
from scripts.utils.websocket_reconnect import WebSocketReconnector
from scripts.utils.transaction_cache import TransactionCache
from scripts.config.mempool_config import get_config
from scripts.utils.db_retry import with_db_retry

import duckdb

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MempoolWhaleMonitor:
    """
    Real-time mempool whale transaction monitor

    Connects to mempool.space WebSocket, filters transactions >100 BTC,
    calculates urgency scores, and broadcasts alerts.
    """

    def __init__(
        self,
        mempool_ws_url: str = "ws://localhost:8999/ws/track-mempool-tx",
        whale_threshold_btc: float = 100.0,
        db_path: Optional[str] = None,
    ):
        """
        Initialize mempool whale monitor

        Args:
            mempool_ws_url: WebSocket URL for mempool.space transaction stream
            whale_threshold_btc: Minimum BTC value to classify as whale (default: 100.0)
            db_path: Path to DuckDB database (default: from config)
        """
        self.mempool_ws_url = mempool_ws_url
        self.whale_threshold_btc = whale_threshold_btc

        # Load configuration
        config = get_config()
        self.db_path = db_path or config.database.db_path

        # Transaction cache (prevents duplicate processing)
        self.tx_cache = TransactionCache(maxlen=10000)

        # Statistics
        self.stats = {
            "total_transactions": 0,
            "whale_transactions": 0,
            "alerts_broadcasted": 0,
            "db_writes": 0,
            "parse_errors": 0,
        }

        # WebSocket reconnector (with auto-reconnection)
        self.reconnector = WebSocketReconnector(
            url=self.mempool_ws_url,
            on_connect_callback=self._on_connect,
            on_disconnect_callback=self._on_disconnect,
            max_retries=None,  # Infinite retries
            initial_delay=1.0,
            max_delay=30.0,
        )

        # Broadcaster reference (will be set externally)
        self.broadcaster = None

        logger.info("Mempool whale monitor initialized")
        logger.info(f"Whale threshold: {whale_threshold_btc} BTC")
        logger.info(f"Database: {self.db_path}")

    async def _on_connect(self, websocket):
        """Handle WebSocket connection established"""
        logger.info("🔗 Connected to mempool.space transaction stream")

        # Listen for incoming messages
        async for message in websocket:
            await self._handle_transaction(message)

    async def _on_disconnect(self):
        """Handle WebSocket disconnection"""
        logger.warning("🔌 Disconnected from mempool.space - will retry")

    async def _handle_transaction(self, message: str):
        """
        Process incoming transaction message

        Args:
            message: JSON string from WebSocket
        """
        try:
            self.stats["total_transactions"] += 1

            # Parse JSON message
            data = json.loads(message)

            # Extract transaction data
            tx_data = self._parse_transaction(data)
            if not tx_data:
                return

            # Check if whale transaction (>100 BTC)
            if tx_data["btc_value"] < self.whale_threshold_btc:
                return  # Not a whale, skip

            # Check cache (prevent duplicate processing)
            if self.tx_cache.contains(tx_data["txid"]):
                logger.debug(f"Transaction {tx_data['txid'][:8]}... already processed")
                return

            logger.info(
                f"🐋 WHALE DETECTED: {tx_data['btc_value']:.2f} BTC "
                f"(fee: {tx_data['fee_rate']:.1f} sat/vB, "
                f"urgency: {tx_data['urgency_score']:.2f})"
            )

            # Create whale signal
            signal = await self._create_whale_signal(tx_data)

            # Store in cache
            self.tx_cache.add(tx_data["txid"], signal)

            # Persist to database
            await self._persist_to_db(signal)

            # Broadcast alert to clients
            await self._broadcast_alert(signal)

            self.stats["whale_transactions"] += 1

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse transaction JSON: {e}")
            self.stats["parse_errors"] += 1
        except Exception as e:
            logger.error(f"Error handling transaction: {e}", exc_info=True)
            self.stats["parse_errors"] += 1

    def _parse_transaction(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse transaction data from mempool.space message

        Args:
            data: Raw transaction data from WebSocket

        Returns:
            Parsed transaction dict or None if invalid
        """
        try:
            # mempool.space format: {txid, fee, vsize, value, ...}
            txid = data.get("txid")
            if not txid:
                return None

            # Extract values
            fee_sats = data.get("fee", 0)
            vsize = data.get("vsize", 1)
            value_sats = data.get("value", 0)

            # Calculate metrics
            fee_rate = fee_sats / vsize if vsize > 0 else 0
            btc_value = value_sats / 100_000_000  # Satoshis to BTC

            # RBF detection
            rbf_enabled = data.get("rbf", False) or data.get(
                "bip125-replaceable", False
            )

            # Calculate urgency score (fee-based)
            urgency_score = self._calculate_urgency_score(fee_rate)

            return {
                "txid": txid,
                "btc_value": btc_value,
                "fee_rate": fee_rate,
                "urgency_score": urgency_score,
                "rbf_enabled": rbf_enabled,
                "raw_data": data,
            }

        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Error parsing transaction: {e}")
            return None

    def _calculate_urgency_score(self, fee_rate: float) -> float:
        """
        Calculate urgency score based on fee rate

        Simple heuristic:
        - <10 sat/vB: Low urgency (0.0-0.3)
        - 10-50 sat/vB: Medium urgency (0.3-0.7)
        - >50 sat/vB: High urgency (0.7-1.0)

        Args:
            fee_rate: Transaction fee rate in sat/vB

        Returns:
            Urgency score between 0.0 and 1.0
        """
        if fee_rate < 10:
            # Low urgency: scale 0-10 sat/vB to 0.0-0.3
            return min(0.3, (fee_rate / 10) * 0.3)
        elif fee_rate < 50:
            # Medium urgency: scale 10-50 sat/vB to 0.3-0.7
            return 0.3 + ((fee_rate - 10) / 40) * 0.4
        else:
            # High urgency: scale 50-100+ sat/vB to 0.7-1.0
            return min(1.0, 0.7 + ((fee_rate - 50) / 50) * 0.3)

    async def _create_whale_signal(self, tx_data: Dict[str, Any]) -> MempoolWhaleSignal:
        """
        Create MempoolWhaleSignal from transaction data

        Args:
            tx_data: Parsed transaction data

        Returns:
            MempoolWhaleSignal instance
        """
        # Generate unique prediction ID
        prediction_id = str(uuid.uuid4())

        # Classify flow type (simplified - defaults to UNKNOWN)
        # TODO: Implement exchange address detection for proper classification
        flow_type = FlowType.UNKNOWN

        # Create signal
        signal = MempoolWhaleSignal(
            prediction_id=prediction_id,
            transaction_id=tx_data["txid"],
            flow_type=flow_type,
            btc_value=tx_data["btc_value"],
            fee_rate=tx_data["fee_rate"],
            urgency_score=tx_data["urgency_score"],
            rbf_enabled=tx_data["rbf_enabled"],
            detection_timestamp=datetime.now(timezone.utc),
            predicted_confirmation_block=None,  # TODO: Estimate based on fee
            exchange_addresses=[],  # TODO: Detect exchange addresses
            confidence_score=None,  # TODO: Calculate classification confidence
        )

        return signal

    @with_db_retry(max_attempts=3)
    async def _persist_to_db(self, signal: MempoolWhaleSignal):
        """
        Persist whale signal to DuckDB

        Args:
            signal: MempoolWhaleSignal to persist
        """
        try:
            conn = duckdb.connect(self.db_path)

            # Insert into mempool_predictions table
            insert_query = """
                INSERT INTO mempool_predictions (
                    prediction_id,
                    transaction_id,
                    flow_type,
                    btc_value,
                    fee_rate,
                    urgency_score,
                    rbf_enabled,
                    detection_timestamp,
                    predicted_confirmation_block,
                    exchange_addresses,
                    confidence_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            conn.execute(
                insert_query,
                [
                    signal.prediction_id,
                    signal.transaction_id,
                    signal.flow_type.value,
                    signal.btc_value,
                    signal.fee_rate,
                    signal.urgency_score,
                    signal.rbf_enabled,
                    signal.detection_timestamp,
                    signal.predicted_confirmation_block,
                    json.dumps(signal.exchange_addresses),
                    signal.confidence_score,
                ],
            )

            conn.close()

            self.stats["db_writes"] += 1
            logger.debug(
                f"Persisted prediction {signal.prediction_id[:8]}... to database"
            )

        except Exception as e:
            logger.error(f"Failed to persist to database: {e}", exc_info=True)
            raise

    async def _broadcast_alert(self, signal: MempoolWhaleSignal):
        """
        Broadcast whale alert to connected clients

        Args:
            signal: MempoolWhaleSignal to broadcast
        """
        if not self.broadcaster:
            logger.warning("No broadcaster configured - skipping broadcast")
            return

        try:
            # Convert signal to dict for broadcasting
            alert_data = signal.to_broadcast_format()

            # Broadcast to all authenticated clients with 'read' permission
            await self.broadcaster.broadcast_whale_alert(alert_data)

            self.stats["alerts_broadcasted"] += 1
            logger.debug(f"Broadcasted alert {signal.prediction_id[:8]}...")

        except Exception as e:
            logger.error(f"Failed to broadcast alert: {e}", exc_info=True)

    async def start(self):
        """Start the mempool whale monitor"""
        logger.info("🚀 Starting mempool whale monitor...")
        await self.reconnector.start()

    async def stop(self):
        """Stop the mempool whale monitor"""
        logger.info("🛑 Stopping mempool whale monitor...")
        await self.reconnector.stop()

    def get_stats(self) -> Dict[str, Any]:
        """Get monitor statistics"""
        return {
            **self.stats,
            "cache_stats": self.tx_cache.get_stats(),
            "reconnector_stats": self.reconnector.get_stats(),
        }


# Example usage / entry point
async def main():
    """Main entry point for standalone execution"""
    monitor = MempoolWhaleMonitor()

    try:
        await monitor.start()
    except KeyboardInterrupt:
        logger.info("\n🛑 Shutting down...")
        await monitor.stop()

        # Print final stats
        stats = monitor.get_stats()
        logger.info(f"Final stats: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    asyncio.run(main())
