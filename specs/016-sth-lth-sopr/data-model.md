# Data Model: STH/LTH SOPR

**Spec**: spec-016
**Date**: 2025-12-06

---

## Entity Definitions

### SpentOutputSOPR

Individual spent output with SOPR calculation.

```python
@dataclass
class SpentOutputSOPR:
    """SOPR calculation for a single spent output."""

    # Identity
    txid: str                           # Spending transaction ID
    vout_index: int                     # Original output index
    outpoint: str                       # f"{prev_txid}:{vout_index}"

    # Lifecycle
    creation_block: int                 # Block where UTXO was created
    creation_timestamp: datetime        # Creation timestamp
    creation_price_usd: float           # UTXOracle price at creation
    spend_block: int                    # Block where UTXO was spent
    spend_timestamp: datetime           # Spend timestamp
    spend_price_usd: float              # UTXOracle price at spend
    btc_value: float                    # BTC amount

    # SOPR Calculation
    sopr: float                         # spend_price / creation_price
    age_days: int                       # Days between creation and spend
    age_blocks: int                     # Blocks between creation and spend

    # Classification
    cohort: str                         # "STH" | "LTH"
    profit_loss: str                    # "PROFIT" | "LOSS" | "BREAKEVEN"

    # Validity
    is_valid: bool                      # True if both prices available
    price_source: str                   # "utxoracle" | "mempool" | "fallback"
    validation_errors: list[str]        # Any issues encountered

    def __post_init__(self):
        """Calculate derived fields."""
        if self.creation_price_usd > 0 and self.spend_price_usd > 0:
            self.sopr = self.spend_price_usd / self.creation_price_usd
            self.is_valid = True
        else:
            self.sopr = 0.0
            self.is_valid = False

        self.age_blocks = self.spend_block - self.creation_block
        self.age_days = self.age_blocks // 144  # ~144 blocks/day

        # Cohort classification (155 days threshold)
        sth_threshold = int(os.getenv("SOPR_STH_THRESHOLD_DAYS", "155"))
        self.cohort = "STH" if self.age_days < sth_threshold else "LTH"

        # Profit/Loss classification
        if self.sopr > 1.01:
            self.profit_loss = "PROFIT"
        elif self.sopr < 0.99:
            self.profit_loss = "LOSS"
        else:
            self.profit_loss = "BREAKEVEN"
```

### BlockSOPR

Aggregated SOPR for a single block with STH/LTH split.

```python
@dataclass
class BlockSOPR:
    """Aggregated SOPR metrics for a block."""

    # Identity
    block_height: int
    block_hash: str
    timestamp: datetime

    # Aggregate SOPR
    aggregate_sopr: float               # Weighted average of all outputs
    sth_sopr: float | None              # STH-only weighted average
    lth_sopr: float | None              # LTH-only weighted average

    # Sample Sizes
    total_outputs: int                  # Total spent outputs processed
    valid_outputs: int                  # Outputs with valid SOPR
    sth_outputs: int                    # STH cohort count
    lth_outputs: int                    # LTH cohort count

    # Volume
    total_btc_moved: float              # Total BTC in spent outputs
    sth_btc_moved: float                # STH BTC volume
    lth_btc_moved: float                # LTH BTC volume

    # Profit/Loss Distribution
    profit_outputs: int
    loss_outputs: int
    breakeven_outputs: int
    profit_ratio: float                 # profit_outputs / valid_outputs

    # Validity
    is_valid: bool                      # True if minimum samples met
    min_samples: int                    # Minimum required (default: 100)

    @classmethod
    def from_outputs(
        cls,
        block_height: int,
        block_hash: str,
        timestamp: datetime,
        outputs: list[SpentOutputSOPR],
        min_samples: int = 100
    ) -> "BlockSOPR":
        """Aggregate individual outputs into block SOPR."""
        valid = [o for o in outputs if o.is_valid]
        sth = [o for o in valid if o.cohort == "STH"]
        lth = [o for o in valid if o.cohort == "LTH"]

        def weighted_avg(outputs: list[SpentOutputSOPR]) -> float | None:
            if not outputs:
                return None
            total_value = sum(o.btc_value for o in outputs)
            if total_value == 0:
                return None
            return sum(o.sopr * o.btc_value for o in outputs) / total_value

        return cls(
            block_height=block_height,
            block_hash=block_hash,
            timestamp=timestamp,
            aggregate_sopr=weighted_avg(valid) or 0.0,
            sth_sopr=weighted_avg(sth),
            lth_sopr=weighted_avg(lth),
            total_outputs=len(outputs),
            valid_outputs=len(valid),
            sth_outputs=len(sth),
            lth_outputs=len(lth),
            total_btc_moved=sum(o.btc_value for o in valid),
            sth_btc_moved=sum(o.btc_value for o in sth),
            lth_btc_moved=sum(o.btc_value for o in lth),
            profit_outputs=len([o for o in valid if o.profit_loss == "PROFIT"]),
            loss_outputs=len([o for o in valid if o.profit_loss == "LOSS"]),
            breakeven_outputs=len([o for o in valid if o.profit_loss == "BREAKEVEN"]),
            profit_ratio=len([o for o in valid if o.profit_loss == "PROFIT"]) / len(valid) if valid else 0,
            is_valid=len(valid) >= min_samples,
            min_samples=min_samples,
        )
```

