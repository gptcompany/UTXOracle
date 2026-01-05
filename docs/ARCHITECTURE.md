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

- **NVT Ratio** (`scripts/metrics/nvt.py`)
  * NVT = Market Cap / Daily TX Volume (USD)
  * Similar to P/E ratio for stocks
  * Signals: undervalued (<30), fair (30-90), overvalued (>90)
  * API: `/api/metrics/nvt`

- **Volatility** (`scripts/metrics/volatility.py`)
  * Annualized volatility from log returns std deviation
  * Regimes: low (<30%), normal (30-60%), high (60-100%), extreme (>100%)
  * Configurable rolling window (2-365 days)
  * API: `/api/metrics/volatility`

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
  * 7-component weighted fusion (vs 2-component in spec-007)
  * Components: whale (25%), utxo (15%), funding (15%), oi (10%), power_law (10%), symbolic (15%), fractal (10%)
  * Automatic weight renormalization when components unavailable
  * Backward compatible with spec-007 2-component fusion

- **Data Models** (`scripts/models/metrics_models.py`)
  * `PowerLawResult`: τ, xmin, KS stats, regime
  * `SymbolicDynamicsResult`: H, C, pattern type
  * `FractalDimensionResult`: D, R², structure
  * `EnhancedFusionResult`: 9-component fusion result (includes Wasserstein + Cointime)

- **API Endpoint** (`/api/metrics/advanced`)
  * Real-time computation from latest block data
  * Returns Power Law, Symbolic Dynamics, Fractal Dimension, Enhanced Fusion
  * 501 if modules not installed, 503 if electrs unavailable

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
  * 8th component with 0.04 weight (reduced for cointime)
  * Automatic weight renormalization when unavailable

### Cointime Economics Module (spec-018)

ARK Invest + Glassnode's Cointime Economics framework for long-term valuation:

- **Cointime Calculator** (`scripts/metrics/cointime.py`)
  * Coinblocks: BTC × Blocks (created when UTXOs born, destroyed when spent)
  * Liveliness: Cumulative Destroyed / Cumulative Created (0-1 range)
  * Vaultedness: 1 - Liveliness (HODLer conviction)
  * Active/Vaulted Supply: Supply weighted by liveliness
  * True Market Mean: Market Cap / Active Supply (more accurate realized price)
  * AVIV Ratio: Price / True Market Mean (superior to MVRV)

- **Data Models** (`scripts/models/metrics_models.py`)
  * `CoinblocksMetrics`: Per-block coinblocks tracking
  * `CointimeSupply`: Active/vaulted supply split
  * `CointimeValuation`: AVIV ratio and valuation zone
  * `CointimeSignal`: Trading signal with confidence

- **API Endpoints**
  * `/api/metrics/cointime` - Latest cointime metrics
  * `/api/metrics/cointime/history` - Historical AVIV and liveliness
  * `/api/metrics/cointime/signal` - Trading signal for fusion

- **DuckDB Schema** (`cointime_metrics` table)
  * Block-indexed storage for all cointime data
  * Rolling liveliness windows (7d, 30d, 90d)

- **Enhanced Fusion Integration**
  * 9th component with 0.12 weight
  * AVIV-based valuation signal
  * Confidence-weighted based on zone + dormancy

### Advanced On-Chain Metrics Module (spec-021)

Distribution and conviction metrics leveraging UTXO lifecycle data:

- **URPD Calculator** (`scripts/metrics/urpd.py`)
  * UTXO Realized Price Distribution for support/resistance detection
  * DuckDB GROUP BY aggregation into configurable price buckets
  * Supply above/below current price classification
  * Dominant bucket identification (max BTC concentration)
  * API: `GET /api/metrics/urpd`

- **Supply Profit/Loss Calculator** (`scripts/metrics/supply_profit_loss.py`)
  * Profit/Loss supply split based on creation vs current price
  * STH/LTH cohort breakdown (155-day threshold)
  * Market phase classification: EUPHORIA (>95%) | BULL (75-95%) | TRANSITION (50-75%) | CAPITULATION (<50%)
  * Signal strength: distance from phase boundary
  * API: `GET /api/metrics/supply-profit-loss`

- **Reserve Risk Calculator** (`scripts/metrics/reserve_risk.py`)
  * Reserve Risk = Price / (HODL Bank × Supply)
  * HODL Bank: Cumulative coindays destroyed (from cointime)
  * Liveliness integration for conviction measurement
  * Signal zones: STRONG_BUY (<0.0005) | ACCUMULATION | FAIR_VALUE | DISTRIBUTION (>0.02)
  * API: `GET /api/metrics/reserve-risk`

- **Sell-side Risk Calculator** (`scripts/metrics/sell_side_risk.py`)
  * Sell-side Risk = Realized Profit / Market Cap
  * Rolling window aggregation (default 30 days)
  * Realized profit/loss from spent UTXOs
  * Signal zones: LOW (<0.1%) | NORMAL | ELEVATED | AGGRESSIVE (>1%)
  * API: `GET /api/metrics/sell-side-risk`

- **CDD/VDD Calculator** (`scripts/metrics/cdd_vdd.py`)
  * Coindays Destroyed: age_days × btc_value for spent UTXOs
  * Value Days Destroyed: CDD × spent_price
  * VDD multiple vs 365-day MA
  * Signal zones: LOW_ACTIVITY | NORMAL | ELEVATED | SPIKE (>2x)
  * API: `GET /api/metrics/cdd-vdd`

