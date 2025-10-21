"""
Pipeline Orchestrator - Extended with Baseline Calculator

Connects all backend modules:
- Mempool: ZMQ Listener → TX Processor → Mempool Analyzer → API Broadcast
- Baseline: ZMQ Blocks → Block Parser → Baseline Calculator → Mempool Analyzer
"""

import asyncio
import logging
import time
from typing import Optional

from live.backend.zmq_listener import ZMQListener
from live.backend.tx_processor import process_mempool_transaction
from live.backend.mempool_analyzer import MempoolAnalyzer
from live.backend.baseline_calculator import BaselineCalculator
from live.backend.block_parser import extract_transactions_from_block
from live.backend.config import get_config

logger = logging.getLogger("live.orchestrator")


class PipelineOrchestrator:
    """Orchestrates mempool + baseline pipelines"""

    def __init__(
        self,
        zmq_tx_endpoint: str = "tcp://127.0.0.1:28332",
        zmq_block_endpoint: str = "tcp://127.0.0.1:28333",
        window_hours: float = 3.0,
        min_broadcast_interval: float = 0.5,
    ):
        self.zmq_tx_endpoint = zmq_tx_endpoint
        self.zmq_block_endpoint = zmq_block_endpoint
        self.window_hours = window_hours
        self.min_broadcast_interval = min_broadcast_interval

        # ZMQ listener (transactions + blocks)
        self.zmq_listener = ZMQListener(
            tx_endpoint=zmq_tx_endpoint, block_endpoint=zmq_block_endpoint
        )

        # Baseline calculator (24h on-chain price)
        self.baseline_calc = BaselineCalculator(window_blocks=144)

        # Mempool analyzer (3h real-time price)
        self.analyzer = MempoolAnalyzer(window_hours=window_hours)

        # FIX: Use global streamer instance from api.py
        from live.backend.api import streamer

        self.streamer = streamer
        self.streamer.set_analyzer(self.analyzer)

        self.total_received = 0
        self.total_processed = 0
        self.total_filtered = 0
        self.total_blocks = 0
        self._running = False

    async def start(self) -> None:
        logger.info("Starting UTXOracle Live pipeline (mempool + baseline)...")

        # Connect to mempool transactions
        try:
            await self.zmq_listener.connect()
            logger.info(f"Connected to ZMQ transactions: {self.zmq_tx_endpoint}")
        except ConnectionError as e:
            logger.error(f"Failed to connect to mempool: {e}")
            raise

        # Connect to blocks (optional - continue if fails)
        try:
            await self.zmq_listener.connect_blocks()
            logger.info(f"Connected to ZMQ blocks: {self.zmq_block_endpoint}")
        except ConnectionError as e:
            logger.warning(f"Failed to connect to blocks (baseline disabled): {e}")

        self._running = True

        # Run all pipeline tasks
        await asyncio.gather(
            self._process_transactions(),
            self._process_blocks(),
            self._cleanup_old_transactions(),
            self._broadcast_updates(),
        )

    async def stop(self) -> None:
        logger.info("Stopping UTXOracle Live pipeline...")
        self._running = False
        await self.zmq_listener.disconnect_all()
        logger.info("Pipeline stopped")

    async def _process_transactions(self) -> None:
        """Process mempool transactions (T051)"""
        logger.info("Starting mempool transaction processing...")

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
                        f"Mempool: {self.total_processed}/{self.total_received} "
                        f"({self.total_filtered} filtered)"
                    )

        except Exception as e:
            logger.error(f"Error in mempool processing: {e}", exc_info=True)
            self._running = False

    async def _process_blocks(self) -> None:
        """Process new blocks for baseline calculation (T102)"""
        logger.info("Starting block processing for baseline...")

        try:
            async for block_bytes, block_height in self.zmq_listener.stream_blocks():
                if not self._running:
                    break

                self.total_blocks += 1
                logger.info(f"Received new block #{block_height}")

                # Extract transactions from block
                block_timestamp = time.time()
                transactions = extract_transactions_from_block(
                    block_bytes, block_timestamp
                )

                if not transactions:
                    logger.warning(f"No valid transactions in block #{block_height}")
                    continue

                # Add block to baseline calculator
                self.baseline_calc.add_block(transactions, height=block_height)

                # Recalculate baseline
                baseline_result = self.baseline_calc.calculate_baseline()

                if baseline_result:
                    logger.info(
                        f"Baseline updated: ${baseline_result.price:,.0f} "
                        f"(±{baseline_result.price_max - baseline_result.price:.0f}), "
                        f"confidence {baseline_result.confidence:.2f}"
                    )

                    # T103: Pass baseline to mempool analyzer for Y-axis scaling
                    self.analyzer.set_baseline(baseline_result)
                else:
                    logger.warning("Baseline calculation failed (insufficient data)")

        except RuntimeError as e:
            # Block stream not connected - baseline disabled
            logger.warning(f"Baseline disabled: {e}")
        except Exception as e:
            logger.error(f"Error in block processing: {e}", exc_info=True)

    async def _cleanup_old_transactions(self) -> None:
        """Cleanup old mempool transactions (T052)"""
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
        """Broadcast updates to WebSocket clients (T052)"""
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
            zmq_tx_endpoint=config.zmq_endpoint,
            zmq_block_endpoint=getattr(
                config, "zmq_block_endpoint", "tcp://127.0.0.1:28333"
            ),
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
