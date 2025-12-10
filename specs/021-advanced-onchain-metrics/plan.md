# spec-021: Implementation Plan

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Advanced On-Chain Metrics                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐                                           │
│  │  utxo_lifecycle  │ ◄── Base data layer (spec-017)            │
│  │   (DuckDB)       │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           ▼                                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Metric Modules                           │ │
│  │                                                              │ │
│  │  ┌──────────┐  ┌─────────────┐  ┌─────────────┐            │ │
│  │  │  urpd.py │  │supply_pl.py │  │reserve_risk │            │ │
│  │  │  (P0)    │  │   (P1)      │  │    (P1)     │            │ │
│  │  └──────────┘  └─────────────┘  └─────────────┘            │ │
│  │                                                              │ │
│  │  ┌──────────────┐  ┌──────────────┐                        │ │
│  │  │sell_side_risk│  │ coindays.py  │                        │ │
│  │  │    (P1)      │  │  (P2: CDD/VDD)│                        │ │
│  │  └──────────────┘  └──────────────┘                        │ │
│  │                                                              │ │
│  └────────────────────────────────────────────────────────────┘ │
│           │                                                      │
│           ▼                                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              monte_carlo_fusion.py                          │ │
│  │         (Signal integration + weights)                      │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: URPD (P0) - 4-6 hours

### Step 1.1: Create Module Structure (30 min)
```python
# scripts/metrics/urpd.py
"""
URPD - UTXO Realized Price Distribution (spec-021)

Shows distribution of unspent BTC by acquisition price.
Key metric for identifying support/resistance zones.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import duckdb
```

### Step 1.2: Define Data Structures (30 min)
```python
@dataclass
class URPDBucket:
    price_low: float
    price_high: float
    btc_amount: float
    utxo_count: int
    pct_of_supply: float

@dataclass
class URPDResult:
    buckets: list[URPDBucket]
    total_supply: float
    current_price: float
    supply_above_price: float
    supply_below_price: float
    supply_at_price: float  # Within ±5% of current
    dominant_bucket: URPDBucket
    timestamp: datetime
```

### Step 1.3: Core Calculation [E] (2-3 hours)
```python
def calculate_urpd(
    conn: duckdb.DuckDBPyConnection,
    current_price: float,
    bucket_size: float = 5000.0,
    min_price: float = 0.0,
    max_price: Optional[float] = None,
) -> URPDResult:
    """Calculate URPD distribution.

    Algorithm approaches:
    - A: Fixed bucket sizes (simpler, faster)
    - B: Logarithmic buckets (better for wide ranges)
    - C: Adaptive buckets (cluster detection)

    Winner: Approach A for simplicity, B for visualization.
    """
```

### Step 1.4: Support/Resistance Detection (1 hour)
```python
def detect_sr_zones(urpd: URPDResult, threshold_pct: float = 5.0) -> list[SRZone]:
    """Detect support/resistance zones from URPD clusters.

    A zone is significant if it holds > threshold_pct of supply.
    """
```

### Step 1.5: Signal Generation (30 min)
```python
def urpd_signal(urpd: URPDResult) -> tuple[float, float]:
    """Generate fusion signal from URPD.

    Returns (vote, confidence):
    - Near heavy support: positive vote
    - Near heavy resistance: negative vote
    """
```

---

## Phase 2: Supply in Profit/Loss (P1) - 2 hours

### Step 2.1: Create Module (30 min)
```python
# scripts/metrics/supply_profit_loss.py
"""
Supply in Profit/Loss (spec-021)

Breakdown of supply by profit/loss status vs current price.
"""

@dataclass
class SupplyProfitLoss:
    supply_in_profit: float
    supply_in_loss: float
    supply_breakeven: float
    total_supply: float
    pct_in_profit: float
    pct_in_loss: float
    current_price: float
    signal: str  # "EUPHORIA", "BULL", "TRANSITION", "CAPITULATION"
    timestamp: datetime
```

### Step 2.2: Core Calculation (45 min)
```python
def calculate_supply_profit_loss(
    conn: duckdb.DuckDBPyConnection,
    current_price: float,
) -> SupplyProfitLoss:
    """Calculate supply breakdown by profit/loss status."""

    result = conn.execute("""
        SELECT
            SUM(CASE WHEN ? > creation_price_usd THEN btc_value ELSE 0 END),
            SUM(CASE WHEN ? < creation_price_usd THEN btc_value ELSE 0 END),
            SUM(CASE WHEN ABS(? - creation_price_usd) < 100 THEN btc_value ELSE 0 END),
            SUM(btc_value)
        FROM utxo_lifecycle
        WHERE is_spent = FALSE
    """, [current_price, current_price, current_price]).fetchone()
```

