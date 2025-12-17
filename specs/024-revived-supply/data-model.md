# Data Model: Revived Supply (spec-024)

**Date**: 2025-12-17
**Status**: Final

## Entities

### 1. RevivedZone (Enum)

**Purpose**: Classify revived supply activity into behavioral zones.

| Value | Threshold (BTC/day) | Description |
|-------|---------------------|-------------|
| `dormant` | < 1000 | Low LTH activity |
| `normal` | 1000-5000 | Baseline movement |
| `elevated` | 5000-10000 | Increased LTH selling |
| `spike` | > 10000 | Major distribution event |

**Location**: `scripts/models/metrics_models.py`

```python
class RevivedZone(str, Enum):
    """Behavioral zone classification for revived supply activity."""
    DORMANT = "dormant"
    NORMAL = "normal"
    ELEVATED = "elevated"
    SPIKE = "spike"
```

---

### 2. RevivedSupplyResult (Dataclass)

**Purpose**: Container for revived supply metrics and context.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `revived_1y` | `float` | BTC revived after 1+ year dormancy | >= 0 |
| `revived_2y` | `float` | BTC revived after 2+ year dormancy | >= 0 |
| `revived_5y` | `float` | BTC revived after 5+ year dormancy | >= 0 |
| `revived_total_usd` | `float` | USD value of revived supply (1y) | >= 0 |
| `revived_avg_age` | `float` | Average age of revived UTXOs (days) | >= 0 |
| `zone` | `RevivedZone` | Behavioral zone classification | Enum value |
| `utxo_count` | `int` | Number of revived UTXOs | >= 0 |
| `window_days` | `int` | Lookback window used | > 0 |
| `current_price_usd` | `float` | Price for USD calculation | > 0 |
| `block_height` | `int` | Current block height | > 0 |
| `timestamp` | `datetime` | Calculation timestamp | Required |
| `confidence` | `float` | Data quality indicator | 0.0-1.0, default 0.85 |

**Location**: `scripts/models/metrics_models.py`

```python
@dataclass
class RevivedSupplyResult:
    """Revived supply metrics for dormant coin movement tracking."""

    revived_1y: float
    revived_2y: float
    revived_5y: float
    revived_total_usd: float
    revived_avg_age: float

    zone: RevivedZone
    utxo_count: int

    window_days: int
    current_price_usd: float
    block_height: int
    timestamp: datetime
    confidence: float = 0.85

    def __post_init__(self):
        """Validate field constraints."""
        if self.revived_1y < 0 or self.revived_2y < 0 or self.revived_5y < 0:
            raise ValueError("Revived values cannot be negative")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0 and 1")

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        return {
            "revived_1y": self.revived_1y,
            "revived_2y": self.revived_2y,
            "revived_5y": self.revived_5y,
            "revived_total_usd": self.revived_total_usd,
            "revived_avg_age": self.revived_avg_age,
            "zone": self.zone.value,
            "utxo_count": self.utxo_count,
            "window_days": self.window_days,
            "current_price_usd": self.current_price_usd,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
        }
```

---

## Relationships

```
utxo_lifecycle_full (VIEW)
         │
         │ SELECT SUM(btc_value), AVG(age_days), COUNT(*)
         │ WHERE is_spent = TRUE AND age_days >= threshold
         │       AND spent_timestamp >= NOW() - window
         │
         ▼
┌─────────────────────────┐
│   RevivedSupplyResult   │
│  ─────────────────────  │
│  revived_1y: float      │
│  revived_2y: float      │
│  revived_5y: float      │◄──── classify_revived_zone()
│  zone: RevivedZone      │
│  utxo_count: int        │
│  ...                    │
└─────────────────────────┘
         │
         │ to_dict()
         ▼
┌─────────────────────────┐
│   API Response (JSON)   │
│  GET /api/metrics/      │
│      revived-supply     │
└─────────────────────────┘
```

---

## Data Source

### utxo_lifecycle_full VIEW (Existing)

The `utxo_lifecycle_full` VIEW provides all required columns:

| Column | Type | Purpose |
|--------|------|---------|
| `btc_value` | DECIMAL | BTC amount of UTXO |
| `age_days` | INTEGER | Days since UTXO creation |
| `is_spent` | BOOLEAN | Whether UTXO has been spent |
| `spent_timestamp` | TIMESTAMP | When UTXO was spent |
| `creation_price_usd` | DECIMAL | USD price at UTXO creation |

**Query Pattern**:
```sql
SELECT
    SUM(btc_value) AS revived_btc,
    AVG(age_days) AS avg_age,
    COUNT(*) AS utxo_count
FROM utxo_lifecycle_full
WHERE is_spent = TRUE
  AND age_days >= :threshold
  AND spent_timestamp >= :window_start
```

---

## Validation Rules

### Zone Classification

```python
def classify_revived_zone(revived_btc_per_day: float) -> RevivedZone:
    """Classify revived supply into behavioral zone."""
    if revived_btc_per_day < 1000:
        return RevivedZone.DORMANT
    elif revived_btc_per_day < 5000:
        return RevivedZone.NORMAL
    elif revived_btc_per_day < 10000:
        return RevivedZone.ELEVATED
    else:
        return RevivedZone.SPIKE
```

### Confidence Calculation

| Condition | Confidence |
|-----------|------------|
| Normal data | 0.85 (Tier A metric) |
| No spent UTXOs in window | 0.0 |
| Low sample size (< 100 UTXOs) | 0.5 |

---

## State Transitions

Not applicable - this is a point-in-time calculation, not a stateful entity.

---

## API Contract Summary

| Endpoint | Method | Request | Response |
|----------|--------|---------|----------|
| `/api/metrics/revived-supply` | GET | `?threshold=365&window=30` | `RevivedSupplyResult.to_dict()` |

See `contracts/api.yaml` for full OpenAPI specification.