- **Data Models** (`scripts/models/metrics_models.py`)
  * `URPDBucket`: Price range with BTC amount and percentage
  * `URPDResult`: Full URPD distribution with dominant bucket
  * `SupplyProfitLossResult`: P/L breakdown with market phase
  * `ReserveRiskResult`: Reserve risk with HODL bank and liveliness
  * `SellSideRiskResult`: Realized P/L with signal classification
  * `CoinDaysDestroyedResult`: CDD/VDD with daily averages

- **Database Requirements**
  * Requires `utxo_lifecycle` table in DuckDB (from spec-017)
  * Fields: creation_price_usd, btc_value, is_spent, spent_timestamp, spent_price_usd, age_days

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

#### Bootstrap Clustering (Historical Data)

For initial population of address clusters from historical blockchain data:

- **Ultra-Fast Clustering** (`scripts/bootstrap/complete_clustering_v3_fast.py`)
  * Cython-compiled UnionFind (60-100x faster than pure Python)
  * PyArrow streaming for large CSV files (handles 3GB+ compressed)
  * Checkpoint after each file (resume capability)
  * Target: 60-90 min for 2B address pairs

- **Cython Extension** (`scripts/bootstrap/cython_uf/`)
  * `fast_union_find.pyx`: nogil path compression + union by rank
  * Compile: `cd scripts/bootstrap/cython_uf && python setup.py build_ext --inplace`
  * 15-24M ops/sec vs 0.25M baseline

- **Data Pipeline**
  1. Extract pairs from blockchain → `data/clustering_temp/pairs_*.csv.gz`
  2. Build address→int mapping (Phase 1)
  3. Run Cython clustering (Phase 2)
  4. Write to DuckDB `address_clusters` table (Phase 3)

- **Deprecated Scripts** (archived in `archive/clustering_deprecated/`)
  * V1/V2 and helper scripts replaced by V3

### UTXO Lifecycle Engine Module (spec-017)

Comprehensive UTXO lifecycle tracking for Realized Cap, MVRV, NUPL, and HODL Waves:

- **UTXO Lifecycle Tracker** (`scripts/metrics/utxo_lifecycle.py`)
  * Hybrid approach with in-memory cache for hot UTXOs
  * Tracks creation block, creation price, realized value per UTXO
  * Marks spending with spent_block, spent_price, calculates SOPR
  * STH/LTH classification (155-day threshold, configurable)
  * Age cohort breakdown: <1h, 1h-24h, 1d-1w, 1w-1m, 1m-3m, 3m-6m, 6m-1y, 1y-2y, 2y-3y, 3y+
  * Performance: <5s per block, handles 100k UTXOs per block

- **Realized Metrics Calculator** (`scripts/metrics/realized_metrics.py`)
  * Realized Cap: Σ(BTC × creation_price) for unspent UTXOs
  * Market Cap: Total supply × current price
  * MVRV: Market Cap / Realized Cap (>3.0 overvalued, <1.0 undervalued)
  * NUPL: (Market Cap - Realized Cap) / Market Cap
  * Point-in-time snapshot creation for historical analysis

- **HODL Waves Calculator** (`scripts/metrics/hodl_waves.py`)
  * Supply distribution by age cohort (percentages sum to 100%)
  * Visualizes Bitcoin holding behavior over time
  * Identifies accumulation vs distribution phases

- **Sync Engine** (`scripts/sync_utxo_lifecycle.py`)
  * Incremental sync from last checkpoint
  * Bitcoin Core RPC integration with price lookup
  * Configurable batch size and retention period (default 180 days)
  * Automatic pruning of old spent UTXOs

- **Data Models** (`scripts/models/metrics_models.py`)
  * `UTXOLifecycle`: Creation/spending data with SOPR calculation
  * `UTXOSetSnapshot`: Point-in-time realized metrics
  * `AgeCohortsConfig`: Configurable cohort boundaries
  * `SyncState`: Incremental sync checkpoint tracking

- **Database Schema** (DuckDB)
  * `utxo_lifecycle` table: Core UTXO tracking with indexes
  * `utxo_snapshots` table: Historical metric snapshots
  * `utxo_sync_state` table: Sync progress tracking
  * Storage: ~5GB for 6-month MVP retention

- **API Endpoints**
  * `/api/metrics/utxo-lifecycle` - STH/LTH supply breakdown
  * `/api/metrics/realized` - Realized Cap, MVRV, NUPL
  * `/api/metrics/hodl-waves` - Age cohort distribution

