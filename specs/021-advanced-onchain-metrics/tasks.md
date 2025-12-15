# Tasks: Advanced On-Chain Metrics (spec-021)

**Input**: Design documents from `/specs/021-advanced-onchain-metrics/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi.yaml

**Tests**: TDD approach - tests written BEFORE implementation per Constitution

**Organization**: Tasks grouped by metric priority (P0 → P1 → P2) for independent delivery

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger - complex algorithmic implementation
- **[Story]**: Which metric story this task belongs to (US1=URPD, US2=Supply P/L, etc.)

---

## Phase 0: Bootstrap (UTXO Lifecycle Data) 🚀 NEW

**Purpose**: Fast bootstrap of UTXO lifecycle data using chainstate dump + rpc-v3 hybrid approach.

**Architecture**: See `docs/ARCHITECTURE.md` section "UTXO Lifecycle Bootstrap Architecture (spec-021, PROPOSED)"

**Context**: Block-by-block sync via electrs estimated at 98+ days. This architecture reduces to ~50 minutes for current UTXOs, plus incremental rpc-v3 sync for spent UTXOs.

### Key Discoveries (2025-12-12)
- **electrs limitation**: prevout does NOT include `block_height` (creation height) - critical for SOPR
- **rpc-v3 advantage**: prevout DOES include `height` field - superior for SOPR calculation
- **mempool price API**: Has exchange prices from 2011 (`/api/v1/historical-price`)
- **Performance**: DuckDB COPY 2,970x faster than INSERT (712K vs 240 rows/sec)

### Two-Tier Architecture

| Tier | Data Source | Coverage | Use Case |
|------|-------------|----------|----------|
| 1 | bitcoin-utxo-dump | Current UTXOs only | URPD, Supply P&L, MVRV |
| 2 | rpc-v3 (incremental) | Spent UTXOs | SOPR, CDD, VDD |

### API Endpoints Used

| Endpoint | Source | Purpose | Example |
|----------|--------|---------|---------|
| `GET /api/v1/historical-price?currency=USD&timestamp={unix}` | mempool:8999 | Daily BTC/USD price | `curl "http://localhost:8999/api/v1/historical-price?currency=USD&timestamp=1310428800"` → `{"USD":16.45}` (Jul 2011) |
| `GET /block-height/{height}` | electrs:3001 | Block hash from height | `curl http://localhost:3001/block-height/920000` → block hash |
| `GET /block/{hash}` | electrs:3001 | Block metadata (timestamp) | Returns `{"timestamp": unix_ts, ...}` |

### Performance Target Details

**Tier 1 Bootstrap** (<50 min target):
- **Hardware**: NVMe SSD, 32GB RAM, 8-core CPU
- **Data volume**: ~180M UTXOs (~12GB chainstate)
- **Bottleneck**: DuckDB COPY at 712K rows/sec
- **Calculation**: 180M / 712K = 253 sec (~4 min) + overhead

### Bootstrap Tasks (TDD Compliant)

**Tests First (RED phase):**
- [x] T0001a Create `tests/test_bootstrap.py` with test fixtures
- [x] T0001b Add `test_build_price_table()` - verify 2011 data fetch
- [x] T0001c Add `test_build_block_heights()` - verify height→timestamp mapping
- [x] T0001d Add `test_import_chainstate()` - verify CSV→DuckDB COPY

**Implementation (GREEN phase):**
- [x] T0001 Create `scripts/bootstrap/` directory structure
- [x] T0002 Implement `build_price_table.py` (mempool `/api/v1/historical-price` → daily_prices table)
- [x] T0003 Implement `build_block_heights.py` (electrs `/block-height/{h}` + `/block/{hash}` → block_heights table)
- [x] T0004 Implement `import_chainstate.py` (bitcoin-utxo-dump CSV → DuckDB COPY)
- [x] T0005 Implement `bootstrap_utxo_lifecycle.py` (orchestrator script)
- [x] T0006 Test full Tier 1 bootstrap workflow (target: <50 min on NVMe SSD, 180M UTXOs) ✅ 12/12 tests pass
- [x] T0007 Implement incremental rpc-v3 sync for Tier 2 (spent UTXOs) ✅ 17/17 bootstrap tests pass

