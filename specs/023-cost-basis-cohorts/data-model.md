# Data Model: STH/LTH Cost Basis (spec-023)

**Date**: 2025-12-16
**Status**: Complete

## Entities

### 1. CostBasisResult (New Dataclass)

Core entity for cost basis calculation results.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `sth_cost_basis` | `float` | Weighted average acquisition price for STH (<155 days) | >= 0 |
| `lth_cost_basis` | `float` | Weighted average acquisition price for LTH (>=155 days) | >= 0 |
| `total_cost_basis` | `float` | Overall realized price (all unspent UTXOs) | >= 0 |
| `sth_mvrv` | `float` | current_price / sth_cost_basis | >= 0 |
| `lth_mvrv` | `float` | current_price / lth_cost_basis | >= 0 |
| `sth_supply_btc` | `float` | Total BTC held by STH cohort | >= 0 |
| `lth_supply_btc` | `float` | Total BTC held by LTH cohort | >= 0 |
| `current_price_usd` | `float` | Price used for MVRV calculation | > 0 |
| `block_height` | `int` | Block height at calculation time | >= 0 |
| `timestamp` | `datetime` | Calculation timestamp | required |
| `confidence` | `float` | Data quality confidence (0.0-1.0) | 0.0-1.0, default 0.85 |

**Location**: `scripts/models/metrics_models.py`

### 2. utxo_lifecycle_full (Existing VIEW)

Source data for cost basis aggregation. No modifications needed.

| Column | Type | Used For |
|--------|------|----------|
| `btc_value` | `float` | Weight for averaging |
| `creation_price_usd` | `float` | Acquisition price |
| `realized_value_usd` | `float` | Pre-computed `btc_value × creation_price_usd` |
| `creation_block` | `int` | Cohort classification (age calculation) |
| `is_spent` | `bool` | Filter to unspent only |

## Relationships

```
CostBasisResult
    ├── Aggregated from: utxo_lifecycle_full (VIEW)
    ├── Uses: AgeCohortsConfig.sth_threshold_days (155)
    └── Extends: Similar pattern to NUPLResult, MVRVExtendedSignal
```

## State Transitions

N/A - `CostBasisResult` is a read-only snapshot, no state machine.

## Validation Rules

### CostBasisResult Validation

```python
def __post_init__(self):
    """Validate cost basis result fields."""
    # Cost basis values must be non-negative
    if self.sth_cost_basis < 0:
        raise ValueError(f"sth_cost_basis must be >= 0: {self.sth_cost_basis}")
    if self.lth_cost_basis < 0:
        raise ValueError(f"lth_cost_basis must be >= 0: {self.lth_cost_basis}")
    if self.total_cost_basis < 0:
        raise ValueError(f"total_cost_basis must be >= 0: {self.total_cost_basis}")

    # MVRV values must be non-negative
    if self.sth_mvrv < 0:
        raise ValueError(f"sth_mvrv must be >= 0: {self.sth_mvrv}")
    if self.lth_mvrv < 0:
        raise ValueError(f"lth_mvrv must be >= 0: {self.lth_mvrv}")

    # Supply must be non-negative
    if self.sth_supply_btc < 0:
        raise ValueError(f"sth_supply_btc must be >= 0: {self.sth_supply_btc}")
    if self.lth_supply_btc < 0:
        raise ValueError(f"lth_supply_btc must be >= 0: {self.lth_supply_btc}")

    # Price must be positive
    if self.current_price_usd <= 0:
        raise ValueError(f"current_price_usd must be > 0: {self.current_price_usd}")

    # Block height must be non-negative
    if self.block_height < 0:
        raise ValueError(f"block_height must be >= 0: {self.block_height}")

    # Confidence must be in [0, 1]
    if not 0.0 <= self.confidence <= 1.0:
        raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")
```

## SQL Query Patterns

### Calculate STH Cost Basis

```sql
SELECT
    COALESCE(SUM(realized_value_usd) / NULLIF(SUM(btc_value), 0), 0) AS sth_cost_basis,
    COALESCE(SUM(btc_value), 0) AS sth_supply_btc
FROM utxo_lifecycle_full
WHERE is_spent = FALSE
  AND creation_block > :cutoff_block  -- current_block - (155 * 144)
  AND creation_price_usd IS NOT NULL
  AND btc_value > 0
```

### Calculate LTH Cost Basis

```sql
SELECT
    COALESCE(SUM(realized_value_usd) / NULLIF(SUM(btc_value), 0), 0) AS lth_cost_basis,
    COALESCE(SUM(btc_value), 0) AS lth_supply_btc
FROM utxo_lifecycle_full
WHERE is_spent = FALSE
  AND creation_block <= :cutoff_block  -- current_block - (155 * 144)
  AND creation_price_usd IS NOT NULL
  AND btc_value > 0
```

### Calculate Total Cost Basis

```sql
SELECT
    COALESCE(SUM(realized_value_usd) / NULLIF(SUM(btc_value), 0), 0) AS total_cost_basis
FROM utxo_lifecycle_full
WHERE is_spent = FALSE
  AND creation_price_usd IS NOT NULL
  AND btc_value > 0
```

## JSON Serialization

```python
def to_dict(self) -> dict:
    """Convert to dictionary for JSON serialization."""
    return {
        "sth_cost_basis": self.sth_cost_basis,
        "lth_cost_basis": self.lth_cost_basis,
        "total_cost_basis": self.total_cost_basis,
        "sth_mvrv": self.sth_mvrv,
        "lth_mvrv": self.lth_mvrv,
        "sth_supply_btc": self.sth_supply_btc,
        "lth_supply_btc": self.lth_supply_btc,
        "current_price_usd": self.current_price_usd,
        "block_height": self.block_height,
        "timestamp": self.timestamp.isoformat()
            if hasattr(self.timestamp, "isoformat")
            else str(self.timestamp),
        "confidence": self.confidence,
    }
```

## Index Requirements

Existing indexes on `utxo_lifecycle_full` VIEW are sufficient:
- `idx_utxo_lifecycle_spent` on `(is_spent)`
- `idx_utxo_lifecycle_creation_block` on `(creation_block)`

No new indexes required.
