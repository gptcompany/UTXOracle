# Implementation Plan: Mining Economics (Hash Ribbons + Mining Pulse)

**Branch**: `030-hash-ribbons` | **Date**: 2025-12-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/030-hash-ribbons/spec.md`

## Summary

Implement mining stress indicators combining hashrate moving averages (Hash Ribbons) and block interval analysis (Mining Pulse). Hash Ribbons provides miner capitulation/recovery signals from 30d/60d MA crossovers, while Mining Pulse offers real-time hashrate change detection via block interval deviations. This dual approach balances historical trend analysis (external API) with instant network status (RPC only).

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: FastAPI, httpx (for external API), dataclasses
**Storage**: N/A (stateless calculation, external data cache optional)
**Testing**: pytest with TDD (`tdd-guard` enforcement)
**Target Platform**: Linux server (Bitcoin Core node)
**Project Type**: Single project (scripts/metrics module)
**Performance Goals**: API response <500ms, hashrate fetch cached 5min
**Constraints**: Mining Pulse MUST work RPC-only (no external dependencies)
**Scale/Scope**: Single metric module, 3 API endpoints

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. KISS/YAGNI | ✅ PASS | Minimal implementation, no abstractions |
| II. TDD | ✅ PASS | Tests first via `pytest-test-generator` |
| III. UX Consistency | ✅ PASS | Standard API patterns from existing metrics |
| IV. Performance | ✅ PASS | Caching for external API, RPC minimal calls |
| V. Privacy | ⚠️ WATCH | Hash Ribbons uses external API - acceptable per spec |

**Privacy Note**: Hash Ribbons requires external hashrate data (mempool.space API). This is acceptable because:
1. Only fetches aggregate network data (not user-specific)
2. Mining Pulse works 100% locally as fallback
3. External API is opt-in (can disable hash-ribbons, keep mining-pulse)

### Post-Design Check

| Principle | Status | Verification |
|-----------|--------|--------------|
| I. KISS/YAGNI | ✅ PASS | 3 models, 1 enum, 4 endpoints - minimal design |
| II. TDD | ✅ PASS | Test structure defined in data-model.md |
| III. UX Consistency | ✅ PASS | OpenAPI contract follows existing patterns |
| IV. Performance | ✅ PASS | 5-min cache, 144-block window documented |
| V. Privacy | ✅ PASS | Mining Pulse works RPC-only, ribbons opt-in |

**Design Validation**:
- No over-engineering detected
- File count: 3 new files (calculator, fetcher, tests)
- Model complexity: dataclass with validation (existing pattern)
- API surface: 4 endpoints (3 metrics + 1 history)

## Project Structure

### Documentation (this feature)

```
specs/030-hash-ribbons/
├── plan.md              # This file
├── research.md          # Phase 0: API patterns, caching strategy
├── data-model.md        # Phase 1: HashRibbonsResult, MiningPulseResult
├── quickstart.md        # Phase 1: Usage examples
├── contracts/           # Phase 1: OpenAPI endpoints
└── tasks.md             # Phase 2: Implementation tasks
```

### Source Code (repository root)

```
scripts/
├── metrics/
│   └── mining_economics.py     # Hash Ribbons + Mining Pulse calculator
├── data/
│   └── hashrate_fetcher.py     # External API client (optional)
└── models/
    └── metrics_models.py       # Add: HashRibbonsResult, MiningPulseResult, MiningPulseZone

api/
└── main.py                     # Add 3 endpoints

tests/
└── test_mining_economics.py    # TDD tests
```

**Structure Decision**: Single project (scripts/metrics module) following existing patterns from binary_cdd.py, exchange_netflow.py.

## Complexity Tracking

*No violations - implementation follows KISS/YAGNI principles.*

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| External API | mempool.space only | Proven, reliable, matches existing infra |
| Caching | Simple 5-min TTL | Avoids rate limiting, hashrate changes slowly |
| Fallback | None for Hash Ribbons | External data required; Mining Pulse works independently |
