"""
Pipeline Orchestrator (T051-T052)

Collega tutti i moduli backend:
ZMQ Listener → TX Processor → Mempool Analyzer → API Broadcast

COPIA QUESTO CONTENUTO IN: live/backend/orchestrator.py
"""

import asyncio
import logging
from typing import Optional

from live.backend.zmq_listener import ZMQListener
from live.backend.tx_processor import process_mempool_transaction
from live.backend.mempool_analyzer import MempoolAnalyzer
from live.backend.config import get_config

# Import global streamer instance from api module (fix for WebSocket client registration bug)

logger = logging.getLogger("live.orchestrator")

# Global instances (shared state)
_zmq_listener: Optional[ZMQListener] = None
_analyzer: Optional[MempoolAnalyzer] = None


class PipelineOrchestrator:
    """
    Orchestrates the complete pipeline:
    Bitcoin Core ZMQ → Transaction Processing → Mempool Analysis → WebSocket Broadcast

    Implements:
    - T051: Pipeline coordination (glue all modules)
    - T052: Update throttling (min 500ms between broadcasts)
    """

    def __init__(
        self,
        zmq_endpoint: str = "tcp://127.0.0.1:28332",
        window_hours: float = 3.0,
        min_broadcast_interval: float = 0.5,
    ):
        """
        Initialize pipeline orchestrator.

        Args:
            zmq_endpoint: Bitcoin Core ZMQ endpoint
            window_hours: Rolling window size for price analysis
            min_broadcast_interval: Minimum seconds between broadcasts (T052 throttling)
        """
        self.zmq_endpoint = zmq_endpoint
        self.window_hours = window_hours
        self.min_broadcast_interval = min_broadcast_interval

        # Module instances
        self.zmq_listener = ZMQListener(endpoint=zmq_endpoint)
        self.analyzer = MempoolAnalyzer(window_hours=window_hours)

        # FIX: Use the global streamer instance from api.py instead of creating a new one
        # This ensures WebSocket clients registered via /ws/mempool endpoint receive broadcasts
        from live.backend.api import streamer

        print(f"DEBUG orchestrator.__init__: importing streamer, id={id(streamer)}")
        self.streamer = streamer
        print(f"DEBUG orchestrator.__init__: self.streamer id={id(self.streamer)}")

        # Statistics
        self.total_received = 0
        self.total_processed = 0
        self.total_filtered = 0

        # Pipeline state
        self._running = False

    async def start(self) -> None:
        """Start the pipeline"""
        logger.info("Starting UTXOracle Live pipeline...")

        # Connect to Bitcoin Core ZMQ
        try:
            await self.zmq_listener.connect()
            logger.info(f"Connected to Bitcoin Core ZMQ at {self.zmq_endpoint}")
        except ConnectionError as e:
            logger.error(f"Failed to connect to Bitcoin Core: {e}")
            raise

        self._running = True

        # Start pipeline tasks
        await asyncio.gather(
            self._process_transactions(),
            self._cleanup_old_transactions(),
            self._broadcast_updates(),
        )

    async def stop(self) -> None:
        """Stop the pipeline gracefully"""
        logger.info("Stopping UTXOracle Live pipeline...")
        self._running = False

        # Disconnect from ZMQ
        await self.zmq_listener.disconnect()
        logger.info("Pipeline stopped")

    # -------------------------------------------------------------------------
    # T051: Pipeline Coordination
    # -------------------------------------------------------------------------

    async def _process_transactions(self) -> None:
        """
        Main pipeline loop: ZMQ → TX Processor → Analyzer

        This is the core of T051 - connecting Module 1 → 2 → 3
        """
        logger.info("Starting transaction processing pipeline...")

        try:
            async for raw_tx in self.zmq_listener.stream_transactions():
                if not self._running:
                    break

                self.total_received += 1

                # Module 1 → Module 2: Parse and filter
                processed_tx = process_mempool_transaction(raw_tx)

                if processed_tx is None:
                    # Transaction filtered out by UTXOracle rules
                    self.total_filtered += 1
                    continue

                # Module 2 → Module 3: Add to mempool analyzer
                self.analyzer.add_transaction(processed_tx)
                self.total_processed += 1

                # Log progress every 100 transactions
                if self.total_received % 100 == 0:
                    logger.info(
                        f"Processed {self.total_processed}/{self.total_received} transactions "
                        f"({self.total_filtered} filtered)"
                    )

        except Exception as e:
            logger.error(
                f"Error in transaction processing pipeline: {e}", exc_info=True
            )
            self._running = False

    async def _cleanup_old_transactions(self) -> None:
        """
        Periodically remove old transactions from rolling window.

        Runs every 60 seconds to clean up expired transactions (older than window_hours).
        """
        logger.info("Starting transaction cleanup task...")

        while self._running:
            try:
                # Wait 60 seconds between cleanups
                await asyncio.sleep(60)

                if not self._running:
                    break

                # Remove transactions older than rolling window
                removed_count = self.analyzer.remove_old_transactions()

                if removed_count > 0:
                    logger.debug(
                        f"Cleanup: removed {removed_count} old transactions "
                        f"(active: {len(self.analyzer.transactions)})"
                    )

            except Exception as e:
                logger.error(f"Error in cleanup task: {e}", exc_info=True)

    # -------------------------------------------------------------------------
    # T052: Update Throttling
    # -------------------------------------------------------------------------

    async def _broadcast_updates(self) -> None:
        """
        Periodically broadcast mempool state to WebSocket clients.

        T052: Implements throttling - broadcasts every min_broadcast_interval seconds.

        Module 3 → Module 4: Analyzer state → WebSocket broadcast
        """
        logger.info(
            f"Starting broadcast task (interval: {self.min_broadcast_interval}s)..."
        )

        while self._running:
            try:
                # T052: Throttle broadcasts to min_broadcast_interval
                await asyncio.sleep(self.min_broadcast_interval)

                if not self._running:
                    break

                # Module 3: Get current mempool state
                state = self.analyzer.get_state()

                # Module 4: Broadcast to all WebSocket clients
                await self.streamer.broadcast(state)

            except Exception as e:
                logger.error(f"Error in broadcast task: {e}", exc_info=True)


