# Feature Specification: UTXO Lifecycle Engine

**Feature Branch**: `017-utxo-lifecycle-engine`
**Created**: 2025-12-06
**Status**: Draft
**Prerequisites**: spec-016 (STH/LTH SOPR) demonstrates value
**Priority**: FOUNDATION (4-6 weeks)
**Evidence Grade**: A (enables all Tier A metrics)

## Context & Motivation

### Background: The Fundamental Gap

From Contadino Galattico analysis:

```
Attuale:  Blocco → TX → Address → Whale Flow / Active Count

Richiesto: UTXO_i:
           ├── created_block
           ├── created_price_usd     ← MANCA
           ├── spent_block           ← MANCA
           ├── spent_price_usd       ← MANCA
           └── age_days              ← MANCA (STH/LTH)
```

**Impact**: Without UTXO lifecycle tracking, we cannot implement:

| Metric | Requirement | Evidence Grade |
|--------|-------------|----------------|
| MVRV | Realized Value per UTXO | A-B |
| Realized Cap | Sum of UTXO creation prices | A |
| NUPL | Net Unrealized P/L | A-B |
| HODL Waves | UTXO age cohorts | A |
| Cointime | UTXO dormancy tracking | A |
| STH/LTH Supply | Supply by holder duration | A-B |

### Gap Analysis: CheckOnChain Comparison

| Categoria | Metrica | UTXOracle Has? | Requires |
|-----------|---------|----------------|----------|
| **Profit/Loss** | MVRV | No | UTXO lifecycle |
| **Profit/Loss** | SOPR | Partial (spec-016) | UTXO lifecycle |
| **Profit/Loss** | NUPL | No | UTXO lifecycle |
| **Supply** | HODL Waves | No | UTXO age cohorts |
| **Supply** | STH/LTH Split | Partial | 155-day threshold |
| **Pricing** | Realized Price | No | UTXO lifecycle |
| **Cointime** | Liveliness | No | UTXO dormancy |

### Design Philosophy: Incremental

Full UTXO set tracking is expensive (100+ GB storage, weeks of sync). We implement incrementally:

1. **Phase 1**: Recent history (6 months) - Enables STH metrics
2. **Phase 2**: Extended history (2 years) - Enables LTH metrics
3. **Phase 3**: Full history (optional) - Complete HODL Waves

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - UTXO Creation Tracking (Priority: P1)

As a Bitcoin analyst, I want to track **when each UTXO was created and at what price**, so I can calculate realized value and profit/loss.

**Acceptance Scenarios**:

1. **Given** a new UTXO created in block 850,000
   **When** lifecycle engine processes the block
   **Then** UTXO record created with `creation_block=850000`, `creation_price=UTXOracle_price`

2. **Given** UTXO value of 1.5 BTC created at $50,000
   **When** realized value calculated
   **Then** `realized_value = 1.5 * 50000 = $75,000`

---

### User Story 2 - UTXO Spending Tracking (Priority: P1)

As a Bitcoin analyst, I want to track **when each UTXO is spent**, so I can calculate SOPR and supply dynamics.

**Acceptance Scenarios**:

1. **Given** UTXO spent in block 860,000 (created in 850,000)
   **When** lifecycle engine processes the block
   **Then** UTXO record updated with `spent_block=860000`, `age_days=~70`

2. **Given** UTXO spent at $100,000 (created at $50,000)
   **When** SOPR calculated
   **Then** `sopr = 100000/50000 = 2.0`

---

### User Story 3 - Age Cohort Analysis (Priority: P1)

As a Bitcoin analyst, I want to classify **supply by holder duration**, so I can understand STH vs LTH behavior.

**Acceptance Scenarios**:

1. **Given** UTXO age = 30 days
   **When** cohort classified
   **Then** `cohort = "STH"`, `sub_cohort = "1w-1m"`

2. **Given** UTXO age = 2 years
   **When** cohort classified
   **Then** `cohort = "LTH"`, `sub_cohort = "1y-2y"`

3. **Given** current block height
   **When** supply distribution queried
   **Then** Returns BTC by age cohort (HODL Waves data)

---

### User Story 4 - Realized Metrics (Priority: P2)

As a Bitcoin trader, I want **realized-value based metrics**, so I can use the most empirically validated signals.

**Acceptance Scenarios**:

1. **Given** total realized value and market cap
   **When** MVRV calculated
   **Then** `mvrv = market_cap / realized_cap`

2. **Given** unrealized profit and market cap
   **When** NUPL calculated
   **Then** `nupl = (market_cap - realized_cap) / market_cap`

---

### Edge Cases

- **What if creation price unknown (pre-UTXOracle)?**
  → Use mempool.space historical API. Mark `price_source="mempool"`.

