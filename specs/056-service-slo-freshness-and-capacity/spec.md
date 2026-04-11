# spec-056: Service SLO, Freshness, and Capacity

> **Status**: IMPLEMENTED
> **Priority**: CRITICAL
> **Effort**: Medium
> **Created**: 2026-04-10

## Problem Statement

`UTXOracle` already exposes health and status semantics, but it does not yet define the quantitative service targets that matter for execution-grade use:

1. how fresh the data must be
2. how fast the service must respond
3. which surfaces are covered by strict targets
4. what load the single-host service is expected to handle
5. when degraded service should block trading

Without these numbers, `healthy` and `degraded` remain informative but not operationally binding.

## Goals

1. define explicit SLOs for tier-1 execution surfaces
2. define freshness classes and thresholds
3. define local single-host capacity assumptions
4. define when SLO violations become execution blockers
5. define the difference between internal SLOs and external SLA claims

## Non-Goals

- multi-region availability engineering
- commercial customer SLA credits
- internet-scale public API load
- benchmarking every historical research route

## Dependencies

- [specs/054-production-boundary-and-surface-tiering/spec.md](/media/sam/1TB/UTXOracle/specs/054-production-boundary-and-surface-tiering/spec.md)
- [specs/055-nt-execution-safety-contract/spec.md](/media/sam/1TB/UTXOracle/specs/055-nt-execution-safety-contract/spec.md)
- [specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md](/media/sam/1TB/UTXOracle/specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md)

Primary references:

- [specs/040-utxoracle-live-service/spec.md](/media/sam/1TB/UTXOracle/specs/040-utxoracle-live-service/spec.md)
- [docs/PRODUCTION_CONSUMER_SERVICE_PROFILE_2026-04-05.md](/media/sam/1TB/UTXOracle/docs/PRODUCTION_CONSUMER_SERVICE_PROFILE_2026-04-05.md)

Implementation entry points likely to be touched later:

- [api/apps/live.py](/media/sam/1TB/UTXOracle/api/apps/live.py)
- [api/routes/live.py](/media/sam/1TB/UTXOracle/api/routes/live.py)
- [api/routes/features.py](/media/sam/1TB/UTXOracle/api/routes/features.py)
- [api/routes/signals.py](/media/sam/1TB/UTXOracle/api/routes/signals.py)
- [scripts/live/source_clients.py](/media/sam/1TB/UTXOracle/scripts/live/source_clients.py)

## Current Baseline

The service already exposes:

- route-level health information
- source freshness hints
- degraded or stale semantics in multiple surfaces

What is still missing is the frozen numeric target layer.

## Design

### 1. SLO Scope

Only `tier_1_execution` surfaces receive strict SLOs in the first slice.

`tier_2_operator` surfaces may have best-effort targets, but they must not drive execution gating directly.

Once [spec-055](/media/sam/1TB/UTXOracle/specs/055-nt-execution-safety-contract/spec.md) lands, its canonical execution-status route inherits the same execution-grade SLO discipline as the other `tier_1_execution` latest surfaces.

### 2. First-Slice Service Targets

Initial target direction for local single-host operation:

- `availability`
  - `tier_1_execution` monthly read availability target: `99.5%`
- `latency`
  - `GET /health` local p95: `<= 100ms`
  - `latest` tier-1 reads local p95: `<= 250ms`
  - bounded `history` reads local p95: `<= 1000ms`
- `freshness` (measured as `now() - latest_block_or_capture_timestamp` at response time)
  - live snapshot healthy freshness target: `<= 15s`
  - live snapshot maximum safety window before `stale`: `>= 30s` (i.e., exactly 30s is stale)
  - feature bundle healthy freshness target: `<= 30s`
  - feature bundle maximum safety window before `stale`: `>= 60s` (i.e., exactly 60s is stale)
  - signal healthy freshness target: `<= 30s`
  - signal maximum safety window before `stale`: `>= 60s` (i.e., exactly 60s is stale)

These are operator targets, not external contractual SLA promises.

### 3. Freshness Classes

This spec standardizes three freshness classes for tier-1 data:

- `healthy`
- `degraded`
- `stale`

Directionally:

- `healthy`
  - within the normal target window
- `degraded`
  - outside target but inside the maximum safety window
- `stale`
  - at or outside the maximum safety window; must not be used for new trading decisions but may be logged/published with explicit degradation markers for operator audit

### 4. Capacity Assumption

The first slice should assume one serious automated consumer, not a public high-scale API.

Minimum capacity model:

- one `NT` consumer
- one execution-status read path on the same host once `spec-055` is implemented
- steady-state polling of tier-1 latest routes at up to every `5s`
- a small number of local operator reads
- burst tolerance for retries and dashboards

The purpose is to define realistic bounds for a single-host trading deployment, not to over-design for unknown future clients.

### 5. Execution Coupling

This spec does not decide the final execution mode by itself, but it defines the numeric thresholds used by [spec-055](/media/sam/1TB/UTXOracle/specs/055-nt-execution-safety-contract/spec.md).

Minimum coupling rule:

- `stale` tier-1 inputs cannot coexist with `trade_enabled`
- live snapshot freshness at or beyond `30s` cannot coexist with `trade_enabled`

## Acceptance Direction

This spec is complete only when all of the following are true:

1. tier-1 routes have frozen SLO and freshness targets
2. the thresholds are documented in one canonical location
3. SLO violations can be translated into execution consequences
4. capacity assumptions match the actual intended deployment model
