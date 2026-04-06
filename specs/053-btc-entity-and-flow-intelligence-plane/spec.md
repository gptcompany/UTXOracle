# spec-053: BTC Entity and Flow Intelligence Plane

> **Status**: DRAFT
> **Priority**: HIGH
> **Effort**: Large
> **Created**: 2026-04-06

## Problem Statement

The repository already contains real blockchain heuristics and operational whale enrichment, but it does not yet provide a full BTC entity intelligence and flow-of-funds plane.

Current strengths already present:

1. address clustering exists with common-input ownership, change detection, CoinJoin filtering, and union-find clustering
2. cluster assignments are now synchronized into QuestDB
3. the canonical whale surface on `:8011` already exposes additive `whale_event.v1` entity fields
4. omission and ambiguity rules for entity enrichment are frozen and production-safe

Current gaps still blocking a true entity intelligence service:

1. there is no canonical entity registry with stable long-lived entity identifiers
2. current `entity_id` is only the provisional `cluster:{cluster_id}` pattern
3. there is no rigorous provenance model for labels
4. there is no decomposed confidence model for:
   - clustering confidence
   - entity mapping confidence
   - label confidence
5. there are no entity movement APIs
6. there is no historical flow-of-funds plane across clusters or labeled entities
7. there is no stable entity-facing bundle or query namespace
8. the current whale enrichment is best-effort and intentionally limited to event augmentation

This spec turns the existing clustering and whale foundations into a first-class BTC entity and flow intelligence plane.

## Goals

1. define a stable BTC entity identity model beyond raw cluster IDs
2. introduce provenance and confidence as first-class fields in entity resolution
3. build materialized historical flow-of-funds surfaces across clusters and entities
4. expose entity and flow APIs suitable for research first and later selective production promotion
5. preserve the current whale event enrichment contract while making the entity plane deeper and more rigorous

## Non-Goals

- claiming full institutional attribution accuracy
- building an AML or sanctions product
- supporting non-BTC chains
- replacing `BRK` as the macro feature engine
- mixing strategy logic into the entity intelligence plane
- forcing immediate admission of the entity plane into the same production contract slice as core live features

## Dependencies

- [specs/013-address-clustering/spec.md](/media/sam/1TB/UTXOracle/specs/013-address-clustering/spec.md)
- [specs/047-whale-entity-surface-unification/spec.md](/media/sam/1TB/UTXOracle/specs/047-whale-entity-surface-unification/spec.md)
- [specs/051-whale-entity-enrichment-operationalization/spec.md](/media/sam/1TB/UTXOracle/specs/051-whale-entity-enrichment-operationalization/spec.md)
- [specs/044-feature-service-contract-registry/spec.md](/media/sam/1TB/UTXOracle/specs/044-feature-service-contract-registry/spec.md)
- [specs/045-feature-dependency-provenance-manifest/spec.md](/media/sam/1TB/UTXOracle/specs/045-feature-dependency-provenance-manifest/spec.md)
- [specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md](/media/sam/1TB/UTXOracle/specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md) once that bundle plane exists

Primary references:

- [docs/WHALE_ENTITY_FOUNDATION.md](/media/sam/1TB/UTXOracle/docs/WHALE_ENTITY_FOUNDATION.md)
- [docs/ADDRESS_CLUSTERS_BRK_ADOPTION_CHECKLIST.md](/media/sam/1TB/UTXOracle/docs/ADDRESS_CLUSTERS_BRK_ADOPTION_CHECKLIST.md)
- [docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md)
- [docs/FEATURE_CONTRACT_REGISTRY.md](/media/sam/1TB/UTXOracle/docs/FEATURE_CONTRACT_REGISTRY.md)
- [docs/FEATURE_DEPENDENCY_MATRIX.md](/media/sam/1TB/UTXOracle/docs/FEATURE_DEPENDENCY_MATRIX.md)

Implementation entry points likely to be touched:

