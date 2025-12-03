# Technical Implementation Plan: mempool.space Integration

**Feature**: 003-mempool-integration-refactor
**Created**: 2025-10-24
**Based on**: `ULTRA_KISS_PLAN.md`

---

## Architecture Overview

### 4-Layer Hybrid Model

```
┌──────────────────────────────────────────────────────────────┐
│                 LAYER 1: INFRASTRUCTURE                       │
│   Stack: mempool.space Self-Hosted (Docker on NVMe)          │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐      │
│   │ Bitcoin Core│──▶│   electrs   │──▶│   MySQL     │      │
│   │  (host)     │   │ (38GB index)│   │  (2GB data) │      │
│   └─────────────┘   └─────────────┘   └─────────────┘      │
│                             │                                 │
│                             ▼                                 │
│            ┌────────────────────────────────┐                │
│            │   Mempool Backend (Node.js)    │                │
│            │   - REST API (:8999)           │                │
│            │   - WebSocket (real-time)      │                │
│            │   - price-updater (5 exchanges)│                │
│            └────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────┘
                             │
                             │ HTTP/WebSocket (localhost)
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                   LAYER 2: INTELLIGENCE                       │
│              UTXOracle Algorithm (Python Library)             │
│   ┌──────────────────────────────────────────────────┐      │
│   │  UTXOracle_library.py (NEW - refactor)           │      │
│   │  - class UTXOracleCalculator                     │      │
│   │  - calculate_price_for_transactions()            │      │
│   │  - Steps 5-11 as library methods                 │      │
│   └──────────────────────────────────────────────────┘      │
│                             │                                 │
│                             ▼                                 │
│   ┌──────────────────────────────────────────────────┐      │
│   │  scripts/daily_analysis.py (Cron - every 10min)  │      │
│   │  1. Fetch mempool API (:8999/api/v1/prices)      │      │
│   │  2. Run UTXOracle algorithm (RPC direct)         │      │
│   │  3. Compare prices (on-chain vs exchange)        │      │
│   │  4. Save to DuckDB (NVMe)                        │      │
│   └──────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────┘
                             │
                             │ Read/Write
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                    LAYER 3: STORAGE                           │
│   DuckDB (file: utxoracle_cache.db on NVMe)                  │
│   ┌──────────────────────────────────────────────────┐      │
│   │  prices table: See tasks.md T048 for schema      │      │
│   │  (timestamp, utxoracle_price, mempool_price,     │      │
│   │   confidence, tx_count, diff_*, is_valid)        │      │
│   └──────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────┘
                             │
                             │ SQL queries
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                 LAYER 4: API & VISUALIZATION                  │
│   FastAPI Backend (port 8000, systemd service)               │
│   ┌──────────────────────────────────────────────────┐      │
│   │  api/main.py                                     │      │
│   │  - GET /api/prices/latest                        │      │
│   │  - GET /api/prices/historical?days=7             │      │
│   │  - GET /api/prices/comparison                    │      │
│   │  - GET /api/stats/divergence                     │      │
│   └──────────────────────────────────────────────────┘      │
│                             │                                 │
│                             ▼                                 │
│   Frontend (Plotly.js - 50 lines vs 500 Canvas)              │
│   ┌──────────────────────────────────────────────────┐      │
│   │  frontend/comparison.html                        │      │
│   │  - Time series chart (dual Y-axis)               │      │
│   │  - Scatter plot (divergence over time)           │      │
│   │  - Stats cards (avg diff, max diff, correlation) │      │
│   └──────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────┘
```

---

## Tech Stack Decisions

### Infrastructure Layer

**mempool.space Docker Stack**:
- **Why**: Battle-tested, professional maintenance, 38GB electrs index included
- **Components**:
  - `mempool/frontend:latest` → Angular UI (port 8080)
  - `mempool/backend:latest` → Node.js API (port 8999)
  - `romanz/electrs:latest` → Rust indexer (port 50001, 38GB RocksDB)
  - `mariadb:10.5.21` → Backend database (port 3306, 2GB)
- **Deployment**: Single `docker-compose.yml` on NVMe
- **Configuration**: `.env` file with Bitcoin Core RPC credentials

