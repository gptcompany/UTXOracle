#!/bin/bash
# UTXOracle Health Check Script (Aligned with Spec-003 and Spec-040)
# Checks Systemd services, Docker containers, API, and Databases

set -e

# Configuration (defaults)
API_PORT_LEGACY=${API_PORT_LEGACY:-8001}
API_PORT_LIVE=${API_PORT_LIVE:-8011}
QUESTDB_PORT=${QUESTDB_PORT:-9000}
DB_PATH=${DB_PATH:-"data/utxoracle.duckdb"}

echo "=== UTXOracle Health Check ==="
echo "Date: $(date)"
echo "Base Dir: $(pwd)"
echo

# 1. Check Systemd Services
echo "[1/5] Checking Systemd services..."
SERVICES=("utxoracle-api" "utxoracle-live-compose" "utxoracle-whale-detection")
for svc in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        echo "✅ $svc is running"
    else
        echo "❌ $svc is NOT running"
        # Not exiting here to see other statuses
    fi
done
echo

# 2. Check Docker containers
echo "[2/5] Checking Docker containers..."
if docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | grep -E "(questdb|mempool|electrs)" > /dev/null 2>&1; then
    docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(questdb|mempool|electrs|NAMES)"
    echo "✅ Key Docker containers running"
else
    echo "⚠️  No key Docker containers found (QuestDB/Mempool stack might be down)"
fi
echo

# 3. Check API endpoints
echo "[3/5] Checking API endpoints..."
# Legacy/Research API
if curl -s "http://localhost:${API_PORT_LEGACY}/health" | grep -q "healthy" 2>/dev/null; then
    echo "✅ Legacy API (${API_PORT_LEGACY}) healthy"
else
    echo "❌ Legacy API (${API_PORT_LEGACY}) not responding"
fi

# Live API (if expected)
if curl -s "http://localhost:${API_PORT_LIVE}/health" | grep -q "healthy" 2>/dev/null; then
    echo "✅ Live API (${API_PORT_LIVE}) healthy"
else
    echo "⚠️  Live API (${API_PORT_LIVE}) not responding (Expected if spec-040 not fully deployed)"
fi

# QuestDB
if curl -s -I "http://localhost:${QUESTDB_PORT}" | grep -q "HTTP/1.1 200 OK" 2>/dev/null; then
    echo "✅ QuestDB (${QUESTDB_PORT}) Web Console up"
else
    echo "❌ QuestDB (${QUESTDB_PORT}) not responding"
fi
echo

# 4. Check Databases
echo "[4/5] Checking Databases..."
if [ -f "$DB_PATH" ]; then
    echo "✅ DuckDB found at $DB_PATH"
    # Basic check if it's a valid duckdb file
    if command -v duckdb >/dev/null 2>&1; then
        ENTRIES=$(duckdb "$DB_PATH" "SELECT count(*) FROM prices" 2>/dev/null || echo "N/A")
        echo "   Prices table count: $ENTRIES"
    fi
else
    echo "❌ DuckDB NOT found at $DB_PATH"
fi
echo

# 5. Check Disk Space
echo "[5/5] Checking disk space..."
df -h . | tail -1 | awk '{print "   Workspace usage: " $3 " used / " $2 " total (" $5 " full)"}'
echo "✅ Disk space check complete"

echo
echo "=== Health Check Complete ==="
