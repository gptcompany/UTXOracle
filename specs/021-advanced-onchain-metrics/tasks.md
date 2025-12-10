# spec-021: Tasks

## Task Dependency Graph

```
URPD (P0):           T001 → T002 → T003 → T004 → T005
                                              ↓
Supply P/L (P1):     T006 → T007 → T008 ────────────┐
                                                     ↓
Reserve Risk (P1):   T009 → T010 → T011 ────────────┤
                                                     ↓
Sell-side (P1):      T012 → T013 → T014 ────────────┤
                                                     ↓
CDD/VDD (P2):        T015 → T016 → T017 → T018 ─────┤
                                                     ↓
Integration:                                    T019 → T020
```

---

## URPD (P0) - 4-6 hours

### T001: Create URPD Module Skeleton
**Status:** TODO
**Priority:** P0
**Effort:** 30 min

#### Description
Create `scripts/metrics/urpd.py` with imports and dataclass definitions.

#### Actions
1. Create file with module docstring
2. Define `URPDBucket` dataclass
3. Define `URPDResult` dataclass
4. Define `SRZone` dataclass for support/resistance

#### Dataclasses
```python
@dataclass
class URPDBucket:
    price_low: float
    price_high: float
    btc_amount: float
    utxo_count: int
    pct_of_supply: float

@dataclass
class URPDResult:
    buckets: list[URPDBucket]
    total_supply: float
    current_price: float
    supply_above_price: float
    supply_below_price: float
    dominant_bucket: URPDBucket
    timestamp: datetime

@dataclass
class SRZone:
    price_center: float
    btc_amount: float
    strength: float  # 0-1, based on % of supply
    zone_type: str  # "SUPPORT" or "RESISTANCE"
```

#### Acceptance Criteria
- [ ] File created
- [ ] All dataclasses defined
- [ ] Module imports without error

---

### T002: Implement URPD Core Calculation [E]
**Status:** TODO
**Priority:** P0
**Effort:** 2 hours
**Depends:** T001
**Algorithm:** AlphaEvolve candidate

#### Description
Implement main `calculate_urpd()` function.

#### Algorithm Approaches
- **A (Fixed Buckets)**: Simple $1k/$5k/$10k buckets
- **B (Logarithmic)**: Log-scale for wide price ranges
- **C (Adaptive)**: Cluster detection for natural groupings

#### SQL Query
```sql
SELECT
    FLOOR(creation_price_usd / :bucket_size) * :bucket_size as price_bucket,
    SUM(btc_value) as btc_in_bucket,
    COUNT(*) as utxo_count
FROM utxo_lifecycle
WHERE is_spent = FALSE
GROUP BY price_bucket
ORDER BY price_bucket
```

#### Acceptance Criteria
- [ ] Function implemented
- [ ] < 30 seconds execution
- [ ] Handles empty DB gracefully
- [ ] Configurable bucket size

---

### T003: Implement Supply Above/Below Price
**Status:** TODO
**Priority:** P0
**Effort:** 30 min
**Depends:** T002

#### Description
Calculate how much supply is above/below current price.

#### Implementation
```python
def calculate_supply_distribution(
    urpd: URPDResult,
    current_price: float,
) -> tuple[float, float, float]:
    """Returns (above, below, at_price)."""
    above = sum(b.btc_amount for b in urpd.buckets if b.price_low > current_price)
    below = sum(b.btc_amount for b in urpd.buckets if b.price_high < current_price)
    at_price = urpd.total_supply - above - below
    return (above, below, at_price)
```

#### Acceptance Criteria
- [ ] Correct above/below calculation
- [ ] Handles edge cases (price at bucket boundary)

---

### T004: Implement S/R Zone Detection
**Status:** TODO
**Priority:** P1
**Effort:** 1 hour
**Depends:** T003

#### Description
Detect support/resistance zones from URPD clusters.

