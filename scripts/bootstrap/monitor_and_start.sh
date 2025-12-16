#!/usr/bin/env bash
# Monitor Bitcoin Core reindex and auto-start block_heights build
#
# Usage:
#   ./scripts/bootstrap/monitor_and_start.sh
#   ./scripts/bootstrap/monitor_and_start.sh --check-only  # Just check status, don't start
#
# This script:
# 1. Monitors Bitcoin Core reindex progress via debug.log
# 2. Checks electrs connectivity
# 3. Auto-starts build_block_heights.py when ready
# 4. Sends notification when complete

set -euo pipefail

# Configuration
BITCOIN_DEBUG_LOG="${BITCOIN_DEBUG_LOG:-/media/sam/3TB-WDC/Bitcoin/debug.log}"
ELECTRS_URL="${ELECTRS_URL:-http://localhost:3001}"
DB_PATH="${DB_PATH:-/media/sam/1TB/UTXOracle/data/utxo_lifecycle.duckdb}"
CHECK_INTERVAL=60  # seconds between checks
PROGRESS_THRESHOLD=0.999  # 99.9% = effectively complete

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

get_bitcoin_progress() {
    if [[ -f "$BITCOIN_DEBUG_LOG" ]]; then
        tail -100 "$BITCOIN_DEBUG_LOG" 2>/dev/null | \
            grep -oP 'progress=\K[0-9.]+' | tail -1 || echo "0"
    else
        echo "0"
    fi
}

get_bitcoin_height() {
    if [[ -f "$BITCOIN_DEBUG_LOG" ]]; then
        tail -100 "$BITCOIN_DEBUG_LOG" 2>/dev/null | \
            grep -oP 'height=\K[0-9]+' | tail -1 || echo "0"
    else
        echo "0"
    fi
}

check_electrs() {
    local tip
    tip=$(curl -s --connect-timeout 5 "${ELECTRS_URL}/blocks/tip/height" 2>/dev/null || echo "")
    if [[ -n "$tip" && "$tip" =~ ^[0-9]+$ ]]; then
        echo "$tip"
    else
        echo "0"
    fi
    # Always return success to avoid set -e exit
    return 0
}

send_notification() {
    local title="$1"
    local message="$2"

    # Try notify-send (Linux desktop)
    if command -v notify-send &>/dev/null; then
        notify-send "$title" "$message" 2>/dev/null || true
    fi

    # Always log
    log "${GREEN}NOTIFICATION: $title - $message${NC}"
}

run_block_heights_build() {
    log "${GREEN}Starting block_heights build...${NC}"

    cd /media/sam/1TB/UTXOracle

    # Use RPC mode if Bitcoin Core is available, otherwise electrs
    if curl -s --connect-timeout 2 "http://localhost:8332" &>/dev/null; then
        log "Using RPC mode (faster)"
        python -m scripts.bootstrap.build_block_heights \
            --use-rpc \
            --db-path "$DB_PATH" \
            --batch-size 500 \
            --rate-limit 50 \
            -v
    else
        log "Using electrs mode (RPC unavailable)"
        python -m scripts.bootstrap.build_block_heights \
            --use-electrs \
            --db-path "$DB_PATH" \
            --batch-size 500 \
            --rate-limit 50 \
            -v
    fi
}

main() {
    local check_only=false

    if [[ "${1:-}" == "--check-only" ]]; then
        check_only=true
    fi

    log "${YELLOW}=== Bitcoin Core & Bootstrap Monitor ===${NC}"
    log "Bitcoin debug.log: $BITCOIN_DEBUG_LOG"
    log "electrs URL: $ELECTRS_URL"
    log "DuckDB path: $DB_PATH"
    echo ""

    while true; do
        # Get Bitcoin Core status
        local progress
        progress=$(get_bitcoin_progress)
        local height
        height=$(get_bitcoin_height)

        # Get electrs status
        local electrs_tip
        electrs_tip=$(check_electrs)

        log "Bitcoin Core: ${progress} (height: $height)"
        log "electrs tip: $electrs_tip"

        # Check if ready (progress >= 0.999)
        # Use awk for floating point comparison
        if awk "BEGIN {exit !($progress >= $PROGRESS_THRESHOLD)}"; then
            if [[ "$electrs_tip" != "0" ]]; then
                log "${GREEN}Bitcoin Core sync complete! electrs ready at height $electrs_tip${NC}"

                if [[ "$check_only" == "true" ]]; then
                    log "Check-only mode: exiting without starting build"
                    exit 0
                fi

                send_notification "Bitcoin Core Ready" "Starting block_heights build..."
                run_block_heights_build
                send_notification "Bootstrap Complete" "block_heights table built successfully"

                log "${GREEN}=== Bootstrap Complete ===${NC}"
                exit 0
            else
                log "${YELLOW}Bitcoin Core ready but electrs not responding yet...${NC}"
            fi
        fi

        if [[ "$check_only" == "true" ]]; then
            log "Check-only mode: exiting"
            exit 0
        fi

        log "Waiting ${CHECK_INTERVAL}s for next check..."
        sleep "$CHECK_INTERVAL"
        echo ""
    done
}

main "$@"
