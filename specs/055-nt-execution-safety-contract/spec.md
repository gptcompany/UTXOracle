# spec-055: NT Execution Safety Contract

> **Status**: IMPLEMENTED
> **Priority**: CRITICAL
> **Effort**: Large
> **Created**: 2026-04-10

## Problem Statement

Even a healthy local API is not automatically safe to use for live trading.

For real-capital `Nautilus Trader` integration, the missing piece is not another feature family. The missing piece is a deterministic execution-safety contract that answers:

1. when new positions are allowed
2. when only risk reduction is allowed
3. when the system must stop trading
4. how startup, replay, staleness, sequence gaps, and partial failures affect those decisions

Without this layer, `NT` is forced to infer safety from a mix of route-specific statuses, which is error-prone and not execution-grade.

## Goals

1. define one bounded machine-consumable execution state for `NT`
2. define the exact gating rules for `trade`, `manage-only`, and `halt`
3. define warmup and restart behavior
4. define fail-closed behavior when execution inputs are unavailable or ambiguous
5. define capital rollout stages from shadow mode to real size

## Non-Goals

- encoding strategy alpha
- defining position sizing formulas
- replacing `NT` risk controls
- covering exchange-side order management in detail

## Dependencies

- [specs/043-nautilus-live-trading-integration/spec.md](/media/sam/1TB/UTXOracle/specs/043-nautilus-live-trading-integration/spec.md) (superseded adapter vocabulary)
- [specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md](/media/sam/1TB/UTXOracle/specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md)
- [specs/054-production-boundary-and-surface-tiering/spec.md](/media/sam/1TB/UTXOracle/specs/054-production-boundary-and-surface-tiering/spec.md)
- [specs/056-service-slo-freshness-and-capacity/spec.md](/media/sam/1TB/UTXOracle/specs/056-service-slo-freshness-and-capacity/spec.md)
- [specs/057-data-quality-reconciliation-and-restatement/spec.md](/media/sam/1TB/UTXOracle/specs/057-data-quality-reconciliation-and-restatement/spec.md)
- [specs/058-schema-evolution-and-deprecation-policy/spec.md](/media/sam/1TB/UTXOracle/specs/058-schema-evolution-and-deprecation-policy/spec.md)
- [specs/059-observability-and-incident-response/spec.md](/media/sam/1TB/UTXOracle/specs/059-observability-and-incident-response/spec.md)

Primary references:

- [docs/NAUTILUS_FEATURE_CONTRACT_V1.md](/media/sam/1TB/UTXOracle/docs/NAUTILUS_FEATURE_CONTRACT_V1.md)
- [docs/PRODUCTION_CONSUMER_SERVICE_PROFILE_2026-04-05.md](/media/sam/1TB/UTXOracle/docs/PRODUCTION_CONSUMER_SERVICE_PROFILE_2026-04-05.md)

Implementation entry points likely to be touched later:

- [api/routes/live.py](/media/sam/1TB/UTXOracle/api/routes/live.py)
- [api/routes/signals.py](/media/sam/1TB/UTXOracle/api/routes/signals.py)
- [api/apps/live.py](/media/sam/1TB/UTXOracle/api/apps/live.py)
- [scripts/live/models.py](/media/sam/1TB/UTXOracle/scripts/live/models.py)
- [scripts/live/storage.py](/media/sam/1TB/UTXOracle/scripts/live/storage.py)

## Current Baseline

The repo already exposes:

- canonical live snapshot state
- bounded BTC feature bundles
- bounded BTC signal snapshots
- degraded and stale status semantics

But it does not yet expose one final execution decision object that `NT` can trust directly.

Compatibility note:

- [spec-043](/media/sam/1TB/UTXOracle/specs/043-nautilus-live-trading-integration/spec.md) froze an earlier adapter-local three-state vocabulary: `STATUS_OK`, `STATUS_LIQUIDATE_ONLY`, `STATUS_HALT`
- [spec-043](/media/sam/1TB/UTXOracle/specs/043-nautilus-live-trading-integration/spec.md) also froze first-slice gates around freshness, required source health, confidence, and anomaly bounds
- this spec supersedes that earlier execution-state shape for the service-side contract
- those earlier safety concerns are not discarded; they must be re-expressed inside the new service-side execution contract
- if the older adapter vocabulary remains temporarily, it must be treated as a compatibility projection from the new execution modes rather than a parallel authority

