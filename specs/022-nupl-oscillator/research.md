# Research: NUPL Oscillator (spec-022)

**Date**: 2025-12-16
**Status**: Complete

## Executive Summary

NUPL (Net Unrealized Profit/Loss) is a core on-chain metric already partially implemented in `scripts/metrics/realized_metrics.py`. This spec creates a dedicated oscillator module with zone classification and API endpoint for CheckOnChain dashboard integration.

## Technical Decisions

### D1: Existing Infrastructure Reuse

**Decision**: Reuse existing `calculate_nupl()` from `realized_metrics.py`

**Rationale**:
- Function already exists at `realized_metrics.py:127-148`
- Formula correctly implemented: `(market_cap - realized_cap) / market_cap`
- Tested via integration with `UTXOSetSnapshot.nupl` field

**Alternatives Rejected**:
- Duplicate calculation in new module (violates DRY)
- Move function to new module (breaks existing imports)

### D2: Zone Classification Thresholds

**Decision**: Use Glassnode-standard thresholds

| Zone | NUPL Range | Interpretation |
|------|------------|----------------|
| CAPITULATION | < 0 | Network underwater, extreme fear |
| HOPE_FEAR | 0 - 0.25 | Recovery phase |
| OPTIMISM | 0.25 - 0.5 | Bull market building |
| BELIEF | 0.5 - 0.75 | Strong conviction |
| EUPHORIA | > 0.75 | Extreme greed, cycle top signal |

**Rationale**:
- Matches Glassnode/CheckOnChain definitions (Evidence Grade A)
- Historically validated across 3+ Bitcoin cycles
- Consistent with existing `classify_mvrv_z_zone()` pattern

### D3: API Response Structure

**Decision**: Follow existing `/api/metrics/*` pattern

```python
@app.get("/api/metrics/nupl")
async def get_nupl() -> NUPLResponse:
    # Returns: nupl, zone, market_cap_usd, realized_cap_usd, timestamp
```

**Rationale**:
- Matches existing API patterns (`/api/metrics/wasserstein`, `/api/metrics/cointime`)
- Pydantic response models for type safety
- DuckDB connection reuse

## Dependencies Identified

### Data Sources
1. `realized_metrics.py:calculate_realized_cap()` - Realized Cap from `utxo_lifecycle_full` VIEW
2. `realized_metrics.py:calculate_market_cap()` - Market Cap = supply × price
3. `realized_metrics.py:get_total_unspent_supply()` - Circulating supply

### Infrastructure
- DuckDB connection (`utxo_lifecycle_full` VIEW must exist)
- FastAPI router (`api/main.py`)
- Pydantic models (`api/main.py` or `scripts/models/`)

## Implementation Architecture

```
scripts/metrics/nupl.py (NEW)
├── NUPLZone (Enum)           # Zone classification
├── classify_nupl_zone()      # Zone classifier
├── calculate_nupl_signal()   # Main orchestrator
└── NUPLResult (dataclass)    # Result container

scripts/models/metrics_models.py (EDIT)
└── NUPLResult                # Dataclass (move here for consistency)

api/main.py (EDIT)
└── GET /api/metrics/nupl     # New endpoint
```

## Testing Strategy

1. **Unit tests** (`tests/test_nupl.py`):
   - Zone boundary tests (< 0, 0-0.25, 0.25-0.5, 0.5-0.75, > 0.75)
   - Edge cases (market_cap = 0, realized_cap = 0)
   - NUPLResult dataclass validation

2. **Integration tests**:
   - API endpoint response validation
   - DuckDB data flow verification

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Zone threshold disagreement | Document source (Glassnode) |
| Test data unavailable | Use fixtures with known NUPL values |
| API endpoint naming collision | Check existing routes first |

## Effort Estimate

| Task | Lines of Code | Complexity |
|------|---------------|------------|
| NUPLResult dataclass | ~40 | Low |
| Zone classifier | ~20 | Low |
| API endpoint | ~50 | Low |
| Tests | ~80 | Low |
| **Total** | ~190 | **1-2 hours** |

## References

1. Glassnode NUPL: https://academy.glassnode.com/indicators/profit-loss-ratio/nupl
2. CheckOnChain dashboard: https://checkonchain.com/
3. Existing implementation: `scripts/metrics/realized_metrics.py:127-148`
