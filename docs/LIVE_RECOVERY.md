# Live snapshots recovery (#89)

The producer uses Electrs HTTP, not the legacy ZMQ listener. A running worker
container and HTTP 200 from `/health` do not establish freshness: inspect the
JSON status and QuestDB timestamp. The market cadence is declared by
`LIVE_MARKET_INTERVAL_SECONDS` in Compose (default 5 seconds).

## Observed on Dell, 2026-11-14 UTC

| Observation | Evidence |
|---|---|
| Live database | Host PG 9912 / HTTP 9900; 629247 rows; max(ts) 2026-09-16T05:34:17.923244Z |
| Mirror database | Host PG 8812 / HTTP 9000; 844121 rows; same max(ts) |
| Last valid payload | 2026-09-16T05:33:41.847236Z; JSON parsed successfully |
| Corrupt payload | 05:33:53.870915Z; 1844 bytes, 1536 NUL bytes, JSON fails at offset 308; comparison/source health also contain NULs |
| Empty tail | 05:34:05.893251Z and 05:34:17.923244Z; snapshot_json and source_health_json empty |
| Worker startup | 2026-11-04T12:39:46Z: hydration fails with JSON decoding error |
| Electrs before operator recovery | Exited 139, FinishedAt 2026-11-04T11:24:59.071525548Z; HTTP 3002 refused |
| Crash | lookup-txo thread panic: RocksDB pread of txstore/066138.sst returned Input/output error |
| Subsequent mount cycle | systemd mount inactive 12:22:07Z, active 12:27:11Z, Result success |
| API | HTTP 200, status unavailable, live health check failed, last_success null |

The crash preceded the recorded mount cycle by 57 minutes. These observations
prove the current failure path, not the original September event or persistent
RocksDB corruption. No database writes or service restarts were used in diagnosis.
No bitcoind RPC credentials or ZMQ topic values were read.

The store walks backward from the latest row until a payload passes JSON and
LiveSnapshot schema validation, logging each rejected timestamp without payloads.
History rejects and logs invalid rows too; no corrupt fields are used. At startup the worker
hydrates from that state; existing carry-forward logic marks missing oracle data
stale and excludes it from comparisons. An unverifiable Electrs tip does the same for a price
read at the last known block: it is never healthy and never compared with the current market.
Without any valid state or a fresh oracle
price the worker still declines to publish a fabricated price.
If the initial store read fails, the worker retries while it has no snapshot.
The retry delay starts at the smaller of the configured block-poll and market
intervals, doubles after each attempt, and is capped at the market interval.
There are no additional timing settings. Health remains unavailable without a
snapshot, and stale/degraded for recovered prices while sources remain down.
Malformed timestamp objects and source timestamp arrays are schema errors;
latest/history discard them with the same timestamp-only warning.

## Operator recovery (B5 only, after review)

1. Confirm the cold volume is mounted and readable. Do not delete the index.
   First try `docker start mempool-electrs`; this requires no reindex decision.
2. Inspect `docker inspect mempool-electrs` state and `docker logs --tail 100
   mempool-electrs` for new panics or RocksDB errors. Read-only HTTP checks:
   `curl --fail http://127.0.0.1:3002/blocks/tip/height` and
   `/block-height/{height}` must succeed; height must catch up to the existing
   node. A repeated failure on the same SST needs a separate storage/index
   recovery decision. Recovery duration cannot be inferred from a single I/O
   error; measure index progress after startup before estimating reindex time.
3. Install the reviewed SHA in the owning checkout using the deployment process;
   confirm its diff is empty. The existing owning unit deploy command is
   `systemctl reload utxoracle-live-compose.service` (ExecReload runs
   `docker compose -f /data/sata/1TB/UTXOracle/docker-compose.live.yml up -d --build`).
   Run with operator privileges; never print or copy the environment file.
4. On live HTTP 9900, compare `SELECT max(ts) FROM live_snapshots` before and
   after consecutive declared producer cycles. Require advancement, nonempty
   latest payload, and successful `/api/v1/live/snapshot` JSON validation.
   A stale carried price is not proof that Electrs recovered: require healthy
   electrs/oracle source status and a current block height separately.
5. After the mirror's declared one-minute cycle, require its maximum timestamp
   to advance too. `/health` must expose the actual source state rather than
   only HTTP success. Compare UTC timestamps; the inspected maxima were identical,
   so no seven-hour correction is justified by these observations.

Rollback the code with a reviewed revert and the same owning unit deployment.
Rollback does not repair the cold volume or index. Never truncate live history
as a recovery technique.
