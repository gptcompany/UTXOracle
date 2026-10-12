# Contract: Environment Variables

**Date**: 2026-06-15
**Spec**: [../spec.md](../spec.md)
**Plan**: [../plan.md](../plan.md)

## `SPEC063_QUESTDB_WRITE` — pilot rollback toggle

**Owner**: spec-063
**Default**: ON (when the variable is unset, the value is treated as ON)
**Type**: string, case-insensitive, whitespace-trimmed at parse time
**Producer**: operator (set in systemd `EnvironmentFile`, shell `export`, or Docker `--env`)
**Consumer**: `scripts/live/flow_aggregator.py::_should_write_questdb()` helper

### Parser contract

```python
def _should_write_questdb() -> bool:
    """Return False iff SPEC063_QUESTDB_WRITE is one of the OFF tokens.

    OFF tokens (case-insensitive, trimmed): '0', 'false', 'no'.
    Anything else, including unset, is ON.
    """
    raw = os.environ.get("SPEC063_QUESTDB_WRITE")
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no"}
```

### Behaviour table

| `SPEC063_QUESTDB_WRITE` value | Parsed by `_should_write_questdb()` | Result |
|---|---|---|
| (unset) | `None` → True | QuestDB write half is ENABLED |
| `""` (empty string) | trim → `""` → True | QuestDB write half is ENABLED (empty does not match any OFF token) |
| `1` / `true` / `yes` / `on` | not in OFF tokens → True | ENABLED |
| `0` | in OFF tokens → False | DISABLED |
| `false` / `FALSE` / `False` / `  false  ` | trim+lower → `false` → in OFF tokens → False | DISABLED |
| `no` / `NO` / `No` | trim+lower → `no` → in OFF tokens → False | DISABLED |
| `disable` / `off` / `nope` | not in OFF tokens → True | ENABLED (silent rejection — operator must use canonical token) |

The intentional asymmetry (only three tokens accepted as OFF, anything else means ON) is documented in Clarify Q1 rationale: typos like `Falsey` or `disable` won't silently leave the producer in OFF state.

### Test contract (FR-008 guard)

`tests/test_flow_aggregator_questdb.py` MUST include:

1. **Parser table-driven test**: exercise all rows in the behaviour table above, assert the boolean output matches column 3.
2. **Connection-open guard**: with the env var set to `0`, invoke `aggregate_flows()` and assert no QuestDB connection is opened (mock `_open_pg_sync` and assert it was not called).
3. **DuckDB integrity under OFF**: with the env var OFF, the DuckDB write count returned by `aggregate_flows()` equals the run without spec-063 (no regression).

### Lifecycle

- **Pilot phase** (spec-063 active): default ON in production, OFF available as rollback per the runbook in [../quickstart.md](../quickstart.md).
- **7-day green gate** (SC-005): operator observes `/v1/streams/health` for `entity_flows_daily` reporting OK at every poll.
- **Legacy removal follow-up spec**: once the gate is green, a separate spec removes the env var entirely (making the QuestDB write unconditional). The follow-up spec MUST keep the OFF tokens accepted for one release cycle to allow a graceful operator transition — they become no-ops that emit a deprecation WARNING.
