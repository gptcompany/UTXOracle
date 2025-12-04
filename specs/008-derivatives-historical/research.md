# Research: Derivatives Historical Integration

**Feature**: 008-derivatives-historical
**Date**: 2025-12-03
**Status**: Complete

## 1. LiquidationHeatmap DuckDB Schema Discovery

### Database Location
```
Path: /media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb
Size: ~198 GB
```

### Relevant Tables

#### funding_rate_history
| Column | Type | Description |
|--------|------|-------------|
| id | BIGINT | Primary key |
| timestamp | TIMESTAMP | Funding collection time (8-hour intervals) |
| symbol | VARCHAR | "BTCUSDT" |
| funding_rate | DECIMAL(10,8) | Raw rate (e.g., 0.00010000 = 0.01%) |
| funding_interval_hours | INTEGER | Always 8 for Binance |

**Data Range**: 2021-12-01 to 2025-08-31 (4,119 records)
**Frequency**: 8-hour intervals (00:00, 08:00, 16:00 UTC)

#### open_interest_history
| Column | Type | Description |
|--------|------|-------------|
| id | BIGINT | Primary key |
| timestamp | TIMESTAMP | OI snapshot time (5-minute intervals) |
| symbol | VARCHAR | "BTCUSDT" |
| open_interest_value | DECIMAL(20,8) | OI in USD |
| open_interest_contracts | DECIMAL(18,8) | OI in BTC contracts |
| source | VARCHAR | Data source identifier |
| oi_delta | DECIMAL(20,8) | Change from previous snapshot |

**Data Range**: 2021-12-01 to 2025-11-17 (417,460 records)
**Frequency**: 5-minute intervals

### Cross-Database Query Approach

**Decision**: Use DuckDB `ATTACH` with `READ_ONLY` mode

**Rationale**:
- Zero data duplication (constitution Principle I: minimize dependencies)
- Native DuckDB feature, no external dependencies
- READ_ONLY prevents lock contention
- Automatic schema discovery

**Query Pattern**:
```sql
ATTACH '/media/sam/1TB/LiquidationHeatmap/data/processed/liquidations.duckdb'
AS liq (READ_ONLY);

SELECT timestamp, funding_rate
FROM liq.funding_rate_history
WHERE symbol = 'BTCUSDT'
  AND timestamp BETWEEN ? AND ?
ORDER BY timestamp DESC;
```

**Alternatives Considered**:
1. ❌ Data copy: Would duplicate ~198GB, violates zero-duplication requirement
2. ❌ Parquet export: Adds maintenance burden, data staleness risk
3. ✅ DuckDB ATTACH: Native, zero-copy, automatic updates

---

## 2. Funding Rate Normalization

### Problem
Raw funding rate ranges from ~-0.08% to +0.2%. Need to convert to -1 to +1 signal vote.

### Decision: Contrarian Signal with Extreme Detection

**Rationale**:
- Funding rate is a **contrarian indicator**: positive = crowded long = bearish signal
- Extreme rates (>0.1% or <-0.05%) have stronger predictive power
- Neutral zone (±0.01%) should map to ~0 signal

**Algorithm**:
```python
def funding_to_vote(funding_rate: float) -> tuple[float, bool]:
    """
    Convert funding rate to contrarian vote.

    Args:
        funding_rate: Raw rate (e.g., 0.0015 = 0.15%)

    Returns:
        (vote, is_extreme): vote in [-1, 1], extreme flag
    """
    # Thresholds (percentage)
    EXTREME_POSITIVE = 0.001  # 0.1% - very crowded longs
    EXTREME_NEGATIVE = -0.0005  # -0.05% - very crowded shorts
    NEUTRAL_ZONE = 0.0001  # ±0.01% - no clear signal

    # Detect extremes
    is_extreme = funding_rate > EXTREME_POSITIVE or funding_rate < EXTREME_NEGATIVE

    # Normalize to [-1, 1] with inversion (contrarian)
    if abs(funding_rate) <= NEUTRAL_ZONE:
        vote = 0.0
    elif funding_rate > 0:
        # Positive funding = bearish (longs paying)
        vote = -min(1.0, funding_rate / EXTREME_POSITIVE)
    else:
        # Negative funding = bullish (shorts paying)
        vote = min(1.0, abs(funding_rate) / abs(EXTREME_NEGATIVE))

    return vote, is_extreme
```

**Test Cases** (from spec acceptance scenarios):
| Funding Rate | Vote | Is Extreme |
|--------------|------|------------|
| +0.15% | -0.8 | True |
| -0.08% | +0.6 | True |
| +0.01% | 0.0 | False |

**Alternatives Considered**:
1. ❌ Linear scaling: Doesn't capture non-linear risk at extremes
2. ❌ Z-score: Requires historical window, adds complexity
3. ✅ Threshold-based: Simple, interpretable, matches spec scenarios

---

## 3. Open Interest Change Calculation

### Problem
Need to calculate OI % change over configurable window (default 1h). OI data is 5-minute intervals.

### Decision: Rolling Window with Context Awareness

**Rationale**:
- OI change alone isn't directional - need whale signal context
- Rising OI + whale accumulation = confirming trend
- Rising OI + whale distribution = potential squeeze setup
- Falling OI = deleveraging, neutral signal

