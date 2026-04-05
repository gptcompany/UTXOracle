# spec-052: Implementation Plan

## Execution Order

```
Phase 1: Contract Freeze
├── freeze exactly four bundle families
├── freeze exactly one signal family
├── freeze top-level metadata and failure vocabulary
└── freeze which existing routes stay outside v1 by design

Phase 2: Storage and Monotonicity
├── decide bundle tables or serving artifacts
├── decide signal table or serving artifact
├── define monotonic `sequence_id` generation
└── freeze replay ordering and history semantics

Phase 3: Cost Basis Promotion
├── freeze admitted cost-basis field subset
├── publish reproducibility and consumer-use note
├── choose QuestDB materialization vs explicit DuckDB caveat path
└── harden degraded and boundary behavior

Phase 4: BRK Macro Bundle
├── freeze curated `BRK` subset for `btc_macro.v1`
├── verify `cost_basis` overlap vs exact equivalence
├── add partial-degradation semantics
└── prove the bundle is bounded and not a BRK mirror

Phase 5: Bundle Serving
├── implement `latest` routes
├── implement `history` routes
├── preserve per-source timestamps and freshness semantics
└── verify replay ordering and stable payloads

Phase 6: Signal Snapshot Layer
├── freeze deterministic component formulas
├── write `btc_signal_snapshot.v1` from admitted bundle inputs only
├── expose `latest/history`
└── verify degraded bundle inputs degrade signal status deterministically

Phase 7: Governance and Consumer Alignment
├── update contract registry
├── update provenance/source-of-truth artifacts
├── update production consumer profile and scope lock
└── publish consumer-facing service guidance
```

## Core Principle

The goal is not to expose more routes. The goal is to convert the existing feature surface into a small, versioned, replayable consumer contract that can be ingested safely by an automated downstream.

## Decision Gates

### Gate A: Bundle Admission

Before admitting any field into a bundle, confirm:

1. the field already has a stable producer
2. the field has clear freshness semantics
3. the field belongs in the target bundle family
4. the field is not only present because it is easy to fetch

### Gate B: Cost Basis Promotion

Before promoting `cost_basis`, confirm:

1. the admitted subset is narrow and frozen
2. reproducibility evidence is written
3. degraded and empty behavior are explicit
4. the serving path is operationally plausible

### Gate C: Macro Ownership

Before expanding `btc_macro.v1`, confirm:

1. the metric is `BRK`-first in the manifest or explicitly approved otherwise
2. the metric belongs in the first admitted macro slice
3. the consumer value is real
4. the bundle remains curated rather than open-ended

### Gate D: Signal Discipline

Before admitting any signal field, confirm:

1. it is derived only from admitted bundle inputs
2. the formula is deterministic
3. missing inputs degrade the output explicitly
4. it is not strategy or execution logic disguised as service output

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| contract freeze and storage design | 1-2 days | high leverage; prevents later drift |
| cost-basis promotion | 2-4 days | depends on materialization choice |
| macro bundle and BRK normalization | 1-3 days | bounded if subset stays narrow |
| bundle serving and history | 2-4 days | mostly API and materialization plumbing |
| signal snapshot layer | 1-3 days | depends on formula simplicity |
| governance/docs alignment | 0.5-1.5 days | should be last |
| **Total** | **7.5-17.5 days** | best done in narrow reviewable commits |
