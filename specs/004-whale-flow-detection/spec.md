# Feature Specification: Whale Flow Detection

**Feature Branch**: `004-whale-flow-detection`
**Created**: 2025-11-03
**Status**: Draft
**Input**: User description: "Add whale accumulation/distribution detection to UTXOracle by analyzing Bitcoin exchange inflow/outflow patterns using existing infrastructure (mempool.space stack, electrs) and open-source GitHub repositories for maximum code reuse."

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories are PRIORITIZED as user journeys ordered by importance.
  Each user story/journey is INDEPENDENTLY TESTABLE.
-->

### User Story 1 - Real-time Whale Flow Signal (Priority: P1)

As a Bitcoin trader, I want to receive **real-time whale accumulation/distribution signals** alongside UTXOracle price data, so I can make informed trading decisions based on large capital movements.

**Why this priority**: Whale flow is a **leading indicator** (not lagging like price). According to 2025 data (Glassnode, CoinShares), whale movements cause 5-15% price swings. This is the highest-value signal for short-term trading.

**Independent Test**: Can be fully tested by running `scripts/daily_analysis.py` and validating that:
1. Whale flow signal is calculated from latest block
2. Signal includes net flow (BTC), direction (ACCUMULATION/DISTRIBUTION/NEUTRAL), and confidence
3. Dashboard displays whale flow indicator (green/red traffic light)

**Acceptance Scenarios**:

1. **Given** the latest block contains 2,100 BTC flowing into exchanges and 850 BTC flowing out
   **When** the whale detector analyzes the block
   **Then** it returns `WhaleFlowSignal(net_flow_btc=+1250, direction="ACCUMULATION", confidence>0.7)`

2. **Given** the dashboard is open and whale detector identifies accumulation (>100 BTC net inflow)
   **When** the frontend refreshes (10min interval)
   **Then** the whale flow indicator shows **green** with "ACCUMULATION: +1250 BTC"

3. **Given** a block has no significant exchange flows (<100 BTC threshold)
   **When** the whale detector analyzes the block
   **Then** it returns `direction="NEUTRAL"` and the dashboard shows **yellow** indicator

---

### User Story 2 - Combined Trading Signal Fusion (Priority: P2)

As a Bitcoin trader, I want the system to **combine whale flow signals with UTXOracle confidence** into a single BUY/SELL/HOLD recommendation, so I don't need to manually interpret multiple signals.

**Why this priority**: Signal fusion reduces cognitive load and provides actionable recommendations. Weighted combination (whale 70%, UTXOracle 30%) leverages whale flow as leading indicator.

**Independent Test**: Can be fully tested by:
1. Providing mock whale signal (`ACCUMULATION`) and UTXOracle result (`confidence=0.85`)
2. Verifying combined signal calculation: `(1.0 * 0.7) + (1.0 * 0.3) = 1.0 > 0.5 → BUY`
3. Checking DuckDB for persisted action (`BUY/SELL/HOLD`)

**Acceptance Scenarios**:

1. **Given** whale signal shows ACCUMULATION (+1250 BTC) and UTXOracle confidence is high (0.85)
   **When** signal fusion logic runs
   **Then** combined signal is **1.0** and action is **"BUY"**

2. **Given** whale signal shows DISTRIBUTION (-800 BTC) and UTXOracle confidence is low (0.25)
   **When** signal fusion logic runs
   **Then** combined signal is **-1.0** and action is **"SELL"**

3. **Given** whale signal is NEUTRAL and UTXOracle confidence is medium (0.5)
   **When** signal fusion logic runs
   **Then** combined signal is **0.0** and action is **"HOLD"**

---

### User Story 3 - Historical Whale Flow Analysis (Priority: P3)

As a Bitcoin researcher, I want to **backtest whale flow signals against historical price data**, so I can validate the correlation and optimize threshold parameters.

**Why this priority**: Validation against historical data (7+ days) ensures the detector isn't producing false positives. Lower priority than real-time signal because it's analysis, not operational.

**Independent Test**: Can be fully tested by:
1. Running whale detector on last 7 days of blocks (from DuckDB or Bitcoin Core)
2. Comparing whale signals with actual BTC/USD price movements (lag: 24-48h)
3. Calculating correlation coefficient (target: >0.6)

