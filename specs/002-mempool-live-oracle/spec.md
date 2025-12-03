# Feature Specification: UTXOracle Live - Real-time Mempool Price Oracle

**Feature Branch**: `002-mempool-live-oracle`
**Created**: 2025-10-19
**Status**: Draft
**Input**: User description: "/media/sam/1TB/UTXOracle/SPECKIT_FEATURE_SPEC.md"

## Problem Statement

### Current Limitation
UTXOracle.py calculates Bitcoin price from **confirmed blocks only** (historical data). This creates:
- **Latency**: Minimum 10-60 minutes delay (block confirmation time)
- **No real-time signal**: Cannot track live market movements
- **Limited use cases**: Only useful for historical analysis, not live trading/monitoring

### Opportunity
Bitcoin Core broadcasts **mempool transactions** in real-time via ZMQ. We can apply UTXOracle's algorithm to **unconfirmed transactions** to estimate price **live** (updated every 0.5-5 seconds).

### Value Proposition
- **Real-time price updates**: Live BTC/USD estimate from mempool activity
- **Exchange-free**: Trust the blockchain, not custodians (same as UTXOracle.py)
- **Transparency**: Every estimate reproducible from public mempool data
- **New use cases**: Live price monitoring, trading signals, market sentiment

---

## User Scenarios & Testing

### User Story 1 - Real-time Price Monitoring (Priority: P1)

**As a** Bitcoin enthusiast
**I want to** see live BTC/USD price estimates from mempool
**So that** I can track market movements without relying on exchange APIs

**Why this priority**: Core value proposition - without this, there's no product

**Independent Test**: Open browser → see live price updating every 0.5-5 seconds → price matches exchange rates ±2%

**Acceptance Scenarios**:

1. **Given** Bitcoin Core node running with mempool activity
   **When** I open http://localhost:8000
   **Then** I see current price estimate displayed prominently (e.g., "$113,600")

2. **Given** I'm viewing the live dashboard
   **When** new transactions enter mempool
   **Then** price updates within 5 seconds

3. **Given** I leave browser tab open for 1 hour
   **When** I check the price
   **Then** it's still updating (no crashes/freezes)

---

### User Story 2 - Visual Transaction Flow (Priority: P2)

**As a** data analyst
**I want to** visualize mempool transactions as scatter plot (timestamp vs price)
**So that** I can identify price clusters and market trends

**Why this priority**: Enhances understanding beyond raw numbers, aligns with UTXOracle's HTML visualization tradition

**Independent Test**: See live scatter plot with transaction dots appearing in real-time, mouseover shows details

**Acceptance Scenarios**:

1. **Given** I'm viewing the live dashboard
   **When** transactions are processed
   **Then** I see dots appearing on scatter plot (X=timestamp, Y=estimated price)

2. **Given** scatter plot has 500+ transactions
   **When** I hover over a dot
   **Then** tooltip shows: price ($113,550), timestamp (HH:MM:SS)

3. **Given** I'm on laptop with 2000 active transactions
   **When** I watch the visualization
   **Then** it renders smoothly at ≥30 FPS (no lag)

---

### User Story 3 - Confidence Awareness (Priority: P2)

**As a** technical user
**I want to** see confidence score for current price estimate
**So that** I know how reliable the signal is

**Why this priority**: Critical for trust - users need to know when estimate is reliable vs uncertain

**Independent Test**: Price displays with confidence score 0.0-1.0, low confidence shows warning

**Acceptance Scenarios**:

1. **Given** mempool has 1000+ qualifying transactions
   **When** I view dashboard
   **Then** confidence score shows 0.8-1.0 (high confidence)

2. **Given** mempool just started (only 10 transactions)
   **When** I view dashboard
   **Then** confidence score shows 0.1-0.3 + warning "Low confidence - warming up"

3. **Given** I'm watching for 10 minutes
   **When** confidence drops below 0.5
   **Then** price display changes color (yellow/orange) to indicate uncertainty