**Bitcoin Core**:
- **Version**: Already installed and synced
- **Connection**: Cookie authentication (`~/.bitcoin/.cookie`)
- **Ports**: 8332 (RPC), 28332 (ZMQ - optional for future)

### Intelligence Layer

**UTXOracle Library** (NEW):
- **Language**: Python 3.8+ (standard library only for core)
- **Design**: Class-based API (`UTXOracleCalculator`)
- **Input**: List of transaction dicts (mempool.space format or RPC format)
- **Output**: Dict with `price_usd`, `confidence`, `tx_count`, `histogram`
- **Rationale**: Clean interface enables Rust migration later (PyO3)

**Integration Service**:
- **Script**: `scripts/daily_analysis.py`
- **Schedule**: Cron every 10 minutes (`*/10 * * * *`)
- **Data Flow**:
  1. Fetch exchange price: `curl http://localhost:8999/api/v1/prices`
  2. Calculate on-chain price: `UTXOracleCalculator().calculate_price_for_transactions()`
  3. Compare and save: DuckDB insert
- **Error Handling**: Retry 3× with exponential backoff, log failures

### Storage Layer

**DuckDB**:
- **Why**: Single file, no server, SQL analytics, 5× faster than SQLite on NVMe
- **Version**: 1.4.0+ (already installed)
- **Location**: `/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db`
- **Schema**: Single `prices` table (see architecture diagram)
- **Backup**: Daily cron copies to `backups/` directory (3 AM)
- **WAL Mode**: Enabled for crash recovery

### API & Visualization Layer

**FastAPI Backend**:
- **Why**: Fast, async, auto-generated OpenAPI docs, Pydantic validation
- **Deployment**: systemd service (`utxoracle-api.service`)
- **Port**: 8000 (production), 8001 (development)
- **Dependencies**: `fastapi`, `uvicorn[standard]`, `duckdb`
- **CORS**: Enabled for localhost development

**Plotly.js Frontend**:
- **Why**: 10× less code than custom Canvas (50 lines vs 500 lines)
- **Features**: Time series, scatter plots, hover tooltips, zoom/pan
- **CDN**: `https://cdn.plot.ly/plotly-2.26.0.min.js` (no build step)
- **Deployment**: Static HTML served by FastAPI

---

## Directory Structure

### Development (Git Repository)

```
/media/sam/1TB/UTXOracle/              # Git repo (code)
├── UTXOracle.py                       # CLI (backward compatible)
├── UTXOracle_library.py               # NEW: Core algorithm library
├── scripts/
│   ├── daily_analysis.py              # NEW: Cron job script
│   ├── setup_full_mempool_stack.sh    # EXISTING: Setup automation
│   └── verify_mempool_setup.sh        # EXISTING: Health checks
├── api/
│   └── main.py                        # NEW: FastAPI backend
├── frontend/
│   └── comparison.html                # NEW: Plotly visualization
├── tests/
│   ├── test_utxoracle_library.py      # NEW: Library unit tests
│   ├── test_daily_analysis.py         # NEW: Integration tests
│   └── test_api.py                    # NEW: API tests
├── live/                              # OLD: Archive after refactor
│   └── [to be archived]
└── specs/
    └── 003-mempool-integration-refactor/
        ├── spec.md                    # THIS FILE's parent
        ├── plan.md                    # THIS FILE
        └── tasks.md                   # Next to create
```

### Production (NVMe Runtime)

```
/media/sam/2TB-NVMe/prod/apps/
├── mempool-stack/                     # mempool.space Docker
│   ├── docker-compose.yml             # Generated by setup script
│   ├── .env                           # Bitcoin RPC config
│   ├── data/                          # Persistent data (NVMe)
│   │   ├── electrs/                   # 38GB RocksDB
│   │   ├── mysql/                     # 2GB MariaDB
│   │   └── cache/                     # 500MB backend cache
│   └── logs/                          # Container logs
└── utxoracle/                         # UTXOracle runtime
    ├── data/
    │   ├── utxoracle_cache.db         # DuckDB (NVMe - fast!)
    │   ├── utxoracle_cache.db.wal     # Write-Ahead Log
    │   └── backups/                   # Daily backups (30 days)
    ├── logs/
    │   ├── daily_analysis.log         # Cron job logs
    │   └── api.log                    # FastAPI logs
    └── config/
        ├── cron.d/
        │   └── utxoracle-analysis.cron
        └── systemd/
            └── utxoracle-api.service
```