### SOPRWindow

Rolling window for pattern detection.

```python
@dataclass
class SOPRWindow:
    """Rolling window of SOPR data for pattern detection."""

    # Window Definition
    start_block: int
    end_block: int
    window_blocks: int                  # Number of blocks in window
    window_days: int                    # Approximate days

    # Rolling Statistics
    sth_sopr_mean: float
    sth_sopr_min: float
    sth_sopr_max: float
    sth_sopr_std: float

    lth_sopr_mean: float | None
    lth_sopr_min: float | None
    lth_sopr_max: float | None

    # Trend Analysis
    sth_sopr_trend: str                 # "RISING" | "FALLING" | "STABLE"
    sth_sopr_slope: float               # Linear regression slope

    # Pattern Detection
    consecutive_sth_below_1: int        # Days with STH-SOPR < 1
    consecutive_sth_above_1: int        # Days with STH-SOPR > 1
    last_breakeven_cross: datetime | None
    cross_direction: str | None         # "UP" | "DOWN"
```

### SOPRSignal

Trading signal generated from SOPR patterns.

```python
@dataclass
class SOPRSignal:
    """Trading signal from SOPR pattern detection."""

    # Identity
    block_height: int
    timestamp: datetime
    signal_type: str                    # "CAPITULATION" | "BREAKEVEN_CROSS" | "DISTRIBUTION"

    # Signal Details
    direction: str                      # "BULLISH" | "BEARISH" | "NEUTRAL"
    strength: float                     # 0.0 to 1.0
    confidence: float                   # Based on sample size and pattern clarity

    # Trigger Data
    trigger_value: float                # SOPR value that triggered signal
    trigger_threshold: float            # Threshold that was crossed
    consecutive_periods: int            # How many periods pattern held

    # Context
    sth_sopr: float
    lth_sopr: float | None
    current_price: float

    # For Fusion Integration
    sopr_vote: float                    # -1 to +1 for Monte Carlo fusion

    @classmethod
    def capitulation_signal(
        cls,
        block_height: int,
        timestamp: datetime,
        sth_sopr: float,
        consecutive_days: int,
        current_price: float
    ) -> "SOPRSignal":
        """Generate capitulation (bullish) signal."""
        # Strength increases with consecutive days
        strength = min(1.0, consecutive_days / 7)
        confidence = min(1.0, strength * 0.8)

        return cls(
            block_height=block_height,
            timestamp=timestamp,
            signal_type="CAPITULATION",
            direction="BULLISH",
            strength=strength,
            confidence=confidence,
            trigger_value=sth_sopr,
            trigger_threshold=1.0,
            consecutive_periods=consecutive_days,
            sth_sopr=sth_sopr,
            lth_sopr=None,
            current_price=current_price,
            sopr_vote=0.5 + (strength * 0.3),  # +0.5 to +0.8
        )
```

---

## Database Schema

```sql
-- Block SOPR metrics
CREATE TABLE IF NOT EXISTS sopr_blocks (
    block_height INTEGER PRIMARY KEY,
    block_hash TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,

    -- Aggregate
    aggregate_sopr REAL NOT NULL,
    sth_sopr REAL,
    lth_sopr REAL,

    -- Counts
    total_outputs INTEGER NOT NULL,
    valid_outputs INTEGER NOT NULL,
    sth_outputs INTEGER NOT NULL,
    lth_outputs INTEGER NOT NULL,

    -- Volume
    total_btc_moved REAL NOT NULL,
    sth_btc_moved REAL NOT NULL,
    lth_btc_moved REAL NOT NULL,

    -- P/L
    profit_ratio REAL NOT NULL,

    is_valid BOOLEAN NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Signals
CREATE TABLE IF NOT EXISTS sopr_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    block_height INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    signal_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    strength REAL NOT NULL,
    sopr_vote REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_sopr_blocks_timestamp ON sopr_blocks(timestamp);
CREATE INDEX idx_sopr_signals_type ON sopr_signals(signal_type);
```

---

## Relationships

```
SpentOutputSOPR (many) ──► BlockSOPR (one per block)
                              │
BlockSOPR (many) ──► SOPRWindow (rolling aggregation)
                              │
SOPRWindow ──► SOPRSignal (pattern detection)
                              │
SOPRSignal.sopr_vote ──► EnhancedFusionResult (9th component)
```
