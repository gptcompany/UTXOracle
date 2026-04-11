# spec-054: Production Boundary and Surface Tiering

> **Status**: IMPLEMENTED
> **Priority**: CRITICAL
> **Effort**: Medium
> **Created**: 2026-04-10

## Problem Statement

`UTXOracle` now has a credible live service and a stronger production consumer plane, but the repository still mixes:

1. execution-relevant surfaces
2. operator and debug surfaces
3. research and transition surfaces
4. runtime exposure versus documented exposure

That ambiguity is tolerable for research and local experimentation, but it is not acceptable once `UTXOracle` is treated as an execution input for `Nautilus Trader` with real capital.

Current evidence of the boundary problem:

1. the README still describes `:8011` as exposing only `/health` and `/api/v1/live/*`, while also documenting canonical chart surfaces on `:8011`
2. the actual live app mounts additional families on `:8011`, including chart, QuestDB-backed, bundle, signal, entity, whale, and meta routes
3. there is no single frozen statement of which surfaces are execution-grade versus operator-grade versus research-only
4. there is no fail-closed consumer rule that tells `NT` what it is allowed to read

This spec freezes the service boundary first, before broader execution-grade hardening.

## Goals

1. define the canonical production boundary for `:8011`
2. classify all exposed route families into explicit service tiers
3. define which tiers are allowed to drive `NT`
4. separate execution inputs from operator/debug and research surfaces
5. eliminate documentation-versus-runtime ambiguity

## Non-Goals

- adding new metric families
- redesigning the live worker
- introducing multi-tenant SaaS concepts
- solving detailed auth policy for every route family
- deciding strategy logic or position sizing

## Dependencies

- [specs/040-utxoracle-live-service/spec.md](/media/sam/1TB/UTXOracle/specs/040-utxoracle-live-service/spec.md)
- [specs/044-feature-service-contract-registry/spec.md](/media/sam/1TB/UTXOracle/specs/044-feature-service-contract-registry/spec.md)
- [specs/045-feature-dependency-provenance-manifest/spec.md](/media/sam/1TB/UTXOracle/specs/045-feature-dependency-provenance-manifest/spec.md)
- [specs/048-implemented-route-hardening/spec.md](/media/sam/1TB/UTXOracle/specs/048-implemented-route-hardening/spec.md)
- [specs/050-canonical-8011-promotion/spec.md](/media/sam/1TB/UTXOracle/specs/050-canonical-8011-promotion/spec.md)
- [specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md](/media/sam/1TB/UTXOracle/specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md)
- [specs/053-btc-entity-and-flow-intelligence-plane/spec.md](/media/sam/1TB/UTXOracle/specs/053-btc-entity-and-flow-intelligence-plane/spec.md)

Primary references:

- [docs/PRODUCTION_CONSUMER_SERVICE_PROFILE_2026-04-05.md](/media/sam/1TB/UTXOracle/docs/PRODUCTION_CONSUMER_SERVICE_PROFILE_2026-04-05.md)
- [docs/FEATURE_SERVICE_ROADMAP_2026-04-01.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ROADMAP_2026-04-01.md)
- [docs/FEATURE_CONTRACT_REGISTRY.md](/media/sam/1TB/UTXOracle/docs/FEATURE_CONTRACT_REGISTRY.md)

Implementation entry points likely to be touched later:

- [api/apps/live.py](/media/sam/1TB/UTXOracle/api/apps/live.py)
- [api/routes/live.py](/media/sam/1TB/UTXOracle/api/routes/live.py)
- [api/routes/features.py](/media/sam/1TB/UTXOracle/api/routes/features.py)
- [api/routes/signals.py](/media/sam/1TB/UTXOracle/api/routes/signals.py)
- [api/routes/questdb.py](/media/sam/1TB/UTXOracle/api/routes/questdb.py)
- [api/routes/entities.py](/media/sam/1TB/UTXOracle/api/routes/entities.py)
- [api/mempool_whale_endpoints.py](/media/sam/1TB/UTXOracle/api/mempool_whale_endpoints.py)
- [api/routes/meta.py](/media/sam/1TB/UTXOracle/api/routes/meta.py)

