# spec-058: Schema Evolution and Deprecation Policy

> **Status**: DRAFT
> **Priority**: HIGH
> **Effort**: Medium
> **Created**: 2026-04-10

## Problem Statement

The repo now has real contracts, manifests, and bounded bundle surfaces, but it still lacks the frozen change discipline needed for a live trading consumer:

1. what counts as additive versus breaking
2. how long deprecated shapes remain valid
3. how `NT` compatibility is verified before promotion
4. how replay and live compatibility stay aligned

Without this policy, a harmless-looking payload change can break execution or invalidate replay assumptions.

## Goals

1. define a simple versioning policy for execution-grade surfaces
2. define additive-only rules for current major versions
3. define how breaking changes are introduced
4. define a minimum deprecation window
5. define compatibility checks required before promotion

## Non-Goals

- creating a generic schema registry platform
- versioning every internal helper model
- rewriting all route contracts immediately

## Dependencies

- [specs/044-feature-service-contract-registry/spec.md](/media/sam/1TB/UTXOracle/specs/044-feature-service-contract-registry/spec.md)
- [specs/045-feature-dependency-provenance-manifest/spec.md](/media/sam/1TB/UTXOracle/specs/045-feature-dependency-provenance-manifest/spec.md)
- [specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md](/media/sam/1TB/UTXOracle/specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md)
- [specs/054-production-boundary-and-surface-tiering/spec.md](/media/sam/1TB/UTXOracle/specs/054-production-boundary-and-surface-tiering/spec.md)
- [specs/055-nt-execution-safety-contract/spec.md](/media/sam/1TB/UTXOracle/specs/055-nt-execution-safety-contract/spec.md)

Primary references:

- [docs/FEATURE_CONTRACT_REGISTRY.md](/media/sam/1TB/UTXOracle/docs/FEATURE_CONTRACT_REGISTRY.md)
- [docs/contracts/feature_contract_registry.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_contract_registry.yaml)
- [docs/NAUTILUS_FEATURE_CONTRACT_V1.md](/media/sam/1TB/UTXOracle/docs/NAUTILUS_FEATURE_CONTRACT_V1.md)

Implementation entry points likely to be touched later:

- [api/models/questdb.py](/media/sam/1TB/UTXOracle/api/models/questdb.py)
- [scripts/live/models.py](/media/sam/1TB/UTXOracle/scripts/live/models.py)
- [docs/contracts/feature_contract_registry.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_contract_registry.yaml)
- [docs/contracts/feature_provenance_manifest.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_provenance_manifest.yaml)

## Current Baseline

The repo already has:

- route families with named contracts
- payloads carrying `schema_version`
- a feature contract registry
- a repo-wide governance vocabulary from `spec-044`

What it still lacks is the frozen policy that tells operators and consumers how those contracts may evolve.

Important baseline limitation:

- `spec-044` already introduced broad governance terms such as additive, caveat change, breaking, and deprecation
- it does not yet freeze the stricter execution-grade change discipline required for `NT`-facing surfaces

## Design

### 1. Change Classes

This spec defines four change classes:

- `docs_only`
- `additive_non_breaking`
- `behavioral_tightening`
- `breaking`

Direction:

- `docs_only`
  - no consumer impact
- `additive_non_breaking`
  - new optional fields or metadata only
- `behavioral_tightening`
  - stricter semantics without shape breakage; requires explicit review
  - examples: narrowing the valid range of a numeric field (e.g., `confidence` accepting 0.0-1.0 instead of 0.0-100.0), adding a NOT NULL constraint to a previously nullable optional field, tightening an enum to fewer values, changing a timestamp from "approximate" to "must be monotonic", requiring a field ordering that was previously unordered
- `breaking`
  - removal, rename, incompatible semantic change, required field change, or contract split

Compatibility note:

- `spec-044` remains the broad repo-wide governance baseline
- for execution-grade surfaces, `behavioral_tightening` is the stricter execution-grade analogue of the older `caveat change` label from `spec-044`
- migration rule: existing `caveat change` entries in `feature_contract_registry.yaml` retain their label for non-execution surfaces; for `tier_1_execution` surfaces, each existing `caveat change` must be reclassified as either `additive_non_breaking` or `behavioral_tightening` during task T016
- `deprecation` remains a lifecycle overlay associated with replacement or retirement; it is not a fifth change class here

### 2. Major-Version Rule

For execution-grade `v1` surfaces, the policy is:

- additive-only by default
- no field removal
- no field rename
- no silent semantic repurposing

Breaking changes require:

- a new major version
- an explicit compatibility and migration note
- a parallel overlap period where practical

### 3. Deprecation Window

Minimum first-slice rule:

- breaking replacement of an execution-grade surface should have a minimum `30 day` deprecation window unless an emergency operator override is recorded in the decision log with: override reason, affected surfaces, operator name, and expiration date

### 4. NT Compatibility Gate

Before promoting a schema-affecting or `behavioral_tightening` change into the execution path, the service should require:

- route contract validation
- replay compatibility verification
- `NT` adapter compatibility verification
- explicit signoff when semantics tighten even if the payload shape stays compatible

This is the practical safety check, not bureaucracy.

## Acceptance Direction

This spec is complete only when all of the following are true:

1. execution-grade surfaces have a frozen evolution policy
2. breaking or `behavioral_tightening` changes cannot land silently
3. deprecations have a minimum window
4. `NT` compatibility becomes an explicit promotion gate for schema-affecting or `behavioral_tightening` changes
