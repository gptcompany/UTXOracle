# spec-043 Rollout Order

## Intent

The Nautilus integration must be introduced in controlled stages.

The first implementation slice is not approved for live trading.
It is approved only for:

- offline validation
- replay validation
- shadow-read mode
- paper-trading preparation

## Rollout Sequence

### Stage 0: Offline Contract Validation

Required before any operator runtime use:

- spec-041 remains the only production boundary on `8011`
- spec-042 validation remains green for the admitted chart surface
- `uv run pytest -q tests/test_nautilus_live_integration.py`
- tradable contract freeze in `tradable-contract.md` is still accurate

Exit criteria:

- normalization, gates, replay, and kill-switch tests are green
- no unresolved findings against the current first slice

### Stage 1: Shadow-Read Mode

Adapter mode:

- `shadow_read`

Behavior:

- poll `GET /api/v1/live/snapshot`
- evaluate gate state
- log decisions
- emit no order-routing side effects

Required operator checks:

- verify decision logs are being written
- verify `STATUS_HALT` remains latched until manual reset
- verify kill-switch forces `STATUS_HALT`
- verify monotonicity failures halt the adapter

Exit criteria:

- shadow-read stays stable over a meaningful runtime window
- no unexplained `STATUS_OK` decisions during known degraded inputs
- no accidental trading side effects exist

### Stage 2: Replay Validation

Behavior:

- replay recent `live/history`
- confirm deterministic ordering and gate outcomes
- compare decision patterns against expected degraded/healthy scenarios

Required operator checks:

- replayed snapshots preserve order
- borderline stale/confidence paths produce `STATUS_LIQUIDATE_ONLY`
- anomaly and monotonicity paths produce `STATUS_HALT`

Exit criteria:

- replay output is deterministic
- decision reasons are reviewable and consistent

### Stage 3: Paper Trading

Precondition:

- upstream `sequence_id` exists and is integrated

Adapter mode:

- `paper_trade`

Behavior:

- the adapter may feed Nautilus paper logic
- no live order submission is allowed

Required operator checks:

- `sequence_id` is present and monotonic
- kill-switch path is tested in paper mode
- manual reset path after `STATUS_HALT` is exercised

Exit criteria:

- paper session runs without contract drift
- safety gates produce expected state transitions

### Stage 4: Controlled Live Enablement

Not admitted by the current slice.

This requires a follow-on approval after:

- upstream `sequence_id`
- explicit live order-routing design
- operator runbook sign-off
- separate validation of live execution controls

## Kill-Switch Policy

The kill-switch must be checked before any snapshot is admitted as tradable.

When active:

- no tradable payload is emitted
- adapter result is fail-closed
- decision log reason must be `operator_kill_switch`

## Manual Reset Policy

If the adapter reaches `STATUS_HALT`:

- it stays halted
- subsequent healthy snapshots are insufficient by themselves
- operator reset is required before resuming normal evaluation

This is mandatory for:

- monotonicity failures
- anomaly hard failures
- hard freshness failures
- required-source unhealthy failures