**Checkpoint**: UTXO lifecycle database populated, Tier 1 metrics (URPD, Supply P&L) operational

**Dependencies**:
- Bitcoin Core fully synced (chainstate available)
- `bitcoin-utxo-dump` installed (`go install github.com/in3rsha/bitcoin-utxo-dump@latest`)
- mempool.space backend running (port 8999)
- electrs HTTP API running (port 3001)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify dependencies and add dataclasses to metrics_models.py

- [x] T001 Verify utxo_lifecycle.py has required fields (creation_price_usd, btc_value, is_spent, spent_block, spent_timestamp) in scripts/metrics/utxo_lifecycle.py
- [x] T002 Verify cointime.py has calculate_coinblocks_destroyed() and BLOCKS_PER_DAY constant in scripts/metrics/cointime.py
- [x] T003 Add URPDBucket dataclass to scripts/models/metrics_models.py
- [x] T004 Add URPDResult dataclass to scripts/models/metrics_models.py
- [x] T005 Add SupplyProfitLossResult dataclass to scripts/models/metrics_models.py
- [x] T006 Add ReserveRiskResult dataclass to scripts/models/metrics_models.py
- [x] T007 Add SellSideRiskResult dataclass to scripts/models/metrics_models.py
- [x] T008 Add CoinDaysDestroyedResult dataclass to scripts/models/metrics_models.py

**Checkpoint**: All dataclasses added to metrics_models.py, dependencies verified

---

## Phase 2: Foundational (DuckDB Query Helpers)

**Purpose**: Create shared query utilities for all metrics

- [x] T009 Create get_current_block_height() helper in scripts/metrics/utils.py (or verify exists)
- [x] T010 Verify DuckDB connection pattern from existing metrics modules

**Checkpoint**: Foundation ready - metric implementation can begin

---

## Phase 3: User Story 1 - URPD (Priority: P0) 🎯 MVP

**Goal**: Calculate UTXO Realized Price Distribution for support/resistance detection

**Independent Test**: `uv run pytest tests/test_urpd.py -v` passes with fixture data

### Tests for URPD (TDD - Write First)

- [x] T011 [US1] Create test_urpd.py with test_calculate_urpd_basic() in tests/test_urpd.py
- [x] T012 [US1] Add test_urpd_bucket_aggregation() verifying GROUP BY logic in tests/test_urpd.py
- [x] T013 [US1] Add test_urpd_profit_loss_split() verifying supply above/below price in tests/test_urpd.py
- [x] T014 [US1] Add test_urpd_dominant_bucket() verifying max BTC bucket selection in tests/test_urpd.py
- [x] T015 [US1] Add test_urpd_empty_result() for edge case handling in tests/test_urpd.py

### Implementation for URPD

- [x] T016 [US1] Create scripts/metrics/urpd.py with module docstring and imports
- [x] T017 [US1] Implement calculate_urpd() function with DuckDB GROUP BY query in scripts/metrics/urpd.py
- [x] T018 [US1] Implement _classify_supply_by_price() helper for profit/loss split in scripts/metrics/urpd.py
- [x] T019 [US1] Implement _find_dominant_bucket() helper in scripts/metrics/urpd.py
- [x] T020 [US1] Add structured logging to urpd.py
- [x] T021 [US1] Run tests and verify all pass: `uv run pytest tests/test_urpd.py -v`

### API Endpoint for URPD

- [x] T022 [US1] Add GET /api/metrics/urpd endpoint to api/main.py
- [x] T023 [US1] Add Pydantic request model for URPD query params in api/main.py

**Checkpoint**: URPD metric fully functional - can identify support/resistance zones

---

## Phase 4: User Story 2 - Supply in Profit/Loss (Priority: P1)

**Goal**: Calculate supply breakdown by profit/loss status with STH/LTH segmentation

**Independent Test**: `uv run pytest tests/test_supply_profit_loss.py -v` passes

### Tests for Supply P/L (TDD - Write First)