### Step 2.3: STH/LTH Breakdown (30 min)
```python
def calculate_cohort_profit_loss(
    conn: duckdb.DuckDBPyConnection,
    current_price: float,
    current_block: int,
    cohort: str = "ALL",  # "STH", "LTH", "ALL"
) -> SupplyProfitLoss:
    """Calculate profit/loss for specific cohort."""
```

### Step 2.4: Signal Classification (15 min)
```python
def classify_profit_signal(pct_in_profit: float) -> str:
    if pct_in_profit > 95:
        return "EUPHORIA"
    elif pct_in_profit > 80:
        return "BULL"
    elif pct_in_profit > 50:
        return "TRANSITION"
    else:
        return "CAPITULATION"
```

---

## Phase 3: Reserve Risk (P1) - 2-3 hours

### Step 3.1: Create Module (30 min)
```python
# scripts/metrics/reserve_risk.py
"""
Reserve Risk (spec-021)

Measures long-term holder conviction relative to price.
Low = high conviction (buy zone), High = low conviction (sell zone).
"""

@dataclass
class ReserveRiskResult:
    reserve_risk: float
    hodl_bank: float  # Cumulative opportunity cost
    price: float
    circulating_supply: float
    signal: str  # "STRONG_BUY", "BUY", "FAIR", "SELL"
    confidence: float
    timestamp: datetime
```

### Step 3.2: HODL Bank Calculation (1 hour)
```python
def calculate_hodl_bank(
    conn: duckdb.DuckDBPyConnection,
    up_to_block: int,
) -> float:
    """Calculate cumulative HODL Bank (opportunity cost of holding).

    HODL Bank = Sum of all coindays NOT destroyed
              = Total potential CDD - Actual CDD spent
    """
```

### Step 3.3: Reserve Risk Formula (45 min)
```python
def calculate_reserve_risk(
    price: float,
    hodl_bank: float,
    circulating_supply: float,
) -> ReserveRiskResult:
    """
    Reserve Risk = Price / (HODL Bank × Circulating Supply)

    Alternative using liveliness:
    Reserve Risk = Price / ((1 - Liveliness) × Market Cap)
    """
```

### Step 3.4: Signal Zones (15 min)
```python
def classify_reserve_risk(rr: float) -> tuple[str, float]:
    if rr < 0.002:
        return ("STRONG_BUY", 0.95)
    elif rr < 0.008:
        return ("BUY", 0.75)
    elif rr < 0.02:
        return ("FAIR", 0.50)
    else:
        return ("SELL", 0.80)
```

---

## Phase 4: Sell-side Risk Ratio (P1) - 2-3 hours

### Step 4.1: Create Module (30 min)
```python
# scripts/metrics/sell_side_risk.py
"""
Sell-side Risk Ratio (spec-021)

Ratio of realized profit to market cap.
High = aggressive profit-taking (distribution phase).
"""

@dataclass
class SellSideRiskResult:
    sell_side_risk: float
    realized_profit_usd: float
    market_cap: float
    period_days: int
    signal: str
    confidence: float
    timestamp: datetime
```

### Step 4.2: Realized Profit Calculation (1 hour)
```python
def calculate_realized_profit(
    conn: duckdb.DuckDBPyConnection,
    days: int = 30,
) -> float:
    """Calculate total realized profit over period.

    Only counts profitable spends (sell > buy price).
    """
    cutoff = datetime.now() - timedelta(days=days)

    result = conn.execute("""
        SELECT COALESCE(SUM(
            (spend_price_usd - creation_price_usd) * btc_value
        ), 0)
        FROM utxo_lifecycle
        WHERE is_spent = TRUE
          AND spent_timestamp >= ?
          AND spend_price_usd > creation_price_usd
    """, [cutoff]).fetchone()
```

### Step 4.3: Ratio Calculation (30 min)
```python
def calculate_sell_side_risk(
    conn: duckdb.DuckDBPyConnection,
    current_price: float,
    circulating_supply: float,
    days: int = 30,
) -> SellSideRiskResult:
    """
    Sell-side Risk = Realized Profit / Market Cap
    """
```

