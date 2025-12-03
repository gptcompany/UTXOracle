# Feature Specification: On-Chain Metrics Core

**Feature Branch**: `007-onchain-metrics-core`
**Created**: 2025-12-03
**Status**: Draft
**Input**: User description: "Implement core on-chain metrics bundle: Monte Carlo signal fusion upgrade, Active Addresses tracking, and TX Volume USD calculation. These are foundational metrics that enhance UTXOracle's analytical capabilities with minimal complexity and high ROI."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Monte Carlo Signal Fusion (Priority: P1)

As a Bitcoin trader, I want the signal fusion to provide **confidence intervals** via Monte Carlo sampling instead of simple linear weighting, so I can better understand the uncertainty in BUY/SELL/HOLD recommendations.

**Why this priority**: Current linear fusion (0.7×whale + 0.3×utxo) provides point estimate only. Monte Carlo bootstrap sampling adds confidence intervals (e.g., "BUY with 85% confidence"), enabling better risk management. This is a high-ROI upgrade (~150 LOC) to existing infrastructure.

**Independent Test**: Can be fully tested by:
1. Providing mock whale signal and UTXOracle confidence with known distributions
2. Running Monte Carlo sampling (1000 iterations)
3. Verifying output includes mean, std, and confidence intervals

**Acceptance Scenarios**:

1. **Given** whale signal ACCUMULATION (+200 BTC, confidence 0.8) and UTXOracle confidence 0.85
   **When** Monte Carlo fusion runs with 1000 bootstrap samples
   **Then** output includes `signal_mean`, `signal_std`, `confidence_interval_95` (e.g., [0.72, 0.98])

2. **Given** conflicting signals (whale DISTRIBUTION, UTXOracle high confidence)
   **When** Monte Carlo fusion runs
   **Then** `signal_std` is higher than non-conflicting case (uncertainty reflected)

3. **Given** Monte Carlo fusion produces `signal_mean=0.75, CI_95=[0.65, 0.85]`
   **When** action is determined
   **Then** action is "BUY" with `action_confidence=0.85` (based on CI not crossing threshold)

---

### User Story 2 - Active Addresses Metric (Priority: P1)

As a Bitcoin analyst, I want to see the **number of active addresses** per block/day alongside whale flow, so I can assess network health and user adoption trends.

**Why this priority**: Active addresses is a fundamental on-chain metric (used by Glassnode, CheckOnChain) indicating network activity. Data is already available from Bitcoin Core RPC - zero new infrastructure needed. Quick win (~100 LOC).

**Independent Test**: Can be fully tested by:
1. Fetching block data from Bitcoin Core RPC (or electrs)
2. Counting unique addresses in inputs + outputs
3. Comparing with known block explorer values

**Acceptance Scenarios**:

1. **Given** block 870000 with known transaction data
   **When** active addresses are calculated
   **Then** count matches block explorer (±5% tolerance for methodology differences)

2. **Given** daily analysis runs for a 24h period
   **When** active addresses are aggregated
   **Then** result shows unique addresses (deduplicated across blocks)

3. **Given** active addresses metric is calculated
   **When** stored in DuckDB
   **Then** schema includes: `timestamp`, `block_height`, `active_addresses_24h`, `unique_senders`, `unique_receivers`

---

### User Story 3 - TX Volume USD (Priority: P1)

As a Bitcoin analyst, I want to see **total transaction volume in USD** using UTXOracle's on-chain price, so I can assess economic activity without relying on exchange APIs.

**Why this priority**: TX Volume USD leverages existing data (tx amounts + UTXOracle price) with trivial calculation. Provides economic activity metric comparable to CheckOnChain but privacy-preserving (no exchange API). ~80 LOC.

**Independent Test**: Can be fully tested by:
1. Fetching transactions from daily analysis
2. Summing output values in BTC
3. Multiplying by UTXOracle price for USD equivalent

**Acceptance Scenarios**:

1. **Given** 1000 transactions with total output of 5000 BTC and UTXOracle price $100,000
   **When** TX Volume USD is calculated
   **Then** result is $500,000,000

2. **Given** daily analysis completes with valid UTXOracle price
   **When** TX Volume USD is stored
   **Then** DuckDB contains: `timestamp`, `tx_volume_btc`, `tx_volume_usd`, `utxoracle_price_used`

3. **Given** UTXOracle confidence is below threshold (0.3)
   **When** TX Volume USD is calculated
   **Then** `tx_volume_usd` is NULL or flagged as `low_confidence=true`

---

### Edge Cases

- **What happens when Monte Carlo sampling produces bimodal distribution?**
  → Report both modes with separate confidence intervals; set `distribution_type="bimodal"` flag.

- **What happens when active addresses count is anomalously high (spam attack)?**
  → Add `is_anomaly` flag when count > 3σ from 30-day moving average.

