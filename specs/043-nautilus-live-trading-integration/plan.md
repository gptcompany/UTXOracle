# spec-043: Implementation Plan

## Execution Order

```
Phase 1: Contract Definition
├── freeze polling-only first slice on GET /api/v1/live/snapshot
├── choose the minimal tradable field set
├── define field ownership: live API-produced vs adapter-derived
├── decide whether missing admitted fields require live contract changes
├── define freshness, monotonicity, confidence, and anomaly gates
├── define accepted source health combinations
└── define state machine: OK, LIQUIDATE_ONLY, HALT

Phase 2: RED Safety Tests
├── add failing tests for contract normalization and field ownership rules
├── add failing tests for freshness, health, anomaly, and monotonicity gates
└── add failing tests for kill-switch, recovery, and fail-closed behavior

Phase 3: Adapter
├── build Nautilus integration module
├── implement polling/replay behavior
├── implement required live-contract extensions or adapter-side derivations
├── add monotonic sequence tracking
└── add structured accept/reject logging

Phase 4: Safety Harness
├── add paper trading mode
├── add shadow/live-read mode
├── add circuit breaker and fail-closed semantics
└── add operator kill-switch and recovery policy

Phase 5: Rollout and Validation
├── replay recent history
├── validate adapter behavior against known degraded cases
└── document live enablement steps
```

## Operating Principle

The adapter must fail closed.

If freshness, health, or anomaly rules are not satisfied, no tradable snapshot is emitted to Nautilus.

The first slice remains contract-first. Do not build a Nautilus-specific transport or direct QuestDB/Parquet consumer until the tradable field whitelist and gate semantics are frozen.

Execution MUST follow RED -> GREEN -> REFACTOR for contract normalization and all trading-safety gates.

## Recommended Minimal Field Set

Start with:

- `timestamp`
- `block_height`
- `utxoracle_price`
- `mempool_exchange_price`
- `comparison.utxo_vs_mempool_bps`
- `source_spread_bps`
- `utxoracle_confidence`
- required source health fields

First-slice freeze:

- `sequence_id` is deferred as an upstream prerequisite before paper/live rollout
- `source_spread_bps` is adapter-derived as `abs(comparison.utxo_vs_mempool_bps)`
- required healthy sources are `electrs`, `utxoracle`, and `mempool_api`
- Hyperliquid and BRK fields are not in the first tradable whitelist

Everything else should be added only after validation.

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| contract and safety rules | 0.5 day | mostly design decisions |
| Nautilus adapter implementation | 1-2 days | depends on chosen mode |
| paper/replay harness | 1 day | high value before live rollout |
| kill-switch and recovery semantics | 0.5 day | required for safe rollout |
| rollout docs and tests | 0.5-1 day | must be explicit and operator-friendly |
| **Total** | **3.5-5 days** | lower if polling-only MVP is accepted |
