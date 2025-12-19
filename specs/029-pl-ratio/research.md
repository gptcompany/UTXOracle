# Research: P/L Ratio (Dominance)

**Spec**: spec-029 | **Date**: 2025-12-19

## Overview

This is a "Quick Win" implementation with minimal research required. The P/L Ratio metric is a direct derivative of spec-028 (Net Realized P/L), reusing existing infrastructure.

## Research Tasks

### 1. Dependency: spec-028 Net Realized P/L

**Status**: ✅ Complete

**Findings**:
- `scripts/metrics/net_realized_pnl.py` provides `calculate_net_realized_pnl()` function
- Returns `NetRealizedPnLResult` with `realized_profit_usd` and `realized_loss_usd`
- Already calculates `profit_loss_ratio` (profit / loss)
- Uses `utxo_lifecycle_full` VIEW from spec-017

**Decision**: Reuse spec-028 result directly rather than recalculating from VIEW

**Rationale**:
- Avoids duplicate queries to `utxo_lifecycle_full`
- Ensures consistency with Net Realized P/L metric
- Simpler implementation

**Alternatives Considered**:
1. Direct VIEW query - rejected (duplicate work, inconsistent with spec-028)
2. New database column - rejected (YAGNI, can compute on-the-fly)

### 2. P/L Dominance Formula

**Status**: ✅ Complete

**Findings**:
The spec defines two formulas:
```
P/L Ratio = Realized Profit / Realized Loss
P/L Dominance = (Profit - Loss) / (Profit + Loss)  # Normalized -1 to +1
```

**Decision**: Implement both metrics as complementary views

**Rationale**:
- P/L Ratio: intuitive (>1 = profit dominant, <1 = loss dominant)
- P/L Dominance: normalized (-1 to +1) for easier charting and comparison

**Edge Cases**:
- Loss = 0: Return 1e9 for ratio (JSON-safe infinity)
- Profit + Loss = 0: Return 0.0 for dominance (neutral)
- Both = 0: Return 0.0 for both (no activity)

### 3. Zone Classification

**Status**: ✅ Complete

**Findings** (from spec):

| Zone | P/L Ratio | Dominance | Interpretation |
|------|-----------|-----------|----------------|
| EXTREME_PROFIT | > 5.0 | > 0.67 | Euphoria, potential top |
| PROFIT | 1.5 - 5.0 | 0.2 - 0.67 | Healthy bull market |
| NEUTRAL | 0.67 - 1.5 | -0.2 - 0.2 | Equilibrium |
| LOSS | 0.2 - 0.67 | -0.67 - -0.2 | Bear market |
| EXTREME_LOSS | < 0.2 | < -0.67 | Capitulation, potential bottom |

**Decision**: Implement as Enum with threshold-based classification

**Rationale**:
- Consistent with existing pattern (e.g., `signal` in NetRealizedPnLResult)
- Type-safe zone classification
- Easy to adjust thresholds if needed

### 4. API Design

**Status**: ✅ Complete

**Findings** (from spec):
```
GET /api/metrics/pl-ratio?window=24h
GET /api/metrics/pl-ratio/history?days=30
```

**Decision**: Follow existing API patterns from `api/main.py`

**Rationale**:
- Consistent with other metric endpoints
- Uses Query parameters for filtering
- Pydantic response models for validation

**Pattern Reference**: Similar to how spec-028 would be implemented if it had API endpoints.

## Dependencies Summary

| Dependency | Status | Version/Source |
|------------|--------|----------------|
| spec-028 Net Realized P/L | ✅ Complete | `scripts/metrics/net_realized_pnl.py` |
| spec-017 UTXO Lifecycle | ✅ Complete | `utxo_lifecycle_full` VIEW |
| DuckDB | ✅ Available | Existing dependency |
| pytest | ✅ Available | Existing test infrastructure |

## Implementation Decisions

1. **Reuse over Recompute**: Call spec-028's `calculate_net_realized_pnl()` rather than querying VIEW directly
2. **Dual Metrics**: Provide both ratio and dominance for flexibility
3. **Enum Zones**: Type-safe zone classification with clear thresholds
4. **Minimal API**: Two endpoints (current + history) matching existing patterns

## NEEDS CLARIFICATION

*None - all technical decisions resolved.*
