# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**📘 For Skill Implementation in Other Projects**: See `.claude/SKILLS_FRAMEWORK_BLUEPRINT.md` - Portable meta-framework for implementing Skills in ANY repository.

## Project Overview

UTXOracle is a Bitcoin-native, exchange-free price oracle that calculates the market price of Bitcoin directly from blockchain data. It analyzes on-chain transactions using statistical clustering to derive BTC/USD prices without relying on external exchange APIs.

**Key Principles**:
- Pure Python implementation (no external dependencies beyond standard library)
- Single-file reference implementation for clarity and transparency
- Direct Bitcoin Core RPC connection only
- Privacy-first: no external price feeds

**🎯 Development Philosophy**: KISS (Keep It Simple) + YAGNI (You Ain't Gonna Need It)
→ See [Development Principles](#development-principles) for detailed blueprint

## Running UTXOracle

### Main Script

```bash
# Run for yesterday's price (default)
python3 UTXOracle.py

# Run for specific date
python3 UTXOracle.py -d 2025/10/15

# Use recent 144 blocks
python3 UTXOracle.py -rb

# Specify Bitcoin data directory
python3 UTXOracle.py -p /path/to/bitcoin/data

# View all options
python3 UTXOracle.py -h
```

### Batch Processing

```bash
# Process date range in parallel (12 workers)
python3 scripts/utxoracle_batch.py 2025/10/01 2025/10/10 /home/sam/.bitcoin 12

# Suppress browser opening for batch mode
python3 UTXOracle.py -d 2025/10/17 --no-browser
```

### Requirements

- **Python 3.8+** (standard library only)
- **Bitcoin Core node** (fully synced, RPC enabled)
- **RPC Access**: Either cookie authentication (default) or bitcoin.conf configuration

## Architecture

### Current Implementation (spec-003: Hybrid Architecture)

**4-Layer Architecture** - Combines reference implementation with self-hosted infrastructure:

#### Layer 1: Reference Implementation (UTXOracle.py)
- Single-file reference implementation using sequential 12-step algorithm
- Intentionally verbose for educational transparency
- **IMMUTABLE** - Do not refactor

#### Layer 2: Reusable Library (UTXOracle_library.py)
- Extracted core algorithm (Steps 5-11) from reference implementation
- Public API: `UTXOracleCalculator.calculate_price_for_transactions(txs)`
- Enables Rust migration path (black box replacement)
- Used by integration service for real-time analysis

#### Layer 3: Self-Hosted Infrastructure (mempool.space + electrs)
- **Replaces custom ZMQ/transaction parsing** (saved 1,122 lines of code)
- Docker stack at `/media/sam/2TB-NVMe/prod/apps/mempool-stack/`
- Components:
  * **electrs** - Electrum server (38GB index, 3-4 hour sync on NVMe)
  * **mempool backend** - API server (port 8999)
  * **mempool frontend** - Web UI (port 8080)
  * **MariaDB** - Transaction database
- Benefits: Battle-tested, maintained by mempool.space team, zero custom parsing code

#### Layer 4: Integration & Visualization
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

#### On-Chain Metrics Module (spec-007)

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

#### Advanced On-Chain Analytics Module (spec-009)

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
  * `EnhancedFusionResult`: 8-component fusion result (includes Wasserstein)

- **API Endpoint** (`/api/metrics/advanced`)
  * Real-time computation from latest block data
  * Returns Power Law, Symbolic Dynamics, Fractal Dimension, Enhanced Fusion
  * 501 if modules not installed, 503 if electrs unavailable

#### Wasserstein Distance Module (spec-010)

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
  * 8th component with 0.08 weight
  * Automatic weight renormalization when unavailable

#### Derivatives Historical Module (spec-008)

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

#### Alert System Module (spec-011)

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

#### Backtesting Framework Module (spec-012)

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

#### Address Clustering Module (spec-013)

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

### Spec Implementation Status

| Spec | Module | Status | Files |
|------|--------|--------|-------|
| spec-007 | metrics/ | ✅ Complete | 7 |
| spec-008 | derivatives/ | ✅ Complete | 4 |
| spec-009 | metrics/ (advanced) | ✅ Complete | +3 |
| spec-010 | metrics/wasserstein | ✅ Complete | 1 |
| spec-011 | alerts/ | ✅ Complete | 4 |
| spec-012 | backtest/ | ✅ Complete | 5 |
| spec-013 | clustering/ | ✅ Complete | 5 |

### Code Reduction (spec-002 → spec-003)

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

**Production Configuration** (as of Nov 2, 2025):
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

### Future Architecture Plans

See **MODULAR_ARCHITECTURE.md** for planned Rust-based architecture:
- Rust port of UTXOracle_library.py (black box replacement)
- Real-time mempool analysis with WebGL visualization
- Each module independently replaceable

### Local Infrastructure Quick Reference

**IMPORTANT**: UTXOracle uses **self-hosted infrastructure** (no external API dependencies for transactions).

#### Service Endpoints (Localhost)

| Service | URL | Purpose | Status Check |
|---------|-----|---------|--------------|
| **Bitcoin Core RPC** | `http://localhost:8332` | Blockchain data (Tier 3 fallback) | `bitcoin-cli getblockcount` |
| **electrs HTTP API** | `http://localhost:3001` | Transaction data (Tier 1 primary) | `curl localhost:3001/blocks/tip/height` |
| **mempool backend** | `http://localhost:8999` | Exchange prices | `curl localhost:8999/api/v1/prices` |
| **mempool frontend** | `http://localhost:8080` | Block explorer UI | Open in browser |

#### Transaction Fetching Flow (scripts/daily_analysis.py)

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

#### Docker Stack Location

```bash
# mempool.space + electrs Docker Compose stack
/media/sam/2TB-NVMe/prod/apps/mempool-stack/

# Quick commands:
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack/
docker compose ps              # Check services
docker compose logs -f         # View logs
docker compose restart         # Restart stack
```

#### electrs Sync Status

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

## Repository Organization

### Core Structure

```
UTXOracle/
.env                                # Environment variables (DO NOT COMMIT)
.python-version                     # Python version specification
CLAUDE.md                           # THIS FILE - Claude Code instructions
LICENSE                             # Blue Oak Model License 1.0.0
README.md                           # Project overview
UTXOracle.py                        # Reference implementation v9.1 (IMMUTABLE)
UTXOracle_library.py                # Reusable library (spec-003: T019-T029)
main.py                             # Live system entry point (deprecated)
pyproject.toml                      # UV workspace root
uv.lock                             # Dependency lockfile (commit this!)
│
.claude/                            # Claude Code configuration
├── AGENT_TOOLS_REFERENCE.md
├── BROWSER_MCP_QUICK_REFERENCE.md
├── HOOKS_ANALYSIS.md
├── HOOKS_TUTORIAL_ANALYSIS.md
├── HOOK_CONFIG_SNIPPET.md
├── META_LEARNING_README.md
├── README.md
├── TDD_GUARD_VS_AUTOTEST.md
├── VERIFICATION_REPORT.md
├── config.json
├── settings.local copy.json
├── settings.local.json
├── settings.local.json.backup-20251024-175459
├── agents/                             # 6 specialized subagents
├── commands/                           # Custom slash commands (SpecKit)
├── context_bundles/
├── docs/                               # Meta-documentation
├── hooks/                              # Pre/post tool execution hooks
├── logs/                               # Session logs
├── prompts/                            # Orchestration rules
├── reports/
├── research/                           # Research notes
├── scripts/
├── self_improve/
├── skills/                             # 4 template-driven automation skills
├── stats/
└── tdd-guard/                          # TDD enforcement data
.github/                            # Cleanup automation tools
├── CLEANUP_CHECKLIST.md
├── README.md
└── pre-commit.hook
.serena/                            # Serena MCP (code navigation memory)
├── .gitignore
├── project.yml
├── cache/
└── memories/
.specify/                           # SpecKit (task management)
├── memory/
├── scripts/
└── templates/
archive/                            # Previous versions (v7, v8, v9, spec-002)
├── CHANGELOG_SPEC.md
├── contadino_cosmico.md
├── live-spec002/                       # Archived spec-002 implementation (Phase 3 cleanup)
│   ├── backend/                        # Old modules (archived for reference)
│   ├── frontend/                       # Old frontend (archived)
│   ├── shared/                         # Old models (archived)
│   └── DEPLOYMENT.md                   # Old deployment docs
├── start9/
├── v7/
├── v8/
└── v9/
docs/                               # Documentation
├── session_reports/                    # Session validation reports (moved from root)
│   ├── BROWSER_TEST_RESULTS.md
│   ├── COMPREHENSIVE_VALIDATION_REPORT.md
│   ├── CRITICAL_ISSUES_REPORT.md
│   ├── END_TO_END_TEST_REPORT.md
│   ├── FINAL_SYSTEM_STATE.md
│   ├── IMPLEMENTATION_STATUS_REPORT.md
│   ├── INFRASTRUCTURE_STATUS.md
│   ├── INTEGRATION_TEST_REPORT.md
│   ├── PHASE3_VERIFICATION.md
│   ├── PHASE_005_FINAL_STATUS.md
│   ├── PRODUCTION_READINESS_FINAL_REPORT.md
│   ├── SPECKIT_IMPLEMENT_SUMMARY.md
│   ├── SYSTEM_STATUS_REPORT.md
│   ├── TASKS_VERIFICATION_REPORT.md
│   └── TASK_STATUS_2025-11-02.md
├── BASELINE_LIVE_ARCHITECTURE.md
├── BASELINE_RENDERING_CHECKLIST.md
├── BASELINE_RENDERING_IMPLEMENTATION.md
├── BASELINE_RENDERING_SUCCESS.md
├── BASELINE_RENDERING_SUMMARY.md
├── BUGFIX_REPORT_2025-10-23.md
├── CANVAS_IMPLEMENTATION_COMPLETE.md
├── GEMINI_FIX_ANALYSIS.md
├── IMPLEMENTATION_CHECKLIST.md
├── MANUAL_TEST_US3_CONFIDENCE_WARNING.md
├── PHASE7_COMPLETION_REPORT.md
├── SELFHOSTED_MEMPOOL_INTEGRATION.md
├── STEP10_IMPLEMENTATION_REPORT.md
├── T093_FINAL_REPORT.md
├── T093_FINAL_SUCCESS.png
├── T093_SUCCESS_VALIDATED.png
├── T093_VALIDATION_REPORT.md
├── T093_validation_LIVE_final.png
├── T093_validation_LIVE_final_v2.png
├── T093_validation_report.md
├── T093_validation_screenshot.png
├── T103_SECURITY_AUDIT_REPORT.md
├── VISUALIZATION_FIX_PLAN.md
├── VISUALIZATION_GAP_ANALYSIS.md
├── VISUALIZATION_ISSUES_PLAN.md
├── VISUAL_COMPARISON_SUMMARY.md
├── algorithm_concepts.md
├── mcp-builder-agent.md
├── skills-creator-agent.md
└── tasks/                              # Agent task specifications (01-05)
examples/                           # Example outputs and screenshots
├── README.md
├── UTXOracle_Local_Node_Price.png
├── mempool.png
├── mempool2.png
├── mempool3.png
├── mempool4.png
├── mempool_attuale.png
├── mempuul.png
└── visual_errata.png
historical_data/                    # 672 days of historical outputs
└── html_files/                         # HTML price analysis files
    └── [672 HTML files]
api/                                # FastAPI backend (spec-003)
├── __init__.py
└── main.py                             # REST API server (420 lines)
frontend/                           # Plotly.js dashboard (spec-003)
└── comparison.html                     # Price comparison visualization
scripts/                            # Utilities (batch processing, integration)
├── README.md
├── daily_analysis.py                   # Integration service (spec-003)
├── init_metrics_db.py                  # DuckDB metrics table migration (spec-007)
├── setup_full_mempool_stack.sh         # Infrastructure deployment (spec-003)
├── utxoracle_batch.py                  # Batch historical processing
├── alerts/                             # Alert system (spec-011)
│   ├── __init__.py                     # Public API
│   ├── generators.py                   # Alert generation logic
│   ├── dispatcher.py                   # Webhook dispatch with retry
│   └── models.py                       # Alert data models
├── backtest/                           # Backtesting framework (spec-012)
│   ├── __init__.py                     # Public API
│   ├── engine.py                       # Backtest execution engine
│   ├── metrics.py                      # Performance metrics
│   ├── optimizer.py                    # Weight optimization
│   └── data_loader.py                  # Historical data loading
├── clustering/                         # Address clustering (spec-013)
│   ├── __init__.py                     # Public API
│   ├── union_find.py                   # Disjoint-set structure
│   ├── address_clustering.py           # Clustering algorithm
│   ├── coinjoin_detector.py            # CoinJoin detection
│   └── change_detector.py              # Change output heuristics
├── derivatives/                        # Derivatives data (spec-008)
│   ├── __init__.py                     # Public API
│   ├── funding_rate_reader.py          # Funding rate signals
│   ├── oi_reader.py                    # Open interest signals
│   └── enhanced_fusion.py              # 4-component fusion
├── metrics/                            # On-chain metrics (spec-007 + spec-009)
│   ├── __init__.py                     # DB helpers
│   ├── monte_carlo_fusion.py           # Bootstrap signal fusion
│   ├── active_addresses.py             # Address counting
│   ├── tx_volume.py                    # TX volume in USD
│   ├── power_law.py                    # Power law detector (spec-009)
│   ├── symbolic_dynamics.py            # Permutation entropy (spec-009)
│   └── fractal_dimension.py            # Box-counting (spec-009)
└── models/
    ├── metrics_models.py               # Metrics data models
    └── derivatives_models.py           # Derivatives data models
specs/                              # Feature specifications (SpecKit)
├── 007-onchain-metrics-core/           # ✅ Implemented
├── 008-derivatives-historical/         # ✅ Implemented
├── 009-advanced-onchain-analytics/     # ✅ Implemented
├── 010-wasserstein-distance/           # ❌ Not started
├── 011-alert-system/                   # ✅ Implemented
├── 012-backtesting-framework/          # ✅ Implemented
└── 013-address-clustering/             # ✅ Implemented
tests/                              # Test suite (pytest)
├── __init__.py
├── conftest.py
├── test_api.py
├── test_baseline_calculator.py
├── test_hook_example.py
├── test_mempool_analyzer.py
├── test_models.py
├── test_orchestrator_stats_bug.py
├── test_orchestrator_streamer_integration.py
├── test_security.py
├── test_step10_intraday_points.py
├── test_tx_processor.py
├── test_zmq_listener.py
├── benchmark/                          # Performance benchmarks
├── fixtures/                           # Test data
├── integration/                        # End-to-end tests
├── test_core/
└── test_live/
```

### Claude Code Configuration (`.claude/`)

**Agent System**:
- `agents/` - 6 specialized subagents (1 per task + tdd-guard)
- `skills/` - 4 template-driven automation skills (pytest, github, pydantic, bitcoin-rpc)
- `prompts/` - Orchestration rules (utxoracle-system.md)

**Automation Infrastructure**:
- `hooks/` - Pre/post tool execution hooks (auto-format, safety checks, git guards)
- `tdd-guard/` - TDD enforcement data (coverage, test history)
- `commands/` - Custom slash commands (SpecKit integration)

**Documentation & Analysis**:
- `docs/` - Meta-documentation (skills analysis, MCP optimization, framework blueprint)
- `research/` - Research notes (hook systems, best practices)
- `logs/` - Session logs (tool usage tracking)

**Configuration**:
- `settings.local.json` - Permissions & hooks configuration
- `config.json` - Claude configuration

### MCP Server Memory (`.serena/`, `.specify/`)

- **Serena**: Code navigation memory (project knowledge base)
- **SpecKit**: Task management (memory, templates, automation scripts)

### File Placement Conventions

**New backend modules** → `api/` (FastAPI endpoints)
**New frontend code** → `frontend/` (HTML/JS/CSS)
**Integration scripts** → `scripts/` (cron jobs, batch processing)
**Core library** → Root directory (`UTXOracle_library.py`)
**New tests** → `tests/test_<module>.py`
**New docs** → `docs/` (or `.claude/docs/` if meta-documentation)
**Agent specs** → `.claude/agents/`
**Skills** → `.claude/skills/`
**Specs** → `specs/<feature-id>/`

### Immutable Files

- **UTXOracle.py** - Reference implementation (do not refactor)
- **UTXOracle_library.py** - Extracted algorithm (only refactor with tests)
- Historical data in `historical_data/html_files/`

### Deprecated/Archived (spec-002)

- `archive/live-spec002/` - Old custom infrastructure (ZMQ, tx parsing, orchestrator)
  - 3,102 lines of code (backend, frontend, shared models)
  - Replaced by: mempool.space Docker stack + `scripts/daily_analysis.py`
- `archive/scripts-spec002/` - Legacy integration scripts
  - `live_mempool_with_baseline.py` - Old integration approach
  - `utxoracle_mempool_integration.py` - Deprecated integration
  - `setup_mempool_env.sh` - Old environment setup
  - `verify_mempool_setup.sh` - Old verification script
- `main.py` - Old entry point (replaced by `scripts/daily_analysis.py`)
- `live.backup.*/` - Temporary backups during migration (gitignored)

## Agent & Skill Architecture

### **Subagents** (7) - Complex Reasoning
Specialized agents for deep domain expertise and multi-step workflows.

| Agent | Task | Responsibility | Token Cost |
|-------|------|---------------|-----------|
| bitcoin-onchain-expert | 01 | ZMQ listener, Bitcoin Core integration | ~8,000 |
| transaction-processor | 02 | Binary parsing, UTXOracle filtering | ~7,500 |
| mempool-analyzer | 03 | Histogram, stencil, price estimation | ~9,000 |
| data-streamer | 04 | FastAPI WebSocket server | ~6,000 |
| visualization-renderer | 05 | Canvas 2D + Three.js WebGL | ~7,000 |
| tdd-guard | - | TDD enforcement, coverage validation | ~5,000 |
| **alpha-debug** | - | AlphaEvolve-style iterative bug hunter | ~6,000 |

**Usage**: Invoke via Claude Code for complex implementation tasks.

### **Alpha Debug** - Evolutionary Bug Hunting

AlphaEvolve-inspired iterative debugging system that finds bugs even when tests pass.

**Invocation Patterns**:
```
# After implementation phase
"run alpha-debug on wasserstein implementation"

# Before commit (N rounds)
"alpha-debug 3 rounds before commit"

# General bug hunt
"esegui N rounds di verifica e ricerca bug"
```

**How It Works**:
1. **SubagentStop Hook** (`alpha-debug-loop.py`) controls the loop
2. Each round: ANALYZE → HYPOTHESIZE → VERIFY → FIX → SCORE
3. Continues until:
   - MAX_ROUNDS reached (default: 5)
   - 2 consecutive clean rounds (0 bugs)
   - Tests failing (needs human intervention)
   - Critical issue requiring review

**Bug Categories Hunted**:
- **A**: Logic errors (off-by-one, wrong comparisons)
- **B**: Edge cases (empty, boundary, large inputs)
- **C**: Integration issues (API contracts, type mismatches)
- **D**: Code smells (unused vars, complexity)

**Output Format**:
```
=== ALPHA DEBUG COMPLETE ===
Reason: Code is clean (2 consecutive rounds with 0 bugs)

Final Statistics:
- Total rounds: 3
- Total bugs found: 2
- Total bugs fixed: 2
- Success rate: 100%
```

### **Skills** (4) - Template-Driven Automation
Lightweight templates for repetitive operations with 60-83% token savings.

| Skill | Purpose | Token Savings | Status |
|-------|---------|---------------|--------|
| pytest-test-generator | Auto-generate test boilerplate | 83% (3,000→500) | ✅ |
| github-workflow | PR/Issue/Commit templates | 79% (18,900→4,000) | ✅ |
| pydantic-model-generator | Pydantic data models with validators | 75% (2,000→500) | ✅ |
| bitcoin-rpc-connector | Bitcoin Core RPC client setup | 60% (2,500→1,000) | ✅ |

**Total Skill Savings**: ~20,400 tokens/task (77% reduction on template-driven operations)

**Usage**: Automatically triggered by keywords:
- "generate tests" → pytest-test-generator
- "create PR" → github-workflow
- "pydantic model" → pydantic-model-generator
- "bitcoin rpc" → bitcoin-rpc-connector

### **Modus Operandi**
See `.claude/prompts/utxoracle-system.md` for:
- Task classification rules (01-05)
- TDD workflow enforcement
- Agent spawning patterns
- Checkpoint management
- Error handling protocols

**Combined Token Savings**: ~20,400 tokens/task (Skills) + MCP optimization (~67,200 tokens/pipeline) = **87,600 tokens total**

## Development Principles

### 🎯 KISS & YAGNI Blueprint (ALWAYS REMEMBER!)

#### **KISS** - Keep It Simple, Stupid
- **Choose boring technology**: Python, not Rust (until needed)
- **Avoid premature optimization**: Make it work, then make it fast
- **One module, one purpose**: Each file does ONE thing well
- **Minimize dependencies**: Every dependency is technical debt
- **Clear over clever**: Code that a junior can understand beats "smart" code

#### **YAGNI** - You Ain't Gonna Need It
- **Don't build for hypothetical futures**: Solve TODAY's problem
- **No unused Skills**: 4 Skills are enough (don't add the other 3)
- **No generic solutions**: Specific beats flexible
- **Delete dead code**: If unused for 2 weeks, remove it
- **Resist abstraction temptation**: 3 similar things ≠ need for abstraction

#### **Code Reuse First** - Don't Reinvent the Wheel
- **NEVER write custom code if >80% can be reused**: Use existing libraries, services, or infrastructure
- **Analyze before automating**: Verify existing solutions don't already solve the problem
- **Self-host over custom build**: Deploy proven open-source solutions instead of reimplementing
- **Example**: Use mempool.space (battle-tested) instead of custom ZMQ parser (1,222 lines)

#### **Applied to UTXOracle**
✅ **DO**: Use existing 6 subagents + 4 skills
✅ **DO**: Write simple Python that works
✅ **DO**: Focus on Tasks 01-05 implementation
❌ **DON'T**: Create more Skills "just in case"
❌ **DON'T**: Over-engineer for "future scalability"
❌ **DON'T**: Abstract before you have 3+ real use cases

**Remember**: The best code is no code. The second best is deleted code. The third best is simple code.

---

### Vibe Coding Architecture (Eskil Steenberg)

This project follows "black box" architecture principles for maintainability and AI-assisted development:

1. **Constant developer velocity** - Fast iteration regardless of project size
2. **One module, one person** - Each module can be owned/developed independently
3. **Everything replaceable** - If you don't understand a module, rewrite it without breaking others
4. **Black box interfaces** - Modules communicate only through clean, defined APIs
5. **Write 5 lines today** - Avoid future context switching by writing upfront, not editing later

**Why this matters**: When AI generates complex code, we can easily replace that specific module without touching the rest of the system. Each module is a manageable, bite-sized chunk.

**Reference**: [Eskil Steenberg - Architecting LARGE Software Projects](https://www.youtube.com/watch?v=sSpULGNHyoI)

### Code Philosophy

1. **Transparency over efficiency**: Code is structured for human understanding, not computational optimization
2. **Zero dependencies**: Only Python 3 standard library (reference impl) or minimal deps (live system)
3. **Reproducibility**: Every price calculation is verifiable from public blockchain data
4. **Single file clarity**: UTXOracle.py intentionally avoids function abstraction to keep logic flow visible

### Working with UTXOracle.py

- **Do NOT refactor into functions/classes** unless creating a separate implementation
- **Do NOT add external dependencies** to the reference implementation
- The verbose, repetitive style is intentional for educational purposes
- Code comments with hash tags explain algorithm to non-programmers

### Mempool Live System Development

**Current Status**: Implementation complete (MVP functional, Phase 7 polish in progress)
- ✅ Phases 1-6 complete (T001-T093): All core modules implemented
- 🔄 Phase 7 in progress (T094-T104): Polish & cross-cutting concerns
- ⚠️ Manual validation pending: T062-T064 require live Bitcoin Core ZMQ connection
- 📋 See `specs/002-mempool-live-oracle/tasks.md` for detailed status

**Tech Stack (KISS MVP)**:
- **Dependency management**: UV (not pip) - 10-100x faster, deterministic lockfiles
- **Backend**: FastAPI + PyZMQ (minimal dependencies)
- **Frontend MVP**: Vanilla JS + Canvas 2D (zero dependencies, no build step)
- **Frontend Production**: Three.js WebGL (only when >5k points cause Canvas lag)
- **Core algorithm**: Pure Python (reuse UTXOracle.py logic exactly)

**Agent Assignment**:
- `bitcoin-onchain-expert`: Task 01 (ZMQ interface)
- `general-purpose`: Tasks 02-05 (processing, analysis, streaming, visualization)

**Development Workflow**:
1. Read task file in `docs/tasks/XX_module_name.md`
2. Launch appropriate agent with task file as context
3. Agent implements module as black box with defined interface
4. Test module independently
5. Integrate with pipeline

**Rust Migration Path** (future):
- Core algorithm (histogram, stencil, convergence) can be rewritten in Rust or Cython
- Replaces Python modules without touching ZMQ/WebSocket/frontend
- Black box interface ensures seamless swap

---

## 🔧 Development Workflow

### TDD Implementation Flow

**Red-Green-Refactor** (when applicable):

1. **🔴 RED**: Write failing test first
   ```bash
   uv run pytest tests/test_module.py::test_new_feature -v  # MUST fail
   git add tests/ && git commit -m "TDD RED: Add test for feature X"
   ```

2. **🟢 GREEN - BABY STEPS** (critical - TDD guard enforces this):

   **Step 2a**: Add MINIMAL stub (just method signature)
   ```python
   def new_method(self):
       """Stub - not implemented yet"""
       raise NotImplementedError
   ```
   Run test → Should fail differently (NotImplementedError instead of AttributeError)

   **Step 2b**: Add MINIMAL implementation
   ```python
   def new_method(self):
       """Minimal implementation to pass test"""
       return []  # Simplest return value
   ```
   Run test → May still fail on assertions

   **Step 2c**: Iterate until GREEN
   ```bash
   uv run pytest tests/test_module.py::test_new_feature -v  # Should pass
   git add . && git commit -m "TDD GREEN: Implement feature X"
   ```

3. **♻️ REFACTOR**: Clean up with tests passing
   ```bash
   # Improve code quality without changing behavior
   uv run pytest  # All tests still pass
   git add . && git commit -m "TDD REFACTOR: Clean up feature X"
   ```

**⚠️ TDD Guard Rules** (enforced automatically):
- ❌ **NEVER** implement without failing test first
- ❌ **NEVER** add multiple tests at once (one test at a time)
- ❌ **NEVER** implement more than needed to pass current test
- ✅ **ALWAYS** run pytest immediately before AND after each edit
- ✅ **ALWAYS** implement smallest possible change
- ✅ **FOLLOW** error messages literally (AttributeError → add method, AssertionError → fix logic)

**Baby Step Example**:
```python
# ❌ WRONG (too much at once):
def get_history(self):
    if not hasattr(self, 'history'):
        self.history = deque(maxlen=500)
    return list(self.history)

# ✅ CORRECT (baby steps):
# Step 1: Just stub
def get_history(self):
    pass

# Step 2: Minimal return
def get_history(self):
    return []

# Step 3: Add empty list if test needs it
def get_history(self):
    if not hasattr(self, 'history'):
        self.history = []
    return self.history

# Step 4: Fix after test shows we need deque
def get_history(self):
    if not hasattr(self, 'history'):
        self.history = deque(maxlen=500)
    return list(self.history)
```

**When TDD doesn't fit**: Frontend JS, visualization, exploratory code → Write tests after, document why.

---

### When Stuck Protocol

**CRITICAL**: Maximum **3 attempts** per issue, then STOP.

#### After 3 Failed Attempts:

1. **Document failure**:
   ```markdown
   ## Blocker: [Issue Description]

   **Attempts**:
   1. Tried: [approach] → Failed: [error]
   2. Tried: [approach] → Failed: [error]
   3. Tried: [approach] → Failed: [error]

   **Why stuck**: [hypothesis]
   ```

2. **Research alternatives** (15min max):
   - Find 2-3 similar implementations (GitHub, docs)
   - Note different approaches used
   - Check if problem is already solved differently

3. **Question fundamentals**:
   - Is this the right abstraction level?
   - Can this be split into smaller problems?
   - Is there a simpler approach entirely?
   - Do I need this feature at all? (YAGNI check)

4. **Try different angle OR ask for help**:
   - Different library/framework feature?
   - Remove abstraction instead of adding?
   - Defer to later iteration?

**Never**: Keep trying the same approach >3 times. That's insanity, not persistence.

---

### Decision Framework

When multiple valid approaches exist, choose based on **priority order**:

1. **Testability** → Can I easily test this? (automated, fast, deterministic)
2. **Simplicity** → Is this the simplest solution that works? (KISS)
3. **Consistency** → Does this match existing project patterns?
4. **Readability** → Will someone understand this in 6 months? (Future you)
5. **Reversibility** → How hard to change later? (Prefer reversible)

**Example**:
```python
# ❌ Clever but hard to test
result = reduce(lambda x,y: x|y, map(parse, data), {})

# ✅ Simple, testable, readable
result = {}
for item in data:
    parsed = parse(item)
    result.update(parsed)
```

---

### Error Handling Standards

**Principles**:
- **Fail fast** with descriptive messages
- **Include context** for debugging (not just "Error")
- **Handle at appropriate level** (don't catch everywhere)
- **Never silently swallow** exceptions

**Good Error Messages**:
```python
# ❌ Bad
raise ValueError("Invalid input")

# ✅ Good
raise ValueError(
    f"Bitcoin RPC connection failed: {rpc_url} "
    f"(check bitcoin.conf rpcuser/rpcpassword)"
)
```

**Logging over print**:
```python
# ❌ Bad
print(f"Processing block {height}")  # Lost in production

# ✅ Good
logger.info(f"Processing block {height}", extra={"block_height": height})
```

---

### Test Guidelines

**Principles**:
- Test **behavior**, not implementation
- **One assertion** per test when possible (or closely related assertions)
- **Clear test names** describing scenario: `test_<what>_<when>_<expected>`
- **Use existing fixtures/helpers** (check `tests/conftest.py`)
- Tests must be **deterministic** (no random, no time dependencies)

**Good Test Structure**:
```python
def test_histogram_removes_round_amounts_when_filtering_enabled():
    """Round BTC amounts (1.0, 5.0) should be filtered from histogram."""
    # Arrange
    histogram = {"1.0": 100, "1.23456": 50, "5.0": 200}

    # Act
    filtered = remove_round_amounts(histogram)

    # Assert
    assert "1.0" not in filtered
    assert "5.0" not in filtered
    assert filtered["1.23456"] == 50
```

**Bad Tests**:
```python
# ❌ Testing implementation details
def test_histogram_uses_dict():
    assert isinstance(histogram, dict)  # Who cares?

# ❌ Multiple unrelated assertions
def test_everything():
    assert process() == expected  # Too vague
    assert config.loaded  # Unrelated
    assert server.running  # Unrelated
```

---

### Important Reminders

#### ❌ **NEVER**:
- Use `--no-verify` to bypass commit hooks (fix the issue instead)
- Disable tests instead of fixing them (broken tests = broken code)
- Commit code that doesn't compile/run
- Use `print()` for logging (use `logging` module)
- Hardcode secrets/API keys (use `.env`)
- Commit without testing locally first

#### ✅ **ALWAYS**:
- Run tests before committing (`uv run pytest`)
- Format/lint before committing (`ruff check . && ruff format .`)
- Write commit message explaining **WHY** (not just what)
- Update relevant docs when changing behavior
- Check `.gitignore` before committing sensitive files
- Use `uv` for dependencies (not `pip`)

---

## 🧹 Task Completion Protocol

**IMPORTANT**: Run this checklist BEFORE marking any task as complete or creating a commit.

### ✅ Pre-Commit Cleanup Checklist

When completing a task, **ALWAYS** do the following cleanup:

#### 1. Remove Temporary Files
```bash
# Check for temporary files
find . -type f \( -name "*.tmp" -o -name "*.bak" -o -name "*~" -o -name "*.swp" \)

# Remove if found (review first!)
# find . -type f \( -name "*.tmp" -o -name "*.bak" -o -name "*~" \) -delete
```

#### 2. Clean Python Cache
```bash
# Remove Python cache (auto-regenerates)
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete
```

#### 3. Remove Debug/Test Outputs
```bash
# Check for test artifacts
ls -la *.html *.json *.log 2>/dev/null | grep -v "UTXOracle_"

# Move to archive if historical data, delete if temporary
```

#### 4. Code Cleanup (Manual Review)

**Remove**:
- ❌ Commented-out code blocks (if >1 week old)
- ❌ `print()` debug statements
- ❌ Unused imports (`ruff check --select F401`)
- ❌ TODO comments that are now resolved
- ❌ Dead functions/classes (never called)

**Fix**:
- ✅ Run linter: `ruff check .` (if available)
- ✅ Format code: `ruff format .` (if available)
- ✅ Type hints: Add where missing

#### 5. Documentation Cleanup

**Consolidate**:
- ❌ Delete draft `.md` files not referenced anywhere
- ❌ Remove obsolete documentation
- ✅ Update CLAUDE.md if structure changed
- ✅ Update relevant task files in `docs/tasks/`

**Check**:
```bash
# Find unreferenced markdown files
find docs -name "*.md" -type f

# Review each - is it still needed?
```

#### 6. Git Status Review

```bash
# Check what's about to be committed
git status

# Review untracked files - keep or delete?
git status --short | grep "^??"

# Check for large files (>1MB)
find . -type f -size +1M -not -path "./.git/*" -not -path "./historical_data/*"
```

#### 7. Update .gitignore (If Needed)

If you find temporary files that shouldn't be committed:
```bash
# Add patterns to .gitignore
echo "*.tmp" >> .gitignore
echo "debug_*.log" >> .gitignore
echo ".DS_Store" >> .gitignore
```

---

### 🚨 Before Every Commit

**Mandatory checks** (MUST pass before committing):

```bash
# 1. No uncommitted temporary files
[ -z "$(find . -name '*.tmp' -o -name '*.bak')" ] && echo "✅ No temp files" || echo "❌ Temp files found"

# 2. Tests pass (if applicable)
# uv run pytest tests/ && echo "✅ Tests pass" || echo "❌ Tests fail"

# 3. No obvious debug code
! git diff --cached | grep -E "(print\(|console\.log|debugger|import pdb)" && echo "✅ No debug code" || echo "⚠️  Debug code in commit"

# 4. File count reasonable
CHANGED=$(git diff --cached --name-only | wc -l)
[ $CHANGED -lt 20 ] && echo "✅ Changed files: $CHANGED" || echo "⚠️  Many files: $CHANGED (review needed)"
```

---

### 🗑️ What to DELETE vs KEEP

#### ❌ DELETE (Always)
- Temporary files (`.tmp`, `.bak`, `~`)
- Python cache (`__pycache__`, `.pyc`)
- Test cache (`.pytest_cache`, `.coverage`)
- Debug logs (`debug_*.log`, `*.trace`)
- Screenshots for debugging (unless documented)
- Experiment files not integrated (`test_*.py` outside tests/)
- Commented code blocks >1 week old
- Unused imports
- TODOs marked DONE

#### ✅ KEEP (Always)
- Historical data (`historical_data/html_files/`)
- Documentation (if referenced in CLAUDE.md or README)
- Tests (`tests/**/*.py`)
- Configuration files (`.claude/`, `pyproject.toml`, `.gitignore`)
- Source code in `live/`, `core/`, `scripts/`
- `uv.lock` (dependency lockfile - COMMIT THIS!)

#### ⚠️ REVIEW CASE-BY-CASE
- Jupyter notebooks (`.ipynb`) - Keep if documented, archive if experimental
- Large binary files (>1MB) - Consider git LFS or external storage
- Generated HTML files - Keep if part of output, delete if test artifacts
- Log files - Keep if needed for debugging, delete if >1 week old

---

### 📝 Post-Cleanup Commit Message

After cleanup, commit with clear message:

```bash
# Good commit message pattern:
git commit -m "[Task XX] Module: Description

Changes:
- Implemented: feature.py
- Tests: test_feature.py (coverage: 85%)
- Cleanup: Removed 3 temp files, 2 unused imports

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 🔄 Periodic Cleanup (Weekly)

Run this every Friday or after completing a major task:

```bash
# Find files not modified in 2 weeks
find . -type f -mtime +14 -not -path "./.git/*" -not -path "./historical_data/*"

# Review and archive or delete
```

**Check for**:
- Orphaned files (not referenced anywhere)
- Old experiment branches (`git branch --merged`)
- Unused Skills (check usage in logs)
- Outdated documentation

---

### 🎯 Cleanup Automation (Optional)

Create `.git/hooks/pre-commit` for automatic checks:

```bash
#!/bin/bash
# .git/hooks/pre-commit

echo "🧹 Running pre-commit cleanup..."

# Remove Python cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# Check for temp files
TEMP_FILES=$(find . -name "*.tmp" -o -name "*.bak" 2>/dev/null)
if [ -n "$TEMP_FILES" ]; then
    echo "❌ Temporary files found:"
    echo "$TEMP_FILES"
    echo "Remove them before committing"
    exit 1
fi

# Check for debug code
if git diff --cached | grep -E "(print\(|console\.log|debugger)"; then
    echo "⚠️  Debug code detected in staged files"
    echo "Review and remove before committing (or use --no-verify to skip)"
    # Don't block commit, just warn
fi

echo "✅ Pre-commit checks passed"
```

---

## Bitcoin Node Connection

UTXOracle connects to Bitcoin Core using:

1. **Cookie authentication** (default): Reads `.cookie` file from Bitcoin data directory
2. **bitcoin.conf settings**: If RPC credentials are configured

Default Bitcoin data paths:
- **Linux**: `~/.bitcoin`
- **macOS**: `~/Library/Application Support/Bitcoin`
- **Windows**: `%APPDATA%\Bitcoin`

Required bitcoin.conf settings for future ZMQ features:
```conf
zmqpubhashtx=tcp://127.0.0.1:28332
zmqpubrawblock=tcp://127.0.0.1:28333
zmqpubrawtx=tcp://127.0.0.1:28332
rpcuser=<user>
rpcpassword=<password>
rpcallowip=127.0.0.1
```

## Historical Data

The repository includes 672 days of historical analysis (Dec 15, 2023 → Oct 17, 2025) as HTML files in `historical_data/html_files/`. Each file contains:

- Daily BTC/USD price calculation
- Statistical confidence score
- Transaction histogram analysis
- Intraday price evolution
- Interactive visualizations
- Blockchain metadata

Processing stats: 99.85% success rate, ~2.25 seconds per date with 12 parallel workers.

## Output

UTXOracle generates:
- **Console output**: Date and calculated price (e.g., "2025-10-15 price: $111,652")
- **HTML file**: Interactive visualization saved as `UTXOracle_YYYY-MM-DD.html`
- **Auto-opens browser**: Unless `--no-browser` flag is used

## Testing & Verification

All results are reproducible:
```bash
# Verify specific historical date
python3 UTXOracle.py -d 2025/10/15

# Should output: $111,652
```

Compare against historical_data files to verify algorithm consistency.

## License

Blue Oak Model License 1.0.0 - permissive open-source license designed for simplicity and developer freedom.
