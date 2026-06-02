# UTXOracle Consumption Contract — Ready for Adoption (`nautilus_dev`)

**Status**: Code-complete, awaiting operational data backfill.
**Source**: gptcompany/UTXOracle Issue #8 closure, branch `061-stream-consumption-contract`.
**Implementation spec**: `specs/061-stream-consumption-contract/`.
**Target consumer**: `nautilus_dev/strategies/common/flow_discovery/onchain_context.py`.

## What you can adopt today

### 1. Public surface

```http
GET /v1/streams/health HTTP/1.1
Host: utxoracle.internal:8001
Authorization: Bearer <your-jwt>
```

Single authenticated poll. Returns 13 streams + rollup. No pagination,
no cursors, no second roundtrip.

### 2. Response shape

```json
{
  "as_of": "2026-06-02T18:00:00Z",
  "streams": [
    {
      "name": "live_snapshots",
      "last_row_ts": "2026-06-02T17:59:42Z",
      "stale_seconds": 18,
      "sla_seconds": 3600,
      "schema_version": "1.0.0",
      "status": "OK"
    }
    /* ...12 more entries (one per registry stream)... */
  ],
  "overall": "OK"
}
```

Pinned OpenAPI 3.0.3 contract:
[`specs/061-stream-consumption-contract/contracts/streams_health.openapi.yaml`](../specs/061-stream-consumption-contract/contracts/streams_health.openapi.yaml)

### 3. The 13 canonical stream names

These names are **contractual** — pin against them, do not rename.

| # | Stream | SLA | Tier |
|---|---|---|---|
| 1 | `live_snapshots` | 1h | real-time |
| 2 | `whale_transactions` | 1h | event-driven |
| 3 | `mempool_predictions` | 30min | sub-hour |
| 4 | `net_flow_metrics` | 6h | hourly agg |
| 5 | `entity_flows_daily` | 36h | daily |
| 6 | `price_analysis` | 36h | daily |
| 7 | `urpd_features_daily` | 36h | daily |
| 8 | `utxo_snapshots` | 48h | daily |
| 9 | `mvrv_daily` | 48h | daily |
| 10 | `nupl_daily` | 48h | daily |
| 11 | `realized_cap_daily` | 48h | daily |
| 12 | `utxo_lifecycle_full` | tip - 72h | per-block |
| 13 | `backtest_whale_signals` | 168h (7d) | research-batch |

Source-of-truth registry: [`docs/contracts/stream_registry.yaml`](contracts/stream_registry.yaml).

### 4. How to consume it

```python
# strategies/common/flow_discovery/onchain_context.py

import httpx

async def gate_strict_mode_run() -> bool:
    """Returns True iff every onchain stream is fresh enough to trade."""
    async with httpx.AsyncClient(timeout=2.0) as client:
        resp = await client.get(
            f"{UTXO_ORACLE_URL}/v1/streams/health",
            headers={"Authorization": f"Bearer {UTXO_TOKEN}"},
        )
    resp.raise_for_status()
    body = resp.json()
    if body["overall"] != "OK":
        not_ok = [
            (s["name"], s["status"], s["stale_seconds"])
            for s in body["streams"]
            if s["status"] != "OK"
        ]
        log.warning("strict-mode blocked; not-OK streams: %s", not_ok)
        return False
    return True
```

For research-only mode: branch on `overall != "OK"` and tag outputs
with `data_quality: degraded`. Per-stream `stale_seconds` lets you
choose which streams to use vs skip.

### 5. Hard guarantees from the producer

- **No rename**: the 13 names are frozen until a `MAJOR` `schema_version`
  bump on the affected entry, with a 30-day overlap window.
- **No silent staleness**: past-SLA → `status: STALE` with the real
  `stale_seconds`. Unreachable → `status: MISSING` with optional `error`.
- **No fallback to legacy DuckDB**: `overall: OK` strictly means "QuestDB
  has fresh data". Not "we found something somewhere".
- **Idempotent re-reads**: two consecutive polls with the same `as_of`
  instant give the same rollup. Daily aggregates use
  `WAL DEDUP UPSERT KEYS(ts)` — re-runs do not duplicate rows.
- **No in-process cache**: status reflects the live state. Recovery from
  STALE → OK is visible on the next poll, not after a TTL.

### 6. Backend target

