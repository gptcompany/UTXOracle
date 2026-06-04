# UTXOracle Live QuestDB Mirror Timer Install Check

Date: 2026-06-04

Phase 1 deliverable: verify the existing repo-root mirror units and
record the host install state.

## Repo Files

Both unit files exist at the repo root:

- `utxoracle-mirror-live-questdb.service`
- `utxoracle-mirror-live-questdb.timer`

`systemd-analyze verify` succeeds for the pair on this host. The command
also prints unrelated warnings from other host units; none reference the
mirror unit files.

```bash
systemd-analyze verify \
  utxoracle-mirror-live-questdb.service \
  utxoracle-mirror-live-questdb.timer
```

## Host Install State

The units are not installed in systemd on this host:

| Unit | Repo file | `systemctl is-enabled` | `systemctl is-active` |
|---|---:|---|---|
| `utxoracle-mirror-live-questdb.service` | yes | no such unit file | `inactive` |
| `utxoracle-mirror-live-questdb.timer` | yes | no such unit file | `inactive` |

## Operator Install Command

Run this from the repo root:

```bash
sudo cp utxoracle-mirror-live-questdb.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now utxoracle-mirror-live-questdb.timer
systemctl list-timers 'utxoracle-*' --no-pager
```

Expected post-install state:

- `utxoracle-mirror-live-questdb.timer`: enabled and active/waiting.
- `/tmp/spec061_mirror_checkpoint.json`: advances monotonically after
  each successful mirror pass.

