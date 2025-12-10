# spec-020: Tasks

## Task Dependency Graph

```
T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008
```

---

## T001: Add MVRV-Z Score Function
**Status:** TODO
**Priority:** P0
**Effort:** 45 min

### Description
Add `calculate_mvrv_z()` to `scripts/metrics/realized_metrics.py`.

### Actions
1. Add import for `statistics` module
2. Implement function:
```python
def calculate_mvrv_z(
    market_cap: float,
    realized_cap: float,
    market_cap_history: list[float],
) -> float:
    """Calculate MVRV-Z score for cross-cycle comparison.

    MVRV-Z = (Market Cap - Realized Cap) / StdDev(Market Cap)

    Args:
        market_cap: Current market cap in USD
        realized_cap: Current realized cap in USD
        market_cap_history: Historical market caps (365 days recommended)

    Returns:
        MVRV-Z score (typically -2 to +10 range)
    """
    if len(market_cap_history) < 30:
        return 0.0

    std = statistics.stdev(market_cap_history)
    if std == 0:
        return 0.0

    return (market_cap - realized_cap) / std
```

### Acceptance Criteria
- [ ] Function implemented
- [ ] Handles < 30 days history
- [ ] Handles zero std deviation

---

## T002: Add Market Cap History Helper
**Status:** TODO
**Priority:** P0
**Effort:** 45 min
**Depends:** T001

### Description
Add helper to fetch historical market caps from `utxo_snapshots`.

### Implementation
```python
def get_market_cap_history(
    conn: duckdb.DuckDBPyConnection,
    days: int = 365,
) -> list[float]:
    """Get historical market caps from snapshots table.

    Args:
        conn: DuckDB connection
        days: Number of days of history (default 365)

    Returns:
        List of market cap values, newest first
    """
    result = conn.execute("""
        SELECT market_cap_usd
        FROM utxo_snapshots
        WHERE market_cap_usd IS NOT NULL
        ORDER BY block_height DESC
        LIMIT ?
    """, [days]).fetchall()

    return [r[0] for r in result if r[0] is not None]
```

### Acceptance Criteria
- [ ] Returns list of floats
- [ ] Handles empty table
- [ ] Orders by block_height DESC

---

## T003: Add Cohort Realized Cap Function
**Status:** TODO
**Priority:** P0
**Effort:** 45 min
**Depends:** T002

### Description
Add `calculate_cohort_realized_cap()` for STH/LTH breakdown.

### Implementation
```python
def calculate_cohort_realized_cap(
    conn: duckdb.DuckDBPyConnection,
    current_block: int,
    cohort: Literal["STH", "LTH"],
    threshold_days: int = 155,
) -> float:
    """Calculate realized cap for specific age cohort.

    Args:
        conn: DuckDB connection
        current_block: Current block height
        cohort: "STH" (< threshold) or "LTH" (>= threshold)
        threshold_days: STH/LTH boundary (default 155 days)

    Returns:
        Realized cap in USD for the cohort
    """
    threshold_blocks = threshold_days * 144
    cutoff_block = current_block - threshold_blocks

    op = ">" if cohort == "STH" else "<="

    result = conn.execute(f"""
        SELECT COALESCE(SUM(btc_value * creation_price_usd), 0)
        FROM utxo_lifecycle
        WHERE is_spent = FALSE
          AND creation_block {op} ?
    """, [cutoff_block]).fetchone()

    return result[0] if result else 0.0
```

### Acceptance Criteria
- [ ] STH = UTXOs younger than threshold
- [ ] LTH = UTXOs older than threshold
- [ ] Returns 0.0 for empty result

---

## T004: Add Cohort MVRV Functions
**Status:** TODO
**Priority:** P0
**Effort:** 30 min
**Depends:** T003

### Description
Add functions to calculate MVRV for each cohort.

### Implementation
```python
def calculate_cohort_mvrv(
    market_cap: float,
    cohort_realized_cap: float,
) -> float:
    """Calculate MVRV for a specific cohort."""
    if cohort_realized_cap <= 0:
        return 0.0
    return market_cap / cohort_realized_cap


def calculate_all_mvrv_variants(
    conn: duckdb.DuckDBPyConnection,
    current_block: int,
    market_cap: float,
) -> dict[str, float]:
    """Calculate all MVRV variants in one call.

    Returns:
        Dict with keys: mvrv, sth_mvrv, lth_mvrv
    """
    total_rc = calculate_realized_cap(conn)
    sth_rc = calculate_cohort_realized_cap(conn, current_block, "STH")
    lth_rc = calculate_cohort_realized_cap(conn, current_block, "LTH")

    return {
        "mvrv": calculate_mvrv(market_cap, total_rc),
        "sth_mvrv": calculate_cohort_mvrv(market_cap, sth_rc),
        "lth_mvrv": calculate_cohort_mvrv(market_cap, lth_rc),
    }
```

### Acceptance Criteria
- [ ] All variants calculated
- [ ] Division by zero handled

---

## T005: Add MVRVExtendedSignal Dataclass
**Status:** TODO
**Priority:** P1
**Effort:** 15 min
**Depends:** T004

### Description
Add dataclass for extended MVRV signal.

### Implementation
```python
@dataclass
class MVRVExtendedSignal:
    """Extended MVRV signal with Z-score and cohort variants."""
    mvrv: float
    mvrv_z: float
    sth_mvrv: float
    lth_mvrv: float
    zone: str  # "EXTREME_SELL", "CAUTION", "NORMAL", "ACCUMULATION"
    confidence: float
    timestamp: datetime
```

