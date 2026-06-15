#!/usr/bin/env bash
# Install Phase 1.5-v2 systemd units (block_heights + daily_prices, QuestDB-native).
# Requires sudo. Idempotent: safe to re-run.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UNITS=(
  utxoracle-block-heights-catchup.service
  utxoracle-block-heights-catchup.timer
  utxoracle-daily-prices-refresh.service
  utxoracle-daily-prices-refresh.timer
)

echo "Installing Phase 1.5-v2 units from $REPO"
for u in "${UNITS[@]}"; do
  src="$REPO/$u"
  dst="/etc/systemd/system/$u"
  if [[ ! -f "$src" ]]; then
    echo "ERROR: missing $src" >&2
    exit 1
  fi
  sudo install -o root -g root -m 0644 "$src" "$dst"
  echo "  installed $dst"
done

sudo systemctl daemon-reload
sudo systemctl enable --now \
  utxoracle-block-heights-catchup.timer \
  utxoracle-daily-prices-refresh.timer

echo
echo "--- timer state ---"
systemctl list-timers --no-pager | grep -E "block-heights|daily-prices" || true

echo
echo "--- next scheduled fires ---"
for t in utxoracle-block-heights-catchup.timer utxoracle-daily-prices-refresh.timer; do
  echo "$t:"
  systemctl show "$t" -p NextElapseUSecRealtime -p LastTriggerUSec | sed 's/^/  /'
done

echo
echo "Done. Tail journal with:"
echo "  journalctl -u utxoracle-block-heights-catchup.service -u utxoracle-daily-prices-refresh.service -f"
