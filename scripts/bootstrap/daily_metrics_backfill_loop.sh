#!/usr/bin/env bash
# Background backfill loop for daily metrics (mvrv/nupl/realized_cap).
# Walks backwards from the most recent date that has both block data and a
# price (max(daily_prices.date) in DuckDB). Stops at --days back, or when a
# day fails with no recoverable error. Idempotent: re-runs the same date
# overwrite via QuestDB DEDUP UPSERT KEYS(ts).
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 1
export PORT_GUARD_OFF=1
DAYS_BACK="${1:-365}"
START_DATE="${2:-2025-12-14}"

current="$START_DATE"
attempts=0
for i in $(seq 1 "$DAYS_BACK"); do
    {
        echo "=== $(date -Iseconds) backfilling $current ==="
        uv run python -m scripts.metrics.calculate_daily_metrics \
            --date "$current" --questdb-only 2>&1
        echo "=== exit $? ==="
    } >> /tmp/daily_metrics_backfill.log 2>&1
    # decrement
    current=$(date -d "$current -1 day" +%Y-%m-%d)
    attempts=$((attempts + 1))
done
echo "$(date -Iseconds) backfill loop done ($attempts attempts)" >> /tmp/daily_metrics_backfill.log
