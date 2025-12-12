# Implementation Plan: Advanced On-Chain Metrics (spec-021)

**Branch**: `021-advanced-onchain-metrics` | **Date**: 2025-12-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/021-advanced-onchain-metrics/spec.md`

## Summary

Implement six professional-grade on-chain metrics for institutional Bitcoin analysis:
- **P0**: URPD (UTXO Realized Price Distribution) - Support/resistance detection
- **P1**: Supply in Profit/Loss - Market sentiment classification
- **P1**: Reserve Risk - Long-term holder conviction measurement
- **P1**: Sell-side Risk Ratio - Distribution pressure detection
- **P2**: CDD (Coindays Destroyed) - Old money movement tracking
- **P2**: VDD (Value Days Destroyed) - CDD weighted by price

All metrics build on existing `utxo_lifecycle` (spec-017), `cointime` (spec-018), and `realized_metrics` (spec-020) modules using DuckDB aggregation for performance.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: DuckDB, Pydantic, FastAPI (for API endpoints)
**Storage**: DuckDB (`utxo_lifecycle`, `utxo_snapshots` tables)
**Testing**: pytest with pytest-asyncio
**Target Platform**: Linux server (self-hosted)
**Project Type**: Single (backend library modules)
**Performance Goals**: URPD < 30s, other metrics < 5s each (DuckDB aggregation)
**Constraints**: Use DuckDB queries, not Python loops (NFR-001)
**Scale/Scope**: ~19.5M BTC supply, ~180M UTXOs (historical)

## ⚠️ Phase 0: Bootstrap Architecture (Added 2025-12-12)

> **BLOCKING DEPENDENCY**: Block-by-block sync via electrs estimated at 98+ days.
> This architecture reduces bootstrap to ~50 minutes for Tier 1 data.
> See `docs/ARCHITECTURE.md` section "UTXO Lifecycle Bootstrap Architecture (spec-021, PROPOSED)"

### Problem Statement

Original spec assumed `utxo_lifecycle` data already populated. Performance testing revealed:
- electrs block-by-block: ~180s/block → 920,000 blocks = **1,917 days**
- DuckDB INSERT bottleneck: 240 rows/sec → too slow for 180M UTXOs

### Solution: Two-Tier Architecture

| Tier | Data Source | Coverage | Metrics Enabled |
|------|-------------|----------|-----------------|
| **Tier 1** | bitcoin-utxo-dump (chainstate) | Current UTXOs only | URPD, Supply P&L, MVRV |
| **Tier 2** | rpc-v3 (incremental) | Spent UTXOs | SOPR, CDD, VDD |

### Key Discoveries

| Finding | Impact |
|---------|--------|
| electrs prevout lacks `block_height` | Cannot calculate SOPR via electrs |
| rpc-v3 prevout includes `height` | Superior for SOPR calculation |
| mempool price API from 2011 | 14+ years historical prices |
| DuckDB COPY vs INSERT | 2,970x speedup (712K vs 240 rows/sec) |

### Bootstrap Tasks (T0001-T0007)

| Task | Script | Purpose |
|------|--------|---------|
| T0002 | `build_price_table.py` | mempool API → daily_prices (2011-present) |
| T0003 | `build_block_heights.py` | electrs → block_heights table |
| T0004 | `import_chainstate.py` | bitcoin-utxo-dump CSV → DuckDB COPY |
| T0005 | `bootstrap_utxo_lifecycle.py` | Orchestrator script |

### Performance Targets

- **Tier 1 bootstrap**: ~50 min (180M UTXOs via chainstate dump + DuckDB COPY)
- **Tier 2 incremental**: ~15s/block via rpc-v3 (for new blocks only)

### Dependencies

| Dependency | Required For | Status |
|------------|--------------|--------|
| `bitcoin-utxo-dump` | T0004 | `go install github.com/in3rsha/bitcoin-utxo-dump@latest` |
| Bitcoin Core (synced) | chainstate access | ✅ Available |
| mempool.space backend | price API | ✅ Port 8999 |

## Constitution Check (Pre-Phase 0)

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Code Quality & Simplicity ✅ PASS
- **Boring Technology**: Uses Python + DuckDB (proven stack)
- **KISS**: Each metric is a standalone module with single purpose
- **YAGNI**: No premature abstractions - specific implementations
- **Dependencies**: Only existing project dependencies (DuckDB, Pydantic)
- **Readability**: Clear mathematical formulas documented in spec

### II. Test-First Discipline ✅ PASS (TDD Required)
- Tests will be written BEFORE implementation
- Each module requires: unit tests + integration tests
- Coverage target: 80%+ per module
- `tdd-guard` agent will validate compliance

### III. User Experience Consistency ✅ PASS
- **CLI**: Follows existing `-d YYYY/MM/DD` date patterns
- **API**: REST endpoints matching existing `/api/metrics/` pattern
- **Output**: JSON format consistent with existing metrics

### IV. Performance Standards ✅ PASS
- **URPD**: < 30 seconds (uses DuckDB GROUP BY aggregation)
- **Other metrics**: < 5 seconds each
- **Memory**: DuckDB handles aggregation (no Python collections)
- **Logging**: Structured JSON logging per Constitution

### V. Data Privacy & Security ✅ PASS
- **Local Processing**: All calculations from local DuckDB
- **No External APIs**: Uses existing `utxo_lifecycle` data
- **Pydantic Validation**: All inputs validated via models
- **No Sensitive Data**: Aggregate metrics only (no individual UTXOs exposed)

### Complexity Justification

No violations to justify - design follows existing patterns.

## Project Structure

### Documentation (this feature)

```
specs/021-advanced-onchain-metrics/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI schemas)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```
scripts/metrics/
├── urpd.py                    # [NEW] URPD calculation
├── supply_profit_loss.py      # [NEW] Supply in Profit/Loss
├── reserve_risk.py            # [NEW] Reserve Risk metric
├── sell_side_risk.py          # [NEW] Sell-side Risk Ratio
├── coindays.py                # [NEW] CDD + VDD metrics
├── realized_metrics.py        # [EXISTS] Realized Cap, MVRV, NUPL
├── utxo_lifecycle.py          # [EXISTS] Core UTXO data
├── cointime.py                # [EXISTS] Liveliness, coinblocks
└── hodl_waves.py              # [EXISTS] Age cohorts

scripts/models/
└── metrics_models.py          # [EXTEND] Add dataclasses for new metrics

tests/
├── test_urpd.py               # [NEW] URPD tests
├── test_supply_profit_loss.py # [NEW] Supply P/L tests
├── test_reserve_risk.py       # [NEW] Reserve Risk tests
├── test_sell_side_risk.py     # [NEW] Sell-side Risk tests
└── test_coindays.py           # [NEW] CDD/VDD tests

api/
└── main.py                    # [EXTEND] Add metric endpoints
```

