#!/bin/bash
# Full mempool.space + electrs Stack Setup on NVMe
# Creates unified docker-compose for production deployment
# UPDATED: 2025-10-24 - With working configuration from testing

set -e

PROD_DIR="/media/sam/2TB-NVMe/prod/apps"
BITCOIN_DATADIR="/media/sam/3TB-WDC/Bitcoin"  # Custom datadir (not ~/.bitcoin)

echo "🚀 Setting up Full mempool.space + electrs Stack"
echo "=================================================="
echo

# Step 1: Create directory structure
echo "📁 Creating production directories..."
mkdir -p "$PROD_DIR/mempool-stack/"{data,logs,config}
mkdir -p "$PROD_DIR/mempool-stack/data/"{electrs,mysql,cache}

echo "✅ Directories created"
echo

# Step 1.5: Detect host IP address
echo "🔍 Detecting host IP address..."
HOST_IP=$(ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v 127.0.0.1 | head -1)
echo "✅ Host IP detected: $HOST_IP"
echo

# Step 2: Create unified docker-compose.yml with TESTED configuration
echo "📝 Creating unified docker-compose.yml..."
cat > "$PROD_DIR/mempool-stack/docker-compose.yml" << EOF
networks:
  mempool-network:
    driver: bridge

services:
  # electrs - Bitcoin indexer (38GB database on NVMe)
  # Uses network_mode: host to access Bitcoin Core on 127.0.0.1:8332
  electrs:
    image: mempool/electrs:latest
    container_name: mempool-electrs
    restart: unless-stopped
    network_mode: host
    volumes:
      # NVMe storage for 38GB database
      - /media/sam/2TB-NVMe/prod/apps/mempool-stack/data/electrs:/data
      # Bitcoin Core data (read-only) - custom datadir on WDC HDD
      - /media/sam/3TB-WDC/Bitcoin:/bitcoin:ro
    environment:
      - RUST_LOG=electrs=info
    command:
      - -vvv
      - --db-dir
      - /data
      - --daemon-dir
      - /bitcoin
      - --daemon-rpc-addr
      - 127.0.0.1:8332
      - --cookie
      - "bitcoinrpc:$$(openssl rand -hex 32)"
      - --network
      - mainnet
      - --electrum-rpc-addr
      - 127.0.0.1:50001
      - --http-addr
      - 127.0.0.1:3001
      - --monitoring-addr
      - 127.0.0.1:4224
      - --address-search
      - --index-unspendables
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4224"]
      interval: 30s
      timeout: 10s
      retries: 3

  # MariaDB - mempool backend database
  db:
    image: mariadb:10.5.21
    container_name: mempool-db
    restart: unless-stopped
    networks:
      - mempool-network
    volumes:
      # NVMe storage for MySQL
      - /media/sam/2TB-NVMe/prod/apps/mempool-stack/data/mysql:/var/lib/mysql
    environment:
      MYSQL_DATABASE: mempool
      MYSQL_USER: mempool
      MYSQL_PASSWORD: mempool
      MYSQL_ROOT_PASSWORD: admin
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 3

  # mempool backend - Node.js API
  api:
    image: mempool/backend:latest
    container_name: mempool-api
    restart: unless-stopped
    networks:
      - mempool-network
    depends_on:
      - db
      - electrs
    volumes:
      # NVMe storage for cache
      - /media/sam/2TB-NVMe/prod/apps/mempool-stack/data/cache:/backend/cache
    environment:
      # Backend mode - using esplora (HTTP REST API) instead of electrum (RPC protocol)
      MEMPOOL_BACKEND: "esplora"

      # Bitcoin Core RPC (direct host IP since electrs uses host network)
      CORE_RPC_HOST: "$HOST_IP"
      CORE_RPC_PORT: "8332"
      CORE_RPC_USERNAME: "bitcoinrpc"
      CORE_RPC_PASSWORD: "$$(openssl rand -hex 32)"  # Literal string from bitcoin.conf

      # electrs connection via esplora REST API (direct host IP since electrs uses host network mode)
      # Port 3001 instead of 3000 to avoid conflict with Grafana
      ESPLORA_REST_API_URL: "http://$HOST_IP:3001"

      # Database
      DATABASE_ENABLED: "true"
      DATABASE_HOST: "db"
      DATABASE_DATABASE: "mempool"
      DATABASE_USERNAME: "mempool"
      DATABASE_PASSWORD: "mempool"

      # Statistics
      STATISTICS_ENABLED: "true"

      # API settings
      MEMPOOL_API_URL_PREFIX: "/api/v1/"
      MEMPOOL_HTTP_PORT: "8999"

      # KEEP price-updater for exchange comparison
      MEMPOOL_PRICE_UPDATE_INTERVAL: "600"  # 10 minutes
    extra_hosts:
      - "host.docker.internal:host-gateway"

  # mempool frontend - Angular UI
  web:
    image: mempool/frontend:latest
    container_name: mempool-web
    restart: unless-stopped
    networks:
      - mempool-network
    depends_on:
      - api
    ports:
      - "8080:8080"
    environment:
      FRONTEND_HTTP_PORT: "8080"
      BACKEND_MAINNET_HTTP_HOST: "api"
    command: "./wait-for db:3306 --timeout=720 -- nginx -g 'daemon off;'"

