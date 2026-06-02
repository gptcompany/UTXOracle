#!/usr/bin/env bash
# spec-061 post-mirror automation chain.
#
# Watches the lifecycle mirror checkpoint, then runs the full Wave 6 chain
# fail-fast in sequence when the mirror completes:
#
#   1. verify_utxo_lifecycle_mirror             (F1 duplicate check)
#   2. verify_utxo_lifecycle_mirror --fix       (only if duplicates found)
#   3. catchup_utxo_lifecycle_to_tip            (creation tip catch-up)
#   4. historical_spent_backfill --target-backend questdb
#                                               (spent backfill to tip)
#   5. calculate_daily_metrics --backfill 160   (T037)
#   6. pytest -m integration tests/integration/test_streams_health_contract.py
#                                               (T010 — overall == OK gate)
#   7. gh issue comment on gptcompany/UTXOracle#8 with all commit hashes
#
# Each step's stdout/stderr is appended to a single log file under /tmp.
# Steps 2 and onward run only if the previous step exited 0.
#
# Usage:
#   nohup bash scripts/bootstrap/spec061_post_mirror_chain.sh \
#     > /tmp/spec061_chain.log 2>&1 &
#
# Inspect:
#   tail -f /tmp/spec061_chain.log
#   cat /tmp/spec061_chain.state
#
# Stop:
#   pkill -f spec061_post_mirror_chain.sh

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

LOG="/tmp/spec061_chain.log"
STATE="/tmp/spec061_chain.state"
CHECKPOINT="data/questdb_utxo_lifecycle_mirror_checkpoint.json"
TARGET_BLOCK=927966
POLL_SECONDS=60

log() {
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '[%s] %s\n' "$ts" "$*" | tee -a "$LOG" >&2
}

notify_discord() {
    # Best-effort notification on terminal state transitions.
    # Uses DISCORD_WEBHOOK_URL from env if present; silent no-op otherwise.
    local msg="$1"
    if [ -n "${DISCORD_WEBHOOK_URL:-}" ] && command -v curl >/dev/null 2>&1; then
        curl -fsS -m 5 -H "Content-Type: application/json" \
            -d "$(printf '{"content": "spec-061 chain: %s"}' "$msg")" \
            "$DISCORD_WEBHOOK_URL" > /dev/null 2>&1 || true
    fi
}

set_state() {
    echo "$1" > "$STATE"
    log "STATE=$1"
    case "$1" in
        complete|fatal_*|fail_*)
            notify_discord "state=$1 (see /tmp/spec061_chain.log)"
            ;;
    esac
}