## Design

### 1. Execution Modes

This spec defines exactly five execution modes:

- `halted`
- `warming_up`
- `observe_only`
- `manage_only`
- `trade_enabled`

Mode meaning:

- `halted`
  - no new orders
  - no strategy-driven position changes
  - operator intervention required or a hard fail-closed condition is active
- `warming_up`
  - service is starting, replaying, or rebuilding enough state to become trustworthy
  - no new risk may be added
- `observe_only`
  - data may still be visible to dashboards and logs
  - `NT` must not trade from it
- `manage_only`
  - reducing or neutralizing risk is allowed
  - opening new directional exposure is not allowed
- `trade_enabled`
  - all execution-grade conditions are satisfied

### 2. Fail-Closed Rule

Unknown or ambiguous safety state MUST resolve to `halted`, not to `trade_enabled`.

Quorum rule: if any single required tier-1 input (per section 3) is unavailable or stale at or beyond `spec-056` thresholds, the system must not remain in `trade_enabled`. The unavailability of even one input is sufficient to trigger degradation. Timeout for "unavailable" is defined by the boundary-inclusive `spec-056` freshness stale thresholds (live snapshot: >= 30s, bundle/signal: >= 60s).

Examples:

- execution endpoint unavailable
- required tier-1 input unavailable or stale at or beyond spec-056 threshold
- monotonic sequence guarantee violated
- unresolved critical restatement (per spec-057)
- schema compatibility unknown (per spec-058)

### 3. Minimum Inputs

The first slice should derive execution safety only from `tier_1_execution` inputs:

- `/health`
- `/api/v1/live/snapshot`
- `/api/features/btc/core/latest`
- `/api/features/btc/flow/latest`
- `/api/features/btc/macro/latest`
- `/api/features/btc/cohort/latest`
- `/api/signals/btc/latest`

No `tier_2_operator` route may be required for `trade_enabled`.

Health rule:

- `/health` is a blocking corroboration input, not a sufficient positive signal by itself
- healthy `/health` alone must never promote the system to `trade_enabled`
- unhealthy or unavailable `/health` may downgrade or halt execution depending on the failure context

Minimum gating dimensions:

- freshness of required tier-1 inputs
- source-health and service-health corroboration
- confidence and anomaly cues carried by tier-1 inputs
- sequence and continuity integrity
- unresolved restatement or quarantine state
- explicit operator stage and kill-switch state

### 4. Startup and Recovery Rules

Minimum execution warmup rules:

- do not allow `trade_enabled` immediately on process start
- require a minimum number of consecutive valid tier-1 reads
- require sequence monotonicity confirmation
- require freshness within SLO for all required inputs

Minimum restart rule:

- after process restart, default to `warming_up` or `observe_only` until the warmup criteria pass again

History and replay rule:

- tier-1 `history` routes may be used as startup and recovery verification aids
- they are not steady-state required inputs for every execution decision
- inability to verify recent continuity during warmup must keep the system in a safe non-trading mode

### 5. Capital Rollout Stages

The contract should support these operator stages:

- `shadow`
- `paper_live`
- `canary_capital`
- `full_capital`

Important rule:

- progression between stages requires explicit operator action plus a validation checklist; it must never happen implicitly

### 6. Preferred Contract Shape

Preferred first-slice route:

- `GET /api/execution/btc/status`

Minimum payload direction:

- `execution_mode`
- `status_reason`
- `compatibility_status`
- `evaluated_at`
- `input_refs`
- `freshness_summary`
- `sequence_summary`
- `restatement_status`
- `operator_stage`

Compatibility transition rule:

- if an older adapter still consumes `STATUS_OK`, `STATUS_LIQUIDATE_ONLY`, or `STATUS_HALT`, the mapping from `execution_mode` must be explicit and documented
- the new `execution_mode` surface remains authoritative

## Acceptance Direction

This spec is complete only when all of the following are true:

1. `NT` can consume one explicit execution decision object
2. the state machine is deterministic and fail-closed
3. startup, restart, and stale-data behavior are frozen
4. new exposure versus risk-reduction behavior is formally separated