#### Logic
```python
def detect_sr_zones(
    urpd: URPDResult,
    current_price: float,
    threshold_pct: float = 3.0,  # Minimum % of supply
) -> list[SRZone]:
    zones = []
    for bucket in urpd.buckets:
        if bucket.pct_of_supply >= threshold_pct:
            zone_type = "RESISTANCE" if bucket.price_low > current_price else "SUPPORT"
            zones.append(SRZone(
                price_center=(bucket.price_low + bucket.price_high) / 2,
                btc_amount=bucket.btc_amount,
                strength=min(1.0, bucket.pct_of_supply / 10.0),
                zone_type=zone_type,
            ))
    return zones
```

#### Acceptance Criteria
- [ ] Zones correctly classified
- [ ] Strength calculation sensible
- [ ] Sorted by proximity to current price

---

### T005: URPD Signal Generation + Tests
**Status:** TODO
**Priority:** P0
**Effort:** 1.5 hours
**Depends:** T004

#### Description
Generate fusion signal and write comprehensive tests.

#### Signal Logic
```python
def urpd_signal(urpd: URPDResult, zones: list[SRZone]) -> tuple[float, float]:
    """
    - Near strong support: +0.3 to +0.6
    - Near strong resistance: -0.3 to -0.6
    - In no-man's-land: 0.0
    """
```

#### Tests
```python
def test_urpd_basic_calculation(test_db):
def test_urpd_empty_db():
def test_urpd_single_bucket():
def test_sr_zone_detection():
def test_urpd_signal_near_support():
def test_urpd_signal_near_resistance():
```

#### Acceptance Criteria
- [ ] Signal generation working
- [ ] All tests pass
- [ ] Coverage > 90%

---

## Supply in Profit/Loss (P1) - 2 hours

### T006: Create Supply P/L Module
**Status:** TODO
**Priority:** P1
**Effort:** 30 min
**Depends:** T005

#### Description
Create `scripts/metrics/supply_profit_loss.py`.

#### Dataclass
```python
@dataclass
class SupplyProfitLoss:
    supply_in_profit: float
    supply_in_loss: float
    supply_breakeven: float
    total_supply: float
    pct_in_profit: float
    pct_in_loss: float
    current_price: float
    signal: str
    confidence: float
    timestamp: datetime
```

#### Acceptance Criteria
- [ ] File created
- [ ] Dataclass defined

---

### T007: Implement P/L Calculation
**Status:** TODO
**Priority:** P1
**Effort:** 45 min
**Depends:** T006

#### SQL
```sql
SELECT
    SUM(CASE WHEN :price > creation_price_usd THEN btc_value ELSE 0 END),
    SUM(CASE WHEN :price < creation_price_usd THEN btc_value ELSE 0 END),
    SUM(CASE WHEN ABS(:price - creation_price_usd) < :price * 0.01 THEN btc_value ELSE 0 END),
    SUM(btc_value)
FROM utxo_lifecycle
WHERE is_spent = FALSE
```

#### Acceptance Criteria
- [ ] Accurate calculation
- [ ] Breakeven within 1% tolerance

---

### T008: P/L Signal + STH/LTH Breakdown + Tests
**Status:** TODO
**Priority:** P1
**Effort:** 45 min
**Depends:** T007

#### Signal Classification
```python
def classify_profit_signal(pct: float) -> tuple[str, float]:
    if pct > 95: return ("EUPHORIA", 0.90)
    if pct > 80: return ("BULL", 0.70)
    if pct > 50: return ("TRANSITION", 0.50)
    return ("CAPITULATION", 0.85)
```

#### Acceptance Criteria
- [ ] Signal classification working
- [ ] STH/LTH breakdown available
- [ ] Tests pass

---

## Reserve Risk (P1) - 2-3 hours

### T009: Create Reserve Risk Module
**Status:** TODO
**Priority:** P1
**Effort:** 30 min
**Depends:** T008

#### Description
Create `scripts/metrics/reserve_risk.py`.

