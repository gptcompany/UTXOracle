# Tasks: mempool.space Integration & Codebase Refactor

**Input**: Design documents from `/media/sam/1TB/UTXOracle/specs/003-mempool-integration-refactor/`
**Prerequisites**: plan.md ✅, spec.md ✅

**Tests**: Tests ARE REQUIRED per project constitution (TDD-first discipline)

**Organization**: Tasks are grouped by implementation phase to enable sequential execution with clear checkpoints.

## Format: `[ID] [P?] [Phase] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Phase]**: Which phase this task belongs to (e.g., Infra, Refactor, Integration, API, Cleanup)
- Include exact file paths in descriptions

## Path Conventions
- **Production**: `/media/sam/2TB-NVMe/prod/apps/` for deployed applications
- **Development**: `/media/sam/1TB/UTXOracle/` for source code
- **Tests**: `tests/` at repository root
- **Scripts**: `scripts/` for automation

---

## Phase 1: Infrastructure Setup 🏗️

**Purpose**: Deploy self-hosted mempool.space + electrs stack on NVMe

**Time Estimate**: 4-6 hours (including 3-4 hour electrs sync on NVMe)

- [ ] T001 Verify prerequisites: Bitcoin Core synced, Docker installed, NVMe has 50GB free
- [ ] T002 Review setup script: `scripts/setup_full_mempool_stack.sh` (already created)
- [ ] T003 Run setup script: `bash scripts/setup_full_mempool_stack.sh` (creates directory structure + docker-compose.yml)
- [ ] T004 Verify configuration: Check `/media/sam/2TB-NVMe/prod/apps/mempool-stack/.env` has correct Bitcoin RPC credentials
- [ ] T005 Start Docker stack: `cd /media/sam/2TB-NVMe/prod/apps/mempool-stack && docker-compose up -d`
- [ ] T006 Monitor electrs sync: `docker-compose logs -f electrs` (wait for "finished full compaction" - 3-4 hours on NVMe)
- [ ] T007 Verify all containers healthy: `docker-compose ps` (all should show "Up" and "(healthy)")
- [ ] T008 [P] Test electrs connectivity: `curl -s http://localhost:50001 | head -5` (should respond)
- [ ] T009 [P] Test backend API: `curl http://localhost:8999/api/blocks/tip/height` (should return current block height)
- [ ] T010 [P] Test frontend: `curl -s http://localhost:8080 | grep mempool` (should return HTML)
- [ ] T011 [P] Test exchange prices: `curl http://localhost:8999/api/v1/prices | jq .USD` (should return price)
- [ ] T012 Document infrastructure status: Create `INFRASTRUCTURE_STATUS.md` with container IDs, ports, disk usage

**Checkpoint**: Infrastructure ready - mempool.space stack fully operational

---

## Phase 2: Algorithm Refactor 🔬

**Purpose**: Refactor UTXOracle.py into reusable library with clean API

**Time Estimate**: 2-3 days

### Tests for Algorithm Refactor (TDD: Write FIRST, ensure FAIL)

- [ ] T013 [P] [Refactor] Write failing test for histogram bins generation in `tests/test_utxoracle_library.py` (test_histogram_bins_count_is_2400)
- [ ] T014 [P] [Refactor] Write failing test for bin index calculation in `tests/test_utxoracle_library.py` (test_get_bin_index_for_various_amounts)
- [ ] T015 [P] [Refactor] Write failing test for round amount filtering in `tests/test_utxoracle_library.py` (test_remove_round_amounts)
- [ ] T016 [P] [Refactor] Write failing test for stencil construction in `tests/test_utxoracle_library.py` (test_build_stencils)
- [ ] T017 [P] [Refactor] Write failing test for price estimation in `tests/test_utxoracle_library.py` (test_estimate_price_from_histogram)
- [ ] T018 [P] [Refactor] Write failing test for full calculation in `tests/test_utxoracle_library.py` (test_calculate_price_for_transactions)

### Implementation

