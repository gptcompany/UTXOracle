# spec-059: Observability and Incident Response

> **Status**: IMPLEMENTED
> **Priority**: HIGH
> **Effort**: Medium
> **Created**: 2026-04-10

## Problem Statement

`UTXOracle` already has health checks, logging, and multiple status surfaces, but that is still not the same thing as execution-grade observability.

For real-capital use, the operator needs to know quickly and unambiguously:

1. whether the execution inputs are fresh
2. whether sequences are monotonic
3. whether upstreams are diverging
4. whether the service should keep trading or stop
5. what exact runbook to follow when things go wrong

Without this, the system may fail in a "gray" mode where it keeps running but should not be trusted.

## Goals

1. define the canonical metrics and alerts for tier-1 execution surfaces
2. define incident severity classes
3. define minimum runbooks for critical failure modes
4. define how observability feeds the execution safety state
5. define the minimum operator evidence required after an incident

## Non-Goals

- building a full enterprise SOC
- public status pages
- cross-region incident management
- replacing `NT` risk monitoring

## Dependencies

- [specs/054-production-boundary-and-surface-tiering/spec.md](/media/sam/1TB/UTXOracle/specs/054-production-boundary-and-surface-tiering/spec.md)
- [specs/055-nt-execution-safety-contract/spec.md](/media/sam/1TB/UTXOracle/specs/055-nt-execution-safety-contract/spec.md)
- [specs/056-service-slo-freshness-and-capacity/spec.md](/media/sam/1TB/UTXOracle/specs/056-service-slo-freshness-and-capacity/spec.md)
- [specs/057-data-quality-reconciliation-and-restatement/spec.md](/media/sam/1TB/UTXOracle/specs/057-data-quality-reconciliation-and-restatement/spec.md)

Primary references:

- [docs/OPERATIONS.md](/media/sam/1TB/UTXOracle/docs/OPERATIONS.md)
- [api/metrics_collector.py](/media/sam/1TB/UTXOracle/api/metrics_collector.py)
- [docs/NAUTILUS_FEATURE_CONTRACT_V1.md](/media/sam/1TB/UTXOracle/docs/NAUTILUS_FEATURE_CONTRACT_V1.md)

Implementation entry points likely to be touched later:

- [api/apps/live.py](/media/sam/1TB/UTXOracle/api/apps/live.py)
- [api/routes/live.py](/media/sam/1TB/UTXOracle/api/routes/live.py)
- [scripts/live/source_clients.py](/media/sam/1TB/UTXOracle/scripts/live/source_clients.py)
- [scripts/live/storage.py](/media/sam/1TB/UTXOracle/scripts/live/storage.py)

## Current Baseline

The repo already has parts of the observability story:

- health endpoints
- source-level status in live snapshots
- some metrics and logging utilities
- operator runbooks in broader docs

What it still lacks is the explicit execution-grade observability and incident model.

Important baseline limitations:

- the generic metrics collector measures HTTP behavior, not execution trust by itself
- the current broad operations runbook is useful background, but it is not yet a frozen execution-grade runbook set for tier-1 trading surfaces

## Design

### 1. Canonical Metric Families

The first slice should require metrics for:

- tier-1 read latency
- tier-1 error rate
- live snapshot freshness
- bundle freshness
- signal freshness
- sequence monotonicity and gap detection
- upstream source status
- divergence and quarantine event counts
- restatement event counts
- current execution mode and execution-state transition events

Modeling rule:

- a green `/health` response or generic app-level latency metric cannot by itself clear an execution-affecting condition
- execution-affecting recovery must be justified by tier-1 freshness, sequence, source, and execution-state evidence

### 2. Alert Severity

This spec defines three alert levels:

- `warning`
- `critical`
- `fatal`

Direction:

- `warning`
  - investigate soon; trading may remain possible
  - execution mapping: no automatic mode change; operator should investigate within 15 minutes
- `critical`
  - trading should degrade or stop unless cleared quickly
  - execution mapping: system transitions to `manage_only` or `halted` depending on condition (see threshold table below)
- `fatal`
  - immediate fail-closed state
  - execution mapping: immediate transition to `halted`

Severity threshold table (reuses spec-056 numeric targets):

