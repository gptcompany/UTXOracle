# Whale Detection Dashboard - Production Deployment Guide

**Version**: 1.0
**Last Updated**: 2025-11-29
**Target Environment**: Ubuntu 22.04+ / Debian 12+

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Infrastructure Setup](#infrastructure-setup)
4. [Backend Deployment](#backend-deployment)
5. [Frontend Deployment](#frontend-deployment)
6. [Integration Service](#integration-service)
7. [Monitoring & Maintenance](#monitoring--maintenance)
8. [Security Hardening](#security-hardening)
9. [Troubleshooting](#troubleshooting)
10. [Backup & Recovery](#backup--recovery)

---

## Overview

The Whale Detection Dashboard is a real-time Bitcoin whale transaction monitoring system with the following architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    Production Stack                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐      ┌────────────────┐                   │
│  │ Bitcoin Core │◄─────┤ mempool.space  │                   │
│  │   RPC:8332   │      │  Docker Stack  │                   │
│  └──────────────┘      │  - electrs     │                   │
│         │              │  - backend     │                   │
│         │              │  - frontend    │                   │
│         │              │  - MariaDB     │                   │
│         │              └────────────────┘                   │
│         │                      │                             │
│         │                      │                             │
│         ▼                      ▼                             │
│  ┌─────────────────────────────────────┐                    │
│  │   Integration Service (Cron)        │                    │
│  │   - 3-Tier Transaction Fetching     │                    │
│  │   - UTXOracle Price Calculation     │                    │
│  │   - DuckDB Storage                  │                    │
│  └─────────────────────────────────────┘                    │
│                      │                                       │
│                      ▼                                       │
│  ┌─────────────────────────────────────┐                    │
│  │   FastAPI Backend (:8000)           │                    │
│  │   - REST API                        │                    │
│  │   - WebSocket Server                │                    │
│  │   - Static File Serving             │                    │
│  └─────────────────────────────────────┘                    │
│                      │                                       │
│                      ▼                                       │
│  ┌─────────────────────────────────────┐                    │
│  │   nginx Reverse Proxy (:80/:443)    │                    │
│  │   - SSL/TLS Termination             │                    │
│  │   - Rate Limiting                   │                    │
│  │   - Static Caching                  │                    │
│  └─────────────────────────────────────┘                    │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**Key Components**:
1. **Bitcoin Core** - Blockchain data source
2. **mempool.space Docker Stack** - Transaction indexing (electrs + mempool backend)
3. **Integration Service** - Price calculation & data collection (cron job)
4. **FastAPI Backend** - REST API + WebSocket server
5. **nginx** - Reverse proxy with SSL/TLS

**Technology Stack**:
- Python 3.8+ (FastAPI, uvicorn, websockets)
- DuckDB (embedded analytics database)
- Docker & Docker Compose (mempool stack)
- systemd (service management)
- nginx (reverse proxy)

---

## Prerequisites

### System Requirements

**Minimum**:
- **CPU**: 4 cores
- **RAM**: 8GB
- **Disk**: 1TB SSD/NVMe (for Bitcoin blockchain + electrs index)
- **Network**: 100 Mbps+ (for blockchain sync)

**Recommended**:
- **CPU**: 8+ cores
- **RAM**: 16GB+
- **Disk**: 2TB NVMe (blockchain: ~600GB, electrs: ~38GB, headroom)
- **Network**: 1 Gbps

### Software Requirements

```bash
# Ubuntu 22.04 / Debian 12
sudo apt update && sudo apt install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    docker.io \
    docker-compose \
    nginx \
    git \
    curl \
    jq \
    htop

# Install UV (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env
```

### User Setup

```bash
# Create dedicated user for UTXOracle
sudo useradd -m -s /bin/bash utxoracle
sudo usermod -aG docker utxoracle

# Switch to utxoracle user for remaining steps
sudo su - utxoracle
```

---

## Infrastructure Setup

### 1. Bitcoin Core Installation

**Option A: From Bitcoin.org (Recommended)**

```bash
# Download Bitcoin Core 27.0+ (verify GPG signatures in production!)
cd /tmp
wget https://bitcoincore.org/bin/bitcoin-core-27.0/bitcoin-27.0-x86_64-linux-gnu.tar.gz
tar -xzf bitcoin-27.0-x86_64-linux-gnu.tar.gz
sudo install -m 0755 -o root -g root -t /usr/local/bin bitcoin-27.0/bin/*

# Verify installation
bitcoin-cli --version
```

**Option B: From Ubuntu PPA**

```bash
sudo add-apt-repository ppa:luke-jr/bitcoincore
sudo apt update
sudo apt install -y bitcoind bitcoin-qt
```

### 2. Bitcoin Core Configuration

```bash
# Create Bitcoin data directory
mkdir -p ~/.bitcoin

# Create bitcoin.conf
cat > ~/.bitcoin/bitcoin.conf << 'EOF'
# Network
testnet=0                    # Mainnet (set to 1 for testnet)
prune=0                      # Full node (no pruning)

# RPC
server=1
rpcuser=utxoracle
rpcpassword=CHANGE_THIS_PASSWORD_IN_PRODUCTION
rpcallowip=127.0.0.1
rpcbind=127.0.0.1:8332

# Performance
dbcache=4096                 # 4GB cache (adjust based on RAM)
maxconnections=125

# ZMQ (for future real-time features)
# zmqpubhashtx=tcp://127.0.0.1:28332
# zmqpubrawblock=tcp://127.0.0.1:28333
# zmqpubrawtx=tcp://127.0.0.1:28332
EOF

# Secure permissions
chmod 600 ~/.bitcoin/bitcoin.conf
```

**Start Bitcoin Core**:

```bash
# Create systemd service
sudo tee /etc/systemd/system/bitcoind.service > /dev/null << 'EOF'
[Unit]
Description=Bitcoin Core Daemon
After=network.target

[Service]
Type=forking
User=utxoracle
Group=utxoracle
ExecStart=/usr/local/bin/bitcoind -daemon -conf=/home/utxoracle/.bitcoin/bitcoin.conf -datadir=/home/utxoracle/.bitcoin
ExecStop=/usr/local/bin/bitcoin-cli -conf=/home/utxoracle/.bitcoin/bitcoin.conf stop
Restart=on-failure
RestartSec=60
TimeoutStopSec=3600

# Hardening
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

# Start Bitcoin Core
sudo systemctl daemon-reload
sudo systemctl enable bitcoind
sudo systemctl start bitcoind

# Monitor sync progress (takes 1-3 days for initial sync)
bitcoin-cli -getinfo
```

### 3. mempool.space Docker Stack Setup

**Directory Structure**:

```bash
# Create project directory (on SSD/NVMe for best performance)
sudo mkdir -p /media/utxoracle/mempool-stack
sudo chown -R utxoracle:utxoracle /media/utxoracle/mempool-stack
cd /media/utxoracle/mempool-stack
```

**Docker Compose Configuration**:

```bash
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  # MariaDB - Transaction database
  mariadb:
    image: mariadb:10.11
    container_name: mempool-mariadb
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: mempool_root_password
      MYSQL_DATABASE: mempool
      MYSQL_USER: mempool
      MYSQL_PASSWORD: mempool_password
    volumes:
      - ./mariadb-data:/var/lib/mysql
    networks:
      - mempool-network

  # electrs - Electrum server (transaction indexing)
  electrs:
    image: getumbrel/electrs:v0.10.2
    container_name: mempool-electrs
    restart: always
    ports:
      - "127.0.0.1:3001:3001"  # HTTP API
      - "127.0.0.1:50001:50001"  # Electrum TCP
    volumes:
      - ./electrs-data:/data
      - /home/utxoracle/.bitcoin:/bitcoin:ro
    environment:
      ELECTRS_ELECTRUM_RPC_ADDR: 0.0.0.0:50001
      ELECTRS_DAEMON_RPC_ADDR: 172.17.0.1:8332
      ELECTRS_DAEMON_P2P_ADDR: 172.17.0.1:8333
      ELECTRS_MONITORING_ADDR: 0.0.0.0:4224
      ELECTRS_NETWORK: bitcoin
      ELECTRS_LOG_FILTERS: INFO
    networks:
      - mempool-network

  # mempool backend - API server
  mempool-backend:
    image: mempool/backend:latest
    container_name: mempool-backend
    restart: always
    ports:
      - "127.0.0.1:8999:8999"
    environment:
      MEMPOOL_BACKEND: "electrum"
      ELECTRUM_HOST: electrs
      ELECTRUM_PORT: 50001
      ELECTRUM_TLS_ENABLED: "false"
      CORE_RPC_HOST: 172.17.0.1
      CORE_RPC_PORT: 8332
      CORE_RPC_USERNAME: utxoracle
      CORE_RPC_PASSWORD: CHANGE_THIS_PASSWORD_IN_PRODUCTION
      DATABASE_ENABLED: "true"
      DATABASE_HOST: mariadb
      DATABASE_PORT: 3306
      DATABASE_DATABASE: mempool
      DATABASE_USERNAME: mempool
      DATABASE_PASSWORD: mempool_password
      STATISTICS_ENABLED: "true"
    depends_on:
      - mariadb
      - electrs
    networks:
      - mempool-network

  # mempool frontend - Web UI
  mempool-frontend:
    image: mempool/frontend:latest
    container_name: mempool-frontend
    restart: always
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      FRONTEND_HTTP_PORT: 8080
      BACKEND_MAINNET_HTTP_HOST: mempool-backend
    depends_on:
      - mempool-backend
    networks:
      - mempool-network

networks:
  mempool-network:
    driver: bridge

volumes:
  mariadb-data:
  electrs-data:
EOF
```

**Start mempool stack**:

```bash
# Pull images
docker-compose pull

# Start services
docker-compose up -d

# Monitor logs
docker-compose logs -f

# Check service status
docker-compose ps
```

**Wait for electrs sync** (~3-4 hours on NVMe):

```bash
# Monitor electrs sync
docker logs -f mempool-electrs

# Check sync status
curl -s http://localhost:3001/blocks/tip/height
# Should match: bitcoin-cli getblockcount
```

---

## Backend Deployment

### 1. Clone Repository

```bash
cd ~
git clone https://github.com/your-repo/UTXOracle.git
cd UTXOracle
```

### 2. Python Environment Setup

```bash
# Create virtual environment using UV
uv venv --python 3.11
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt

# Verify installation
python -c "import fastapi; import duckdb; import websockets; print('✅ Dependencies OK')"
```

### 3. Environment Configuration

```bash
# Create .env file
cat > .env << 'EOF'
# Bitcoin Core RPC
BITCOIN_RPC_URL=http://localhost:8332
BITCOIN_RPC_USER=utxoracle
BITCOIN_RPC_PASSWORD=CHANGE_THIS_PASSWORD_IN_PRODUCTION
BITCOIN_DATADIR=/home/utxoracle/.bitcoin

# mempool.space API
MEMPOOL_API_URL=http://localhost:8999
ELECTRS_API_URL=http://localhost:3001

# Database
DUCKDB_PATH=/home/utxoracle/UTXOracle/data/utxoracle.duckdb
DUCKDB_BACKUP_PATH=/home/utxoracle/UTXOracle/data/backups/utxoracle_backup.duckdb

# API Server
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=false

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/utxoracle/api.log

# CORS (production: set to your domain)
ALLOWED_ORIGINS=https://your-domain.com

# Privacy
MEMPOOL_PUBLIC_API_ENABLED=false  # Only use self-hosted infrastructure
EOF

# Secure permissions
chmod 600 .env
```

### 4. Database Initialization

```bash
# Create data directories
mkdir -p data/backups
mkdir -p /var/log/utxoracle

# Initialize DuckDB
python -c "
import duckdb
conn = duckdb.connect('data/utxoracle.duckdb')
conn.execute('''
    CREATE TABLE IF NOT EXISTS whale_prices (
        timestamp TIMESTAMP PRIMARY KEY,
        date DATE NOT NULL,
        utxoracle_price DOUBLE,
        exchange_price DOUBLE,
        confidence DOUBLE,
        transaction_count INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.close()
print('✅ Database initialized')
"
```

### 5. systemd Service Configuration

```bash
# Create service file
sudo tee /etc/systemd/system/utxoracle-api.service > /dev/null << 'EOF'
[Unit]
Description=UTXOracle Whale Detection API
After=network.target bitcoind.service docker.service
Requires=bitcoind.service

[Service]
Type=simple
User=utxoracle
Group=utxoracle
WorkingDirectory=/home/utxoracle/UTXOracle
Environment="PATH=/home/utxoracle/UTXOracle/.venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/home/utxoracle/UTXOracle/.env
ExecStart=/home/utxoracle/UTXOracle/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Hardening
PrivateTmp=true
NoNewPrivileges=true
ReadOnlyPaths=/etc
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/home/utxoracle/UTXOracle/data /var/log/utxoracle

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and start service
sudo systemctl daemon-reload
sudo systemctl enable utxoracle-api
sudo systemctl start utxoracle-api

# Check status
sudo systemctl status utxoracle-api

# View logs
sudo journalctl -u utxoracle-api -f
```

### 6. Test API

```bash
# Health check
curl http://localhost:8000/health

# Latest whale data
curl http://localhost:8000/api/whale/latest | jq

# Historical data
curl http://localhost:8000/api/whale/history?timeframe=24h | jq
```

---

## Frontend Deployment

The frontend is served as static files by FastAPI. No separate deployment needed.

**Verify static files**:

```bash
# Check frontend files
ls -lh frontend/
# Should see: whale_dashboard.html, css/, js/

# Test in browser
curl http://localhost:8000/static/whale_dashboard.html
```

---

## Integration Service

### 1. Cron Job Setup

The `daily_analysis.py` script runs every 10 minutes to:
- Fetch latest mempool transactions (3-tier: electrs → mempool.space → Bitcoin Core)
- Calculate UTXOracle price
- Compare with exchange price
- Store in DuckDB

**Install cron job**:

```bash
# Edit crontab
crontab -e

# Add this line (runs every 10 minutes)
*/10 * * * * cd /home/utxoracle/UTXOracle && .venv/bin/python scripts/daily_analysis.py >> /var/log/utxoracle/daily_analysis.log 2>&1
```

**Manual test**:

```bash
# Run once
cd ~/UTXOracle
.venv/bin/python scripts/daily_analysis.py

# Check logs
tail -f /var/log/utxoracle/daily_analysis.log
```

### 2. Backfill Historical Data (Optional)

```bash
# Backfill missing days automatically
.venv/bin/python scripts/daily_analysis.py --auto-backfill

# Backfill specific date range
.venv/bin/python scripts/daily_analysis.py --backfill-start 2025-11-01 --backfill-end 2025-11-15
```

---

## Monitoring & Maintenance

### 1. Health Checks

**API Health Check**:

```bash
# Local check
curl -f http://localhost:8000/health || echo "API DOWN"

# Setup monitoring cron (every 5 minutes)
crontab -e
# Add:
*/5 * * * * curl -sf http://localhost:8000/health > /dev/null || echo "UTXOracle API DOWN" | mail -s "Alert: UTXOracle API" admin@example.com
```

**Service Status Check**:

```bash
#!/bin/bash
# /usr/local/bin/check_utxoracle.sh

echo "=== UTXOracle Health Check ==="
echo "Timestamp: $(date)"
echo

# Bitcoin Core
if systemctl is-active --quiet bitcoind; then
    BLOCK_COUNT=$(bitcoin-cli getblockcount 2>/dev/null || echo "ERROR")
    echo "✅ Bitcoin Core: Running (Blocks: $BLOCK_COUNT)"
else
    echo "❌ Bitcoin Core: DOWN"
fi

# Docker Stack
if docker ps | grep -q mempool-electrs; then
    ELECTRS_HEIGHT=$(curl -s http://localhost:3001/blocks/tip/height || echo "ERROR")
    echo "✅ electrs: Running (Height: $ELECTRS_HEIGHT)"
else
    echo "❌ electrs: DOWN"
fi

# API
if systemctl is-active --quiet utxoracle-api; then
    API_STATUS=$(curl -s http://localhost:8000/health | jq -r '.status' 2>/dev/null || echo "ERROR")
    echo "✅ UTXOracle API: Running (Status: $API_STATUS)"
else
    echo "❌ UTXOracle API: DOWN"
fi

# Database
if [ -f ~/UTXOracle/data/utxoracle.duckdb ]; then
    DB_SIZE=$(du -h ~/UTXOracle/data/utxoracle.duckdb | cut -f1)
    echo "✅ DuckDB: OK (Size: $DB_SIZE)"
else
    echo "❌ DuckDB: MISSING"
fi

echo
echo "=== End Health Check ==="
```

### 2. Log Management

**Logrotate Configuration**:

```bash
sudo tee /etc/logrotate.d/utxoracle > /dev/null << 'EOF'
/var/log/utxoracle/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 utxoracle utxoracle
    sharedscripts
    postrotate
        systemctl reload utxoracle-api > /dev/null 2>&1 || true
    endscript
}
EOF
```

### 3. Resource Monitoring

```bash
# Check disk usage
df -h | grep -E "(Filesystem|bitcoin|mempool)"

# Check memory usage
free -h

# Check Docker resources
docker stats --no-stream

# Check database size
du -sh ~/UTXOracle/data/utxoracle.duckdb
```

---

## Security Hardening

### 1. Firewall Configuration

```bash
# Install ufw
sudo apt install -y ufw

# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (change port if using non-standard)
sudo ufw allow 22/tcp

# Allow nginx (if using reverse proxy)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status verbose
```

### 2. nginx Reverse Proxy (with SSL)

**Install certbot for Let's Encrypt**:

```bash
sudo apt install -y certbot python3-certbot-nginx
```

**nginx Configuration**:

```bash
sudo tee /etc/nginx/sites-available/utxoracle > /dev/null << 'EOF'
# Rate limiting zone
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=ws_limit:10m rate=5r/s;

# HTTP -> HTTPS redirect
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL certificates (managed by certbot)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # API endpoints
    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket endpoint
    location /ws/ {
        limit_req zone=ws_limit burst=10 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    # Static files (with caching)
    location /static/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        expires 1h;
        add_header Cache-Control "public, immutable";
    }

    # Root
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health check (no rate limit)
    location /health {
        proxy_pass http://127.0.0.1:8000;
        access_log off;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/utxoracle /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

### 3. Fail2ban (Optional)

```bash
# Install fail2ban
sudo apt install -y fail2ban

# Create jail for nginx rate limiting
sudo tee /etc/fail2ban/jail.d/nginx-rate-limit.conf > /dev/null << 'EOF'
[nginx-rate-limit]
enabled = true
port = http,https
filter = nginx-rate-limit
logpath = /var/log/nginx/error.log
maxretry = 10
findtime = 60
bantime = 3600
EOF

# Create filter
sudo tee /etc/fail2ban/filter.d/nginx-rate-limit.conf > /dev/null << 'EOF'
[Definition]
failregex = limiting requests, excess:.* by zone.*client: <HOST>
ignoreregex =
EOF

# Restart fail2ban
sudo systemctl restart fail2ban
```

---

## Troubleshooting

### Common Issues

#### 1. Bitcoin Core Not Syncing

```bash
# Check sync status
bitcoin-cli -getinfo

# Check connections
bitcoin-cli getconnectioncount

# Check logs
tail -f ~/.bitcoin/debug.log

# If stuck, restart
sudo systemctl restart bitcoind
```

#### 2. electrs Sync Slow/Stuck

```bash
# Check electrs logs
docker logs -f mempool-electrs

# Check disk I/O (should be on SSD/NVMe)
iostat -x 5

# Restart if needed
docker-compose restart electrs
```

#### 3. API Returns Empty Data

```bash
# Check DuckDB has data
python -c "
import duckdb
conn = duckdb.connect('data/utxoracle.duckdb')
print(conn.execute('SELECT COUNT(*) FROM whale_prices').fetchone())
conn.close()
"

# Run integration service manually
.venv/bin/python scripts/daily_analysis.py

# Check logs
tail -f /var/log/utxoracle/daily_analysis.log
```

#### 4. WebSocket Connection Fails

```bash
# Check if API is running
sudo systemctl status utxoracle-api

# Test WebSocket locally
python -c "
import asyncio
import websockets

async def test():
    async with websockets.connect('ws://localhost:8000/ws/whale') as ws:
        print('Connected!')
        await ws.send('{\"type\": \"subscribe\", \"channels\": [\"transactions\"]}')
        msg = await ws.recv()
        print(f'Received: {msg}')

asyncio.run(test())
"
```

### Performance Tuning

**If API is slow**:

```bash
# Increase uvicorn workers (in systemd service file)
ExecStart=... --workers 4  # Change from 2 to 4

# Restart API
sudo systemctl restart utxoracle-api
```

**If database queries are slow**:

```bash
# Create indices (if needed)
python -c "
import duckdb
conn = duckdb.connect('data/utxoracle.duckdb')
conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON whale_prices(timestamp)')
conn.execute('CREATE INDEX IF NOT EXISTS idx_date ON whale_prices(date)')
conn.close()
"
```

---

## Backup & Recovery

### 1. Automated Backups

```bash
# Create backup script
cat > ~/UTXOracle/scripts/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=/home/utxoracle/UTXOracle/data/backups
DATE=$(date +%Y%m%d_%H%M%S)

# DuckDB backup
cp /home/utxoracle/UTXOracle/data/utxoracle.duckdb "$BACKUP_DIR/utxoracle_$DATE.duckdb"

# Keep only last 7 days
find "$BACKUP_DIR" -name "utxoracle_*.duckdb" -mtime +7 -delete

# Compress old backups
find "$BACKUP_DIR" -name "utxoracle_*.duckdb" -mtime +1 ! -name "*$(date +%Y%m%d)*" -exec gzip {} \;

echo "Backup completed: utxoracle_$DATE.duckdb"
EOF

chmod +x ~/UTXOracle/scripts/backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
# Add:
0 2 * * * /home/utxoracle/UTXOracle/scripts/backup.sh >> /var/log/utxoracle/backup.log 2>&1
```

### 2. Restore from Backup

```bash
# Stop API
sudo systemctl stop utxoracle-api

# Restore database
cp /home/utxoracle/UTXOracle/data/backups/utxoracle_YYYYMMDD_HHMMSS.duckdb \
   /home/utxoracle/UTXOracle/data/utxoracle.duckdb

# Start API
sudo systemctl start utxoracle-api
```

### 3. Disaster Recovery

**If server crashes**:

1. **Reinstall OS** on new server
2. **Restore Bitcoin blockchain** from backup or re-sync (~3 days)
3. **Restore electrs index** from backup or re-sync (~4 hours)
4. **Deploy UTXOracle** using this guide
5. **Restore DuckDB** from backup
6. **Run backfill** for any missing days:
   ```bash
   .venv/bin/python scripts/daily_analysis.py --auto-backfill
   ```

---

## Production Checklist

Before going live, verify:

- [ ] Bitcoin Core fully synced (`bitcoin-cli -getinfo`)
- [ ] electrs fully synced (`curl localhost:3001/blocks/tip/height`)
- [ ] mempool backend running (`curl localhost:8999/api/v1/prices`)
- [ ] DuckDB initialized with data
- [ ] API health check passes (`curl localhost:8000/health`)
- [ ] Frontend loads (`curl localhost:8000/static/whale_dashboard.html`)
- [ ] WebSocket connects successfully
- [ ] Cron job running (`crontab -l`)
- [ ] systemd services enabled and running
- [ ] Firewall configured (`sudo ufw status`)
- [ ] SSL certificate valid (`sudo certbot certificates`)
- [ ] nginx reverse proxy working
- [ ] Backups configured and tested
- [ ] Monitoring/alerting configured
- [ ] Logs rotating correctly (`/etc/logrotate.d/utxoracle`)
- [ ] Resource usage normal (CPU < 50%, RAM < 80%, Disk < 80%)

---

## Support

For issues or questions:

- **GitHub Issues**: https://github.com/your-repo/UTXOracle/issues
- **API Documentation**: `/docs/WHALE_API_DOCUMENTATION.md`
- **Project Documentation**: `/README.md`

---

**Deployment Complete! 🐋**

Monitor your dashboard at: `https://your-domain.com`