**Structure Decision**: Single project structure - all modules in `scripts/metrics/` following existing patterns. No new directories needed.

## Dependencies Analysis

| Dependency | Module | Status | Notes |
|------------|--------|--------|-------|
| `utxo_lifecycle.py` | All metrics | ✅ Complete | Core UTXO table with `creation_price_usd`, `btc_value`, `is_spent`, `spent_block` |
| `cointime.py` | Reserve Risk | ✅ Complete | `calculate_coinblocks_destroyed()` |
| `realized_metrics.py` | Reserve Risk, MVRV integration | ✅ Complete | `calculate_mvrv()`, `get_total_unspent_supply()` |
| `hodl_waves.py` | Supply P/L (STH/LTH split) | ✅ Complete | Age cohort classification |
| DuckDB | All metrics | ✅ Complete | Aggregation queries |

## Risk Analysis

### Low Risk
- **URPD**: Straightforward `GROUP BY` query on price buckets
- **Supply in Profit/Loss**: Simple comparison to `current_price`
- **CDD/VDD**: Direct translation from `cointime.py` formulas

### Medium Risk
- **Reserve Risk**: Formula depends on cumulative HODL Bank (cointime integration)
  - *Mitigation*: Use existing `cumulative_destroyed` from cointime if available
- **Sell-side Risk**: Requires 30-day rolling window of spent UTXOs
  - *Mitigation*: DuckDB window functions handle rolling aggregations efficiently

### No Unknowns (All Context Available)
All formulas are documented in spec-021. All dependencies exist and have been verified.

## Implementation Approach

### Per-Metric Pattern

Each metric follows the same implementation pattern:

1. **Dataclass** in `metrics_models.py`
2. **Calculation function** in dedicated module
3. **Unit tests** with fixture data
4. **Integration test** with real DuckDB
5. **API endpoint** in `main.py`

### Code Reuse Strategy

| Existing Function | Used By |
|------------------|---------|
| `get_total_unspent_supply()` | Supply P/L, Reserve Risk |
| `calculate_mvrv()` | Reserve Risk (MVRV component) |
| `calculate_coinblocks_destroyed()` | Reserve Risk (HODL Bank) |
| `get_sth_lth_supply()` | Supply P/L (STH/LTH breakdown) |

## Phase Summary

**Phase 0 (Research)**: No unknowns - all formulas documented
**Phase 1 (Design)**: Generate data models, API contracts, quickstart guide
**Phase 2 (Tasks)**: TDD implementation of 6 metrics in priority order

## Constitution Check (Post-Design)

*Re-evaluation after Phase 1 design artifacts generated.*

### I. Code Quality & Simplicity ✅ PASS
- **6 dataclasses** defined in `data-model.md` - each single-purpose
- **No new abstractions** - follows existing `metrics_models.py` patterns
- **Clear formulas** - mathematical definitions documented with validation

### II. Test-First Discipline ✅ PASS
- **5 test files** planned in project structure
- **TDD pattern** documented in quickstart.md
- **Coverage target**: 80%+ confirmed in plan

### III. User Experience Consistency ✅ PASS
- **OpenAPI contract** generated in `contracts/openapi.yaml`
- **Endpoint pattern**: `/api/metrics/{metric-name}` - matches existing
- **Response format**: JSON with `to_dict()` methods

### IV. Performance Standards ✅ PASS
- **DuckDB aggregation** - no Python loops for data processing
- **SQL queries** documented in research.md and data-model.md
- **Performance targets**: URPD < 30s, others < 5s

### V. Data Privacy & Security ✅ PASS
- **Pydantic validation** - all dataclasses have `__post_init__()` validators
- **Local-only processing** - no external API calls
- **Aggregate data only** - no individual UTXO exposure

### Design Artifacts Generated

| Artifact | Status | Location |
|----------|--------|----------|
| `plan.md` | ✅ Complete | This file |
| `research.md` | ✅ Complete | `specs/021-advanced-onchain-metrics/research.md` |
| `data-model.md` | ✅ Complete | `specs/021-advanced-onchain-metrics/data-model.md` |
| `contracts/openapi.yaml` | ✅ Complete | `specs/021-advanced-onchain-metrics/contracts/openapi.yaml` |
| `quickstart.md` | ✅ Complete | `specs/021-advanced-onchain-metrics/quickstart.md` |
| Agent context | ✅ Updated | `CLAUDE.md` |

## Next Steps

Run `/speckit.tasks` to generate implementation tasks based on this plan.
