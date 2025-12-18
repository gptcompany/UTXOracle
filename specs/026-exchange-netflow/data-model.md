# Data Model: Exchange Netflow (spec-026)

**Date**: 2025-12-18
**Status**: Final

## Entities

### 1. NetflowZone (Enum)

**Purpose**: Classify exchange netflow into behavioral zones for market sentiment analysis.

| Value | Threshold (BTC/day) | Description |
|-------|---------------------|-------------|
| `strong_outflow` | < -1000 | Heavy accumulation, bullish |
| `weak_outflow` | -1000 to 0 | Mild accumulation, neutral-bullish |
| `weak_inflow` | 0 to 1000 | Mild selling, neutral-bearish |
| `strong_inflow` | > 1000 | Heavy selling pressure, bearish |

**Location**: `scripts/models/metrics_models.py`

```python
class NetflowZone(str, Enum):
    """Exchange netflow behavioral zone classification."""
    STRONG_OUTFLOW = "strong_outflow"   # Heavy accumulation
    WEAK_OUTFLOW = "weak_outflow"       # Mild accumulation
    WEAK_INFLOW = "weak_inflow"         # Mild selling
    STRONG_INFLOW = "strong_inflow"     # Heavy selling
```

---

### 2. ExchangeNetflowResult (Dataclass)

**Purpose**: Container for exchange netflow metrics and context.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `exchange_inflow` | `float` | BTC flowing into exchanges | >= 0 |
| `exchange_outflow` | `float` | BTC flowing out of exchanges | >= 0 |
| `netflow` | `float` | Inflow - Outflow (positive = selling) | Any |
| `netflow_7d_ma` | `float` | 7-day moving average of netflow | Any |
| `netflow_30d_ma` | `float` | 30-day moving average of netflow | Any |
| `zone` | `NetflowZone` | Behavioral zone classification | Enum value |
| `window_hours` | `int` | Lookback window in hours | > 0 |
| `exchange_count` | `int` | Number of exchanges in dataset | >= 0 |
| `address_count` | `int` | Number of addresses matched | >= 0 |
| `current_price_usd` | `float` | Price for USD calculation | > 0 |
| `inflow_usd` | `float` | USD value of inflow | >= 0 |
| `outflow_usd` | `float` | USD value of outflow | >= 0 |
| `block_height` | `int` | Current block height | > 0 |
| `timestamp` | `datetime` | Calculation timestamp | Required |
| `confidence` | `float` | Data quality indicator | 0.0-1.0, default 0.75 |

**Location**: `scripts/models/metrics_models.py`

```python
@dataclass
class ExchangeNetflowResult:
    """Exchange netflow metrics for capital flow tracking."""

    exchange_inflow: float
    exchange_outflow: float
    netflow: float
    netflow_7d_ma: float
    netflow_30d_ma: float

    zone: NetflowZone

    window_hours: int
    exchange_count: int
    address_count: int

    current_price_usd: float
    inflow_usd: float
    outflow_usd: float

    block_height: int
    timestamp: datetime
    confidence: float = 0.75  # B-C grade metric

    def __post_init__(self):
        """Validate field constraints."""
        if self.exchange_inflow < 0 or self.exchange_outflow < 0:
            raise ValueError("Inflow/outflow values cannot be negative")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0 and 1")

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        return {
            "exchange_inflow": self.exchange_inflow,
            "exchange_outflow": self.exchange_outflow,
            "netflow": self.netflow,
            "netflow_7d_ma": self.netflow_7d_ma,
            "netflow_30d_ma": self.netflow_30d_ma,
            "zone": self.zone.value,
            "window_hours": self.window_hours,
            "exchange_count": self.exchange_count,
            "address_count": self.address_count,
            "current_price_usd": self.current_price_usd,
            "inflow_usd": self.inflow_usd,
            "outflow_usd": self.outflow_usd,
            "block_height": self.block_height,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
        }
```

---

### 3. ExchangeAddress (Lookup Data)

**Purpose**: Curated list of known exchange addresses for netflow calculation.

| Field | Type | Description |
|-------|------|-------------|
| `exchange_name` | `VARCHAR` | Exchange identifier (Binance, Kraken, etc.) |
| `address` | `VARCHAR` | Bitcoin address (base58/bech32) |
| `type` | `VARCHAR` | Wallet type (hot_wallet, cold_wallet, segwit_hot) |

**Location**: `data/exchange_addresses.csv` (existing file)

**Schema** (DuckDB table):
```sql
CREATE TABLE exchange_addresses (
    exchange_name VARCHAR NOT NULL,
    address VARCHAR PRIMARY KEY,
    type VARCHAR NOT NULL
);
```

