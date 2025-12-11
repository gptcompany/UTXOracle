# Data Model: Advanced On-Chain Metrics (spec-021)

**Date**: 2025-12-10 | **Location**: `scripts/models/metrics_models.py`

## Entity Overview

| Entity | Purpose | Relationships |
|--------|---------|---------------|
| `URPDBucket` | Single price bucket with BTC amount | Part of `URPDResult.buckets` |
| `URPDResult` | Full URPD distribution | Contains `List[URPDBucket]` |
| `SupplyProfitLossResult` | Supply breakdown by profit/loss status | Uses `utxo_lifecycle` data |
| `ReserveRiskResult` | Long-term holder conviction metric | Uses `cointime` + `realized_metrics` |
| `SellSideRiskResult` | Distribution pressure metric | Uses `utxo_lifecycle` (spent UTXOs) |
| `CoinDaysDestroyedResult` | CDD + VDD metrics | Uses `cointime` coinblocks |

## Dataclass Definitions

### URPDBucket

```python
@dataclass
class URPDBucket:
    """Single price bucket in URPD distribution.

    Represents BTC supply accumulated within a price range.

    Attributes:
        price_low: Lower bound of bucket (USD)
        price_high: Upper bound of bucket (USD)
        btc_amount: Total BTC in bucket
        utxo_count: Number of UTXOs in bucket
        percentage: % of total supply in bucket
    """
    price_low: float
    price_high: float
    btc_amount: float
    utxo_count: int
    percentage: float

    def __post_init__(self):
        """Validate bucket fields."""
        if self.price_low < 0:
            raise ValueError(f"price_low must be >= 0: {self.price_low}")
        if self.price_high < self.price_low:
            raise ValueError(f"price_high must be >= price_low")
        if self.btc_amount < 0:
            raise ValueError(f"btc_amount must be >= 0: {self.btc_amount}")
        if self.utxo_count < 0:
            raise ValueError(f"utxo_count must be >= 0: {self.utxo_count}")
        if not 0.0 <= self.percentage <= 100.0:
            raise ValueError(f"percentage must be in [0, 100]: {self.percentage}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "price_low": self.price_low,
            "price_high": self.price_high,
            "btc_amount": self.btc_amount,
            "utxo_count": self.utxo_count,
            "percentage": self.percentage,
        }
```

### URPDResult

```python
@dataclass
class URPDResult:
    """UTXO Realized Price Distribution result.

    Shows distribution of unspent BTC by acquisition price (cost basis).
    Used for identifying support/resistance zones and profit-taking levels.

    Attributes:
        buckets: List of price buckets (sorted by price descending)
        bucket_size_usd: Size of each bucket in USD
        total_supply_btc: Total BTC in distribution
        current_price_usd: Current BTC price for context
        supply_above_price_btc: BTC with cost basis > current price (in loss)
        supply_below_price_btc: BTC with cost basis < current price (in profit)
        supply_above_price_pct: % of supply in loss
        supply_below_price_pct: % of supply in profit
        dominant_bucket: Bucket with highest BTC amount
        block_height: Block height at calculation
        timestamp: Calculation timestamp
    """
    buckets: list  # List[URPDBucket]
    bucket_size_usd: float
    total_supply_btc: float
    current_price_usd: float
    supply_above_price_btc: float
    supply_below_price_btc: float
    supply_above_price_pct: float
    supply_below_price_pct: float
    dominant_bucket: Optional[URPDBucket]
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate URPD result fields."""
        if self.bucket_size_usd <= 0:
            raise ValueError(f"bucket_size_usd must be > 0: {self.bucket_size_usd}")
        if self.total_supply_btc < 0:
            raise ValueError(f"total_supply_btc must be >= 0: {self.total_supply_btc}")
        if self.current_price_usd <= 0:
            raise ValueError(f"current_price_usd must be > 0: {self.current_price_usd}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "buckets": [b.to_dict() for b in self.buckets],
            "bucket_size_usd": self.bucket_size_usd,
            "total_supply_btc": self.total_supply_btc,
            "current_price_usd": self.current_price_usd,
            "supply_above_price_btc": self.supply_above_price_btc,
            "supply_below_price_btc": self.supply_below_price_btc,
            "supply_above_price_pct": self.supply_above_price_pct,
            "supply_below_price_pct": self.supply_below_price_pct,
            "dominant_bucket": self.dominant_bucket.to_dict() if self.dominant_bucket else None,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat(),
        }
```

### SupplyProfitLossResult