- **What if storage limits exceeded?**
  → Prune UTXOs older than retention period. Default: 6 months for MVP.

- **What if UTXO is from coinbase (mining)?**
  → Mark `is_coinbase=True`, use block subsidy + fees for value.

- **What if reorg occurs?**
  → Mark affected UTXOs as `reorg_invalidated=True`, reprocess.

---

## Requirements *(mandatory)*

### Functional Requirements

**UTXO Creation**:
- **FR-001**: System MUST create lifecycle record for every new UTXO in processed blocks
- **FR-002**: Creation record MUST include: txid, vout, block_height, timestamp, btc_value
- **FR-003**: Creation price MUST be stored in USD (from UTXOracle)
- **FR-004**: System MUST handle batch creation (multiple UTXOs per TX)

**UTXO Spending**:
- **FR-005**: System MUST update lifecycle record when UTXO is spent
- **FR-006**: Spending record MUST include: spending_txid, spent_block, spent_timestamp
- **FR-007**: System MUST calculate age at spend (spent_block - creation_block)
- **FR-008**: System MUST calculate SOPR at spend (spend_price / creation_price)

**Age Cohorts**:
- **FR-009**: System MUST classify UTXOs into age cohorts:
  - `<1d`, `1d-1w`, `1w-1m`, `1m-3m`, `3m-6m` (STH)
  - `6m-1y`, `1y-2y`, `2y-3y`, `3y-5y`, `>5y` (LTH)
- **FR-010**: STH/LTH threshold: 155 days (configurable)
- **FR-011**: System MUST calculate supply distribution by cohort

**Aggregate Metrics**:
- **FR-012**: Realized Cap = Σ(UTXO_value × creation_price)
- **FR-013**: MVRV = Market Cap / Realized Cap
- **FR-014**: NUPL = (Market Cap - Realized Cap) / Market Cap
- **FR-015**: STH Supply = Σ(UTXO_value where age < 155 days)
- **FR-016**: LTH Supply = Σ(UTXO_value where age ≥ 155 days)

**Storage**:
- **FR-017**: UTXO records MUST be stored in DuckDB
- **FR-018**: Default retention: 6 months (configurable)
- **FR-019**: Pruning MUST remove spent UTXOs older than retention period
- **FR-020**: Index on (txid, vout) for fast lookup

### Non-Functional Requirements

- **NFR-001**: Block processing MUST complete in <5 seconds per block
- **NFR-002**: Storage growth MUST be <1GB per month for MVP (6-month retention)
- **NFR-003**: System MUST support incremental sync (resume from last block)
- **NFR-004**: System MUST handle 100,000+ UTXOs per block

### Key Entities *(mandatory)*

```python
@dataclass
class UTXOLifecycle:
    # Identity
    txid: str
    vout_index: int
    outpoint: str  # f"{txid}:{vout_index}"

    # Creation
    creation_block: int
    creation_timestamp: datetime
    creation_price_usd: float
    btc_value: float
    realized_value_usd: float  # btc_value × creation_price

    # Spending (optional, None if unspent)
    spent_block: int | None
    spent_timestamp: datetime | None
    spent_price_usd: float | None
    spending_txid: str | None

    # Derived
    age_days: int | None  # Current age or age at spend
    cohort: str  # "STH" | "LTH"
    sub_cohort: str  # "<1d", "1d-1w", etc.
    sopr: float | None  # None if unspent

    # Metadata
    is_coinbase: bool
    is_spent: bool
    price_source: str  # "utxoracle" | "mempool" | "fallback"

@dataclass
class UTXOSetSnapshot:
    block_height: int
    timestamp: datetime

    # Supply Distribution
    total_supply_btc: float
    sth_supply_btc: float
    lth_supply_btc: float
    supply_by_cohort: dict[str, float]

    # Realized Metrics
    realized_cap_usd: float
    market_cap_usd: float
    mvrv: float
    nupl: float

    # HODL Waves
    hodl_waves: dict[str, float]  # cohort -> % of supply

@dataclass
class AgeCohortsConfig:
    sth_threshold_days: int = 155
    cohorts: list[tuple[str, int, int]] = field(default_factory=lambda: [
        ("<1d", 0, 1),
        ("1d-1w", 1, 7),
        ("1w-1m", 7, 30),
        ("1m-3m", 30, 90),
        ("3m-6m", 90, 180),
        ("6m-1y", 180, 365),
        ("1y-2y", 365, 730),
        ("2y-3y", 730, 1095),
        ("3y-5y", 1095, 1825),
        (">5y", 1825, float("inf")),
    ])
```

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: UTXO creation tracking captures 100% of new UTXOs
- **SC-002**: UTXO spending tracking captures 100% of spent UTXOs
- **SC-003**: Age classification matches Glassnode within ±1% (if comparison available)
- **SC-004**: MVRV calculation matches Glassnode within ±5% (if comparison available)
- **SC-005**: Storage growth <1GB/month for 6-month retention
- **SC-006**: Block processing <5 seconds per block