- [ ] T019 [Refactor] Create `UTXOracle_library.py` with `UTXOracleCalculator` class skeleton (empty methods)
- [ ] T020 [Refactor] Implement `_build_histogram_bins()` method (copy from UTXOracle.py Step 5, lines 502-518)
- [ ] T021 [Refactor] Implement `_get_bin_index(amount_btc)` method (copy from UTXOracle.py, lines 521-537)
- [ ] T022 [Refactor] Implement `_remove_round_amounts(histogram)` method (copy from UTXOracle.py Step 7)
- [ ] T023 [Refactor] Implement `_build_smooth_stencil()` method (copy from UTXOracle.py Step 8)
- [ ] T024 [Refactor] Implement `_build_spike_stencil()` method (copy from UTXOracle.py Step 8)
- [ ] T025 [Refactor] Implement `_estimate_price(histogram)` method (copy from UTXOracle.py Steps 9-11)
- [ ] T026 [Refactor] Implement `calculate_price_for_transactions(txs)` public method (orchestrates all steps)
- [ ] T027 [Refactor] Add type hints to all methods (Python 3.8+ style)
- [ ] T028 [Refactor] Add docstrings to all public methods (Google style)
- [ ] T029 [Refactor] Verify T013-T018 tests now PASS (GREEN)

### Backward Compatibility

- [ ] T030 [Refactor] Modify `UTXOracle.py` to import `UTXOracleCalculator` from library
- [ ] T031 [Refactor] Replace Steps 5-11 code in `UTXOracle.py` with library calls
- [ ] T032 [Refactor] Test CLI still works: `python3 UTXOracle.py -rb` (output should be identical)
- [ ] T033 [Refactor] Test with specific date: `python3 UTXOracle.py -d 2025/10/23` (verify price matches historical)

**Checkpoint**: UTXOracle algorithm available as importable library, CLI backward compatible

---

## Phase 3: Integration Service 🔗

**Purpose**: Create cron job that compares on-chain vs exchange prices, saves to DuckDB

**Time Estimate**: 2 days

### Tests for Integration (TDD: Write FIRST, ensure FAIL)

- [ ] T034 [P] [Integration] Write failing test for mempool price fetch in `tests/test_daily_analysis.py` (test_fetch_mempool_price_returns_float)
- [ ] T035 [P] [Integration] Write failing test for UTXOracle calculation in `tests/test_daily_analysis.py` (test_calculate_utxoracle_price)
- [ ] T036 [P] [Integration] Write failing test for price comparison in `tests/test_daily_analysis.py` (test_compare_prices_computes_difference)
- [ ] T037 [P] [Integration] Write failing test for DuckDB save in `tests/test_daily_analysis.py` (test_save_to_duckdb)

### Implementation

