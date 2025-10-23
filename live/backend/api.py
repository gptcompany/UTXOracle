"""
Task 04: FastAPI WebSocket Server
Agent: data-streamer

Responsibilities:
- WebSocket endpoint for real-time data streaming
- Client connection management
- Broadcast price updates and histogram data
- CORS configuration
"""

import logging
import sys
from contextlib import asynccontextmanager
import time
from pathlib import Path
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import random

from live.shared.models import (
    MempoolState,
    WebSocketMessage,
    MempoolUpdateData,
    TransactionPoint,
    SystemStats,
)

# Configure logging to ensure our messages appear
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG to see broadcast messages
    format="%(levelname)s:     %(name)s - %(message)s",
    stream=sys.stderr,
    force=True,
)

logger = logging.getLogger("live.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    # Startup
    # DEBUG: Write to file to verify lifespan is called
    with open("/tmp/lifespan_debug.txt", "w") as f:
        f.write("LIFESPAN CALLED!\n")

    logger.info("=" * 60)
    logger.info("LIFESPAN: Starting up...")
    logger.info("=" * 60)
    app.state.start_time = time.time()
    logger.info("UTXOracle Live API started")

    # Import here to avoid circular dependency
    from live.backend.orchestrator import get_orchestrator

    logger.info("FastAPI startup: Initializing pipeline orchestrator...")
    orchestrator = get_orchestrator()
    logger.info(f"Orchestrator created: {orchestrator}")

    # Start orchestrator in background task
    import asyncio

    logger.info("Creating orchestrator background task...")
    orchestrator_task = asyncio.create_task(orchestrator.start())
    logger.info(f"Task created successfully: {orchestrator_task}")
    app.state.orchestrator_task = orchestrator_task
    app.state.orchestrator = orchestrator
    logger.info("Pipeline orchestrator started - task running in background")
    logger.info("=" * 60)

    yield  # Application runs here

    # Shutdown
    logger.info("FastAPI shutdown: Stopping pipeline orchestrator...")
    if hasattr(app.state, "orchestrator"):
        await app.state.orchestrator.stop()
    logger.info("UTXOracle Live API shutting down")


# FastAPI App Setup
app = FastAPI(
    title="UTXOracle Live API",
    description="Real-time Bitcoin price oracle from mempool analysis",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


class DataStreamer:
    """Manages WebSocket client connections and broadcasts mempool updates"""

    def __init__(self, max_updates_per_second: int = 10):
        self.active_clients: List[WebSocket] = []
        self.max_updates_per_second = max_updates_per_second
        self.last_broadcast_time = 0.0
        self.min_broadcast_interval = (
            1.0 / max_updates_per_second if max_updates_per_second > 0 else 0.0
        )
        self.analyzer = None  # Set by orchestrator

    def set_analyzer(self, analyzer):
        """Set analyzer reference for transaction history (T074e)"""
        self.analyzer = analyzer

    async def register_client(self, websocket: WebSocket) -> None:
        """Register a new WebSocket client (must already be accepted)"""
        self.active_clients.append(websocket)
        logger.info(f"Client connected. Total clients: {len(self.active_clients)}")

    def unregister_client(self, websocket: WebSocket) -> None:
        """Unregister a disconnected WebSocket client"""
        if websocket in self.active_clients:
            self.active_clients.remove(websocket)
            logger.info(
                f"Client disconnected. Total clients: {len(self.active_clients)}"
            )

    async def broadcast(self, state: MempoolState) -> None:
        """Broadcast MempoolState to all connected clients"""
        current_time = time.time()
        if self.min_broadcast_interval > 0:
            elapsed = current_time - self.last_broadcast_time
            if elapsed < self.min_broadcast_interval:
                return

        if not self.active_clients:
            logger.debug(
                f"Broadcast skipped: No active clients connected (clients={len(self.active_clients)}, txs={state.active_tx_count})"
            )
            return

        message = self._create_websocket_message(state)
        message_json = message.model_dump_json()

        logger.info(
            f"Broadcasting to {len(self.active_clients)} client(s): price=${state.price:,.0f}, confidence={state.confidence:.2f}, txs={state.active_tx_count}"
        )

        disconnected_clients = []
        for client in self.active_clients:
            try:
                await client.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")
                disconnected_clients.append(client)

        for client in disconnected_clients:
            self.unregister_client(client)

        self.last_broadcast_time = current_time

    async def send_to_client(self, websocket: WebSocket, state: MempoolState) -> None:
        """Send initial state to a single client (includes full transaction history)"""
        try:
            message = self._create_websocket_message(state)
            message_json = message.model_dump_json()
            await websocket.send_text(message_json)
            logger.info(
                f"Sent initial sync to client: price=${state.price:,.0f}, txs={state.active_tx_count}"
            )
        except Exception as e:
            logger.error(f"Failed to send initial sync to client: {e}")
            raise

    def _create_websocket_message(self, state: MempoolState) -> WebSocketMessage:
        """Convert MempoolState to WebSocketMessage (T068: includes transaction history, T106: includes baseline)"""
        transactions = []
        baseline_data = None

        # T068: Get transaction history from analyzer if available
        # T106: Get baseline data from analyzer if available
        if hasattr(self, "analyzer") and self.analyzer:
            history = self.analyzer.get_transaction_history()
            transactions = [
                point
                for point in history  # history already contains TransactionPoint objects
            ]

            # T106: Get combined history (baseline + mempool)
            combined = self.analyzer.get_combined_history()
            if combined["baseline"] is not None:
                from live.shared.models import BaselineData

                bl = combined["baseline"]

                # T107-T109: Convert baseline intraday_points to TransactionPoint format
                baseline_transactions = []

                # Use Step 10 intraday_points if available (dense point cloud)
                if hasattr(bl, "intraday_points") and bl.intraday_points:
                    for price, block_height, timestamp in bl.intraday_points:
                        baseline_transactions.append(
                            TransactionPoint(
                                timestamp=timestamp,
                                price=price,  # Use calculated price from Step 10
                                btc_amount=None,  # Not needed for baseline visualization
                            )
                        )
                    logger.debug(
                        f"Using {len(baseline_transactions)} intraday points for baseline visualization"
                    )
                # Fallback: use raw transactions with scatter if intraday_points not available
                elif hasattr(bl, "transactions") and bl.transactions:
                    for amount_btc, timestamp in bl.transactions:
                        baseline_transactions.append(
                            TransactionPoint(
                                timestamp=timestamp,
                                # BUGFIX 2025-10-23: Calculate individual price with ±2% scatter (Bug #2)
                                # Simulates real market variation instead of single consensus price
                                price=bl.price * (0.98 + random.random() * 0.04),
                            )
                        )
                    logger.debug(
                        f"Using {len(baseline_transactions)} raw transactions (fallback)"
                    )

                baseline_data = BaselineData(
                    price=bl.price,
                    price_min=bl.price_min,
                    price_max=bl.price_max,
                    confidence=bl.confidence,
                    timestamp=bl.timestamp,
                    block_height=bl.block_height,
                    transactions=baseline_transactions,
                )

        stats = SystemStats(
            total_received=state.total_received,
            total_filtered=state.total_filtered,
            active_in_window=state.active_tx_count,
            uptime_seconds=state.uptime_seconds,
        )

        data = MempoolUpdateData(
            price=state.price,
            confidence=state.confidence,
            transactions=transactions,
            stats=stats,
            timestamp=time.time(),
            baseline=baseline_data,  # T106: Add baseline
        )

        return WebSocketMessage(type="mempool_update", data=data)

    def get_client_count(self) -> int:
        """Get number of connected clients"""
        return len(self.active_clients)


# Global DataStreamer instance
streamer = DataStreamer(max_updates_per_second=10)


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve frontend HTML"""
    index_path = frontend_dir / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            content="<h1>UTXOracle Live</h1><p>Frontend not found</p>",
            status_code=404,
        )
    return HTMLResponse(content=index_path.read_text())


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse(
        {
            "status": "ok",
            "uptime": time.time() - app.state.start_time,
            "clients": streamer.get_client_count(),
        }
    )


@app.websocket("/ws/mempool")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time mempool updates"""
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info(f"WebSocket connection attempt from {client_host}")

    await websocket.accept()
    logger.info(f"WebSocket accepted from {client_host}")

    await streamer.register_client(websocket)
    logger.info(
        f"Client {client_host} registered. Active clients: {len(streamer.active_clients)}"
    )

    # Send initial sync with full history
    if hasattr(app.state, "orchestrator") and app.state.orchestrator.analyzer:
        initial_state = app.state.orchestrator.analyzer.get_state()
        await streamer.send_to_client(websocket, initial_state)
        logger.info(f"Sent initial sync to {client_host}")

    try:
        while True:
            # Use receive() instead of receive_text() to handle all message types
            # including ping/pong frames and avoid disconnecting on non-text messages
            message = await websocket.receive()
            # Log any client messages for debugging
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect()
    except WebSocketDisconnect:
        streamer.unregister_client(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        streamer.unregister_client(websocket)


__all__ = ["app", "DataStreamer", "streamer"]


@app.get("/styles.css")
async def serve_styles():
    """Serve CSS file"""
    css_path = frontend_dir / "styles.css"
    if not css_path.exists():
        return HTMLResponse(content="/* CSS not found */", status_code=404)
    return HTMLResponse(content=css_path.read_text(), media_type="text/css")


@app.get("/mempool-viz.js")
async def serve_js():
    """Serve JavaScript file"""
    js_path = frontend_dir / "mempool-viz.js"
    if not js_path.exists():
        return HTMLResponse(content="// JS not found", status_code=404)
    return HTMLResponse(
        content=js_path.read_text(), media_type="application/javascript"
    )
