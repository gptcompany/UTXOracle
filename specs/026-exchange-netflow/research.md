# Research: Exchange Netflow (spec-026)

**Date**: 2025-12-18
**Status**: Complete

## Research Summary

All technical unknowns resolved. Implementation approach validated against existing codebase patterns. This is a medium-complexity metric requiring address matching against a curated exchange address list, following patterns from NUPL (spec-022), Cost Basis (spec-023), and Revived Supply (spec-024).

**Key Finding**: The existing `data/exchange_addresses.csv` file contains 10 exchange addresses from major exchanges (Binance, Bitfinex, Kraken, Coinbase). This is sufficient for MVP, with the option to expand via community contributions.

---

## 1. Exchange Address Data Source

### Decision
Use the existing `data/exchange_addresses.csv` file, loaded into DuckDB as a lookup table:
```sql
CREATE TABLE exchange_addresses (
    exchange_name VARCHAR,
    address VARCHAR PRIMARY KEY,
    type VARCHAR  -- hot_wallet, cold_wallet, segwit_hot
);
```

### Rationale
- **KISS/YAGNI**: File already exists with 10 addresses from 4 major exchanges
- No external API dependencies (privacy-first per Constitution Principle V)
- CSV is human-readable and easily editable
- DuckDB can efficiently JOIN against VARCHAR address column

### Alternatives Considered
1. **spec-013 Address Clustering integration**: Use heuristic-detected exchange addresses - Rejected: spec-013 not yet implemented, adds dependency
2. **External API (Glassnode/CryptoQuant)**: Real-time exchange data - Rejected: violates privacy-first principle, adds cost
3. **JSON format**: Structured data file - Rejected: CSV is simpler, already exists

### Coverage Analysis
| Exchange | Addresses | Coverage |
|----------|-----------|----------|
| Binance | 4 | High-volume hot/cold wallets |
| Bitfinex | 2 | Hot/cold wallets |
| Kraken | 2 | Cold/segwit wallets |
| Coinbase | 2 | Cold/segwit wallets |
| **Total** | **10** | ~60-70% of exchange volume (top 4) |

**Future Enhancement**: Add more exchanges via community PRs to `data/exchange_addresses.csv`.

---

## 2. Inflow/Outflow Calculation Formula

### Decision
Calculate inflow and outflow from the `utxo_lifecycle_full` VIEW:

```sql
-- Exchange Inflow: BTC sent TO exchange addresses
SELECT SUM(btc_value) AS inflow
FROM utxo_lifecycle_full u
JOIN exchange_addresses e ON u.address = e.address  -- dest address is exchange
WHERE u.is_spent = TRUE
  AND u.spent_timestamp >= :window_start

-- Exchange Outflow: BTC sent FROM exchange addresses
SELECT SUM(btc_value) AS outflow
FROM utxo_lifecycle_full u
JOIN exchange_addresses e ON u.address = e.address  -- source address is exchange
WHERE u.is_spent = TRUE
  AND u.spent_timestamp >= :window_start
```

**Key Insight**: The `utxo_lifecycle_full` VIEW has an `address` column that represents the UTXO destination address. When `is_spent = TRUE`, this UTXO was spent FROM that address.

### Rationale
- **Inflow Detection**: When an exchange address receives BTC, a UTXO is created at that address
- **Outflow Detection**: When an exchange spends BTC, a UTXO at that address is marked spent
- Single VIEW query with JOIN against lookup table

### Alternatives Considered
1. **Track individual transaction inputs/outputs**: Parse full tx structure - Rejected: over-engineering, VIEW already has what we need
2. **Separate inflow/outflow tables**: Pre-aggregate - Rejected: YAGNI, on-demand calculation is fast enough

### Query Clarification

The `utxo_lifecycle_full` VIEW schema shows:
- `address`: The destination address of the UTXO output
- `is_spent`: Whether this UTXO has been spent

**Inflow Logic**:
- When BTC flows INTO an exchange, someone creates a UTXO at an exchange address
- Query: Find UTXOs WHERE destination address is an exchange AND created within window

**Outflow Logic**:
- When BTC flows OUT of an exchange, the exchange spends a UTXO
- Query: Find UTXOs WHERE destination address is an exchange AND spent within window

```sql
-- Combined query for efficiency
SELECT
    -- Inflow: UTXOs created at exchange addresses (BTC received)
    SUM(CASE WHEN u.creation_timestamp >= :window_start
        THEN btc_value ELSE 0 END) AS inflow,

    -- Outflow: UTXOs spent from exchange addresses (BTC sent)
    SUM(CASE WHEN u.is_spent AND u.spent_timestamp >= :window_start
        THEN btc_value ELSE 0 END) AS outflow
FROM utxo_lifecycle_full u
JOIN exchange_addresses e ON u.address = e.address
```