- [x] T024 [US2] Create test_supply_profit_loss.py with test_calculate_basic() in tests/test_supply_profit_loss.py
- [x] T025 [US2] Add test_sth_lth_breakdown() verifying cohort split in tests/test_supply_profit_loss.py
- [x] T026 [US2] Add test_market_phase_classification() for phase thresholds in tests/test_supply_profit_loss.py
- [x] T027 [US2] Add test_signal_strength_calculation() in tests/test_supply_profit_loss.py

### Implementation for Supply P/L

- [x] T028 [US2] Create scripts/metrics/supply_profit_loss.py with module docstring and imports
- [x] T029 [US2] Implement calculate_supply_profit_loss() with DuckDB CASE WHEN query in scripts/metrics/supply_profit_loss.py
- [x] T030 [US2] Implement _calculate_sth_lth_breakdown() using hodl_waves cohort classification in scripts/metrics/supply_profit_loss.py
- [x] T031 [US2] Implement _classify_market_phase() helper for EUPHORIA/BULL/TRANSITION/CAPITULATION in scripts/metrics/supply_profit_loss.py
- [x] T032 [US2] Add structured logging to supply_profit_loss.py
- [x] T033 [US2] Run tests and verify all pass: `uv run pytest tests/test_supply_profit_loss.py -v`

### API Endpoint for Supply P/L

- [x] T034 [US2] Add GET /api/metrics/supply-profit-loss endpoint to api/main.py

**Checkpoint**: Supply P/L metric delivers market phase classification

---

## Phase 5: User Story 3 - Reserve Risk (Priority: P1)

**Goal**: Calculate long-term holder conviction metric using HODL Bank

**Independent Test**: `uv run pytest tests/test_reserve_risk.py -v` passes

### Tests for Reserve Risk (TDD - Write First)

- [x] T035 [US3] Create test_reserve_risk.py with test_calculate_basic() in tests/test_reserve_risk.py
- [x] T036 [US3] Add test_hodl_bank_calculation() verifying cumulative CDD integration in tests/test_reserve_risk.py
- [x] T037 [US3] Add test_signal_zone_thresholds() for zone classification in tests/test_reserve_risk.py
- [x] T038 [US3] Add test_reserve_risk_with_mvrv() verifying context fields in tests/test_reserve_risk.py

### Implementation for Reserve Risk

- [x] T039 [US3] Create scripts/metrics/reserve_risk.py with module docstring and imports
- [x] T040 [US3] Implement calculate_reserve_risk() using cointime cumulative_destroyed in scripts/metrics/reserve_risk.py
- [x] T041 [US3] Implement _calculate_hodl_bank() converting coinblocks to coindays in scripts/metrics/reserve_risk.py
- [x] T042 [US3] Implement _classify_signal_zone() for STRONG_BUY/ACCUMULATION/FAIR_VALUE/DISTRIBUTION in scripts/metrics/reserve_risk.py
- [x] T043 [US3] Add structured logging to reserve_risk.py
- [x] T044 [US3] Run tests and verify all pass: `uv run pytest tests/test_reserve_risk.py -v`

### API Endpoint for Reserve Risk

- [x] T045 [US3] Add GET /api/metrics/reserve-risk endpoint to api/main.py

**Checkpoint**: Reserve Risk metric identifies LTH conviction levels

---

## Phase 6: User Story 4 - Sell-side Risk Ratio (Priority: P1)

**Goal**: Calculate distribution pressure from realized profit relative to market cap

**Independent Test**: `uv run pytest tests/test_sell_side_risk.py -v` passes

### Tests for Sell-side Risk (TDD - Write First)

- [x] T046 [US4] Create test_sell_side_risk.py with test_calculate_basic() in tests/test_sell_side_risk.py
- [x] T047 [US4] Add test_realized_profit_calculation() verifying spent UTXO aggregation in tests/test_sell_side_risk.py
- [x] T048 [US4] Add test_rolling_window_filter() for 7d/30d/90d windows in tests/test_sell_side_risk.py
- [x] T049 [US4] Add test_signal_zone_classification() for LOW/NORMAL/ELEVATED/AGGRESSIVE in tests/test_sell_side_risk.py

