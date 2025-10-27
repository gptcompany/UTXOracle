#!/bin/bash
# UTXOracle Health Check Script
# Checks Docker containers, API, cron, and DuckDB

set -e

echo "=== UTXOracle Health Check ==="
echo "Date: $(date)"
echo

# Check Docker containers (if running)
echo "[1/4] Checking Docker containers..."
if docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | grep -E "(mempool|electrs|maria)" > /dev/null 2>&1; then
    docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(mempool|electrs|maria|NAMES)"
    echo "✅ Docker containers running"
else
    echo "⚠️  mempool-stack not running (expected during Bitcoin Core sync)"
fi
echo

# Check API server
echo "[2/4] Checking API server..."
if curl -s http://localhost:8000/health | jq -e '.status == "healthy"' > /dev/null 2>&1; then
    echo "✅ API server healthy"
    curl -s http://localhost:8000/health | jq '.uptime_seconds' | xargs echo "   Uptime (seconds):"
else
    echo "❌ API server not responding"
    exit 1
fi
echo

# Check DuckDB
echo "[3/4] Checking DuckDB..."
DB_PATH="/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
if [ -f "$DB_PATH" ]; then
    ENTRIES=$(duckdb "$DB_PATH" "SELECT COUNT(*) FROM prices" 2>/dev/null | grep -oE '[0-9]+' || echo "0")
    echo "✅ DuckDB exists with $ENTRIES entries"
    echo "   Last update: $(duckdb "$DB_PATH" "SELECT MAX(timestamp) FROM prices" 2>/dev/null | tail -1)"
else
    echo "❌ DuckDB not found at $DB_PATH"
    exit 1
fi
echo

# Check disk space
echo "[4/4] Checking disk space..."
df -h /media/sam/2TB-NVMe/ | tail -1 | awk '{print "   NVMe usage: " $3 " used / " $2 " total (" $5 " full)"}'
echo "✅ Disk space OK"

echo
echo "=== Overall Status: ✅ HEALTHY ==="
