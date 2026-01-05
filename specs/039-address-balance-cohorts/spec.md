# spec-039: Address Balance Cohorts Analysis

## Overview

Calculate cost basis, MVRV, and supply metrics segmented by address balance size
(whale vs retail cohorts). Extends spec-023's time-based cohorts with balance-based
segmentation for deeper market structure analysis.

## Problem Statement

Current metrics (STH/LTH from spec-023, wallet waves from spec-025) segment by:
- Time (age of UTXOs)
- Balance bands (supply distribution)

Missing: **Cost basis by balance cohort**. Who has the better entry - whales or retail?
This reveals accumulation/distribution patterns and conviction levels.

## Cohort Definitions

Using simplified 3-tier structure (aligned with spec-025 but consolidated):

| Cohort | Balance Range | Description | Bands Covered |
|--------|---------------|-------------|---------------|
| RETAIL | < 1 BTC | Small holders | SHRIMP |
| MID_TIER | 1-100 BTC | Affluent individuals | CRAB + FISH |
| WHALE | >= 100 BTC | Institutions/Funds | SHARK + WHALE + HUMPBACK |

**Rationale**: 100 BTC threshold aligns with whale detection (spec-004, spec-005).

## Metrics

### Per-Cohort Metrics

| Metric | Formula | Description |
|--------|---------|-------------|
| `{cohort}_cost_basis` | SUM(creation_price * btc) / SUM(btc) | Weighted avg acquisition price |
| `{cohort}_supply_btc` | SUM(btc_value) WHERE balance in cohort | Total BTC held |
| `{cohort}_supply_pct` | cohort_supply / total_supply * 100 | % of circulating supply |
| `{cohort}_mvrv` | current_price / cost_basis | Market value to realized value |
| `{cohort}_address_count` | COUNT(DISTINCT address) | Number of addresses |

### Cross-Cohort Analysis

| Metric | Formula | Signal |
|--------|---------|--------|
| `whale_retail_spread` | whale_cost_basis - retail_cost_basis | Positive = whales bought higher |
| `whale_retail_mvrv_ratio` | whale_mvrv / retail_mvrv | < 1 = whales more profitable |
| `accumulation_signal` | -1 to +1 based on supply flow | Who's accumulating? |

### Signal Interpretation

**Whale vs Retail Cost Basis Spread:**
- Spread > 0: Whales bought at higher prices (retail has better basis)
- Spread < 0: Whales bought at lower prices (whales have conviction)
- Spread narrowing during dip: Whales accumulating

**Accumulation Signal:**
- +1.0: Strong whale accumulation (whale supply % increasing during price decline)
- -1.0: Strong whale distribution (whale supply % decreasing during price rise)
- 0.0: Neutral (balanced flows or sideways market)

## Technical Design

### Data Source

Uses `utxo_lifecycle_full` VIEW (existing from spec-017):
- `address`: Decoded address (may be NULL for OP_RETURN)
- `btc_value`: UTXO value in BTC
- `creation_price_usd`: Acquisition price
- `is_spent`: FALSE for unspent UTXOs

### Core Query

```sql
WITH address_balances AS (
    SELECT
        address,
        SUM(btc_value) AS balance,
        SUM(creation_price_usd * btc_value) AS weighted_cost_numerator,
        SUM(btc_value) AS weighted_cost_denominator
    FROM utxo_lifecycle_full
    WHERE is_spent = FALSE
      AND address IS NOT NULL
      AND creation_price_usd IS NOT NULL
      AND btc_value > 0
    GROUP BY address
),
cohort_classified AS (
    SELECT
        address,
        balance,
        weighted_cost_numerator,
        weighted_cost_denominator,
        CASE
            WHEN balance < 1 THEN 'retail'
            WHEN balance < 100 THEN 'mid_tier'
            ELSE 'whale'
        END AS cohort
    FROM address_balances
)
SELECT
    cohort,
    SUM(weighted_cost_numerator) / NULLIF(SUM(weighted_cost_denominator), 0) AS cost_basis,
    SUM(balance) AS supply_btc,
    COUNT(DISTINCT address) AS address_count
FROM cohort_classified
GROUP BY cohort;
```

### Output Structure

```python
@dataclass
class CohortMetrics:
    """Metrics for a single address cohort."""
    cohort: str                 # "retail", "mid_tier", "whale"
    cost_basis: float           # Weighted avg acquisition price
    supply_btc: float           # Total BTC in cohort
    supply_pct: float           # % of total supply
    mvrv: float                 # Price / Cost Basis
    address_count: int          # Number of addresses


@dataclass
class AddressCohortsResult:
    """Complete address cohorts analysis result."""
    timestamp: datetime
    block_height: int
    current_price_usd: float

    # Per-cohort metrics
    retail: CohortMetrics
    mid_tier: CohortMetrics
    whale: CohortMetrics

    # Cross-cohort analysis
    whale_retail_spread: float       # whale_cb - retail_cb
    whale_retail_mvrv_ratio: float   # whale_mvrv / retail_mvrv

    # Totals
    total_supply_btc: float
    total_addresses: int
```

## API Endpoint

```
GET /api/metrics/address-cohorts?current_price=98500

Response:
{
    "timestamp": "2025-01-05T12:00:00Z",
    "block_height": 878000,
    "current_price_usd": 98500.00,
    "cohorts": {
        "retail": {
            "cost_basis": 42500.00,
            "supply_btc": 2850000,
            "supply_pct": 14.5,
            "mvrv": 2.32,
            "address_count": 48500000
        },
        "mid_tier": {...},
        "whale": {...}
    },
    "analysis": {
        "whale_retail_spread": -7500.00,
        "whale_retail_mvrv_ratio": 1.21
    }
}
```

## Dependencies

- **spec-017**: utxo_lifecycle_full VIEW (data source)
- **spec-023**: CostBasisResult pattern (code reuse)
- **spec-025**: WalletBand classification (consistency)

## Success Criteria

1. Cohort classification covers 99%+ of addressable supply
2. Cost basis calculation matches spec-023 methodology
3. Query execution < 10 seconds for full UTXO set
4. Test coverage >= 85%

## Evidence Grade: B

Similar to CheckOnChain's "Entity-Adjusted" metrics but simplified.

## Estimated Effort: 5-7 hours
