# Implementation Plan: UTXO Lifecycle Engine

**Branch**: `017-utxo-lifecycle-engine` | **Date**: 2025-12-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/017-utxo-lifecycle-engine/spec.md`

## Summary

Implement UTXO lifecycle tracking to enable all Tier A metrics (MVRV, Realized Cap, NUPL, HODL Waves, Cointime). Track UTXO creation and spending with associated prices to build the foundation for advanced on-chain analytics.

**Technical Approach**: Track every new UTXO creation with block/price data, update records when spent, classify by age cohort, calculate aggregate metrics (Realized Cap, MVRV), and provide incremental sync capability.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: DuckDB, Pydantic, Bitcoin Core RPC
**Storage**: DuckDB `utxo_lifecycle` table (~5GB for 6-month MVP)
**Testing**: pytest with UTXO fixtures
**Target Platform**: Linux server
**Project Type**: Single project (extension of metrics system)
**Performance Goals**: <5 seconds per block processing
**Constraints**: <1GB/month storage growth, 6-month retention (MVP)
**Scale/Scope**: ~50M UTXOs for 6-month history

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Code Quality & Simplicity** | ✅ PASS | Phased approach, MVP first |
| **II. Test-First Discipline** | ✅ REQUIRES | TDD mandatory |
| **III. UX Consistency** | ✅ PASS | Follows existing API patterns |
| **IV. Performance Standards** | ✅ PASS | <5s/block, indexed queries |
| **V. Data Privacy & Security** | ✅ PASS | Local-only processing |

## Project Structure

### Documentation

```
specs/017-utxo-lifecycle-engine/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── tasks.md
```

### Source Code

```
scripts/
├── metrics/
│   ├── utxo_lifecycle.py      # NEW: Core lifecycle engine
│   ├── realized_metrics.py    # NEW: MVRV, NUPL, Realized Cap
│   └── hodl_waves.py          # NEW: Age distribution
├── daily_analysis.py          # MODIFY: Add lifecycle tracking
└── models/
    └── metrics_models.py      # MODIFY: Add lifecycle dataclasses

api/
└── main.py                    # MODIFY: Add lifecycle endpoints

tests/
├── test_utxo_lifecycle.py     # NEW
├── test_realized_metrics.py   # NEW
└── fixtures/
    └── utxo_fixtures.py       # NEW
```

## Phase 0: Research

### R1: Storage Strategy
**Decision**: DuckDB with 6-month retention + pruning
**Rationale**: ~5GB manageable, indexed queries, incremental sync

### R2: Sync Approach
**Decision**: Forward-only from last checkpoint
**Rationale**: Resume capability, no full rescan needed

### R3: Price Source
**Decision**: Local UTXOracle prices + mempool.space fallback
**Rationale**: Privacy-first, complete coverage

## Phase 1: Design

See [data-model.md](./data-model.md) for entities.

### Implementation Phases

**Phase 1 (MVP)**: 6-month history
- UTXOLifecycle tracking
- Basic age cohorts
- Realized Cap

**Phase 2**: Extended metrics
- MVRV, NUPL
- HODL Waves
- API endpoints

**Phase 3**: Optimization
- Pruning
- Caching
- Performance tuning

---

## Next Steps

Run `/speckit.tasks` to generate implementation tasks.
