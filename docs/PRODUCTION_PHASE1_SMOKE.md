# Production Phase 1 Smoke

Spec: `spec-061` Phase 1 + Phase 1.5-v2.
Branch: `061-stream-consumption-contract`.
Latest verification date: 2026-06-05.

## Verdict

| Area | Result | Notes |
| --- | --- | --- |
| Phase 1 supervisor units | PASS | Creation and spent services still verify and keep the Discord failure hook. |
| Phase 1.5 original DuckDB timers | REVOKED | Revoked 2026-06-04. The old service definitions scheduled DuckDB writers and must not be installed. |
| Phase 1.5-v2 QuestDB timers | PASS | The installable service files now point to QuestDB-native writer modules. |
| QuestDB source tables | PASS | `block_heights` and `daily_prices` exist with `walEnabled=True`, `dedup=True`. |
| Writer smoke | PASS | Both v2 writers advanced QuestDB max markers without opening DuckDB. |
| Aggregator smoke | PARTIAL | `--questdb-reads --questdb-only` emitted `mvrv_daily`, but still opened DuckDB read-only for `utxo_lifecycle_full` until spec-062. |
| Full schema bootstrap test | PASS with scoped test | `tests/test_create_tables_ddl.py` validates live table state and directly validates Phase 1.5-v2 DDL; the monolithic live bootstrap is intentionally not invoked because it hangs on pre-existing schema DDL on this host. |

## Superseded Phase 1.5

The previous Phase 1.5 sign-off is revoked as of 2026-06-04.

Superseded files:

- `utxoracle-block-heights-catchup.service` formerly ran `scripts.bootstrap.build_block_heights --use-rpc`.
- `utxoracle-daily-prices-refresh.service` formerly ran `scripts.bootstrap.build_price_table`.

Those modules write `data/utxoracle.duckdb`. The 2026-06-04 smoke proved the
failure mode: both commands reached DuckDB connect and failed on the live file
lock. That was not external noise; the unit definitions themselves scheduled
the conflicting DuckDB write path.

Phase 1.5-v2 replaces that design with QuestDB-native writers:

- `scripts.bootstrap.build_block_heights_questdb`
- `scripts.bootstrap.build_price_table_questdb`

The two legacy DuckDB scripts remain only for historical one-shot backfills and
now carry deprecation banners.

## Static Verification

Command:

```bash
systemd-analyze verify \
  utxoracle-utxo-creation-catchup.service \
  utxoracle-utxo-spent-backfill.service \
  utxoracle-block-heights-catchup.service \
  utxoracle-block-heights-catchup.timer \
  utxoracle-daily-prices-refresh.service \
  utxoracle-daily-prices-refresh.timer
```

Result: exit code 0.

Host warnings observed during verify were unrelated pre-existing host warnings
or the pre-existing executable-bit warning on `utxoracle-whale-detection.service`.
None came from the Phase 1.5-v2 unit definitions.

## Tests

Commands run:

```bash
uv run pytest tests/test_create_tables_ddl.py -q
uv run pytest tests/test_calculate_daily_metrics_questdb.py -q
uv run pytest tests/test_spec061_phase15_writers.py -q
uv run pytest tests/test_spec061_phase15_units.py -q
```

Results:

```text
tests/test_create_tables_ddl.py: 3 passed, 24 warnings
tests/test_calculate_daily_metrics_questdb.py: 7 passed, 24 warnings
tests/test_spec061_phase15_writers.py: 3 passed, 24 warnings
tests/test_spec061_phase15_units.py: 4 passed, 24 warnings
```

Warnings are existing Pydantic deprecations and the existing pytest config
warning.

## QuestDB DDL Evidence

Metadata check:

```sql
SELECT table_name, walEnabled, dedup
FROM tables()
WHERE table_name IN ('block_heights', 'daily_prices')
ORDER BY table_name;
```

Observed:

```text
('block_heights', True, True)
('daily_prices', True, True)
```

## Writer Smoke

Precondition:

```bash
fuser data/utxoracle.duckdb || true
```

Observed output before writer runs: empty.

Commands:

```bash
timeout 60 uv run python -m scripts.bootstrap.build_block_heights_questdb \
  --start-block 952408 \
  --end-block 952408 \
  --workers 1

timeout 60 uv run python -m scripts.bootstrap.build_price_table_questdb \
  --start-date 2026-06-04 \
  --end-date 2026-06-04 \
  --batch-size 1 \
  --rate-limit 1
```

Results:

```text
Inserted 1 block_heights rows into QuestDB
Inserted 1 daily_prices rows into QuestDB
```

Post-run `fuser data/utxoracle.duckdb || true` output: empty.

QuestDB max markers after the run:

```text
block_heights: max(height)=952408, max(ts)=2026-06-04 23:26:58
daily_prices: max(date)=2026-06-04 00:00:00
```

This proves the v2 timer targets can advance source freshness without touching
DuckDB.

## Aggregator Smoke

Command:

```bash
timeout 60 uv run python -m scripts.metrics.calculate_daily_metrics \
  --date 2026-06-04 \
  --questdb-reads \
  --questdb-only
```

Result:

```text
QuestDB-only metrics mirrored for 2026-06-04
Metrics persisted for 2026-06-04
```

QuestDB check:

```text
mvrv_daily row for 2026-06-04: count=1
```

During this run, `fuser data/utxoracle.duckdb` showed the aggregator Python PID.
That is expected in Phase 1.5-v2 because `calculate_daily_metrics` still reads
`utxo_lifecycle_full` from DuckDB. The v2 migration removes DuckDB from
`block_heights` and `daily_prices`; complete removal of DuckDB reads belongs to
spec-062 when `utxo_lifecycle` becomes the QuestDB SSOT.

## Operator Install Commands

The host path `/etc/systemd/system` is not writable for this user, so install
still requires an operator shell with sudo:

```bash
sudo cp \
  utxoracle-utxo-creation-catchup.service \
  utxoracle-utxo-spent-backfill.service \
  utxoracle-block-heights-catchup.service \
  utxoracle-block-heights-catchup.timer \
  utxoracle-daily-prices-refresh.service \
  utxoracle-daily-prices-refresh.timer \
  /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl start utxoracle-block-heights-catchup.service
sudo systemctl start utxoracle-daily-prices-refresh.service
sudo systemctl enable --now utxoracle-block-heights-catchup.timer
sudo systemctl enable --now utxoracle-daily-prices-refresh.timer
```
