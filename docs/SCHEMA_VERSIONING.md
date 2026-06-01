# Stream Consumption Contract - Schema Versioning

**Scope**: the 13 consumer-facing onchain streams declared in
`docs/contracts/stream_registry.yaml` and exposed via
`GET /v1/streams/health`. Authored by spec-061 to satisfy FR-009.

This document specializes the project-wide change policy in
`docs/contracts/CHANGE_POLICY.md` (spec-058). It restates the rules in
terms of the stream registry surface and the consumer
(`nautilus_dev/strategies/common/flow_discovery/onchain_context.py`).
When in doubt, the project-wide policy wins.

## Scope of the Version

Every entry in `stream_registry.yaml` carries a
`schema_version: MAJOR.MINOR.PATCH` field. All 13 baseline streams start
at `1.0.0`. The version is the contract of:

- the columns named in `pinned_columns`;
- their semantic meaning: units, encoding, and null-vs-missing convention;
- the freshness strategy (`max_ts` vs `tip_lag_blocks`) and its probe
  column (`timestamp_column` or `block_column`);
- the rollup behaviour in `GET /v1/streams/health`: status enum and
  `overall` semantics.

The version is not the contract of:

- `sla_seconds`: SLA tuning is a config knob, not a schema change;
- `notes` and `source_spec`: documentation;
- internal columns the consumer does not pin.

## Change Classes Per Stream

Each PR that touches `stream_registry.yaml` or a backing table must label
the change in the commit message and PR description.

| Class | Examples | Version bump | Window |
|---|---|---|---|
| `docs_only` | edit `notes`, fix `source_spec` link | none | none |
| `additive_non_breaking` | add a QuestDB column the consumer does not pin; add a new stream entry | none for existing entries; new entry starts at `1.0.0` | none |
| `additive_pinned` | promote an internal column to `pinned_columns` | MINOR bump on the affected entry | none; consumer adoption is opt-in |
| `behavioral_tightening` | tighten the semantics of an existing pinned column; change freshness strategy without changing the SLA | MINOR bump on the affected entry | 30 days during which both old and new semantics are served if feasible; otherwise consumer signoff is required |
| `breaking` | rename a stream; remove, rename, or retype a pinned column; rename a backing table; switch backend, for example QuestDB to REST | MAJOR bump with a new side-by-side entry | 30 days minimum (FR-009) |

## Worked Example: Promoting `realized_cap_daily` to v2

Suppose we want to rename the pinned column `realized_cap` to
`realized_cap_usd` to disambiguate the unit. That is a breaking change.
The migration ships in two PRs.

### PR 1 - Introduce v2 Side-by-Side (Day 0)

1. Create the new backing table `realized_cap_daily_v2` with the renamed
   column. Add its DDL to
   `api/questdb_repository.py::create_tables_if_not_exist`.
2. Wire the producer to dual-write to both tables.
3. Edit `docs/contracts/stream_registry.yaml`:

```yaml
- name: realized_cap_daily
  table: realized_cap_daily
  freshness_strategy: max_ts
  timestamp_column: ts
  schema_version: "1.0.0"
  sla_seconds: 172800
  source_spec: specs/040
  pinned_columns: [ts, realized_cap]
  deprecated_at: "2026-08-01"
  notes: Deprecated; migrate to realized_cap_daily_v2 by 2026-08-31.

- name: realized_cap_daily_v2
  table: realized_cap_daily_v2
  freshness_strategy: max_ts
  timestamp_column: ts
  schema_version: "2.0.0"
  sla_seconds: 172800
  source_spec: specs/040
  pinned_columns: [ts, realized_cap_usd]
  notes: v2 renames realized_cap to realized_cap_usd for unit clarity.
```

The current registry schema requires unique `name` values, so the v2
entry uses a distinct stream name. If the contract later moves to
uniqueness by `(name, schema_version)`, this example can be updated, but
until then the side-by-side version must be a distinct registry entry.

4. The `/v1/streams/health` endpoint returns both entries. The consumer
   sees v1 with `deprecated_at` set and v2 as the fresh migration target.

### PR 2 - Retire v1 (Day 30+)

After at least 30 days of overlap during which the consumer has cut over:

1. Remove the v1 entry from `stream_registry.yaml`.
2. Drop the v1 backing table, or keep it for historical replay if the
   owning spec requires it.
3. Remove the producer's dual-write code path.

The 30-day window is the floor, not the ceiling. The consumer team may
ask for longer, in which case the planned removal date moves later.

## Registry Edit Workflow

Use the workflow from
`specs/061-stream-consumption-contract/quickstart.md`, section
`Edit the contract (the right way to change a stream)`:

1. Edit `docs/contracts/stream_registry.yaml`.
2. For breaking changes, keep the old entry, set `deprecated_at`, and add
   the new side-by-side entry.
3. Run the registry and endpoint tests before merge:

```bash
uv run pytest tests/test_stream_registry.py tests/test_streams_health.py -q
```

## What This Document Does Not Cover

- Producer internals: how a metric is computed can change as long as the
  pinned-column semantics remain stable.
- Storage backend choice for individual streams: a cross-cutting backend
  decision belongs in `decisions.md`, not in a per-stream schema bump.
- `sla_seconds` tuning: changing an SLA does not bump `schema_version`,
  but it should be communicated to the consumer team.

## Review Checklist

When reviewing a PR that touches `docs/contracts/stream_registry.yaml`,
verify:

- [ ] Is the change class named in the PR body?
- [ ] If `breaking`, is the new entry added side-by-side with the old
      one, and does the old entry carry `deprecated_at`?
- [ ] If `breaking`, is the deprecation window at least 30 days from
      `deprecated_at` to the planned removal date?
- [ ] If a stream is being renamed, is the old name retained with
      `deprecated_at` set and the new entry added separately?
- [ ] If a column is removed from `pinned_columns`, is the change a
      breaking MAJOR bump with overlap?
- [ ] Does the `nautilus_dev` consumer team have visibility on this
      change through an issue link, PR link, or handoff note?
- [ ] Are `tests/test_stream_registry.py::test_stream_names_frozen` and
      `tests/test_streams_health.py::test_schema_version_echoed_in_response`
      still green?

## References

- `docs/contracts/CHANGE_POLICY.md`: project-wide schema policy (spec-058)
- `docs/contracts/feature_contract_registry.yaml`: feature-level contracts
- `specs/061-stream-consumption-contract/spec.md`: FR-005, FR-006, FR-009
- `specs/061-stream-consumption-contract/quickstart.md`: registry edit workflow
- `gptcompany/nautilus_dev` PR #146: source contract document
- `gptcompany/UTXOracle` Issue #8: closure checklist
