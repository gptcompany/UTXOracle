# Production Phase 1 Smoke

Spec: `spec-061` Phase 1 + Phase 1.5.
Branch head during verification: `061-stream-consumption-contract`.
Date: 2026-06-04.

## Summary

| Check | Result | Notes |
| --- | --- | --- |
| New unit files present | PASS | Six files are present at repo root: two continuous supervisor services and two service/timer pairs. |
| `systemd-analyze verify` | PASS | All new units verify with exit code 0. Host warnings are unrelated pre-existing unit warnings. |
| Unit contract tests | PASS | `11 passed, 24 warnings` for the spec-061 systemd tests plus the existing daily aggregator timer test. |
| Mirror timer install | DOCUMENTED | Existing mirror files verify, but are not installed on this host. Operator commands are in `docs/PRODUCTION_MIRROR_TIMER_INSTALL.md`. |
| Supervisor failure webhook | PASS | Simulated failure posted exactly one JSON request to a local webhook endpoint. |
| `systemctl start` smoke | BLOCKED | `/etc/systemd/system` is not writable for this user, so the new units cannot be installed or started without operator sudo. |
| Live DuckDB row-count delta | BLOCKED | Both source-freshness scripts are blocked by the active DuckDB writer lock held by the live wave1 materializer. |

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

Host warnings observed during verify:

- `netplan-ovs-cleanup.service`: permission denied under `/run/systemd/system`
- `utxoracle-whale-detection.service`: executable permission bit warning
- unrelated installed host units with ignored keys or executable bit warnings

None of those warnings came from the new spec-061 unit files.

## Tests

Command:

```bash
uv run pytest \
  tests/test_spec061_phase1_units.py \
  tests/test_spec061_phase15_units.py \
  tests/test_daily_aggregator_timer.py \
  -q
```

Result:

```text
11 passed, 24 warnings in 20.03s
```

The warnings are existing Pydantic deprecation warnings and one existing pytest config warning.

## Webhook Simulation

The `ExecStopPost=` curl path was tested against a local HTTP endpoint with:

- `SERVICE_RESULT=exit-code`
- `EXIT_CODE=exited`
- `EXIT_STATUS=42`
- `DISCORD_WEBHOOK_URL=http://127.0.0.1:<ephemeral>/discord`

Observed request count: `1`.

Observed body:

```json
{"content":"utxoracle-utxo-creation-catchup.service failed: result=exit-code exit=exited/42"}
```

The unit file keeps `%n` for systemd unit-name expansion and escapes the `printf`
placeholders as `%%s`, so systemd does not consume the JSON formatting fields.

## Install And Start Commands

The host path `/etc/systemd/system` is not writable for this user, so the live
`systemctl start` portion requires an operator shell with sudo:

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

sudo systemctl start utxoracle-utxo-creation-catchup.service
sudo systemctl start utxoracle-utxo-spent-backfill.service
sudo systemctl start utxoracle-block-heights-catchup.service
sudo systemctl start utxoracle-daily-prices-refresh.service

sudo systemctl enable --now utxoracle-block-heights-catchup.timer
sudo systemctl enable --now utxoracle-daily-prices-refresh.timer
```

## DuckDB Live Trial

Before the attempted source-freshness runs:

| Table | Count | Max marker |
| --- | ---: | --- |
| `block_heights` | 928139 | `height=928138`, `timestamp=1765896950` |
| `daily_prices` | 5462 | `date=2025-12-14` |

Attempted commands:

```bash
timeout 60 uv run python -m scripts.bootstrap.build_block_heights \
  --use-rpc \
  --start-height 928139 \
  --end-height 928139 \
  --batch-size 1 \
  --rate-limit 10

timeout 60 uv run python -m scripts.bootstrap.build_price_table \
  --start-date 2025-12-15 \
  --end-date 2025-12-15 \
  --batch-size 1 \
  --rate-limit 1
```

Both commands reached DuckDB connect and failed before writing:

```text
_duckdb.IOException: IO Error: Could not set lock on file
"/media/sam/1TB/UTXOracle/data/utxoracle.duckdb": Conflicting lock is held in
/home/sam/.local/share/uv/python/cpython-3.11.13-linux-x86_64-gnu/bin/python3.11
(PID 7201).
```

The active holder at verification time was:

```text
/media/sam/1TB/UTXOracle/.venv/bin/python -m scripts.live.wave1_materializer_runtime
```

After the attempts, the table counts and max markers were unchanged. This leaves
the requested "advance by at least 1 day" smoke blocked by live DuckDB lock
contention, not by the new unit definitions.
