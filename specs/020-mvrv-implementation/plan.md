# spec-020: Implementation Plan

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 MVRV Extended (spec-020)                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Existing (spec-017):                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  realized_metrics.py                                  │   │
│  │  - calculate_mvrv() ✅                                │   │
│  │  - calculate_realized_cap() ✅                        │   │
│  │  - calculate_nupl() ✅                                │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  NEW (this spec):                                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  + calculate_mvrv_z()                                 │   │
│  │  + calculate_cohort_realized_cap()                    │   │
│  │  + calculate_cohort_mvrv()                            │   │
│  │  + MVRVExtendedSignal dataclass                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  monte_carlo_fusion.py                                │   │
│  │  + mvrv_z_vote, mvrv_z_conf parameters                │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: MVRV-Z Score (1.5 hours)

### Step 1.1: Add to realized_metrics.py (45 min)
```python
def calculate_mvrv_z(
    market_cap: float,
    realized_cap: float,
    market_cap_history: list[float],
) -> float:
    """Calculate MVRV-Z score for cross-cycle comparison."""
    import statistics

    if len(market_cap_history) < 30:
        return 0.0

    std = statistics.stdev(market_cap_history)
    if std == 0:
        return 0.0

    return (market_cap - realized_cap) / std
```

### Step 1.2: Market Cap History Helper (45 min)
```python
def get_market_cap_history(
    conn: duckdb.DuckDBPyConnection,
    days: int = 365,
) -> list[float]:
    """Get historical market caps from snapshots table."""
    result = conn.execute("""
        SELECT market_cap_usd
        FROM utxo_snapshots
        ORDER BY block_height DESC
        LIMIT ?
    """, [days]).fetchall()

    return [r[0] for r in result]
```

---

## Phase 2: Cohort Realized Cap (1 hour)

### Step 2.1: STH/LTH Realized Cap (45 min)
```python
def calculate_cohort_realized_cap(
    conn: duckdb.DuckDBPyConnection,
    current_block: int,
    cohort: Literal["STH", "LTH"],
    threshold_days: int = 155,
) -> float:
    """Calculate realized cap for STH or LTH cohort."""
    threshold_blocks = threshold_days * 144
    cutoff_block = current_block - threshold_blocks

    op = ">" if cohort == "STH" else "<="

    result = conn.execute(f"""
        SELECT COALESCE(SUM(btc_value * creation_price_usd), 0)
        FROM utxo_lifecycle
        WHERE is_spent = FALSE
          AND creation_block {op} ?
    """, [cutoff_block]).fetchone()

    return result[0]
```

### Step 2.2: Validation Helper (15 min)
```python
def validate_cohort_split(
    total_rc: float,
    sth_rc: float,
    lth_rc: float,
    tolerance: float = 0.01,
) -> bool:
    """Validate that STH + LTH ≈ Total realized cap."""
    return abs((sth_rc + lth_rc) - total_rc) / total_rc < tolerance
```

---

## Phase 3: STH/LTH MVRV (30 min)

### Step 3.1: Cohort MVRV Calculation
```python
def calculate_cohort_mvrv(
    market_cap: float,
    cohort_realized_cap: float,
) -> float:
    """Calculate MVRV for specific cohort."""
    if cohort_realized_cap <= 0:
        return 0.0
    return market_cap / cohort_realized_cap


def calculate_all_mvrv_variants(
    conn: duckdb.DuckDBPyConnection,
    current_block: int,
    current_price: float,
    total_supply: float,
) -> dict[str, float]:
    """Calculate all MVRV variants in one call."""
    market_cap = current_price * total_supply

    # Get realized caps
    total_rc = calculate_realized_cap(conn)
    sth_rc = calculate_cohort_realized_cap(conn, current_block, "STH")
    lth_rc = calculate_cohort_realized_cap(conn, current_block, "LTH")

    return {
        "mvrv": market_cap / total_rc if total_rc > 0 else 0.0,
        "sth_mvrv": market_cap / sth_rc if sth_rc > 0 else 0.0,
        "lth_mvrv": market_cap / lth_rc if lth_rc > 0 else 0.0,
    }
```

