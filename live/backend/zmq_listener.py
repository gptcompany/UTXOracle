"""Bitcoin Core ZMQ Listener - Extended for Transactions + Blocks"""

import asyncio
import logging
import time
from typing import AsyncGenerator, Tuple

import zmq
import zmq.asyncio

from live.shared.models import RawTransaction

logger = logging.getLogger("live.zmq_listener")

# Reconnection settings
INITIAL_BACKOFF_SEC = 0.5
MAX_BACKOFF_SEC = 5.0
BACKOFF_MULTIPLIER = 1.5


class ZMQListener:
    """Bitcoin Core ZMQ listener for mempool transactions AND blocks"""

    def __init__(
        self,
        tx_endpoint: str = "tcp://127.0.0.1:28332",
        block_endpoint: str = "tcp://127.0.0.1:28333",
    ):
        self.tx_endpoint = tx_endpoint
        self.block_endpoint = block_endpoint
        self._connected_tx = False
        self._connected_block = False
        self._context = None
        self._tx_socket = None
        self._block_socket = None

    @property
    def is_connected(self) -> bool:
        """Check if connected to at least one ZMQ feed."""
        return self._connected_tx or self._connected_block

    async def connect(self) -> None:
        """Connect to Bitcoin Core ZMQ for transactions."""
        try:
            self._context = zmq.asyncio.Context()
            self._tx_socket = self._context.socket(zmq.SUB)
            self._tx_socket.connect(self.tx_endpoint)
            self._tx_socket.subscribe(b"rawtx")
            self._connected_tx = True
            logger.info(f"Connected to ZMQ transactions: {self.tx_endpoint}")
        except Exception as e:
            self._connected_tx = False
            raise ConnectionError(f"Failed to connect to transactions: {e}") from e

    async def connect_blocks(self) -> None:
        """Connect to Bitcoin Core ZMQ for blocks."""
        try:
            if not self._context:
                self._context = zmq.asyncio.Context()
            self._block_socket = self._context.socket(zmq.SUB)
            self._block_socket.connect(self.block_endpoint)
            self._block_socket.subscribe(b"rawblock")
            self._connected_block = True
            logger.info(f"Connected to ZMQ blocks: {self.block_endpoint}")
        except Exception as e:
            self._connected_block = False
            raise ConnectionError(f"Failed to connect to blocks: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from Bitcoin Core ZMQ (transactions)."""
        if self._tx_socket:
            self._tx_socket.close()
            self._tx_socket = None
        self._connected_tx = False

    async def disconnect_blocks(self) -> None:
        """Disconnect from Bitcoin Core ZMQ (blocks)."""
        if self._block_socket:
            self._block_socket.close()
            self._block_socket = None
        self._connected_block = False

    async def disconnect_all(self) -> None:
        """Disconnect from all ZMQ feeds."""
        await self.disconnect()
        await self.disconnect_blocks()
        if self._context:
            self._context.term()
            self._context = None

    async def stream_transactions(self) -> AsyncGenerator[RawTransaction, None]:
        """Stream raw mempool transactions from Bitcoin Core ZMQ."""
        if not self._connected_tx or not self._tx_socket:
            raise RuntimeError("Must call connect() before streaming transactions")

        backoff = INITIAL_BACKOFF_SEC

        while True:
            try:
                # Receive multipart message: [topic, data] or [topic, data, sequence]
                message = await self._tx_socket.recv_multipart()

                # Validate message structure
                if len(message) not in (2, 3):
                    logger.warning(
                        f"Malformed TX message: expected 2-3 parts, got {len(message)}"
                    )
                    continue

                # Parse message parts
                topic_bytes, tx_bytes = message[0], message[1]
                topic = topic_bytes.decode("utf-8")

                # Filter by topic
                if topic != "rawtx":
                    logger.debug(f"Skipping non-rawtx topic: {topic}")
                    continue

                # Validate data
                if not tx_bytes:
                    logger.warning("Received empty transaction data")
                    continue

                # Create RawTransaction object
                timestamp = time.time()
                raw_tx = RawTransaction(
                    raw_bytes=tx_bytes, timestamp=timestamp, topic="rawtx"
                )

                # Reset backoff on success
                backoff = INITIAL_BACKOFF_SEC
                yield raw_tx

            except zmq.ZMQError as e:
                logger.error(f"ZMQ TX error: {e}. Reconnecting in {backoff:.1f}s...")
                self._connected_tx = False
                await asyncio.sleep(backoff)
                backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF_SEC)

                try:
                    await self.disconnect()
                    await self.connect()
                    logger.info("TX reconnected successfully")
                except Exception as reconnect_error:
                    logger.error(f"TX reconnection failed: {reconnect_error}")
                    continue

            except asyncio.CancelledError:
                logger.info("TX stream cancelled")
                await self.disconnect()
                break

            except Exception as e:
                logger.exception(f"Unexpected error in stream_transactions: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF_SEC)

    async def stream_blocks(self) -> AsyncGenerator[Tuple[bytes, int], None]:
        """
        Stream raw blocks from Bitcoin Core ZMQ.

        Yields:
            Tuple[bytes, int]: (raw_block_bytes, block_height)
        """
        if not self._connected_block or not self._block_socket:
            raise RuntimeError("Must call connect_blocks() before streaming blocks")

        backoff = INITIAL_BACKOFF_SEC
        last_block_height = 0

        while True:
            try:
                # Receive multipart message: [topic, data] or [topic, data, sequence]
                message = await self._block_socket.recv_multipart()

                # Validate message structure
                if len(message) not in (2, 3):
                    logger.warning(
                        f"Malformed block message: expected 2-3 parts, got {len(message)}"
                    )
                    continue

                # Parse message parts
                topic_bytes, block_bytes = message[0], message[1]
                topic = topic_bytes.decode("utf-8")

                # Filter by topic
                if topic != "rawblock":
                    logger.debug(f"Skipping non-rawblock topic: {topic}")
                    continue

                # Validate data
                if not block_bytes:
                    logger.warning("Received empty block data")
                    continue

                # Extract block height from sequence (if available)
                # For now, increment counter (real implementation would parse block header)
                last_block_height += 1

                # Reset backoff on success
                backoff = INITIAL_BACKOFF_SEC

                yield (block_bytes, last_block_height)
                logger.info(f"Received new block (approx height: {last_block_height})")

            except zmq.ZMQError as e:
                logger.error(f"ZMQ block error: {e}. Reconnecting in {backoff:.1f}s...")
                self._connected_block = False
                await asyncio.sleep(backoff)
                backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF_SEC)

                try:
                    await self.disconnect_blocks()
                    await self.connect_blocks()
                    logger.info("Block reconnected successfully")
                except Exception as reconnect_error:
                    logger.error(f"Block reconnection failed: {reconnect_error}")
                    continue

            except asyncio.CancelledError:
                logger.info("Block stream cancelled")
                await self.disconnect_blocks()
                break

            except Exception as e:
                logger.exception(f"Unexpected error in stream_blocks: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF_SEC)
