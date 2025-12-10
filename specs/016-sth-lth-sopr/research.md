# Research: STH/LTH SOPR Implementation

**Spec**: spec-016
**Date**: 2025-12-06

---

## R1: Historical Price Lookup Strategy

### Question
How to efficiently retrieve creation prices for spent outputs?

### Research Findings

**Option 1: Local UTXOracle prices table**
- UTXOracle stores prices from 672 days of historical analysis
- Query: `SELECT price_usd FROM utxoracle_prices WHERE block_height = ?`
- Performance: O(1) with index, <1ms per lookup
- Coverage: Dec 2023 → Present

**Option 2: External API (mempool.space)**
- Endpoint: `GET /api/v1/historical-price`
- Latency: 50-200ms per request
- Rate limits apply
- Privacy concern: leaks query patterns

**Option 3: Re-calculate on demand**
- Run UTXOracle algorithm for historical block
- Time: 2-5 seconds per block
- Too slow for real-time SOPR

### Decision
**Option 1: Local UTXOracle prices table** with Option 2 as fallback.

### Rationale
- Privacy-first (Principle V)
- Performance (<1ms vs 50-200ms)
- Already have 672 days of data
- Fallback ensures coverage for gaps

---

## R2: UTXO Age Calculation

### Question
How to determine UTXO age without full UTXO set tracking?

### Research Findings

**Option 1: Extract from prevout reference**
- Bitcoin Core RPC: `getrawtransaction` returns `vin[].txid`, `vin[].vout`
- Query original transaction for `blockhash` → block height
- 2 RPC calls per spent output

**Option 2: Full UTXO set (spec-017)**
- Track all UTXOs with creation block
- 4-6 weeks implementation
- ~5GB storage for 6 months

**Option 3: Heuristic estimation**
- Estimate based on transaction patterns
- Lower accuracy (~80%)
- Fast but unreliable

### Decision
**Option 1: Extract from prevout reference** with caching.

### Rationale
- Accurate (100% correct age)
- MVP-compatible (no spec-017 dependency)
- Cache mitigates RPC overhead
- Prepares data model for spec-017

### Implementation Notes
```python
def get_utxo_creation_block(txid: str, vout: int, rpc: BitcoinRPC) -> int:
    """Get the block height where this UTXO was created."""
    # Check cache first
    cache_key = f"{txid}:{vout}"
    if cache_key in creation_block_cache:
        return creation_block_cache[cache_key]

    # Query original transaction
    tx = rpc.getrawtransaction(txid, verbose=True)
    block_hash = tx.get("blockhash")

    if not block_hash:
        # Unconfirmed or not found
        return None

    block = rpc.getblock(block_hash)
    creation_block = block["height"]

    # Cache result
    creation_block_cache[cache_key] = creation_block
    return creation_block
```

---

## R3: STH/LTH Threshold

### Question
What threshold separates short-term from long-term holders?

### Research Findings

**Industry Standards**:
| Source | STH Threshold | Notes |
|--------|---------------|-------|
| Glassnode | 155 days | Standard for all cohort metrics |
| CryptoQuant | 155 days | Follows Glassnode |
| On-Chain College | 155 days | Educational standard |
| Academic (Omole 2024) | 155 days | Used in 82.44% accuracy study |

**Rationale for 155 days**:
- ~5 months, aligns with market cycle phases
- Captures speculative vs conviction-based behavior
- Empirically validated in ML studies

### Decision
**155 days** (configurable via `SOPR_STH_THRESHOLD_DAYS`)

### Configuration
```bash
# .env
SOPR_STH_THRESHOLD_DAYS=155
```

---

## R4: Signal Detection Patterns

### Question
Which SOPR patterns are predictive?

### Research Findings

**Pattern 1: STH Capitulation (Bullish)**
- Condition: `sth_sopr < 1.0` for 3+ consecutive days
- Meaning: Short-term holders selling at loss (panic)
- Historical accuracy: High for bottoms
- Contrarian signal: Buy

**Pattern 2: STH Break-Even Cross (Reversal)**
- Condition: `sth_sopr` crosses 1.0 from below
- Meaning: STH no longer underwater
- Historical accuracy: Medium, confirms trend change
- Signal: Confirm direction

**Pattern 3: LTH Distribution (Bearish)**
- Condition: `lth_sopr > 3.0`
- Meaning: Long-term holders taking significant profit
- Historical accuracy: High for cycle tops
- Signal: Sell / reduce exposure

### Decision
Implement all three patterns with configurable thresholds.

---

## R5: SOPR Calculation Formula

### Question
What is the exact formula for SOPR calculation?

### Research Findings

**Individual Output SOPR**:
```
output_sopr = spend_price_usd / creation_price_usd
```

**Block SOPR (Weighted Average)**:
```
block_sopr = Σ(output_sopr × btc_value) / Σ(btc_value)
```

**STH/LTH Split**:
```
sth_sopr = weighted_avg(outputs where age < 155 days)
lth_sopr = weighted_avg(outputs where age >= 155 days)
```

### Edge Cases
- `creation_price = 0`: Skip output (invalid)
- `spend_price = 0`: Skip output (shouldn't happen)
- `age = 0`: Include in STH (same-day spend)

---

## Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Price lookup | Local table + fallback | Privacy, performance |
| Age calculation | Prevout + cache | Accuracy, MVP-compatible |
| STH threshold | 155 days | Industry standard |
| Patterns | 3 patterns | Empirically validated |
