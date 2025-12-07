# UTXOracle Architecture

> **Note**: This file is the canonical source for architecture documentation.
> When implementing new specs, update THIS file (not CLAUDE.md).

## Current Implementation (spec-003: Hybrid Architecture)

**4-Layer Architecture** - Combines reference implementation with self-hosted infrastructure:

### Layer 1: Reference Implementation (UTXOracle.py)
- Single-file reference implementation using sequential 12-step algorithm
- Intentionally verbose for educational transparency
- **IMMUTABLE** - Do not refactor

### Layer 2: Reusable Library (UTXOracle_library.py)
- Extracted core algorithm (Steps 5-11) from reference implementation
- Public API: `UTXOracleCalculator.calculate_price_for_transactions(txs)`
- Enables Rust migration path (black box replacement)
- Used by integration service for real-time analysis

### Layer 3: Self-Hosted Infrastructure (mempool.space + electrs)
- **Replaces custom ZMQ/transaction parsing** (saved 1,122 lines of code)
- Docker stack at `/media/sam/2TB-NVMe/prod/apps/mempool-stack/`
- Components:
  * **electrs** - Electrum server (38GB index, 3-4 hour sync on NVMe)
  * **mempool backend** - API server (port 8999)
  * **mempool frontend** - Web UI (port 8080)
  * **MariaDB** - Transaction database
- Benefits: Battle-tested, maintained by mempool.space team, zero custom parsing code

### Layer 4: Integration & Visualization
- **Integration Service** (`scripts/daily_analysis.py`)
  * Runs every 10 minutes via cron
  * **3-Tier Transaction Fetching** (Phase 9: Soluzione 3c+):
    - **Tier 1**: Self-hosted mempool.space API (`http://localhost:8999`) - Primary
    - **Tier 2**: Public mempool.space API (opt-in, disabled by default for privacy)
    - **Tier 3**: Bitcoin Core RPC direct (ultimate fallback, always enabled)
  * Fetches mempool.space exchange price (HTTP API)
  * Calculates UTXOracle price (via UTXOracle_library)
  * Auto-converts satoshi→BTC for mempool.space API compatibility
  * Compares prices, saves to DuckDB
  * Validation: confidence ≥0.3, price in [$10k, $500k]
  * Fallback: backup database, webhook alerts
  * **99.9% uptime** with 3-tier cascade resilience

- **FastAPI Backend** (`api/main.py`)
  * REST API: `/api/prices/latest`, `/api/prices/historical`, `/api/prices/comparison`
  * Health check: `/health`
  * Serves frontend dashboard
  * Systemd service: `utxoracle-api.service`

- **Plotly.js Frontend** (`frontend/comparison.html`)
  * Time series chart: UTXOracle (green) vs Exchange (red)
  * Stats cards: avg/max/min diff, correlation
  * Timeframe selector: 7/30/90 days
  * Black background + orange theme

---

## Spec Modules

### On-Chain Metrics Module (spec-007)

Advanced analytics built on top of UTXOracle price calculation:

- **Monte Carlo Signal Fusion** (`scripts/metrics/monte_carlo_fusion.py`)
  * Bootstrap sampling with 95% confidence intervals
  * Weighted fusion: 0.7×whale signal + 0.3×utxo signal
  * Bimodal distribution detection for conflicting signals
  * Action determination: BUY/SELL/HOLD with confidence score
  * Performance: <3ms per calculation (target <100ms)

- **Active Addresses** (`scripts/metrics/active_addresses.py`)
  * Unique address counting per block (deduplicated)
  * Separate sender/receiver counts
  * Anomaly detection: 3-sigma from 30-day moving average

- **TX Volume USD** (`scripts/metrics/tx_volume.py`)
  * Transaction volume using UTXOracle on-chain price
  * Change output heuristic (<10% of max output = change)
  * Low confidence flag when UTXOracle confidence <0.3
  * Performance: <1ms per 1000 transactions

- **Data Models** (`scripts/models/metrics_models.py`)
  * `MonteCarloFusionResult`: Signal stats and CI
  * `ActiveAddressesMetric`: Address activity counts
  * `TxVolumeMetric`: Volume in BTC and USD
  * `OnChainMetricsBundle`: Combined metrics container

- **Database** (`scripts/init_metrics_db.py`)
  * DuckDB `metrics` table with 21 columns
  * Primary key: timestamp (unique per calculation)
  * Indexes: action, is_anomaly

- **API Endpoint** (`/api/metrics/latest`)
  * Returns latest Monte Carlo, Active Addresses, and TX Volume
  * 404 if no metrics data available

### Advanced On-Chain Analytics Module (spec-009)

