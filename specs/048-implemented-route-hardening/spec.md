# spec-048: Implemented Route Hardening

> **Status**: IMPLEMENTED
> **Priority**: HIGH
> **Effort**: Medium
> **Created**: 2026-04-01
> **Implemented**: 2026-04-01

## Problem Statement

Several routes are already exposed as implemented surfaces, but some still contain placeholder inputs, hardcoded baselines, routing conflicts, or duplicate exposure.

Current known issues:

1. `PRO Risk` is implemented, but its API response is built from hardcoded component inputs and empty history
2. `Puell Multiple` is implemented, but its baseline relies on hardcoded constants rather than real issuance history
3. `/api/v1/models/power-law/predict` is shadowed by the generic models router order
4. `/api/v1/live/*` is exposed on both the main app and the dedicated live app
5. contract labels and runtime behavior are now documented, but the implementation itself still carries the debt

This spec hardens implemented routes so supported surfaces are either trustworthy or explicitly removed from the admitted contract.

## Goals

1. eliminate mocked or hardcoded analytical inputs from admitted implemented routes
2. resolve route-order and duplicate-exposure ambiguities
3. define when a route must be demoted instead of silently caveated forever
4. align implementation with the contract registry and provenance manifest

## Non-Goals

- productizing all `calculator only` routes
- designing new trading logic
- expanding the live contract beyond current scope

## Dependencies

- [specs/033-pro-risk-metric/spec.md](/media/sam/1TB/UTXOracle/specs/033-pro-risk-metric/spec.md)
- [specs/034-price-power-law/spec.md](/media/sam/1TB/UTXOracle/specs/034-price-power-law/spec.md)
- [specs/040-utxoracle-live-service/spec.md](/media/sam/1TB/UTXOracle/specs/040-utxoracle-live-service/spec.md)
- [specs/044-feature-service-contract-registry/spec.md](/media/sam/1TB/UTXOracle/specs/044-feature-service-contract-registry/spec.md)
- [specs/045-feature-dependency-provenance-manifest/spec.md](/media/sam/1TB/UTXOracle/specs/045-feature-dependency-provenance-manifest/spec.md)

## Design

### 1. Hardening Principle

A route already exposed to consumers must satisfy one of two states:

- trustworthy enough to remain admitted
- explicitly demoted or isolated as experimental/research

Permanent undocumented caveats are not an acceptable steady state.

### 2. PRO Risk Remediation

`PRO Risk` must choose one path:

- Path A: wire real component inputs and historical context into the existing endpoints
- Path B: demote the route family out of the admitted contract until real inputs exist

`/api/risk/pro/history` must not remain a silent empty-history success response if the route is treated as supported.

### 3. Puell Multiple Remediation

`Puell Multiple` must choose one path:

- Path A: calculate the denominator from real historical issuance inputs
- Path B: remain exposed only as an explicitly caveated research route

Hardcoded baseline math must not be represented as trustworthy production analytics.

### 4. Power Law Route Order

The router order conflict between:

- `/api/v1/models/{name}/predict`
- `/api/v1/models/power-law/predict`

must be resolved in code, not only documented.

### 5. Live Route Host Policy

The repository must decide whether:

- `:8011` is the only canonical live host, or
- `:8001` remains a documented alias with explicit policy

Ambiguous dual exposure is not acceptable for an admitted contract.

## Functional Requirements

### FR1: No Mocked Inputs in Admitted Implemented Routes

An admitted implemented route MUST NOT depend on mocked or hardcoded analytical component inputs.

### FR2: No Hardcoded Baseline Math in Admitted Implemented Routes

An admitted implemented route MUST NOT depend on hardcoded baseline constants for the core metric calculation.

### FR3: Route-Order Integrity

No admitted route may be shadowed by an earlier generic router registration.

### FR4: Canonical Live Host Policy

The repository MUST define one canonical policy for `/api/v1/live/*` host exposure.

### FR5: Demotion Rule

If hardening is not yet implemented, the route MUST be demoted in the contract registry rather than silently treated as supported.

### FR6: Registry Alignment

Any route hardened or demoted by this spec MUST update spec-044 and spec-045 artifacts.

## Success Criteria

1. `PRO Risk` is either real or contractually demoted
2. `Puell Multiple` is either real or contractually demoted
3. `/api/v1/models/power-law/predict` is no longer shadowed
4. live route exposure policy is singular and documented
5. implementation and contract docs agree on all hardened route families
