# spec-043: Nautilus Trader Live Integration

> **Status**: DRAFT
> **Priority**: HIGH
> **Effort**: Medium
> **Created**: 2026-03-31

## Problem Statement

The repository now has a working live snapshot contract, but no production-ready integration path for Nautilus Trader.

Current gaps:

1. there is no dedicated Nautilus adapter or client package
2. the live contract is HTTP-first and not yet shaped as a streaming or replay-friendly market data integration
3. freshness, anomaly, and fail-safe rules for trading consumption are not yet formalized
4. the repository does not yet define which fields are safe to trade on versus which fields are research-only

This spec defines a controlled integration layer for Nautilus Trader on top of the QuestDB-backed production API delivered by spec-041 and the validation confidence from spec-042.

## Goals

1. provide a stable Nautilus-compatible data integration path
2. formalize freshness and anomaly gates for live trading consumption
3. define the minimal tradable contract instead of exposing the whole repo surface
4. support paper trading and controlled live rollout

## Non-Goals

- strategy design
- exchange execution adapters
- automated leverage or risk sizing logic
- exposing every research metric directly into Nautilus

## Dependencies

- requires spec-041 for clean production boundary and QuestDB-backed API
- should consume validation outputs from spec-042 where useful

## Design

### 1. Tradable Contract

Define a minimal, versioned trading contract derived from the live service.

Recommended initial payload classes:

- sequence id
- canonical oracle price
- reference prices
- deviation bps
- source spread bps
- source freshness
- source health
- confidence

Every admitted field MUST have an explicit ownership model:

- produced directly by the production live API contract, or
- deterministically derived inside the Nautilus adapter from admitted live fields with documented formulas and tests

Fields with no declared producer MUST NOT be part of the tradable contract.

Current repo reality: the live snapshot contract currently exposes timestamp, block height, prices, comparison fields, feature fields, source health, and source timestamps, but it does not yet expose `sequence_id` or `source_spread_bps`. One of the first deliverables of this spec is to decide whether those fields are added upstream or derived in-adapter.

Anything not explicitly admitted as tradable remains research-only.

### 2. Integration Mode

Support at least one deterministic integration mode for Nautilus:

- polling adapter against `GET /api/v1/live/snapshot`

Optional follow-up:

- push transport such as WebSocket or SSE for lower latency

### 3. Trading Gates

The Nautilus integration MUST enforce:

- maximum snapshot age
- monotonic timestamp and block progression
- allowed deviation bounds
- minimum source health requirements
- minimum confidence requirements
- circuit breaker behavior when data becomes stale, unavailable, or anomalous

### 4. Replay and Paper Trading

The integration should support:

- paper trading mode
- replay or backfill from recent QuestDB-backed history
- deterministic logging of accepted vs rejected trading signals

The adapter MUST track:

- `last_seen_timestamp`
- `last_seen_block_height`
- `last_seen_sequence_id`

and MUST reject any snapshot that moves backward on hard monotonicity signals. Backward `block_height` movement MUST follow the explicit re-org policy below.

Monotonicity policy:

- `sequence_id` and `timestamp` are hard monotonicity gates
- `block_height` is a soft monotonicity gate so the adapter can support explicit re-org handling policies without silently accepting inconsistent data
- if block height moves backward, the default behavior MUST be fail-closed unless an operator-approved re-org handling mode is active

### 5. Rollout Policy

Rollout order:

1. offline adapter tests
2. paper trading in Nautilus
3. shadow/live-read mode without order submission
4. controlled live trading enablement

### 6. Kill-Switch and Recovery

The integration MUST support an operator kill-switch.

Minimum operational states:

- `STATUS_OK`
- `STATUS_LIQUIDATE_ONLY`
- `STATUS_HALT`

Required behavior:

- stale or operator-disabled data emits `STATUS_HALT`
- low-confidence or borderline anomaly conditions emit `STATUS_LIQUIDATE_ONLY`
- recovery behavior MUST be explicit: either manual reset or automatic resume after a configured number of consecutive healthy snapshots

## Functional Requirements

### FR1: Versioned Nautilus Contract

The repository MUST define a minimal, versioned payload or adapter contract for Nautilus Trader.

### FR2: Accepted Field Set

Only explicitly approved fields may be used by the Nautilus adapter for trading decisions.

Each admitted field MUST declare whether it is produced by the live API or deterministically derived inside the adapter.

### FR3: Freshness Gate

The adapter MUST reject snapshots older than the configured freshness threshold.

### FR4: Health Gate

The adapter MUST reject snapshots when required sources are degraded or unavailable.

### FR5: Anomaly Gate

The adapter MUST reject snapshots when deviation or price behavior breaches configured anomaly thresholds.

### FR6: Monotonicity Gate

The adapter MUST track timestamp, block height, and sequence progression.

`sequence_id` and timestamp MUST be treated as hard monotonicity gates.

`block_height` MUST be treated as a soft monotonicity gate to allow explicit re-org handling policies, but backward block movement MUST still fail closed by default unless operator-approved handling is enabled.

### FR7: Replay Support

The adapter MUST support recent history replay for paper trading and diagnostics.

### FR8: Auditability

The integration MUST log why each snapshot was accepted, rejected, or downgraded.

### FR9: Kill-Switch

The integration MUST support an operator-controlled kill-switch that causes the adapter to fail closed.

### FR10: Recovery Policy

The integration MUST define how `STATUS_HALT` and `STATUS_LIQUIDATE_ONLY` recover back to normal operation.

## Success Criteria

| Criterion | Target |
|----------|--------|
| Adapter exists | Nautilus can consume the live contract without BRK-specific logic |
| Safety | stale/anomalous snapshots are rejected deterministically |
| Monotonicity | snapshots never move backward without explicit rejection |
| Rollout | paper trading mode works before live enablement |
| Auditability | accepted vs rejected decisions are logged and reviewable |
| Scope control | only minimal tradable fields are used |

## Risks

| Risk | Mitigation |
|------|------------|
| Trading on research-grade fields | whitelist tradable fields explicitly |
| Snapshot instability across blocks | anomaly gate and confidence gate |
| Upstream freshness mismatch | enforce stricter thresholds in adapter than in generic API |
| Hidden dependency on old endpoints | adapter only uses the post-spec-041 production contract |