---

## Implementation Approach

### Phase 1: Infrastructure Setup (Week 1, Days 1-2)

**Goal**: Self-hosted mempool.space stack running on NVMe

**Tasks**:
1. Run setup script: `bash scripts/setup_full_mempool_stack.sh`
2. Start Docker stack: `docker-compose up -d`
3. Monitor electrs sync: `docker-compose logs -f electrs` (3-4 hours on NVMe)
4. Verify APIs: `curl localhost:8999/api/v1/prices`

**Validation**:
- ✅ Frontend accessible: `http://localhost:8080`
- ✅ electrs synced: "finished full compaction" in logs
- ✅ Backend API returns prices: `{"USD": 67234, ...}`

---

### Phase 2: Algorithm Refactor (Week 1, Days 3-4)

**Goal**: UTXOracle.py → UTXOracle_library.py (class-based)

**Tasks**:
1. Create `UTXOracle_library.py` with `UTXOracleCalculator` class
2. Extract Steps 5-11 logic to methods:
   - `_build_histogram_bins()`
   - `_get_bin_index(amount_btc)`
   - `_remove_round_amounts(histogram)`
   - `_build_smooth_stencil()`
   - `_build_spike_stencil()`
   - `_estimate_price(histogram)`
   - `calculate_price_for_transactions(txs)` → Public API
3. Modify `UTXOracle.py` to import and use library (backward compatible)
4. Write unit tests: `tests/test_utxoracle_library.py`
5. Verify output identical: `pytest tests/test_utxoracle_library.py -v`

**Validation**:
- ✅ `python3 UTXOracle.py -rb` works (CLI unchanged)
- ✅ Can import: `from UTXOracle_library import UTXOracleCalculator`
- ✅ Tests pass with 80%+ coverage

---

### Phase 3: Integration Service (Week 1, Days 5-6)

**Goal**: Cron job that compares prices and saves to DuckDB

**Tasks**:
1. Create `scripts/daily_analysis.py`:
   - Fetch mempool price: `requests.get('http://localhost:8999/api/v1/prices')`
   - Calculate UTXOracle price: `UTXOracleCalculator().calculate_price_for_transactions()`
   - Compare and compute difference
   - Save to DuckDB: `duckdb.connect().execute("INSERT INTO prices ...")`
2. Initialize DuckDB schema: `--init-db` flag
3. Write integration tests: `tests/test_daily_analysis.py`
4. Setup cron job: `/etc/cron.d/utxoracle-analysis`
5. Test manual run: `python3 scripts/daily_analysis.py`

**Validation**:
- ✅ Script runs without errors
- ✅ DuckDB has data: `duckdb utxoracle_cache.db "SELECT COUNT(*) FROM prices"`
- ✅ Cron executes every 10 minutes

---

### Phase 4: API & Frontend (Week 1, Day 7)

**Goal**: FastAPI serves data, Plotly.js visualizes comparison

**Tasks**:
1. Create `api/main.py`:
   - Endpoint: `GET /api/prices/latest`
   - Endpoint: `GET /api/prices/historical?days=7`
   - Endpoint: `GET /api/prices/comparison` (stats)
2. Create `frontend/comparison.html`:
   - Fetch data: `fetch('http://localhost:8000/api/prices/historical?days=7')`
   - Plot dual time series: Plotly.js
   - Show stats: Average diff, max diff, correlation
3. Setup systemd service: `systemctl enable utxoracle-api`
4. Write API tests: `tests/test_api.py`

**Validation**:
- ✅ API responds: `curl http://localhost:8000/api/prices/latest`
- ✅ Frontend loads: `http://localhost:8000/comparison.html`
- ✅ Chart shows data (green = UTXOracle, red = Exchange)

---

### Phase 5: Cleanup & Documentation (Week 2)