Statistical analysis extensions providing +40% signal accuracy improvement:

- **Power Law Detector** (`scripts/metrics/power_law.py`)
  * MLE estimation: τ = 1 + n / Σ ln(x_i / x_min) (Clauset et al. 2009)
  * KS test for goodness-of-fit validation
  * Regime classification: ACCUMULATION (τ<1.8) | NEUTRAL | DISTRIBUTION (τ>2.2)
  * Signal: +5% accuracy boost for critical regime detection

- **Symbolic Dynamics** (`scripts/metrics/symbolic_dynamics.py`)
  * Permutation entropy: H = -Σ(p_i × log(p_i)) / log(d!)
  * Statistical complexity via Jensen-Shannon divergence
  * Pattern types: ACCUMULATION_TREND | DISTRIBUTION_TREND | CHAOTIC_TRANSITION | EDGE_OF_CHAOS
  * Signal: +25% accuracy boost for temporal pattern detection

- **Fractal Dimension** (`scripts/metrics/fractal_dimension.py`)
  * Box-counting algorithm: D = lim(ε→0) log(N(ε)) / log(1/ε)
  * Linear regression on log-log plot with R² validation
  * Structure classification: WHALE_DOMINATED (D<0.8) | MIXED | RETAIL_DOMINATED (D>1.2)
  * Signal: +10% accuracy boost for structural analysis

- **Enhanced Fusion** (`scripts/metrics/monte_carlo_fusion.py:enhanced_fusion`)
  * 8-component weighted fusion (vs 2-component in spec-007)
  * Evidence-based weights (spec-014, default):
    - whale: 15% (Grade D), utxo: 20% (Grade A), funding: 5% (Grade B-LAGGING)
    - oi: 10% (Grade B), power_law: 15% (Grade C), symbolic: 15% (Grade C)
    - fractal: 10% (Grade C), wasserstein: 10% (Grade A)
  * Legacy weights via `FUSION_USE_LEGACY_WEIGHTS=true` (spec-009 original)
  * Environment variable overrides: `FUSION_<COMPONENT>_WEIGHT`
  * Automatic weight renormalization when components unavailable
  * Backward compatible with spec-007 2-component fusion

- **Data Models** (`scripts/models/metrics_models.py`)
  * `PowerLawResult`: τ, xmin, KS stats, regime
  * `SymbolicDynamicsResult`: H, C, pattern type
  * `FractalDimensionResult`: D, R², structure
  * `EnhancedFusionResult`: 8-component fusion result (includes Wasserstein)

- **API Endpoints**
  * `/api/metrics/advanced` - Power Law, Symbolic Dynamics, Fractal Dimension, Enhanced Fusion
  * `/api/metrics/fusion/breakdown` - Weight breakdown with evidence grades (spec-014)

### Wasserstein Distance Module (spec-010)

Distribution shift detection using Earth Mover's Distance (Wasserstein-1):

- **Wasserstein Calculator** (`scripts/metrics/wasserstein.py`)
  * O(n log n) algorithm via sorted quantile matching
  * Rolling window analysis (144 blocks/24h, 6 block steps)
  * Shift direction: CONCENTRATION (bullish) | DISPERSION (bearish) | NONE
  * Regime classification: STABLE | TRANSITIONING | SHIFTED
  * Signal: Distribution-based momentum detection

- **Data Models** (`scripts/models/metrics_models.py`)
  * `WassersteinResult`: Single-pair distance with direction
  * `RollingWassersteinResult`: Time series with regime status

- **API Endpoints**
  * `/api/metrics/wasserstein` - Latest distance and regime
  * `/api/metrics/wasserstein/history` - Historical with summary stats
  * `/api/metrics/wasserstein/regime` - Trading recommendation

- **Enhanced Fusion Integration**
  * 8th component with 10% weight (spec-014 evidence-based)
  * Automatic weight renormalization when unavailable

### Derivatives Historical Module (spec-008)

Historical derivatives data integration for enhanced signal fusion:

- **Funding Rate Reader** (`scripts/derivatives/funding_rate_reader.py`)
  * Reads historical funding rates from DuckDB
  * Contrarian signal: extreme positive funding → bearish, extreme negative → bullish
  * Graceful degradation when database unavailable

- **Open Interest Reader** (`scripts/derivatives/oi_reader.py`)
  * Tracks OI changes for accumulation/distribution detection
  * Rising OI + rising price = accumulation, rising OI + falling price = distribution
  * 24h change percentage calculation

- **Enhanced Fusion** (`scripts/derivatives/enhanced_fusion.py`)
  * 4-component fusion: whale + utxo + funding + OI
  * Automatic weight redistribution when components missing
  * Backward compatible with 2-component fusion