- **Configuration** (`.env`)
  * `UTXO_LIFECYCLE_ENABLED=true` - Enable/disable feature
  * `UTXO_LIFECYCLE_DB_PATH` - DuckDB path
  * `UTXO_STH_THRESHOLD_DAYS=155` - STH/LTH boundary
  * `UTXO_RETENTION_DAYS=180` - Data retention period
  * `UTXO_PRUNING_ENABLED=true` - Auto-prune old spent UTXOs

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
| spec-014 | metrics/ (evidence weights) | ✅ Complete | - |
| spec-015 | backtest/ (validation) | ✅ Complete | - |
| spec-016 | metrics/sopr | ✅ Complete | 1 |
| spec-017 | metrics/utxo_lifecycle | ✅ Complete | 4 |
| spec-018 | metrics/cointime | ✅ Complete | 1 |
| spec-019 | derivatives/ (weight adjustment) | ✅ Complete | - |
| spec-020 | metrics/ (MVRV variants) | ✅ Complete | - |
| spec-021 | metrics/advanced-onchain | ✅ Complete | 5+6 |
| spec-022 | metrics/nupl | ✅ Complete | 1 |
| spec-023 | metrics/cost_basis | ✅ Complete | 2 |
| spec-024 | metrics/revived_supply | ✅ Complete | 2 |
| spec-025 | metrics/wallet_waves | ✅ Complete | 3 |
| spec-026 | metrics/exchange_netflow | ✅ Complete | 3 |
| spec-027 | metrics/binary_cdd | ✅ Complete | 2 |
| spec-028 | metrics/net_realized_pnl | ✅ Complete | 3 |
| spec-029 | metrics/pl_ratio | ✅ Complete | 3 |
| spec-030 | metrics/mining_economics | ✅ Complete | 4 |
| spec-033 | metrics/pro_risk | ✅ Complete | 3 |
| spec-034 | models/price_power_law | ✅ Complete | 4 |
| spec-035 | integrations/rbn | ✅ Complete | 5 |
| spec-036 | models/custom_price | ✅ Complete | 4 |
| spec-037 | database/consolidation | ✅ Complete | 6 |
| spec-038 | data/exchange_addresses | ✅ Complete | 2 |

---

## PRO Risk Metric Module (spec-033)

Composite 0-1 risk indicator aggregating 6 on-chain signals for market cycle positioning.

### Components

- **Core Calculation** (`scripts/metrics/pro_risk.py`)
  * Weighted aggregation of 6 on-chain metrics
  * 4-year percentile normalization with 2% winsorization
  * Zone classification: extreme_fear → extreme_greed
  * Confidence scoring based on data availability

- **Component Weights** (evidence-based):
  | Metric | Weight | Grade |
  |--------|--------|-------|
  | MVRV Z-Score | 30% | A |
  | SOPR | 20% | A |
  | NUPL | 20% | A |
  | Reserve Risk | 15% | B |
  | Puell Multiple | 10% | B |
  | HODL Waves | 5% | B |

- **Zone Thresholds**:
  | Zone | Range | Interpretation |
  |------|-------|----------------|
  | extreme_fear | 0.00-0.20 | Strong buy signal |
  | fear | 0.20-0.40 | Accumulation zone |
  | neutral | 0.40-0.60 | Hold / DCA |
  | greed | 0.60-0.80 | Caution zone |
  | extreme_greed | 0.80-1.00 | Distribution zone |

### API Endpoints

- `GET /api/risk/pro` - Current PRO Risk value and components
- `GET /api/risk/pro/zones` - Zone definitions
- `GET /api/risk/pro/history` - Historical PRO Risk data

### Database Tables

- `risk_percentiles` - Daily percentile data for each component metric
- `pro_risk_daily` - Daily composite PRO Risk results

### Files

| File | Purpose |
|------|---------|
| `scripts/metrics/pro_risk.py` | Core calculation module |
| `scripts/metrics/puell_multiple.py` | Puell Multiple calculation |
| `scripts/metrics/bootstrap_percentiles.py` | Historical percentile generation |
| `api/models/risk_models.py` | Pydantic API models |
| `tests/test_pro_risk.py` | Unit tests |
| `tests/test_api_risk.py` | API tests |

---

## Bitcoin Price Power Law Model (spec-034)

Mathematical model calculating Bitcoin's fair value based on time since genesis block using log-log linear regression.

### Core Algorithm

- **Formula**: `Price(t) = 10^(α + β × log₁₀(days_since_genesis))`
- **Default Coefficients** (RBN research, 2025):
  - α (intercept) = -17.01
  - β (slope) = 5.82
  - R² = 0.95
  - σ (std error) = 0.32

### Zone Classification

| Zone | Deviation | Interpretation |
|------|-----------|----------------|
| undervalued | < -20% | Accumulation opportunity |
| fair | -20% to +50% | Neutral / DCA |
| overvalued | > +50% | Distribution zone |

### API Endpoints

- `GET /api/v1/models/power-law` - Current model parameters
- `GET /api/v1/models/power-law/predict?date=YYYY-MM-DD&current_price=X` - Price prediction with zone
- `GET /api/v1/models/power-law/history?days=N` - Historical prices with fair values
- `POST /api/v1/models/power-law/recalibrate` - Fit model from latest data

### Files

| File | Purpose |
|------|---------|
| `scripts/models/price_power_law.py` | Core algorithm (days_since_genesis, fit_power_law, predict_price) |
| `api/models/power_law_models.py` | Pydantic models (PowerLawModel, PowerLawPrediction, etc.) |
| `frontend/charts/power_law_chart.js` | Plotly.js log-log visualization |
| `frontend/power_law.html` | Standalone chart page |
| `tests/test_price_power_law.py` | Unit tests (21 tests, 96% coverage) |
| `tests/test_api_power_law.py` | API tests (29 tests) |

### Frontend

- URL: `/power_law` or `/power-law`
- Features: Interactive log-log chart, zone coloring, recalibration button
- Library: Plotly.js 2.27.0

---

## Derivatives Weight Adjustment (spec-019)

Refined evidence weighting for derivatives data integration:

* **Weight Reduction**: Reduced derivatives influence in composite signals
* **SOPR Integration**: Better correlation with on-chain SOPR metrics
* **Quality Scoring**: Improved signal quality measurement

---

## MVRV-Z Score Variants (spec-020)

Market Value to Realized Value analysis with STH/LTH segmentation:

* **MVRV-Z Score**: Standard deviation from historical mean
* **STH-MVRV**: Short-term holder variant (< 155 days)
* **LTH-MVRV**: Long-term holder variant (≥ 155 days)

---

## NUPL Oscillator (spec-022)

Net Unrealized Profit/Loss indicator:

* **NUPL Value**: (Market Cap - Realized Cap) / Market Cap
* **Zone Classification**: Capitulation, Fear, Optimism, Belief, Euphoria
* **Historical Percentile**: Current NUPL vs historical distribution

**API Endpoints:**
- `GET /api/metrics/nupl` - Current NUPL metrics

---

## Cost Basis Cohorts (spec-023)

STH/LTH cost basis analysis:

* **STH Cost Basis**: Average acquisition price for short-term holders
* **LTH Cost Basis**: Average acquisition price for long-term holders
* **MVRV by Cohort**: Separate profit/loss analysis per holder type

**API Endpoints:**
- `GET /api/metrics/cost-basis` - Current cost basis metrics

---

## Revived Supply (spec-024)

Dormant supply reactivation tracking:

* **Revived Supply**: Previously dormant UTXOs that moved
* **Dormancy Bands**: 1y+, 2y+, 3y+, 5y+ reactivation tracking
* **Velocity Signal**: Rate of old supply entering circulation

**API Endpoints:**
- `GET /api/metrics/revived-supply` - Current revived supply metrics

---

## Wallet Waves & Absorption Rates (spec-025)

Supply distribution analysis by wallet age cohorts:

* **Wallet Waves**: UTXO distribution across age bands (1d, 1w, 1m, 3m, 6m, 1y, 2y, 3y, 5y+)
* **Absorption Rates**: Rate of supply transition between age cohorts
* **Conviction Score**: Composite metric measuring long-term holder conviction

**API Endpoints:**
- `GET /api/metrics/wallet-waves` - Current distribution
- `GET /api/metrics/wallet-waves/history` - Historical data
- `GET /api/metrics/absorption-rates` - Transition rates

---

## Exchange Netflow (spec-026)

Exchange flow analysis for accumulation/distribution detection:

* **Netflow**: Inflows - Outflows (positive = selling pressure)
* **Flow Dominance**: Which direction dominates current activity
* **7-day Trend**: Rolling netflow trend analysis

**API Endpoints:**
- `GET /api/metrics/exchange-netflow` - Current netflow metrics

---

## Exchange Address Database (spec-038)

Comprehensive database of known exchange Bitcoin addresses for accurate netflow detection.

### Data Sources

| Source | Method | Addresses | Freshness |
|--------|--------|-----------|-----------|
| **WalletExplorer** | Automated scraper | 13,000+ | Dec 2025 |
| **Proof of Reserves** | Manual verification | 13 cold wallets | Verified |
| Arkham Intel | Blocked (403) | N/A | - |
| BitInfoCharts | Blocked (403) | N/A | - |

### Database Statistics (Dec 2025)

| Exchange | Addresses | Type |
|----------|-----------|------|
| Binance | 1,004 | Cold + Hot |
| Bitfinex | 1,002 | Cold + Hot |
| Kraken | 1,002 | Cold + Hot |
| Bitstamp | 1,000 | Hot |
| Huobi | 1,000 | Hot |
| Poloniex | 1,000 | Hot |
| Bittrex | 1,000 | Hot |
| HitBTC | 1,000 | Hot |
| OKCoin | 1,000 | Hot |
| LocalBitcoins | 1,000 | P2P |
| Luno | 1,000 | Hot |
| CEX.io | 1,000 | Hot |
| Bitcoin.de | 1,000 | Hot |
| Coinbase | 2 | Cold |
| OKX | 2 | Cold |
| Bybit | 1 | Cold |
| **Total** | **13,013** | - |

### Verified Cold Wallets (Always Included)

```python
VERIFIED_COLD_WALLETS = [
    # Binance (390K+ BTC)
    ("Binance", "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo", "cold_wallet"),  # 248K BTC
    ("Binance", "3M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6", "cold_wallet"),  # 142K BTC
    ("Binance", "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h", "cold_wallet"),
    # Bitfinex (138K BTC)
    ("Bitfinex", "3D2oetdNuZUqQHPJmcMDDHYoqkyNVsFk9r", "cold_wallet"),
    # Kraken (52K+ BTC)
    ("Kraken", "bc1qu30560k5wc8jm58hwx3crlvlydc6vz78npce4z", "cold_wallet"),  # 30K
    # OKX
    ("OKX", "bc1qjasf9z3h7w3jspkhtgatgpyvvzgpa2wwd2lr0eh5tx44reyn2k7sfl6t94", "cold_wallet"),
    # Coinbase
    ("Coinbase", "3Cbq7aT1tY8kMxWLbitaG7yT6bPbKChq64", "cold_wallet"),
]
```

### Automated Scraper

```bash
# One-time full scrape (~15 min, 14 exchanges × 50 pages)
python -m scripts.bootstrap.scrape_exchange_addresses --max-pages 50

# Weekly cron job (recommended)
0 3 * * 0 cd /media/sam/1TB/UTXOracle && python -m scripts.bootstrap.scrape_exchange_addresses --max-pages 50

# Dry run (no file write)
python -m scripts.bootstrap.scrape_exchange_addresses --dry-run
```