- [scripts/clustering/address_clustering.py](/media/sam/1TB/UTXOracle/scripts/clustering/address_clustering.py)
- [scripts/clustering/cost_basis.py](/media/sam/1TB/UTXOracle/scripts/clustering/cost_basis.py)
- [scripts/bootstrap/sync_clusters_to_questdb.py](/media/sam/1TB/UTXOracle/scripts/bootstrap/sync_clusters_to_questdb.py)
- [api/questdb_repository.py](/media/sam/1TB/UTXOracle/api/questdb_repository.py)
- [api/mempool_whale_endpoints.py](/media/sam/1TB/UTXOracle/api/mempool_whale_endpoints.py)
- [scripts/whale_flow_detector.py](/media/sam/1TB/UTXOracle/scripts/whale_flow_detector.py)
- [docs/WHALE_ENTITY_FOUNDATION.md](/media/sam/1TB/UTXOracle/docs/WHALE_ENTITY_FOUNDATION.md)
- [docs/ADDRESS_CLUSTERS_BRK_ADOPTION_CHECKLIST.md](/media/sam/1TB/UTXOracle/docs/ADDRESS_CLUSTERS_BRK_ADOPTION_CHECKLIST.md)
- [docs/contracts/feature_contract_registry.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_contract_registry.yaml)

## Current Baseline

### Existing heuristics and infrastructure

The repo already has:

- union-find clustering
- common-input-ownership clustering
- multi-input transaction grouping
- CoinJoin detection
- change-address filtering
- QuestDB synchronization for `address_clusters`
- canonical whale event enrichment using `address_clusters`

Current operational whale entity object:

- `entity.cluster_id`
- `entity.entity_id`
- `entity.entity_label`
- `entity.label_source`
- `entity.confidence`
- `entity.attribution_kind`

Current omission behavior:

- `entity = null` when enrichment is unavailable or ambiguous

### Current limitations of the existing entity slice

- `cluster_id` is not the same thing as a long-lived registry-grade `entity_id`
- labels are not backed by a formal provenance table
- the current confidence field is intentionally provisional and not decomposed
- there is no historical entity movement graph
- there are no canonical APIs for entity history, flow edges, or entity balance evolution

### BRK decision baseline

`address_clusters` and entity enrichment remain local for now.

Current evidence already captured:

- `BRK` is `BRK-first` for overlapping shared macro metrics
- `BRK` does not currently expose a named entity/clustering contract proven equivalent to the whale/entity use case
- therefore the local clustering and entity foundation remains repo-owned unless that changes explicitly

### Boundary decisions already frozen before implementation

These decisions are already considered settled input to this spec:

- `address_clusters` remains local and continues to back whale enrichment until a separate adoption checklist proves a viable upstream replacement
- `whale_event.v1` remains canonical for whale events; this spec must not break the base event contract
- current omission behavior (`entity = null` when unavailable or ambiguous) remains the minimum compatibility baseline
- `cluster_id` remains a clustering artifact, not a final entity registry contract
- this spec is not where `BRK` macro policy is decided; that belongs to the bundle plane and source-of-truth manifest
- this spec is not where trading signals are defined; it produces forensic/entity intelligence inputs only

## Design

### 1. Identity Model

This spec separates four concepts that are currently too compressed:

1. `address`
2. `cluster_id`
3. `entity_id`
4. `entity_label`

Proposed rules:

- `cluster_id` remains the low-level clustering artifact
- `entity_id` becomes the canonical consumer-facing entity identifier
- multiple clusters may later map to one entity if evidence supports that relationship
- labels become metadata attached to `entity_id`, not the identity itself

Recommended canonical format:

- `btc:entity:<namespace>:<stable_id>`

Transitional compatibility rule:

- the current `cluster:{cluster_id}` form may remain as a compatibility alias during migration
- new APIs and registry artifacts should prefer canonical `entity_id`

### 2. Registry Model

This spec introduces a real entity registry layer.

Minimum logical tables or artifacts:

- `entity_registry`
  - `entity_id`
  - `entity_kind`
  - `registry_status`
  - `first_seen`
  - `last_seen`
  - `display_label`
  - `confidence_overall`
