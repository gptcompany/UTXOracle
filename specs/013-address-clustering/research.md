# Research: Address Clustering & CoinJoin Detection

**Feature**: spec-013 | **Date**: 2025-12-04 | **Status**: Complete

## Research Topics

### 1. Clustering Heuristics

**Decision**: Multi-Input Heuristic (MIH) with Union-Find

**Rationale**:
- MIH: Inputs in same transaction → same entity (only owner can sign)
- Union-Find: O(α(n)) amortized operations, path compression
- Highly reliable (>95% accuracy per academic literature)

**Reference**: Meiklejohn et al. (2013) "A Fistful of Bitcoins"

### 2. CoinJoin Detection

**Decision**: Multi-heuristic approach with confidence scoring

**Patterns**:
| Protocol | Detection |
|----------|-----------|
| Wasabi | 100+ outputs, coordinator pattern |
| Whirlpool | Fixed denominations (0.001, 0.01, 0.05, 0.5 BTC) |
| JoinMarket | Multiple equal outputs + maker/taker pattern |
| Generic | >3 equal outputs + >5 inputs |

### 3. Change Detection

**Decision**: Heuristic-based (odd amounts, value proportion)

**Rules**:
1. Odd amount output (many decimals) → likely change
2. Output < 10% of total → likely change
3. Address matches input pattern → likely change

## Conclusions

1. **Union-Find** for efficient incremental clustering
2. **Multi-heuristic** CoinJoin detection with confidence
3. **Conservative** change detection (avoid false positives)

**Ready for Phase 1 design.**
