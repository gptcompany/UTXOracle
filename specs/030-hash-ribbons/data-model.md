# Data Model: Mining Economics (Hash Ribbons + Mining Pulse)

**Date**: 2025-12-19 | **Spec**: spec-030

## Entities

### 1. MiningPulseZone (Enum)

Classification of network hashrate status based on block intervals.

```python
class MiningPulseZone(str, Enum):
    """Classification of mining network status."""
    FAST = "FAST"       # Avg interval < 540s (-10% from target)
    NORMAL = "NORMAL"   # Avg interval 540-660s (±10% from target)
    SLOW = "SLOW"       # Avg interval > 660s (+10% from target)
```

| Value | Condition | Interpretation |
|-------|-----------|----------------|
| FAST | interval < 540s | Hashrate increasing rapidly |
| NORMAL | 540s ≤ interval ≤ 660s | Stable mining |
| SLOW | interval > 660s | Hashrate dropping/difficulty spike |

### 2. HashRibbonsResult (Dataclass)

Hash ribbon signal from 30d/60d MA crossover analysis.

```python
@dataclass
class HashRibbonsResult:
    """Hash Ribbons miner stress indicator (spec-030).

    Detects miner capitulation/recovery via MA crossovers:
    - ribbon_signal=True: 30d MA < 60d MA (stress)
    - recovery_signal=True: Just crossed back up (bullish)

    Attributes:
        hashrate_current: Current network hashrate (EH/s)
        hashrate_ma_30d: 30-day moving average hashrate (EH/s)
        hashrate_ma_60d: 60-day moving average hashrate (EH/s)
        ribbon_signal: True if 30d < 60d (miner stress active)
        capitulation_days: Consecutive days in stress state
        recovery_signal: True if just crossed back up
        data_source: "api" or "difficulty_estimated"
        timestamp: Calculation timestamp
    """
    hashrate_current: float  # EH/s
    hashrate_ma_30d: float   # EH/s
    hashrate_ma_60d: float   # EH/s
    ribbon_signal: bool
    capitulation_days: int
    recovery_signal: bool
    data_source: str  # "api" | "difficulty_estimated"
    timestamp: datetime = field(default_factory=datetime.utcnow)
```

**Validation Rules**:
- `hashrate_current` >= 0
- `hashrate_ma_30d` >= 0
- `hashrate_ma_60d` >= 0
- `capitulation_days` >= 0
- `data_source` in ("api", "difficulty_estimated")

**Field Units**:
- All hashrate values in EH/s (exahashes/second)
- Conversion: `hashrate_eh = raw_hashrate / 1e18`

### 3. MiningPulseResult (Dataclass)

Real-time block interval analysis for hashrate change detection.

```python
@dataclass
class MiningPulseResult:
    """Mining Pulse real-time hashrate indicator (spec-030).

    Analyzes block intervals to detect hashrate changes before
    difficulty adjusts. Works RPC-only, no external dependencies.

    Attributes:
        avg_block_interval: Average interval (seconds)
        interval_deviation_pct: Deviation from 600s target (%)
        blocks_fast: Blocks < 600s in window
        blocks_slow: Blocks >= 600s in window
        implied_hashrate_change: Inferred % hashrate delta
        pulse_zone: FAST | NORMAL | SLOW classification
        window_blocks: Number of blocks analyzed
        tip_height: Current block height
        timestamp: Calculation timestamp
    """
    avg_block_interval: float     # seconds
    interval_deviation_pct: float # percentage
    blocks_fast: int
    blocks_slow: int
    implied_hashrate_change: float  # percentage
    pulse_zone: MiningPulseZone
    window_blocks: int
    tip_height: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
```

**Validation Rules**:
- `avg_block_interval` > 0 (must have at least one interval)
- `interval_deviation_pct` in [-50, +100] (realistic range)
- `blocks_fast` + `blocks_slow` == `window_blocks` - 1
- `window_blocks` >= 2 (need at least 2 blocks for 1 interval)
- `tip_height` > 0

**Derived Fields**:
```python
interval_deviation_pct = (avg_block_interval - 600) / 600 * 100
implied_hashrate_change = -interval_deviation_pct  # inverse relationship
```

### 4. MiningEconomicsResult (Dataclass)

Combined view of Hash Ribbons + Mining Pulse.

```python
@dataclass
class MiningEconomicsResult:
    """Combined mining economics view (spec-030).

    Attributes:
        hash_ribbons: Hash Ribbons analysis (may be None if API unavailable)
        mining_pulse: Mining Pulse analysis (always available via RPC)
        combined_signal: Aggregated interpretation
        timestamp: Calculation timestamp
    """
    hash_ribbons: Optional[HashRibbonsResult]
    mining_pulse: MiningPulseResult
    combined_signal: str  # "miner_stress" | "recovery" | "healthy" | "unknown"
    timestamp: datetime = field(default_factory=datetime.utcnow)
```

**Combined Signal Logic**:
```python
def derive_combined_signal(
    ribbons: Optional[HashRibbonsResult],
    pulse: MiningPulseResult
) -> str:
    if ribbons and ribbons.recovery_signal:
        return "recovery"
    if ribbons and ribbons.ribbon_signal and ribbons.capitulation_days >= 7:
        return "miner_stress"
    if pulse.pulse_zone == MiningPulseZone.SLOW:
        return "miner_stress"
    if pulse.pulse_zone == MiningPulseZone.FAST:
        return "healthy"
    if ribbons is None:
        return "unknown"  # Can't determine without ribbon data
    return "healthy"
```

## State Transitions

### Hash Ribbons State Machine

```
                 ┌──────────────────┐
                 │                  │
                 v                  │
┌─────────┐   cross up        ┌────┴────┐
│ HEALTHY │ ◄───────────────  │ STRESS  │
└────┬────┘                   └────┬────┘
     │                             │
     │ cross down                  │ N days
     │ (30d < 60d)                 │
     v                             v
┌─────────────┐              ┌───────────────┐
│ EARLY_STRESS│  ───────────>│ CAPITULATION  │
│ (< 7 days)  │   >= 7 days  │ (confirmed)   │
└─────────────┘              └───────────────┘
```

### Mining Pulse Zones

```
interval < 540s     540s <= interval <= 660s     interval > 660s
      │                       │                        │
      v                       v                        v
  ┌──────┐              ┌────────┐               ┌──────┐
  │ FAST │              │ NORMAL │               │ SLOW │
  └──────┘              └────────┘               └──────┘
```

## Relationships

```
MiningEconomicsResult 1──────1 MiningPulseResult
         │
         └──0..1 HashRibbonsResult (optional, external API)
```

## JSON Serialization

### HashRibbonsResult.to_dict()
```json
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

### MiningPulseResult.to_dict()
```json
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

### MiningEconomicsResult.to_dict()
```json
{
  "hash_ribbons": { ... },
  "mining_pulse": { ... },
  "combined_signal": "healthy",
  "timestamp": "2025-12-19T12:00:00Z"
}
```

## Integration with Existing Models

Add to `scripts/models/metrics_models.py`:

```python
# =============================================================================
# Spec-030: Mining Economics (Hash Ribbons + Mining Pulse)
# =============================================================================

class MiningPulseZone(str, Enum):
    ...

@dataclass
class HashRibbonsResult:
    ...

@dataclass
class MiningPulseResult:
    ...

@dataclass
class MiningEconomicsResult:
    ...
```

Pattern follows existing metrics: `BinaryCDDResult`, `ExchangeNetflowResult`, `PLRatioResult`.