EOF

echo "✅ docker-compose.yml created"
echo

# Step 3: Verify Bitcoin Core is running
echo "🔍 Verifying Bitcoin Core..."
if bitcoin-cli getblockcount &>/dev/null; then
    BLOCK_HEIGHT=$(bitcoin-cli getblockcount)
    echo "✅ Bitcoin Core running (height: $BLOCK_HEIGHT)"
else
    echo "❌ Bitcoin Core not responding!"
    echo "   Start bitcoind first: bitcoind -daemon"
    exit 1
fi

# Step 4: Detect actual Bitcoin datadir
echo
echo "🔍 Detecting Bitcoin Core datadir..."
ACTUAL_DATADIR=$(ps aux | grep bitcoind | grep -o '\-datadir=[^ ]*' | cut -d= -f2 || echo "$HOME/.bitcoin")
if [ -d "$ACTUAL_DATADIR" ]; then
    echo "✅ Bitcoin datadir: $ACTUAL_DATADIR"
    if [ "$ACTUAL_DATADIR" != "$BITCOIN_DATADIR" ]; then
        echo "⚠️  Warning: Datadir in script ($BITCOIN_DATADIR) differs from running Bitcoin Core ($ACTUAL_DATADIR)"
        echo "   You may need to update the docker-compose.yml volume mount"
    fi
else
    echo "⚠️  Could not detect Bitcoin datadir"
fi

# Step 5: Check Bitcoin Core RPC credentials
echo
echo "🔍 Checking Bitcoin Core authentication..."
BITCOIN_CONF="$HOME/.bitcoin/bitcoin.conf"
if [ -f "$BITCOIN_CONF" ]; then
    RPC_USER=$(grep "^rpcuser=" "$BITCOIN_CONF" | cut -d= -f2 || echo "bitcoinrpc")
    RPC_PASS=$(grep "^rpcpassword=" "$BITCOIN_CONF" | cut -d= -f2)
    echo "✅ Found bitcoin.conf"
    echo "   RPC User: $RPC_USER"
    echo "   RPC Pass: $RPC_PASS"
    echo "   (Cookie-based auth will be used: $RPC_USER:$RPC_PASS)"
else
    echo "⚠️  No bitcoin.conf found, using default credentials"
fi

# Step 6: Set correct permissions
echo
echo "🔒 Setting permissions..."
sudo chown -R sam:sam "$PROD_DIR/mempool-stack/"
echo "✅ Permissions set"

# Step 7: Display next steps
echo
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo
echo "📋 Next Steps:"
echo
echo "1. Start the stack:"
echo "   cd $PROD_DIR/mempool-stack"
echo "   docker compose up -d"
echo
echo "2. Monitor electrs sync (takes 3-4 hours on NVMe):"
echo "   docker compose logs -f electrs"
echo
echo "3. Check services:"
echo "   docker compose ps"
echo
echo "4. Verify APIs:"
echo "   curl http://localhost:8080          # Frontend"
echo "   curl http://localhost:3001          # electrs HTTP API (port 3001 to avoid Grafana conflict)"
echo "   curl http://localhost:8999/api/blocks/tip/height  # Backend API"
echo
echo "5. Access mempool.space UI:"
echo "   http://localhost:8080"
echo
echo "⏱️  Note: electrs initial sync = 3-4 hours on NVMe (much faster than HDD!)"
echo "💾 Database will use ~38GB on NVMe"
echo "📊 Monitor disk: watch -n 5 'du -sh $PROD_DIR/mempool-stack/data/electrs/'"
echo
echo "🔧 Configuration Notes:"
echo "   - electrs uses network_mode: host to access Bitcoin Core on 127.0.0.1"
echo "   - API connects to electrs via esplora REST API at http://$HOST_IP:3001"
echo "   - Port 3001 used instead of 3000 to avoid Grafana conflict"
echo "   - Backend mode: esplora (HTTP REST) instead of electrum (JSON-RPC)"
echo "   - Verbose logging enabled (-vvv) for troubleshooting"
echo