---

## 3. Moving Average Implementation

### Decision
Calculate 7-day and 30-day moving averages in Python after retrieving daily netflow:

```python
def calculate_moving_averages(daily_netflows: list[float], window: int) -> float:
    """Calculate simple moving average of netflow."""
    if len(daily_netflows) < window:
        return sum(daily_netflows) / len(daily_netflows) if daily_netflows else 0.0
    return sum(daily_netflows[-window:]) / window
```

### Rationale
- Simple Moving Average (SMA) is industry standard for netflow visualization
- Python calculation avoids complex SQL window functions
- Historical daily data can be cached for efficiency

### Alternatives Considered
1. **SQL window functions**: `AVG() OVER (ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)` - Rejected: requires historical aggregation table
2. **Exponential Moving Average (EMA)**: More responsive to recent data - Rejected: YAGNI, SMA is sufficient for MVP
3. **Pre-computed daily snapshots**: Store daily netflow - Consider for Phase 2 if performance requires

### Data Source for MA
For MVP, calculate daily netflow on-demand using date-based windows:
```sql
-- Daily netflow for last 30 days
SELECT
    DATE(spent_timestamp) AS day,
    SUM(CASE WHEN created_at_exchange THEN btc_value ELSE 0 END) AS daily_inflow,
    SUM(CASE WHEN spent_from_exchange THEN btc_value ELSE 0 END) AS daily_outflow
FROM ...
GROUP BY DATE(spent_timestamp)
ORDER BY day DESC
LIMIT 30
```

---

## 4. Signal Zone Classification

### Decision
Classify netflow into behavioral zones based on industry research:

| Zone | Netflow (BTC/day) | Interpretation |
|------|-------------------|----------------|
| STRONG_OUTFLOW | < -1000 | Heavy accumulation, bullish |
| WEAK_OUTFLOW | -1000 to 0 | Mild accumulation, neutral-bullish |
| WEAK_INFLOW | 0 to 1000 | Mild selling, neutral-bearish |
| STRONG_INFLOW | > 1000 | Heavy selling pressure, bearish |

### Rationale
- Zone boundaries from spec-026 spec.md
- Aligns with Glassnode/CryptoQuant reporting conventions
- Provides actionable signal without complex statistical modeling

### Alternatives Considered
1. **Percentile-based zones**: Calculate from historical distribution - Rejected: requires historical baseline, adds complexity
2. **Standard deviation bands**: Statistical significance - Rejected: YAGNI for MVP
3. **No zones**: Raw numbers only - Rejected: zones add immediate analytical value

---

## 5. Dataclass Design

### Decision
Create `NetflowZone` enum and `ExchangeNetflowResult` dataclass:

```python
class NetflowZone(str, Enum):
    """Exchange netflow behavioral zone classification."""
    STRONG_OUTFLOW = "strong_outflow"   # Heavy accumulation (< -1000 BTC/day)
    WEAK_OUTFLOW = "weak_outflow"       # Mild accumulation (-1000 to 0)
    WEAK_INFLOW = "weak_inflow"         # Mild selling (0 to 1000)
    STRONG_INFLOW = "strong_inflow"     # Heavy selling (> 1000)

@dataclass
class ExchangeNetflowResult:
    """Exchange netflow metrics for capital flow tracking."""

    exchange_inflow: float       # BTC flowing into exchanges
    exchange_outflow: float      # BTC flowing out of exchanges
    netflow: float               # Inflow - Outflow (positive = selling)
    netflow_7d_ma: float         # 7-day moving average
    netflow_30d_ma: float        # 30-day moving average

    zone: NetflowZone            # Behavioral zone classification

    window_hours: int            # Lookback window (default 24h)
    exchange_count: int          # Number of exchanges in dataset
    address_count: int           # Number of addresses matched

    current_price_usd: float     # For USD value calculation
    inflow_usd: float            # USD value of inflow
    outflow_usd: float           # USD value of outflow

    block_height: int
    timestamp: datetime
    confidence: float = 0.75    # B-C grade metric (lower than Tier A)
```

### Rationale
- Follows `RevivedSupplyResult`, `NUPLResult` patterns
- Includes `to_dict()` for JSON serialization
- Zone enum provides type-safe classification
- Confidence 0.75 (B-C grade) reflects exchange address coverage limitations

### Alternatives Considered
1. **Return dict**: No type safety - Rejected: inconsistent with codebase
2. **Separate inflow/outflow results**: Two classes - Rejected: netflow is primary signal, single class is cleaner