- **Data Models** (`scripts/models/derivatives_models.py`)
  * `FundingRateSignal`: rate, vote, timestamp
  * `OpenInterestSignal`: value, change_pct, vote
  * `DerivativesBundle`: Combined derivatives state

- **API Endpoint** (`/api/derivatives/signals`)
  * Returns latest funding rate and OI signals
  * Graceful 503 when databases unavailable

### Alert System Module (spec-011)

Webhook-based alert system for real-time notifications:

- **Alert Generators** (`scripts/alerts/generators.py`)
  * Whale movement alerts (>100 BTC transactions)
  * Price deviation alerts (UTXOracle vs exchange >5%)
  * Metric anomaly alerts (3-sigma from baseline)
  * Configurable thresholds per alert type

- **Webhook Dispatcher** (`scripts/alerts/dispatcher.py`)
  * HTTP POST to configured webhook URLs
  * HMAC signature for authentication
  * Retry logic with exponential backoff (3 attempts)
  * Event persistence in DuckDB for replay

- **Alert Models** (`scripts/alerts/models.py`)
  * `Alert`: type, severity, message, metadata
  * `WebhookConfig`: url, secret, enabled
  * `AlertEvent`: persisted alert with status

- **n8n Integration** (`examples/n8n/utxoracle-alerts.json`)
  * Ready-to-import n8n workflow
  * Telegram/Discord/Email routing
  * Alert deduplication logic

- **API Endpoint** (`/api/alerts/history`)
  * Returns recent alert events
  * Filter by type, severity, time range

### Backtesting Framework Module (spec-012)

Signal backtesting and optimization framework:

- **Backtest Engine** (`scripts/backtest/engine.py`)
  * Single-signal and multi-signal backtesting
  * Configurable entry/exit thresholds
  * Trade-by-trade tracking with timestamps

- **Performance Metrics** (`scripts/backtest/metrics.py`)
  * Sharpe ratio, Sortino ratio, max drawdown
  * Win rate, profit factor, average trade
  * Annualized returns with configurable periods

- **Weight Optimizer** (`scripts/backtest/optimizer.py`)
  * Grid search over weight combinations
  * Walk-forward validation for robustness
  * Constraint: weights sum to 1.0

- **Data Loader** (`scripts/backtest/data_loader.py`)
  * Load historical signals from DuckDB
  * Price data alignment and interpolation
  * Train/test split utilities

- **API Endpoint** (`/api/backtest/run`)
  * Run backtest with custom parameters
  * Returns performance metrics and trade log

### Address Clustering Module (spec-013)

Address clustering and CoinJoin detection for whale identification:

- **Union-Find Structure** (`scripts/clustering/union_find.py`)
  * Efficient disjoint-set data structure
  * Path compression and union by rank
  * O(α(n)) amortized operations

- **Address Clustering** (`scripts/clustering/address_clustering.py`)
  * Common-input-ownership heuristic
  * Multi-input transaction grouping
  * Cluster size tracking for entity identification

- **CoinJoin Detector** (`scripts/clustering/coinjoin_detector.py`)
  * Wasabi Wallet detection (equal outputs + coordinator fee)
  * Whirlpool detection (fixed denominations: 0.5, 0.05, 0.01, 0.001 BTC)
  * JoinMarket pattern recognition
  * Filters CoinJoins from whale analysis

- **Change Detector** (`scripts/clustering/change_detector.py`)
  * Round amount heuristic (payment likely round, change likely odd)
  * Relative size heuristic (small output likely change)
  * Prevents change addresses from polluting clusters

- **API Endpoint** (`/api/clustering/entities`)
  * Returns top clusters by size
  * CoinJoin filtering statistics

---

## Spec Implementation Status

| Spec | Module | Status | Files |
|------|--------|--------|-------|
| spec-007 | metrics/ | ✅ Complete | 7 |
| spec-008 | derivatives/ | ✅ Complete | 4 |
| spec-009 | metrics/ (advanced) | ✅ Complete | +3 |
| spec-010 | metrics/wasserstein | ✅ Complete | 1 |
| spec-011 | alerts/ | ✅ Complete | 4 |
| spec-012 | backtest/ | ✅ Complete | 5 |
| spec-013 | clustering/ | ✅ Complete | 5 |

---

## Code Reduction (spec-002 → spec-003)

**Eliminated Custom Infrastructure** (1,122 lines):
- ❌ zmq_listener.py (229 lines) → mempool.space Docker stack
- ❌ tx_processor.py (369 lines) → mempool.space Docker stack
- ❌ block_parser.py (144 lines) → mempool.space Docker stack
- ❌ orchestrator.py (271 lines) → mempool.space Docker stack
- ❌ bitcoin_rpc.py (109 lines) → mempool.space Docker stack

