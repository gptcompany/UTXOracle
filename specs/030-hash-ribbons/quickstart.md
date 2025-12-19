# Quickstart: Mining Economics (Hash Ribbons + Mining Pulse)

**Spec**: spec-030 | **Date**: 2025-12-19

## Overview

Mining Economics provides two complementary miner stress indicators:
1. **Hash Ribbons**: 30d/60d MA crossover (external API)
2. **Mining Pulse**: Block interval analysis (RPC-only)

## Prerequisites

- Bitcoin Core node (synced, RPC enabled)
- Self-hosted mempool.space (for Hash Ribbons, optional)
- Python 3.11+

## Quick Test

### Mining Pulse (RPC-only, always works)

```bash
# Via API
curl http://localhost:8000/api/metrics/mining-pulse

# Expected response
{
  "avg_block_interval": 585.3,
  "interval_deviation_pct": -2.45,
  "blocks_fast": 82,
  "blocks_slow": 61,
  "implied_hashrate_change": 2.45,
  "pulse_zone": "FAST",
  "window_blocks": 144,
  "tip_height": 875000,
  "timestamp": "2025-12-19T12:00:00Z"
}
```

### Hash Ribbons (requires mempool.space)

```bash
# Via API
curl http://localhost:8000/api/metrics/hash-ribbons

# Expected response
{
  "hashrate_current": 1180.5,
  "hashrate_ma_30d": 1150.2,
  "hashrate_ma_60d": 1120.8,
  "ribbon_signal": false,
  "capitulation_days": 0,
  "recovery_signal": false,
  "data_source": "api",
  "timestamp": "2025-12-19T12:00:00Z"
}
```

### Combined View

```bash
curl http://localhost:8000/api/metrics/mining-economics

# Returns both + combined_signal
{
  "hash_ribbons": { ... },
  "mining_pulse": { ... },
  "combined_signal": "healthy"
}
```

## Python Usage

```python
from scripts.metrics.mining_economics import (
    calculate_hash_ribbons,
    calculate_mining_pulse,
    calculate_mining_economics
)
from scripts.models.metrics_models import (
    HashRibbonsResult,
    MiningPulseResult,
    MiningEconomicsResult,
    MiningPulseZone
)

# Mining Pulse (RPC-only)
pulse = calculate_mining_pulse(rpc_client, window_blocks=144)
if pulse.pulse_zone == MiningPulseZone.SLOW:
    print("Warning: Hashrate may be dropping")

# Hash Ribbons (external API)
ribbons = calculate_hash_ribbons()
if ribbons.ribbon_signal and ribbons.capitulation_days >= 7:
    print("Miner capitulation detected!")

# Combined analysis
economics = calculate_mining_economics(rpc_client)
if economics.combined_signal == "miner_stress":
    print("Alert: Miner stress detected")
elif economics.combined_signal == "recovery":
    print("Bullish: Miners recovering")
```

## Signal Interpretation

### Hash Ribbons

| Signal | Meaning |
|--------|---------|
| `ribbon_signal=False` | Normal mining, no stress |
| `ribbon_signal=True, days<7` | Early stress, watch |
| `ribbon_signal=True, days>=7` | Confirmed capitulation |
| `recovery_signal=True` | Miners recovering (bullish) |

### Mining Pulse Zones

| Zone | Block Interval | Meaning |
|------|----------------|---------|
| FAST | < 540s | Hashrate increasing |
| NORMAL | 540-660s | Stable mining |
| SLOW | > 660s | Hashrate dropping |

### Combined Signal

| Signal | Condition |
|--------|-----------|
| `healthy` | No stress indicators |
| `miner_stress` | Ribbons active 7+ days OR pulse SLOW |
| `recovery` | Ribbons just crossed up |
| `unknown` | No ribbon data available |

## Custom Window

```bash
# Mining Pulse with 2016-block window (difficulty period)
curl "http://localhost:8000/api/metrics/mining-pulse?window=2016"

# Historical data
curl "http://localhost:8000/api/metrics/mining-economics/history?days=90"
```

## Error Handling

```python
try:
    ribbons = calculate_hash_ribbons()
except ExternalAPIError:
    # Hash ribbons unavailable, use pulse only
    pulse = calculate_mining_pulse(rpc_client)
    print(f"Pulse zone: {pulse.pulse_zone}")
```

## Evidence Grade

Per `contadino_galattico.md`:
- **Evidence Grade**: B→C (declining value)
- **Reason**: Institutional mining reduces predictive power
- **Still useful for**: Historical analysis, extreme events, real-time monitoring

## Files

| File | Purpose |
|------|---------|
| `scripts/metrics/mining_economics.py` | Calculator implementation |
| `scripts/data/hashrate_fetcher.py` | External API client |
| `scripts/models/metrics_models.py` | Data models |
| `tests/test_mining_economics.py` | TDD tests |