**Goal**: Remove old code, update docs, verify production readiness

**Tasks**:
1. Archive `/live/` directory: `mv live/ live.archive/`
2. Delete duplicated code (after backup):
   - `live/backend/zmq_listener.py`
   - `live/backend/tx_processor.py`
   - `live/backend/block_parser.py`
   - `live/backend/orchestrator.py`
   - `live/backend/bitcoin_rpc.py`
3. Refactor `baseline_calculator.py` → 50 line wrapper
4. Update `CLAUDE.md` documentation
5. Update `README.md` with new architecture
6. Run full test suite: `pytest tests/ -v --cov`
7. Measure code reduction: `find . -name '*.py' | xargs wc -l`

**Validation**:
- ✅ Codebase ≤800 lines (77% reduction achieved)
- ✅ All tests pass (80%+ coverage)
- ✅ Documentation up-to-date
- ✅ System survives reboot (systemd auto-starts)

---

## Data Flow Diagrams

### Price Comparison Flow

```
[Every 10 minutes]
      │
      ▼
┌─────────────────┐
│  Cron Trigger   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│  daily_analysis.py                              │
│  ┌───────────────────────────────────────────┐  │
│  │ 1. Fetch Exchange Price                   │  │
│  │    GET http://localhost:8999/api/v1/prices│  │
│  │    → {"USD": 67234, "EUR": 62100, ...}    │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │ 2. Calculate On-Chain Price               │  │
│  │    calc = UTXOracleCalculator()           │  │
│  │    txs = fetch_from_bitcoin_rpc()         │  │
│  │    result = calc.calculate_price(txs)     │  │
│  │    → {"price_usd": 67189, ...}            │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │ 3. Compare & Compute Difference           │  │
│  │    diff_amount = 67189 - 67234 = -45      │  │
│  │    diff_percent = -45/67234 * 100 = -0.07%│  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │ 4. Save to DuckDB                         │  │
│  │    INSERT INTO prices VALUES (            │  │
│  │      timestamp, utxoracle_price,          │  │
│  │      mempool_price, confidence,           │  │
│  │      tx_count, diff_amount, diff_percent  │  │
│  │    )                                      │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│   DuckDB File   │
│   (on NVMe)     │
└─────────────────┘
```

### User Query Flow

```
[User opens browser]
      │
      ▼
┌─────────────────┐
│ comparison.html │
└────────┬────────┘
         │
         ▼ fetch('http://localhost:8000/api/prices/historical?days=7')
┌─────────────────────────────────────────────────┐
│  FastAPI Backend                                │
│  ┌───────────────────────────────────────────┐  │
│  │ api/main.py                               │  │
│  │ @app.get("/api/prices/historical")        │  │
│  │   cutoff = now() - timedelta(days=7)      │  │
│  │   query = "SELECT * FROM prices           │  │
│  │            WHERE timestamp >= ?"           │  │
│  │   result = duckdb.execute(query, cutoff)  │  │
│  │   return result.to_dict(orient='records') │  │
│  └───────────────────────────────────────────┘  │
└────────┬────────────────────────────────────────┘
         │
         ▼ JSON response
┌─────────────────────────────────────────────────┐
│  Frontend (Plotly.js)                           │
│  ┌───────────────────────────────────────────┐  │
│  │ const data = await response.json();       │  │
│  │ const utxoracle_trace = {                 │  │
│  │   x: data.map(d => d.timestamp),          │  │
│  │   y: data.map(d => d.utxoracle_price),    │  │
│  │   name: 'UTXOracle (On-Chain)',           │  │
│  │   line: {color: 'green'}                  │  │
│  │ };                                        │  │
│  │ const mempool_trace = {                   │  │
│  │   x: data.map(d => d.timestamp),          │  │
│  │   y: data.map(d => d.mempool_price),      │  │
│  │   name: 'Exchange (Median)',              │  │
│  │   line: {color: 'red', dash: 'dash'}      │  │
│  │ };                                        │  │
│  │ Plotly.newPlot('chart',                   │  │
│  │   [utxoracle_trace, mempool_trace]        │  │
│  │ );                                        │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  User sees:     │
│  📊 Time series │
│  📈 Divergence  │
│  📋 Stats       │
└─────────────────┘
```