### Implementation for Sell-side Risk

- [x] T050 [US4] Create scripts/metrics/sell_side_risk.py with module docstring and imports
- [x] T051 [US4] Implement calculate_sell_side_risk() with DuckDB date-filtered query in scripts/metrics/sell_side_risk.py
- [x] T052 [US4] Implement _calculate_realized_profit() for profit/loss aggregation in scripts/metrics/sell_side_risk.py
- [x] T053 [US4] Implement _classify_signal_zone() helper in scripts/metrics/sell_side_risk.py
- [x] T054 [US4] Add structured logging to sell_side_risk.py
- [x] T055 [US4] Run tests and verify all pass: `uv run pytest tests/test_sell_side_risk.py -v`

### API Endpoint for Sell-side Risk

- [x] T056 [US4] Add GET /api/metrics/sell-side-risk endpoint to api/main.py

**Checkpoint**: Sell-side Risk metric detects distribution pressure

---

## Phase 7: User Story 5 - CDD/VDD Metrics (Priority: P2)

**Goal**: Calculate Coindays Destroyed and Value Days Destroyed for old money tracking

**Independent Test**: `uv run pytest tests/test_coindays.py -v` passes

### Tests for CDD/VDD (TDD - Write First)

- [x] T057 [US5] Create test_cdd_vdd.py with test_calculate_cdd_basic() in tests/test_cdd_vdd.py
- [x] T058 [US5] Add test_vdd_calculation() verifying CDD × price in tests/test_cdd_vdd.py
- [x] T059 [US5] Add test_vdd_multiple() for 365d MA comparison in tests/test_cdd_vdd.py
- [x] T060 [US5] Add test_signal_zone_classification() for LOW_ACTIVITY/NORMAL/ELEVATED/SPIKE in tests/test_cdd_vdd.py
- [x] T061 [US5] Add test_max_single_day_detection() in tests/test_cdd_vdd.py

### Implementation for CDD/VDD

- [x] T062 [US5] Create scripts/metrics/cdd_vdd.py with module docstring and imports
- [x] T063 [US5] Implement calculate_cdd_vdd() adapting cointime's coinblocks in scripts/metrics/cdd_vdd.py
- [x] T064 [US5] Implement VDD calculation as CDD × price in scripts/metrics/cdd_vdd.py
- [x] T065 [US5] Implement VDD multiple calculation with 365d MA in scripts/metrics/cdd_vdd.py
- [x] T066 [US5] Implement max_single_day_cdd detection in scripts/metrics/cdd_vdd.py
- [x] T067 [US5] Implement _classify_signal_zone() helper in scripts/metrics/cdd_vdd.py
- [x] T068 [US5] Add structured logging to cdd_vdd.py
- [x] T069 [US5] Run tests and verify all pass: `uv run pytest tests/test_cdd_vdd.py -v`

### API Endpoint for CDD/VDD

- [x] T070 [US5] Add GET /api/metrics/cdd-vdd endpoint to api/main.py

**Checkpoint**: CDD/VDD metrics track old money movement

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Integration testing, documentation, performance validation

- [x] T071 Update specs/021-advanced-onchain-metrics/contracts/openapi.yaml with implemented endpoint schemas
- [x] T072 Run all spec-021 tests: `uv run pytest tests/test_urpd.py tests/test_supply_profit_loss.py tests/test_reserve_risk.py tests/test_sell_side_risk.py tests/test_cdd_vdd.py -v` ✅ 68 passed
- [x] T073 Verify URPD performance < 30 seconds with production data (requires UTXO DB) ✅ 0.68s achieved with 164M UTXOs
- [x] T074 Verify other metrics performance < 5 seconds each (requires UTXO DB) ✅ 0.15-0.23s achieved
- [x] T075 [P] Run ruff check and format on all new modules
- [x] T076 [P] Update docs/ARCHITECTURE.md with new metrics documentation
- [ ] T077 Run quickstart.md validation scenarios manually (requires UTXO DB)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Bootstrap (Phase 0)**: No dependencies - can start immediately ⚠️ BLOCKING for production data
- **Setup (Phase 1)**: No dependencies - can start immediately (uses fixture data)
- **Foundational (Phase 2)**: Depends on Setup completion
- **User Stories (Phase 3-7)**: All depend on Setup + Foundational + **Phase 0 for production data**
  - US1 (URPD): Independent - **MVP**
  - US2 (Supply P/L): Independent
  - US3 (Reserve Risk): Depends on cointime.py availability
  - US4 (Sell-side Risk): Independent
  - US5 (CDD/VDD): Depends on cointime.py availability
