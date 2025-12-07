# Data Model: UTXO Lifecycle Engine

**Spec**: spec-017
**Date**: 2025-12-06

---

## Entity Definitions

### UTXOLifecycle

```python
@dataclass
class UTXOLifecycle:
    """Complete lifecycle record for a single UTXO."""

    # Identity
    outpoint: str                       # f"{txid}:{vout_index}"
    txid: str
    vout_index: int

    # Creation
    creation_block: int
    creation_timestamp: datetime
    creation_price_usd: float
    btc_value: float
    realized_value_usd: float           # btc_value × creation_price

    # Spending (None if unspent)
    spent_block: int | None = None
    spent_timestamp: datetime | None = None
    spent_price_usd: float | None = None
    spending_txid: str | None = None

    # Derived
    age_blocks: int | None = None
    age_days: int | None = None
    cohort: str = ""                    # "STH" | "LTH"
    sub_cohort: str = ""                # "<1d", "1d-1w", etc.
    sopr: float | None = None

    # Metadata
    is_coinbase: bool = False
    is_spent: bool = False
    price_source: str = "utxoracle"
```

### UTXOSetSnapshot

```python
@dataclass
class UTXOSetSnapshot:
    """Point-in-time snapshot of UTXO set metrics."""

    block_height: int
    timestamp: datetime

    # Supply Distribution
    total_supply_btc: float
    sth_supply_btc: float               # age < 155 days
    lth_supply_btc: float               # age >= 155 days
    supply_by_cohort: dict[str, float]  # cohort -> BTC

    # Realized Metrics
    realized_cap_usd: float
    market_cap_usd: float
    mvrv: float
    nupl: float

    # HODL Waves
    hodl_waves: dict[str, float]        # cohort -> % of supply
```

### AgeCohortsConfig

```python
@dataclass
class AgeCohortsConfig:
    """Configuration for age cohort classification."""

    sth_threshold_days: int = 155

    cohorts: list[tuple[str, int, int]] = field(default_factory=lambda: [
        ("<1d", 0, 1),
        ("1d-1w", 1, 7),
        ("1w-1m", 7, 30),
        ("1m-3m", 30, 90),
        ("3m-6m", 90, 180),
        ("6m-1y", 180, 365),
        ("1y-2y", 365, 730),
        ("2y-3y", 730, 1095),
        ("3y-5y", 1095, 1825),
        (">5y", 1825, float("inf")),
    ])

    def classify(self, age_days: int) -> tuple[str, str]:
        """Return (cohort, sub_cohort) for given age."""
        cohort = "STH" if age_days < self.sth_threshold_days else "LTH"
        for name, min_days, max_days in self.cohorts:
            if min_days <= age_days < max_days:
                return cohort, name
        return cohort, ">5y"
```

### SyncState

```python
@dataclass
class SyncState:
    """Tracks sync progress for incremental updates."""

    last_processed_block: int
    last_processed_timestamp: datetime
    total_utxos_created: int
    total_utxos_spent: int
    sync_started: datetime
    sync_duration_seconds: float
```

---

## Database Schema

```sql
-- Main UTXO lifecycle table
CREATE TABLE IF NOT EXISTS utxo_lifecycle (
    outpoint TEXT PRIMARY KEY,
    txid TEXT NOT NULL,
    vout_index INTEGER NOT NULL,

    -- Creation
    creation_block INTEGER NOT NULL,
    creation_timestamp TIMESTAMP NOT NULL,
    creation_price_usd REAL NOT NULL,
    btc_value REAL NOT NULL,
    realized_value_usd REAL NOT NULL,

    -- Spending
    spent_block INTEGER,
    spent_timestamp TIMESTAMP,
    spent_price_usd REAL,
    spending_txid TEXT,

    -- Classification
    cohort TEXT,
    sub_cohort TEXT,

    -- Metadata
    is_coinbase BOOLEAN DEFAULT FALSE,
    is_spent BOOLEAN DEFAULT FALSE,
    price_source TEXT DEFAULT 'utxoracle',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Snapshots for historical queries
CREATE TABLE IF NOT EXISTS utxo_snapshots (
    block_height INTEGER PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    total_supply_btc REAL NOT NULL,
    sth_supply_btc REAL NOT NULL,
    lth_supply_btc REAL NOT NULL,
    realized_cap_usd REAL NOT NULL,
    market_cap_usd REAL NOT NULL,
    mvrv REAL NOT NULL,
    nupl REAL NOT NULL,
    hodl_waves_json TEXT
);

-- Sync state
CREATE TABLE IF NOT EXISTS utxo_sync_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    last_processed_block INTEGER NOT NULL,
    last_processed_timestamp TIMESTAMP NOT NULL,
    total_utxos_created INTEGER DEFAULT 0,
    total_utxos_spent INTEGER DEFAULT 0
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_utxo_creation_block ON utxo_lifecycle(creation_block);
CREATE INDEX IF NOT EXISTS idx_utxo_spent_block ON utxo_lifecycle(spent_block);
CREATE INDEX IF NOT EXISTS idx_utxo_is_spent ON utxo_lifecycle(is_spent);
CREATE INDEX IF NOT EXISTS idx_utxo_cohort ON utxo_lifecycle(cohort);
```

---

## Relationships

```
UTXOLifecycle (many) ──► UTXOSetSnapshot (aggregated daily)
                              │
UTXOSetSnapshot ──► hodl_waves (HODL Waves distribution)
                              │
UTXOSetSnapshot ──► realized_cap, mvrv, nupl (Realized metrics)
                              │
SyncState ──► tracks last_processed_block for incremental sync
```