# -----------------------------------------------------------------------------
# Global Orchestrator Instance (for FastAPI startup/shutdown)
# -----------------------------------------------------------------------------

_orchestrator: Optional[PipelineOrchestrator] = None


def get_orchestrator() -> PipelineOrchestrator:
    """Get or create the global orchestrator instance"""
    global _orchestrator

    if _orchestrator is None:
        config = get_config()
        _orchestrator = PipelineOrchestrator(
            zmq_endpoint=config.zmq_endpoint,
            window_hours=config.window_hours,
            min_broadcast_interval=config.min_broadcast_interval,
        )

    return _orchestrator


# -----------------------------------------------------------------------------
# FastAPI Lifecycle Events
# -----------------------------------------------------------------------------


@app.on_event("startup")
async def startup_event():
    """Start orchestrator when FastAPI starts"""
    logger.info("FastAPI startup: Initializing pipeline orchestrator...")

    orchestrator = get_orchestrator()

    # Start pipeline in background
    asyncio.create_task(orchestrator.start())

    logger.info("Pipeline orchestrator started")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop orchestrator when FastAPI shuts down"""
    logger.info("FastAPI shutdown: Stopping pipeline orchestrator...")

    orchestrator = get_orchestrator()
    await orchestrator.stop()

    logger.info("Pipeline orchestrator stopped")


# -----------------------------------------------------------------------------
# Convenience Function (Optional - for standalone testing)
# -----------------------------------------------------------------------------


async def run_standalone():
    """
    Run orchestrator standalone (without FastAPI).

    Useful for testing the pipeline independently.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    orchestrator = get_orchestrator()

    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal...")
    finally:
        await orchestrator.stop()


if __name__ == "__main__":
    # Run standalone for testing
    asyncio.run(run_standalone())
