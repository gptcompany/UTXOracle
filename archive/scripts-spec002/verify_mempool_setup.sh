#!/bin/bash
# Verification script for self-hosted mempool.space setup
# Checks that all services are running and accessible

set -e

MEMPOOL_API="http://localhost:8999/api"
MEMPOOL_FRONTEND="http://localhost:8080"
MEMPOOL_DIR="/media/sam/1TB/mempool/docker"

echo "=== Mempool.space Setup Verification ==="
echo

# Check Docker services
echo "1️⃣  Checking Docker services..."
cd "$MEMPOOL_DIR"

if ! docker-compose ps | grep -q "Up"; then
    echo "   ❌ No services running"
    echo "   Start with: docker-compose up -d"
    exit 1
fi

# Check each service
SERVICES=("backend" "frontend" "electrs" "mysql")
for service in "${SERVICES[@]}"; do
    if docker-compose ps | grep "$service" | grep -q "Up"; then
        echo "   ✅ $service: Running"
    else
        echo "   ❌ $service: Not running"
    fi
done

# Check backend API
echo
echo "2️⃣  Checking Backend API..."
if response=$(curl -s "${MEMPOOL_API}/blocks/tip/height"); then
    HEIGHT=$(echo "$response" | grep -oP '"height":\K[0-9]+' || echo "unknown")
    echo "   ✅ API responding (block height: $HEIGHT)"
else
    echo "   ❌ API not responding"
    echo "   Check logs: docker-compose logs backend"
fi

# Check frontend
echo
echo "3️⃣  Checking Frontend..."
if curl -s -o /dev/null -w "%{http_code}" "$MEMPOOL_FRONTEND" | grep -q "200"; then
    echo "   ✅ Frontend accessible at $MEMPOOL_FRONTEND"
else
    echo "   ❌ Frontend not accessible"
    echo "   Check logs: docker-compose logs frontend"
fi

# Check electrs sync status
echo
echo "4️⃣  Checking Electrs Sync Status..."
ELECTRS_LOGS=$(docker-compose logs --tail=10 electrs 2>&1 || echo "")
if echo "$ELECTRS_LOGS" | grep -q "finished full compaction"; then
    echo "   ✅ Electrs fully synced"
elif echo "$ELECTRS_LOGS" | grep -q "indexing"; then
    echo "   ⏳ Electrs syncing (check progress: docker-compose logs -f electrs)"
else
    echo "   ⚠️  Electrs status unknown"
fi

# Check MySQL
echo
echo "5️⃣  Checking MySQL Database..."
if docker-compose exec -T mysql mysql -umempool -pmempool -e "USE mempool; SHOW TABLES;" &> /dev/null; then
    TABLE_COUNT=$(docker-compose exec -T mysql mysql -umempool -pmempool -e "USE mempool; SHOW TABLES;" 2>/dev/null | wc -l)
    echo "   ✅ MySQL connected ($TABLE_COUNT tables)"
else
    echo "   ❌ MySQL not accessible"
    echo "   Check logs: docker-compose logs mysql"
fi

# Check Bitcoin Core connection
echo
echo "6️⃣  Checking Bitcoin Core Connection..."
if bitcoin-cli getblockcount &> /dev/null; then
    BTC_HEIGHT=$(bitcoin-cli getblockcount)
    echo "   ✅ Bitcoin Core connected (height: $BTC_HEIGHT)"
else
    echo "   ❌ Bitcoin Core not responding"
    echo "   Make sure bitcoind is running"
fi

# Test UTXOracle integration
echo
echo "7️⃣  Testing UTXOracle Integration..."
if [ -f "/media/sam/1TB/UTXOracle/UTXOracle.py" ]; then
    echo "   ✅ UTXOracle.py found"
    echo "   Test with: python3 UTXOracle.py -rb --no-browser"
else
    echo "   ❌ UTXOracle.py not found"
fi

# Summary
echo
echo "=== Verification Complete ==="
echo
echo "📊 Quick Stats:"
curl -s "${MEMPOOL_API}/v1/statistics/1m" 2>/dev/null | head -5 || echo "   API statistics unavailable"

echo
echo "🔗 Useful Links:"
echo "   Frontend: $MEMPOOL_FRONTEND"
echo "   API Docs: ${MEMPOOL_API}/docs"
echo "   WebSocket: ws://localhost:8999/api/v1/ws"
echo
echo "📚 Integration Guide: /media/sam/1TB/UTXOracle/docs/SELFHOSTED_MEMPOOL_INTEGRATION.md"