---

## Phase 4: Signal Classification (30 min)

### Step 4.1: Dataclass Definition
```python
@dataclass
class MVRVExtendedSignal:
    mvrv: float
    mvrv_z: float
    sth_mvrv: float
    lth_mvrv: float
    zone: str
    confidence: float
    timestamp: datetime
```

### Step 4.2: Zone Classification
```python
def classify_mvrv_zone(mvrv_z: float) -> tuple[str, float]:
    """Classify MVRV-Z into actionable zone."""
    if mvrv_z > 7:
        return ("EXTREME_SELL", 0.95)
    elif mvrv_z > 3:
        return ("CAUTION", 0.75)
    elif mvrv_z > -0.5:
        return ("NORMAL", 0.50)
    else:
        return ("ACCUMULATION", 0.85)
```

---

## Phase 5: Fusion Integration (1 hour)

### Step 5.1: Update enhanced_fusion()
```python
def enhanced_fusion(
    # ... existing params ...
    mvrv_z_vote: Optional[float] = None,
    mvrv_z_conf: Optional[float] = None,
    # ...
) -> EnhancedFusionResult:
    # Add to components
    if mvrv_z_vote is not None and mvrv_z_conf is not None:
        components["mvrv_z"] = (mvrv_z_vote, mvrv_z_conf)
```

### Step 5.2: Update Weights
```python
ENHANCED_WEIGHTS = {
    # ... existing ...
    "power_law": 0.06,  # Reduced from 0.09
    "mvrv_z": 0.03,     # NEW
}
```

### Step 5.3: Signal to Vote Converter
```python
def mvrv_z_to_vote(signal: MVRVExtendedSignal) -> tuple[float, float]:
    """Convert MVRV-Z signal to fusion vote.

    Returns (vote, confidence):
    - EXTREME_SELL: -0.8
    - CAUTION: -0.4
    - NORMAL: 0.0
    - ACCUMULATION: +0.6
    """
    zone_to_vote = {
        "EXTREME_SELL": -0.8,
        "CAUTION": -0.4,
        "NORMAL": 0.0,
        "ACCUMULATION": 0.6,
    }
    return (zone_to_vote[signal.zone], signal.confidence)
```

---

## Phase 6: Testing (1 hour)

### Test Cases
```python
def test_mvrv_z_basic():
    """Test Z-score calculation."""
    history = [1e12] * 365  # Constant = std 0
    assert calculate_mvrv_z(1.5e12, 1e12, history) == 0.0

    history = [1e12 + i * 1e10 for i in range(365)]
    z = calculate_mvrv_z(2e12, 1e12, history)
    assert z > 0  # Above realized cap


def test_cohort_realized_cap(test_db):
    """Test STH/LTH realized cap split."""
    sth_rc = calculate_cohort_realized_cap(test_db, 800000, "STH")
    lth_rc = calculate_cohort_realized_cap(test_db, 800000, "LTH")
    total_rc = calculate_realized_cap(test_db)

    assert abs((sth_rc + lth_rc) - total_rc) < total_rc * 0.01


def test_mvrv_zone_classification():
    """Test zone boundaries."""
    assert classify_mvrv_zone(8.0)[0] == "EXTREME_SELL"
    assert classify_mvrv_zone(5.0)[0] == "CAUTION"
    assert classify_mvrv_zone(1.0)[0] == "NORMAL"
    assert classify_mvrv_zone(-1.0)[0] == "ACCUMULATION"
```

---

## Rollout

| Day | Phase | Deliverable |
|-----|-------|-------------|
| 1 AM | Phases 1-2 | MVRV-Z + Cohort RC |
| 1 PM | Phases 3-4 | STH/LTH MVRV + Signals |
| 2 AM | Phases 5-6 | Fusion + Tests |

**Total: 1.5 days**
