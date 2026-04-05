# Address Clusters BRK Adoption Checklist

Date: 2026-04-05

Purpose:

- decide whether `BRK` can replace the repo-local `address_clusters` pipeline for canonical whale/entity enrichment

This checklist exists because `BRK-first` is now the preferred policy for overlapping shared macro metrics, but `address_clusters` is not automatically in that category. It should only migrate if `BRK` proves an equivalent or better contract for the actual whale/entity use case.

## Current Audit Status (2026-04-05)

- Current repo evidence says `not migrable yet`.
- Live inspection of local `BRK` `0.1.9` on `2026-04-05` showed a healthy service and a broad `/api/metrics` universe, but no `entity` or `cluster` metric family or named field suitable for the whale enrichment contract.
- The active `BrkClient` integration only consumes a curated metric subset through `/api/metrics/bulk`: `realized_price_usd`, `liveliness`, and `reserve_risk`.
- Local `BRK` validation scripts also target metric families such as `realized_cap`, `nupl`, `sopr`, and `liveliness`; no local integration path was found for address-to-cluster or address-to-entity lookups.
- The canonical whale contract on `:8011` currently derives `entity.cluster_id`, `entity.entity_id`, `entity.entity_label`, `label_source`, and omission semantics from QuestDB `address_clusters`, not from `BRK`.
- Conclusion for now: keep `address_clusters` local unless a concrete `BRK` entity/clustering API or MCP contract is identified and validated against the checks below.

## Required Equivalence Checks

- `BRK` must expose address-to-cluster or address-to-entity data that can be queried deterministically for the existing whale enrichment flow.
- `BRK` must provide stable identifiers with semantics at least as strong as the current local `cluster_id` usage.
- `BRK` must expose enough metadata to preserve current omission/degradation behavior, for example missing entity, ambiguous attribution, or low-confidence classification.
- `BRK` must support the freshness window required by the canonical whale surface on `:8011`.
- `BRK` must support historical rebuild/backfill workflows without leaving the downstream enrichment contract in an inconsistent state.

## Contract Compatibility Checks

- The resulting entity/clustering contract must preserve current `spec-047` and `spec-051` whale surface semantics or document the intentional differences.
- The migration must not silently change downstream fields, nullability, or omission rules used by [mempool_whale_endpoints.py](/media/sam/1TB/UTXOracle/api/mempool_whale_endpoints.py).
- The replacement path must define what happens when `BRK` is unavailable, stale, or partially degraded.

## Operational Checks

- Query latency and throughput must be acceptable for the current canonical serving path.
- Operational dependency cost must be explicitly accepted, since this would convert whale/entity enrichment from repo-owned state to upstream dependency.
- Monitoring and freshness checks must exist before cutover.

## Validation Plan Before Cutover

- Run a dual-read comparison between local `address_clusters` and candidate `BRK` outputs on a representative address sample.
- Measure disagreement rate, missing coverage, and label drift.
- Confirm that known whale/entity examples continue to resolve correctly.
- Define a rollback path that restores the local sync pipeline if `BRK` equivalence is not met.

## Decision Rule

- Keep `address_clusters` local by default until all checks above pass and the migration decision is written into:
  - [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)
  - [docs/contracts/metric_source_of_truth_manifest.yaml](/media/sam/1TB/UTXOracle/docs/contracts/metric_source_of_truth_manifest.yaml)
  - the active whale/entity operational spec