---

### User Story 4 - System Health Visibility (Priority: P3)

**As a** system operator
**I want to** see mempool processing statistics
**So that** I can verify system is working correctly

**Why this priority**: Important for debugging/monitoring, but not core user value

**Independent Test**: Dashboard shows: total received, filtered, active transactions, uptime

**Acceptance Scenarios**:

1. **Given** system running for 1 hour
   **When** I view dashboard
   **Then** I see stats: "Received: 12,543 | Filtered: 8,234 | Active: 4,309 | Uptime: 1h 02m"

2. **Given** Bitcoin node goes offline
   **When** I check dashboard
   **Then** connection status shows "Disconnected" (red indicator)

3. **Given** I want to validate processing
   **When** I compare "total received" to Bitcoin Core mempool count
   **Then** numbers match ±5% (proves ZMQ working correctly)

---

### Edge Cases

- **What happens when Bitcoin node connection is lost?** System displays "Disconnected" status and attempts auto-reconnect within 5 seconds
- **What happens when mempool is empty (low network activity)?** System displays low confidence warning and falls back to last known valid estimate
- **What happens when browser tab is backgrounded?** WebSocket connection maintains updates, visualization pauses to save resources but resumes on tab focus
- **What happens with invalid transactions?** System filters out non-market transactions (round BTC amounts, same as UTXOracle.py algorithm)
- **What happens when visualization has too many points (>2000)?** Canvas 2D performance degrades; this is a known limitation for MVP, with WebGL upgrade path for production

---

## Requirements

### Functional Requirements

- **FR-001**: System MUST listen to Bitcoin Core ZMQ feed for real-time mempool transactions
- **FR-002**: System MUST parse binary transaction data to extract output values and timestamps
- **FR-003**: System MUST filter transactions using UTXOracle algorithm (remove round BTC amounts, apply stencil logic)
- **FR-004**: System MUST calculate live price estimate using histogram clustering and convergence algorithm (reuse UTXOracle.py Steps 5-11)
- **FR-005**: System MUST update price estimate within 5 seconds of new transactions entering mempool
- **FR-006**: System MUST calculate confidence score based on transaction count and distribution
- **FR-007**: System MUST stream price updates to browser clients via WebSocket connection
- **FR-008**: System MUST render live scatter plot visualization showing timestamp vs estimated price
- **FR-009**: System MUST display tooltips on hover showing transaction price and timestamp
- **FR-010**: System MUST display current price prominently with confidence score
- **FR-011**: System MUST show visual warning (color change) when confidence drops below 0.5
- **FR-012**: System MUST display system statistics: transactions received/filtered/active, uptime, connection status
- **FR-013**: System MUST auto-reconnect to Bitcoin Core ZMQ feed within 5 seconds if connection drops
- **FR-014**: System MUST maintain 3-hour rolling window of mempool transactions (same as UTXOracle.py)
- **FR-015**: System MUST work in browser without requiring npm/webpack build step (vanilla JavaScript)
- **FR-016**: System MUST render visualization at ≥30 FPS with up to 2000 active transactions
- **FR-017**: System MUST match visual style of UTXOracle.py HTML output (black background, cyan/orange theme)

### Key Entities

- **MempoolTransaction**: Represents an unconfirmed Bitcoin transaction with extracted output values, timestamp, and estimated price contribution
- **PriceEstimate**: Current BTC/USD price calculation with confidence score, timestamp, and contributing transaction count
- **TransactionHistogram**: Distribution of transaction values over time, used for statistical clustering (same as UTXOracle.py Step 6)
- **PriceFindingStencil**: Statistical clustering framework for identifying market price from transaction data (same as UTXOracle.py Step 8)
- **SystemStatistics**: Operational metrics including transactions received/filtered/active, uptime, connection status

---

## Success Criteria

### Measurable Outcomes

#### MVP Complete (Target: Week 14)

