# spec-020: MVRV-Z Score + STH/LTH Variants

## Overview

Extend existing MVRV implementation with Z-score normalization and cohort-specific variants (STH/LTH). These additions enable cross-cycle comparison and cohort-level analysis.

## What Already Exists (spec-017)

| Component | Status | Location |
|-----------|--------|----------|
| MVRV base | ✅ | `realized_metrics.py::calculate_mvrv()` |
| Realized Cap | ✅ | `realized_metrics.py::calculate_realized_cap()` |
| Market Cap | ✅ | `realized_metrics.py::calculate_market_cap()` |
| NUPL | ✅ | `realized_metrics.py::calculate_nupl()` |
| AVIV | ✅ | `cointime.py` (Cointime alternative) |

## What This Spec Adds

| Component | Priority | Effort |
|-----------|----------|--------|
| **MVRV-Z Score** | P0 | 1.5h |
| **STH-MVRV** | P0 | 1h |
| **LTH-MVRV** | P0 | 1h |
| Signal classification | P1 | 30min |
| Fusion integration | P1 | 1h |

**Total Effort: 5 hours**

---

## MVRV-Z Score

### Definition
```
MVRV-Z = (Market Cap - Realized Cap) / StdDev(Market Cap)
```

### Why It Matters
- **Cross-cycle comparison**: Raw MVRV of 3.0 in 2017 ≠ 3.0 in 2024 (different volatility)
- **Normalized extremes**: Z > 7 = statistically extreme overvaluation
- **Academic standard**: Used in most research papers

### Signal Interpretation

| MVRV-Z | Zone | Action |
|--------|------|--------|
| > 7 | Extreme | Strong sell signal |
| 3 - 7 | Caution | Reduce exposure |
| -0.5 - 3 | Normal | Hold |
| < -0.5 | Accumulation | Strong buy signal |

### Implementation
```python
def calculate_mvrv_z(
    market_cap: float,
    realized_cap: float,
    market_cap_history: list[float],  # 365 days recommended
) -> float:
    """Calculate MVRV-Z score.

    Args:
        market_cap: Current market cap
        realized_cap: Current realized cap
        market_cap_history: Historical market caps for std calculation

    Returns:
        MVRV-Z score (typically -2 to +10 range)
    """
    if len(market_cap_history) < 30:
        return 0.0  # Insufficient data

    std = statistics.stdev(market_cap_history)
    if std == 0:
        return 0.0

    return (market_cap - realized_cap) / std
```

---

## STH/LTH MVRV Variants

### Definitions
```
STH-MVRV = Market Cap / STH Realized Cap
         = (Price × Supply) / Σ(UTXO × creation_price) for UTXOs < 155 days

LTH-MVRV = Market Cap / LTH Realized Cap
         = (Price × Supply) / Σ(UTXO × creation_price) for UTXOs >= 155 days
```

### Why They Matter

| Metric | What It Shows |
|--------|---------------|
| STH-MVRV | New buyers' profit/loss status |
| LTH-MVRV | Diamond hands' profit/loss status |

### Signal Interpretation

**STH-MVRV:**
| Value | Interpretation |
|-------|----------------|
| > 1.2 | New buyers in profit → distribution risk |
| 1.0 | Break-even |
| < 0.8 | New buyers underwater → capitulation |

**LTH-MVRV:**
| Value | Interpretation |
|-------|----------------|
| > 3.5 | LTH in massive profit → cycle top risk |
| 1.5 - 3.5 | Healthy profit |
| < 1.0 | LTH underwater → generational bottom |