### Definition of Done

- [ ] UTXOLifecycle dataclass implemented
- [ ] UTXO creation tracking from new blocks
- [ ] UTXO spending tracking from inputs
- [ ] Historical price lookup for creation price
- [ ] Age cohort classification (10 cohorts)
- [ ] Supply distribution calculation
- [ ] Realized Cap calculation
- [ ] MVRV calculation
- [ ] NUPL calculation
- [ ] DuckDB schema for UTXO lifecycle
- [ ] Pruning mechanism for storage management
- [ ] API endpoint `/api/metrics/utxo-lifecycle`
- [ ] Unit tests (≥85% coverage)
- [ ] Integration test: full block processing
- [ ] Performance validation (<5s/block)
- [ ] Documentation in CLAUDE.md

---

## Technical Notes

### Implementation Order (KISS)

**Phase 1: MVP (2-3 weeks)**
1. **Schema Design** (~30 LOC) - DuckDB tables
2. **UTXO Creation** (~80 LOC) - Parse vouts, store lifecycle
3. **UTXO Spending** (~60 LOC) - Parse inputs, update lifecycle
4. **Price Lookup** (~40 LOC) - Historical price retrieval
5. **Age Classification** (~30 LOC) - Cohort assignment

**Phase 2: Metrics (1-2 weeks)**
6. **Supply Distribution** (~40 LOC) - By cohort
7. **Realized Cap** (~30 LOC) - Sum of realized values
8. **MVRV/NUPL** (~20 LOC) - Ratio calculations
9. **API Endpoints** (~50 LOC) - REST interface

**Phase 3: Optimization (1 week)**
10. **Pruning** (~40 LOC) - Storage management
11. **Batch Processing** (~30 LOC) - Parallel UTXO handling
12. **Caching** (~30 LOC) - Frequently accessed data

### Files to Create

- `scripts/utils/electrs_async.py` - High-performance async electrs HTTP client
- `scripts/sync_utxo_lifecycle.py` - UTXO lifecycle sync script (CLI)
- `scripts/metrics/utxo_lifecycle.py` - Core lifecycle engine
- `scripts/metrics/realized_metrics.py` - MVRV, NUPL, Realized Cap
- `scripts/metrics/hodl_waves.py` - Age distribution analysis
- `tests/test_utxo_lifecycle.py` - Test suite

### Files to Modify

- `scripts/daily_analysis.py` - Add lifecycle tracking
- `api/main.py` - Add lifecycle endpoints
- `scripts/models/metrics_models.py` - Add lifecycle dataclasses

### Database Schema

```sql
-- Main UTXO lifecycle table
CREATE TABLE IF NOT EXISTS utxo_lifecycle (
    outpoint TEXT PRIMARY KEY,  -- "txid:vout"
    txid TEXT NOT NULL,
    vout_index INTEGER NOT NULL,

    -- Creation
    creation_block INTEGER NOT NULL,
    creation_timestamp TIMESTAMP NOT NULL,
    creation_price_usd REAL NOT NULL,
    btc_value REAL NOT NULL,
    realized_value_usd REAL NOT NULL,

    -- Spending (NULL if unspent)
    spent_block INTEGER,
    spent_timestamp TIMESTAMP,
    spent_price_usd REAL,
    spending_txid TEXT,

    -- Derived
    age_days INTEGER,
    cohort TEXT,  -- "STH" | "LTH"
    sub_cohort TEXT,
    sopr REAL,

    -- Metadata
    is_coinbase BOOLEAN DEFAULT FALSE,
    is_spent BOOLEAN DEFAULT FALSE,
    price_source TEXT DEFAULT 'utxoracle',

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast queries
CREATE INDEX idx_utxo_creation_block ON utxo_lifecycle(creation_block);
CREATE INDEX idx_utxo_spent_block ON utxo_lifecycle(spent_block) WHERE spent_block IS NOT NULL;
CREATE INDEX idx_utxo_is_spent ON utxo_lifecycle(is_spent);
CREATE INDEX idx_utxo_cohort ON utxo_lifecycle(cohort) WHERE is_spent = FALSE;

-- Snapshots for historical queries
CREATE TABLE IF NOT EXISTS utxo_snapshots (
    block_height INTEGER PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    total_supply_btc REAL NOT NULL,
    sth_supply_btc REAL NOT NULL,
    lth_supply_btc REAL NOT NULL,
    realized_cap_usd REAL NOT NULL,
    market_cap_usd REAL NOT NULL,
    mvrv REAL NOT NULL,
    nupl REAL NOT NULL,
    hodl_waves_json TEXT  -- JSON of cohort distribution
);
```