- `cluster_entity_map`
  - `cluster_id`
  - `entity_id`
  - `mapping_confidence`
  - `mapping_method`
  - `mapping_version`
  - `first_seen`
  - `last_seen`
- `entity_labels`
  - `entity_id`
  - `label`
  - `label_kind`
  - `label_confidence`
  - `is_primary`
- `entity_label_provenance`
  - `entity_id`
  - `label`
  - `source_kind`
  - `source_name`
  - `source_ref`
  - `ingested_at`
  - `review_status`
  - `method_version`

### 3. Confidence Model

The current single `confidence` field is not sufficient for a serious entity plane.

This spec separates:

- `cluster_confidence`
- `mapping_confidence`
- `label_confidence`
- `confidence_overall`

Hard rule:

- these values are not trading scores
- they are forensic attribution confidence only

### 4. Provenance Model

Every label and entity mapping must carry provenance.

Minimum provenance vocabulary:

- `source_kind`
  - `heuristic`
  - `curated_csv`
  - `manual_operator`
  - `external_dataset`
  - `inherited_cluster_label`
- `review_status`
  - `unreviewed`
  - `provisional`
  - `reviewed`
  - `deprecated`
- `method_version`
  - exact heuristic or pipeline version identifier

### 5. Flow-of-Funds Plane

The repository needs more than static entity labels. It needs a movement plane.

This spec introduces two distinct movement layers:

1. event layer
2. aggregate layer

#### Event layer

Candidate entities:

- `entity_movement_events`
- `entity_transfer_edges`

Minimum event concepts:

- source entity or cluster
- destination entity or cluster
- amount in BTC
- transaction id
- block height
- timestamp
- direction classification
- attribution confidence

#### Aggregate layer

Candidate entities:

- `entity_flows_daily`
- `entity_balance_snapshots_daily`
- `entity_counterparty_edges_daily`

Minimum aggregate concepts:

- inflow/outflow by entity
- exchange inflow/outflow by entity
- netflow by entity
- top counterparties
- internal reshuffle vs external movement

### 6. Movement Classification

The plane must classify at least:

- `exchange_inflow`
- `exchange_outflow`
- `entity_to_entity`
- `entity_to_unlabeled`
- `unlabeled_to_entity`
- `internal_entity_reshuffle`
- `ambiguous`

The system must not silently label internal reshuffles as new external capital flow.

### 7. Serving Architecture

This spec must preserve the current compute/serve separation:

- clustering and resolution logic may still compute from DuckDB and repo-native workflows
- QuestDB should remain the serving plane for production-grade reads

Recommended ownership split:

- DuckDB or versioned local artifacts = compute and registry-authoring source
- QuestDB = materialized serving copy for API reads

### 8. API Namespace

This spec should not silently stuff everything into the existing whale namespace.

Preferred direction:

- research-first namespace for deeper entity APIs, for example `/api/forensics/*` or `/api/entities/*`
- later optional bundle projection into the consumer bundle plane via `btc_entity.v1`

Candidate route families:

- `GET /api/entities/{entity_id}`
- `GET /api/entities/{entity_id}/history`
- `GET /api/entities/{entity_id}/flows`
- `GET /api/entities/flows`
- `GET /api/entities/search`
- `GET /api/entities/top-movers`

First-slice scope note:

- the guaranteed first slice is limited to:
  - entity metadata lookup
  - entity history
  - entity flow query routes
- `/api/entities/search` and `/api/entities/top-movers` are explicitly deferred unless a later slice admits them with frozen payloads and serving semantics

### 8a. Minimum API Payload Definitions

The first entity API slice MUST freeze minimum payload shapes before RED tests are written.

#### Entity metadata response

Minimum fields:

- `entity_id`
- `display_label`
- `entity_kind`
- `registry_status`
- `first_seen`
- `last_seen`
- `confidence`
  - `cluster_confidence`
  - `mapping_confidence`
  - `label_confidence`
  - `confidence_overall`
- `labels`
- `provenance_summary`
- `source_status`

#### Entity history row

Minimum fields:

