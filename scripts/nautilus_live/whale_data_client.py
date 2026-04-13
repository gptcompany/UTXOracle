import asyncio
import json
import logging
from typing import Optional
import websockets

from nautilus_trader.core.rust.common import Clock
from nautilus_trader.core.rust.model.data import Data
from nautilus_trader.live.client import LiveClient
from nautilus_trader.live.providers import DataProvider

logger = logging.getLogger(__name__)

class WhaleSignalData(Data):
    """
    Custom data object for Nautilus Trader representing a UTXOracle Whale Signal.
    """
    def __init__(
        self,
        ts_event: int,
        ts_init: int,
        prediction_id: str,
        sequence_id: int,
        transaction_id: str,
        flow_type: str,
        btc_value: float,
        urgency_score: float,
        confidence_score: float,
        rbf_enabled: bool,
    ):
        super().__init__(ts_event, ts_init)
        self.prediction_id = prediction_id
        self.sequence_id = sequence_id
        self.transaction_id = transaction_id
        self.flow_type = flow_type
        self.btc_value = btc_value
        self.urgency_score = urgency_score
        self.confidence_score = confidence_score
        self.rbf_enabled = rbf_enabled

class WhaleDataClient(LiveClient):
    """
    Nautilus Trader LiveClient for UTXOracle Whale WebSocket Stream.
    """
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        clock: Clock,
        ws_url: str = "ws://127.0.0.1:8011/api/execution/btc/stream",
    ):
        super().__init__(loop=loop, clock=clock)
        self._ws_url = ws_url
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._is_connected = False

    async def connect(self):
        """Establish connection to UTXOracle."""
        try:
            self._ws = await websockets.connect(self._ws_url)
            self._is_connected = True
            logger.info(f"✅ Connected to UTXOracle Whale Stream: {self._ws_url}")
            self._receive_task = self.loop.create_task(self._receive_loop())
        except Exception as e:
            logger.error(f"❌ Failed to connect to UTXOracle: {e}")
            raise

    async def disconnect(self):
        """Disconnect from UTXOracle."""
        self._is_connected = False
        if self._receive_task:
            self._receive_task.cancel()
        if self._ws:
            await self._ws.close()
            logger.info("🔌 Disconnected from UTXOracle Whale Stream")

    async def _receive_loop(self):
        """Listen for incoming whale signals."""
        while self._is_connected and self._ws:
            try:
                message = await self._ws.recv()
                self._handle_message(message)
            except websockets.ConnectionClosed:
                logger.warning("UTXOracle connection closed unexpectedly.")
                break
            except Exception as e:
                logger.error(f"Error receiving whale signal: {e}")

    def _handle_message(self, message: str):
        """Parse JSON and route to Nautilus MessageBus."""
        try:
            data = json.loads(message)
            if data.get("type") != "whale_alert":
                return
                
            payload = data.get("data", {})
            
            # Convert ISO timestamp to nanoseconds for Nautilus
            # e.g. "2026-04-13T19:04:24.422511+00:00"
            # Here we simplify for the example. In production, use fast parsing.
            ts_event = self.clock.timestamp_ns() 
            ts_init = self.clock.timestamp_ns()
            
            signal = WhaleSignalData(
                ts_event=ts_event,
                ts_init=ts_init,
                prediction_id=payload["prediction_id"],
                sequence_id=payload.get("sequence_id", 0),
                transaction_id=payload["transaction_id"],
                flow_type=payload["flow_type"],
                btc_value=float(payload["btc_value"]),
                urgency_score=float(payload["urgency_score"]),
                confidence_score=float(payload.get("confidence_score", 0.0)),
                rbf_enabled=bool(payload.get("rbf_enabled", False))
            )
            
            # Send to Nautilus Trader MessageBus
            self.msgbus.publish_data(signal)
            logger.debug(f"🐋 Routed Whale Signal to NT Bus: {signal.flow_type} | {signal.btc_value} BTC")
            
        except Exception as e:
            logger.error(f"Failed to parse whale signal: {e}")

class WhaleDataProvider(DataProvider):
    """Provider to register the client with Nautilus."""
    def __init__(self, client: WhaleDataClient):
        super().__init__(client=client)