- **Polish (Phase 8)**: Depends on all user stories complete

### User Story Dependencies

| Story | Module | Dependencies | Can Parallelize With |
|-------|--------|--------------|---------------------|
| US1 | URPD | utxo_lifecycle | US2, US4 |
| US2 | Supply P/L | utxo_lifecycle, hodl_waves | US1, US4 |
| US3 | Reserve Risk | cointime, realized_metrics | US4, US5 |
| US4 | Sell-side Risk | utxo_lifecycle | US1, US2 |
| US5 | CDD/VDD | cointime | US3 |

### Parallel Opportunities

**Within Setup Phase:**
- T003-T008 (dataclasses) must be sequential - same file (metrics_models.py)

**Within Each User Story:**
- Test tasks must be sequential - same test file per story
- Implementation must be sequential (module → functions → logging)

**Across User Stories (MAIN PARALLELISM):**
- US1 + US2 + US4 can run in parallel (different modules, different test files)
- US3 + US5 can run in parallel (both use cointime, different modules)

**Polish Phase:**
- T074 + T075 can run in parallel (different files)

---

## Parallel Example: Cross-Story Parallelism

```bash
# CORRECT: Run entire user stories in parallel (different files):
# Agent A works on US1 (URPD):
#   tests/test_urpd.py + scripts/metrics/urpd.py

# Agent B works on US2 (Supply P/L) simultaneously:
#   tests/test_supply_profit_loss.py + scripts/metrics/supply_profit_loss.py

# Agent C works on US4 (Sell-side Risk) simultaneously:
#   tests/test_sell_side_risk.py + scripts/metrics/sell_side_risk.py

# WITHIN each story, tasks are SEQUENTIAL (same files):
# T011 → T012 → T013 → T014 → T015 (all in test_urpd.py)
# T016 → T017 → T018 → T019 → T020 → T021 (all in urpd.py)
```

---

## Implementation Strategy

### MVP First (URPD Only)

1. Complete Phase 1: Setup (dataclasses)
2. Complete Phase 2: Foundational (query helpers)
3. Complete Phase 3: User Story 1 (URPD)
4. **STOP and VALIDATE**: `uv run pytest tests/test_urpd.py -v`
5. Test API endpoint manually: `curl "http://localhost:8000/api/metrics/urpd?bucket_size=5000&current_price=100000"`
6. MVP delivered - URPD identifies support/resistance zones

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 (URPD) → Test independently → **MVP delivered**
3. US2 (Supply P/L) → Test independently → Market phase classification
4. US3 (Reserve Risk) → Test independently → LTH conviction
5. US4 (Sell-side Risk) → Test independently → Distribution detection
6. US5 (CDD/VDD) → Test independently → Old money tracking
7. Polish → Full integration

### Priority Order (Effort-Adjusted)

| Priority | Story | Effort | Cumulative |
|----------|-------|--------|------------|
| P0 | URPD | 4-6h | 6h |
| P1 | Supply P/L | 2h | 8h |
| P1 | Reserve Risk | 2-3h | 11h |
| P1 | Sell-side Risk | 2-3h | 14h |
| P2 | CDD/VDD | 3h | 17h |

---

## Notes

- [P] tasks = different files, no dependencies (T074, T075 only)
- No [E] markers - all formulas are well-defined DuckDB queries, not complex algorithms
- Test tasks do NOT have [P] - each story's tests edit the same test file
- TDD enforced: Tests written BEFORE implementation per Constitution
- Each metric independently testable after implementation
- Performance targets: URPD < 30s, others < 5s
- All metrics use DuckDB aggregation (NFR-001) - no Python loops
