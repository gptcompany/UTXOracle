# Implementation Plan: Address Clustering & CoinJoin Detection

**Branch**: `013-address-clustering` | **Date**: 2025-12-04 | **Spec**: [spec.md](./spec.md)

## Summary

Implement address clustering heuristics (Multi-Input, Change Detection) and CoinJoin detection to improve whale tracking accuracy by identifying entity relationships and filtering privacy transactions.

**Primary Value**: +10-15% whale detection precision improvement

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: None (pure Python)
**Storage**: DuckDB (address_clusters, coinjoin_cache tables)
**Testing**: pytest
**Performance Goals**: <10s for 10,000 transactions
**Constraints**: Pure Python, O(α(n)) for Union-Find operations

## Constitution Check

All principles ✅ PASS - Pure Python, local processing, TDD approach.

## Project Structure

```
scripts/
├── clustering/
│   ├── __init__.py
│   ├── union_find.py        # Disjoint set data structure
│   ├── address_clustering.py # Multi-input heuristic
│   ├── coinjoin_detector.py  # CoinJoin pattern matching
│   └── change_detector.py    # Change output heuristics

tests/
├── test_clustering.py
└── integration/
    └── test_clustering_whale.py
```

## Phase 0: Research

See [research.md](./research.md)

## Phase 1: Design

See [data-model.md](./data-model.md), [quickstart.md](./quickstart.md)