### Acceptance Criteria
- [ ] Dataclass defined
- [ ] All fields typed

---

## T006: Add Zone Classification
**Status:** TODO
**Priority:** P1
**Effort:** 15 min
**Depends:** T005

### Description
Add function to classify MVRV-Z into actionable zones.

### Implementation
```python
def classify_mvrv_zone(mvrv_z: float) -> tuple[str, float]:
    """Classify MVRV-Z into actionable zone.

    Returns:
        (zone_name, confidence)
    """
    if mvrv_z > 7:
        return ("EXTREME_SELL", 0.95)
    elif mvrv_z > 3:
        return ("CAUTION", 0.75)
    elif mvrv_z > -0.5:
        return ("NORMAL", 0.50)
    else:
        return ("ACCUMULATION", 0.85)
```

### Acceptance Criteria
- [ ] All zones covered
- [ ] Confidence values sensible

---

## T007: Fusion Integration
**Status:** TODO
**Priority:** P1
**Effort:** 1 hour
**Depends:** T006

### Description
Add MVRV-Z signal to Monte Carlo Fusion.

### Actions
1. Add parameters to `enhanced_fusion()`:
```python
mvrv_z_vote: Optional[float] = None,
mvrv_z_conf: Optional[float] = None,
```

2. Add to `ENHANCED_WEIGHTS`:
```python
"power_law": 0.06,  # Reduced from 0.09
"mvrv_z": 0.03,     # NEW
```

3. Add component handling:
```python
if mvrv_z_vote is not None and mvrv_z_conf is not None:
    components["mvrv_z"] = (mvrv_z_vote, mvrv_z_conf)
```

4. Add `mvrv_z_weight` to `EnhancedFusionResult`

5. Add vote converter:
```python
def mvrv_z_to_vote(signal: MVRVExtendedSignal) -> tuple[float, float]:
    zone_to_vote = {
        "EXTREME_SELL": -0.8,
        "CAUTION": -0.4,
        "NORMAL": 0.0,
        "ACCUMULATION": 0.6,
    }
    return (zone_to_vote[signal.zone], signal.confidence)
```

### Acceptance Criteria
- [ ] Parameters added
- [ ] Weights rebalanced (sum = 1.0)
- [ ] Vote converter working

---

## T008: Tests
**Status:** TODO
**Priority:** P0
**Effort:** 1 hour
**Depends:** T007

### Description
Add comprehensive tests for all new functions.

### Test Cases
```python
# test_realized_metrics.py additions

def test_mvrv_z_basic():
    """Test Z-score with normal distribution."""
    history = [1e12 + i * 1e10 for i in range(365)]
    z = calculate_mvrv_z(2e12, 1e12, history)
    assert z > 0


def test_mvrv_z_insufficient_history():
    """Test handling of insufficient data."""
    history = [1e12] * 20  # Only 20 days
    assert calculate_mvrv_z(2e12, 1e12, history) == 0.0


def test_mvrv_z_zero_std():
    """Test handling of zero standard deviation."""
    history = [1e12] * 365  # Constant
    assert calculate_mvrv_z(2e12, 1e12, history) == 0.0


def test_cohort_realized_cap_sth(test_db):
    """Test STH realized cap calculation."""
    rc = calculate_cohort_realized_cap(test_db, 800000, "STH")
    assert rc >= 0


def test_cohort_realized_cap_lth(test_db):
    """Test LTH realized cap calculation."""
    rc = calculate_cohort_realized_cap(test_db, 800000, "LTH")
    assert rc >= 0


def test_cohort_sum_equals_total(test_db):
    """Validate STH + LTH ≈ Total."""
    total = calculate_realized_cap(test_db)
    sth = calculate_cohort_realized_cap(test_db, 800000, "STH")
    lth = calculate_cohort_realized_cap(test_db, 800000, "LTH")

    if total > 0:
        assert abs((sth + lth) - total) / total < 0.01


def test_zone_classification():
    """Test all zone boundaries."""
    assert classify_mvrv_zone(8.0)[0] == "EXTREME_SELL"
    assert classify_mvrv_zone(5.0)[0] == "CAUTION"
    assert classify_mvrv_zone(1.0)[0] == "NORMAL"
    assert classify_mvrv_zone(-1.0)[0] == "ACCUMULATION"


def test_fusion_with_mvrv_z():
    """Test fusion integration."""
    result = enhanced_fusion(
        whale_vote=0.5, whale_conf=0.8,
        mvrv_z_vote=-0.4, mvrv_z_conf=0.75,
    )
    assert result.mvrv_z_weight > 0
```

### Acceptance Criteria
- [ ] All tests pass
- [ ] Edge cases covered
- [ ] Integration test with fusion

---

## Summary

| Task | Description | Effort | Priority |
|------|-------------|--------|----------|
| T001 | MVRV-Z function | 45 min | P0 |
| T002 | Market cap history | 45 min | P0 |
| T003 | Cohort realized cap | 45 min | P0 |
| T004 | Cohort MVRV functions | 30 min | P0 |
| T005 | MVRVExtendedSignal | 15 min | P1 |
| T006 | Zone classification | 15 min | P1 |
| T007 | Fusion integration | 1h | P1 |
| T008 | Tests | 1h | P0 |

**Total: 8 tasks, ~5.5 hours**
