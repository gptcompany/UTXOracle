# spec-043 Operator Runbook

## Purpose

This runbook explains how to enable and observe the current Nautilus integration slice safely.

The current slice is limited to:

- polling client
- contract normalization
- safety gating
- replay
- `shadow_read` and `paper_trade` adapter modes

It does not approve live order routing.

## Preconditions

Before enabling the adapter:

1. confirm `8011` is healthy
2. confirm spec-042 chart validation surface is healthy enough for operator trust
3. confirm the tradable contract in `tradable-contract.md` still matches the live snapshot schema
4. confirm the test suite below is green

Recommended verification:

```bash
uv run pytest -q tests/test_nautilus_live_integration.py tests/test_live_models.py
```

## Shadow-Read Bring-Up

Use `shadow_read` first.

Expected behavior:

- snapshots are polled from `GET /api/v1/live/snapshot`
- decisions are logged
- no order-routing side effects happen

Operator checklist:

1. verify the adapter is configured for `shadow_read`
2. verify decision logs are present
3. verify `STATUS_OK`, `STATUS_LIQUIDATE_ONLY`, and `STATUS_HALT` reasons are intelligible
4. verify no external trading action is triggered

## Replay Validation

Replay is used to validate deterministic behavior against recent history.

Operator checklist:

1. replay recent `live/history`
2. verify ordering is ascending
3. confirm stale/confidence/anomaly cases map to the expected gate states
4. archive the decision log if the run is used as evidence

## Kill-Switch Procedure

When risk is unclear or the environment is unstable:

1. activate operator kill-switch
2. verify the adapter emits no tradable result
3. verify decision reason is `operator_kill_switch`
4. keep the adapter in fail-closed mode until the incident is understood

## Manual Reset Procedure

`STATUS_HALT` is latched.

Do not resume operation by waiting for healthy snapshots alone.

Required operator flow:

1. identify the halt reason in the decision log
2. confirm the underlying cause is resolved
3. perform manual reset
4. observe the next decisions before trusting the adapter again

Examples that require manual reset:

- timestamp monotonicity failure
- backward block movement
- hard anomaly breach
- required source not healthy
- hard freshness breach

## Paper Trading Preconditions

Paper trading is not approved until:

- upstream `sequence_id` exists
- the adapter consumes and validates that field
- shadow-read has already been stable
- kill-switch and manual reset procedures have been exercised successfully

## Current Non-Goals

This runbook does not cover:

- live execution routing
- exchange adapter behavior
- position sizing or liquidation strategy logic
- direct QuestDB or Parquet consumption by Nautilus