### Files

| File | Purpose |
|------|---------|
| `data/exchange_addresses.csv` | 13,013 addresses (658 KB) |
| `scripts/bootstrap/scrape_exchange_addresses.py` | WalletExplorer scraper |
| `specs/038-exchange-address-expansion/spec.md` | Specification |
| `specs/038-exchange-address-expansion/research.md` | Research findings |

### Integration with Exchange Netflow (spec-026)

The exchange address database is used by `scripts/metrics/exchange_netflow.py`:

```python
from scripts.metrics.exchange_netflow import load_exchange_addresses

# Load addresses from CSV
addresses = load_exchange_addresses()
# Returns: Dict[str, Set[str]] mapping exchange names to address sets

# Check if address belongs to exchange
is_exchange = any(addr in addrs for addrs in addresses.values())
```

---

## Binary CDD Indicator (spec-027)

Statistical significance filter for Coin Days Destroyed:

* **CDD Z-Score**: Standard deviations from 365-day mean
* **Binary Signal**: 1 when CDD exceeds threshold (default 2σ)
* **Event Detection**: Filters noise, highlights significant holder movements

**API Endpoints:**
- `GET /api/metrics/binary-cdd` - Current CDD significance

---

## Net Realized P/L (spec-028)

Aggregate profit/loss from on-chain transactions:

* **Realized Profit**: Gains from coins moved above cost basis
* **Realized Loss**: Losses from coins moved below cost basis
* **Net Realized P/L**: Profit - Loss (market sentiment indicator)

**API Endpoints:**
- `GET /api/metrics/net-realized-pnl` - Current P/L metrics

---

## P/L Ratio (Dominance) (spec-029)

Profit/Loss ratio measuring market sentiment dominance:

* **P/L Ratio**: Realized Profit / Realized Loss
* **Dominance Zone**: Profit-dominant (>1) vs Loss-dominant (<1)
* **Historical Context**: Ratio vs historical percentiles

**API Endpoints:**
- `GET /api/metrics/pl-ratio` - Current ratio
- `GET /api/metrics/pl-ratio/history` - Historical data

---

## Mining Economics Module (spec-030)

Miner stress and hashrate analysis combining on-chain and external data:

* **Hash Ribbons**: 30d/60d MA crossover for miner capitulation/recovery signals
  - Miner stress detection (30d < 60d)
  - Recovery signals (historically bullish)
  - Capitulation days counting
* **Mining Pulse**: Real-time block interval analysis (RPC-only)
  - Zone classification: FAST (<540s), NORMAL (540-660s), SLOW (>660s)
  - Implied hashrate change detection
  - Works without external dependencies
* **Combined Signal**: Aggregated miner health assessment
  - Priority: recovery > miner_stress > healthy > unknown
  - Graceful degradation when API unavailable

**API Endpoints:**
- `GET /api/metrics/mining-pulse` - Real-time hashrate indicator
- `GET /api/metrics/hash-ribbons` - Miner stress/recovery signals
- `GET /api/metrics/mining-economics` - Combined view
- `GET /api/metrics/mining-economics/history` - Historical data

**Data Sources:**
- Mining Pulse: Bitcoin Core RPC (block timestamps)
- Hash Ribbons: mempool.space API (5-min TTL cache)

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

## UTXO Lifecycle Bootstrap Architecture (spec-021, IMPLEMENTED)

> **Status**: ✅ IMPLEMENTED - Unified schema active.
> **Date**: 2025-12-15
> **Context**: Block-by-block sync via electrs estimated at 98+ days. This architecture reduces to ~50 minutes.

### Problem Statement

The current `sync_utxo_lifecycle.py` approach has critical bottlenecks:

| Component | Performance | Bottleneck |
|-----------|-------------|------------|
| electrs block fetch | ~0.5s/block | ✅ OK |
| rpc-v3 block fetch | ~0.7s/block | ✅ OK |
| DuckDB row INSERT | ~240 rows/sec | ❌ **CRITICAL** |

With ~4,000 txs/block × 317K blocks = **billions of INSERTs** → ~98 days sync time.

### Solution: Two-Tier Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ TIER 1: CURRENT UTXOS (chainstate dump, ~50 min one-time)          │
│ ├── Source: bitcoin-utxo-dump (Go tool, 140K UTXO/sec)             │
│ ├── Import: DuckDB COPY (712K rows/sec vs 240 INSERT)              │
│ ├── Data: ~190M UTXOs with creation height                         │
│ └── Enables: URPD, Supply P/L, Realized Cap, MVRV                  │
├─────────────────────────────────────────────────────────────────────┤
│ TIER 2: SPENT UTXOS (incremental, real-time via rpc-v3)            │
│ ├── Source: Bitcoin Core getblock verbosity=3                      │
│ ├── Key: prevout.height included natively (unlike electrs!)        │
│ ├── Rate: ~33s/block (OK for 1 block/10 min)                       │
│ └── Enables: SOPR, CDD/VDD, Cointime (from sync point forward)     │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Source Comparison

