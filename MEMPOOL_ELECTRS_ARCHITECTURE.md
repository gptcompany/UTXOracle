# 🏗️ Architettura Corretta: mempool.space + electrs

**IMPORTANTE**: mempool.space e electrs sono **progetti separati**, non un unico stack.

---

## 📦 Componenti Separati

### 1. Bitcoin Core (Già installato)
- **Repo**: https://github.com/bitcoin/bitcoin
- **Location**: Sistema operativo (bitcoind daemon)
- **Data**: `~/.bitcoin/` (blocks, chainstate, .cookie)
- **Ports**: 8332 (RPC), 8333 (P2P), 28332 (ZMQ)

### 2. electrs (Indexer Rust - Separato)
- **Repo**: https://github.com/romanz/electrs
- **Location**: `/media/sam/1TB/electrs/` (source code)
- **Database**: 38GB RocksDB index
- **Port**: 50001 (Electrum RPC)
- **Deploy**: Docker container SEPARATO
- **Purpose**: Indicizza blockchain per query veloci (address lookup, UTXO set, tx history)

### 3. mempool.space (Backend Node.js - Separato)
- **Repo**: https://github.com/mempool/mempool
- **Location**: `/media/sam/1TB/mempool/` (source code)
- **Database**: MariaDB (backend storage)
- **Port**: 8999 (REST API)
- **Deploy**: Docker container che si CONNETTE a electrs
- **Purpose**: API REST/WebSocket, fee estimates, mining stats, **price-updater (exchange APIs)**

### 4. mempool.space (Frontend Angular)
- **Included**: Nel repo mempool
- **Port**: 8080 (Nginx)
- **Deploy**: Docker container
- **Purpose**: UI web per visualizzare dati

---

## 🔗 Come Comunicano

```
┌─────────────────────────────────────────────────────────────┐
│                      HOST SYSTEM                             │
│                                                              │
│  Bitcoin Core (bitcoind)                                     │
│  ├─ RPC: 127.0.0.1:8332                                     │
│  ├─ Data: ~/.bitcoin/ (blocks, .cookie)                     │
│  └─ ZMQ: 127.0.0.1:28332 (rawtx stream)                     │
│                                                              │
└────────────┬─────────────────────────────────────────────────┘
             │
             │ Read blocks + RPC calls
             ▼
┌─────────────────────────────────────────────────────────────┐
│              Docker Container: electrs                       │
│                                                              │
│  electrs (Rust indexer)                                      │
│  ├─ Reads: /bitcoin/.cookie (auth)                          │
│  ├─ Reads: /bitcoin/blocks/*.dat (blockchain)               │
│  ├─ Writes: /data/ (38GB RocksDB index)                     │
│  ├─ Listens: 0.0.0.0:50001 (Electrum protocol)              │
│  └─ Initial sync: 8-12 hours                                 │
│                                                              │
└────────────┬─────────────────────────────────────────────────┘
             │
             │ Electrum protocol queries
             ▼
┌─────────────────────────────────────────────────────────────┐
│          Docker Container: mempool-api                       │
│                                                              │
│  mempool backend (Node.js)                                   │
│  ├─ Connects to: electrs:50001                              │
│  ├─ Connects to: Bitcoin Core RPC (host.docker.internal)    │
│  ├─ Connects to: MariaDB (db:3306)                          │
│  ├─ Listens: 0.0.0.0:8999 (REST API + WebSocket)            │
│  ├─ Cache: /backend/cache (NVMe)                            │
│  └─ price-updater: Fetches 5 exchange APIs every 10min      │
│                                                              │
└────────────┬─────────────────────────────────────────────────┘
             │
             │ HTTP API calls
             ▼
┌─────────────────────────────────────────────────────────────┐
│          Docker Container: mempool-web                       │
│                                                              │
│  mempool frontend (Angular + Nginx)                         │
│  ├─ Connects to: api:8999                                   │
│  ├─ Serves: Static HTML/JS/CSS                              │
│  └─ Listens: 0.0.0.0:8080 (HTTP)                            │
│                                                              │
└────────────┬─────────────────────────────────────────────────┘
             │
             │ Browser HTTP
             ▼
       User's Browser
       http://localhost:8080
```

---

## 🎯 Deployment Corretto su NVMe

### Directory Structure

```
/media/sam/2TB-NVMe/prod/apps/mempool-stack/
├── docker-compose.yml              # Unified orchestration
├── data/                           # All persistent data on NVMe
│   ├── electrs/                    # 38GB RocksDB (fast random reads)
│   ├── mysql/                      # ~2GB MariaDB (transactions)
│   └── cache/                      # ~500MB mempool cache
└── logs/                           # Application logs

/media/sam/1TB/                     # Source code (not deployed)
├── electrs/                        # electrs source (for reference)
└── mempool/                        # mempool source (for reference)
```

---

## 🚀 Startup Sequence

**Corretto ordine di avvio**:

```bash
# 1. Bitcoin Core (must be running)
bitcoind -daemon
bitcoin-cli getblockcount  # Verify synced

# 2. Start Docker stack (electrs + mempool + db)
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker-compose up -d

# 3. Monitor electrs sync (8-12 hours first time)
docker-compose logs -f electrs
# Wait for: "finished full compaction"

# 4. Check all services healthy
docker-compose ps
# All should show "Up" and healthy

# 5. Verify APIs
curl http://localhost:50001  # electrs (should connect)
curl http://localhost:8080   # Frontend
curl http://localhost:8999/api/blocks/tip/height  # Backend API

# 6. Access UI
firefox http://localhost:8080
```

---

