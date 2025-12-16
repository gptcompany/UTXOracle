# Data Model: NUPL Oscillator (spec-022)

**Date**: 2025-12-16

## Entities

### NUPLZone (Enum)

Market cycle zone classification based on NUPL value.

```python
class NUPLZone(str, Enum):
    """NUPL market cycle zones."""
    CAPITULATION = "CAPITULATION"    # < 0: Network underwater
    HOPE_FEAR = "HOPE_FEAR"          # 0 - 0.25: Recovery phase
    OPTIMISM = "OPTIMISM"            # 0.25 - 0.5: Bull building
    BELIEF = "BELIEF"                # 0.5 - 0.75: Strong conviction
    EUPHORIA = "EUPHORIA"            # > 0.75: Extreme greed
```

### NUPLResult (Dataclass)

Complete NUPL oscillator result.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `nupl` | float | -1.0 to 1.0 (typical) | Net Unrealized Profit/Loss |
| `zone` | NUPLZone | enum member | Market cycle zone |
| `market_cap_usd` | float | >= 0 | Market Cap in USD |
| `realized_cap_usd` | float | >= 0 | Realized Cap in USD |
| `unrealized_profit_usd` | float | any | market_cap - realized_cap |
| `pct_supply_in_profit` | float | 0-100 | % of supply with cost basis < price |
| `block_height` | int | > 0 | Block height at calculation |
| `timestamp` | datetime | required | Calculation timestamp |
| `confidence` | float | 0.0 to 1.0 | Signal confidence |

#### Validation Rules

1. `market_cap_usd >= 0`
2. `realized_cap_usd >= 0`
3. `0.0 <= confidence <= 1.0`
4. `zone` must be valid enum member

#### State Transitions

NUPL zones follow market cycle progression (though reversals are common):

```
CAPITULATION → HOPE_FEAR → OPTIMISM → BELIEF → EUPHORIA
     ↑                                              ↓
     └──────────────── (cycle reset) ───────────────┘
```

## Relationships

```
NUPLResult
    ├── uses → realized_metrics.calculate_realized_cap()
    ├── uses → realized_metrics.calculate_market_cap()
    ├── uses → realized_metrics.get_total_unspent_supply()
    └── stored_in → utxo_snapshots.nupl (already exists)
```

## Data Flow

```
1. DuckDB (utxo_lifecycle_full VIEW)
   ↓
2. calculate_realized_cap() → realized_cap_usd
   ↓
3. get_total_unspent_supply() × current_price → market_cap_usd
   ↓
4. calculate_nupl_signal() → NUPLResult
   ↓
5. API Response (JSON)
```

## Database Schema

**No new tables required.** NUPL is already stored in `utxo_snapshots.nupl` column.

Existing schema:
```sql
CREATE TABLE utxo_snapshots (
    block_height INTEGER PRIMARY KEY,
    timestamp TIMESTAMP,
    total_supply_btc DOUBLE,
    sth_supply_btc DOUBLE,
    lth_supply_btc DOUBLE,
    realized_cap_usd DOUBLE,
    market_cap_usd DOUBLE,
    mvrv DOUBLE,
    nupl DOUBLE,           -- Already exists
    hodl_waves_json TEXT
);
```

## Python Dataclass Definition

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal


class NUPLZone(str, Enum):
    """NUPL market cycle zones based on Glassnode thresholds."""
    CAPITULATION = "CAPITULATION"
    HOPE_FEAR = "HOPE_FEAR"
    OPTIMISM = "OPTIMISM"
    BELIEF = "BELIEF"
    EUPHORIA = "EUPHORIA"


@dataclass
class NUPLResult:
    """NUPL Oscillator result with zone classification.

    Net Unrealized Profit/Loss = (Market Cap - Realized Cap) / Market Cap

    Interpretation:
    - NUPL > 0.75: Euphoria (historically cycle tops)
    - NUPL 0.5-0.75: Belief
    - NUPL 0.25-0.5: Optimism
    - NUPL 0-0.25: Hope/Fear
    - NUPL < 0: Capitulation (historically cycle bottoms)

    Spec: spec-022
    """

    nupl: float
    zone: NUPLZone
    market_cap_usd: float
    realized_cap_usd: float
    unrealized_profit_usd: float
    pct_supply_in_profit: float  # Optional: from supply_profit_loss metric
    block_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    confidence: float = 0.8  # Default high confidence for Tier A metric

    def __post_init__(self):
        """Validate NUPL result fields."""
        if self.market_cap_usd < 0:
            raise ValueError(f"market_cap_usd must be >= 0: {self.market_cap_usd}")
        if self.realized_cap_usd < 0:
            raise ValueError(f"realized_cap_usd must be >= 0: {self.realized_cap_usd}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")
        if not isinstance(self.zone, NUPLZone):
            raise ValueError(f"zone must be NUPLZone enum: {self.zone}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "nupl": self.nupl,
            "zone": self.zone.value,
            "market_cap_usd": self.market_cap_usd,
            "realized_cap_usd": self.realized_cap_usd,
            "unrealized_profit_usd": self.unrealized_profit_usd,
            "pct_supply_in_profit": self.pct_supply_in_profit,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat()
                if hasattr(self.timestamp, "isoformat")
                else str(self.timestamp),
            "confidence": self.confidence,
        }
```