```python
@dataclass
class SupplyProfitLossResult:
    """Supply breakdown by profit/loss status.

    Classifies circulating supply by whether UTXOs are in profit
    (current price > creation price) or loss.

    Signals:
        > 95% in profit: Euphoria (cycle top warning)
        80-95% in profit: Bull market
        50-80% in profit: Transition
        < 50% in profit: Capitulation (accumulation zone)

    Attributes:
        current_price_usd: Price used for calculation
        total_supply_btc: Total unspent BTC
        supply_in_profit_btc: BTC where current_price > creation_price
        supply_in_loss_btc: BTC where current_price < creation_price
        supply_breakeven_btc: BTC where current_price == creation_price
        pct_in_profit: % of supply in profit
        pct_in_loss: % of supply in loss
        sth_in_profit_btc: STH (<155d) supply in profit
        sth_in_loss_btc: STH supply in loss
        sth_pct_in_profit: % of STH in profit
        lth_in_profit_btc: LTH (>=155d) supply in profit
        lth_in_loss_btc: LTH supply in loss
        lth_pct_in_profit: % of LTH in profit
        market_phase: "EUPHORIA" | "BULL" | "TRANSITION" | "CAPITULATION"
        signal_strength: 0.0 to 1.0 based on extremity
        block_height: Block height at calculation
        timestamp: Calculation timestamp
    """
    current_price_usd: float
    total_supply_btc: float
    supply_in_profit_btc: float
    supply_in_loss_btc: float
    supply_breakeven_btc: float
    pct_in_profit: float
    pct_in_loss: float
    sth_in_profit_btc: float
    sth_in_loss_btc: float
    sth_pct_in_profit: float
    lth_in_profit_btc: float
    lth_in_loss_btc: float
    lth_pct_in_profit: float
    market_phase: str  # "EUPHORIA" | "BULL" | "TRANSITION" | "CAPITULATION"
    signal_strength: float
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate supply profit/loss fields."""
        valid_phases = {"EUPHORIA", "BULL", "TRANSITION", "CAPITULATION"}
        if self.market_phase not in valid_phases:
            raise ValueError(f"market_phase must be one of {valid_phases}: {self.market_phase}")
        if not 0.0 <= self.signal_strength <= 1.0:
            raise ValueError(f"signal_strength must be in [0, 1]: {self.signal_strength}")
        if not 0.0 <= self.pct_in_profit <= 100.0:
            raise ValueError(f"pct_in_profit must be in [0, 100]: {self.pct_in_profit}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "current_price_usd": self.current_price_usd,
            "total_supply_btc": self.total_supply_btc,
            "supply_in_profit_btc": self.supply_in_profit_btc,
            "supply_in_loss_btc": self.supply_in_loss_btc,
            "supply_breakeven_btc": self.supply_breakeven_btc,
            "pct_in_profit": self.pct_in_profit,
            "pct_in_loss": self.pct_in_loss,
            "sth_in_profit_btc": self.sth_in_profit_btc,
            "sth_in_loss_btc": self.sth_in_loss_btc,
            "sth_pct_in_profit": self.sth_pct_in_profit,
            "lth_in_profit_btc": self.lth_in_profit_btc,
            "lth_in_loss_btc": self.lth_in_loss_btc,
            "lth_pct_in_profit": self.lth_pct_in_profit,
            "market_phase": self.market_phase,
            "signal_strength": self.signal_strength,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat(),
        }
```

### ReserveRiskResult

