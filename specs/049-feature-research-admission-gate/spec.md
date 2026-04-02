# spec-049: Feature Research Admission Gate

> **Status**: COMPLETE
> **Priority**: HIGH
> **Effort**: Medium
> **Created**: 2026-04-02
> **Governance Baseline Published**: 2026-04-02
> **Decision Closed**: 2026-04-02

## Problem Statement

`M6` made `/api/metrics/nupl` and `/api/metrics/cost-basis` live as `tier_3_research` routes, but the repo still lacks a formal gate for promoting live research routes into a future consumer contract.

Current gaps:

1. runtime availability can be mistaken for contract admission
2. `nupl` contains one explicitly estimated output field that needs field-level policy before any promotion
3. `cost-basis` is analytically strong, but no post-`M6` consumer-use or reproducibility gate has been frozen
4. `reserve-risk` is still analytically incomplete and must not be pulled into the same admission discussion

This spec defines the post-`M6` governance gate for any future research-to-production promotion.

## Goals

1. define explicit admission criteria for live research-only routes
2. separate route availability from consumer admission
3. freeze route-specific promotion rules for `nupl` and `cost-basis`
4. keep `reserve-risk` out of the gate until hardening is complete

## Non-Goals

- promoting `nupl` or `cost-basis` immediately
- hardening `reserve-risk`
- reworking DuckDB serving semantics already frozen in `M6`
- expanding the `nautilus_dev` `v1` contract

## Dependencies

- [specs/043-nautilus-live-trading-integration/spec.md](/media/sam/1TB/UTXOracle/specs/043-nautilus-live-trading-integration/spec.md)
- [specs/044-feature-service-contract-registry/spec.md](/media/sam/1TB/UTXOracle/specs/044-feature-service-contract-registry/spec.md)
- [specs/045-feature-dependency-provenance-manifest/spec.md](/media/sam/1TB/UTXOracle/specs/045-feature-dependency-provenance-manifest/spec.md)
- [specs/046-calculator-surface-productization/spec.md](/media/sam/1TB/UTXOracle/specs/046-calculator-surface-productization/spec.md)

## Design

### 1. Admission Rule

No live research route may enter a downstream consumer contract without an explicit admission decision recorded in roadmap, registry, provenance, and consumer docs.

### 2. Evidence Classes

Every candidate route must be assessed on:

1. runtime correctness and degraded semantics
2. field-level semantic stability
3. validation evidence
4. operator reproducibility
5. consumer-use justification

### 3. Route-Specific Gates

#### `nupl_surface`

Before any promotion beyond `tier_3_research`, confirm:

1. the core `nupl` value has acceptable external-validation evidence
2. `pct_supply_in_profit` is either excluded from the admitted slice or admitted only with explicit estimated-field semantics
3. the admitted field subset is frozen

#### `cost_basis_surface`

Before any promotion beyond `tier_3_research`, confirm:

1. the consumer use case is explicit
2. the admitted field subset is explicit
3. operator reproducibility checks are frozen
4. route-level degraded semantics remain part of the contract

#### `reserve-risk`

`reserve-risk` must not be considered by this spec until a separate hardening slice removes placeholder/default internals.

### 4. Promotion Output

This spec may end in any of the following valid outcomes:

- no promotion
- promotion of `cost_basis_surface` only
- promotion of a reduced `nupl_surface` slice only
- promotion of both routes with route-specific caveats

## Functional Requirements

### FR1: Explicit Post-M6 Gate

The repo MUST define a named post-`M6` admission gate for live research routes.

### FR2: Field-Level Policy

Every route considered for promotion MUST have field-level admission policy, not only route-level status.

### FR3: Estimated Fields

Estimated fields MUST be either excluded from admitted consumer slices or explicitly marked as estimated in consumer-facing contract docs.

### FR4: NUPL Validation

`nupl_surface` MUST NOT be promoted without named validation evidence for the core `nupl` signal.

### FR5: Cost Basis Reproducibility

`cost_basis_surface` MUST NOT be promoted without frozen reproducibility and operator-acceptance criteria.

### FR6: Reserve Risk Separation

`reserve-risk` MUST remain outside this gate until hardening removes placeholder/default internals.

### FR7: Contract Update Discipline

Any promotion decision produced by this spec MUST update:

- roadmap
- contract registry
- provenance manifest
- consumer contract docs

## Success Criteria

1. `nupl` and `cost-basis` each have explicit go/no-go criteria beyond `tier_3_research`
2. `reserve-risk` is explicitly kept out of this gate
3. the roadmap no longer implies that live research routes can drift into consumer contracts by convention
4. future admission work can proceed without re-auditing `M6`