- **What happens when UTXOracle price is unavailable?**
  → TX Volume USD returns BTC amount only; USD field is NULL with `price_unavailable=true`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Monte Carlo fusion MUST perform 1000 bootstrap samples by default (configurable)
- **FR-002**: Monte Carlo output MUST include: mean, std, 95% CI, action, action_confidence
- **FR-003**: Active addresses MUST count unique addresses from transaction inputs AND outputs
- **FR-004**: Active addresses MUST deduplicate across blocks for daily aggregation
- **FR-005**: TX Volume USD MUST use UTXOracle price (not exchange price) for privacy-preservation
- **FR-006**: TX Volume USD MUST flag results when UTXOracle confidence < threshold
- **FR-007**: All metrics MUST be stored in existing DuckDB schema (extend `price_history` table or create `metrics` table)
- **FR-008**: All metrics MUST be calculated during `daily_analysis.py` run (no separate cronjob)
- **FR-009**: API endpoint `/api/metrics/latest` MUST return all three metrics in single response
- **FR-010**: Monte Carlo fusion MUST complete in <100ms for 1000 samples (performance constraint)

### Non-Functional Requirements

- **NFR-001**: Zero new external dependencies (use numpy only if already installed, else pure Python)
- **NFR-002**: Backward compatible with existing signal fusion (linear mode as fallback)
- **NFR-003**: All code follows existing patterns in `daily_analysis.py` and `UTXOracle_library.py`

### Key Entities *(include if feature involves data)*

```python
@dataclass
class MonteCarloFusionResult:
    signal_mean: float           # Mean of bootstrap samples
    signal_std: float            # Standard deviation
    ci_lower: float              # 95% CI lower bound
    ci_upper: float              # 95% CI upper bound
    action: str                  # BUY/SELL/HOLD
    action_confidence: float     # Probability action is correct
    n_samples: int               # Number of bootstrap iterations
    distribution_type: str       # "unimodal" | "bimodal"

@dataclass
class ActiveAddressesMetric:
    timestamp: datetime
    block_height: int
    active_addresses_block: int  # Unique addresses in single block
    active_addresses_24h: int    # Unique addresses in last 24h
    unique_senders: int          # Unique input addresses
    unique_receivers: int        # Unique output addresses
    is_anomaly: bool             # True if > 3σ from MA

@dataclass
class TxVolumeMetric:
    timestamp: datetime
    tx_count: int                # Number of transactions
    tx_volume_btc: float         # Total BTC transferred
    tx_volume_usd: float | None  # USD equivalent (None if price unavailable)
    utxoracle_price_used: float  # Price used for conversion
    low_confidence: bool         # True if UTXOracle confidence < 0.3
```

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Monte Carlo fusion provides CI that contains true signal 95% of time (validated via backtest)
- **SC-002**: Active addresses metric matches Blockstream.info within ±10% for same block
- **SC-003**: TX Volume USD calculation adds <50ms to daily analysis runtime
- **SC-004**: All three metrics visible in API response within 1 second of request
- **SC-005**: Zero regressions in existing daily_analysis.py tests
- **SC-006**: Code coverage for new modules ≥80%

### Definition of Done

- [ ] Monte Carlo fusion implemented with configurable sample count
- [ ] Active addresses calculated per block and aggregated daily
- [ ] TX Volume USD calculated using UTXOracle price
- [ ] DuckDB schema extended for new metrics
- [ ] API endpoint `/api/metrics/latest` returns all metrics
- [ ] Unit tests for all three features (≥80% coverage)
- [ ] Integration test: full daily_analysis.py run with new metrics
- [ ] Documentation updated in CLAUDE.md
- [ ] Performance validated (<100ms Monte Carlo, <50ms TX Volume)

## Technical Notes

### Implementation Order (KISS)

1. **TX Volume USD** (easiest, ~80 LOC) - leverages existing tx data
2. **Active Addresses** (~100 LOC) - simple count from existing data
3. **Monte Carlo Fusion** (~150 LOC) - upgrade existing fusion

### Files to Modify

- `scripts/daily_analysis.py` - Add metric calculations to main flow
- `api/main.py` - Add `/api/metrics/latest` endpoint
- `scripts/models/` - Add new dataclass models (or extend existing)

### Files to Create

- `scripts/metrics/monte_carlo_fusion.py` - Bootstrap sampling logic
- `scripts/metrics/active_addresses.py` - Address counting logic
- `scripts/metrics/tx_volume.py` - Volume calculation logic
- `tests/test_onchain_metrics.py` - Test suite for all three metrics

### Dependencies

- **Internal**: `UTXOracle_library.py`, `daily_analysis.py`, `api/main.py`
- **External**: None (pure Python, optionally numpy for faster sampling)
- **Data**: Bitcoin Core RPC (already connected), DuckDB (already configured)

## Out of Scope

- Real-time streaming of metrics (batch only for now)
- Historical backfill (future spec if needed)
- Visualization in whale_dashboard.html (separate spec)
- Comparison with CheckOnChain metrics (research task, not implementation)
