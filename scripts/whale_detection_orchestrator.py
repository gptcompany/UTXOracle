#!/usr/bin/env python3
"""
Whale Detection Orchestrator - Main Entry Point
Task: T017 - Coordinate monitor + broadcaster + database

Orchestrates:
- Database initialization
- WebSocket server (WhaleAlertBroadcaster)
- Mempool monitor (MempoolWhaleMonitor)
- Graceful shutdown with statistics

Usage:
    python3 scripts/whale_detection_orchestrator.py

    # Custom configuration
    python3 scripts/whale_detection_orchestrator.py \\
        --db-path data/custom.db \\
        --ws-port 8765 \\
        --mempool-url ws://localhost:8999/ws/track-mempool-tx
"""

import asyncio
import signal
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
import argparse

# Add parent dirs to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.mempool_whale_monitor import MempoolWhaleMonitor
from scripts.whale_alert_broadcaster import WhaleAlertBroadcaster
from scripts.config.mempool_config import get_config
from scripts.init_database import init_database

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class WhaleDetectionOrchestrator:
    """
    Main orchestrator for whale detection system

    Coordinates:
    - Database initialization
    - WebSocket broadcaster server
    - Mempool transaction monitor
    - Graceful shutdown
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        ws_host: str = "0.0.0.0",
        ws_port: int = 8765,
        mempool_ws_url: str = "ws://localhost:8999/ws/track-mempool-tx",
        whale_threshold_btc: float = 100.0,
        auth_enabled: bool = True,
    ):
        """
        Initialize orchestrator

        Args:
            db_path: Path to DuckDB database
            ws_host: WebSocket server host
            ws_port: WebSocket server port
            mempool_ws_url: Mempool.space WebSocket URL
            whale_threshold_btc: Minimum BTC to classify as whale
            auth_enabled: Enable WebSocket authentication (default: True)
        """
        # Load config
        config = get_config()
        self.db_path = db_path or config.database_path
        self.ws_host = ws_host
        self.ws_port = ws_port
        self.mempool_ws_url = mempool_ws_url
        self.whale_threshold_btc = whale_threshold_btc
        self.auth_enabled = auth_enabled

        # Components (will be initialized in start())
        self.broadcaster: Optional[WhaleAlertBroadcaster] = None
        self.monitor: Optional[MempoolWhaleMonitor] = None

        # Lifecycle
        self.start_time = datetime.now()
        self.shutdown_requested = False

        logger.info("Whale Detection Orchestrator initialized")
        logger.info(f"Database: {self.db_path}")
        logger.info(f"WebSocket Server: {ws_host}:{ws_port}")
        logger.info(f"Mempool URL: {mempool_ws_url}")
        logger.info(f"Whale Threshold: {whale_threshold_btc} BTC")

    async def initialize_database(self) -> bool:
        """Initialize database schema if needed"""
        logger.info("Initializing database...")

        try:
            success = init_database(self.db_path)
            if success:
                logger.info("✅ Database ready")
                return True
            else:
                logger.error("❌ Database initialization failed")
                return False
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}", exc_info=True)
            return False

    async def start(self):
        """Start all components"""
        logger.info("=" * 60)
        logger.info("🚀 Starting Whale Detection System...")
        logger.info("=" * 60)

        # Step 1: Initialize database
        if not await self.initialize_database():
            logger.error("Failed to initialize database - aborting")
            return

        # Step 2: Create and start WebSocket broadcaster
        logger.info("Starting WebSocket broadcaster...")
        self.broadcaster = WhaleAlertBroadcaster(
            host=self.ws_host, port=self.ws_port, auth_enabled=self.auth_enabled
        )

        # Start broadcaster in background task
        broadcaster_task = asyncio.create_task(
            self.broadcaster.start_server(), name="broadcaster"
        )

        # Give broadcaster time to start
        await asyncio.sleep(1.0)

        # Step 3: Create mempool monitor
        logger.info("Creating mempool whale monitor...")
        self.monitor = MempoolWhaleMonitor(
            mempool_ws_url=self.mempool_ws_url,
            whale_threshold_btc=self.whale_threshold_btc,
            db_path=self.db_path,
        )

        # Connect monitor to broadcaster
        self.monitor.broadcaster = self.broadcaster
        logger.info("✅ Monitor connected to broadcaster")

        # Step 4: Start monitor
        logger.info("Starting mempool monitor...")
        monitor_task = asyncio.create_task(self.monitor.start(), name="monitor")

        logger.info("=" * 60)
        logger.info("✅ Whale Detection System RUNNING")
        logger.info("=" * 60)
        logger.info("Press Ctrl+C to stop")

        # Run until shutdown requested
        try:
            await asyncio.gather(broadcaster_task, monitor_task)
        except asyncio.CancelledError:
            logger.info("Tasks cancelled - shutting down")

    async def stop(self):
        """Stop all components gracefully"""
        if self.shutdown_requested:
            logger.warning("Shutdown already in progress...")
            return

        self.shutdown_requested = True

        logger.info("=" * 60)
        logger.info("🛑 Shutting down Whale Detection System...")
        logger.info("=" * 60)

        # Stop monitor
        if self.monitor:
            logger.info("Stopping mempool monitor...")
            try:
                await asyncio.wait_for(self.monitor.stop(), timeout=5.0)
                logger.info("✅ Monitor stopped")
            except asyncio.TimeoutError:
                logger.warning("⚠️ Monitor stop timeout")

        # Stop broadcaster
        if self.broadcaster:
            logger.info("Stopping WebSocket broadcaster...")
            try:
                await asyncio.wait_for(self.broadcaster.stop(), timeout=5.0)
                logger.info("✅ Broadcaster stopped")
            except asyncio.TimeoutError:
                logger.warning("⚠️ Broadcaster stop timeout")

        # Print final statistics
        await self.print_statistics()

        logger.info("=" * 60)
        logger.info("✅ Shutdown complete")
        logger.info("=" * 60)

    async def print_statistics(self):
        """Print final system statistics"""
        uptime = (datetime.now() - self.start_time).total_seconds()

        logger.info("\n" + "=" * 60)
        logger.info("📊 FINAL STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Uptime: {uptime:.1f} seconds ({uptime / 60:.1f} minutes)")

        # Monitor stats
        if self.monitor:
            logger.info("\n🐋 Monitor Statistics:")
            stats = self.monitor.get_stats()
            for key, value in stats.items():
                if isinstance(value, dict):
                    logger.info(f"  {key}:")
                    for sub_key, sub_value in value.items():
                        logger.info(f"    {sub_key}: {sub_value}")
                else:
                    logger.info(f"  {key}: {value}")

        # Broadcaster stats
        if self.broadcaster:
            logger.info("\n📡 Broadcaster Statistics:")
            stats = self.broadcaster.get_stats()
            for key, value in stats.items():
                logger.info(f"  {key}: {value}")

        logger.info("=" * 60 + "\n")


async def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Whale Detection System Orchestrator")
    parser.add_argument("--db-path", help="Path to DuckDB database")
    parser.add_argument("--ws-host", default="0.0.0.0", help="WebSocket server host")
    parser.add_argument(
        "--ws-port", type=int, default=8765, help="WebSocket server port"
    )
    parser.add_argument(
        "--mempool-url",
        default="ws://localhost:8999/ws/track-mempool-tx",
        help="Mempool.space WebSocket URL",
    )
    parser.add_argument(
        "--whale-threshold",
        type=float,
        default=100.0,
        help="Minimum BTC to classify as whale",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable WebSocket authentication (development only)",
    )

    args = parser.parse_args()

    # Create orchestrator
    orchestrator = WhaleDetectionOrchestrator(
        db_path=args.db_path,
        ws_host=args.ws_host,
        ws_port=args.ws_port,
        mempool_ws_url=args.mempool_url,
        whale_threshold_btc=args.whale_threshold,
        auth_enabled=not args.no_auth,
    )

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def shutdown_handler(sig):
        logger.info(f"\n\n🛑 Received signal {sig.name} - initiating shutdown...")
        asyncio.create_task(orchestrator.stop())

    def reload_handler():
        logger.info("♻️ Received SIGHUP - reloading data...")
        if orchestrator.monitor:
            asyncio.create_task(orchestrator.monitor.reload_exchange_registry())

    # Register signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: shutdown_handler(s))
    
    loop.add_signal_handler(signal.SIGHUP, reload_handler)

    try:
        # Start system
        await orchestrator.start()
    except KeyboardInterrupt:
        logger.info("\n\n🛑 Keyboard interrupt - shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        # Ensure cleanup
        if not orchestrator.shutdown_requested:
            await orchestrator.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")
        sys.exit(0)