- **SC-001**: Real-time price updates display every 0.5-5 seconds
- **SC-002**: Price estimate accuracy within ±2% of exchange rates
- **SC-003**: Live scatter plot visualization renders using Canvas 2D
- **SC-004**: Confidence score displays accurately based on transaction count
- **SC-005**: System runs continuously for 24+ hours without restart
- **SC-006**: Dashboard works correctly on 3 major browsers (Chrome, Firefox, Safari latest 2 versions)

#### Production Ready (Target: Week 18, Optional)

- **SC-007**: System handles 100 concurrent WebSocket connections
- **SC-008**: Visualization renders at 60 FPS with 50,000 data points using WebGL
- **SC-009**: Historical mempool replay capability available for testing
- **SC-010**: Monitoring and logging system operational for diagnostics

---

## Non-Functional Requirements

### Performance
- **Latency**: Price updates within 5 seconds of new transactions entering mempool
- **Throughput**: Handle 1000+ transactions/second (Bitcoin peak load)
- **Uptime**: Run continuously for 7+ days without restart
- **Accuracy**: Price estimate within ±2% of exchange rates (same as UTXOracle.py)

### Scalability
- **Clients**: Support 100 concurrent WebSocket connections (future public API)
- **History**: Maintain 3-hour rolling window (same as UTXOracle.py)
- **Memory**: Backend <500MB RAM, Frontend <50MB browser heap

### Usability
- **Zero setup**: Open browser → works immediately (if Bitcoin node running)
- **No install**: No npm/webpack required for frontend
- **Cross-browser**: Works on Chrome, Firefox, Safari (Canvas API standard)

---

## Out of Scope (MVP)

- **Authentication/Authorization**: Public/open system for MVP
- **Multi-currency support**: BTC/USD only
- **Historical data storage**: In-memory only (no database)
- **Mobile app**: Browser-only for MVP
- **Exchange comparison**: No external API calls (privacy-first principle)
- **Alerts/notifications**: View-only for MVP

---

## Constraints

### Technical
- **Pure Python backend**: No Rust optimization for MVP (future Phase 3)
- **Zero frontend dependencies**: Vanilla JS + Canvas 2D (no React/Vue/build step)
- **Bitcoin Core dependency**: Requires local node with ZMQ enabled
- **Single-server deployment**: No Redis/PostgreSQL for MVP (in-memory state)

### Business
- **Open source**: Blue Oak Model License 1.0.0 (permissive)
- **No external dependencies**: Cannot rely on exchange APIs (privacy-first)
- **Educational transparency**: Code must be understandable by junior developers

### Design
- **KISS principle**: Boring tech, minimal dependencies (UV, FastAPI, PyZMQ only)
- **YAGNI principle**: Don't build features until needed (no premature optimization)
- **Black box architecture**: Each module independently replaceable

---

## Risks & Mitigations

### Risk 1: Mempool price differs significantly from exchange price
**Likelihood**: Medium
**Impact**: High (breaks core value proposition)
**Mitigation**: Historical validation tests comparing mempool estimates vs confirmed block prices

### Risk 2: Bitcoin node ZMQ feed interruption
**Likelihood**: Medium
**Impact**: Medium (system stops working)
**Mitigation**: Auto-reconnect logic (<5 seconds downtime), connection status indicator

### Risk 3: Browser performance degradation with many transactions
**Likelihood**: High (>2000 points)
**Impact**: Medium (laggy UI)
**Mitigation**: Canvas 2D for MVP (<2k points), WebGL upgrade path for production (50k+ points)

### Risk 4: Complexity creep (adding too many features)
**Likelihood**: High (developer enthusiasm)
**Impact**: Medium (delays MVP)
**Mitigation**: Strict adherence to YAGNI - only P1/P2 user stories for MVP

---

## Visual Reference

### Dual-Panel Design (Production Target)

