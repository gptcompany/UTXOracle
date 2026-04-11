# spec-057: Data Quality, Reconciliation, and Restatement

> **Status**: DRAFT
> **Priority**: CRITICAL
> **Effort**: Large
> **Created**: 2026-04-10

## Problem Statement

`UTXOracle` already has meaningful source-of-truth decisions and bounded contracts, but it still lacks the formal data-governance layer required for real-capital execution:

1. what counts as valid versus suspect data
2. how divergence between sources is handled
3. when a value is quarantined
4. how historical corrections are recorded
5. how corrected data affects downstream execution safety

Without this spec, the service can still "work" while silently serving data that should have blocked or degraded execution.

## Goals

1. define a small data-quality state model
2. define validation and reconciliation checkpoints across ingest, materialization, and serving
3. define divergence and quarantine behavior
4. define historical restatement semantics
5. define how data-quality events feed execution safety

## Non-Goals

- claiming perfect market truth
- rebuilding every metric from multiple independent vendors
- turning the repo into a generic data-governance platform

## Dependencies

- [specs/054-production-boundary-and-surface-tiering/spec.md](/media/sam/1TB/UTXOracle/specs/054-production-boundary-and-surface-tiering/spec.md)
- [docs/FEATURE_DEPENDENCY_MATRIX.md](/media/sam/1TB/UTXOracle/docs/FEATURE_DEPENDENCY_MATRIX.md)
- [specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md](/media/sam/1TB/UTXOracle/specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md)
- [specs/055-nt-execution-safety-contract/spec.md](/media/sam/1TB/UTXOracle/specs/055-nt-execution-safety-contract/spec.md)
- [specs/056-service-slo-freshness-and-capacity/spec.md](/media/sam/1TB/UTXOracle/specs/056-service-slo-freshness-and-capacity/spec.md)

Primary references:

- [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)
- [docs/FEATURE_DEPENDENCY_MATRIX.md](/media/sam/1TB/UTXOracle/docs/FEATURE_DEPENDENCY_MATRIX.md)
- [docs/contracts/feature_provenance_manifest.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_provenance_manifest.yaml)

Implementation entry points likely to be touched later:

- [api/questdb_repository.py](/media/sam/1TB/UTXOracle/api/questdb_repository.py)
- [scripts/live/storage.py](/media/sam/1TB/UTXOracle/scripts/live/storage.py)
- [scripts/live/bundle_writer.py](/media/sam/1TB/UTXOracle/scripts/live/bundle_writer.py)
- [scripts/live/signal_writer.py](/media/sam/1TB/UTXOracle/scripts/live/signal_writer.py)

## Current Baseline

The repo already has:

- source-of-truth ownership decisions
- bundle and signal materialization
- degraded and misconfigured semantics
- optional historical replay via `history` endpoints

What it does not yet have is a formal quality-control and correction model.

Important baseline limitation:

- the source-of-truth manifest already tells the repo which source owns a metric
- it does not yet tell the service how to react when observed values diverge, regress, or require correction

## Design

### 1. Data Quality States

This spec introduces one bounded quality model with four terms:

- `valid`
- `suspect`
- `quarantined`
- `restated`

Meaning:

- `valid`
  - safe to serve normally
- `suspect`
  - anomaly detected; may still be visible but cannot silently pass as normal
- `quarantined`
  - not valid for execution use
- `restated`
  - previously published data was corrected after the fact

Important modeling rule:

- `valid`, `suspect`, and `quarantined` describe the current evaluation state of an artifact or serving decision
- `restated` is a correction overlay or artifact status attached to previously published data; it is not a replacement for the current runtime quality state
- a latest artifact may therefore be `valid` today while still referencing a prior `restated` correction event historically

### 2. Validation Layers

Minimum validation layers:

1. ingest validation
2. materialization validation
3. serve-time validation

Examples:

- missing required fields
- timestamp regressions
- impossible numeric ranges
- broken monotonic sequence behavior
- upstream divergence beyond allowed thresholds

### 3. Reconciliation Direction

Reconciliation should compare:

- local canonical values versus declared upstream references where relevant
- current artifacts versus prior artifacts for regression detection
- tier-1 latest payloads versus recent history continuity

Reconciliation must follow declared source ownership:

- if a field is `local_canonical`, upstream disagreement is a reference signal, not automatic proof of corruption
- if a field is `adopt_from_brk`, divergence from the adopted upstream is materially more serious
- disagreement handling must follow the metric source-of-truth manifest rather than ad hoc operator intuition

The first slice should prioritize the fields most directly tied to execution:

- live snapshot timestamps and price fields
- bundle sequence integrity
- signal freshness and completeness

### 4. Restatement Model

When historical data must be corrected, the system should emit an explicit restatement artifact rather than mutating history silently.

Minimum restatement fields:

- `restatement_id`
- `issued_at`
- `affected_surface`
- `affected_time_range`
- `severity`
- `reason`
- `supersedes_ref`

### 5. Execution Coupling

This spec feeds [spec-055](/media/sam/1TB/UTXOracle/specs/055-nt-execution-safety-contract/spec.md) through one simple rule:

- `quarantined` or unresolved critical `restated` tier-1 data cannot coexist with `trade_enabled`

Additional coupling rule:

- `suspect` tier-1 data must never remain execution-equivalent to `valid` by omission; it must either downgrade execution explicitly or be explicitly allowlisted by a written rule

## Acceptance Direction

This spec is complete only when all of the following are true:

1. tier-1 data has an explicit quality state model
2. reconciliation checks exist at the right stages
3. historical corrections are explicit and auditable
4. data-quality failures map cleanly into execution consequences
