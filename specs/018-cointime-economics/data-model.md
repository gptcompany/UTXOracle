# Data Model: Cointime Economics

**Spec**: spec-018
**Date**: 2025-12-06

---

## Entity Definitions

### CoinblocksMetrics

```python
@dataclass
class CoinblocksMetrics:
    """Per-block coinblocks metrics."""

    block_height: int
    timestamp: datetime

    # Per-block
    coinblocks_created: float
    coinblocks_destroyed: float

    # Cumulative (all time)
    cumulative_created: float
    cumulative_destroyed: float

    # Derived
    liveliness: float  # destroyed / created (0-1)
    vaultedness: float  # 1 - liveliness
```

### CointimeSupply

```python
@dataclass
class CointimeSupply:
    """Supply breakdown by activity."""

    block_height: int
    timestamp: datetime
    total_supply_btc: float

    # Supply split
    active_supply_btc: float    # total × liveliness
    vaulted_supply_btc: float   # total × vaultedness
    active_supply_pct: float
    vaulted_supply_pct: float
```

### CointimeValuation

```python
@dataclass
class CointimeValuation:
    """AVIV and True Market Mean."""

    block_height: int
    timestamp: datetime
    current_price_usd: float
    market_cap_usd: float

    # Cointime metrics
    active_supply_btc: float
    true_market_mean_usd: float  # market_cap / active_supply
    aviv_ratio: float  # price / tmm

    # Context
    aviv_percentile: float  # 0-100
    valuation_zone: str  # "UNDERVALUED" | "FAIR" | "OVERVALUED"
```

### CointimeSignal

```python
@dataclass
class CointimeSignal:
    """Trading signal from Cointime."""

    block_height: int
    timestamp: datetime

    # Trend
    liveliness_7d_change: float
    liveliness_30d_change: float
    liveliness_trend: str

    # Valuation
    aviv_ratio: float
    valuation_zone: str

    # Pattern detection
    extreme_dormancy: bool     # liveliness < 0.15
    supply_squeeze: bool       # active_supply declining
    distribution_warning: bool # AVIV > 2.0 + liveliness spike

    # For fusion
    cointime_vote: float  # -1 to +1
    confidence: float
```

---

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS cointime_metrics (
    block_height INTEGER PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,

    -- Per-block
    coinblocks_created REAL NOT NULL,
    coinblocks_destroyed REAL NOT NULL,

    -- Cumulative
    cumulative_created REAL NOT NULL,
    cumulative_destroyed REAL NOT NULL,

    -- Derived
    liveliness REAL NOT NULL,
    vaultedness REAL NOT NULL,

    -- Supply
    active_supply_btc REAL NOT NULL,
    vaulted_supply_btc REAL NOT NULL,

    -- Valuation
    true_market_mean_usd REAL,
    aviv_ratio REAL,
    aviv_percentile REAL
);

CREATE INDEX idx_cointime_timestamp ON cointime_metrics(timestamp);
```

---

## Relationships

```
UTXOLifecycle (spec-017) ──► CoinblocksMetrics (per block)
                                    │
CoinblocksMetrics ──► CointimeSupply (derived)
                                    │
CointimeSupply ──► CointimeValuation (with price)
                                    │
CointimeValuation ──► CointimeSignal (pattern detection)
                                    │
CointimeSignal.cointime_vote ──► EnhancedFusion (10th component)
```
