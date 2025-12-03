# Feature Specification: mempool.space Integration & Codebase Refactor

**Feature Branch**: `003-mempool-integration-refactor`
**Created**: 2025-10-24
**Status**: Draft
**Parent Spec**: 002-mempool-live-oracle (builds upon existing live system)

---

## Problem Statement

### Current Limitation

The `/live/` directory (from spec 002) contains **1,222 lines of code duplicating existing infrastructure**:

- `zmq_listener.py` (229 lines) → Reinvents Bitcoin Core ZMQ streaming
- `tx_processor.py` (369 lines) → Reinvents transaction parsing
- `block_parser.py` (144 lines) → Reinvents block parsing
- `orchestrator.py` (271 lines) → Reinvents pipeline coordination
- `bitcoin_rpc.py` (109 lines) → Reinvents RPC client
- `baseline_calculator.py` (581 lines) → **Duplicates UTXOracle.py Steps 5-11**

**Total**: 1,703 lines of reinvented infrastructure + 581 lines of duplicated algorithm.

### Why This Violates KISS Principle

**mempool.space + electrs stack** already provides:
- ✅ Battle-tested ZMQ streaming (via electrs)
- ✅ Transaction parsing and indexing (38GB RocksDB)
- ✅ REST API + WebSocket (real-time)
- ✅ Price data from 5 exchanges (Coinbase, Kraken, Bitfinex, Gemini, Bitflyer)
- ✅ Professional maintenance (active open-source project)

**We reinvented the wheel** instead of using proven infrastructure.

### Opportunity

**Self-host mempool.space stack** → Use as infrastructure layer → Focus on unique value (UTXOracle algorithm).

**Benefits**:
- 77% code reduction (3,041 → 700 lines)
- Eliminate maintenance burden
- Enable price comparison (on-chain vs exchange)
- Prepare for Rust migration (clean library interface)

---

## Value Proposition

### What We Keep (Unique Value)

**UTXOracle Algorithm** (376 lines):
- On-chain price discovery via statistical clustering
- Exchange-free, privacy-first
- Steps 5-11 from UTXOracle.py (histogram, stencil, convergence)

**Frontend Visualization** (~500 lines, but refactor):
- Replace Canvas custom code → Plotly.js (50 lines)
- 90% code reduction while improving features

### What We Replace (Infrastructure)

**Delete** (1,122 lines):
- Custom ZMQ/RPC/parser → Use mempool.space API
- Custom orchestrator → Use mempool.space backend

**Refactor** (581 → 50 lines):
- `baseline_calculator.py` → Wrapper around `UTXOracle_library.py`

---

## User Scenarios & Testing

### User Story 1 - Price Comparison Dashboard (Priority: P1)

**As a** Bitcoin analyst
**I want to** compare on-chain price (UTXOracle) vs exchange prices (mempool.space)
**So that** I can identify market discrepancies and arbitrage opportunities

**Why this priority**: Core value proposition - shows UTXOracle's unique on-chain signal vs centralized exchanges

**Independent Test**: Dashboard displays two time series: UTXOracle (green) vs Exchange median (red), shows difference percentage

**Acceptance Scenarios**:

1. **Given** self-hosted mempool.space is running with price-updater enabled
   **When** I open http://localhost:8000/comparison
   **Then** I see latest prices: UTXOracle (on-chain) and Exchange (median of 5)

2. **Given** UTXOracle calculates new price every 10 minutes
   **When** I view historical chart (last 7 days)
   **Then** I see two lines diverge/converge showing market dynamics

3. **Given** prices differ by >2%
   **When** dashboard loads
   **Then** I see highlighted warning: "Large divergence detected: +3.2%"

---

### User Story 2 - Simplified Codebase (Priority: P1)

**As a** developer maintaining UTXOracle
**I want to** reduce codebase from 3,041 to 700 lines
**So that** I can focus on algorithm improvements, not infrastructure maintenance

**Why this priority**: Reduces technical debt, enables faster iteration