**Current Data**:
| Exchange | Address | Type |
|----------|---------|------|
| Binance | 1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX | hot_wallet |
| Binance | 3P14159f73E4gFrCh2HRze1k41v22b2p7g | cold_wallet |
| Binance | 1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s | hot_wallet |
| Binance | bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h | segwit_hot |
| Bitfinex | 1Kr6QSydW9bFQG1mXiPNNu6WpJGmUa9i1g | hot_wallet |
| Bitfinex | 3D2oetdNuZUqQHPJmcMDDHYoqkyNVsFk9r | cold_wallet |
| Kraken | 3FupZp77ySr7jwoLYEJ9mwzJpvoNBXsBnE | cold_wallet |
| Kraken | bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97 | segwit_hot |
| Coinbase | 3Cbq7aT1tY8kMxWLbitaG7yT6bPbKChq64 | cold_wallet |
| Coinbase | bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh | segwit_hot |

---

## Relationships

```
data/exchange_addresses.csv
         │
         │ LOAD CSV → DuckDB Table
         ▼
┌─────────────────────────┐
│   exchange_addresses    │
│  ─────────────────────  │
│  address (PK): VARCHAR  │
│  exchange_name: VARCHAR │
│  type: VARCHAR          │
└───────────┬─────────────┘
            │
            │ JOIN ON address
            ▼
┌─────────────────────────┐
│   utxo_lifecycle_full   │
│  (VIEW - existing)      │
│  ─────────────────────  │
│  address: VARCHAR       │
│  btc_value: DOUBLE      │
│  creation_timestamp     │
│  is_spent: BOOLEAN      │
│  spent_timestamp        │
└───────────┬─────────────┘
            │
            │ Aggregate (SUM, COUNT)
            ▼
┌─────────────────────────┐
│  ExchangeNetflowResult  │
│  ─────────────────────  │
│  exchange_inflow: float │
│  exchange_outflow: float│
│  netflow: float         │◄──── classify_netflow_zone()
│  zone: NetflowZone      │
│  ...                    │
└───────────┬─────────────┘
            │
            │ to_dict()
            ▼
┌─────────────────────────┐
│   API Response (JSON)   │
│  GET /api/metrics/      │
│      exchange-netflow   │
└─────────────────────────┘
```

---

## Data Source

### utxo_lifecycle_full VIEW (Existing)

The `utxo_lifecycle_full` VIEW provides all required columns:

| Column | Type | Purpose |
|--------|------|---------|
| `address` | VARCHAR | Destination address of UTXO |
| `btc_value` | DOUBLE | BTC amount of UTXO |
| `creation_timestamp` | BIGINT | Unix timestamp when created |
| `is_spent` | BOOLEAN | Whether UTXO has been spent |
| `spent_timestamp` | BIGINT | Unix timestamp when spent |

**Query Pattern**:
```sql
-- Calculate inflow and outflow in single query
WITH exchange_utxos AS (
    SELECT
        u.btc_value,
        u.creation_timestamp,
        u.is_spent,
        u.spent_timestamp
    FROM utxo_lifecycle_full u
    JOIN exchange_addresses e ON u.address = e.address
)
SELECT
    -- Inflow: UTXOs created at exchange addresses within window
    SUM(CASE
        WHEN creation_timestamp >= :window_start
        THEN btc_value
        ELSE 0
    END) AS inflow,

    -- Outflow: UTXOs spent from exchange addresses within window
    SUM(CASE
        WHEN is_spent AND spent_timestamp >= :window_start
        THEN btc_value
        ELSE 0
    END) AS outflow
FROM exchange_utxos
```

---

## Validation Rules

### Zone Classification

```python
def classify_netflow_zone(netflow_btc_per_day: float) -> NetflowZone:
    """Classify netflow into behavioral zone."""
    if netflow_btc_per_day < -1000:
        return NetflowZone.STRONG_OUTFLOW
    elif netflow_btc_per_day < 0:
        return NetflowZone.WEAK_OUTFLOW
    elif netflow_btc_per_day < 1000:
        return NetflowZone.WEAK_INFLOW
    else:
        return NetflowZone.STRONG_INFLOW
```

### Moving Average Calculation

```python
def calculate_moving_average(daily_values: list[float], window: int) -> float:
    """Calculate simple moving average."""
    if not daily_values:
        return 0.0
    if len(daily_values) < window:
        return sum(daily_values) / len(daily_values)
    return sum(daily_values[-window:]) / window
```

### Confidence Calculation

| Condition | Confidence |
|-----------|------------|
| Normal data, 10+ addresses | 0.75 (B-C grade) |
| Fewer than 5 addresses matched | 0.5 |
| No addresses matched | 0.0 |
| Exchange file not found | 0.0 (warning log) |

---

## State Transitions

Not applicable - this is a point-in-time calculation, not a stateful entity.

---

## API Contract Summary

| Endpoint | Method | Request | Response |
|----------|--------|---------|----------|
| `/api/metrics/exchange-netflow` | GET | `?window=24` (hours) | `ExchangeNetflowResult.to_dict()` |
| `/api/metrics/exchange-netflow/history` | GET | `?days=30` | `{"days": 30, "data": [...]}` |

See `contracts/api.yaml` for full OpenAPI specification.