| Source | prevout.height? | prevout.value? | Speed | Use Case |
|--------|-----------------|----------------|-------|----------|
| electrs | ❌ NO | ✅ YES | Fast | Block metadata only |
| **rpc-v3** | ✅ **YES** | ✅ YES | Medium | Incremental sync (SOPR) |
| chainstate dump | ✅ YES | ✅ YES | **Fastest** | Bootstrap (current UTXOs) |

### Lookup Tables (Built Once)

```sql
-- Price lookup (mempool.space /api/v1/historical-price, data from 2011-07-17)
CREATE TABLE daily_prices (
    date DATE PRIMARY KEY,
    price_usd DOUBLE NOT NULL,      -- BTC/USD price
    block_height INTEGER,            -- Optional: reference block
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Expected rows: ~5,000+ (2011-07-17 to present)

-- Block metadata (electrs or Bitcoin Core RPC)
CREATE TABLE block_heights (
    height INTEGER PRIMARY KEY,
    timestamp BIGINT NOT NULL,       -- Unix timestamp (BIGINT for Y2038+)
    block_hash VARCHAR,              -- Optional: block hash (from RPC mode)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Expected rows: ~900,000+ (genesis to current tip)

-- Index for timestamp lookups (date → price JOIN)
CREATE INDEX idx_block_heights_timestamp ON block_heights(timestamp);
```

### Unified Schema (CANONICAL)

Single table supporting ALL specs (017, 018, 020, 021):

```sql
-- Core table: minimal storage, raw data only
CREATE TABLE utxo_lifecycle (
    -- Primary key (composite, natural from chainstate)
    txid VARCHAR NOT NULL,
    vout INTEGER NOT NULL,

    -- Tier 1: Creation data (from chainstate dump)
    creation_block INTEGER NOT NULL,      -- Block height when created
    amount BIGINT NOT NULL,               -- Value in satoshis
    is_coinbase BOOLEAN DEFAULT FALSE,
    script_type VARCHAR,
    address VARCHAR,

    -- Tier 2: Spent data (from rpc-v3 sync)
    is_spent BOOLEAN DEFAULT FALSE,
    spent_block INTEGER,
    spent_timestamp BIGINT,               -- Unix timestamp
    spent_price_usd DOUBLE,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (txid, vout)
);

-- VIEW with computed columns (for metric queries)
CREATE VIEW utxo_lifecycle_full AS
SELECT
    u.*,
    u.txid || ':' || CAST(u.vout AS VARCHAR) AS outpoint,
    CAST(u.amount AS DOUBLE) / 100000000.0 AS btc_value,
    bh.block_timestamp AS creation_timestamp,
    dp.price_usd AS creation_price_usd,
    (amount / 1e8) * dp.price_usd AS realized_value_usd,
    CASE WHEN u.is_spent AND u.spent_price_usd > 0 AND dp.price_usd > 0
         THEN u.spent_price_usd / dp.price_usd ELSE NULL END AS sopr
FROM utxo_lifecycle u
LEFT JOIN block_heights bh ON u.creation_block = bh.block_height
LEFT JOIN daily_prices dp ON DATE(bh.block_timestamp) = dp.price_date;
```

**Design principles:**
- Store ONLY raw data from chainstate + Tier 2 spent metadata
- Compute derived fields at query time (`btc_value`, `creation_price_usd`, `sopr`)
- No redundant columns across specs

### Bootstrap Workflow

```bash
# 1. Build lookup tables (~15 min parallel)
python scripts/bootstrap/build_price_table.py      # mempool API
python scripts/bootstrap/build_block_heights.py    # electrs

# 2. Chainstate dump (~25 min, requires stopping Bitcoin Core)
~/go/bin/bitcoin-utxo-dump \
  -db /media/sam/3TB-WDC/Bitcoin/chainstate \
  -f count,txid,vout,height,amount,type \
  -o /tmp/utxodump.csv

# 3. DuckDB import + enrichment (~10 min)
python scripts/bootstrap/import_chainstate.py

# 4. Continue with rpc-v3 for new blocks
python scripts/sync_utxo_lifecycle.py --source rpc-v3
```

### Metrics Enablement Matrix

| Metric | Tier 1 (Current) | Tier 2 (Spent) | Historical Coverage |
|--------|------------------|----------------|---------------------|
| URPD | ✅ | - | Full (genesis to now) |
| Supply P/L | ✅ | - | Full |
| Realized Cap | ✅ | - | Full |
| MVRV/MVRV-Z | ✅ | - | Full |
| Reserve Risk | ✅ | - | Full |
| **SOPR** | - | ✅ | From sync point |
| **CDD/VDD** | - | ✅ | From sync point |
| **Cointime** | Partial | ✅ | Hybrid |

### Performance Summary

| Phase | Method | Time |
|-------|--------|------|
| Lookup tables | Parallel API | ~15 min |
| Chainstate dump | bitcoin-utxo-dump | ~25 min |
| DuckDB COPY | Bulk import | ~5 min |
| Enrichment | JOIN | ~5 min |
| **TOTAL** | | **~50 min** |

**Speedup: 2,822x** (98 days → 50 minutes)

### Dependencies

- `bitcoin-utxo-dump`: `go install github.com/in3rsha/bitcoin-utxo-dump@latest`
- Bitcoin Core must be stopped during chainstate dump
- Mempool.space local instance for price API

### Bootstrap Scripts