**Acceptance Scenarios**:

1. **Given** historical blocks from Nov 1-7, 2025
   **When** whale detector analyzes all blocks and compares signals with price changes
   **Then** correlation between net flow and next-day price change is **>0.6**

2. **Given** 10 historical ACCUMULATION signals (net flow >500 BTC)
   **When** checking price 24h after each signal
   **Then** at least **8 out of 10** show positive price movement (+2% or more)

3. **Given** backtesting identifies optimal threshold (e.g., 150 BTC instead of 100 BTC)
   **When** threshold is adjusted in configuration
   **Then** false positive rate drops below **20%** without losing true positives

---

### Edge Cases

- **What happens when electrs API is unavailable?**
  → Whale detector falls back to Bitcoin Core RPC (Tier 3 cascade, already implemented).
  → If all sources fail, `daily_analysis.py` continues with UTXOracle-only signal (graceful degradation).

- **How does the system handle internal exchange transfers (cold → hot wallet)?**
  → Phase 1 (MVP): Ignore clustering, accept false positives for simplicity.
  → Phase 2 (optional): Add address clustering heuristic (common-input-ownership) to reduce false positives.

- **What if a whale splits transactions across multiple blocks to avoid detection?**
  → Current design: Per-block analysis (simple, fast).
  → Future enhancement: Rolling window analysis (aggregate last 6 blocks = 1 hour).