---

## 6. API Endpoint Design

### Decision
Add two REST endpoints:

```
GET /api/metrics/exchange-netflow?window=24h
GET /api/metrics/exchange-netflow/history?days=30
```

**Primary Response** (`/exchange-netflow`):
```json
{
    "exchange_inflow": 5432.50,
    "exchange_outflow": 4234.75,
    "netflow": 1197.75,
    "netflow_7d_ma": 856.25,
    "netflow_30d_ma": 523.10,
    "zone": "weak_inflow",
    "window_hours": 24,
    "exchange_count": 4,
    "address_count": 10,
    "current_price_usd": 105000.0,
    "inflow_usd": 570412500.00,
    "outflow_usd": 444648750.00,
    "block_height": 875000,
    "timestamp": "2025-12-18T10:00:00Z",
    "confidence": 0.75
}
```

**History Response** (`/exchange-netflow/history`):
```json
{
    "days": 30,
    "data": [
        {"date": "2025-12-18", "netflow": 1197.75},
        {"date": "2025-12-17", "netflow": -523.40},
        ...
    ]
}
```

### Rationale
- Consistent with existing `/api/metrics/*` endpoints
- Primary endpoint for current snapshot
- History endpoint for charting (30-day trend)
- Optional `window` parameter for flexibility (24h default)

### Alternatives Considered
1. **WebSocket streaming**: Real-time updates - Rejected: YAGNI, netflow changes slowly
2. **Per-exchange breakdown**: Separate inflow/outflow per exchange - Rejected: adds complexity, can add later

---

## 7. Error Handling

### Decision
Handle edge cases gracefully:

| Scenario | Handling |
|----------|----------|
| Zero matched UTXOs | Return `netflow = 0.0`, `zone = WEAK_INFLOW` |
| No exchange addresses loaded | Return `confidence = 0.0`, warning log |
| Missing price data | Return `*_usd = 0.0` |
| Database connection error | Raise HTTPException(503) |

### Rationale
- Follows existing patterns in `calculate_revived_supply_signal()`
- Never raise exceptions for edge cases in metrics calculations
- Use confidence field to indicate data quality

---

## 8. Test Strategy

### Decision
TDD approach with fixture-based testing:

1. **Unit tests** (`tests/test_exchange_netflow.py`):
   - `test_load_exchange_addresses` - CSV loading
   - `test_calculate_exchange_inflow` - Inflow calculation
   - `test_calculate_exchange_outflow` - Outflow calculation
   - `test_calculate_netflow` - Combined netflow
   - `test_classify_netflow_zone_strong_outflow`
   - `test_classify_netflow_zone_weak_outflow`
   - `test_classify_netflow_zone_weak_inflow`
   - `test_classify_netflow_zone_strong_inflow`
   - `test_moving_average_calculation`
   - `test_empty_window_handling`
   - `test_exchange_netflow_api_endpoint`

2. **Integration test**: API endpoint response validation

### Rationale
- Follow existing test patterns in `tests/test_revived_supply.py`
- Use DuckDB in-memory for fast tests
- Mock exchange address CSV for deterministic testing

---

## 9. Performance Considerations

### Decision
Optimize for <200ms latency:

1. **Index on address column**: DuckDB will use hash join
2. **Limit window size**: Default 24h, max 7 days for real-time endpoint
3. **Cache exchange addresses**: Load once at startup, refresh on file change
4. **TTL cache for results**: 5-minute cache like other metrics

### Rationale
- Exchange address list is small (10-100 addresses)
- JOIN performance dominated by UTXO table scan
- Caching reduces repeated calculations

### Benchmarks (Expected)
| Query | Estimated Time |
|-------|----------------|
| 24h window, 10 addresses | <100ms |
| 7d window, 10 addresses | <200ms |
| 30d window, 10 addresses | <500ms |

---

## Dependencies Summary

| Dependency | Version | Purpose |
|------------|---------|---------|
| DuckDB | existing | SQL query engine |
| FastAPI | existing | REST API framework |
| Pydantic | existing | Response validation |
| pytest | existing | Test framework |

**No new dependencies required.**

---

## Implementation Order

1. Add `NetflowZone` enum and `ExchangeNetflowResult` dataclass to `metrics_models.py`
2. Write TDD tests (`tests/test_exchange_netflow.py`) - RED phase
3. Create `scripts/metrics/exchange_netflow.py` with calculation functions - GREEN phase
4. Add API endpoints to `api/main.py`
5. Run full test suite

**Estimated Effort**: 3-5 days (as specified in spec, medium complexity)