**Independent Test**: Run `find live/ -name '*.py' | xargs wc -l` before/after shows 77% reduction

**Acceptance Scenarios**:

1. **Given** refactor is complete
   **When** I count Python lines
   **Then** Total is ≤800 lines (including tests)

2. **Given** mempool.space provides infrastructure
   **When** I need to add new feature
   **Then** I only modify UTXOracle algorithm code, not infrastructure

3. **Given** code is simplified
   **When** New contributor reviews codebase
   **Then** They understand architecture in <30 minutes

---

### User Story 3 - Rust Migration Preparation (Priority: P2)

**As a** performance engineer
**I want to** refactor UTXOracle.py into a Python library with clean API
**So that** I can later swap implementation to Rust without changing callers

**Why this priority**: Enables future performance optimization without breaking existing code

**Independent Test**: Import `UTXOracle_library` and calculate price without subprocess

**Acceptance Scenarios**:

1. **Given** `UTXOracle_library.py` exists with `UTXOracleCalculator` class
   **When** I call `calc.calculate_price_for_transactions(txs)`
   **Then** I get `{'price_usd': float, 'confidence': float}`

2. **Given** library has clean interface
   **When** I replace import with `from utxoracle_rust import UTXOracleCalculator`
   **Then** Code works identically (drop-in replacement)

3. **Given** original `UTXOracle.py` CLI still exists
   **When** I run `python3 UTXOracle.py -rb`
   **Then** Output is identical to before (backward compatible)

---

### User Story 4 - Production Deployment (Priority: P2)

**As a** system administrator
**I want to** deploy mempool.space + UTXOracle on NVMe with systemd
**So that** system runs reliably 24/7 with automatic restarts

**Why this priority**: Production-ready deployment, not just development prototype

**Independent Test**: System survives server reboot, all services auto-start

**Acceptance Scenarios**:

1. **Given** systemd services configured
   **When** Server reboots
   **Then** mempool-stack and utxoracle-api auto-start

2. **Given** cron job configured
   **When** Clock reaches 10-minute mark
   **Then** `daily_analysis.py` runs and updates DuckDB

3. **Given** electrs database on NVMe
   **When** I query address
   **Then** Response time is <100ms (vs 1s on HDD)

---

## Success Criteria

### Functional Requirements

- ✅ Price comparison API endpoint returns both UTXOracle and exchange prices
- ✅ Plotly.js dashboard visualizes historical comparison
- ✅ DuckDB stores time series data on NVMe
- ✅ Cron job updates prices every 10 minutes
- ✅ FastAPI serves data with <50ms latency

### Code Quality Requirements

- ✅ Total Python codebase ≤800 lines (77% reduction achieved)
- ✅ `UTXOracle_library.py` has 80%+ test coverage
- ✅ All integration tests pass (mempool API → algorithm → DuckDB)
- ✅ Zero duplication of UTXOracle algorithm logic
- ✅ Documentation updated (CLAUDE.md, README.md)

### Performance Requirements

- ✅ electrs query response: <100ms on NVMe
- ✅ DuckDB analytics queries: <50ms
- ✅ Daily analysis execution: <5 minutes per run

### Deployment Requirements

- ✅ Self-hosted mempool.space stack runs on NVMe
- ✅ electrs database synced (3-4 hours initial on NVMe)
- ✅ Systemd services auto-start on boot
- ✅ Cron jobs execute reliably
- ✅ Logs rotate and archive automatically

---

## Non-Functional Requirements

### Error Handling

**Requirement**: System MUST handle infrastructure failures gracefully with retry logic and notifications.

**Scenarios**:

1. **mempool.space API Unreachable**:
   - **When** `daily_analysis.py` cannot connect to `http://localhost:8080/api`
   - **Then** Retry 3 times with exponential backoff (5s, 15s, 45s)
   - **And** If all retries fail, log ERROR and exit with code 1
   - **And** Send notification (email/webhook) to admin if configured