## ⚙️ Configuration Mappings

### Bitcoin Core → electrs

**electrs needs**:
- Read access to `~/.bitcoin/.cookie` (authentication)
- Read access to `~/.bitcoin/blocks/*.dat` (blockchain data)

**Docker volume**:
```yaml
volumes:
  - ${HOME}/.bitcoin:/bitcoin:ro  # Read-only!
```

**Command**:
```bash
electrs --daemon-dir /bitcoin  # Uses /bitcoin/.cookie
```

---

### electrs → mempool backend

**mempool backend needs**:
- Connect to electrs on port 50001
- Know it's "electrum" protocol (not "esplora")

**Environment**:
```yaml
MEMPOOL_BACKEND: "electrum"      # romanz/electrs uses "electrum"
ELECTRUM_HOST: "electrs"         # Docker service name
ELECTRUM_PORT: "50001"
ELECTRUM_TLS_ENABLED: "false"
```

---

### Bitcoin Core RPC → mempool backend

**mempool backend needs**:
- Access Bitcoin Core RPC on host (127.0.0.1:8332)
- Use credentials from bitcoin.conf

**Environment**:
```yaml
CORE_RPC_HOST: "host.docker.internal"  # Special Docker hostname
CORE_RPC_PORT: "8332"
CORE_RPC_USERNAME: "bitcoinrpc"
CORE_RPC_PASSWORD: ""                  # Empty = use cookie
```

**Docker extra_hosts**:
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"  # Linux workaround
```

---

## 📊 Resource Requirements

| Component | CPU | RAM | Disk | Initial Sync |
|-----------|-----|-----|------|--------------|
| Bitcoin Core | 2 cores | 2GB | ~600GB | Already synced |
| electrs | 4 cores | 4GB | 38GB (NVMe) | **8-12 hours** |
| mempool backend | 1 core | 1GB | 2GB (MySQL) | ~10 minutes |
| mempool frontend | 0.5 core | 512MB | ~100MB | Instant |

**Total NVMe**: ~40GB

---

## 🔍 Verification Checklist

```bash
# 1. Bitcoin Core synced
bitcoin-cli getblockchaininfo | grep blocks
# Should match current height

# 2. electrs running and synced
docker logs mempool-electrs 2>&1 | tail -20
# Look for: "finished full compaction"
# Look for: "RPC server running on"

# 3. electrs responding
curl -s http://localhost:50001 | head -5
# Should get some response (not connection refused)

# 4. mempool backend healthy
docker ps --filter name=mempool-api
# Should show "Up" and "(healthy)"

# 5. Backend API working
curl http://localhost:8999/api/blocks/tip/height
# Should return current block height

# 6. Frontend serving
curl -s http://localhost:8080 | grep mempool
# Should return HTML with "mempool"

# 7. Database accessible
docker exec mempool-db mysql -umempool -pmempool -e "SHOW DATABASES;"
# Should list "mempool" database

# 8. Disk usage
du -sh /media/sam/2TB-NVMe/prod/apps/mempool-stack/data/*
# electrs: ~38GB, mysql: ~2GB, cache: ~500MB
```

---

## ⚠️ Common Issues & Fixes

### Issue 1: electrs Can't Connect to Bitcoin Core

**Symptom**:
```
ERROR - JSONRPC error: Connection refused
```

**Fix**:
```bash
# Check Bitcoin Core is running
bitcoin-cli getblockcount

# Verify .cookie file exists
ls -la ~/.bitcoin/.cookie

# Check docker volume mapping
docker inspect mempool-electrs | grep -A5 Mounts
```

---

### Issue 2: mempool backend Can't Connect to electrs

**Symptom**:
```
Error: connect ECONNREFUSED electrs:50001
```

**Fix**:
```bash
# Check electrs is running
docker ps --filter name=electrs

# Check electrs logs
docker logs mempool-electrs | tail -50

# Verify network
docker network inspect mempool-stack_mempool-network
```

---

### Issue 3: Frontend Shows "Backend Unavailable"

**Symptom**:
UI loads but shows error connecting to backend

**Fix**:
```bash
# Check API is running
curl http://localhost:8999/api/blocks/tip/height

# Check frontend environment
docker exec mempool-web env | grep BACKEND
# Should show: BACKEND_MAINNET_HTTP_HOST=api
```

---

## 🎯 For UTXOracle Integration

**What we need from this stack**:

1. **Exchange Prices** (for comparison):
   ```bash
   curl http://localhost:8999/api/v1/prices
   # Returns: {"USD": 67234, "EUR": 62100, ...}
   ```

2. **Real-time mempool** (optional - for live dashboard):
   ```bash
   ws://localhost:8999/api/v1/ws
   # Subscribe to mempool-blocks channel
   ```

3. **Historical blocks** (alternative to direct RPC):
   ```bash
   curl http://localhost:8999/api/block/000000000000000000...
   # Returns block with all transactions
   ```

**UTXOracle will**:
- Calculate on-chain price from RPC (Bitcoin Core direct)
- Fetch exchange price from mempool API
- Compare and store difference in DuckDB
- Visualize with Plotly

---

## 📚 References

- **electrs**: https://github.com/romanz/electrs
- **mempool.space**: https://github.com/mempool/mempool
- **Docker docs**: https://github.com/mempool/mempool/tree/master/docker
- **Setup script**: `/media/sam/1TB/UTXOracle/scripts/setup_full_mempool_stack.sh`

---

**Ready to deploy?** Run the setup script:

```bash
bash /media/sam/1TB/UTXOracle/scripts/setup_full_mempool_stack.sh
```