### Implementation
```python
def calculate_cohort_realized_cap(
    conn: duckdb.DuckDBPyConnection,
    current_block: int,
    cohort: Literal["STH", "LTH"],
    threshold_days: int = 155,
) -> float:
    """Calculate realized cap for specific cohort."""
    threshold_blocks = threshold_days * 144
    cutoff_block = current_block - threshold_blocks

    if cohort == "STH":
        condition = f"creation_block > {cutoff_block}"
    else:
        condition = f"creation_block <= {cutoff_block}"

    result = conn.execute(f"""
        SELECT COALESCE(SUM(btc_value * creation_price_usd), 0)
        FROM utxo_lifecycle
        WHERE is_spent = FALSE AND {condition}
    """).fetchone()

    return result[0]


def calculate_cohort_mvrv(
    market_cap: float,
    cohort_realized_cap: float,
) -> float:
    """Calculate MVRV for specific cohort."""
    if cohort_realized_cap <= 0:
        return 0.0
    return market_cap / cohort_realized_cap
```

---

## Functional Requirements

### FR-001: MVRV-Z Score
- Calculate using 365-day rolling market cap history
- Handle insufficient data gracefully (return 0.0)
- Store historical values for time-series analysis

### FR-002: Cohort Realized Cap
- Query `utxo_lifecycle` with age filter
- Configurable STH/LTH threshold (default 155 days)

### FR-003: STH/LTH MVRV
- Calculate both variants in single function call
- Return structured result with both values

### FR-004: Signal Classification
```python
@dataclass
class MVRVExtendedSignal:
    mvrv: float          # From existing realized_metrics.py
    mvrv_z: float        # NEW
    sth_mvrv: float      # NEW
    lth_mvrv: float      # NEW
    zone: str            # "EXTREME_SELL", "CAUTION", "NORMAL", "ACCUMULATION"
    confidence: float
    timestamp: datetime
```

### FR-005: Fusion Integration
- Add `mvrv_z_vote` and `mvrv_z_conf` to `enhanced_fusion()`
- Weight: 0.03 (reduce power_law from 0.09 to 0.06)

---

## Non-Functional Requirements

### NFR-001: Performance
- Cohort realized cap: < 5 seconds
- Z-score calculation: < 100ms

### NFR-002: Storage
- Extend `utxo_snapshots` table with new columns
- Or create separate `mvrv_extended` table

---

## Data Requirements

### Market Cap History
Need 365 days of market cap for proper Z-score. Options:
1. Query `utxo_snapshots` table (if populated)
2. Calculate from historical price × supply
3. External data source for bootstrap

### SQL for Cohort Realized Cap
```sql
-- STH Realized Cap (< 155 days)
SELECT COALESCE(SUM(btc_value * creation_price_usd), 0)
FROM utxo_lifecycle
WHERE is_spent = FALSE
  AND creation_block > :current_block - 22320  -- 155 * 144

-- LTH Realized Cap (>= 155 days)
SELECT COALESCE(SUM(btc_value * creation_price_usd), 0)
FROM utxo_lifecycle
WHERE is_spent = FALSE
  AND creation_block <= :current_block - 22320
```

---

## Acceptance Criteria

1. [ ] `calculate_mvrv_z()` returns valid Z-score
2. [ ] `calculate_cohort_realized_cap()` works for STH/LTH
3. [ ] `calculate_cohort_mvrv()` returns correct ratios
4. [ ] STH + LTH realized cap ≈ Total realized cap (validation)
5. [ ] Signal classification zones implemented
6. [ ] Fusion integration working
7. [ ] All tests pass

---

## Files to Modify

| File | Changes |
|------|---------|
| `scripts/metrics/realized_metrics.py` | Add Z-score, cohort functions |
| `scripts/metrics/monte_carlo_fusion.py` | Add mvrv_z signal |
| `tests/test_realized_metrics.py` | Add new tests |

**No new files needed** - extend existing `realized_metrics.py`

---

## Dependencies

| Dependency | Status |
|------------|--------|
| `realized_metrics.py` | ✅ Has MVRV base |
| `utxo_lifecycle` table | ✅ Has creation_price_usd |
| Market cap history | ⚠️ May need bootstrap |

---

## Effort Summary

| Task | Effort |
|------|--------|
| MVRV-Z Score implementation | 1.5h |
| STH/LTH Realized Cap | 1h |
| STH/LTH MVRV calculation | 30min |
| Signal classification | 30min |
| Fusion integration | 1h |
| Tests | 1h |
| **Total** | **5.5 hours** |
