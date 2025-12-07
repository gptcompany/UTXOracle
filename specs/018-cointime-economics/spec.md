# Feature Specification: Cointime Economics Framework

**Feature Branch**: `018-cointime-economics`
**Created**: 2025-12-06
**Status**: Draft
**Prerequisites**: spec-017 (UTXO Lifecycle Engine) complete
**Priority**: TIER A (Score 62, 3-4 weeks after spec-017)
**Evidence Grade**: A (ARK Invest + Glassnode White Paper, 2023)

## Context & Motivation

### Background: A Superior Framework

Cointime Economics was introduced in 2023 by James Check (Glassnode) and David Puell (ARK Invest) as a revolutionary approach to Bitcoin on-chain analysis that **removes heuristic assumptions**.

| Traditional Approach | Problem | Cointime Solution |
|---------------------|---------|-------------------|
| HODL Waves | Assumes "hodling" behavior | **Vaultedness**: Objectively measures inactivity |
| Active Supply | Subjective threshold | **Liveliness**: Mathematical ratio |
| MVRV | Single ratio, no context | **AVIV**: Activity-weighted realized value |

### Core Innovation: Coinblocks

```
Coinblocks Created = BTC × Blocks Held
Coinblocks Destroyed = BTC × Blocks Since Last Move (when spent)
```

### Key Metrics

| Metric | Formula | Meaning |
|--------|---------|---------|
| **Liveliness** | Destroyed / Created | Network activity (0-1) |
| **Vaultedness** | 1 - Liveliness | Network inactivity (0-1) |
| **Active Supply** | Supply × Liveliness | BTC actively moving |
| **Vaulted Supply** | Supply × Vaultedness | BTC dormant |
| **True Market Mean** | Market Cap / Active Supply | Activity-adjusted price |
| **AVIV Ratio** | Price / True Market Mean | Superior MVRV |

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Coinblocks Tracking (Priority: P1)

As a Bitcoin analyst, I want to track **coinblocks created and destroyed**, so I can measure network activity objectively.

**Acceptance Scenarios**:

1. **Given** new UTXO of 1 BTC at block 850,000
   **When** block 850,100 reached (100 blocks later)
   **Then** `coinblocks_created = 1 × 100 = 100`

2. **Given** that UTXO spent at block 850,100
   **When** coinblocks destroyed calculated
   **Then** `coinblocks_destroyed = 1 × 100 = 100`

---

### User Story 2 - Liveliness Calculation (Priority: P1)

As a Bitcoin trader, I want to calculate **network liveliness**, so I can understand whether the network is active or dormant.

**Acceptance Scenarios**:

1. **Given** cumulative coinblocks created = 10B, destroyed = 3B
   **When** liveliness calculated
   **Then** `liveliness = 0.3` (30% active)

2. **Given** liveliness = 0.15 (all-time low range)
   **When** signal generated
   **Then** `extreme_dormancy = True` (accumulation phase)

---

### User Story 3 - AVIV Ratio (Priority: P1)

As a Bitcoin trader, I want the **AVIV ratio** as a superior MVRV.

**Acceptance Scenarios**:

1. **Given** current price = $100K, true market mean = $50K
   **When** AVIV calculated
   **Then** `aviv = 2.0` (potentially overvalued)

2. **Given** AVIV < 1.0
   **When** signal generated
   **Then** `undervalued = True` (bullish accumulation zone)

---

## Requirements *(mandatory)*

### Functional Requirements

**Coinblocks**:
- **FR-001**: Track cumulative coinblocks created (all time)
- **FR-002**: Track cumulative coinblocks destroyed (all time)
- **FR-003**: Per-block destroyed = Σ(spent_btc × blocks_since_creation)

**Liveliness/Vaultedness**:
- **FR-004**: Liveliness = cumulative_destroyed / cumulative_created
- **FR-005**: Vaultedness = 1 - Liveliness
- **FR-006**: Track rolling liveliness (7d, 30d, 90d)

**Supply Metrics**:
- **FR-007**: Active Supply = Total Supply × Liveliness
- **FR-008**: Vaulted Supply = Total Supply × Vaultedness

**Valuation**:
- **FR-009**: True Market Mean = Market Cap / Active Supply
- **FR-010**: AVIV Ratio = Current Price / True Market Mean

**Integration**:
- **FR-011**: Cointime vote in enhanced fusion (10th component)
- **FR-012**: Default weight: 0.12
- **FR-013**: API endpoint `/api/metrics/cointime`

### Key Entities *(mandatory)*

```python
@dataclass
class CoinblocksMetrics:
    block_height: int
    coinblocks_created: float
    coinblocks_destroyed: float
    cumulative_created: float
    cumulative_destroyed: float
    liveliness: float
    vaultedness: float

@dataclass
class CointimeValuation:
    block_height: int
    active_supply_btc: float
    true_market_mean_usd: float
    aviv_ratio: float
    valuation_zone: str  # "UNDERVALUED" | "FAIR" | "OVERVALUED"

@dataclass
class CointimeSignal:
    liveliness_trend: str
    aviv_ratio: float
    extreme_dormancy: bool
    cointime_vote: float
    confidence: float
```

---

## Success Criteria *(mandatory)*

- **SC-001**: Liveliness matches Glassnode within ±2%
- **SC-002**: AVIV ratio matches Glassnode within ±5%
- **SC-003**: Calculation <1s per block
- **SC-004**: Positive contribution to fusion Sharpe
- **SC-005**: Code coverage ≥85%

### Definition of Done

- [ ] Coinblocks calculation from UTXO lifecycle
- [ ] Liveliness and Vaultedness calculation
- [ ] Active/Vaulted Supply split
- [ ] True Market Mean and AVIV Ratio
- [ ] Enhanced fusion extended (10 components)
- [ ] API endpoint `/api/metrics/cointime`
- [ ] Unit tests (≥85% coverage)
- [ ] Documentation updated

---

## Technical Notes

### Files to Create

- `scripts/metrics/cointime.py` - Core calculations
- `tests/test_cointime.py` - Test suite

### Configuration

```bash
COINTIME_ENABLED=true
COINTIME_WEIGHT=0.12
COINTIME_AVIV_UNDERVALUED=1.0
COINTIME_AVIV_OVERVALUED=2.5
```

---

## References

1. **ARK Invest + Glassnode (2023)**. "Cointime Economics"
   - https://www.ark-invest.com/white-papers/cointime-economics

2. **Contadino Galattico**: TIER A ranking, Score 62