QuestDB single-tenant via PG-wire on `:8812`, fronted by the existing
FastAPI surface (`api/main.py`) with the existing `HTTPBearer` auth
dependency. No mixed backends. No partition-layout knowledge required.

Backend rationale: [`specs/061-stream-consumption-contract/decisions.md::D1`](../specs/061-stream-consumption-contract/decisions.md).

### 7. Schema evolution rule (the durable contract)

| Change class | Version bump | Window | Examples |
|---|---|---|---|
| `docs_only` | none | none | edit `notes`, fix link |
| `additive_non_breaking` | none | none | add a column the consumer doesn't pin |
| `additive_pinned` | MINOR | none | promote internal column to `pinned_columns` |
| `behavioral_tightening` | MINOR | 30d if feasible | tighten existing pinned-column semantics |
| **`breaking`** | **MAJOR** | **30d minimum** | rename stream, drop pinned column, change type |

Full policy: [`docs/SCHEMA_VERSIONING.md`](SCHEMA_VERSIONING.md).
Underlying project policy: [`docs/contracts/CHANGE_POLICY.md`](contracts/CHANGE_POLICY.md) (spec-058).

### 8. Special note: `utxo_lifecycle_full` uses a different freshness strategy

This one stream uses **`tip_lag_blocks`**; the other 12 use **`max_ts`**.

Reason: the table's `ts` is row-creation time, not block time, so
`max(ts)` would lie during a backfill (rows created today represent
blocks from months ago). The probe instead computes:

```
stale_seconds = (getblockcount() - max(spent_block | creation_block)) * 600
```

Both `creation_block` AND `spent_block` are checked — the **worst lag**
wins, so a fresh spent-catchup cannot mask a stale creation-catchup.

**The consumer needs no special handling**: `stale_seconds` is reported
in the same units (seconds) as every other stream. You always compare
`stale_seconds <= sla_seconds`.

### 9. Operational status today

| Step | Owner | Status |
|---|---|---|
| QuestDB DDL for all 13 tables | producer | ✅ Live |
| Lifecycle catch-up (164M rows DuckDB → QuestDB) | producer | ⏳ Running (~3h ETA) |
| Creation tip catch-up | producer | ⏳ Queued (post-mirror) |
| Spent backfill `--target-backend questdb` | producer | ⏳ Queued |
| Daily aggregator timer first run | producer | ⏳ Queued (next 02:30 UTC) |
| Acceptance test green (`overall == OK`) | both | ⏳ Blocked on above |

Automation: a watchdog script (`scripts/bootstrap/spec061_post_mirror_chain.sh`)
runs the full chain unattended. It writes terminal state to
`/tmp/spec061_chain.state` and live log to `/tmp/spec061_chain.log`.

### 10. Outstanding tasks blocking adoption

- **Producer side**: none code-level; only the ~3h backfill.
- **Consumer side**: integrate the `/v1/streams/health` poll into
  `onchain_context.py`'s strict-mode entry point. Replace the 13
  direct table reads with one health call.

### 11. Issue tracking

- Producer issue: gptcompany/UTXOracle#8 (closes when acceptance gate green)
- Consumer source PR: gptcompany/nautilus_dev#146 (the contract document)
- Implementation branch: `gptcompany/UTXOracle:061-stream-consumption-contract`
- Decision records: [`specs/061-stream-consumption-contract/decisions.md`](../specs/061-stream-consumption-contract/decisions.md) (D1-D6)
- Spec quickstart: [`specs/061-stream-consumption-contract/quickstart.md`](../specs/061-stream-consumption-contract/quickstart.md)

### 12. TL;DR

**Yes, you can adopt the contract.** The wire shape, registry, and
schema versioning rules are frozen as of branch
`061-stream-consumption-contract`. The only thing not green today is
the live `overall == "OK"` assertion, blocked on the data backfill
running autonomously. Implement against the OpenAPI spec; the gate
will flip green on its own.

### 13. Contact

Open an issue against `gptcompany/UTXOracle` and reference Issue #8.
For real-time questions, ping the channel referenced in the parent PR.

### Appendix — Quick local smoke

```bash
# Verify the contract document hasn't drifted from what you read here
sha256sum specs/061-stream-consumption-contract/contracts/streams_health.openapi.yaml
sha256sum docs/contracts/stream_registry.yaml

# Hit the route locally once the API is up
curl -s -H "Authorization: Bearer $UTXO_TOKEN" \
  http://localhost:8001/v1/streams/health | jq .overall
```
