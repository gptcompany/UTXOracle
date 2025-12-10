# Quickstart: MVRV-Z Score + STH/LTH Variants

**Spec**: spec-020
**Date**: 2025-12-10

---

## Installation

No additional dependencies. Uses existing DuckDB and Python stdlib.

```bash
# Existing environment is sufficient
uv run pytest tests/test_realized_metrics.py -v
```

---

## Basic Usage

### Calculate MVRV-Z Score

```python
from scripts.metrics.realized_metrics import (
    calculate_mvrv_z,
    calculate_realized_cap,
    calculate_market_cap,
    get_total_unspent_supply,
)
import duckdb

# Connect to database
conn = duckdb.connect("utxo_lifecycle.duckdb")

# Get current values
supply = get_total_unspent_supply(conn)
current_price = 100000.0  # From UTXOracle
market_cap = calculate_market_cap(supply, current_price)
realized_cap = calculate_realized_cap(conn)

# Get market cap history (365 days)
history = conn.execute("""
    SELECT market_cap_usd
    FROM utxo_snapshots
    WHERE timestamp >= NOW() - INTERVAL 365 DAY
    ORDER BY block_height DESC
""").fetchall()
market_cap_history = [row[0] for row in history]

# Calculate MVRV-Z
mvrv_z = calculate_mvrv_z(market_cap, realized_cap, market_cap_history)
print(f"MVRV-Z Score: {mvrv_z:.2f}")
```

### Calculate Cohort MVRV

```python
from scripts.metrics.realized_metrics import (
    calculate_cohort_realized_cap,
    calculate_cohort_mvrv,
)

# Get current block height
current_block = 870000

# STH Realized Cap (< 155 days)
sth_realized_cap = calculate_cohort_realized_cap(
    conn, current_block, cohort="STH", threshold_days=155
)

# LTH Realized Cap (>= 155 days)
lth_realized_cap = calculate_cohort_realized_cap(
    conn, current_block, cohort="LTH", threshold_days=155
)

# Calculate cohort MVRVs
sth_mvrv = calculate_cohort_mvrv(market_cap, sth_realized_cap)
lth_mvrv = calculate_cohort_mvrv(market_cap, lth_realized_cap)

print(f"STH-MVRV: {sth_mvrv:.2f}")
print(f"LTH-MVRV: {lth_mvrv:.2f}")

# Validate invariant
total_realized = calculate_realized_cap(conn)
assert abs(sth_realized_cap + lth_realized_cap - total_realized) < 0.01
```

### Get Extended Signal

```python
from scripts.metrics.realized_metrics import get_mvrv_extended_signal

signal = get_mvrv_extended_signal(
    conn=conn,
    current_block=870000,
    current_price_usd=100000.0,
)

print(f"MVRV: {signal.mvrv:.2f}")
print(f"MVRV-Z: {signal.mvrv_z:.2f}")
print(f"Zone: {signal.zone}")
print(f"STH-MVRV: {signal.sth_mvrv:.2f}")
print(f"LTH-MVRV: {signal.lth_mvrv:.2f}")
print(f"Confidence: {signal.confidence:.2f}")
```

---

## Integration with Fusion

### Using MVRV-Z in Enhanced Fusion

```python
from scripts.metrics.monte_carlo_fusion import enhanced_fusion

# Convert MVRV-Z to vote
def mvrv_z_to_vote(mvrv_z: float) -> tuple[float, float]:
    """Convert MVRV-Z to fusion vote and confidence."""
    if mvrv_z > 7:
        # Extreme sell zone
        return -0.8, 0.9
    elif mvrv_z > 3:
        # Caution zone
        return -0.4, 0.7
    elif mvrv_z < -0.5:
        # Accumulation zone
        return 0.8, 0.85
    else:
        # Normal zone
        return 0.0, 0.6

mvrv_z_vote, mvrv_z_conf = mvrv_z_to_vote(signal.mvrv_z)

# Include in fusion
result = enhanced_fusion(
    whale_vote=0.6,
    whale_conf=0.85,
    utxo_vote=0.3,
    utxo_conf=0.9,
    mvrv_z_vote=mvrv_z_vote,  # NEW
    mvrv_z_conf=mvrv_z_conf,  # NEW
    # ... other votes
)

print(f"Fused Signal: {result.signal_mean:.2f}")
print(f"Action: {result.action} ({result.action_confidence:.0%})")
```

---

## Signal Interpretation

### MVRV-Z Score Zones

| MVRV-Z | Zone | Market Condition | Action |
|--------|------|------------------|--------|
| > 7 | EXTREME_SELL | Historically extreme overvaluation | Strong sell signal |
| 3 - 7 | CAUTION | Elevated valuation | Reduce exposure |
| -0.5 - 3 | NORMAL | Fair value range | Hold |
| < -0.5 | ACCUMULATION | Historically extreme undervaluation | Strong buy signal |

### STH-MVRV Interpretation

| Value | Meaning | Market Implication |
|-------|---------|-------------------|
| > 1.2 | New buyers in profit | Distribution risk - weak hands may sell |
| 1.0 | Break-even | Neutral |
| < 0.8 | New buyers underwater | Capitulation risk - bottom signal |

### LTH-MVRV Interpretation

| Value | Meaning | Market Implication |
|-------|---------|-------------------|
| > 3.5 | LTH in massive profit | Cycle top risk - even diamond hands distribute |
| 1.5 - 3.5 | Healthy profit | Bull market continuation |
| < 1.0 | LTH underwater | Generational bottom - extremely rare |

---

## Common Patterns

### Check for Extreme Conditions

```python
def check_market_extremes(signal: MVRVExtendedSignal) -> str:
    """Identify extreme market conditions from MVRV signals."""
    warnings = []

    if signal.mvrv_z > 7:
        warnings.append("EXTREME: MVRV-Z indicates historical top region")

    if signal.sth_mvrv > 1.3:
        warnings.append("CAUTION: STH in significant profit - distribution likely")

    if signal.lth_mvrv > 3.5:
        warnings.append("EXTREME: Even LTH in massive profit - cycle top risk")

    if signal.mvrv_z < -0.5 and signal.lth_mvrv < 1.5:
        warnings.append("OPPORTUNITY: Deep value accumulation zone")

    return "\n".join(warnings) if warnings else "Normal market conditions"
```

### Validate Cohort Data Consistency

```python
def validate_cohort_data(
    total_realized: float,
    sth_realized: float,
    lth_realized: float,
    tolerance: float = 0.01,
) -> bool:
    """Ensure STH + LTH = Total (data integrity check)."""
    return abs(sth_realized + lth_realized - total_realized) < tolerance
```

---

## Error Handling

```python
# Handle insufficient history
mvrv_z = calculate_mvrv_z(market_cap, realized_cap, history)
if mvrv_z == 0.0 and len(history) < 30:
    print("Warning: Insufficient history for Z-score calculation")

# Handle zero realized cap (edge case)
if realized_cap == 0:
    print("Error: No realized cap data available")
    mvrv = 0.0
else:
    mvrv = calculate_mvrv(market_cap, realized_cap)
```

---

## Performance Notes

- **MVRV-Z calculation**: <100ms (in-memory statistics)
- **Cohort realized cap**: <5 seconds (uses `idx_utxo_creation_block` index)
- **Full signal generation**: <6 seconds total

For high-frequency queries, cache the market cap history and refresh every 10 minutes.
