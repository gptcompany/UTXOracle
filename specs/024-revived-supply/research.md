# Research: Revived Supply (spec-024)

**Date**: 2025-12-17
**Status**: Complete

## Research Summary

All technical unknowns resolved. Implementation approach validated against existing codebase patterns. This is a straightforward metric following the same pattern as NUPL (spec-022) and Cost Basis (spec-023).

---

## 1. Revived Supply Formula Validation

### Decision
Use aggregate SUM query with age threshold filtering:
```sql
Revived Supply = SUM(btc_value)
                 WHERE is_spent = TRUE
                 AND age_days >= threshold (default: 365)
                 AND spent_timestamp >= NOW() - INTERVAL window DAY
```

### Rationale
- Industry-standard formula used by Glassnode (Coin Days Destroyed related metrics)
- Direct mapping to existing `utxo_lifecycle_full` VIEW columns
- `age_days` already calculated in VIEW, no additional computation needed

### Alternatives Considered
1. **Coin Days Destroyed (CDD)**: `SUM(btc_value × age_days)` - Different metric (already in spec-018 cointime)
2. **Revived by Value Band**: Segment by BTC value - Rejected: YAGNI, can add later

---

## 2. Age Threshold Definitions

### Decision
Support multiple thresholds via parameters with defaults:
- `threshold=365` (1 year) - Default
- Support `threshold=730` (2 years) and `threshold=1825` (5 years) as optional

### Rationale
- 365-day boundary is industry standard for "dormant" coins
- Glassnode uses 1y/2y/5y/10y thresholds
- Parameterized approach allows flexibility without over-engineering

### Alternatives Considered
1. **Fixed threshold only**: Hardcode 365 days - Rejected: loses valuable 2y/5y insights
2. **Many predefined thresholds**: Add 30d/90d/180d - Rejected: YAGNI, these aren't "revived"

---

## 3. Query Pattern for utxo_lifecycle_full VIEW

### Decision
Follow existing aggregate query pattern:

```sql
-- Revived Supply Query
SELECT
    SUM(btc_value) AS revived_btc,
    AVG(age_days) AS avg_age,
    COUNT(*) AS utxo_count
FROM utxo_lifecycle_full
WHERE is_spent = TRUE
  AND age_days >= :threshold  -- e.g., 365
  AND spent_timestamp >= NOW() - INTERVAL :window DAY  -- e.g., 30
```

### Rationale
- Reuses existing VIEW with `is_spent`, `age_days`, `spent_timestamp` columns
- Single aggregate query (no complex JOINs)
- Filter ensures only recently-spent dormant coins counted

### Alternatives Considered
1. **Rolling window in Python**: Process rows in memory - Rejected: inefficient, DuckDB handles this
2. **Pre-aggregated table**: Store daily revived totals - Rejected: adds complexity, VIEW is fast enough

---

## 4. Signal Zone Classification

### Decision
Classify revived supply into behavioral zones:

| Zone | Revived BTC/Day | Interpretation |
|------|-----------------|----------------|
| DORMANT | < 1000 | Low LTH activity |
| NORMAL | 1000-5000 | Baseline movement |
| ELEVATED | 5000-10000 | Increased LTH selling |
| SPIKE | > 10000 | Major distribution event |

### Rationale
- Based on historical Bitcoin on-chain data patterns
- Zone boundaries from Glassnode/CheckOnChain research
- Provides actionable signal without complex calculations

### Alternatives Considered
1. **No zones**: Just return raw numbers - Rejected: zones add analytical value
2. **Percentile-based zones**: Calculate from historical data - Rejected: requires historical baseline, adds complexity

---

## 5. Dataclass Design

### Decision
Create `RevivedSupplyResult` and `RevivedZone` enum:

```python
class RevivedZone(str, Enum):
    DORMANT = "dormant"
    NORMAL = "normal"
    ELEVATED = "elevated"
    SPIKE = "spike"

@dataclass
class RevivedSupplyResult:
    """Revived supply metrics for dormant coin movement tracking."""

    revived_1y: float           # BTC revived after 1+ year dormancy
    revived_2y: float           # BTC revived after 2+ year dormancy
    revived_5y: float           # BTC revived after 5+ year dormancy
    revived_total_usd: float    # USD value of revived supply
    revived_avg_age: float      # Average age of revived UTXOs (days)

    zone: RevivedZone           # Behavioral zone classification
    utxo_count: int             # Number of revived UTXOs

    window_days: int            # Lookback window used
    current_price_usd: float    # Price for USD calculation
    block_height: int
    timestamp: datetime
    confidence: float = 0.85    # High confidence for Tier A metric
```

### Rationale
- Follows `NUPLResult`, `CostBasisResult` patterns
- Includes `to_dict()` for JSON serialization
- Zone enum provides type-safe classification
- Stores context (window, price, block, timestamp) for API response

### Alternatives Considered
1. **Return dict**: No type safety - Rejected: inconsistent with codebase
2. **Separate result per threshold**: Three classes - Rejected: single class with multiple fields is cleaner

---

## 6. API Endpoint Design

### Decision
Add REST endpoint with optional parameters:

```
GET /api/metrics/revived-supply?threshold=365&window=30
```

Response:
```json
{
    "revived_1y": 5432.50,
    "revived_2y": 1234.75,
    "revived_5y": 567.25,
    "revived_total_usd": 516087500.00,
    "revived_avg_age": 892.5,
    "zone": "elevated",
    "utxo_count": 15234,
    "window_days": 30,
    "current_price_usd": 95000.0,
    "block_height": 875000,
    "timestamp": "2025-12-17T10:00:00Z",
    "confidence": 0.85
}
```

### Rationale
- Consistent with existing `/api/metrics/*` endpoints
- Optional `threshold` and `window` parameters for flexibility
- Single endpoint returns complete revived supply view

### Alternatives Considered
1. **WebSocket streaming**: Real-time updates - Rejected: YAGNI, metric changes slowly
2. **Separate endpoints per threshold**: `/api/metrics/revived-supply/1y` - Rejected: unnecessary complexity

---

## 7. Error Handling

### Decision
Handle edge cases gracefully:

| Scenario | Handling |
|----------|----------|
| Zero BTC revived | Return `revived_*y = 0.0`, `zone = DORMANT` |
| No spent UTXOs in window | Return `confidence = 0.0` (no data) |
| No price data | Return `revived_total_usd = 0.0` |

### Rationale
- Follows existing patterns in `calculate_nupl_signal()` and `calculate_cost_basis_signal()`
- Never raise exceptions for edge cases in metrics calculations
- Use confidence field to indicate data quality

---

## 8. Test Strategy

### Decision
TDD approach with fixture-based testing:

1. **Unit tests** (`tests/test_revived_supply.py`):
   - `test_calculate_revived_supply_basic`
   - `test_revived_supply_with_thresholds`
   - `test_classify_revived_zone_dormant`
   - `test_classify_revived_zone_normal`
   - `test_classify_revived_zone_elevated`
   - `test_classify_revived_zone_spike`
   - `test_empty_window_handling`
   - `test_revived_supply_api_endpoint`

2. **Integration test**: API endpoint response validation

### Rationale
- Follow existing test patterns in `tests/test_nupl.py` and `tests/test_cost_basis.py`
- Use DuckDB in-memory for fast tests
- Create sample spent UTXOs with known ages for deterministic validation

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

1. Add `RevivedZone` enum and `RevivedSupplyResult` dataclass to `metrics_models.py`
2. Write TDD tests (`tests/test_revived_supply.py`) - RED phase
3. Create `scripts/metrics/revived_supply.py` with calculation functions - GREEN phase
4. Add API endpoint to `api/main.py`
5. Run full test suite

**Estimated Effort**: 2-3 hours (as specified in spec)
