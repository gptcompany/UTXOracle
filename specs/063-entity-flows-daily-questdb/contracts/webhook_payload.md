# Contract: Discord Webhook Aggregated Payload

**Date**: 2026-06-15
**Spec**: [../spec.md](../spec.md)
**Plan**: [../plan.md](../plan.md)
**Owner**: spec-063 (FR-007)
**Reuses**: spec-062 FR-012 helper `_post_discord_failure` (will be generalised in implementation)

## Trigger condition

Exactly one POST per `aggregate_flows()` run, fired iff `failed_rows` is non-empty at end-of-run. Zero POSTs on a fully successful run. Zero POSTs on a run that opens no QuestDB connection (e.g. env var OFF).

## Endpoint

`os.environ["DISCORD_WEBHOOK_URL"]` — same env var spec-062 uses. If unset (or set to a dotenvx-encrypted placeholder like `ENC[...]`), the helper logs a WARNING and skips the POST (matches spec-062 `_post_discord_failure` behaviour).

## Payload schema

```json
{
  "content": ":rotating_light: entity_flows_daily QuestDB write failed for {date_token}: {failed_count} rows failed ({exception_summary})"
}
```

### Field definitions

| Field | Type | Source | Example |
|---|---|---|---|
| `:rotating_light:` (emoji prefix) | literal Discord emoji code | Constant for paging signals | `:rotating_light:` |
| `entity_flows_daily` | literal stream name | Hardcoded; matches `stream_registry.yaml` | `entity_flows_daily` |
| `{date_token}` | ISO date string or range | Computed at end-of-run | `2026-06-15` or `2026-06-13..2026-06-15` |
| `{failed_count}` | integer | `len(failed_rows)` at end-of-run | `47` |
| `{exception_summary}` | qualified class name OR `MultipleFailureClasses` | Most common exception class; if multiple classes observed, the literal `MultipleFailureClasses` is used and per-class breakdown lives in structured ERROR logs | `psycopg.OperationalError` |

### `date_token` derivation rule

- If all failed rows share the same `date`, emit `YYYY-MM-DD`.
- If failed rows span multiple distinct `date` values, emit `min(date)..max(date)` (ISO format, no comma).
- The same rule applies even if only some of the run's dates had failures — the token reflects the failure span, not the run span.

### `exception_summary` derivation rule

- Iterate `failed_rows`; count occurrences of each exception class name.
- If exactly one class is observed, emit its qualified name (`module.ClassName`).
- If two or more distinct classes are observed, emit `MultipleFailureClasses` and rely on the structured ERROR logs for per-class breakdown.

This avoids embedding multi-line text in the Discord payload (which would make the message hard to read in the channel) while still giving the operator a paging-quality signal.

## Worked examples

### Example 1 — single date, single exception class

47 rows failed, all for `date=2026-06-15`, all with `psycopg.OperationalError`:

```json
{
  "content": ":rotating_light: entity_flows_daily QuestDB write failed for 2026-06-15: 47 rows failed (psycopg.OperationalError)"
}
```

### Example 2 — date range, single exception class

3 rows failed for `2026-06-13`, 4 rows failed for `2026-06-14`, 2 rows failed for `2026-06-15`; all `psycopg.OperationalError`:

```json
{
  "content": ":rotating_light: entity_flows_daily QuestDB write failed for 2026-06-13..2026-06-15: 9 rows failed (psycopg.OperationalError)"
}
```

### Example 3 — single date, multiple exception classes

5 rows failed with `psycopg.OperationalError`, 2 rows failed with `psycopg.errors.DataError`, all on `2026-06-15`:

```json
{
  "content": ":rotating_light: entity_flows_daily QuestDB write failed for 2026-06-15: 7 rows failed (MultipleFailureClasses)"
}
```

The per-class breakdown lives in the journal, queryable via `journalctl -u <invoker> | grep entity_flows_daily QuestDB save failed`.

## Failure isolation of the webhook itself

Per spec-062 FR-012 behaviour, the webhook POST itself MUST NOT mask the underlying run state. If `DISCORD_WEBHOOK_URL` is unreachable or returns non-2xx, the helper logs a WARNING and the aggregator run exit code is unchanged (exit code reflects the DuckDB SSOT integrity per FR-002 — DuckDB write succeeded = exit 0 regardless of QuestDB or webhook outcome).

## Test guards (FR-008)

`tests/test_flow_aggregator_questdb.py` MUST include:

1. **Guard d.1 — exactly one POST on failing run**: simulate N rows failing, assert `urllib.request.urlopen` was called exactly once and the URL is `os.environ['DISCORD_WEBHOOK_URL']`.
2. **Guard d.2 — payload schema match**: parse the JSON body, assert `content` matches the regex `^:rotating_light: entity_flows_daily QuestDB write failed for [\d\-\.]+: \d+ rows failed \([\w\.]+\)$`.
3. **Guard d.3 — zero POSTs on successful run**: simulate all rows succeeding, assert `urllib.request.urlopen` was NOT called.
4. **Guard d.4 — date range token**: simulate failures on three distinct dates, assert the payload contains `min(date)..max(date)` not a comma-separated list.
5. **Guard d.5 — multiple exception classes**: simulate two distinct exception classes, assert the payload contains the literal `MultipleFailureClasses`.

## Lifecycle

- spec-063 introduces the aggregated payload format as a refinement of spec-062 FR-012 (which posts one webhook per failure, no aggregation across rows).
- The implementation MAY generalise `_post_discord_failure` to accept the aggregated payload shape, in which case spec-062's per-run usage is preserved (failed_count = 1, exception_summary = its single exception class).
- The follow-up legacy-removal spec will retire this webhook entirely once the QuestDB write half is unconditional — until then it stays.