- `entity_id`
- `as_of`
- `event_type`
- `registry_status`
- `cluster_ids`
- `confidence_overall`
- `provenance_ref`

#### Flow query row

Minimum fields:

- `window_start`
- `window_end`
- `source_entity_id`
- `target_entity_id`
- `movement_classification`
- `btc_amount`
- `attribution_confidence`
- `is_internal`
- `materialization_status`

#### Error and degraded payload rules

All entity and flow APIs MUST explicitly distinguish:

- `not_found`
- `ambiguous`
- `stale`
- `degraded`
- `partial_materialization`

### 9. Relationship to the Whale Surface

The whale surface remains canonical for whale events.

This spec must:

- preserve `whale_event.v1` backward compatibility
- allow whale events to point to richer registry-backed entity objects later
- avoid making deep entity success a hard dependency for the base whale event

### 10. Relationship to the Future Bundle Plane

The entity intelligence plane is not automatically admitted into the core production bundle plane.

However, this spec should produce a clean future path for:

- `btc_entity.v1`
- `btc_flow.v2` enriched by entity movement context

### 11. History and Replay

The entity plane must be historical by construction.

Minimum requirements:

- event history ordered by block height and timestamp
- daily aggregate history ordered by date and sequence/materialization id
- explicit stale and degraded semantics when upstream clustering or registry refresh lags

### 12. Failure and Degradation Semantics

The entity plane must explicitly distinguish:

- no entity evidence
- ambiguous entity evidence
- stale registry
- stale clustering
- partial aggregate materialization

The current whale omission semantics should be treated as the minimum baseline, not the full final answer.

## Functional Requirements

### FR1: Canonical Entity Identifier

The repository MUST define a stable canonical `entity_id` separate from raw `cluster_id`.

### FR2: Registry Layer

The repository MUST define an entity registry and cluster-to-entity mapping layer.

### FR3: Provenance

Every label and mapping used by the entity plane MUST carry provenance metadata.

### FR4: Confidence Decomposition

The entity plane MUST separate clustering confidence, mapping confidence, and label confidence.

### FR5: Movement Plane

The repository MUST expose a historical movement plane across entities or clusters.

### FR6: Internal vs External Flow

The plane MUST distinguish internal reshuffles from external directional movement whenever the evidence supports that distinction.

### FR7: QuestDB Serving Path

If the entity plane is intended for fast consumer reads, it MUST define a QuestDB materialization path for serving-grade APIs.

### FR8: Whale Compatibility

The canonical whale event surface MUST remain backward compatible while richer entity intelligence is added.

### FR9: Explicit Namespace

The repository MUST define an explicit namespace for entity and movement APIs rather than overloading `/api/whale`.

### FR10: No Unsupported BRK Migration

The implementation MUST NOT assume `BRK` can replace local entity/clustering semantics unless the address-clusters adoption checklist is explicitly satisfied.

## Implementer Handoff

The intended order of attack is:

1. freeze the vocabulary and canonical `entity_id` model
2. design registry and provenance artifacts before touching API shape
3. define how existing `address_clusters` and whale enrichment map into the new registry
4. define historical movement entities and aggregate artifacts
5. choose what must be materialized into QuestDB for serving-grade reads
6. add deeper entity APIs without breaking the whale namespace
7. only after the above, decide whether a future `btc_entity.v1` or `btc_flow.v2` projection is justified

Implementation risks to watch explicitly:

- collapsing `cluster_id` and `entity_id` back into the same concept
- adding labels without provenance
- exposing a single opaque confidence number as if it were registry-grade evidence
- silently classifying internal reshuffles as directional capital flow
- overloading `/api/whale` with deep entity semantics instead of defining an explicit namespace

## Success Criteria

1. the repo has a canonical entity identity model beyond `cluster:{cluster_id}`
2. label provenance and confidence are no longer implicit
3. entity movement and flow history are queryable through explicit APIs
4. internal reshuffles and external flows are not conflated
5. the whale surface can reference richer entity data without losing backward compatibility
6. the repo has a clear path to an eventual `btc_entity.v1` bundle without forcing premature admission into the core live contract
