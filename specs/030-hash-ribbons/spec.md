# spec-030: Mining Economics (Hash Ribbons + Mining Pulse)

## Overview
Mining stress indicators combining hashrate moving averages (Hash Ribbons) and block interval analysis (Mining Pulse).
Tracks miner health, capitulation events, and real-time network hashrate changes.

**Evidence Grade**: B→C (contadino_galattico.md: "declining value" due to institutional mining)
**Priority**: Medium (useful for historical context, less predictive in institutional era)

---

## Part 1: Hash Ribbons

### Formula
```
Hash Ribbon Signal = MA_30d_hashrate < MA_60d_hashrate
Miner Capitulation = Hash Ribbon Signal sustained for N days
Recovery Signal = MA_30d crosses back above MA_60d
```

### Metrics
| Metric | Description |
|--------|-------------|
| `hashrate_current` | Current network hashrate (EH/s) |
| `hashrate_ma_30d` | 30-day moving average hashrate |
| `hashrate_ma_60d` | 60-day moving average hashrate |
| `ribbon_signal` | Boolean (True = 30d < 60d, miner stress) |
| `capitulation_days` | Days in continuous capitulation state |
| `recovery_signal` | Boolean (True = just crossed back up) |

### Signal Interpretation
| Signal | Duration | Interpretation |
|--------|----------|----------------|
| No Ribbon | - | Normal mining, no stress |
| Ribbon Active | < 7 days | Early miner stress, watch |
| Ribbon Active | 7-30 days | Confirmed capitulation |
| Ribbon Active | > 30 days | Extended stress, potential bottom |
| Recovery | - | Miners recovering, bullish signal |

---

## Part 2: Mining Pulse

### Formula
```
Block Interval = block_timestamp[n] - block_timestamp[n-1]
Expected Interval = 600 seconds (10 minutes)
Mining Pulse = (Actual Interval - Expected) / Expected * 100
```

### Metrics
| Metric | Description |
|--------|-------------|
| `avg_block_interval` | Average block interval (seconds) |
| `interval_deviation_pct` | Deviation from 600s target (%) |
| `blocks_fast` | Blocks found faster than 10 min (last 144) |
| `blocks_slow` | Blocks found slower than 10 min (last 144) |
| `implied_hashrate_change` | Inferred hashrate change from intervals |
| `pulse_zone` | Classification (FAST, NORMAL, SLOW) |

### Pulse Zones
| Zone | Avg Interval | Deviation | Interpretation |
|------|--------------|-----------|----------------|
| FAST | < 540s | < -10% | Hashrate increasing rapidly |
| NORMAL | 540-660s | -10% to +10% | Stable mining |
| SLOW | > 660s | > +10% | Hashrate dropping or difficulty spike |

### Signal Value
- **Real-time proxy**: Detects hashrate changes before difficulty adjusts
- **Miner migration**: Fast blocks after halving = efficient miners dominating
- **Network stress**: Slow blocks = potential miner shutdown event

---

## Implementation

### Data Sources
1. **Hash Ribbons**: External API (mempool.space) or difficulty-based calculation
2. **Mining Pulse**: Bitcoin Core RPC (block headers) - no external dependency

### External API Integration (Hash Ribbons)
```python
# mempool.space API
GET https://mempool.space/api/v1/mining/hashrate/3m
# Returns: [{"timestamp": 1234567890, "avgHashrate": 500000000000000000000}]
```

### Bitcoin Core RPC (Mining Pulse)
```python
# Get recent block timestamps
for height in range(tip - 144, tip + 1):
    block_hash = rpc.getblockhash(height)
    block = rpc.getblock(block_hash)
    timestamps.append(block['time'])
```

### Files
- `scripts/metrics/mining_economics.py` - Combined calculator
- `scripts/data/hashrate_fetcher.py` - External API client (Hash Ribbons)
- `tests/test_mining_economics.py` - TDD tests
- `scripts/models/metrics_models.py` - Add HashRibbonsResult, MiningPulseResult, MiningPulseZone enum

### API
- `GET /api/metrics/hash-ribbons` - Hash ribbon status
- `GET /api/metrics/mining-pulse` - Real-time block interval analysis
- `GET /api/metrics/mining-economics` - Combined view
- `GET /api/metrics/mining-economics/history?days=90`

### Query (Mining Pulse from blocks)
```sql
WITH recent_blocks AS (
    SELECT
        block_height,
        timestamp,
        LAG(timestamp) OVER (ORDER BY block_height) AS prev_timestamp
    FROM blocks
    WHERE block_height > (SELECT MAX(block_height) - 144 FROM blocks)
)
SELECT
    AVG(timestamp - prev_timestamp) AS avg_interval,
    (AVG(timestamp - prev_timestamp) - 600.0) / 600.0 * 100 AS deviation_pct,
    COUNT(CASE WHEN timestamp - prev_timestamp < 600 THEN 1 END) AS blocks_fast,
    COUNT(CASE WHEN timestamp - prev_timestamp >= 600 THEN 1 END) AS blocks_slow
FROM recent_blocks
WHERE prev_timestamp IS NOT NULL;
```

### Query (Hash Ribbons from difficulty)
```sql
-- Approximate hashrate from difficulty
-- hashrate ≈ difficulty * 2^32 / 600
WITH difficulty_history AS (
    SELECT
        block_height,
        timestamp,
        difficulty,
        (difficulty * 4294967296.0 / 600) / 1e18 AS hashrate_eh
    FROM blocks
    WHERE timestamp >= NOW() - INTERVAL 90 DAY
)
SELECT
    AVG(CASE WHEN timestamp >= NOW() - INTERVAL 30 DAY THEN hashrate_eh END) AS ma_30d,
    AVG(hashrate_eh) AS ma_60d
FROM difficulty_history;
```

## Dependencies
- Bitcoin Core RPC (block headers) - for Mining Pulse
- External hashrate API OR difficulty data - for Hash Ribbons

## Caveats
- **Institutional Mining**: Hash ribbons less predictive since 2020 due to:
  - Public mining companies with treasury reserves
  - Access to capital markets (debt financing)
  - Hedging strategies
- **Mining Pulse**: More responsive but noisy (variance in block times is natural)
- **Still useful for**: Historical analysis, extreme stress events, real-time monitoring

## Effort: 4-5 hours (medium complexity)
## ROI: Medium - historically significant, Mining Pulse adds real-time value
