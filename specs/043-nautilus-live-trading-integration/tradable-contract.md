# spec-043 Tradable Contract Freeze

## First Admitted Integration Mode

The first admitted integration mode is:

- polling-only
- source endpoint: `GET /api/v1/live/snapshot` on `8011`
- scope: shadow-read and offline adapter validation first

No streaming transport is admitted in the first slice.
No direct QuestDB or Parquet consumption is admitted in this spec slice.

Those may become the preferred paths for `nautilus_dev`, but they are follow-on consumer choices, not the first contract freeze inside this repository.

## Tradable Field Whitelist

The first admitted tradable field set is intentionally small.

### Live API-produced fields

- `schema_version`
- `timestamp`
- `block_height`
- `utxoracle_price`
- `utxoracle_confidence`
- `mempool_exchange_price`
- `comparison.utxo_vs_mempool_bps`
- `source_health.electrs.status`
- `source_health.utxoracle.status`
- `source_health.mempool_api.status`
- `source_timestamps.electrs`
- `source_timestamps.utxoracle`
- `source_timestamps.mempool_api`

### Adapter-derived fields

- `source_spread_bps`
  - formula: `abs(comparison.utxo_vs_mempool_bps)`
- `status`
  - one of `STATUS_OK`, `STATUS_LIQUIDATE_ONLY`, `STATUS_HALT`
- `decision_reason`
  - explicit acceptance or rejection reason for audit logging

### Explicitly not admitted in the first slice

- `features.*`
- `hyperliquid_*`
- `comparison.utxo_vs_hl_oracle_bps`
- `comparison.utxo_vs_hl_mark_bps`
- any whale or legacy metric routes

These remain research-only until a later slice declares them tradable.

## Missing Field Decisions

### `sequence_id`

Decision:

- `sequence_id` is **not** derived in-adapter in the first slice
- shadow-read mode may proceed without it
- paper trading and live enablement are blocked until `sequence_id` is added upstream to the live contract

Reason:

- timestamp alone is usable as a hard monotonicity gate for the first shadow-read slice
- a synthetic adapter-derived sequence would risk encoding polling behavior rather than producer truth

### `source_spread_bps`

Decision:

- `source_spread_bps` is admitted as an adapter-derived field
- formula: `abs(comparison.utxo_vs_mempool_bps)`

Reason:

- the first tradable slice admits mempool as the only required reference source
- the formula is deterministic, simple, and testable from already admitted upstream fields

## Safety Gates

### Freshness

- `snapshot_age_seconds <= 15` -> candidate for `STATUS_OK`
- `15 < snapshot_age_seconds <= 30` -> `STATUS_LIQUIDATE_ONLY`
- `snapshot_age_seconds > 30` -> `STATUS_HALT`

### Source Health

Required healthy sources for admitted trading consumption:

- `electrs`
- `utxoracle`
- `mempool_api`

Policy:

- all three healthy -> gate may pass
- any required source `degraded`, `stale`, or `unavailable` -> `STATUS_HALT`

### Confidence

- `utxoracle_confidence >= 0.75` -> candidate for `STATUS_OK`
- `0.60 <= utxoracle_confidence < 0.75` -> `STATUS_LIQUIDATE_ONLY`
- `utxoracle_confidence < 0.60` or missing -> `STATUS_HALT`

### Anomaly

Using `source_spread_bps = abs(comparison.utxo_vs_mempool_bps)`:

- `source_spread_bps <= 100` -> candidate for `STATUS_OK`
- `100 < source_spread_bps <= 250` -> `STATUS_LIQUIDATE_ONLY`
- `source_spread_bps > 250` or missing -> `STATUS_HALT`

## Monotonicity Policy

### Hard gates

- `timestamp` must move forward strictly

If a snapshot timestamp is equal to or older than `last_seen_timestamp`, the adapter must fail closed with `STATUS_HALT`.

### Soft gate

- `block_height` is soft-monotonic

Policy:

- forward movement is accepted
- same height is accepted
- backward movement defaults to `STATUS_HALT`
- any future re-org mode must be explicit and operator-approved

### `sequence_id`

Because upstream `sequence_id` does not yet exist:

- it is not part of the first shadow-read admission
- it becomes a prerequisite before paper/live rollout

## Recovery Policy

- `STATUS_HALT` requires manual operator reset in the first slice
- `STATUS_LIQUIDATE_ONLY` may auto-recover to `STATUS_OK` only after `3` consecutive healthy snapshots

## Kill-Switch

The adapter must support an operator kill-switch.

When the kill-switch is active:

- no tradable snapshot may be emitted
- effective adapter state is always `STATUS_HALT`