### Step 4.4: Signal Classification (30 min)
```python
def classify_sell_side_risk(ssr: float) -> tuple[str, float]:
    if ssr < 0.001:  # < 0.1%
        return ("LOW_DISTRIBUTION", 0.70)
    elif ssr < 0.003:  # 0.1-0.3%
        return ("NORMAL", 0.50)
    elif ssr < 0.01:  # 0.3-1%
        return ("ELEVATED", 0.75)
    else:  # > 1%
        return ("AGGRESSIVE_DISTRIBUTION", 0.90)
```

---

## Phase 5: CDD/VDD (P2) - 3 hours

### Step 5.1: Create Module (30 min)
```python
# scripts/metrics/coindays.py
"""
Coindays Destroyed (CDD) and Value Days Destroyed (VDD)

Measures "old money" movement in the network.
Builds on cointime.py coinblocks infrastructure.
"""

@dataclass
class CoindaysResult:
    cdd: float  # Coindays destroyed
    vdd: float  # Value days destroyed (CDD × price)
    cdd_7d_avg: float
    cdd_30d_avg: float
    cdd_365d_avg: float
    vdd_multiple: float  # VDD / 365d_MA(VDD)
    signal: str
    timestamp: datetime
```

### Step 5.2: CDD Calculation (45 min)
```python
def calculate_cdd(
    conn: duckdb.DuckDBPyConnection,
    date: datetime.date,
) -> float:
    """Calculate Coindays Destroyed for a specific date.

    CDD = Σ(age_days × btc_value) for UTXOs spent on date
    """
    result = conn.execute("""
        SELECT COALESCE(SUM(
            (spent_block - creation_block) / 144.0 * btc_value
        ), 0)
        FROM utxo_lifecycle
        WHERE is_spent = TRUE
          AND DATE(spent_timestamp) = ?
    """, [date]).fetchone()
```

### Step 5.3: VDD Calculation (30 min)
```python
def calculate_vdd(
    conn: duckdb.DuckDBPyConnection,
    date: datetime.date,
) -> float:
    """Calculate Value Days Destroyed.

    VDD = Σ(age_days × btc_value × spend_price)
    """
```

### Step 5.4: Rolling Averages (45 min)
```python
def calculate_cdd_averages(
    conn: duckdb.DuckDBPyConnection,
    end_date: datetime.date,
) -> dict[str, float]:
    """Calculate 7d, 30d, 365d rolling averages."""
```

### Step 5.5: VDD Multiple (30 min)
```python
def calculate_vdd_multiple(
    vdd_current: float,
    vdd_365d_avg: float,
) -> float:
    """VDD Multiple = VDD / 365d_MA(VDD)

    > 2.0 indicates significant LTH distribution
    """
```

---

## Phase 6: Testing (2-3 hours)

### Test Files
- `tests/test_urpd.py`
- `tests/test_supply_profit_loss.py`
- `tests/test_reserve_risk.py`
- `tests/test_sell_side_risk.py`
- `tests/test_coindays.py`

### Test Strategy
1. Unit tests with mock data
2. Integration tests with test DuckDB
3. Validation against known Glassnode values (where available)

---

## Phase 7: Fusion Integration (1-2 hours)

### Step 7.1: Add to Monte Carlo Fusion
```python
# In monte_carlo_fusion.py

ENHANCED_WEIGHTS = {
    # ... existing ...
    "urpd": 0.02,
    "supply_profit": 0.02,
    "reserve_risk": 0.02,
    "sell_side": 0.02,
}
```

### Step 7.2: Signal Converters
```python
def urpd_to_vote(urpd: URPDResult) -> tuple[float, float]:
    """Convert URPD to fusion vote."""

def profit_loss_to_vote(spl: SupplyProfitLoss) -> tuple[float, float]:
    """Convert supply profit/loss to fusion vote."""

def reserve_risk_to_vote(rr: ReserveRiskResult) -> tuple[float, float]:
    """Convert reserve risk to fusion vote."""

def sell_side_to_vote(ssr: SellSideRiskResult) -> tuple[float, float]:
    """Convert sell-side risk to fusion vote."""
```

---

## Rollout Plan

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Phase 1 | Day 1 | URPD module + tests |
| Phase 2 | Day 1 | Supply Profit/Loss |
| Phase 3 | Day 2 | Reserve Risk |
| Phase 4 | Day 2 | Sell-side Risk |
| Phase 5 | Day 3 | CDD/VDD |
| Phase 6 | Day 3 | Testing |
| Phase 7 | Day 4 | Fusion integration |

**Total: 4 days**

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Test coverage | > 90% |
| Performance (URPD) | < 30s |
| Performance (others) | < 5s each |
| Glassnode parity | < 5% deviation |