2. **Bitcoin Core RPC Timeout**:
   - **When** UTXOracle library cannot connect to Bitcoin Core
   - **Then** Retry 2 times with 10s delay
   - **And** If fails, fall back to cached data (if <1 hour old)
   - **And** Log WARNING with timestamp of cached data

3. **DuckDB Write Failure**:
   - **When** Database write fails (disk full, permission denied)
   - **Then** Attempt write to fallback location `/tmp/utxoracle_backup.duckdb`
   - **And** Log CRITICAL error with full exception traceback
   - **And** Do NOT continue execution (prevent data inconsistency)

4. **Invalid Price Calculation**:
   - **When** UTXOracle returns confidence score <0.3 or price outside range [$10k, $500k]
   - **Then** Log WARNING with transaction data summary
   - **And** Store result with `is_valid=false` flag in database
   - **And** Dashboard displays "Low confidence" warning

**Error Response Format** (API):
```json
{
  "error": {
    "code": "MEMPOOL_API_UNAVAILABLE",
    "message": "Cannot connect to mempool.space backend",
    "retry_after": 300,
    "details": {
      "url": "http://localhost:8080/api/v1/prices",
      "attempts": 3,
      "last_error": "Connection refused"
    }
  }
}
```

### Configuration Management

**Requirement**: All deployment-specific values MUST be configurable via environment variables or `.env` file.

**Configuration Schema**:

```bash
# .env file (NOT committed to git)

# Mempool.space Backend
MEMPOOL_API_URL=http://localhost:8080
MEMPOOL_WS_URL=ws://localhost:8999

# Bitcoin Core
BITCOIN_RPC_URL=http://127.0.0.1:8332
BITCOIN_RPC_USER=your_user
BITCOIN_RPC_PASSWORD=your_password
BITCOIN_DATADIR=/home/user/.bitcoin

# Database
DUCKDB_PATH=/mnt/nvme/utxoracle.duckdb
DUCKDB_BACKUP_PATH=/mnt/backup/utxoracle_backup.duckdb

# API Server
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
FASTAPI_WORKERS=4

# UTXOracle Algorithm
UTXORACLE_CONFIDENCE_THRESHOLD=0.3
UTXORACLE_MIN_PRICE_USD=10000
UTXORACLE_MAX_PRICE_USD=500000

# Scheduling
ANALYSIS_INTERVAL_MINUTES=10

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/utxoracle/analysis.log
LOG_RETENTION_DAYS=30

# Notifications (optional)
ALERT_EMAIL=admin@example.com
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK
```

**Loading Priority**:
1. Environment variables (highest)
2. `.env` file in project root
3. Default values (hardcoded fallbacks)

**Example** (`daily_analysis.py`):
```python
import os
from dotenv import load_dotenv

load_dotenv()

MEMPOOL_API_URL = os.getenv('MEMPOOL_API_URL', 'http://localhost:8080')
DUCKDB_PATH = os.getenv('DUCKDB_PATH', './utxoracle.duckdb')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
```

**Validation**:
- MUST validate required variables on startup
- MUST fail fast with clear error if critical config missing
- MUST log which config file/source was loaded

### Logging

**Requirement**: All components MUST produce structured logs for monitoring and debugging.

**Log Format** (JSON structured):
```json
{
  "timestamp": "2025-10-24T14:30:00.123Z",
  "level": "INFO",
  "component": "daily_analysis",
  "message": "Price calculation completed",
  "context": {
    "price_usd": 67234.56,
    "confidence": 0.87,
    "tx_count": 1423,
    "duration_seconds": 3.2,
    "mempool_api_version": "2.5.0"
  }
}
```

**Log Levels**:

| Level | Use Case | Example |
|-------|----------|---------|
| DEBUG | Development debugging | "Fetched 1423 transactions from mempool API" |
| INFO | Normal operations | "Cron job started: daily_analysis.py" |
| WARNING | Recoverable errors | "Low confidence score: 0.25 (threshold: 0.3)" |
| ERROR | Failed operations | "mempool API unreachable after 3 retries" |
| CRITICAL | System failures | "DuckDB write failed: disk full" |