**LEFT Panel** - Confirmed On-Chain Data:
- **Reference**: `examples/UTXOracle_Local_Node_Price.png`
- **Color scheme**: Black background, cyan/teal points, green price label
- **Data source**: Confirmed blocks (3-hour window)
- **Update rate**: Every ~10 minutes (new block)
- **Point density**: Very high (thousands of points)
- **Purpose**: Show immutable consensus price from blockchain
- **MVP Status**: ⚠️ Optional for MVP (can be static placeholder or omitted)

**RIGHT Panel** - Mempool Live Data:
- **Reference**: `examples/Screenshot from 2025-10-18 09-26-*.png` (sequential)
- **Color scheme**: Black background, orange points, orange/yellow price label
- **Data source**: Real-time mempool transactions
- **Update rate**: Every 0.5-5 seconds (live streaming)
- **Point density**: Medium (300-500 visible points in rolling window)
- **Purpose**: Show real-time market activity before confirmation
- **MVP Status**: ✅ **REQUIRED for MVP** - this is the core feature

### Visual Characteristics
- **Real-time animation**: Points accumulate right-to-left over time
- **Price display**: Large "Avg: $XXX,XXX" prominently shown (orange for mempool)
- **Metadata**: "Last Block: Xmin", timestamp display
- **Point density**: 300-500 visible points (3-hour rolling window)
- **Layout**: Dual-panel split (~50/50) with synchronized Y-axes

**Reference files**:
- `examples/UTXOracle_Local_Node_Price.png` - LEFT panel reference (confirmed data, cyan points)
- `examples/Screenshot from 2025-10-18 09-26-57.png` - RIGHT panel t=0s baseline
- `examples/Screenshot from 2025-10-18 09-27-03.png` - t=6s (points accumulating)
- `examples/Screenshot from 2025-10-18 09-27-11.png` - t=14s (vertical spread)
- `examples/README.md` - Detailed dual-panel comparison table

### Historical Output Reference
UTXOracle.py generates Canvas-based HTML visualizations (example: `historical_data/html_files/UTXOracle_2025-10-16.html`):
- 1000x660px canvas rendering
- Black background with cyan/orange theme
- Interactive tooltips
- Save PNG button
- JavaScript data arrays for plotting

**Design goal**: UTXOracle Live should match this proven visual style.

---

## Related Documents

- **Algorithm Reference**: `UTXOracle.py` (Steps 1-12)
- **Historical Analysis**: `HISTORICAL_DATA.md` (672 days, 99.85% success rate)
- **Visual Reference**: `examples/README.md` (production UI screenshots + analysis)
- **HTML Output Example**: `historical_data/html_files/UTXOracle_2025-10-16.html`
- **Architecture Blueprint**: SPECKIT_TECH_PLAN.md (tech stack, modules, black box design)
- **Task Breakdown**: `docs/tasks/01-05_*.md` (per-module implementation specs)

---

## Assumptions

1. **Bitcoin Core setup**: Users have Bitcoin Core running locally with ZMQ enabled (standard setup for Bitcoin developers)
2. **Browser compatibility**: Latest 2 versions of Chrome, Firefox, Safari (covers 95%+ of users)
3. **Network bandwidth**: Standard broadband connection sufficient for WebSocket streaming (minimal data transfer)
4. **Mempool activity**: Assumes normal Bitcoin network activity (100+ transactions/minute); low-activity periods will have lower confidence scores
5. **UTXOracle algorithm validity**: Assumes existing UTXOracle.py algorithm (Steps 5-11) is valid for mempool data (to be validated via historical testing)
6. **Development environment**: Using UV package manager (as per project standard), Python 3.8+
7. **No authentication needed**: MVP assumes single-user localhost deployment (public API is future scope)
8. **Data retention**: 3-hour rolling window matches UTXOracle.py default (sufficient for price estimation without excessive memory usage)

---

*Feature Specification v1.0 - UTXOracle Live*
*Created*: 2025-10-19
*Status*: Draft - Ready for validation
