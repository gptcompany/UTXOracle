# Implementation Plan: On-Chain Metrics Core

**Branch**: `007-onchain-metrics-core` | **Date**: 2025-12-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/007-onchain-metrics-core/spec.md`

## Summary

Implement three foundational on-chain metrics that enhance UTXOracle's analytical capabilities:

1. **Monte Carlo Signal Fusion** (~150 LOC): Upgrade existing linear fusion (0.7×whale + 0.3×utxo) to bootstrap sampling with 95% confidence intervals
2. **Active Addresses** (~100 LOC): Count unique addresses per block/day from Bitcoin Core RPC
3. **TX Volume USD** (~80 LOC): Calculate total transaction volume using UTXOracle's on-chain price

All metrics integrate into existing `daily_analysis.py` flow with zero new external dependencies.

## Technical Context

**Language/Version**: Python 3.11 (matches existing codebase)
**Primary Dependencies**: None new (pure Python, optionally numpy if already installed)
**Storage**: DuckDB (extend existing `utxoracle_cache.db` schema)
**Testing**: pytest (existing setup in `tests/`)
**Target Platform**: Linux server (same as existing UTXOracle deployment)
**Project Type**: Single project (extend existing scripts/ and api/)
**Performance Goals**:
- Monte Carlo fusion: <100ms for 1000 samples
- TX Volume USD: <50ms additional overhead
- Active Addresses: <200ms per block (including RPC call)
**Constraints**:
- Zero new external dependencies (NFR-001)
- Backward compatible with linear fusion (NFR-002)
- Follow existing code patterns (NFR-003)
**Scale/Scope**:
- 1 block analyzed per 10-minute cron run
- 24h aggregation for daily metrics
- ~144 blocks/day processed

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Code Quality & Simplicity ✅

| Requirement | Compliance | Notes |
|-------------|------------|-------|
| KISS (boring tech) | ✅ PASS | Pure Python, no new frameworks |
| Single purpose modules | ✅ PASS | 3 separate files: `monte_carlo_fusion.py`, `active_addresses.py`, `tx_volume.py` |
| Minimize dependencies | ✅ PASS | Zero new dependencies, numpy optional |
| Readable code | ✅ PASS | Follows existing `daily_analysis.py` patterns |
| No premature abstraction | ✅ PASS | Direct implementation, no generic "metrics framework" |

### Principle II: Test-First Discipline ✅

| Requirement | Compliance | Notes |
|-------------|------------|-------|
| TDD Red-Green-Refactor | ✅ PLANNED | Tests written first for all 3 features |
| 80% coverage minimum | ✅ PLANNED | Target: ≥80% for new modules |
| Integration tests | ✅ PLANNED | `tests/test_onchain_metrics.py` |

### Principle III: User Experience Consistency ✅

| Requirement | Compliance | Notes |
|-------------|------------|-------|
| API standards | ✅ PASS | New endpoint `/api/metrics/latest` follows existing patterns |
| JSON output format | ✅ PASS | Pydantic models for response schema |
| Backward compatibility | ✅ PASS | Existing endpoints unchanged |

### Principle IV: Performance Standards ✅

| Requirement | Compliance | Notes |
|-------------|------------|-------|
| Execution time limits | ✅ PLANNED | <100ms Monte Carlo, <50ms TX Volume |
| Resource limits | ✅ PASS | No additional RPC calls beyond existing |
| Structured logging | ✅ PASS | Use existing logging patterns |

### Principle V: Data Privacy & Security ✅

| Requirement | Compliance | Notes |
|-------------|------------|-------|
| Local-first processing | ✅ PASS | All data from local Bitcoin Core/DuckDB |
| No external APIs | ✅ PASS | Uses UTXOracle price, not exchange API |
| Input validation | ✅ PLANNED | Pydantic models for type safety |

**GATE STATUS**: ✅ ALL PRINCIPLES SATISFIED - Proceed to Phase 0

## Project Structure

### Documentation (this feature)

```
specs/007-onchain-metrics-core/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (API schemas)
│   └── metrics_api.py   # Pydantic response models
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```
scripts/
├── daily_analysis.py           # MODIFY: Add metrics calculation to main flow
├── metrics/                    # NEW: Metrics module directory
│   ├── __init__.py
│   ├── monte_carlo_fusion.py   # NEW: Bootstrap sampling logic
│   ├── active_addresses.py     # NEW: Address counting logic
│   └── tx_volume.py            # NEW: Volume calculation logic
└── models/
    └── metrics_models.py       # NEW: Dataclass models (or extend existing)

api/
└── main.py                     # MODIFY: Add /api/metrics/latest endpoint

tests/
├── test_onchain_metrics.py     # NEW: Unit tests for all 3 metrics
└── integration/
    └── test_metrics_integration.py  # NEW: Integration with daily_analysis.py
```

**Structure Decision**: Extend existing `scripts/` structure with new `metrics/` subdirectory. Follows existing pattern where `scripts/models/` contains dataclasses and `scripts/*.py` contains logic modules.

## Complexity Tracking

*No constitution violations requiring justification.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |

## Implementation Phases

### Phase 0: Research (Complete in plan generation)
- Monte Carlo bootstrap sampling best practices
- DuckDB schema extension patterns
- Active address counting methodology (match Blockstream)

### Phase 1: Design
- Data models (Pydantic/dataclass)
- API contracts (OpenAPI schema for `/api/metrics/latest`)
- DuckDB schema migration

### Phase 2: Implementation (via /speckit.tasks)
1. TX Volume USD (easiest first)
2. Active Addresses
3. Monte Carlo Fusion (most complex last)
4. API endpoint
5. Integration tests
