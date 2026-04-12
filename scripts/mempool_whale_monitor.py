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
from scripts.utils.rbf_detector import is_rbf_enabled
from scripts.whale_urgency_scorer import WhaleUrgencyScorer

from api.questdb_repository import QuestDBRepository

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
            db_path: Path to database (obsolete, using QuestDB now)
        """
        self.mempool_ws_url = mempool_ws_url
        self.whale_threshold_btc = whale_threshold_btc

        # Load configuration
        config = get_config()
        
        # Initialize QuestDB repository
        self.repo = QuestDBRepository()

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

        self.broadcaster = None

        # Load exchange addresses using shared robust utility
        from scripts.utils.whale_utils import load_exchange_addresses
        self.exchange_addresses = load_exchange_addresses("data/exchange_addresses.csv")

        # Urgency scorer (for fee-based urgency calculation)
        self.urgency_scorer = WhaleUrgencyScorer(
            mempool_api_url=config.mempool_http_url,
            update_interval_seconds=60,
        )

        logger.info(f"Mempool whale monitor initialized with {len(self.exchange_addresses)} exchange addresses")
        logger.info(f"Whale threshold: {whale_threshold_btc} BTC")
        logger.info("Using QuestDB for persistence")

    async def _on_connect(self, websocket):
        """Handle WebSocket connection established"""
        logger.info("🔗 Connected to mempool.space transaction stream")

        # Initialize repository on first connect if needed
        await self.repo.initialize()

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

            # Format urgency for display
            urgency = tx_data["urgency_score"]
            if urgency >= 0.7:
                urgency_label = "🔴 HIGH"
            elif urgency >= 0.4:
                urgency_label = "🟡 MEDIUM"
            else:
                urgency_label = "🟢 LOW"

            # Format RBF status
            rbf_indicator = "⚡RBF" if tx_data["rbf_enabled"] else ""

            logger.info(
                f"🐋 WHALE DETECTED: {tx_data['btc_value']:.2f} BTC | "
                f"Fee: {tx_data['fee_rate']:.1f} sat/vB | "
                f"Urgency: {urgency_label} ({urgency:.2f}) {rbf_indicator}"
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

            # RBF detection (BIP 125 compliant)
            # First try mempool.space's rbf field, otherwise check sequence numbers
            rbf_from_api = data.get("rbf", False) or data.get(
                "bip125-replaceable", False
            )

            # For proper BIP 125 detection, check sequence numbers if transaction has vin
            if "vin" in data and len(data.get("vin", [])) > 0:
                rbf_enabled = is_rbf_enabled(data)
            else:
                # Fallback to API field if no input data available
                rbf_enabled = rbf_from_api

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
        Calculate urgency score based on current mempool fee market conditions

        Uses WhaleUrgencyScorer which fetches real-time fee estimates from
        mempool.space and calculates urgency relative to current percentiles.

        Args:
            fee_rate: Transaction fee rate in sat/vB

        Returns:
            Urgency score between 0.0 and 1.0
        """
        try:
            # Use real-time fee market data for urgency calculation
            return self.urgency_scorer.calculate_urgency(fee_rate)
        except RuntimeError:
            # Fallback: If metrics not initialized yet, use simple heuristic
            logger.warning("Urgency metrics not initialized, using fallback heuristic")
            if fee_rate < 10:
                return min(0.3, (fee_rate / 10) * 0.3)
            elif fee_rate < 50:
                return 0.3 + ((fee_rate - 10) / 40) * 0.4
            else:
                return min(1.0, 0.7 + ((fee_rate - 50) / 50) * 0.3)

    async def _create_whale_signal(self, tx_data: Dict[str, Any]) -> MempoolWhaleSignal:
        """
        Create MempoolWhaleSignal from transaction data
        """
        prediction_id = str(uuid.uuid4())
        raw_data = tx_data.get("raw_data", {})
        
        # Extract addresses from input/output
        involved_addresses = []
        for vin in raw_data.get("vin", []):
            if vin.get("is_coinbase", False): continue
            if "prevout" in vin and "scriptpubkey_address" in vin["prevout"]:
                involved_addresses.append(vin["prevout"]["scriptpubkey_address"])
        for vout in raw_data.get("vout", []):
            if "scriptpubkey_address" in vout:
                involved_addresses.append(vout["scriptpubkey_address"])
                
        # Identify exchange addresses (CSV first)
        identified = {addr: self.exchange_addresses[addr] for addr in involved_addresses if addr in self.exchange_addresses}
        
        # Enrichment: try DB lookup for addresses not in CSV
        for addr in involved_addresses:
            if addr not in identified:
                cluster = await self.repo.get_cluster_for_address(addr)
                if cluster:
                    identified[addr] = cluster.get("label") or cluster.get("cluster_id")
        
        # Classify flow type and analyze involved exchanges
        flow_type = FlowType.UNKNOWN
        involved_exchanges = list(set(identified.values()))
        
        # Check inputs and outputs for specific exchange involvement
        inflow_addresses = {addr for vout in raw_data.get("vout", []) for addr in [vout.get("scriptpubkey_address")] if addr in identified}
        outflow_addresses = {addr for vin in raw_data.get("vin", []) for addr in [vin.get("prevout", {}).get("scriptpubkey_address")] if addr in identified}
        
        inflow_exchanges = {identified[addr] for addr in inflow_addresses}
        outflow_exchanges = {identified[addr] for addr in outflow_addresses}
        
        # Logic refinement:
        # 1. Internal transfer: Input and Output share exchanges (or across different exchanges)
        # 2. Inflow: Only Output involves an exchange
        # 3. Outflow: Only Input involves an exchange
        
        if inflow_exchanges and outflow_exchanges:
            flow_type = FlowType.INTERNAL
            confidence = 0.98 if inflow_exchanges == outflow_exchanges else 0.9
        elif inflow_exchanges:
            flow_type = FlowType.INFLOW
            confidence = 0.95
        elif outflow_exchanges:
            flow_type = FlowType.OUTFLOW
            confidence = 0.95
        else:
            # Fallback for complex/non-direct cases
            flow_type = FlowType.UNKNOWN
            confidence = 0.0

        # Predict confirmation block based on fee rate
        try:
            predicted_block = self.urgency_scorer.predict_confirmation_block(tx_data["fee_rate"])
        except RuntimeError:
            predicted_block = None

        # Create signal
        return MempoolWhaleSignal(
            prediction_id=prediction_id,
            transaction_id=tx_data["txid"],
            flow_type=flow_type,
            btc_value=tx_data["btc_value"],
            fee_rate=tx_data["fee_rate"],
            urgency_score=tx_data["urgency_score"],
            rbf_enabled=tx_data["rbf_enabled"],
            detection_timestamp=datetime.now(timezone.utc),
            predicted_confirmation_block=predicted_block,
            exchange_addresses=list(identified.keys()),
            confidence_score=confidence,
        )

    @with_db_retry(max_attempts=3)
    async def _persist_to_db(self, signal: MempoolWhaleSignal):
        """
        Persist whale signal to QuestDB via ILP

        Args:
            signal: MempoolWhaleSignal to persist
        """
        try:
            # Use QuestDBRepository with async worker for non-blocking ILP ingestion
            success = await self.repo.async_send_row(
                "mempool_predictions",
                symbols={
                    "prediction_id": signal.prediction_id,
                    "transaction_id": signal.transaction_id,
                    "flow_type": signal.flow_type.value if hasattr(signal.flow_type, "value") else str(signal.flow_type),
                },
                columns={
                    "btc_value": float(signal.btc_value),
                    "fee_rate": float(signal.fee_rate),
                    "urgency_score": float(signal.urgency_score),
                    "rbf_enabled": bool(signal.rbf_enabled),
                    "ts": signal.detection_timestamp,
                    "predicted_confirmation_block": signal.predicted_confirmation_block,
                    "exchange_addresses": ",".join(signal.exchange_addresses) if signal.exchange_addresses else "",
                    "confidence_score": float(signal.confidence_score) if signal.confidence_score is not None else None,
                    "was_modified": bool(signal.was_modified),
                    "created_at": signal.created_at,
                },
                at=signal.detection_timestamp
            )

            if success:
                self.stats["db_writes"] += 1
                logger.debug(
                    f"Persisted prediction {signal.prediction_id[:8]}... to QuestDB"
                )
            else:
                logger.error(f"Failed to persist prediction {signal.prediction_id[:8]}... to QuestDB")

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
            alert_data = signal.to_broadcast_dict()

            # Broadcast to all authenticated clients with 'read' permission
            await self.broadcaster.broadcast_alert(signal)

            self.stats["alerts_broadcasted"] += 1
            logger.debug(f"Broadcasted alert {signal.prediction_id[:8]}...")

        except Exception as e:
            logger.error(f"Failed to broadcast alert: {e}", exc_info=True)

    async def start(self):
        """Start the mempool whale monitor"""
        logger.info("🚀 Starting mempool whale monitor...")

        # Start urgency scorer (fee metrics updates)
        await self.urgency_scorer.start()
        logger.info("✅ Urgency scorer started")

        # Start WebSocket connection
        await self.reconnector.start()

    async def stop(self):
        """Stop the mempool whale monitor"""
        logger.info("🛑 Stopping mempool whale monitor...")

        # Stop WebSocket connection
        await self.reconnector.stop()

        # Stop urgency scorer
        await self.urgency_scorer.stop()
        logger.info("✅ Urgency scorer stopped")

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