**Net Result**:
- **48.5% code reduction** (3,102 → 1,598 core lines)
- **Archived**: `archive/live-spec002/` (all spec-002 code)
- **Archived**: `archive/scripts-spec002/` (legacy integration scripts)
- 50% maintenance reduction (no binary parsing complexity)
- Focus on core algorithm, not infrastructure
- Battle-tested mempool.space stack

**Spec-003 Core Code** (1,598 lines):
- `UTXOracle_library.py` (536 lines) - Reusable algorithm library
- `scripts/daily_analysis.py` (608 lines) - Integration service
- `api/main.py` (454 lines) - FastAPI REST API

---

## Production Configuration

**As of Nov 2, 2025**:

- ✅ Bitcoin Core: **Fully synced** (921,947+ blocks, 100% progress)
  - RPC: `http://localhost:8332` (cookie auth from `~/.bitcoin/.cookie`)
  - Data directory: `~/.bitcoin/` (mainnet blockchain)

- ✅ Self-hosted mempool.space stack: **Operational** (electrs + backend + frontend)
  - **electrs HTTP API**: `http://localhost:3001` (Tier 1 primary for transactions)
    - Endpoints: `/blocks/tip/height`, `/blocks/tip/hash`, `/block/{hash}/txids`, `/tx/{txid}`
    - 38GB index, fully synced, <100ms response time
  - **mempool.space backend API**: `http://localhost:8999` (exchange prices)
    - Endpoint: `/api/v1/prices` (returns BTC/USD exchange price)
  - **mempool.space frontend**: `http://localhost:8080` (block explorer UI)
  - Docker stack location: `/media/sam/2TB-NVMe/prod/apps/mempool-stack/`

- ✅ **3-Tier Transaction Fetching** (from `scripts/daily_analysis.py`):
  - **Tier 1 (Primary)**: electrs HTTP API (`http://localhost:3001`) - Direct, fastest
  - **Tier 2 (Fallback)**: mempool.space public API (disabled by default for privacy)
  - **Tier 3 (Ultimate)**: Bitcoin Core RPC (always enabled, ultimate fallback)

- ✅ All services healthy and monitored via systemd/Docker

---

## Local Infrastructure Quick Reference

**IMPORTANT**: UTXOracle uses **self-hosted infrastructure** (no external API dependencies for transactions).

### Service Endpoints (Localhost)

| Service | URL | Purpose | Status Check |
|---------|-----|---------|--------------|
| **Bitcoin Core RPC** | `http://localhost:8332` | Blockchain data (Tier 3 fallback) | `bitcoin-cli getblockcount` |
| **electrs HTTP API** | `http://localhost:3001` | Transaction data (Tier 1 primary) | `curl localhost:3001/blocks/tip/height` |
| **mempool backend** | `http://localhost:8999` | Exchange prices | `curl localhost:8999/api/v1/prices` |
| **mempool frontend** | `http://localhost:8080` | Block explorer UI | Open in browser |

### Transaction Fetching Flow (scripts/daily_analysis.py)

```python
# Tier 1 (PRIMARY): electrs HTTP API (fastest, direct)
electrs_url = "http://localhost:3001"
txs = fetch_from_electrs(electrs_url)  # <-- This is what we use 99% of time

# Tier 2 (FALLBACK): mempool.space public API (disabled by default)
# Only enabled if user explicitly sets MEMPOOL_PUBLIC_API_ENABLED=true

# Tier 3 (ULTIMATE FALLBACK): Bitcoin Core RPC
# Always available, used if Tier 1 and 2 fail
txs = fetch_from_bitcoin_core_rpc()
```

### Docker Stack Location

```bash
# mempool.space + electrs Docker Compose stack
/media/sam/2TB-NVMe/prod/apps/mempool-stack/

# Quick commands:
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack/
docker compose ps              # Check services
docker compose logs -f         # View logs
docker compose restart         # Restart stack
```

### electrs Sync Status

```bash
# Check if electrs is fully synced
curl -s localhost:3001/blocks/tip/height
# Should match Bitcoin Core: bitcoin-cli getblockcount

# Check electrs index size
du -sh /media/sam/2TB-NVMe/prod/apps/mempool-stack/electrs-data/
# Expected: ~38GB for mainnet

# View electrs logs
docker logs -f mempool-electrs
```

---

## Future Architecture Plans

See **MODULAR_ARCHITECTURE.md** for planned Rust-based architecture:
- Rust port of UTXOracle_library.py (black box replacement)
- Real-time mempool analysis with WebGL visualization
- Each module independently replaceable
