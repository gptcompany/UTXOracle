# spec-045: Feature Dependency & Provenance Manifest

> **Status**: IMPLEMENTED
> **Priority**: HIGH
> **Effort**: Medium
> **Created**: 2026-04-01
> **Implemented**: 2026-04-01

## Problem Statement

The repository now has a partial dependency map in documentation, but dependency and provenance are still implicit at runtime.

Current gaps:

1. route families do not expose one authoritative dependency manifest
2. consumers cannot distinguish QuestDB-backed, DuckDB-backed, RPC-backed, externally sourced, or hardcoded-computed outputs without reading code
3. credentials and service requirements are not attached to feature surfaces in a machine-readable way
4. provenance semantics are inconsistent across live APIs, main app APIs, and research calculators

This spec defines one manifest for route dependency, provenance, writer ownership, and failure semantics.

## Goals

1. create one machine-readable dependency and provenance manifest
2. map each route family to backend class, tables, upstreams, credentials, and failure modes
3. make provenance queryable by operators and downstream consumers
4. support future CI checks for dependency drift

## Non-Goals

- rewriting existing health checks
- exposing full lineage for every historical dataset in the first pass
- replacing OpenAPI with a custom metadata protocol

## Dependencies

- [specs/044-feature-service-contract-registry/spec.md](/media/sam/1TB/UTXOracle/specs/044-feature-service-contract-registry/spec.md)
- [docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md)

## Design

### 1. Manifest Scope

The manifest MUST capture, per route family:

- backend kind
- specific tables or views
- external upstreams
- required credentials or env vars
- write-path owner
- expected freshness owner
- empty/stale/error semantics
- provenance notes and caveats

### 2. Required Artifacts

Implementation MUST produce:

- `docs/FEATURE_DEPENDENCY_MATRIX.md`
- `docs/contracts/feature_provenance_manifest.yaml`

Optional but recommended:

- `GET /api/meta/features`

The endpoint, if implemented, MUST return metadata only. It must not be treated as a new data plane.

### 3. Backend Classes

Allowed initial backend classes:

- `questdb`
- `duckdb_utxo_lifecycle`
- `duckdb_daily_prices`
- `bitcoin_core_rpc`
- `external_api`
- `computed_inline`
- `hybrid`

### 4. Provenance Fields

Each manifest entry MUST include:

- `route_family`
- `backend_class`
- `primary_tables`
- `upstreams`
- `required_env`
- `writer_owner`
- `read_path_owner`
- `freshness_source`
- `failure_mode`
- `provenance_notes`

### 5. Failure Semantics

Failure semantics MUST distinguish at least:

- `empty`
- `stale`
- `degraded`
- `misconfigured`
- `placeholder`

This is required because a route can be implemented but still be non-admissible for operational reasons.

### 6. Priority Surfaces

First-pass coverage MUST include:

- `/api/prices/*`
- `/api/metrics/latest`
- `/api/metrics/exchange-netflow*`
- `/api/metrics/sopr`
- `/api/metrics/nvt`
- `/api/metrics/volatility`
- `/api/metrics/puell-multiple`
- `/api/metrics/mining-*`
- `/api/risk/pro*`
- `/api/v1/live/*`
- `/api/v1/charts/*`
- `/api/v1/validation/rbn/*`
- `/api/whale/*`

## Functional Requirements

### FR1: Machine-Readable Manifest

The repository MUST maintain one YAML manifest for dependency and provenance metadata.

### FR2: Backend Classification

Every covered route family MUST declare its backend class.

### FR3: Credentials and Upstreams

Every route family that depends on external services or credentials MUST declare them explicitly.

### FR4: Writer Ownership

Every route family MUST declare which process or subsystem is responsible for keeping its data current.

### FR5: Failure Mode Semantics

Every route family MUST declare expected empty, stale, degraded, and misconfigured behavior.

### FR6: Consumer-Visible Provenance

The repository SHOULD expose manifest data through a metadata endpoint or equivalent generated documentation.

### FR7: Drift Detection

The manifest MUST be suitable for validation against code and docs in CI.

## Success Criteria

1. no admitted route family has ambiguous backend attribution
2. routes with hardcoded calculations are classified explicitly as `computed_inline`
3. operators can identify missing env or missing upstream dependencies without source inspection
4. future roadmap work can group tasks by dependency family instead of by route name only
