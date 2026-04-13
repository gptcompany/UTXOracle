import asyncio
import logging
import sys

from nautilus_trader.core.rust.common import Clock
from nautilus_trader.core.rust.model.venue import Venue
from nautilus_trader.core.rust.model.instrument import InstrumentId
from nautilus_trader.trading.node import TradingNode

from scripts.nautilus_live.whale_data_client import WhaleDataClient, WhaleDataProvider
from scripts.nautilus_live.strategy import WhaleImpactStrategy, WhaleImpactStrategyConfig
from scripts.nautilus_live.nt_adapter import NTWhaleAdapter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Initializing Nautilus Trader Node for UTXOracle Whale Detection...")
    
    # 1. Check Execution Gatekeeper before starting
    # This prevents the trading node from starting if UTXOracle is degraded
    gatekeeper = NTWhaleAdapter(api_url="http://127.0.0.1:8011", max_jitter_ms=500)
    if not await gatekeeper.can_execute():
        logger.error("🛑 UTXOracle Gatekeeper denied execution (System degraded or high jitter). Aborting startup.")
        sys.exit(1)
        
    logger.info("✅ UTXOracle Gatekeeper passed. System is healthy.")

    # 2. Setup Nautilus Node
    node = TradingNode()
    
    # 3. Setup Data Client (WebSocket Stream to UTXOracle)
    loop = asyncio.get_event_loop()
    clock = Clock()
    
    whale_client = WhaleDataClient(loop=loop, clock=clock, ws_url="ws://127.0.0.1:8011/api/execution/btc/stream")
    whale_provider = WhaleDataProvider(client=whale_client)
    
    # Register Provider
    node.data_engine.register_provider(whale_provider)
    
    # 4. Configure Strategy
    # In a real setup, Venue and InstrumentId would be fully configured for Hyperliquid/Binance
    venue = Venue("HYPERLIQUID")
    instrument = InstrumentId.from_str("BTC-USDT.HYPERLIQUID")
    
    config = WhaleImpactStrategyConfig(
        instrument_id=instrument,
        venue=venue,
        min_confidence=0.85,
        min_urgency=0.70,
        impact_threshold_pct=1.5,
        trade_size_usd=10000.0
    )
    
    strategy = WhaleImpactStrategy(config=config)
    node.trader.add_strategy(strategy)
    
    # 5. Start Execution
    logger.info("🚀 Starting Nautilus Trading Node...")
    await node.start()
    
    try:
        # Keep alive
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await node.stop()

if __name__ == "__main__":
    asyncio.run(main())