| Condition | Threshold | Duration | Severity | Execution Mode |
|-----------|-----------|----------|----------|----------------|
| live snapshot freshness | ≥ 15s, < 30s | any | `warning` | no change |
| live snapshot freshness | ≥ 30s | any | `critical` | `manage_only` → `halted` if > 60s |
| bundle/signal freshness | ≥ 30s, < 60s | any | `warning` | no change |
| bundle/signal freshness | ≥ 60s | any | `critical` | `manage_only` → `halted` if > 120s |
| tier-1 read latency p95 | > 250ms | 2 min | `warning` | no change |
| tier-1 read latency p95 | > 1000ms | 2 min | `critical` | `manage_only` |
| tier-1 endpoint error rate | > 5% | 2 min | `critical` | `manage_only` |
| tier-1 endpoint unavailable | any | 30s | `fatal` | `halted` |
| sequence monotonicity broken | any | immediate | `fatal` | `halted` |
| quarantined tier-1 data | any | immediate | `critical` | `halted` (per spec-057) |
| unresolved critical restatement | any | immediate | `critical` | `manage_only` |

Clearance rule:

- `critical` and `fatal` alerts remain active until the underlying tier-1 evidence recovers; dashboard greenness alone is not enough
- clearance requires: the triggering metric returns within healthy range for at least 2 consecutive check intervals

### 3. Minimum Runbooks

The first slice should require runbooks for at least the following scenarios. Each runbook must specify: trigger condition, severity, first operator action, recovery confirmation, and execution consequence.

- stale live snapshot
  - trigger: live snapshot freshness ≥ 30s
  - severity: `critical`
  - action: check live worker health, verify Bitcoin Core RPC, check source_clients status
  - recovery: freshness returns to < 15s for 2 consecutive reads
  - execution: `manage_only` while stale; `halted` if > 60s
- tier-1 endpoint failure
  - trigger: any tier-1 endpoint returns 5xx or is unreachable for > 30s
  - severity: `fatal`
  - action: check uvicorn process, review error logs, verify upstream dependencies
  - recovery: endpoint returns 200 with valid payload for 3 consecutive reads
  - execution: immediate `halted`
- bundle or signal sequence gap
  - trigger: `sequence_id` non-monotonic or gap > 1
  - severity: `fatal`
  - action: verify bundle_writer/signal_writer, check QuestDB writes, inspect last known good sequence
  - recovery: monotonic sequence resumes for 5 consecutive writes
  - execution: immediate `halted`
- upstream divergence spike
  - trigger: local vs upstream disagreement exceeds allowed threshold per source-of-truth manifest
  - severity: `critical`
  - action: check BRK sync status, verify electrs, compare with mempool data
  - recovery: divergence falls within threshold for 3 consecutive checks
  - execution: `manage_only`
- QuestDB unavailable
  - trigger: QuestDB health check fails or query timeout > 5s
  - severity: `critical`
  - action: check QuestDB process, disk space, connection pool
  - recovery: QuestDB responds within 1s for 3 consecutive health checks
  - execution: `manage_only` (materialized data may be stale)
- restatement affecting execution inputs
  - trigger: restatement artifact with severity `critical` on tier-1 surface
  - severity: `critical`
  - action: review restatement artifact, assess impact on current positions, decide accept-risk or wait
  - recovery: restatement resolved or explicitly accepted with documented risk
  - execution: `manage_only` until resolved
- execution-status unavailable or inconsistent with its input evidence
  - trigger: `/api/execution/btc/status` unavailable or `execution_mode` contradicts tier-1 input states
  - severity: `fatal`
  - action: verify execution-state derivation logic, check tier-1 inputs, compare individual freshness
  - recovery: execution-status returns consistent state matching tier-1 evidence for 3 consecutive reads
  - execution: immediate `halted`

### 4. Incident Evidence

Every critical or fatal incident should produce a small artifact set with the following schema:

```json
{
  "incident_id": "INC-YYYYMMDD-NNN",
  "started_at": "ISO-8601",
  "ended_at": "ISO-8601 or null if ongoing",
  "trigger": "alert name and metric value that triggered",
  "severity": "critical | fatal",
  "affected_surfaces": ["list of route families affected"],
  "execution_consequence": "mode transition taken (e.g., trade_enabled → halted)",
  "operator_action": "what the operator did",
  "recovery_confirmation": "evidence that recovery criteria were met",
  "followup": "fix applied, or explicit accepted-risk with expiration date"
}
```

If multiple runbooks are executed during a single incident, they produce one incident record with a combined action log, not separate records per runbook.

### 5. Execution Coupling

This spec feeds [spec-055](/media/sam/1TB/UTXOracle/specs/055-nt-execution-safety-contract/spec.md) by defining the telemetry and alert evidence that can justify `observe_only`, `manage_only`, or `halted`.

Observability provides evidence for fail-closed execution decisions; it does not override the execution state machine.

## Acceptance Direction

This spec is complete only when all of the following are true:

1. tier-1 surfaces have canonical telemetry
2. critical failure modes have explicit runbooks
3. incidents produce consistent evidence
4. observability is tied to execution decisions, not just dashboards