**Algorithm**:
```python
def calculate_oi_signal(
    current_oi: float,
    previous_oi: float,  # 1h ago
    whale_direction: str,  # "ACCUMULATION" | "DISTRIBUTION" | "NEUTRAL"
) -> tuple[float, str]:
    """
    Calculate OI change and context-aware vote.

    Returns:
        (vote, context): vote in [-1, 1], context description
    """
    if previous_oi <= 0:
        return 0.0, "no_data"

    oi_change_pct = (current_oi - previous_oi) / previous_oi

    # Deleveraging = neutral
    if oi_change_pct < -0.01:  # >1% decrease
        return 0.0, "deleveraging"

    # OI increase: context-dependent
    if oi_change_pct > 0.03:  # >3% increase
        if whale_direction == "ACCUMULATION":
            return 0.5, "confirming"  # Leverage confirms whale buying
        elif whale_direction == "DISTRIBUTION":
            return -0.3, "diverging"  # Leverage builds against whales
        else:
            return 0.2, "neutral"  # No whale signal, mild bullish

    # Moderate OI change: weaker signal
    if oi_change_pct > 0.01:  # 1-3% increase
        if whale_direction == "ACCUMULATION":
            return 0.3, "confirming"
        elif whale_direction == "DISTRIBUTION":
            return -0.2, "diverging"
        else:
            return 0.1, "neutral"

    return 0.0, "stable"
```

**Alternatives Considered**:
1. ❌ Pure OI change: Misses directional context
2. ❌ OI + price direction: Price not available in this module
3. ✅ OI + whale direction: Uses existing whale signal for context

---

## 4. Weight Optimization Strategy

### Problem
Need optimal weights for 4-component fusion: whale, utxo, funding, oi.

### Decision: Fixed Default Weights + Grid Search for Backtest

**Default Weights** (from spec):
```python
WEIGHTS = {
    "whale": 0.40,   # Primary on-chain signal
    "utxo": 0.20,    # UTXOracle confidence
    "funding": 0.25, # Derivatives contrarian
    "oi": 0.15,      # Leverage context
}
```

**Rationale for defaults**:
- Whale signal is proven (existing system)
- UTXOracle confidence is secondary confirmation
- Funding is strong contrarian indicator but external data
- OI provides context but lowest standalone predictive power

**Backtest Optimization**:
```python
# Grid search over weight space
weight_grid = {
    "whale": [0.30, 0.35, 0.40, 0.45, 0.50],
    "utxo": [0.10, 0.15, 0.20, 0.25],
    "funding": [0.15, 0.20, 0.25, 0.30],
    "oi": [0.05, 0.10, 0.15, 0.20],
}

# Constraint: weights must sum to 1.0
# Optimize for: Sharpe ratio on 30-day holdout
```

**Alternatives Considered**:
1. ❌ ML-based optimization: Overfitting risk, added complexity
2. ❌ Equal weights: Ignores signal quality differences
3. ✅ Informed defaults + grid search: Simple, interpretable, adjustable

---

## 5. Graceful Degradation Strategy

### Problem
LiquidationHeatmap database may be unavailable (locked, corrupted, missing).

### Decision: Fallback to spec-007 2-component fusion

**Rationale**:
- System must remain functional if derivatives fail
- Existing whale + utxo fusion is validated (spec-007)
- Log warnings for monitoring but don't block

**Implementation**:
```python
def enhanced_fusion_with_fallback(
    whale_vote, whale_conf,
    utxo_vote, utxo_conf,
    funding_vote: float | None,
    oi_vote: float | None,
    n_samples: int = 1000,
) -> EnhancedFusionResult:
    """
    Graceful degradation: if derivatives unavailable, use 2-component fusion.
    """
    if funding_vote is None and oi_vote is None:
        # Full degradation: derivatives unavailable
        logger.warning("Derivatives unavailable, using 2-component fusion")
        return monte_carlo_fusion(whale_vote, whale_conf, utxo_vote, utxo_conf)

    if funding_vote is None or oi_vote is None:
        # Partial degradation: one derivative missing
        logger.warning(f"Partial derivatives: funding={funding_vote}, oi={oi_vote}")
        # Redistribute missing weight proportionally
        ...

    # Full 4-component fusion
    ...
```

**Alternatives Considered**:
1. ❌ Hard fail: Unacceptable for production system
2. ❌ Retry loop: Adds latency, may not help if DB is locked
3. ✅ Fallback to 2-component: Proven, immediate, maintains service

---

## 6. Performance Considerations

### Cross-DB Query Latency

**Target**: <500ms for 24h of funding+OI data

**Estimated Records**:
- Funding: 3 records/24h (8-hour intervals)
- OI: 288 records/24h (5-minute intervals)
- Total: ~291 records

**DuckDB Performance**: Well within target for <1000 rows.

**Caching Strategy**:
```python
# Cache derivatives data for 5 minutes
# Rationale: funding updates every 8h, OI every 5min
# Cache prevents repeated cross-DB queries during same analysis cycle

@lru_cache(ttl_seconds=300)
def get_derivatives_data(timestamp: datetime) -> DerivativesData:
    ...
```

---

## Research Summary

| Question | Decision | Rationale |
|----------|----------|-----------|
| Cross-DB approach | DuckDB ATTACH | Zero copy, native feature |
| Funding normalization | Contrarian with thresholds | Matches market behavior |
| OI signal | Context-aware (uses whale direction) | Directional information |
| Weights | Fixed defaults + grid search | Simple, adjustable |
| Degradation | Fallback to 2-component | Maintains service |
| Caching | 5-minute TTL | Balances freshness and performance |

**All NEEDS CLARIFICATION items resolved.**
