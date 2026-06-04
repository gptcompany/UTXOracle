# UTXOracle Production Unit Audit

Date: 2026-06-04
Host context: `/media/sam/1TB/UTXOracle`

This audit records the host systemd state for `utxoracle-*` units before
spec-061 Phase 1 changes. It uses the roadmap status classes:

- `absent`: not installed in systemd on this host.
- `present-not-enabled`: installed but not enabled, or static.
- `present-enabled-not-running`: enabled but not active.
- `present-enabled-running`: enabled and active.

Commands used:

```bash
systemctl list-unit-files 'utxoracle-*' --all --no-pager
systemctl list-units 'utxoracle-*' --all --no-pager
systemctl is-enabled <unit>
systemctl is-active <unit>
systemctl show <unit> -p LoadState -p UnitFileState -p ActiveState -p SubState -p FragmentPath -p Result
```

## Installed Unit State

| Unit | Classification | Enabled state | Active state | Load state | Fragment path | Notes |
|---|---|---:|---:|---:|---|---|
| `utxoracle-api.service` | `present-enabled-not-running` | `enabled` from `list-unit-files`; empty from `systemctl show` | `inactive` | `not-found` | empty from `systemctl show`; `/etc/systemd/system/utxoracle-api.service` is a symlink to `/media/sam/2TB-NVMe/prod/apps/utxoracle/config/systemd/utxoracle-api.service` | Anomalous host state: list-unit-files sees it as enabled, but the manager reports `LoadState=not-found`. Do not modify in Phase 1 per roadmap constraint. |
| `utxoracle-backtest-mirror.service` | `present-not-enabled` | `disabled` | `inactive/dead` | `loaded` | `/etc/systemd/system/utxoracle-backtest-mirror.service` | Timer-triggered oneshot. |
| `utxoracle-daily-aggregator.service` | `present-not-enabled` | `disabled` | `failed/failed` | `loaded` | `/etc/systemd/system/utxoracle-daily-aggregator.service` | Timer-triggered oneshot. Last run failed with exit status 1, consistent with stale DuckDB sources. |
| `utxoracle-live-wave1-materializer.service` | `present-enabled-running` | `enabled` | `active/running` | `loaded` | `/etc/systemd/system/utxoracle-live-wave1-materializer.service` | Long-lived service. Existing restart policy is `Restart=always`. |
| `utxoracle-snapshot-refresh.service` | `present-not-enabled` | `static` | `inactive/dead` | `loaded` | `/etc/systemd/system/utxoracle-snapshot-refresh.service` | Static timer target service. |
| `utxoracle-backtest-mirror.timer` | `present-enabled-running` | `enabled` | `active/waiting` | `loaded` | `/etc/systemd/system/utxoracle-backtest-mirror.timer` | Timer active. |
| `utxoracle-daily-aggregator.timer` | `present-enabled-running` | `enabled` | `active/waiting` | `loaded` | `/etc/systemd/system/utxoracle-daily-aggregator.timer` | Timer active. |
| `utxoracle-snapshot-refresh.timer` | `present-enabled-running` | `enabled` | `active/waiting` | `loaded` | `/etc/systemd/system/utxoracle-snapshot-refresh.timer` | Timer active. |

## Repo Units Not Installed In Systemd

| Unit | Classification | Repo file | Host state | Notes |
|---|---|---:|---|---|
| `utxoracle-whale-detection.service` | `absent` | yes | `systemctl is-enabled`: no such file; `is-active`: `inactive` | The repo unit wraps `scripts/whale_detection_orchestrator.py`. That orchestrator starts `MempoolWhaleMonitor`, and `MempoolWhaleMonitor` writes `mempool_predictions` via `repo.async_send_row("mempool_predictions", ...)`. If this unit is installed and running, it covers Phase 2 stream #2. On this host it is not installed, so it does not currently cover the stream. |
| `utxoracle-mirror-live-questdb.service` | `absent` | yes | no such unit file | Repo file exists; not installed on this host. Install command is documented in `docs/PRODUCTION_MIRROR_TIMER_INSTALL.md`. |
| `utxoracle-mirror-live-questdb.timer` | `absent` | yes | no such unit file | Repo file exists; not installed on this host. Install command is documented in `docs/PRODUCTION_MIRROR_TIMER_INSTALL.md`. |

## Phase 2 Producer Gate

`mempool_predictions` is QuestDB-ready in code, but not operationally
covered on this host because `utxoracle-whale-detection.service` is not
installed. Phase 2 should either install/reuse that unit or create a
smaller `utxoracle-mempool-predictions.service`; it must avoid running
two `MempoolWhaleMonitor` instances against the same mempool stream.

## Phase 1 No-Change Units

The roadmap explicitly excludes restart-policy edits for:

- `utxoracle-api.service`: repo unit already has `Restart=on-failure`.
- `utxoracle-live-wave1-materializer.service`: repo unit already has
  `Restart=always`.