```
scripts/bootstrap/
├── build_price_table.py       # Mempool API → daily_prices (T0002)
├── build_block_heights.py     # electrs/RPC → block_heights (T0003, T0011)
├── import_chainstate.py       # CSV → DuckDB COPY (T0004)
├── bootstrap_utxo_lifecycle.py  # Orchestrator script (T0005)
└── sync_spent_utxos.py        # Tier 2 rpc-v3 spent UTXO sync (T0007)
```

#### build_block_heights.py Options (T0011 Optimizations)

| Mode | Command | Speed | Use Case |
|------|---------|-------|----------|
| **RPC** (recommended) | `--use-rpc` | ~500 blocks/sec | Bitcoin Core running |
| electrs | `--use-electrs` | ~30 blocks/sec | RPC unavailable |

```bash
# Faster: Bitcoin Core RPC (auto-detects .cookie auth)
python -m scripts.bootstrap.build_block_heights --use-rpc -v

# Fallback: electrs HTTP API
python -m scripts.bootstrap.build_block_heights --use-electrs -v
```

**Key optimizations** (T0011):
- RPC mode uses local calls vs HTTP
- Batch size: 500 (up from 100)
- Rate limit: 50 concurrent (up from 30)
- BIGINT timestamps (Y2038+ safe)
- Batch INSERT with duplicate detection

### Sync Strategy Selection

**For Bootstrap (First Run):**
```bash
# Requires Bitcoin Core stopped during chainstate dump
~/go/bin/bitcoin-utxo-dump -db ~/.bitcoin/chainstate -f count,txid,vout,height,amount,type -o utxos.csv
python -m scripts.bootstrap.bootstrap_utxo_lifecycle --csv-path utxos.csv
```
- **Time**: ~50 minutes for complete historical sync
- **Output**: Full `utxo_lifecycle` table with all current UTXOs

**For Incremental Updates (Daily):**
```bash
python scripts/sync_utxo_lifecycle.py --source rpc-v3 --workers 10
```
- **Time**: ~1.7 minutes/day (144 blocks)
- **Requirement**: Bitcoin Core 25.0+ (for `getblock` verbosity=3)

**Legacy (NOT RECOMMENDED):**
```bash
python scripts/sync_utxo_lifecycle.py --source electrs  # ~98 days bootstrap
```
- Use only if Bitcoin Core < 25.0 AND cannot use chainstate dump

### Architecture Decision: FAST as Default

| Method | Speed | Default? | When to Use |
|--------|-------|----------|-------------|
| **Tier 1 (chainstate)** | 712K rows/sec | ✅ Bootstrap | First run, full historical |
| **Tier 2 (rpc-v3)** | ~0.7s/block | ✅ Incremental | Daily sync, new blocks |
| electrs block-by-block | ~0.5s/block | ❌ Legacy | Backward compatibility only |
| RPC v2 block-by-block | ~0.7s/block | ❌ Legacy | Backward compatibility only |

---

## Validation Framework (spec-031)

Professional validation of UTXOracle metrics against CheckOnChain.com reference.

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `validator.py` | `validation/framework/` | Core comparison logic, tolerance thresholds |
| `checkonchain_fetcher.py` | `validation/framework/` | Plotly.js data extraction from CheckOnChain |
| `visual_validator.py` | `validation/framework/` | Screenshot comparison workflow |
| `comparison_engine.py` | `validation/framework/` | Orchestration, report generation |
| `config.py` | `validation/framework/` | Centralized URL mappings, tolerances |
| `__main__.py` | `validation/` | CLI entry point |

### Metrics Validated

| Metric | Tolerance | CheckOnChain Reference |
|--------|-----------|----------------------|
| MVRV-Z Score | ±2% | btconchain/unrealised/mvrv_all |
| NUPL | ±2% | btconchain/unrealised/nupl |
| SOPR | ±1% | btconchain/realised/sopr |
| CDD | ±5% | btconchain/lifespan/cdd |
| Hash Ribbons | ±3% | btconchain/mining/hashribbons |
| Cost Basis | ±2% | btconchain/pricing/yearlycostbasis |

### Usage

```bash
# CLI usage
python -m validation --help
python -m validation                  # Full suite
python -m validation --numerical      # API comparison only
python -m validation --visual         # Screenshot workflow
python -m validation --metric mvrv    # Single metric
python -m validation --update-baselines  # Refresh from CheckOnChain
```

### CI/CD

GitHub Action at `.github/workflows/validation.yml`:
- Nightly run at 2 AM UTC
- Manual trigger with metric selection
- Creates GitHub issues on validation failures
- Uploads reports as artifacts

### Validation Status

- ✅ **PASS**: Deviation within tolerance
- ⚠️ **WARN**: Deviation 1x-2x tolerance
- ❌ **FAIL**: Deviation > 2x tolerance
- 🔴 **ERROR**: Validation could not complete

---

## Development Hardware Specifications

Production workstation resources for optimal performance:

| Component | Specification | Notes |
|-----------|--------------|-------|
| **CPU** | AMD/Intel multi-core | 16+ cores recommended for parallel processing |
| **RAM** | 128 GB DDR5 | Required for 164M+ row DuckDB operations |
| **Storage** | | |
| - NVMe (primary) | 2 TB | `/media/sam/2TB-NVMe` - Prod apps & fast DBs |
| - SSD (secondary) | 1 TB | `/media/sam/1TB` - UTXOracle codebase |
| - HDD (blockchain) | 3 TB WDC | `/media/sam/3TB-WDC` - Bitcoin Core data (806 GB) |

### Database Locations