#### Dataclass
```python
@dataclass
class ReserveRiskResult:
    reserve_risk: float
    hodl_bank: float
    price: float
    circulating_supply: float
    signal: str
    confidence: float
    timestamp: datetime
```

#### Acceptance Criteria
- [ ] File created
- [ ] Dataclass defined

---

### T010: Implement HODL Bank Calculation [E]
**Status:** TODO
**Priority:** P1
**Effort:** 1.5 hours
**Depends:** T009
**Algorithm:** AlphaEvolve candidate

#### Description
Calculate cumulative HODL Bank (opportunity cost of NOT selling).

#### Formula Options
- **A**: Sum of all unspent coindays
- **B**: Integrate liveliness from cointime.py
- **C**: Approximate via supply × avg_age

#### Acceptance Criteria
- [ ] HODL Bank calculated
- [ ] Integrates with cointime if possible

---

### T011: Reserve Risk Formula + Signal + Tests
**Status:** TODO
**Priority:** P1
**Effort:** 1 hour
**Depends:** T010

#### Formula
```python
reserve_risk = price / (hodl_bank * circulating_supply)
```

#### Signal Zones
| Reserve Risk | Signal |
|--------------|--------|
| < 0.002 | STRONG_BUY |
| 0.002 - 0.008 | BUY |
| 0.008 - 0.02 | FAIR |
| > 0.02 | SELL |

#### Acceptance Criteria
- [ ] Formula matches Glassnode methodology
- [ ] Signal zones implemented
- [ ] Tests pass

---

## Sell-side Risk (P1) - 2-3 hours

### T012: Create Sell-side Risk Module
**Status:** TODO
**Priority:** P1
**Effort:** 30 min
**Depends:** T011

#### Description
Create `scripts/metrics/sell_side_risk.py`.

#### Acceptance Criteria
- [ ] File created
- [ ] Dataclass defined

---

### T013: Implement Realized Profit Calculation
**Status:** TODO
**Priority:** P1
**Effort:** 1 hour
**Depends:** T012

#### SQL
```sql
SELECT COALESCE(SUM(
    (spend_price_usd - creation_price_usd) * btc_value
), 0)
FROM utxo_lifecycle
WHERE is_spent = TRUE
  AND spent_timestamp >= :cutoff
  AND spend_price_usd > creation_price_usd
```

#### Acceptance Criteria
- [ ] Only counts profits (not losses)
- [ ] Configurable rolling window

---

### T014: Sell-side Risk Ratio + Signal + Tests
**Status:** TODO
**Priority:** P1
**Effort:** 1 hour
**Depends:** T013

#### Formula
```python
sell_side_risk = realized_profit / market_cap
```

#### Signal Zones
| Sell-side Risk | Signal |
|----------------|--------|
| < 0.1% | LOW_DISTRIBUTION |
| 0.1-0.3% | NORMAL |
| 0.3-1.0% | ELEVATED |
| > 1.0% | AGGRESSIVE |

#### Acceptance Criteria
- [ ] Ratio calculated correctly
- [ ] Signal zones implemented
- [ ] Tests pass

---

## CDD/VDD (P2) - 3 hours

### T015: Create Coindays Module
**Status:** TODO
**Priority:** P2
**Effort:** 30 min
**Depends:** T014

#### Description
Create `scripts/metrics/coindays.py`.

#### Dataclass
```python
@dataclass
class CoindaysResult:
    cdd: float
    vdd: float
    cdd_7d_avg: float
    cdd_30d_avg: float
    cdd_365d_avg: float
    vdd_multiple: float
    signal: str
    timestamp: datetime
```

#### Acceptance Criteria
- [ ] File created
- [ ] Dataclass defined

---

### T016: Implement CDD Calculation
**Status:** TODO
**Priority:** P2
**Effort:** 45 min
**Depends:** T015

#### SQL
```sql
SELECT COALESCE(SUM(
    ((spent_block - creation_block) / 144.0) * btc_value
), 0) as cdd
FROM utxo_lifecycle
WHERE is_spent = TRUE
  AND DATE(spent_timestamp) = :target_date
```