## Current Baseline

Today the repo already has a meaningful service profile:

- `:8011` is treated as the canonical consumer host
- `:8001` is treated as legacy and research-heavy
- `spec-052` introduces a bounded bundle and signal plane
- `spec-053` introduces deeper entity and flow surfaces

What is still missing is the frozen answer to this question:

`Which of these surfaces may directly influence execution, and which must never do so?`

## Design

### 1. Service Tier Model

This spec introduces exactly three tiers:

- `tier_1_execution`
- `tier_2_operator`
- `tier_3_research`

Tier semantics:

- `tier_1_execution`
  - may be consumed directly by `NT`
  - must be bounded, versioned, and fail-closed
  - must participate in execution-safety and SLO rules
- `tier_2_operator`
  - useful for visibility, debugging, validation, and forensics
  - must not be a direct execution dependency
  - may degrade more often than tier 1 without forcing contract expansion
- `tier_3_research`
  - may exist in code, on a non-canonical host, or temporarily on the canonical host during transition
  - not allowed in automated trading decisions

### 2. Proposed Initial Tiering

Important note: this is a conservative first-slice baseline. Surfaces currently labeled `tier_1_production` in `FEATURE_CONTRACT_REGISTRY.md` (such as `/api/prices/*`, `/api/metrics/latest`, `/api/v1/charts/*`, and cost-basis metrics) are intentionally placed in `tier_2_operator` here because they are not yet required by `NT` for execution gating. This is not a demotion of their production quality — it limits the execution-grade contract surface to the minimum set that `NT` actually consumes. Promotion to `tier_1_execution` is available via task T027 (change-control rule).

Initial `tier_1_execution` target:

- `GET /health`
- `GET /api/v1/live/snapshot`
- `GET /api/v1/live/history`
- `GET /api/v1/live/comparison/latest`
- `GET /api/v1/live/ready`
- `GET /api/features/btc/*`
- `GET /api/signals/btc/*`

Initial `tier_2_operator` target:

- `GET /api/prices/*`
- `GET /api/metrics/latest`
- `GET /api/metrics/address-cohorts`
- `GET /api/metrics/cost-basis`
- `GET /api/metrics/wallet-waves`
- `GET /api/metrics/absorption-rates`
- `GET /api/whale/*`
- `GET /api/entities/*`
- `GET /api/v1/charts/*`
- `GET /charts/*`
- `GET /api/meta/features`
- remaining operator and validation endpoints on `:8011` (enumerated during T002)

Initial `tier_3_research` target:

- `:8001` mixed legacy surfaces
- `GET /api/research/tier-stats` even if it remains temporarily exposed on `:8011`
- calculator-heavy families not formally admitted into the canonical service (e.g., research scoring endpoints)
- validation-only and transition-only routes (e.g., migration helpers from spec-050)

### 3. Canonical Consumer Rule

`NT` MUST consume only `tier_1_execution` surfaces.

Important negative rule:

- no direct `NT` dependency on `tier_2_operator` routes is allowed, even if those routes are available on `:8011`

This is the key KISS decision. `NT` should read a small execution-grade contract, not the whole API inventory.

### 4. Runtime Exposure Policy

This spec deliberately separates:

1. `what is exposed`
2. `what is execution-safe`

Allowed transitional state:

- `:8011` may continue exposing `tier_2_operator` routes for now
- `:8011` may continue exposing narrowly scoped `tier_3_research` transition routes if they are explicitly marked
- those routes must be contractually marked as non-execution inputs

Preferred end state:

- operator and research-only families move behind explicit operator documentation, stronger auth posture, or separate host segmentation

### 5. Boundary Artifact

This spec should produce one canonical boundary artifact at `docs/contracts/surface_boundary.yaml`, with at least:

- route family
- host
- tier
- allowed consumers
- source of truth
- fail mode
- execution eligibility

## Acceptance Direction

This spec is complete only when all of the following are true:

1. every route family on `:8011` is assigned to exactly one tier
2. the README and boundary docs match runtime reality
3. `NT` execution inputs are explicitly narrowed to `tier_1_execution`
4. no execution path depends on an unclassified or research-only surface
