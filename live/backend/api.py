"""
Task 04: FastAPI WebSocket Server
Agent: data-streamer

Responsibilities:
- WebSocket endpoint for real-time data streaming
- Client connection management
- Broadcast price updates and histogram data
- CORS configuration
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from live.shared.models import (
    MempoolState,
    WebSocketMessage,
    MempoolUpdateData,
    TransactionPoint,
    SystemStats,
)

logger = logging.getLogger("live.api")

# FastAPI App Setup
app = FastAPI(
    title="UTXOracle Live API",
    description="Real-time Bitcoin price oracle from mempool analysis",
    version="1.0.0",
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
        self.min_broadcast_interval = 1.0 / max_updates_per_second if max_updates_per_second > 0 else 0.0

    async def register_client(self, websocket: WebSocket) -> None:
        """Register a new WebSocket client (must already be accepted)"""
        self.active_clients.append(websocket)
        logger.info(f"Client connected. Total clients: {len(self.active_clients)}")

    def unregister_client(self, websocket: WebSocket) -> None:
        """Unregister a disconnected WebSocket client"""
        if websocket in self.active_clients:
            self.active_clients.remove(websocket)
            logger.info(f"Client disconnected. Total clients: {len(self.active_clients)}")

    async def broadcast(self, state: MempoolState) -> None:
        """Broadcast MempoolState to all connected clients"""
        current_time = time.time()
        if self.min_broadcast_interval > 0:
            elapsed = current_time - self.last_broadcast_time
            if elapsed < self.min_broadcast_interval:
                return

        if not self.active_clients:
            return

        message = self._create_websocket_message(state)
        message_json = message.model_dump_json()

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

    def _create_websocket_message(self, state: MempoolState) -> WebSocketMessage:
        """Convert MempoolState to WebSocketMessage"""
        transactions = []

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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time mempool updates"""
    await websocket.accept()
    await streamer.register_client(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        streamer.unregister_client(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        streamer.unregister_client(websocket)


@app.on_event("startup")
async def startup_event():
    """Initialize app state on startup"""
    app.state.start_time = time.time()
    logger.info("UTXOracle Live API started")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    logger.info("UTXOracle Live API shutting down")


__all__ = ["app", "DataStreamer", "streamer"]
