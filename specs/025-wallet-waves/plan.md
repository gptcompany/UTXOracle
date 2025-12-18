# Implementation Plan: Wallet Waves & Absorption Rates

**Branch**: `025-wallet-waves` | **Date**: 2025-12-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/025-wallet-waves/spec.md`

## Summary

Implement supply distribution analysis across wallet size bands (shrimp to whale) and absorption rate tracking. Uses existing `utxo_lifecycle_full` VIEW which already contains `address` column for balance aggregation. Two calculators: WalletWavesCalculator (distribution) and AbsorptionRatesCalculator (time-series delta).

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: DuckDB (existing), Pydantic (existing), FastAPI (existing)
**Storage**: DuckDB `utxo_lifecycle_full` VIEW (address column confirmed)
**Testing**: pytest with TDD (RED → GREEN → REFACTOR)
**Target Platform**: Linux server
**Project Type**: single
**Performance Goals**: <5 seconds for wallet wave calculation (aggregate query)
**Constraints**: <500MB RAM for aggregation, leverage existing indexes
**Scale/Scope**: ~150M UTXOs, ~50M unique addresses (estimated)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. KISS/YAGNI | ✅ PASS | Reuses existing VIEW, no new tables. Simple SQL aggregation. |
| II. TDD | ✅ PASS | Tests defined before implementation (T007-T008, T012-T013 RED phase) |
| III. UX Consistency | ✅ PASS | Follows existing API patterns (GET /api/metrics/X) |
| IV. Performance | ✅ PASS | DuckDB optimized for OLAP aggregation |
| V. Privacy | ✅ PASS | Local processing only, no external APIs |

## Project Structure

### Documentation (this feature)

```
specs/025-wallet-waves/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (api.yaml)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```
scripts/
├── metrics/
│   ├── wallet_waves.py        # NEW: Distribution calculator
│   └── absorption_rates.py    # NEW: Absorption rate calculator
└── models/
    └── metrics_models.py      # ADD: WalletBand enum, WalletWavesResult, AbsorptionRatesResult

api/
└── main.py                    # ADD: 3 endpoints

tests/
├── test_wallet_waves.py       # NEW: TDD tests
└── test_absorption_rates.py   # NEW: TDD tests
```

**Structure Decision**: Single project (scripts/metrics/ + api/ + tests/)

## Complexity Tracking

*No violations - straightforward aggregation on existing data.*
