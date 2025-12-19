# Research: Mining Economics (Hash Ribbons + Mining Pulse)

**Date**: 2025-12-19 | **Spec**: spec-030

## Research Questions

### Q1: External API for Hash Ribbons

**Decision**: mempool.space `/api/v1/mining/hashrate/{timeframe}` API

**Rationale**:
- Self-hosted mempool.space instance already deployed (per CLAUDE.md)
- Returns daily hashrate snapshots with difficulty adjustments
- Response includes `hashrates[]` with `timestamp` and `avgHashrate` fields
- Supports 3m, 6m, 1y, 2y, 3y timeframes

**API Response Structure**:
```json
{
  "hashrates": [
    {"timestamp": 1702684800, "avgHashrate": 5.5e20}
  ],
  "difficulty": [
    {"time": 1702684800, "height": 820000, "difficulty": 7.2e13, "adjustment": 1.05}
  ],
  "currentHashrate": 1.18e21,
  "currentDifficulty": 1.1e14
}
```

**Alternatives Considered**:
- Blockchain.com API: Rate limited, requires API key
- Glassnode: Paid tier required for hashrate
- Calculate from difficulty: Less accurate (only updates every ~2016 blocks)

### Q2: Hashrate Caching Strategy

**Decision**: 5-minute TTL cache with memory-based storage

**Rationale**:
- Hashrate data updates daily, 5-min cache prevents API abuse
- Network hashrate changes slowly (hours to days for significant moves)
- Simple `functools.lru_cache` with TTL wrapper sufficient
- No need for Redis/external cache (KISS principle)

**Implementation**:
```python
from functools import lru_cache
from time import time

def ttl_cache(ttl_seconds=300):
    def decorator(func):
        @lru_cache(maxsize=1)
        def wrapper(*args, _ttl_hash=None, **kwargs):
            return func(*args, **kwargs)

        def cached_func(*args, **kwargs):
            return wrapper(*args, _ttl_hash=int(time() // ttl_seconds), **kwargs)
        return cached_func
    return decorator
```

**Alternatives Considered**:
- Per-request fetch: Too many API calls, potential rate limiting
- Redis cache: Over-engineering for single-value cache
- File-based cache: Adds I/O, unnecessary complexity

### Q3: Mining Pulse Data Source

**Decision**: Bitcoin Core RPC `getblock` for last 144 blocks

**Rationale**:
- 144 blocks = ~1 day window (10 min * 144 = 24h)
- Block timestamps available via RPC, no external dependency
- Aligns with Constitution Principle V (privacy-first, local processing)

**RPC Pattern**:
```python
tip_hash = rpc.getbestblockhash()
tip = rpc.getblock(tip_hash)
tip_height = tip['height']

for height in range(tip_height - 143, tip_height + 1):
    block_hash = rpc.getblockhash(height)
    block = rpc.getblock(block_hash)
    timestamps.append(block['time'])
```

**Alternatives Considered**:
- Batch RPC (`getblock` with height array): Not supported natively
- Store timestamps in local DB: Adds storage complexity, YAGNI

### Q4: Difficulty-Based Hashrate Fallback

**Decision**: Implement as optional fallback, not primary source

**Rationale**:
- Formula: `hashrate = difficulty * 2^32 / 600`
- Only updates every 2016 blocks (~2 weeks)
- Less granular than daily API data
- Useful for fully offline/privacy scenarios

**Formula**:
```python
def estimate_hashrate_from_difficulty(difficulty: float) -> float:
    """Estimate hashrate in H/s from difficulty."""
    return difficulty * (2**32) / 600
```

**Use Cases**:
- Hash Ribbons API unavailable (network issues)
- User opts out of external API calls
- Historical validation against API data

### Q5: Signal Persistence Requirements

**Decision**: Stateless calculation with optional capitulation_days tracking

**Rationale**:
- Hash Ribbons signal = simple MA crossover (no state needed per call)
- `capitulation_days` requires knowing when ribbon first activated
- Can derive from historical hashrate data in same API call

**Implementation**:
```python
def count_capitulation_days(hashrates: list[dict]) -> int:
    """Count consecutive days where 30d MA < 60d MA."""
    # Iterate from most recent, count streak
    pass
```

**Alternatives Considered**:
- Store signal state in DB: Over-engineering, YAGNI
- External state service: Adds dependency, unnecessary

## Technology Decisions

| Component | Choice | Token Savings |
|-----------|--------|---------------|
| HTTP Client | httpx (already in use) | N/A |
| Caching | functools TTL wrapper | No new deps |
| Models | dataclass (existing pattern) | 75% via skill |
| Tests | pytest (existing) | 83% via skill |

## Dependencies Review

| Dependency | Status | Notes |
|------------|--------|-------|
| httpx | Existing | Used by other data fetchers |
| dataclasses | Stdlib | No new dependency |
| Bitcoin Core RPC | Existing | bitcoin-rpc-connector skill |

## Open Questions Resolved

All NEEDS CLARIFICATION items resolved:
- ✅ External API: mempool.space hashrate endpoint
- ✅ Caching: 5-min TTL, memory-based
- ✅ RPC pattern: 144-block window for Mining Pulse
- ✅ Fallback: Difficulty-based estimation available
