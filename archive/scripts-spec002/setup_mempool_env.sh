#!/bin/bash
# Setup script for self-hosted mempool.space configuration
# Creates .env file with correct settings for UTXOracle integration

set -e

MEMPOOL_DIR="/media/sam/1TB/mempool/docker"
BITCOIN_DATADIR="${HOME}/.bitcoin"

echo "=== Mempool.space Self-Hosted Setup for UTXOracle ==="
echo

# Check prerequisites
if [ ! -d "$MEMPOOL_DIR" ]; then
    echo "❌ Error: Mempool directory not found at $MEMPOOL_DIR"
    echo "   Clone it first: git clone https://github.com/mempool/mempool"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker not installed"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Error: Docker Compose not installed"
    exit 1
fi

# Get Bitcoin Core RPC credentials
echo "🔍 Detecting Bitcoin Core RPC credentials..."

if [ -f "${BITCOIN_DATADIR}/bitcoin.conf" ]; then
    RPC_USER=$(grep "^rpcuser=" "${BITCOIN_DATADIR}/bitcoin.conf" | cut -d'=' -f2)
    RPC_PASS=$(grep "^rpcpassword=" "${BITCOIN_DATADIR}/bitcoin.conf" | cut -d'=' -f2)
    echo "   Found credentials in bitcoin.conf"
else
    echo "⚠️  No bitcoin.conf found, checking for cookie authentication..."
    if [ -f "${BITCOIN_DATADIR}/.cookie" ]; then
        echo "   Using cookie authentication (recommended)"
        RPC_USER=""
        RPC_PASS=""
    else
        echo "❌ Error: No RPC credentials found"
        echo "   Please configure bitcoin.conf with rpcuser/rpcpassword"
        exit 1
    fi
fi

# Create .env file
ENV_FILE="${MEMPOOL_DIR}/.env"

echo
echo "📝 Creating ${ENV_FILE}..."

cat > "$ENV_FILE" << EOF
# Mempool.space Configuration for UTXOracle Integration
# Generated: $(date)

# Bitcoin Core RPC
CORE_RPC_HOST=127.0.0.1
CORE_RPC_PORT=8332
CORE_RPC_USERNAME=${RPC_USER:-your_rpc_user}
CORE_RPC_PASSWORD=${RPC_PASS:-your_rpc_password}

# Electrs Configuration
ELECTRUM_HOST=electrs
ELECTRUM_PORT=50002
ELECTRUM_TLS_ENABLED=true

# MySQL Database
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=mempool
MYSQL_USER=mempool
MYSQL_PASS=mempool

# DISABLE price-updater (we use UTXOracle for on-chain prices)
MEMPOOL_PRICE_FEED_UPDATE_INTERVAL=0

# Backend API
MEMPOOL_BACKEND_HTTP_HOST=0.0.0.0
MEMPOOL_BACKEND_HTTP_PORT=8999

# Frontend
MEMPOOL_FRONTEND_HTTP_PORT=8080

# CORS (allow external clients)
MEMPOOL_BACKEND_HTTP_CORS_ALLOW_ALL=true

# Cache settings
MEMPOOL_CACHE_ENABLED=true
MEMPOOL_CACHE_DIR=/cache

# Electrs cache (increase for better performance)
ELECTRS_DB_CACHE_MB=4096
EOF

echo "✅ .env file created"

# Verify Bitcoin Core is running
echo
echo "🔍 Verifying Bitcoin Core connection..."
if bitcoin-cli getblockcount &> /dev/null; then
    BLOCK_HEIGHT=$(bitcoin-cli getblockcount)
    echo "   ✅ Bitcoin Core connected (height: $BLOCK_HEIGHT)"
else
    echo "   ⚠️  Bitcoin Core not responding"
    echo "   Make sure bitcoind is running before starting mempool stack"
fi

echo
echo "=== Setup Complete ==="
echo
echo "Next steps:"
echo "1. Review .env file: nano ${ENV_FILE}"
echo "2. Start mempool stack: cd ${MEMPOOL_DIR} && docker-compose up -d"
echo "3. Monitor electrs sync: docker-compose logs -f electrs"
echo "4. Access frontend: http://localhost:8080"
echo "5. Test API: curl http://localhost:8999/api/blocks/tip/height"
echo
echo "⏱️  Note: First electrs sync takes 8-12 hours"
echo "📚 See: /media/sam/1TB/UTXOracle/docs/SELFHOSTED_MEMPOOL_INTEGRATION.md"