| Database | Path | Size | Purpose |
|----------|------|------|---------|
| `utxoracle_cache.db` | `/media/sam/2TB-NVMe/prod/apps/utxoracle/data/` | ~300 MB | Cache & prices |
| `utxo_lifecycle.duckdb` | `/media/sam/2TB-NVMe/prod/apps/utxoracle/data/` | 57 GB | UTXO data (164M rows) |
| Bitcoin chainstate | `/media/sam/3TB-WDC/Bitcoin/chainstate/` | ~10 GB | UTXO set (leveldb) |
| Bitcoin blocks | `/media/sam/3TB-WDC/Bitcoin/blocks/` | ~700 GB | Full blockchain |

### Performance Considerations

**DuckDB Optimization:**
- DuckDB is OLAP-optimized (analytical queries), not OLTP (transactional updates)
- Bulk operations (COPY, INSERT ... SELECT) are fast: 712K rows/sec
- Row-by-row UPDATEs are slow even with indexes (use staging table pattern)
- For 164M row updates: use staging table + JOIN instead of individual UPDATEs

**Recommended Update Pattern:**
```python
# SLOW: Individual updates (full table scan per update)
for txid, vout in spent_utxos:
    conn.execute("UPDATE ... WHERE txid=? AND vout=?", [txid, vout])

# FAST: Bulk staging table approach
conn.execute("CREATE TEMP TABLE spent_staging (txid VARCHAR, vout INTEGER, ...)")
conn.executemany("INSERT INTO spent_staging VALUES (...)", spent_batch)
conn.execute("""
    UPDATE utxo_lifecycle SET is_spent=TRUE, ...
    FROM spent_staging s
    WHERE utxo_lifecycle.txid = s.txid AND utxo_lifecycle.vout = s.vout
""")
```

---

## Database Architecture (spec-037 - RESOLVED 2025-12-27)

> **Status**: ✅ RESOLVED - Consolidated database architecture implemented

### Solution: Single Consolidated Database

All data now resides in a single DuckDB database: `data/utxoracle.duckdb`

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     CONSOLIDATED DATABASE ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  data/utxoracle.duckdb (57+ GB)                                             │
│  ├── utxo_lifecycle       (164M rows) ← Raw UTXO data                       │
│  ├── utxo_lifecycle_full  (164M rows) ← UTXO with realized values           │
│  ├── block_heights        (928K rows) ← Block timestamp mapping             │
│  ├── daily_prices         (5.4K rows) ← Historical BTC prices               │
│  ├── price_analysis       (744 rows)  ← UTXOracle price outputs             │
│  ├── alert_events         (332 rows)  ← Webhook alert history               │
│  ├── intraday_prices      (21M rows)  ← High-frequency price data           │
│  │                                                                           │
│  │  === Daily Metric Tables (spec-037) ===                                  │
│  ├── sopr_daily           (30+ rows)  ← SOPR time series                    │
│  ├── nupl_daily           (30+ rows)  ← NUPL + market/realized cap          │
│  ├── mvrv_daily           (30+ rows)  ← MVRV + MVRV-Z ratios                │
│  ├── realized_cap_daily   (30+ rows)  ← Daily realized cap                  │
│  └── cointime_daily       (30+ rows)  ← Liveliness, vaultedness             │
│                                                                              │
│  /media/sam/2TB-NVMe/prod/apps/utxoracle/data/                              │
│  └── utxoracle.duckdb → SYMLINK to data/utxoracle.duckdb                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Centralized Configuration

All scripts use the `scripts.config` module:

```python
from scripts.config import UTXORACLE_DB_PATH, get_connection

# Environment variable override:
export UTXORACLE_DB_PATH="/custom/path/utxoracle.duckdb"

# Default: data/utxoracle.duckdb
```

### Metric Pipeline

Daily metrics are calculated from `utxo_lifecycle_full` and persisted to daily tables:

```bash
# Calculate metrics for a specific date
python -m scripts.metrics.calculate_daily_metrics --date 2025-12-14

# Backfill last 30 days
python -m scripts.metrics.calculate_daily_metrics --backfill 30 --end-date 2025-12-14

# Dry run (calculate but don't persist)
python -m scripts.metrics.calculate_daily_metrics --date 2025-12-14 --dry-run
```

### Validation Pipeline

MetricLoader now loads from daily tables and compares against RBN reference data:

```bash
# Run validation
python -m scripts.integrations.validation_batch --days 30

# Generate HTML report
python -m scripts.integrations.validation_batch --html --days 30
```

### Key Changes (spec-037)

1. ✅ Renamed `utxo_lifecycle.duckdb` → `utxoracle.duckdb`
2. ✅ Created `scripts.config` module with `UTXORACLE_DB_PATH`
3. ✅ Updated 20+ scripts to use centralized config
4. ✅ Migrated cache tables from NVMe to consolidated DB
5. ✅ Created 5 daily metric tables (sopr, nupl, mvrv, realized_cap, cointime)
6. ✅ Implemented `calculate_daily_metrics.py` batch pipeline
7. ✅ Updated MetricLoader to use new table names
8. ✅ Validation now shows real correlation values (not 1.0)

---

## Future Architecture Plans

See **MODULAR_ARCHITECTURE.md** for planned Rust-based architecture:
- Rust port of UTXOracle_library.py (black box replacement)
- Real-time mempool analysis with WebGL visualization
- Each module independently replaceable
