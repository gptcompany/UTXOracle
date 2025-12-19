# Data Model: P/L Ratio (Dominance)

**Spec**: spec-029 | **Date**: 2025-12-19

## Entities

### PLDominanceZone (Enum)

Zone classification for P/L dominance metric.

| Value | Description |
|-------|-------------|
| `EXTREME_PROFIT` | Euphoria, potential top (ratio > 5.0, dominance > 0.67) |
| `PROFIT` | Healthy bull market (ratio 1.5-5.0, dominance 0.2-0.67) |
| `NEUTRAL` | Equilibrium (ratio 0.67-1.5, dominance -0.2-0.2) |
| `LOSS` | Bear market (ratio 0.2-0.67, dominance -0.67--0.2) |
| `EXTREME_LOSS` | Capitulation, potential bottom (ratio < 0.2, dominance < -0.67) |

**Location**: `scripts/models/metrics_models.py`

### PLRatioResult (Dataclass)

Result of P/L Ratio calculation.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `pl_ratio` | `float` | Raw ratio (Profit / Loss) | >= 0 |
| `pl_dominance` | `float` | Normalized (-1 to +1) | -1.0 <= x <= 1.0 |
| `profit_dominant` | `bool` | True if ratio > 1 | - |
| `dominance_zone` | `PLDominanceZone` | Zone classification | Valid enum |
| `realized_profit_usd` | `float` | Source profit value | >= 0 |
| `realized_loss_usd` | `float` | Source loss value | >= 0 |
| `window_hours` | `int` | Time window | 1-720 |
| `timestamp` | `datetime` | Calculation time | - |

**Location**: `scripts/models/metrics_models.py`

**Methods**:
- `to_dict() -> dict`: JSON-serializable dictionary

### PLRatioHistoryPoint (Dataclass)

Single point in P/L ratio history.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `date` | `date` | Date of data point | - |
| `pl_ratio` | `float` | Raw ratio for the day | >= 0 |
| `pl_dominance` | `float` | Normalized dominance | -1.0 <= x <= 1.0 |
| `dominance_zone` | `PLDominanceZone` | Zone classification | Valid enum |
| `realized_profit_usd` | `float` | Daily profit | >= 0 |
| `realized_loss_usd` | `float` | Daily loss | >= 0 |

**Location**: `scripts/models/metrics_models.py`

## Relationships

```
NetRealizedPnLResult (spec-028)
    │
    └──▶ PLRatioResult
           ├── pl_ratio = realized_profit_usd / realized_loss_usd
           ├── pl_dominance = (profit - loss) / (profit + loss)
           └── dominance_zone = classify(pl_dominance)

NetRealizedPnLHistoryPoint (spec-028)
    │
    └──▶ PLRatioHistoryPoint
           └── (same derivation as above)
```

## State Transitions

*None - stateless metric calculation.*

## Threshold Constants

```python
# Zone thresholds (from spec)
EXTREME_PROFIT_THRESHOLD = 5.0   # ratio > 5.0
PROFIT_THRESHOLD = 1.5          # ratio > 1.5
NEUTRAL_LOW_THRESHOLD = 0.67    # ratio > 0.67
LOSS_THRESHOLD = 0.2            # ratio > 0.2
# Below 0.2 = EXTREME_LOSS

# Dominance equivalents
DOMINANCE_EXTREME_PROFIT = 0.67   # > 0.67
DOMINANCE_PROFIT = 0.2            # > 0.2
DOMINANCE_NEUTRAL_LOW = -0.2      # > -0.2
DOMINANCE_LOSS = -0.67            # > -0.67
# Below -0.67 = EXTREME_LOSS
```

## Database Schema

*No new database tables required. Uses existing `utxo_lifecycle_full` VIEW via spec-028.*

## Validation Rules

1. **pl_ratio**: Must be >= 0 (non-negative). Special case: 1e9 when loss = 0.
2. **pl_dominance**: Must be in range [-1.0, 1.0]. Special case: 0.0 when profit + loss = 0.
3. **window_hours**: Must be 1-720 (matches spec-028 constraint).
4. **dominance_zone**: Must be valid PLDominanceZone enum value.

## Example Data

```python
# Example 1: Profit dominant market
PLRatioResult(
    pl_ratio=2.5,
    pl_dominance=0.43,  # (2.5-1)/(2.5+1) normalized
    profit_dominant=True,
    dominance_zone=PLDominanceZone.PROFIT,
    realized_profit_usd=250000.0,
    realized_loss_usd=100000.0,
    window_hours=24,
    timestamp=datetime(2025, 12, 19, 12, 0, 0)
)

# Example 2: Capitulation (extreme loss)
PLRatioResult(
    pl_ratio=0.15,
    pl_dominance=-0.74,
    profit_dominant=False,
    dominance_zone=PLDominanceZone.EXTREME_LOSS,
    realized_profit_usd=15000.0,
    realized_loss_usd=100000.0,
    window_hours=24,
    timestamp=datetime(2025, 12, 19, 12, 0, 0)
)

# Example 3: Neutral market
PLRatioResult(
    pl_ratio=1.0,
    pl_dominance=0.0,
    profit_dominant=False,  # ratio must be > 1 for True
    dominance_zone=PLDominanceZone.NEUTRAL,
    realized_profit_usd=50000.0,
    realized_loss_usd=50000.0,
    window_hours=24,
    timestamp=datetime(2025, 12, 19, 12, 0, 0)
)
```
