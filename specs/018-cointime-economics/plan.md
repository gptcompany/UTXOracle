# Implementation Plan: Cointime Economics Framework

**Branch**: `018-cointime-economics` | **Date**: 2025-12-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/018-cointime-economics/spec.md`

## Summary

Implement ARK Invest + Glassnode's Cointime Economics framework: Liveliness, Vaultedness, Active/Vaulted Supply, True Market Mean, and AVIV ratio. This provides the most academically rigorous on-chain analysis framework with no heuristic assumptions.

**Technical Approach**: Calculate coinblocks created/destroyed from UTXO lifecycle data, derive Liveliness/Vaultedness ratios, compute supply splits, and calculate AVIV as superior MVRV.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: DuckDB, spec-017 UTXO Lifecycle
**Storage**: DuckDB `cointime_metrics` table
**Testing**: pytest
**Target Platform**: Linux server
**Project Type**: Single project (extends spec-017)
**Performance Goals**: <1s per block calculation
**Constraints**: Requires spec-017 complete

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Code Quality & Simplicity** | ✅ PASS | Pure mathematical framework |
| **II. Test-First Discipline** | ✅ REQUIRES | TDD mandatory |
| **III. UX Consistency** | ✅ PASS | Follows API patterns |
| **IV. Performance Standards** | ✅ PASS | <1s/block |
| **V. Data Privacy & Security** | ✅ PASS | Local-only |

## Project Structure

### Documentation

```
specs/018-cointime-economics/
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
│   ├── cointime.py            # NEW: Cointime calculations
│   └── monte_carlo_fusion.py  # MODIFY: Add cointime vote
└── models/
    └── metrics_models.py      # MODIFY: Add Cointime dataclasses

api/
└── main.py                    # MODIFY: Add /api/metrics/cointime

tests/
└── test_cointime.py           # NEW
```

## Phase 0: Research

### R1: Coinblocks Formula
**Decision**: Standard ARK/Glassnode formula
- Created: BTC × 1 (per block held)
- Destroyed: BTC × blocks_since_creation (when spent)

### R2: Liveliness Calculation
**Decision**: Cumulative ratio
- Liveliness = Σ(Destroyed) / Σ(Created)
- Range: 0 to 1

## Phase 1: Design

See [data-model.md](./data-model.md) for entities.

### Implementation Order

1. Coinblocks calculation
2. Liveliness/Vaultedness
3. Supply split
4. True Market Mean
5. AVIV ratio
6. Fusion integration

---

## Next Steps

Run `/speckit.tasks` to generate implementation tasks.
