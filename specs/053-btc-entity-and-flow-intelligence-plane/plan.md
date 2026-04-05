# spec-053: Implementation Plan

## Execution Order

```
Phase 1: Vocabulary and Compatibility Freeze
├── freeze identity concepts: address, cluster, entity, label
├── freeze canonical `entity_id` direction
├── freeze whale compatibility guarantees
└── freeze the explicit namespace for deeper APIs

Phase 2: Registry and Provenance Design
├── design `entity_registry`
├── design cluster-to-entity mapping
├── design label and provenance artifacts
└── freeze status and review vocabularies

Phase 3: Confidence and Reconciliation
├── separate clustering, mapping, and label confidence
├── define evidence upgrade and downgrade rules
├── define disagreement handling across evidence sources
└── preserve ambiguity rather than forcing false certainty

Phase 4: Flow-of-Funds Model
├── design event-level movement artifacts
├── design daily aggregate flow artifacts
├── freeze movement classification vocabulary
└── define internal reshuffle vs external flow rules

Phase 5: Materialization and Serving
├── decide which artifacts stay local-authoritative
├── decide which artifacts are served from QuestDB
├── define freshness and degraded behavior
└── define writer/backfill responsibilities

Phase 6: API Surface and Whale Integration
├── implement entity metadata APIs
├── implement entity history and flow APIs
├── preserve current whale enrichment contract
└── add richer entity references without breaking base whale events

Phase 7: Governance and Future Projection
├── update registry/provenance docs
├── update BRK adoption checklist if needed
├── define whether projection into `btc_entity.v1` is justified
└── define whether `btc_flow.v2` should consume entity flow context
```

## Core Principle

This spec is about turning heuristics into a governed intelligence plane. More labels are not enough; the output must carry identity discipline, provenance, confidence, and history.

## Decision Gates

### Gate A: Identity Model

Before introducing a canonical `entity_id`, confirm:

1. it is distinct from raw `cluster_id`
2. compatibility with current whale enrichment is explicit
3. future registry stability is more important than cosmetic naming

### Gate B: Provenance

Before exposing any label through a deeper entity API, confirm:

1. the source is recorded
2. review status is explicit
3. method version is recorded
4. omission remains allowed when evidence is weak

### Gate C: Movement Classification

Before emitting flow-of-funds classifications, confirm:

1. internal reshuffles are not silently treated as external flow
2. ambiguous evidence stays ambiguous
3. event-level and aggregate-level semantics are consistent

### Gate D: Serving Promotion

Before materializing any entity or flow artifact into QuestDB, confirm:

1. the local authoritative source is clear
2. freshness targets are explicit
3. degraded behavior is defined
4. the API consumer value justifies serving-grade exposure

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| vocabulary and registry design | 1-2 days | mostly modeling and governance |
| provenance and confidence model | 1-2 days | requires explicit policy choices |
| movement-plane design | 2-4 days | highest semantic risk |
| materialization and serving path | 2-4 days | depends on desired first slice |
| API surface and whale integration | 1-3 days | compatibility matters more than volume |
| governance/docs alignment | 0.5-1.5 days | should close the loop |
| **Total** | **7.5-16.5 days** | best phased after `spec-052` stabilizes |
