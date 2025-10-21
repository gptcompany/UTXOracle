"""Bitcoin Core ZMQ Mempool Listener"""

import asyncio
import logging
import time
from typing import AsyncGenerator

import zmq
import zmq.asyncio

from live.shared.models import RawTransaction

logger = logging.getLogger("live.zmq_listener")

# Reconnection settings
INITIAL_BACKOFF_SEC = 0.5
MAX_BACKOFF_SEC = 5.0
BACKOFF_MULTIPLIER = 1.5


class ZMQListener:
    """Bitcoin Core ZMQ mempool transaction listener"""

    def __init__(self, endpoint: str = "tcp://127.0.0.1:28332"):
        self.endpoint = endpoint
        self._connected = False
        self._context = None
        self._socket = None

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected

    async def connect(self) -> None:
        """Connect to Bitcoin Core ZMQ."""
        try:
            self._context = zmq.asyncio.Context()
            self._socket = self._context.socket(zmq.SUB)
            self._socket.connect(self.endpoint)
            self._socket.subscribe(b"rawtx")
            self._connected = True
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"Failed to connect: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from Bitcoin Core ZMQ."""
        if self._socket:
            self._socket.close()
            self._socket = None
        if self._context:
            self._context.term()
            self._context = None
        self._connected = False

    async def stream_transactions(self) -> AsyncGenerator[RawTransaction, None]:
        """Stream raw mempool transactions from Bitcoin Core ZMQ."""
        if not self._connected or not self._socket:
            raise RuntimeError("Must call connect() before streaming transactions")

        backoff = INITIAL_BACKOFF_SEC

        while True:
            try:
                # Receive multipart message: [topic, data] or [topic, data, sequence]
                # Bitcoin Core sends 3-part messages with sequence number
                message = await self._socket.recv_multipart()

                # Validate message structure (accept 2 or 3 parts)
                if len(message) not in (2, 3):
                    logger.warning(
                        f"Malformed ZMQ message: expected 2 or 3 parts, got {len(message)}. Skipping."
                    )
                    continue

                # Parse message parts (ignore sequence number if present)
                topic_bytes, tx_bytes = message[0], message[1]

                # Decode topic
                topic = topic_bytes.decode("utf-8")

                # Filter by topic (only 'rawtx' for mempool transactions)
                if topic != "rawtx":
                    logger.debug(f"Skipping non-rawtx topic: {topic}")
                    continue

                # Validate transaction data
                if not tx_bytes:
                    logger.warning("Received empty transaction data. Skipping.")
                    continue

                # Create RawTransaction object
                timestamp = time.time()
                raw_tx = RawTransaction(
                    raw_bytes=tx_bytes, timestamp=timestamp, topic="rawtx"
                )

                # Reset backoff on successful receive
                backoff = INITIAL_BACKOFF_SEC

                yield raw_tx

            except zmq.ZMQError as e:
                # ZMQ error - likely disconnection
                logger.error(
                    f"ZMQ error: {e}. Attempting reconnect in {backoff:.1f}s..."
                )
                self._connected = False

                # Wait before reconnecting
                await asyncio.sleep(backoff)

                # Exponential backoff (capped at MAX_BACKOFF_SEC)
                backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF_SEC)

                # Attempt reconnection
                try:
                    await self.disconnect()
                    await self.connect()
                    logger.info("Reconnected successfully")
                except Exception as reconnect_error:
                    logger.error(f"Reconnection failed: {reconnect_error}")
                    continue

            except asyncio.CancelledError:
                logger.info("Stream cancelled, shutting down")
                await self.disconnect()
                break

            except Exception as e:
                logger.exception(f"Unexpected error in stream_transactions: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF_SEC)
