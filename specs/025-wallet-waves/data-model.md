# Data Model: Wallet Waves & Absorption Rates

**Spec**: spec-025
**Date**: 2025-12-17

## Enums

### WalletBand

```python
class WalletBand(str, Enum):
    """Wallet size classification bands."""
    SHRIMP = "shrimp"      # < 1 BTC
    CRAB = "crab"          # 1-10 BTC
    FISH = "fish"          # 10-100 BTC
    SHARK = "shark"        # 100-1,000 BTC
    WHALE = "whale"        # 1,000-10,000 BTC
    HUMPBACK = "humpback"  # > 10,000 BTC
```

**Threshold Constants**:
```python
BAND_THRESHOLDS = {
    WalletBand.SHRIMP: (0, 1),
    WalletBand.CRAB: (1, 10),
    WalletBand.FISH: (10, 100),
    WalletBand.SHARK: (100, 1000),
    WalletBand.WHALE: (1000, 10000),
    WalletBand.HUMPBACK: (10000, float('inf')),
}
```

## Dataclasses

### WalletBandMetrics

```python
@dataclass
class WalletBandMetrics:
    """Metrics for a single wallet band."""
    band: WalletBand
    supply_btc: float           # Total BTC held by band
    supply_pct: float           # Percentage of total supply
    address_count: int          # Number of addresses in band
    avg_balance: float          # Average balance per address

    def __post_init__(self):
        if self.supply_btc < 0:
            raise ValueError("supply_btc must be non-negative")
        if not 0 <= self.supply_pct <= 100:
            raise ValueError("supply_pct must be between 0 and 100")
        if self.address_count < 0:
            raise ValueError("address_count must be non-negative")
```

### WalletWavesResult

```python
@dataclass
class WalletWavesResult:
    """Complete wallet waves distribution snapshot."""
    timestamp: datetime
    block_height: int
    total_supply_btc: float
    bands: list[WalletBandMetrics]  # 6 bands

    # Aggregates
    retail_supply_pct: float        # Bands 1-3 (shrimp+crab+fish)
    institutional_supply_pct: float # Bands 4-6 (shark+whale+humpback)

    # Metadata
    address_count_total: int
    null_address_btc: float         # BTc in UTXOs without decoded address
    confidence: float               # Data quality score (0.0-1.0)

    def __post_init__(self):
        if len(self.bands) != 6:
            raise ValueError("Must have exactly 6 bands")
        if self.total_supply_btc <= 0:
            raise ValueError("total_supply_btc must be positive")

        # Validate percentages sum to ~100%
        band_sum = sum(b.supply_pct for b in self.bands)
        if not 99.0 <= band_sum <= 101.0:
            raise ValueError(f"Band percentages must sum to ~100%, got {band_sum:.2f}%")
```

### AbsorptionRateMetrics

```python
@dataclass
class AbsorptionRateMetrics:
    """Absorption rate for a single wallet band."""
    band: WalletBand
    absorption_rate: float | None    # Rate of new supply absorbed (0.0-1.0+)
    supply_delta_btc: float          # Change in BTC held
    supply_start_btc: float          # BTC at window start
    supply_end_btc: float            # BTC at window end

    def __post_init__(self):
        if self.absorption_rate is not None and self.absorption_rate < -10:
            raise ValueError("absorption_rate suspiciously negative")
```

### AbsorptionRatesResult

```python
@dataclass
class AbsorptionRatesResult:
    """Absorption rates across all wallet bands."""
    timestamp: datetime
    block_height: int
    window_days: int
    mined_supply_btc: float          # New BTC mined in window

    bands: list[AbsorptionRateMetrics]  # 6 bands

    # Aggregates
    dominant_absorber: WalletBand    # Band with highest absorption
    retail_absorption: float         # Combined bands 1-3
    institutional_absorption: float  # Combined bands 4-6

    # Metadata
    confidence: float
    has_historical_data: bool        # False if baseline unavailable

    def __post_init__(self):
        if len(self.bands) != 6:
            raise ValueError("Must have exactly 6 bands")
        if self.window_days <= 0:
            raise ValueError("window_days must be positive")
```

## Relationships

```
WalletWavesResult
├── bands: list[WalletBandMetrics] (1:6)
│   └── band: WalletBand (enum reference)
└── retail/institutional aggregates (computed from bands)

AbsorptionRatesResult
├── bands: list[AbsorptionRateMetrics] (1:6)
│   └── band: WalletBand (enum reference)
├── dominant_absorber: WalletBand (max absorption)
└── requires: WalletWavesResult (t) and WalletWavesResult (t-n)
```

## Database Queries

### Wallet Waves Query

```sql
WITH address_balances AS (
    SELECT
        address,
        SUM(btc_value) AS balance
    FROM utxo_lifecycle_full
    WHERE is_spent = FALSE
      AND address IS NOT NULL
    GROUP BY address
    HAVING balance > 0
)
SELECT
    CASE
        WHEN balance < 1 THEN 'shrimp'
        WHEN balance < 10 THEN 'crab'
        WHEN balance < 100 THEN 'fish'
        WHEN balance < 1000 THEN 'shark'
        WHEN balance < 10000 THEN 'whale'
        ELSE 'humpback'
    END AS band,
    COUNT(*) AS address_count,
    SUM(balance) AS supply_btc,
    AVG(balance) AS avg_balance
FROM address_balances
GROUP BY band
ORDER BY
    CASE band
        WHEN 'shrimp' THEN 1
        WHEN 'crab' THEN 2
        WHEN 'fish' THEN 3
        WHEN 'shark' THEN 4
        WHEN 'whale' THEN 5
        WHEN 'humpback' THEN 6
    END;
```

### Total Supply Query

```sql
SELECT SUM(btc_value) AS total_supply
FROM utxo_lifecycle_full
WHERE is_spent = FALSE;
```

### NULL Address BTC Query

```sql
SELECT COALESCE(SUM(btc_value), 0) AS null_address_btc
FROM utxo_lifecycle_full
WHERE is_spent = FALSE AND address IS NULL;
```

## Validation Rules

| Field | Rule | Error |
|-------|------|-------|
| `bands` | Exactly 6 elements | "Must have exactly 6 bands" |
| `supply_pct` | 0 ≤ x ≤ 100 | "supply_pct must be between 0 and 100" |
| `band percentages` | Sum ≈ 100% (±1%) | "Band percentages must sum to ~100%" |
| `total_supply_btc` | > 0 | "total_supply_btc must be positive" |
| `window_days` | > 0 | "window_days must be positive" |
| `confidence` | 0.0 ≤ x ≤ 1.0 | "confidence must be between 0 and 1" |

## State Transitions

N/A - Wallet Waves is a stateless snapshot metric. Each calculation is independent.

For Absorption Rates, the calculation requires:
1. Current snapshot (t)
2. Historical snapshot (t - window_days)
3. Mined supply in window = 6.25 BTC × 144 blocks × window_days