resolve_bitcoin_tip() {
    # G6 (review 2026-06-02): bitcoin-cli is the primary path; fall back to
    # the in-repo BitcoinRPC helper if the binary is missing or the daemon
    # rejects the call. Both paths read the same RPC credentials.
    local tip
    if command -v bitcoin-cli >/dev/null 2>&1; then
        tip=$(bitcoin-cli getblockcount 2>/dev/null || true)
        if [ -n "$tip" ] && [ "$tip" -ge 1 ] 2>/dev/null; then
            echo "$tip"
            return 0
        fi
        log "bitcoin-cli getblockcount failed; trying Python BitcoinRPC fallback"
    else
        log "bitcoin-cli not in PATH; using Python BitcoinRPC fallback"
    fi
    tip=$(uv run python -c "
from scripts.sync_utxo_lifecycle import BitcoinRPC
print(BitcoinRPC().getblockcount())
" 2>/dev/null)
    if [ -n "$tip" ] && [ "$tip" -ge 1 ] 2>/dev/null; then
        echo "$tip"
        return 0
    fi
    return 1
}

require_questdb() {
    if ! command -v psql >/dev/null && ! uv run python -c "import psycopg" 2>/dev/null; then
        log "FATAL: neither psql nor psycopg available"
        return 1
    fi
}

# ── Step 0: wait for mirror completion ───────────────────────────────────────

set_state "waiting_for_mirror"
log "Polling $CHECKPOINT every ${POLL_SECONDS}s for last_block >= $TARGET_BLOCK"

while true; do
    if [ ! -f "$CHECKPOINT" ]; then
        log "Checkpoint file missing; assuming mirror not started. Sleeping."
        sleep "$POLL_SECONDS"
        continue
    fi
    LAST_BLOCK=$(jq -r '.last_block // 0' "$CHECKPOINT" 2>/dev/null || echo 0)
    MIRRORED=$(jq -r '.mirrored_rows // 0' "$CHECKPOINT" 2>/dev/null || echo 0)
    log "Mirror progress: last_block=$LAST_BLOCK / target=$TARGET_BLOCK, rows=$MIRRORED"
    if [ "$LAST_BLOCK" -ge "$TARGET_BLOCK" ]; then
        log "Mirror reached target. Proceeding with verification."
        break
    fi
    # Detect crashed mirror: if the pid file points to a dead process, abort.
    if [ -f /tmp/mirror_utxo_lifecycle_to_questdb.pid ]; then
        MIRROR_PID=$(cat /tmp/mirror_utxo_lifecycle_to_questdb.pid)
        if ! kill -0 "$MIRROR_PID" 2>/dev/null; then
            log "FATAL: mirror PID $MIRROR_PID is dead but last_block=$LAST_BLOCK < target=$TARGET_BLOCK"
            set_state "fatal_mirror_crashed"
            exit 2
        fi
    fi
    sleep "$POLL_SECONDS"
done

# ── Step 1: integrity check ───────────────────────────────────────────────────

set_state "verifying_integrity"
log "Step 1: verify_utxo_lifecycle_mirror"
if ! uv run python -m scripts.bootstrap.verify_utxo_lifecycle_mirror >> "$LOG" 2>&1; then
    set_state "duplicates_found"
    log "Step 2: dedup pass (--fix)"
    if ! uv run python -m scripts.bootstrap.verify_utxo_lifecycle_mirror --fix >> "$LOG" 2>&1; then
        log "FATAL: dedup pass failed"
        set_state "fatal_dedup_failed"
        exit 3
    fi
    log "Dedup succeeded; re-verifying"
    if ! uv run python -m scripts.bootstrap.verify_utxo_lifecycle_mirror >> "$LOG" 2>&1; then
        log "FATAL: integrity still failing after dedup"
        set_state "fatal_integrity_post_dedup"
        exit 3
    fi
fi
log "Integrity OK"

# ── Step 3: creation catch-up ────────────────────────────────────────────────

set_state "running_creation_catchup"
log "Step 3: catchup_utxo_lifecycle_to_tip"
if ! uv run python -m scripts.bootstrap.catchup_utxo_lifecycle_to_tip >> "$LOG" 2>&1; then
    log "FATAL: creation catchup failed"
    set_state "fatal_catchup_failed"
    exit 4
fi

# ── Step 4: spent backfill ───────────────────────────────────────────────────

set_state "computing_spent_backfill_range"

# Resolve the live tip via bitcoin-cli with Python RPC fallback (G6).
TIP=$(resolve_bitcoin_tip || true)
if [ -z "${TIP:-}" ]; then
    log "FATAL: could not resolve Bitcoin tip via bitcoin-cli OR Python RPC"
    set_state "fatal_tip_resolve_failed"
    exit 5
fi
log "Live tip: $TIP"

# Resolve the current spent_block frontier in QuestDB
START=$(uv run python - <<'PY' 2>>"$LOG"
import psycopg
from api.questdb_repository import (
    QUESTDB_PG_HOST, QUESTDB_PG_PORT, QUESTDB_PG_USER,
    QUESTDB_PG_PASSWORD, QUESTDB_PG_DATABASE,
)
with psycopg.connect(
    host=QUESTDB_PG_HOST, port=QUESTDB_PG_PORT,
    user=QUESTDB_PG_USER, password=QUESTDB_PG_PASSWORD,
    dbname=QUESTDB_PG_DATABASE, autocommit=True,
) as conn, conn.cursor() as cur:
    cur.execute("SELECT coalesce(max(spent_block), 0) + 1 FROM utxo_lifecycle WHERE spent_block IS NOT NULL")
    print(int(cur.fetchone()[0]))
PY
)
if [ -z "$START" ] || ! [ "$START" -ge 1 ] 2>/dev/null; then
    log "FATAL: could not resolve QuestDB spent frontier (got: '$START')"
    set_state "fatal_spent_frontier_resolve_failed"
    exit 5
fi
log "Spent backfill range: $START..$TIP"

if [ "$START" -gt "$TIP" ]; then
    log "Spent already at tip; skipping backfill"
else
    set_state "running_spent_backfill"
    if ! uv run python -m scripts.bootstrap.historical_spent_backfill \
        --target-backend questdb --start-block "$START" --end-block "$TIP" \
        >> "$LOG" 2>&1; then
        log "FATAL: spent backfill failed"
        set_state "fatal_spent_backfill_failed"
        exit 6
    fi
fi

# ── Step 5: daily metrics backfill (T037) ────────────────────────────────────

set_state "running_daily_metrics_backfill"
log "Step 5: calculate_daily_metrics --backfill 160"
if ! uv run python -m scripts.metrics.calculate_daily_metrics --backfill 160 >> "$LOG" 2>&1; then
    log "WARN: daily metrics backfill failed; continuing to T010 (failures may explain DEGRADED)"
fi

# ── Step 6: T010 integration test ────────────────────────────────────────────

set_state "running_acceptance_gate"
log "Step 6: T010 acceptance gate (pytest -m integration)"
export RUN_STREAMS_HEALTH_CONTRACT=1
if ! uv run pytest tests/integration/test_streams_health_contract.py \
    -v -m integration --tb=short >> "$LOG" 2>&1; then
    log "FAIL: T010 acceptance gate is RED — overall != OK"
    set_state "fail_t010_red"
    exit 7
fi
log "T010 acceptance gate: GREEN"

# ── Step 7: Issue #8 closure comment ─────────────────────────────────────────

set_state "ready_for_issue_closure"
log "All steps green. Operator: comment commit hashes on gptcompany/UTXOracle#8 and close."
log "Suggested gh command:"
log "  gh issue close 8 --repo gptcompany/UTXOracle --comment 'spec-061 complete; T010 green; deliverables 1-5 landed in $(git log --oneline 061-stream-consumption-contract ^main | head -1 | cut -d\" \" -f1)'"

set_state "complete"
exit 0