**Log Outputs**:

1. **Console** (systemd journal):
   - Human-readable format for development
   - Structured JSON for production

2. **File** (`/var/log/utxoracle/analysis.log`):
   - Rotated daily (logrotate)
   - Compressed after 7 days
   - Deleted after 30 days

3. **Optional**: Syslog/Fluentd for centralized logging

**Example Implementation** (`daily_analysis.py`):
```python
import logging
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger("daily_analysis")

# Usage
logger.info(
    "price_calculated",
    price_usd=67234.56,
    confidence=0.87,
    tx_count=1423,
    duration_seconds=3.2
)
```

**Cron Job Logging**:
- STDOUT → `analysis.log` (append)
- STDERR → `analysis_errors.log` (separate file)
- Exit code 0 = success, 1 = failure
- Log file path in crontab:
  ```cron
  */10 * * * * /usr/bin/python3 /path/to/daily_analysis.py >> /var/log/utxoracle/cron.log 2>&1
  ```

**Monitoring Integration**:
- Parse JSON logs with Prometheus `node_exporter` (textfile collector)
- Alert on ERROR/CRITICAL logs via Grafana
- Track metrics: calculation duration, API latency, confidence scores

---

## Out of Scope (Future Work)

- ❌ Advanced statistical analysis (symbolic dynamics, Wasserstein distance) → Defer to spec 004
- ❌ Rust implementation of algorithm → Defer until library API stable
- ❌ Machine learning price prediction → Out of scope
- ❌ Real-time WebSocket streaming (already implemented in spec 002) → Keep as-is
- ❌ Mobile app → Not planned

---

## Dependencies

### Prerequisite Specs

- ✅ **001-specify-scripts-bash**: SpecKit automation (completed)
- ✅ **002-mempool-live-oracle**: Live system MVP (85% complete)

### External Dependencies

- ✅ Bitcoin Core (synced, RPC enabled)
- 🆕 mempool.space Docker images (mempool/frontend, mempool/backend)
- 🆕 electrs Docker image (romanz/electrs)
- 🆕 MariaDB 10.5.21
- 🆕 DuckDB 1.4.0+

### System Requirements

- NVMe storage: 50GB available (38GB electrs + 2GB MySQL + 10GB buffer)
- RAM: 8GB minimum (4GB for electrs, 2GB for backend, 2GB for system)
- CPU: 4 cores (for electrs indexing)

---

## Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| electrs sync takes 12 hours | High | Certain | Run overnight, parallel work on refactor |
| mempool.space API changes | Medium | Low | Self-hosted = control version |
| DuckDB file corruption | Medium | Low | Daily backups, WAL mode enabled |
| Price divergence >10% | Low | Medium | Alert system, investigate root cause |

---

## References

- **Parent Plan**: `/media/sam/1TB/UTXOracle/ULTRA_KISS_PLAN.md`
- **Architecture**: `/media/sam/1TB/UTXOracle/MEMPOOL_ELECTRS_ARCHITECTURE.md`
- **Deployment**: `/media/sam/1TB/UTXOracle/PRODUCTION_DEPLOYMENT.md`
- **Setup Script**: `/media/sam/1TB/UTXOracle/scripts/setup_full_mempool_stack.sh`
- **mempool.space**: https://github.com/mempool/mempool
- **electrs**: https://github.com/romanz/electrs
- **Constitution**: `.specify/memory/constitution.md` (v1.0.0)

---

**Status**: Ready for `/speckit.plan` phase

**Next Command**:
```
/speckit.plan Use self-hosted mempool.space Docker stack for infrastructure (electrs + backend + frontend on NVMe). Refactor UTXOracle.py to Python library (class-based). Store comparison results in DuckDB (single file on NVMe). Expose via FastAPI. Visualize with Plotly.js (replace Canvas custom code). Deploy with systemd + cron for production reliability.
```
