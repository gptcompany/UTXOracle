import logging
from typing import Optional

from nautilus_trader.core.rust.model.data import Data
from nautilus_trader.core.rust.model.order import OrderSide
from nautilus_trader.core.rust.model.position import Position
from nautilus_trader.core.rust.model.venue import Venue
from nautilus_trader.core.rust.model.instrument import InstrumentId
from nautilus_trader.core.rust.model.book import OrderBook
from nautilus_trader.trading.strategy import Strategy, StrategyConfig

from scripts.nautilus_live.whale_data_client import WhaleSignalData

logger = logging.getLogger(__name__)

class WhaleImpactStrategyConfig(StrategyConfig):
    instrument_id: InstrumentId
    venue: Venue
    min_confidence: float = 0.85
    min_urgency: float = 0.70
    impact_threshold_pct: float = 1.5  # 1.5% expected slippage to trigger
    trade_size_usd: float = 10000.0    # Fixed size for testing

class WhaleImpactStrategy(Strategy):
    """
    Nautilus Trader Strategy: "Sensor Fusion" Whale Impact Execution.
    Correlates mempool whale flows with real-time Limit Order Book (LOB) depth.
    """
    def __init__(self, config: WhaleImpactStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id
        self.venue = config.venue
        self.min_confidence = config.min_confidence
        self.min_urgency = config.min_urgency
        self.impact_threshold_pct = config.impact_threshold_pct
        self.trade_size_usd = config.trade_size_usd

    def on_start(self):
        """Called when the strategy is started."""
        # Subscribe to OrderBook updates (L2/L4 depth)
        self.subscribe_order_book(self.instrument_id)
        # Subscribe to our custom UTXOracle Whale Signals
        self.subscribe_data(WhaleSignalData)
        logger.info(f"🐋 WhaleImpactStrategy started for {self.instrument_id}")

    def on_data(self, data: Data):
        """Handle incoming custom data streams (Whale Signals)."""
        if isinstance(data, WhaleSignalData):
            self._handle_whale_signal(data)

    def _handle_whale_signal(self, signal: WhaleSignalData):
        """Core logic for evaluating a whale signal against the LOB."""
        # 1. Quality Filters
        if signal.confidence_score < self.min_confidence:
            return
        if signal.urgency_score < self.min_urgency:
            return
        if signal.flow_type not in ("inflow", "outflow"):
            return

        # 2. Get current OrderBook state
        book: Optional[OrderBook] = self.cache.order_book(self.instrument_id)
        if not book or not book.is_valid:
            logger.warning("Whale signal received but OrderBook is invalid/missing.")
            return

        # 3. Market Impact Simulation (Sensor Fusion)
        # If INFLOW -> Whale might SELL -> Check BID liquidity
        # If OUTFLOW -> Whale might BUY -> Check ASK liquidity
        
        current_price = float(book.mid_price())
        whale_usd_value = signal.btc_value * current_price
        
        estimated_slippage_pct = 0.0
        
        if signal.flow_type == "inflow":
            # Simulate selling 'whale_usd_value' into the Bids
            estimated_slippage_pct = self._simulate_market_impact(book.bids(), whale_usd_value, current_price)
            trade_side = OrderSide.SELL  # Front-run the dump
            
        elif signal.flow_type == "outflow":
            # Simulate buying 'whale_usd_value' into the Asks
            estimated_slippage_pct = self._simulate_market_impact(book.asks(), whale_usd_value, current_price)
            trade_side = OrderSide.BUY   # Front-run the pump
            
        logger.info(f"Signal: {signal.btc_value} BTC {signal.flow_type.upper()} | Est. Impact: {estimated_slippage_pct:.2f}%")

        # 4. Execution Trigger
        if estimated_slippage_pct >= self.impact_threshold_pct:
            self._execute_snipe(trade_side, current_price)

    def _simulate_market_impact(self, book_side, usd_volume: float, mid_price: float) -> float:
        """
        Simulate walking the book to find the final execution price 
        if the entire USD volume is market-executed.
        """
        remaining_vol = usd_volume
        final_price = mid_price
        
        for level in book_side:
            level_price = float(level.price)
            level_qty_usd = float(level.quantity) * level_price
            
            if remaining_vol <= level_qty_usd:
                final_price = level_price
                break
            else:
                remaining_vol -= level_qty_usd
                final_price = level_price
                
        impact_pct = abs(final_price - mid_price) / mid_price * 100.0
        return impact_pct

    def _execute_snipe(self, side: OrderSide, current_price: float):
        """Execute a rapid entry."""
        position: Optional[Position] = self.cache.position(self.venue, self.instrument_id)
        if position and position.is_open:
            logger.info("Already in position, skipping signal.")
            return
            
        qty = self.trade_size_usd / current_price
        
        # Submit Market Order for immediate execution (Snipe)
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=self.cache.quantity(self.instrument_id, qty)
        )
        self.submit_order(order)
        logger.info(f"🔥 MISSILE FIRED: Submitted {side.name} order for {qty:.4f} BTC")