#### Acceptance Criteria
- [ ] Daily CDD calculated
- [ ] Age in days (not blocks)

---

### T017: Implement VDD + Rolling Averages
**Status:** TODO
**Priority:** P2
**Effort:** 1 hour
**Depends:** T016

#### VDD Formula
```python
vdd = sum(age_days * btc_value * spend_price for each spent utxo)
```

#### Rolling Averages
- 7-day MA
- 30-day MA
- 365-day MA

#### Acceptance Criteria
- [ ] VDD calculated
- [ ] All rolling averages working
- [ ] VDD Multiple = VDD / 365d_MA

---

### T018: CDD/VDD Signal + Tests
**Status:** TODO
**Priority:** P2
**Effort:** 45 min
**Depends:** T017

#### Signal Logic
```python
def classify_vdd_multiple(mult: float) -> tuple[str, float]:
    if mult > 3.0: return ("EXTREME_DISTRIBUTION", 0.90)
    if mult > 2.0: return ("HIGH_DISTRIBUTION", 0.75)
    if mult > 1.0: return ("NORMAL", 0.50)
    return ("LOW_ACTIVITY", 0.60)
```

#### Acceptance Criteria
- [ ] Signal classification working
- [ ] Tests pass
- [ ] Integration with cointime.py verified

---

## Integration (1-2 hours)

### T019: Update Monte Carlo Fusion
**Status:** TODO
**Priority:** P1
**Effort:** 1 hour
**Depends:** T005, T008, T011, T014, T018

#### Actions
1. Add new weight keys to `ENHANCED_WEIGHTS`
2. Add parameters to `enhanced_fusion()`
3. Update `EnhancedFusionResult` dataclass
4. Rebalance weights (sum = 1.0)

#### New Weights
```python
"urpd": 0.02,
"supply_profit": 0.02,
"reserve_risk": 0.02,
"sell_side": 0.02,
# Total: +0.08, reduce from lower-evidence signals
```

#### Acceptance Criteria
- [ ] All signals integrated
- [ ] Weights sum to 1.0
- [ ] Backward compatible

---

### T020: Full Integration Test + Documentation
**Status:** TODO
**Priority:** P1
**Effort:** 1 hour
**Depends:** T019

#### Actions
1. Integration test with all metrics
2. Update ARCHITECTURE.md
3. Update module __init__.py exports

#### Acceptance Criteria
- [ ] Full pipeline test passes
- [ ] Documentation updated
- [ ] All modules exported

---

## Summary Table

| Task | Description | Effort | Priority | [E] |
|------|-------------|--------|----------|-----|
| T001 | URPD module skeleton | 30 min | P0 | |
| T002 | URPD core calculation | 2h | P0 | [E] |
| T003 | Supply above/below | 30 min | P0 | |
| T004 | S/R zone detection | 1h | P1 | |
| T005 | URPD signal + tests | 1.5h | P0 | |
| T006 | Supply P/L module | 30 min | P1 | |
| T007 | P/L calculation | 45 min | P1 | |
| T008 | P/L signal + tests | 45 min | P1 | |
| T009 | Reserve Risk module | 30 min | P1 | |
| T010 | HODL Bank calculation | 1.5h | P1 | [E] |
| T011 | Reserve Risk + tests | 1h | P1 | |
| T012 | Sell-side module | 30 min | P1 | |
| T013 | Realized Profit calc | 1h | P1 | |
| T014 | Sell-side + tests | 1h | P1 | |
| T015 | Coindays module | 30 min | P2 | |
| T016 | CDD calculation | 45 min | P2 | |
| T017 | VDD + averages | 1h | P2 | |
| T018 | CDD/VDD signal + tests | 45 min | P2 | |
| T019 | Fusion integration | 1h | P1 | |
| T020 | Integration test + docs | 1h | P1 | |

**Total: 20 tasks, ~17 hours**
