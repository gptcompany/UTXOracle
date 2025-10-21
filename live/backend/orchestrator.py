"""
Pipeline Orchestrator (T051-T052)

Connects all backend modules:
ZMQ Listener → TX Processor → Mempool Analyzer → API Broadcast
"""

import asyncio
import logging
import time
from typing import Optional

from live.backend.zmq_listener import ZMQListener
from live.backend.tx_processor import process_mempool_transaction
from live.backend.mempool_analyzer import MempoolAnalyzer
from live.backend.api import DataStreamer
from live.backend.config import get_config

logger = logging.getLogger("live.orchestrator")


class PipelineOrchestrator:
    """Orchestrates the complete pipeline (T051-T052)"""

    def __init__(
        self,
        zmq_endpoint: str = "tcp://127.0.0.1:28332",
        window_hours: float = 3.0,
        min_broadcast_interval: float = 0.5,
    ):
        self.zmq_endpoint = zmq_endpoint
        self.window_hours = window_hours
        self.min_broadcast_interval = min_broadcast_interval

        self.zmq_listener = ZMQListener(endpoint=zmq_endpoint)
        self.analyzer = MempoolAnalyzer(window_hours=window_hours)
        self.streamer = DataStreamer(
            max_updates_per_second=int(1.0 / min_broadcast_interval)
        )

        self.total_received = 0
        self.total_processed = 0
        self.total_filtered = 0
        self._running = False

    async def start(self) -> None:
        logger.info("Starting UTXOracle Live pipeline...")

        try:
            await self.zmq_listener.connect()
            logger.info(f"Connected to Bitcoin Core ZMQ at {self.zmq_endpoint}")
        except ConnectionError as e:
            logger.error(f"Failed to connect to Bitcoin Core: {e}")
            raise

        self._running = True

        await asyncio.gather(
            self._process_transactions(),
            self._cleanup_old_transactions(),
            self._broadcast_updates(),
        )

    async def stop(self) -> None:
        logger.info("Stopping UTXOracle Live pipeline...")
        self._running = False
        await self.zmq_listener.disconnect()
        logger.info("Pipeline stopped")

    async def _process_transactions(self) -> None:
        logger.info("Starting transaction processing pipeline...")

        try:
            async for raw_tx in self.zmq_listener.stream_transactions():
                if not self._running:
                    break

                self.total_received += 1
                processed_tx = process_mempool_transaction(raw_tx)

                if processed_tx is None:
                    self.total_filtered += 1
                    continue

                self.analyzer.add_transaction(processed_tx)
                self.total_processed += 1

                if self.total_received % 100 == 0:
                    logger.info(
                        f"Processed {self.total_processed}/{self.total_received} "
                        f"({self.total_filtered} filtered)"
                    )

        except Exception as e:
            logger.error(f"Error in transaction processing: {e}", exc_info=True)
            self._running = False

    async def _cleanup_old_transactions(self) -> None:
        logger.info("Starting transaction cleanup task...")

        while self._running:
            try:
                await asyncio.sleep(60)

                if not self._running:
                    break

                removed_count = self.analyzer.cleanup_old_transactions(time.time())

                if removed_count > 0:
                    logger.debug(
                        f"Cleanup: removed {removed_count} old transactions "
                        f"(active: {len(self.analyzer.transactions)})"
                    )

            except Exception as e:
                logger.error(f"Error in cleanup task: {e}", exc_info=True)

    async def _broadcast_updates(self) -> None:
        logger.info(
            f"Starting broadcast task (interval: {self.min_broadcast_interval}s)..."
        )

        while self._running:
            try:
                await asyncio.sleep(self.min_broadcast_interval)

                if not self._running:
                    break

                state = self.analyzer.get_state()
                await self.streamer.broadcast(state)

            except Exception as e:
                logger.error(f"Error in broadcast task: {e}", exc_info=True)


_orchestrator: Optional[PipelineOrchestrator] = None


def get_orchestrator() -> PipelineOrchestrator:
    global _orchestrator

    if _orchestrator is None:
        config = get_config()
        _orchestrator = PipelineOrchestrator(
            zmq_endpoint=config.zmq_endpoint,
            window_hours=config.window_hours,
            min_broadcast_interval=config.min_broadcast_interval,
        )

    return _orchestrator


async def run_standalone():
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
    asyncio.run(run_standalone())