### Storage Estimates

| Retention | UTXOs (approx) | Storage |
|-----------|---------------|---------|
| 6 months | ~50M | ~5 GB |
| 1 year | ~100M | ~10 GB |
| 2 years | ~200M | ~20 GB |
| Full history | ~1B+ | ~100+ GB |

**Recommendation**: Start with 6 months, expand based on demonstrated value.

### Configuration

```bash
# .env additions
UTXO_LIFECYCLE_ENABLED=true
UTXO_RETENTION_DAYS=180
UTXO_STH_THRESHOLD_DAYS=155
UTXO_PRUNING_ENABLED=true
UTXO_BATCH_SIZE=10000
```

---

## Dependencies

### Internal
- spec-016 (STH/LTH SOPR) - Validates approach before full investment
- Historical UTXOracle prices - Creation price lookup

### External
- **electrs HTTP API** - PRIMARY block/TX data (localhost:3001)
- mempool.space API - Fallback price data
- Bitcoin Core RPC - DEPRECATED for UTXO sync

### Data Source Hierarchy (December 2025)

| Tier | Source | Endpoint | Status |
|------|--------|----------|--------|
| **1 - PRIMARY** | electrs HTTP | `http://localhost:3001` | Production |
| 2 - FALLBACK | mempool.space | `https://mempool.space/api` | Optional |
| 3 - DEPRECATED | Bitcoin Core RPC | `http://localhost:8332` | Not used |

**Why electrs?**
- **5-12x faster** than Bitcoin Core RPC for batch TX fetching
- Paginated endpoint: `/block/{hash}/txs/{start}` returns 25 txs per request
- `prevout` data included in inputs (no extra lookup needed)
- Self-hosted (Docker stack): privacy-preserving, no external API calls

### Performance Benchmarks (December 2025)

| Configuration | Blocks | Time | Speed |
|--------------|--------|------|-------|
| Async (workers=5) | 5 | 218s | 43.6s/block |
| Sequential (workers=1) | 5 | 252s | 50.4s/block |
| **Speedup** | - | - | **1.16x** |

**CLI Usage**:
```bash
# Default: electrs with 5 workers
python scripts/sync_utxo_lifecycle.py --start-block 900000 --end-block 900999

# Explicit source and workers
python scripts/sync_utxo_lifecycle.py --start-block 900000 --end-block 900999 \
    --source electrs --workers 10
```

### Async Implementation (scripts/utils/electrs_async.py)

Key features:
- **aiohttp TCPConnector**: Connection pooling (limit=100 connections)
- **asyncio.Semaphore**: Rate limiting (default 50 concurrent requests)
- **Paginated fetching**: 25 txs per page, much faster than individual tx fetches
- **Exponential backoff**: 3 retries with 1s, 2s, 4s delays

```python
async with ElectrsAsyncClient() as client:
    block = await client.get_block_async(900000)
    blocks = await client.get_blocks_batch_async([900000, 900001, 900002])
```

---

## Phased Implementation

### Phase 1: 6-Month History (4-6 weeks)
- Enables: STH metrics, recent SOPR, partial HODL Waves
- Storage: ~5 GB
- Processing: ~2 weeks initial sync

### Phase 2: 2-Year History (Optional, +2 weeks)
- Enables: Full LTH metrics, complete supply analysis
- Storage: ~20 GB
- Processing: ~1 month initial sync

### Phase 3: Full History (Optional, +4 weeks)
- Enables: Complete HODL Waves, historical analysis
- Storage: ~100+ GB
- Processing: ~2-3 months initial sync

---

## Out of Scope

- Real-time mempool UTXO tracking (batch only)
- Cross-chain UTXO tracking (Bitcoin only)
- Lightning Network UTXO handling
- Privacy-enhanced UTXO analysis (CoinJoin, etc.)

---

## References

1. **Glassnode Academy**: "Realized Cap and MVRV"
   - https://academy.glassnode.com/indicators/market-value-to-realized-value/mvrv-ratio

2. **Glassnode Academy**: "HODL Waves"
   - https://academy.glassnode.com/supply/hodl-waves/hodl-waves

3. **ARK Invest + Glassnode**: "Cointime Economics"
   - https://www.ark-invest.com/white-papers/cointime-economics

4. **Contadino Galattico**: Gap Analysis Section
   - Internal evidence-based analysis

---

## Accuracy Projection

```
Current (spec-016):              █████████████████████████████░ 82%
+ UTXO Lifecycle (spec-017):     ██████████████████████████████ 85%+ (+3-5%)
  Enables: MVRV, Realized Cap, HODL Waves, Cointime...
```

This is the **foundation** that enables all Tier A metrics.
