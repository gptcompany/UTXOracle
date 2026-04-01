# spec-047: Whale Surface Unification & Entity Foundations

> **Status**: IMPLEMENTED
> **Priority**: HIGH
> **Effort**: Large
> **Created**: 2026-04-01
> **M4a Implemented**: 2026-04-01
> **M4b Implemented**: 2026-04-02

## Problem Statement

The repository currently exposes overlapping whale surfaces under `/api/whale`.

Current gaps:

1. real query endpoints and placeholder legacy endpoints coexist in the same namespace
2. historical whale intelligence and live whale monitoring are not presented as one canonical product surface
3. there is no entity or attribution foundation for future forensic expansion
4. consumers cannot tell which whale routes are canonical and which are vestigial

This spec unifies whale APIs into one supported surface and lays the minimum entity foundations needed for future cluster-aware features. Route canonicalization and the first entity foundation slice are now implemented.

## Goals

1. define one canonical whale API surface
2. remove or deprecate legacy placeholder whale routes
3. align historical query, summary, and transaction drill-down paths
4. introduce a minimal entity foundation model with provenance and confidence

## Non-Goals

- full institutional attribution
- complete forensic dashboard redesign
- cross-chain whale analytics

## Dependencies

- [specs/004-whale-flow-detection/spec.md](/media/sam/1TB/UTXOracle/specs/004-whale-flow-detection/spec.md)
- [specs/005-mempool-whale-realtime/spec.md](/media/sam/1TB/UTXOracle/specs/005-mempool-whale-realtime/spec.md)
- [specs/013-address-clustering/spec.md](/media/sam/1TB/UTXOracle/specs/013-address-clustering/spec.md)
- [specs/044-feature-service-contract-registry/spec.md](/media/sam/1TB/UTXOracle/specs/044-feature-service-contract-registry/spec.md)
- [specs/045-feature-dependency-provenance-manifest/spec.md](/media/sam/1TB/UTXOracle/specs/045-feature-dependency-provenance-manifest/spec.md)

## Design

### 1. Canonical Whale Surface

The canonical surface MUST start from the already implemented query endpoints:

- `/api/whale/transactions`
- `/api/whale/summary`
- `/api/whale/transaction/{txid}`

Legacy placeholder routes MUST be either:

- removed
- deprecated with explicit notices
- reimplemented on top of canonical data

Silent coexistence is not allowed.

### 2. Data Model Direction

The long-term canonical object is a `whale_event`.

Minimum fields:

- `event_id`
- `transaction_id`
- `flow_type`
- `btc_value`
- `urgency_score`
- `detection_timestamp`
- `source`
- `status`

Optional enrichment fields:

- `cluster_id`
- `entity_id`
- `entity_label`
- `label_source`
- `confidence`

### 3. Entity Foundations

This spec does not require full attribution, but it MUST define a foundation for future enrichment:

- stable `entity_id`
- provenance for any label
- confidence score for inferred attribution
- clear distinction between observed facts and inferred labels

### 4. Namespace Policy

The whale namespace MUST not mix:

- canonical supported routes
- placeholder routes
- legacy aliases

without explicit deprecation metadata.

### 5. Backward Compatibility

If legacy routes are kept temporarily, they MUST:

- return deprecation metadata
- point to the canonical route family
- avoid diverging payload semantics

## Functional Requirements

### FR1: Canonical Whale API

The repository MUST define one canonical whale route family.

### FR2: Legacy Resolution

Placeholder whale routes MUST be removed, deprecated, or reimplemented on canonical data.

### FR3: Canonical Event Shape

Whale surfaces MUST converge on one shared event schema.

### FR4: Entity Foundation Schema

The repository MUST define a minimal entity foundation schema even if enrichment remains optional in the first slice.

### FR5: Provenance and Confidence

Any entity label or attribution field MUST carry provenance and confidence metadata.

### FR6: Contract Alignment

The final whale surface MUST update spec-044 and spec-045 artifacts.

## Success Criteria

1. `/api/whale` no longer contains ambiguous placeholder/canonical overlap
2. consumers can identify one supported whale surface without reading code
3. future entity-aware work has a stable schema foundation
4. deprecation of legacy whale routes is explicit and operator-visible