```python
@dataclass
class ReserveRiskResult:
    """Reserve Risk metric result.

    Measures confidence of long-term holders relative to price.
    Lower values = higher conviction (good buy zones).

    Formula: Reserve Risk = Price / (HODL Bank × Circulating Supply)
    HODL Bank = Cumulative Coindays Destroyed (opportunity cost)

    Signal Zones:
        < 0.002: Strong buy zone (historically cycle bottoms)
        0.002 - 0.008: Accumulation zone
        0.008 - 0.02: Fair value
        > 0.02: Distribution zone (cycle top warning)

    Attributes:
        reserve_risk: Main metric value
        current_price_usd: BTC price used
        hodl_bank: Cumulative coindays destroyed (scaled)
        circulating_supply_btc: Total unspent BTC
        mvrv: MVRV ratio (for context)
        liveliness: Network liveliness (from cointime)
        signal_zone: "STRONG_BUY" | "ACCUMULATION" | "FAIR_VALUE" | "DISTRIBUTION"
        confidence: Signal confidence (0.0 to 1.0)
        block_height: Block height at calculation
        timestamp: Calculation timestamp
    """
    reserve_risk: float
    current_price_usd: float
    hodl_bank: float
    circulating_supply_btc: float
    mvrv: float
    liveliness: float
    signal_zone: str  # "STRONG_BUY" | "ACCUMULATION" | "FAIR_VALUE" | "DISTRIBUTION"
    confidence: float
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate reserve risk fields."""
        valid_zones = {"STRONG_BUY", "ACCUMULATION", "FAIR_VALUE", "DISTRIBUTION"}
        if self.signal_zone not in valid_zones:
            raise ValueError(f"signal_zone must be one of {valid_zones}: {self.signal_zone}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")
        if self.reserve_risk < 0:
            raise ValueError(f"reserve_risk must be >= 0: {self.reserve_risk}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "reserve_risk": self.reserve_risk,
            "current_price_usd": self.current_price_usd,
            "hodl_bank": self.hodl_bank,
            "circulating_supply_btc": self.circulating_supply_btc,
            "mvrv": self.mvrv,
            "liveliness": self.liveliness,
            "signal_zone": self.signal_zone,
            "confidence": self.confidence,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat(),
        }
```

### SellSideRiskResult

```python
@dataclass
class SellSideRiskResult:
    """Sell-side Risk Ratio result.

    Ratio of realized profit to market cap. High values indicate
    aggressive profit-taking (potential distribution).

    Formula: Sell-side Risk = Realized Profit (30d) / Market Cap
    Realized Profit = Sum((spend_price - creation_price) × btc_value) for spent UTXOs

    Signal Zones:
        < 0.1%: Low distribution (bullish)
        0.1% - 0.3%: Normal profit-taking
        0.3% - 1.0%: Elevated distribution
        > 1.0%: Aggressive distribution (top warning)

    Attributes:
        sell_side_risk: Main metric value (ratio)
        sell_side_risk_pct: Metric as percentage
        realized_profit_usd: Profit realized in window
        realized_loss_usd: Loss realized in window (for context)
        net_realized_pnl_usd: Net realized P&L
        market_cap_usd: Market cap at calculation time
        window_days: Rolling window size (default 30)
        spent_utxos_in_window: Number of UTXOs spent
        signal_zone: "LOW" | "NORMAL" | "ELEVATED" | "AGGRESSIVE"
        confidence: Signal confidence (0.0 to 1.0)
        block_height: Block height at calculation
        timestamp: Calculation timestamp
    """
    sell_side_risk: float
    sell_side_risk_pct: float
    realized_profit_usd: float
    realized_loss_usd: float
    net_realized_pnl_usd: float
    market_cap_usd: float
    window_days: int
    spent_utxos_in_window: int
    signal_zone: str  # "LOW" | "NORMAL" | "ELEVATED" | "AGGRESSIVE"
    confidence: float
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate sell-side risk fields."""
        valid_zones = {"LOW", "NORMAL", "ELEVATED", "AGGRESSIVE"}
        if self.signal_zone not in valid_zones:
            raise ValueError(f"signal_zone must be one of {valid_zones}: {self.signal_zone}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")
        if self.sell_side_risk < 0:
            raise ValueError(f"sell_side_risk must be >= 0: {self.sell_side_risk}")
        if self.window_days <= 0:
            raise ValueError(f"window_days must be > 0: {self.window_days}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "sell_side_risk": self.sell_side_risk,
            "sell_side_risk_pct": self.sell_side_risk_pct,
            "realized_profit_usd": self.realized_profit_usd,
            "realized_loss_usd": self.realized_loss_usd,
            "net_realized_pnl_usd": self.net_realized_pnl_usd,
            "market_cap_usd": self.market_cap_usd,
            "window_days": self.window_days,
            "spent_utxos_in_window": self.spent_utxos_in_window,
            "signal_zone": self.signal_zone,
            "confidence": self.confidence,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat(),
        }
```

### CoinDaysDestroyedResult