- [ ] T038 [Integration] Create `scripts/daily_analysis.py` with main() skeleton
- [ ] T039 [Integration] Implement `fetch_mempool_price()` function (GET http://localhost:8999/api/v1/prices)
- [ ] T040 [Integration] Implement `calculate_utxoracle_price()` function (uses UTXOracleCalculator library)
- [ ] T041 [Integration] Implement `compare_prices(utx_price, mem_price)` function (computes diff_amount, diff_percent)
- [ ] T042 [Integration] Implement `init_database(db_file)` function (creates DuckDB schema if not exists)
- [ ] T043 [Integration] Implement `save_to_duckdb(data, db_file)` function (INSERT INTO prices)
- [ ] T044 [Integration] Add error handling: retry 3× with exponential backoff for network errors
- [ ] T045 [Integration] Add logging: structured logs to `/media/sam/2TB-NVMe/prod/apps/utxoracle/logs/daily_analysis.log`
- [ ] T046 [Integration] Add CLI flags: `--init-db`, `--dry-run`, `--verbose`
- [ ] T047 [Integration] Verify T034-T037 tests now PASS (GREEN)

### DuckDB Schema

- [ ] T048 [P] [Integration] Create DuckDB schema definition in `scripts/daily_analysis.py`:
  ```sql
  CREATE TABLE IF NOT EXISTS prices (
      timestamp TIMESTAMP PRIMARY KEY,
      utxoracle_price DECIMAL(12, 2),
      mempool_price DECIMAL(12, 2),
      confidence DECIMAL(5, 4),
      tx_count INTEGER,
      diff_amount DECIMAL(12, 2),
      diff_percent DECIMAL(6, 2)
  )
  ```
- [ ] T049 [Integration] Test manual run: `python3 scripts/daily_analysis.py --init-db --verbose`
- [ ] T050 [Integration] Verify DuckDB has data: `duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db "SELECT * FROM prices ORDER BY timestamp DESC LIMIT 5"`

### Cron Setup

- [ ] T051 [Integration] Create cron job file: `/media/sam/2TB-NVMe/prod/apps/utxoracle/config/cron.d/utxoracle-analysis.cron`
  ```cron
  */10 * * * * sam cd /media/sam/1TB/UTXOracle && UTXORACLE_DATA_DIR=/media/sam/2TB-NVMe/prod/apps/utxoracle/data python3 scripts/daily_analysis.py >> /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/daily_analysis.log 2>&1
  ```
- [ ] T052 [Integration] Install cron job: `sudo ln -sf /media/sam/2TB-NVMe/prod/apps/utxoracle/config/cron.d/utxoracle-analysis.cron /etc/cron.d/utxoracle-analysis`
- [ ] T053 [Integration] Reload cron: `sudo service cron reload`
- [ ] T054 [Integration] Verify cron executes: Wait 10 minutes, check logs and database for new entries

**Checkpoint**: Cron job running every 10 minutes, DuckDB accumulating data

---

## Phase 4: API & Visualization 📊

**Purpose**: FastAPI backend serves data, Plotly.js visualizes comparison

**Time Estimate**: 1-2 days

### Tests for API (TDD: Write FIRST, ensure FAIL)

- [ ] T055 [P] [API] Write failing test for latest price endpoint in `tests/test_api.py` (test_get_latest_price_returns_json)
- [ ] T056 [P] [API] Write failing test for historical prices endpoint in `tests/test_api.py` (test_get_historical_prices_with_days_param)
- [ ] T057 [P] [API] Write failing test for comparison stats endpoint in `tests/test_api.py` (test_get_comparison_stats_computes_avg_diff)

### FastAPI Backend

- [ ] T058 [API] Create `api/main.py` with FastAPI app initialization
- [ ] T059 [API] Add CORS middleware for localhost development
- [ ] T060 [API] Implement `GET /api/prices/latest` endpoint (queries DuckDB, returns most recent row)
- [ ] T061 [API] Implement `GET /api/prices/historical?days=7` endpoint (queries DuckDB with date filter)
- [ ] T062 [API] Implement `GET /api/prices/comparison` endpoint (computes avg_diff, max_diff, min_diff, correlation)
- [ ] T063 [API] Add health check endpoint: `GET /health` (returns uptime, DuckDB status)
- [ ] T064 [API] Add environment variable support: `UTXORACLE_DATA_DIR` for DuckDB path
- [ ] T065 [API] Verify T055-T057 tests now PASS (GREEN)

### Systemd Service

- [ ] T066 [P] [API] Create systemd service file: `/media/sam/2TB-NVMe/prod/apps/utxoracle/config/systemd/utxoracle-api.service`
  ```ini
  [Unit]
  Description=UTXOracle API Server
  After=network.target

  [Service]
  Type=simple
  User=sam
  WorkingDirectory=/media/sam/1TB/UTXOracle
  Environment="UTXORACLE_DATA_DIR=/media/sam/2TB-NVMe/prod/apps/utxoracle/data"
  ExecStart=/usr/bin/python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000
  Restart=always
  RestartSec=10

  [Install]
  WantedBy=multi-user.target
  ```
- [ ] T067 [API] Install systemd service: `sudo ln -sf /media/sam/2TB-NVMe/prod/apps/utxoracle/config/systemd/utxoracle-api.service /etc/systemd/system/`
- [ ] T068 [API] Enable service: `sudo systemctl daemon-reload && sudo systemctl enable utxoracle-api`
- [ ] T069 [API] Start service: `sudo systemctl start utxoracle-api`
- [ ] T070 [API] Verify service running: `sudo systemctl status utxoracle-api` (should show "active (running)")
- [ ] T071 [API] Test API endpoint: `curl http://localhost:8000/api/prices/latest | jq`

### Plotly.js Frontend

- [ ] T072 [P] [API] Create `frontend/comparison.html` with basic HTML structure
- [ ] T073 [API] Add Plotly.js CDN: `<script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>`
- [ ] T074 [API] Implement JavaScript: Fetch data from `http://localhost:8000/api/prices/historical?days=7`
- [ ] T075 [API] Implement Plotly time series chart:
  - Trace 1: UTXOracle price (green line)
  - Trace 2: Exchange price (red dashed line)
  - Dual Y-axis (optional)
  - Hover tooltips with timestamp + price + diff
- [ ] T076 [API] Add stats cards: Average diff, Max diff, Correlation coefficient
- [ ] T077 [API] Add CSS styling: Black background, orange theme (consistent with UTXOracle brand)
- [ ] T078 [API] Serve frontend via FastAPI: `app.mount("/", StaticFiles(directory="frontend"), name="frontend")`
- [ ] T079 [API] Test frontend loads: Open `http://localhost:8000/comparison.html` in browser

**Checkpoint**: API serves data via REST, frontend visualizes comparison with Plotly

---

## Phase 5: Cleanup & Documentation 🧹

**Purpose**: Remove old code, update docs, verify production readiness

**Time Estimate**: 1-2 days

### Code Cleanup

- [ ] T080 [Cleanup] Create backup of `/live/` directory: `cp -r live/ live.backup.$(date +%Y%m%d)`
- [ ] T081 [Cleanup] Archive `/live/` directory: `mv live/ archive/live-spec002/`
- [ ] T082 [Cleanup] Delete duplicated infrastructure files (after verifying backup exists):
  - `archive/live-spec002/backend/zmq_listener.py` (229 lines)
  - `archive/live-spec002/backend/tx_processor.py` (369 lines)
  - `archive/live-spec002/backend/block_parser.py` (144 lines)
  - `archive/live-spec002/backend/orchestrator.py` (271 lines)
  - `archive/live-spec002/backend/bitcoin_rpc.py` (109 lines)
- [ ] T083 [Cleanup] Refactor `archive/live-spec002/backend/baseline_calculator.py` → Create new `scripts/baseline_wrapper.py` (50 lines using UTXOracle_library)
- [ ] T084 [Cleanup] Update `.gitignore` to exclude production data: `/media/sam/2TB-NVMe/`, `*.db`, `*.db.wal`
- [ ] T085 [Cleanup] Measure code reduction: `find . -name '*.py' -not -path './archive/*' -not -path './tests/*' | xargs wc -l | tail -1`

### Documentation Updates

- [ ] T086 [P] [Cleanup] Update `CLAUDE.md`:
  - Add new architecture section (4-layer hybrid)
  - Update directory structure
  - Add production deployment section
  - Update agent responsibilities (no longer need custom infrastructure)
- [ ] T087 [P] [Cleanup] Update `README.md`:
  - Add self-hosted mempool.space section
  - Add price comparison feature
  - Update installation instructions
  - Add architecture diagram
- [ ] T088 [P] [Cleanup] Create `MIGRATION_GUIDE.md`:
  - How to migrate from spec 002 to spec 003
  - What changed and why
  - Backward compatibility notes
  - Troubleshooting common issues

### Testing & Validation

- [ ] T089 [Cleanup] Run full test suite: `pytest tests/ -v --cov` (target: 80%+ coverage)
- [ ] T090 [Cleanup] Test CLI backward compatibility: `python3 UTXOracle.py -d 2025/10/23` (verify output identical)
- [ ] T091 [Cleanup] Test cron job reliability: Monitor for 24 hours, verify no failures
- [ ] T092 [Cleanup] Test systemd service resilience: `sudo systemctl restart utxoracle-api` (should auto-restart)
- [ ] T093 [Cleanup] Test server reboot: `sudo reboot` → Verify all services auto-start (mempool-stack, utxoracle-api, cron)
- [ ] T094 [Cleanup] Performance benchmark: Measure API latency (target: <50ms), DuckDB query time (target: <50ms)

### Production Readiness

- [ ] T095 [Cleanup] Setup DuckDB backup cron: Daily backup at 3 AM to `backups/utxoracle_cache_YYYY-MM-DD.db`
- [ ] T096 [Cleanup] Setup log rotation: Configure logrotate for `daily_analysis.log` and `api.log` (keep 30 days)
- [ ] T097 [Cleanup] Create monitoring script: `scripts/health_check.sh` (checks Docker containers, API, cron, DuckDB)
- [ ] T098 [Cleanup] Test disaster recovery: Delete DuckDB file, verify can restore from backup
- [ ] T099 [Cleanup] Document operational runbook: Start/stop procedures, common issues, escalation

**Checkpoint**: Codebase cleaned, docs updated, production-ready

---

## Phase 6: Integration Testing & Validation ✅

**Purpose**: End-to-end testing and final validation

**Time Estimate**: 1 day

- [ ] T100 [Validation] End-to-end test: Trigger cron manually → Verify new data in DuckDB → Verify API returns it → Verify frontend shows it
- [ ] T101 [Validation] Load test: Insert 10,000 rows into DuckDB, measure query performance (should remain <50ms)
- [ ] T102 [Validation] Failure recovery test: Stop mempool-stack → Verify daily_analysis.py handles error gracefully → Restart stack → Verify resumes
- [ ] T103 [Validation] Price divergence test: Simulate large divergence (>5%) → Verify logged prominently
- [ ] T104 [Validation] Memory leak test: Run API for 24 hours → Monitor memory usage (should remain stable)
- [ ] T105 [Validation] Disk usage check: Verify electrs database ~38GB, DuckDB <100MB, logs <1GB
- [ ] T106 [Validation] Network bandwidth test: Measure mempool-stack bandwidth usage (should be minimal, mostly localhost)

### Acceptance Criteria Validation

- [ ] T107 [Validation] User Story 1: Price comparison dashboard shows dual time series (green vs red)
- [ ] T108 [Validation] User Story 2: Codebase is ≤800 lines (excluding tests and archive)
- [ ] T109 [Validation] User Story 3: `UTXOracle_library` import works, Rust migration path clear
- [ ] T110 [Validation] User Story 4: System survives reboot, all services auto-start

**Checkpoint**: All acceptance criteria met, system production-ready

---

## Summary

### Total Tasks: 110
### Estimated Time: 10-12 days
### Phases: 6

### Key Milestones:
1. **Day 2**: Infrastructure deployed (mempool.space + electrs running)
2. **Day 4**: Algorithm refactored to library
3. **Day 6**: Integration service operational (cron + DuckDB)
4. **Day 8**: API + frontend serving data
5. **Day 10**: Cleanup complete, docs updated
6. **Day 12**: Validation complete, production-ready

### Critical Path:
- T001-T012 (Infrastructure) → MUST complete before any other phase
- T013-T033 (Refactor) → Blocks T034-T050 (Integration)
- T034-T054 (Integration) → Blocks T055-T079 (API)
- electrs sync (3-4 hours on NVMe) → Can parallelize with refactor work

### Parallelization Opportunities:
- T008-T012 (infrastructure tests) can run in parallel
- T013-T018 (write tests) can run in parallel
- T034-T037 (write integration tests) can run in parallel
- T055-T057 (write API tests) can run in parallel
- T086-T088 (documentation updates) can run in parallel

---

**Status**: Ready for `/speckit.implement` phase

**Next Command**:
```
/speckit.implement
```