---

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| electrs query latency | <100ms | `time curl localhost:50001` |
| DuckDB query latency | <50ms | `time duckdb "SELECT * FROM prices WHERE ..."` |
| Daily analysis runtime | <5 min | `time python3 scripts/daily_analysis.py` |
| API endpoint response | <50ms | `time curl http://localhost:8000/api/prices/latest` |
| Frontend chart render | <500ms | Browser DevTools Network tab |
| Cron job reliability | 99.9% | Monitor logs for failures |

---

## Testing Strategy

### Unit Tests

**UTXOracle Library**:
- `test_histogram_bins_generation()`
- `test_bin_index_calculation()`
- `test_round_amount_filtering()`
- `test_stencil_construction()`
- `test_price_estimation()`
- `test_calculate_price_for_transactions()`

**Daily Analysis**:
- `test_fetch_mempool_price()` (mock HTTP)
- `test_calculate_utxoracle_price()` (mock transactions)
- `test_save_to_duckdb()` (test DB)

**API Endpoints**:
- `test_get_latest_price()`
- `test_get_historical_prices()`
- `test_get_comparison_stats()`

### Integration Tests

- `test_end_to_end_pipeline()` - mempool API → UTXOracle → DuckDB → FastAPI
- `test_cron_execution()` - Verify cron job runs and updates DB
- `test_systemd_restart()` - Service survives restart

### Performance Tests

- `benchmark_duckdb_queries()` - Measure query latency
- `benchmark_api_endpoints()` - Measure HTTP response time
- `test_electrs_query_performance()` - Verify <100ms target

---

## Deployment Checklist

### Pre-Deployment

- [ ] Bitcoin Core synced and RPC accessible
- [ ] NVMe has 50GB free space
- [ ] Docker and docker-compose installed
- [ ] Python 3.8+ installed
- [ ] DuckDB 1.4.0+ installed

### Infrastructure Deployment

- [ ] Run `bash scripts/setup_full_mempool_stack.sh`
- [ ] Start Docker stack: `cd /media/sam/2TB-NVMe/prod/apps/mempool-stack && docker-compose up -d`
- [ ] Wait for electrs sync (3-4 hours on NVMe)
- [ ] Verify all containers healthy: `docker-compose ps`

### Application Deployment

- [ ] Install Python dependencies: `uv pip install -e .`
- [ ] Initialize DuckDB: `python3 scripts/daily_analysis.py --init-db`
- [ ] Test daily analysis: `python3 scripts/daily_analysis.py`
- [ ] Install cron job: `sudo ln -s $PWD/config/cron.d/utxoracle-analysis.cron /etc/cron.d/`
- [ ] Install systemd service: `sudo ln -s $PWD/config/systemd/utxoracle-api.service /etc/systemd/system/`
- [ ] Enable service: `sudo systemctl enable utxoracle-api && sudo systemctl start utxoracle-api`

### Validation

- [ ] Cron job executes: `tail -f /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/daily_analysis.log`
- [ ] DuckDB has data: `duckdb utxoracle_cache.db "SELECT COUNT(*) FROM prices"`
- [ ] API responds: `curl http://localhost:8000/api/prices/latest`
- [ ] Frontend loads: `firefox http://localhost:8000/comparison.html`

---

## Risk Mitigation

### electrs Sync Time (3-4 hours on NVMe)

**Mitigation**: Can work on refactor in parallel while syncing

### mempool.space API Changes

**Mitigation**: Self-hosted = version pinned, control updates

### DuckDB Corruption

**Mitigation**: Daily backups (3 AM cron), WAL mode enabled

### Price Divergence Alert

**Mitigation**: Add email/Telegram alert if diff >5%

---

## Success Metrics

- ✅ Code reduction: 3,041 → 700 lines (77%)
- ✅ Test coverage: 80%+
- ✅ Performance: All targets met
- ✅ Reliability: 99.9% uptime (30 days)
- ✅ Documentation: CLAUDE.md, README.md updated

---

**Status**: Ready for `/speckit.tasks` phase

**Next Command**:
```
/speckit.tasks
```
