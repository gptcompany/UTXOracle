#!/usr/bin/env bash
# Supervisor for the two utxo_lifecycle backfill paths. Restart on failure
# until both report "Already at tip". Each run picks up from where the
# previous one stopped (the scripts default --start-block to QuestDB's
# max + 1).
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 1
export PORT_GUARD_OFF=1

NAME="$1"  # creation | spent
case "$NAME" in
    creation)
        MODULE=scripts.bootstrap.tip_catchup_lifecycle_via_rpc
        LOG=/tmp/tip_catchup.log
        ;;
    spent)
        MODULE=scripts.bootstrap.tip_spent_backfill_via_rpc
        LOG=/tmp/spent_backfill.log
        ;;
    *)
        echo "usage: $0 {creation|spent}" >&2
        exit 2
        ;;
esac

ATTEMPT=0
MAX_ATTEMPTS=50
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    ATTEMPT=$((ATTEMPT + 1))
    {
        echo "=== $(date -Iseconds) supervisor attempt $ATTEMPT ==="
        uv run python -m "$MODULE" --workers 6 2>&1
        echo "=== $(date -Iseconds) exit code $? ==="
    } >> "$LOG" 2>&1
    # If we reach "Already at tip" or "complete", we are done.
    if tail -n 30 "$LOG" | grep -qE "Already at tip|backfill complete|catch-up complete"; then
        echo "$(date -Iseconds) $NAME supervisor: caught up, exiting." >> "$LOG"
        exit 0
    fi
    sleep 30
done
echo "$(date -Iseconds) $NAME supervisor: max attempts exceeded." >> "$LOG"
exit 1
