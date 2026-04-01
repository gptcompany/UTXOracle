# Whale Entity Foundation

Date: 2026-04-02

Status: Initial `whale_event.v1` entity foundation for the canonical whale API surface

Canonical surface:

- `GET /api/whale/transactions`
- `GET /api/whale/summary`
- `GET /api/whale/transaction/{txid}`

## 1. Purpose

This document freezes the minimum entity foundation used by the canonical whale API surface.

It does not claim full attribution. It only defines:

- a stable additive `whale_event.v1` shape
- the minimum `entity` object for future enrichment
- the omission rules when enrichment is unavailable or ambiguous

## 2. `whale_event.v1`

Observed event fields:

- `event_id`
- `prediction_id`
- `transaction_id`
- `flow_type`
- `btc_value`
- `fee_rate`
- `urgency_score`
- `rbf_enabled`
- `detection_timestamp`
- `predicted_confirmation_block`
- `confidence_score`
- `source`
- `status`

Entity enrichment fields:

- `entity_enrichment_status`
- `entity.cluster_id`
- `entity.entity_id`
- `entity.entity_label`
- `entity.label_source`
- `entity.confidence`
- `entity.attribution_kind`

## 3. Entity Object

The canonical additive entity object is:

```json
{
  "cluster_id": "cluster_001",
  "entity_id": "cluster:cluster_001",
  "entity_label": "Binance",
  "label_source": "questdb.address_clusters.label",
  "confidence": 0.8,
  "attribution_kind": "inferred"
}
```

Rules:

- `entity_id` is stable within this slice and is derived as `cluster:{cluster_id}`
- `cluster_id` comes from `address_clusters.cluster_id`
- `entity_label` is optional and comes from `address_clusters.label`
- `label_source` must identify the concrete source field used
- `confidence` is required whenever `entity` is present
- `attribution_kind` is `inferred` in this slice

## 4. Confidence Semantics

This slice uses provisional confidence values only for the entity foundation:

- `0.8` when a stable cluster and a single label are available
- `0.6` when only a stable cluster is available

These values are not trading scores. They are enrichment-confidence placeholders for future entity work.

## 5. Omission Behavior

`entity` must be omitted (`null`) when:

- `exchange_addresses` is absent from the whale event
- no matching `address_clusters` rows exist
- enrichment resolves to conflicting cluster IDs

`entity_enrichment_status` must then be:

- `unavailable` when no enrichment can be derived
- `ambiguous` when conflicting cluster evidence exists
- `inferred` when the `entity` object is populated

## 6. Observed vs Inferred Policy

Observed facts:

- the whale transaction itself
- prediction identifiers
- flow classification
- urgency, fee, and confirmation fields

Inferred data:

- cluster membership
- derived `entity_id`
- human-readable labels
- attribution confidence

Consumers must treat observed and inferred fields differently.

## 7. Data Dependencies

Base event data comes from:

- QuestDB `mempool_predictions`

Optional enrichment comes from:

- QuestDB `address_clusters`

If enrichment data is unavailable, the base whale event contract still remains valid.