```python
@dataclass
class CoinDaysDestroyedResult:
    """Coindays Destroyed (CDD) and Value Days Destroyed (VDD) result.

    CDD: When a UTXO is spent, CDD = age_days × btc_value
    VDD: CDD weighted by price = CDD × price

    Measures "old money" movement - spikes indicate long-term holders
    moving coins (distribution or exchange deposit).

    Attributes:
        cdd_total: Total CDD in period
        cdd_daily_avg: Average daily CDD
        vdd_total: Total VDD in period (CDD × price)
        vdd_daily_avg: Average daily VDD
        vdd_multiple: VDD / 365d_MA(VDD), > 2.0 = significant distribution
        window_days: Analysis window (default 30)
        spent_utxos_count: Number of UTXOs spent
        avg_utxo_age_days: Average age of spent UTXOs
        max_single_day_cdd: Peak CDD in a single day
        max_single_day_date: Date of peak CDD
        current_price_usd: Price used for VDD
        signal_zone: "LOW_ACTIVITY" | "NORMAL" | "ELEVATED" | "SPIKE"
        confidence: Signal confidence (0.0 to 1.0)
        block_height: Block height at calculation
        timestamp: Calculation timestamp
    """
    cdd_total: float
    cdd_daily_avg: float
    vdd_total: float
    vdd_daily_avg: float
    vdd_multiple: Optional[float]  # None if insufficient history for MA
    window_days: int
    spent_utxos_count: int
    avg_utxo_age_days: float
    max_single_day_cdd: float
    max_single_day_date: Optional[date]
    current_price_usd: float
    signal_zone: str  # "LOW_ACTIVITY" | "NORMAL" | "ELEVATED" | "SPIKE"
    confidence: float
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate CDD/VDD fields."""
        valid_zones = {"LOW_ACTIVITY", "NORMAL", "ELEVATED", "SPIKE"}
        if self.signal_zone not in valid_zones:
            raise ValueError(f"signal_zone must be one of {valid_zones}: {self.signal_zone}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")
        if self.cdd_total < 0:
            raise ValueError(f"cdd_total must be >= 0: {self.cdd_total}")
        if self.vdd_total < 0:
            raise ValueError(f"vdd_total must be >= 0: {self.vdd_total}")
        if self.window_days <= 0:
            raise ValueError(f"window_days must be > 0: {self.window_days}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "cdd_total": self.cdd_total,
            "cdd_daily_avg": self.cdd_daily_avg,
            "vdd_total": self.vdd_total,
            "vdd_daily_avg": self.vdd_daily_avg,
            "vdd_multiple": self.vdd_multiple,
            "window_days": self.window_days,
            "spent_utxos_count": self.spent_utxos_count,
            "avg_utxo_age_days": self.avg_utxo_age_days,
            "max_single_day_cdd": self.max_single_day_cdd,
            "max_single_day_date": self.max_single_day_date.isoformat() if self.max_single_day_date else None,
            "current_price_usd": self.current_price_usd,
            "signal_zone": self.signal_zone,
            "confidence": self.confidence,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat(),
        }
```

## Validation Rules Summary

| Field | Rule | Error Message |
|-------|------|---------------|
| `price_*` | >= 0 | "must be >= 0" |
| `btc_*` | >= 0 | "must be >= 0" |
| `percentage` | [0, 100] | "must be in [0, 100]" |
| `confidence` | [0, 1] | "must be in [0, 1]" |
| `signal_zone` / `market_phase` | Enum values | "must be one of {valid_set}" |
| `window_days` | > 0 | "must be > 0" |

## State Transitions

### Market Phase (Supply Profit/Loss)

```
                ┌──────────────────────────────┐
                │                              │
    >95%  ───>  │        EUPHORIA              │ ───> <95%
                │                              │
                └───────────┬──────────────────┘
                            │
                            v
                ┌──────────────────────────────┐
                │                              │
    80-95% ──>  │          BULL                │ ──> <80%
                │                              │
                └───────────┬──────────────────┘
                            │
                            v
                ┌──────────────────────────────┐
                │                              │
    50-80% ──>  │       TRANSITION             │ ──> <50%
                │                              │
                └───────────┬──────────────────┘
                            │
                            v
                ┌──────────────────────────────┐
                │                              │
    <50%  ───>  │      CAPITULATION            │ ───> >50%
                │                              │
                └──────────────────────────────┘
```

### Reserve Risk Signal Zones

```
Reserve Risk Value:
0 ────────────────────────────────────────> 0.05+
  │<0.002      │0.002-0.008│0.008-0.02 │>0.02
  │            │           │           │
  v            v           v           v
STRONG_BUY  ACCUMULATION  FAIR_VALUE  DISTRIBUTION
```

## Integration with Existing Models

These new dataclasses follow the same patterns as:
- `MVRVExtendedSignal` (spec-020)
- `CointimeSignal` (spec-018)
- `RollingWassersteinResult` (spec-010)

All include:
- `to_dict()` for JSON serialization
- `__post_init__()` validation
- `timestamp` and `block_height` metadata
- Signal zone/phase classification
- Confidence score
