# spec-044: Feature Service Contract Registry

> **Status**: IMPLEMENTED
> **Priority**: HIGH
> **Effort**: Medium
> **Created**: 2026-04-01
> **Implemented**: 2026-04-01

## Problem Statement

`UTXOracle` now has a verified endpoint inventory, but it still lacks a formal feature contract for downstream consumers such as `nautilus_dev`.

Current gaps:

1. the repository has multiple route families, but no canonical contract registry
2. route labels such as `runtime verified`, `code implemented`, `calculator only`, and `placeholder` are useful for audit, but insufficient for consumer admission
3. there is no versioned declaration of which surfaces are safe for trading, research, or manual-only usage
4. deprecation, freshness, and ownership rules are not centrally documented

This spec defines a versioned contract registry for `UTXOracle` feature surfaces so roadmap work can promote features intentionally instead of by convention.

## Goals

1. define a canonical registry of feature surfaces and their consumer-facing status
2. separate audit labels from consumer admission tiers
3. publish the first `nautilus_dev`-oriented contract slice with explicit caveats
4. introduce versioning and deprecation rules for future contract evolution

## Non-Goals

- implementing every missing endpoint
- redesigning metric formulas
- replacing existing OpenAPI schemas
- turning research-only calculators into public API in this spec alone

## Dependencies

- [docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md)
- [specs/041-questdb-operational-convergence/spec.md](/media/sam/1TB/UTXOracle/specs/041-questdb-operational-convergence/spec.md)
- [specs/043-nautilus-live-trading-integration/spec.md](/media/sam/1TB/UTXOracle/specs/043-nautilus-live-trading-integration/spec.md)

## Design

### 1. Registry Purpose

The registry is the canonical answer to:

- what exists
- who may consume it
- under what caveats
- from which backend
- with which freshness and deprecation rules

It is not a replacement for the route inventory. It is the contract layer on top of the inventory.

### 2. Required Artifacts

Implementation MUST produce:

- `docs/FEATURE_CONTRACT_REGISTRY.md`
- `docs/NAUTILUS_FEATURE_CONTRACT_V1.md`
- `docs/contracts/feature_contract_registry.yaml`

The markdown documents are for operator and integrator reading. The YAML file is the machine-readable source of truth for tooling, validation, and future CI checks.

### 3. Registry Entry Shape

Each contract entry MUST include at least:

- `surface_id`
- `route_family`
- `consumer`
- `current_label`
- `admission_tier`
- `source_of_truth`
- `backend_class`
- `freshness_target`
- `empty_state_policy`
- `stale_state_policy`
- `known_caveats`
- `owner`
- `version`
- `deprecation_status`

### 4. Admission Tiers

Admission tiers are distinct from audit labels.

Initial allowed tiers:

- `tier_1_production`
- `tier_2_production_with_caveats`
- `tier_3_research`
- `tier_4_not_admitted`

Rules:

- `runtime verified` routes may still be excluded if contract requirements are not met
- `code implemented` routes may be admitted only with explicit caveats
- `calculator only` routes are `tier_3_research` unless promoted by a later spec
- `placeholder` routes are `tier_4_not_admitted`

### 5. Frozen First Slice

The first contract slice for `nautilus_dev` MUST include at least:

- live snapshot surface on `8011`
- live charts surface on `8011`
- price comparison APIs
- whale query APIs backed by `mempool_predictions`
- selected main metrics with no known placeholder math in the response body

The first slice MUST explicitly exclude or caveat:

- `PRO Risk`
- `Puell Multiple`
- placeholder whale routes
- any route shadowed by router order

### 6. Governance Rules

Every change to an admitted surface MUST declare one of:

- additive, backward compatible
- caveat change, non-breaking but operationally relevant
- breaking contract change
- deprecation

No breaking change may be merged without:

1. updating the registry version
2. documenting migration notes
3. naming the affected consumer

## Functional Requirements

### FR1: Canonical Registry

The repository MUST maintain one canonical contract registry for feature surfaces.

### FR2: Machine-Readable Source of Truth

The registry MUST exist in machine-readable form as YAML.

### FR3: Consumer-Specific Admission

Each surface MUST declare whether it is admitted for `nautilus_dev`, research-only, or not admitted.

### FR4: Separation of Audit vs Contract Status

The registry MUST preserve the audit label and a separate admission tier.

### FR5: Caveat Capture

Any surface with mocked inputs, hardcoded constants, route shadowing, or duplicate exposure MUST carry an explicit caveat entry.

### FR6: Freshness and Failure Semantics

Every admitted surface MUST declare freshness target plus empty/stale behavior.

### FR7: Versioning

The initial contract MUST be published as `v1`.

### FR8: Deprecation Policy

Every admitted route family MUST have a defined deprecation policy or explicitly state `none`.

## Success Criteria

1. `nautilus_dev` can identify the first admitted feature slice without reading source code
2. every admitted surface has an owner, backend class, and freshness target
3. all currently known caveats from the roadmap prep document are represented in the registry
4. future roadmap work can reference the registry instead of re-auditing route status