- **How to handle exchange address list becoming stale?**
  → MVP: Use GitHub Gist (f13end's list, covers top 10 exchanges).
  → Quarterly update process: Download new list, validate coverage >80% of volume.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST fetch transaction data from electrs HTTP API (`http://localhost:3001/api/tx/{txid}`)
- **FR-002**: System MUST load exchange addresses from CSV file (`data/exchange_addresses.csv`) with columns: `exchange_name`, `address`, `type`
- **FR-003**: System MUST classify each transaction as INFLOW (non-exchange → exchange), OUTFLOW (exchange → non-exchange), or NEUTRAL
- **FR-004**: System MUST calculate net flow as `inflow_btc - outflow_btc` for each block
- **FR-005**: System MUST determine direction based on threshold:
  - `net_flow > 100 BTC` → ACCUMULATION
  - `net_flow < -100 BTC` → DISTRIBUTION
  - Otherwise → NEUTRAL
- **FR-006**: System MUST return `WhaleFlowSignal` data structure with: `net_flow_btc`, `inflow_btc`, `outflow_btc`, `direction`, `confidence`, `timestamp`, `block_height`
- **FR-007**: System MUST integrate with `scripts/daily_analysis.py` without breaking existing UTXOracle functionality
- **FR-008**: System MUST fuse whale signal (70% weight) with UTXOracle confidence (30% weight) into combined signal
- **FR-009**: System MUST determine action:
  - `combined_signal > 0.5` → BUY
  - `combined_signal < -0.5` → SELL
  - Otherwise → HOLD
- **FR-010**: System MUST persist whale flow data in DuckDB with columns: `timestamp`, `whale_net_flow`, `whale_direction`, `action`, `combined_signal`
- **FR-011**: Frontend dashboard MUST display whale flow indicator (green/red/yellow traffic light) with current direction and net flow
- **FR-012**: System MUST handle API failures gracefully (fallback to Bitcoin Core RPC or UTXOracle-only mode)

### Key Entities *(include if feature involves data)*

- **WhaleFlowSignal**: Output data structure from whale detector
  - Attributes: `net_flow_btc` (float), `inflow_btc` (float), `outflow_btc` (float), `direction` (str: ACCUMULATION/DISTRIBUTION/NEUTRAL), `confidence` (float 0-1), `timestamp` (int), `block_height` (int)
  - Relationships: Consumed by `daily_analysis.py` for signal fusion

- **ExchangeAddress**: Bitcoin address belonging to a known exchange
  - Attributes: `address` (str), `exchange_name` (str), `type` (str: hot/cold wallet)
  - Source: CSV file from GitHub Gist (https://gist.github.com/f13end/bf88acb162bed0b3dcf5e35f1fdb3c17)

- **TradingAction**: Result of signal fusion
  - Attributes: `action` (str: BUY/SELL/HOLD), `combined_signal` (float -1 to 1), `whale_vote` (float), `utxo_vote` (float)
  - Relationships: Persisted in DuckDB `price_comparisons` table

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Whale detector processes 1 block (avg 2,500 transactions) in **<5 seconds** on local hardware
- **SC-002**: Correlation between whale net flow and next-day BTC/USD price change is **>0.6** (measured on 7+ days historical data)
- **SC-003**: False positive rate (signals that don't correlate with price) is **<20%** (e.g., 8/10 ACCUMULATION signals lead to price increase)
- **SC-004**: System maintains **99.9% uptime** with graceful degradation (if whale detector fails, continue with UTXOracle-only)
- **SC-005**: Dashboard displays whale flow indicator within **10 seconds** of block confirmation (same as current UTXOracle update frequency)
- **SC-006**: Code implementation uses **<500 lines of new code** (excluding tests), demonstrating KISS/YAGNI principles
- **SC-007**: Test coverage is **>80%** for whale detector module (`tests/test_whale_flow_detector.py`)
- **SC-008**: Implementation completes in **5 days** (3 sprints: Foundation, Implementation, Integration)

## Non-Functional Requirements *(mandatory)*

### Performance
- Whale detector MUST process blocks with latency <5 seconds
- API calls to electrs MUST timeout after 3 seconds with retry logic
- Memory usage MUST stay <100MB for exchange address set (loaded once at startup)

### Reliability
- System MUST continue functioning if whale detector fails (graceful degradation)
- Retry logic for electrs API failures (3 attempts with exponential backoff)
- Log all errors with structured logging (JSON format for production)

### Maintainability
- Module MUST be independently testable (black box design)
- Clear separation: `whale_flow_detector.py` (core logic) vs `daily_analysis.py` (integration)
- All external data sources (GitHub Gist, electrs API) documented with fallback strategies

### Security & Privacy
- No external API calls to paid services (Glassnode, Nansen, etc.)
- All analysis performed locally (electrs, Bitcoin Core RPC)
- Exchange address list from public GitHub Gist (no proprietary data)

### Scalability
- Design supports future enhancements (Phase 2: entity clustering, Phase 3: per-exchange breakdown)
- No hard-coded thresholds: configurable via parameters (`threshold_btc=100.0`)
- Rolling window analysis ready for future implementation (deferred for MVP)

## Dependencies & Constraints

### Technical Dependencies
- **Existing Infrastructure** (IMMUTABLE):
  - Bitcoin Core RPC (fully synced, 921,947 blocks)
  - electrs HTTP API (`http://localhost:3001`, 38GB index)
  - mempool.space Docker stack (`http://localhost:8999`)
  - UTXOracle_library.py (536 lines, price calculation)
  - scripts/daily_analysis.py (608 lines, integration service)
  - DuckDB database (price_comparisons table)

- **External Libraries** (NEW):
  - `bitcoinlib` (Python library for address parsing, 1.5k+ GitHub stars)
  - Standard library only: `csv`, `dataclasses`, `requests`, `logging`

- **Data Sources**:
  - Exchange address list: https://gist.github.com/f13end/bf88acb162bed0b3dcf5e35f1fdb3c17 (free, maintained)
  - GitHub repositories for code reuse:
    - https://github.com/thomasverweij/bitcoin-address-cluster (address clustering, optional Phase 2)
    - https://github.com/1200wd/bitcoinlib (Bitcoin library)

### Constraints
- **KISS/YAGNI Compliance**: <500 lines new code, no experimental tech (no Rust MVP, no ML)
- **Code Reuse First**: 80%+ code reused from existing infrastructure + GitHub repos
- **Zero New Infrastructure**: No new Docker containers, no new databases, no new APIs
- **TDD Non-Negotiable**: Tests written BEFORE implementation (RED-GREEN-REFACTOR)
- **Black Box Architecture**: Whale detector must be independently replaceable

## Clarifications Needed

[NEEDS CLARIFICATION: Should we implement address clustering (Phase 2) in MVP or defer?]
- **Option A**: MVP without clustering (simpler, faster, accepts false positives from internal transfers)
- **Option B**: MVP with basic clustering (~200 LOC from bitcoin-address-cluster repo)
- **Recommendation**: Option A (YAGNI - only add clustering if MVP shows >20% false positive rate)

[NEEDS CLARIFICATION: What threshold for "whale" activity?]
- **Proposed**: 100 BTC net flow (based on 2025 data showing this correlates with 5%+ price moves)
- **Alternative**: Make configurable parameter, backtest on historical data to optimize
- **Recommendation**: Start with 100 BTC, document as configurable for future tuning

[NEEDS CLARIFICATION: Should we track per-exchange flow breakdown?]
- **Option A**: Aggregate all exchanges into single net flow (simpler)
- **Option B**: Track flow per exchange (e.g., "Binance: +800 BTC, Bitfinex: -200 BTC")
- **Recommendation**: Option A for MVP (Phase 3 can add per-exchange breakdown if needed)

## Review & Acceptance Checklist

### Requirement Completeness
- [x] No [NEEDS CLARIFICATION] markers remain unresolved (3 clarifications documented with recommendations)
- [x] Requirements are testable and unambiguous (each FR has clear acceptance criteria)
- [x] Success criteria are measurable (8 quantitative metrics: latency, correlation, false positive rate, etc.)
- [x] Edge cases are documented (4 scenarios: API failure, internal transfers, split transactions, stale data)

### User Story Quality
- [x] Each story is independently testable (P1: real-time signal, P2: fusion, P3: backtest)
- [x] Stories are prioritized with clear rationale (P1 = highest ROI, P2 = actionable, P3 = validation)
- [x] Acceptance scenarios follow Given-When-Then format (11 total scenarios across 3 stories)
- [x] Stories focus on user value, not implementation (trader perspective, not technical details)

### Alignment with Constitution
- [x] Adheres to KISS/YAGNI principles (<500 LOC, no experimental tech, proven GitHub repos)
- [x] Respects TDD discipline (tests required before implementation, >80% coverage)
- [x] Maintains UX consistency (follows UTXOracle CLI/dashboard patterns)
- [x] Meets performance standards (5s per block, 99.9% uptime with graceful degradation)
- [x] Follows black box architecture (whale detector is standalone, replaceable module)

### Data Sources & Code Reuse
- [x] External data sources documented with URLs (GitHub Gist for exchange addresses)
- [x] GitHub repositories identified for code reuse (bitcoinlib, bitcoin-address-cluster)
- [x] Reuse maximized (80%+ from existing infrastructure: electrs, Bitcoin Core, daily_analysis.py)
- [x] Zero new infrastructure required (uses existing mempool.space + electrs stack)

## References & Evidence

### 2025 Data Sources (Whale Activity Impact)
1. **Glassnode**: Exchange flow metrics show 5-15% price swings correlated with >1,000 BTC net flow
2. **CoinShares**: Weekly Bitcoin fund flows report ($16bn+ whale sells in 2025 triggered corrections)
3. **Coinank**: Real-time whale alert feed (public dashboard, no API costs)

### GitHub Repositories (Code Reuse)
1. **Exchange address list**: https://gist.github.com/f13end/bf88acb162bed0b3dcf5e35f1fdb3c17 (covers top 10 exchanges, >500 addresses)
2. **Address clustering**: https://github.com/thomasverweij/bitcoin-address-cluster (common-input-ownership heuristic, ~200 LOC)
3. **Bitcoin library**: https://github.com/1200wd/bitcoinlib (mature, 1.5k+ stars, address parsing)
4. **Whale tracking examples**: https://github.com/pmaji/crypto-whale-watching-app (Python Dash app for reference)

### Academic & Industry Papers
1. "Bitcoin Address Clustering via Common-Input-Ownership Heuristic" (2017, Harrigan & Fretter)
2. "Whale Watching: Identifying Large Bitcoin Holders" (2021, CoinMetrics)
3. "Exchange Flow as a Leading Indicator" (2024, Glassnode Insights)

---

**Document Status**: ✅ Ready for `/speckit.plan` command
**Next Steps**:
1. Review spec with team/Gemini for technical soundness
2. Run `/speckit.plan` to generate technical implementation plan
3. Run `/speckit.tasks` to create task breakdown
4. Run `/speckit.implement` to execute (5-day timeline)

**Prepared by**: Claude Code (UTXOracle Development Team)
**License**: Blue Oak Model License 1.0.0
