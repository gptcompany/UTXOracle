# Data Model: MVRV-Z Score + STH/LTH Variants

**Spec**: spec-020
**Date**: 2025-12-10

---

## Entity Definitions

### MVRVExtendedSignal (NEW)

```python
@dataclass
class MVRVExtendedSignal:
    """Extended MVRV metrics with Z-score and cohort variants.

    Combines base MVRV with Z-score normalization and STH/LTH breakdown.
    Used for signal classification and fusion integration.
    """

    # Base metrics (from existing calculate_mvrv)
    mvrv: float              # Market Cap / Realized Cap
    market_cap_usd: float
    realized_cap_usd: float

    # Z-Score (NEW)
    mvrv_z: float            # (Market Cap - Realized Cap) / StdDev(Market Cap)
    z_history_days: int      # Number of days used for std calculation

    # Cohort variants (NEW)
    sth_mvrv: float          # Market Cap / STH Realized Cap
    sth_realized_cap_usd: float
    lth_mvrv: float          # Market Cap / LTH Realized Cap
    lth_realized_cap_usd: float

    # Signal classification
    zone: str                # "EXTREME_SELL", "CAUTION", "NORMAL", "ACCUMULATION"
    confidence: float        # 0.0 to 1.0

    # Metadata
    timestamp: datetime
    block_height: int
    threshold_days: int = 155  # STH/LTH boundary
```

### Prerequisite Models (from spec-017, NOT YET IMPLEMENTED)

The following models must be added to `scripts/models/metrics_models.py`:

#### UTXOLifecycle

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

#### UTXOSetSnapshot

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

#### AgeCohortsConfig

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

#### SyncState

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

## Database Schema Extensions

### No Schema Changes Required

The existing `utxo_lifecycle` and `utxo_snapshots` tables support all required queries:

```sql
-- STH Realized Cap (age < 155 days)
SELECT COALESCE(SUM(btc_value * creation_price_usd), 0)
FROM utxo_lifecycle
WHERE is_spent = FALSE
  AND creation_block > :current_block - 22320;  -- 155 * 144

-- LTH Realized Cap (age >= 155 days)
SELECT COALESCE(SUM(btc_value * creation_price_usd), 0)
FROM utxo_lifecycle
WHERE is_spent = FALSE
  AND creation_block <= :current_block - 22320;

-- Market Cap History (365 days)
SELECT market_cap_usd
FROM utxo_snapshots
WHERE timestamp >= :start_timestamp
ORDER BY block_height DESC;
```

---

## Relationships

```
MVRVExtendedSignal (computed)
    │
    ├── mvrv ← calculate_mvrv(market_cap, realized_cap)
    │
    ├── mvrv_z ← calculate_mvrv_z(market_cap, realized_cap, history)
    │     └── history ← utxo_snapshots.market_cap_usd (365 days)
    │
    ├── sth_mvrv ← calculate_cohort_mvrv(market_cap, sth_realized_cap)
    │     └── sth_realized_cap ← utxo_lifecycle (creation_block > cutoff)
    │
    └── lth_mvrv ← calculate_cohort_mvrv(market_cap, lth_realized_cap)
          └── lth_realized_cap ← utxo_lifecycle (creation_block <= cutoff)
```

---

## Validation Rules

### MVRVExtendedSignal

| Field | Rule |
|-------|------|
| `mvrv` | >= 0.0 (market cap can't be negative) |
| `mvrv_z` | Typically -2 to +10, no hard bounds |
| `sth_mvrv` | >= 0.0 |
| `lth_mvrv` | >= 0.0 |
| `zone` | One of: "EXTREME_SELL", "CAUTION", "NORMAL", "ACCUMULATION" |
| `confidence` | 0.0 to 1.0 |
| `z_history_days` | >= 30 for valid Z-score, 0 if insufficient |

### Invariant Validation

```python
# STH + LTH realized cap should equal total realized cap
assert abs(sth_realized_cap + lth_realized_cap - total_realized_cap) < 0.01
```

---

## State Transitions

MVRV-Z Signal Zones (state machine):

```
                  +7.0
    EXTREME_SELL ─────┐
         │            │
    +3.0 ▼            │
    CAUTION ──────────┤
         │            │
    -0.5 ▼            │
    NORMAL ───────────┤
         │            │
    -∞   ▼            │
    ACCUMULATION ─────┘
         │
         ▼ (any zone can transition to any other)
```

Zone transitions based on MVRV-Z thresholds:
- `> 7.0`: EXTREME_SELL
- `3.0 to 7.0`: CAUTION
- `-0.5 to 3.0`: NORMAL
- `< -0.5`: ACCUMULATION
