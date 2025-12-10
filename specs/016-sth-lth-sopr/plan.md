# Implementation Plan: STH/LTH SOPR Implementation

**Branch**: `016-sth-lth-sopr` | **Date**: 2025-12-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/016-sth-lth-sopr/spec.md`

## Summary

Implement SOPR (Spent Output Profit Ratio) calculation with STH/LTH cohort splitting to add the most empirically validated on-chain metric (82.44% accuracy - Omole & Enke 2024) to the UTXOracle fusion engine.

**Technical Approach**: Calculate SOPR from spent outputs in processed blocks by comparing spend price vs creation price, classify outputs by holder duration (STH < 155 days, LTH >= 155 days), detect capitulation/distribution patterns, and integrate as 9th fusion component.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: DuckDB, Pydantic, Bitcoin Core RPC (existing)
**Storage**: DuckDB `utxoracle_prices` table for historical prices
**Testing**: pytest with fixtures for SOPR calculations
**Target Platform**: Linux server (existing UTXOracle infrastructure)
**Project Type**: Single project (extension of existing metrics system)
**Performance Goals**: <100ms per block SOPR calculation
**Constraints**: <500MB RAM, no external price APIs for core calculation
**Scale/Scope**: Process ~3000 spent outputs per block, 6 months lookback

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Code Quality & Simplicity** | ✅ PASS | Single-purpose module, extends existing patterns |
| **II. Test-First Discipline** | ✅ REQUIRES | RED-GREEN-REFACTOR mandatory, 80%+ coverage |
| **III. UX Consistency** | ✅ PASS | New API endpoint follows existing patterns |
| **IV. Performance Standards** | ✅ PASS | <100ms/block target, aligns with spec-009 |
| **V. Data Privacy & Security** | ✅ PASS | Local-only price lookup, no external APIs |

**No violations requiring justification.**

## Project Structure

### Documentation (this feature)

```
specs/016-sth-lth-sopr/
├── plan.md              # This file
├── research.md          # Phase 0: Price lookup strategies
├── data-model.md        # Phase 1: SOPR entities
├── quickstart.md        # Phase 1: Quick implementation guide
├── contracts/           # Phase 1: API contracts
│   └── sopr-api.yaml    # OpenAPI spec for /api/metrics/sopr
└── tasks.md             # Phase 2: Implementation tasks
```

### Source Code (repository root)

```
scripts/
├── metrics/
│   ├── sopr.py              # NEW: Core SOPR calculation
│   └── monte_carlo_fusion.py # MODIFY: Add 9th component
├── daily_analysis.py        # MODIFY: Add SOPR to pipeline
└── models/
    └── metrics_models.py    # MODIFY: Add SOPR dataclasses

api/
└── main.py                  # MODIFY: Add /api/metrics/sopr

tests/
├── test_sopr.py             # NEW: SOPR unit tests
└── fixtures/
    └── sopr_fixtures.py     # NEW: Test data
```

**Structure Decision**: Extends existing `scripts/metrics/` pattern. New module `sopr.py` follows same structure as `wasserstein.py` from spec-010.

## Complexity Tracking

*No violations to justify - design follows existing patterns.*

---

## Phase 0: Research

### R1: Historical Price Lookup Strategy

**Question**: How to efficiently retrieve creation prices for spent outputs?

**Decision**: Query existing `utxoracle_prices` table by block height

**Rationale**:
- UTXOracle already stores historical prices from 672 days of analysis
- Block height → price lookup is O(1) with index
- Fallback to mempool.space API only if local data unavailable

**Alternatives Rejected**:
- External API for all prices: Violates Principle V (privacy)
- Re-calculate prices on demand: Too slow (>10s per block)

### R2: UTXO Age Calculation

**Question**: How to determine UTXO age without full UTXO set tracking?

**Decision**: Extract creation block from transaction input reference (prevout)

**Rationale**:
- Bitcoin Core RPC provides `vin[].txid` and `vin[].vout`
- Query original transaction to get creation block
- Cache frequently accessed transactions

**Alternatives Rejected**:
- Full UTXO set (spec-017): Requires 4-6 weeks, this is MVP
- Heuristics only: Less accurate than direct lookup

### R3: STH/LTH Threshold

**Question**: What threshold separates short-term from long-term holders?

**Decision**: 155 days (Glassnode standard)

**Rationale**:
- Industry standard used by Glassnode, CryptoQuant
- Approximately 5 months, aligns with market cycle research
- Configurable via environment variable

---

## Phase 1: Design

### Data Model

See [data-model.md](./data-model.md) for full entity definitions.

**Core Entities**:
- `SpentOutputSOPR`: Individual output SOPR calculation
- `BlockSOPR`: Aggregated block SOPR with STH/LTH split
- `SOPRWindow`: Rolling window for pattern detection
- `SOPRSignal`: Trading signal from SOPR patterns

### API Contracts

See [contracts/sopr-api.yaml](./contracts/sopr-api.yaml) for OpenAPI spec.

**Endpoints**:
- `GET /api/metrics/sopr/current` - Latest block SOPR
- `GET /api/metrics/sopr/history` - Historical SOPR data
- `GET /api/metrics/sopr/signals` - Active SOPR signals

### Implementation Order

1. **Price Lookup** (~50 LOC) - Query historical prices
2. **Output SOPR** (~40 LOC) - Individual output calculation
3. **Block SOPR** (~60 LOC) - Aggregate with STH/LTH split
4. **Signal Detection** (~50 LOC) - Pattern recognition
5. **Fusion Integration** (~30 LOC) - 9th component
6. **API Endpoint** (~30 LOC) - REST interface

### Quickstart

See [quickstart.md](./quickstart.md) for implementation guide.

---

## Next Steps

Run `/speckit.tasks` to generate Phase 2 implementation tasks.
