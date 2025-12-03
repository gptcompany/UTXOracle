# UTXOracle Operations Runbook

**Version**: 1.0.0
**Feature Branch**: `003-mempool-integration-refactor`
**Last Updated**: 2025-10-26
**Status**: Production Ready

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Start/Stop Procedures](#startstop-procedures)
3. [Monitoring](#monitoring)
4. [Common Issues & Troubleshooting](#common-issues--troubleshooting)
5. [Maintenance Tasks](#maintenance-tasks)
6. [Disaster Recovery](#disaster-recovery)
7. [Configuration Files](#configuration-files)
8. [Appendix](#appendix)

---

## System Overview

### Architecture Diagram (ASCII)

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION ENVIRONMENT                    │
│                   /media/sam/2TB-NVMe/prod                   │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ Bitcoin Core  │    │ mempool.space │    │   UTXOracle   │
│   (External)  │    │     Stack     │    │   Analysis    │
│               │    │  (Docker)     │    │   Service     │
│ • RPC: 8332   │───▶│               │───▶│               │
│ • ZMQ: 28332  │    │ • electrs     │    │ • Cron Job    │
│ • Data: 3TB   │    │ • MariaDB     │    │ • DuckDB      │
│   WDC HDD     │    │ • Backend API │    │ • FastAPI     │
│               │    │ • Frontend UI │    │               │
└───────────────┘    └───────────────┘    └───────────────┘
       │                     │                     │
       │                     │                     │
       ▼                     ▼                     ▼
  ~/.bitcoin            localhost:8080      NVMe DuckDB Cache
  (Cookie Auth)        (Web Interface)     (/prod/apps/utxoracle)
```

### Component Dependencies

#### Critical Path (All required for full operation)

```
Bitcoin Core (Running)
    ↓
electrs (Synced) ──→ mempool.space Backend ──→ mempool.space Frontend
    ↓                        ↓
MariaDB (Healthy)            │
                             ↓
                    UTXOracle Cron Job ──→ DuckDB (NVMe)
                             ↓
                    FastAPI (Optional - for API access)
```

#### Component Locations

| Component | Location | Storage | Purpose |
|-----------|----------|---------|---------|
| Bitcoin Core | `/media/sam/3TB-WDC/Bitcoin` | 3TB HDD | Full node & RPC |
| electrs DB | `/media/sam/2TB-NVMe/prod/apps/mempool-stack/data/electrs` | 38GB NVMe | Transaction index |
| MariaDB | `/media/sam/2TB-NVMe/prod/apps/mempool-stack/data/mysql` | 2GB NVMe | mempool backend DB |
| DuckDB | `/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db` | ~100MB NVMe | Price history |
| Logs | `/media/sam/2TB-NVMe/prod/apps/mempool-stack/logs` | <1GB NVMe | System logs |

### Data Flow

1. **Bitcoin Core** → Serves blockchain data via RPC (port 8332)
2. **electrs** → Indexes transactions, provides Esplora REST API (port 3001)
3. **mempool Backend** → Aggregates data, provides JSON API (port 8999)
4. **mempool Frontend** → Web UI (port 8080)
5. **UTXOracle Cron** → Runs every 10 min, calculates price, saves to DuckDB
6. **FastAPI** (optional) → Serves DuckDB data via HTTP API

---

## Start/Stop Procedures

### 🟢 Starting All Services (Correct Order)

#### Step 1: Verify Bitcoin Core is Running

```bash
# Check Bitcoin Core status
bitcoin-cli getblockcount

# Expected output: Block height (e.g., 867123)
# If error: Start Bitcoin Core first
```

**If Bitcoin Core not running:**
```bash
bitcoind -daemon -datadir=/media/sam/3TB-WDC/Bitcoin

# Wait 30 seconds for startup
sleep 30

# Verify RPC accessible
bitcoin-cli -rpcconnect=127.0.0.1 -rpcport=8332 getblockcount
```

#### Step 2: Start mempool.space Stack (Docker)

```bash
# Navigate to mempool stack directory
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack

# Start all containers
docker compose up -d

# Expected output:
# [+] Running 4/4
#  ✔ Container mempool-db      Started
#  ✔ Container mempool-electrs Started
#  ✔ Container mempool-api     Started
#  ✔ Container mempool-web     Started
```

**Wait for services to be healthy (2-5 minutes):**
```bash
# Watch container status
watch -n 2 'docker compose ps'

# All should show "Up" and "(healthy)" status
# NAME              STATUS
# mempool-db        Up 2 minutes (healthy)
# mempool-electrs   Up 2 minutes (healthy)
# mempool-api       Up 2 minutes (healthy)
# mempool-web       Up 2 minutes (healthy)
```

#### Step 3: Verify electrs Sync Status

```bash
# Check electrs logs for sync status
docker compose logs electrs --tail 50

# Expected output (if synced):
# INFO electrs::db: Indexing height=867123 (finished)

# If syncing in progress:
# INFO electrs::db: Tx indexing is up to height=850000
```

**Check electrs database size (should be ~38GB when synced):**
```bash
du -sh data/electrs
# Expected: 38G data/electrs
```

#### Step 4: Test mempool.space APIs

```bash
# Test frontend (should return HTML)
curl -I http://localhost:8080
# Expected: HTTP/1.1 200 OK

# Test backend API (should return block height)
curl http://localhost:8999/api/v1/blocks/tip/height
# Expected: 867123 (current block height)

# Test electrs Esplora API (should return block hash)
curl http://localhost:3001/blocks/tip/hash
# Expected: 00000000000000000001a... (64-char hex)

# Test price endpoint (mempool.space exchange prices)
curl http://localhost:8999/api/v1/prices
# Expected: {"USD":67234.56,"EUR":...}
```

#### Step 5: Initialize DuckDB (First Time Only)

```bash
# Navigate to UTXOracle root
cd /media/sam/1TB/UTXOracle

# Initialize database schema
uv run python3 scripts/daily_analysis.py --init-db

# Expected output:
# 2025-10-26 14:00:00 [INFO] Database initialized: /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db
```

#### Step 6: Test UTXOracle Analysis (Manual)

```bash
# Run analysis in dry-run mode (no DB write)
uv run python3 scripts/daily_analysis.py --dry-run --verbose

# Expected output:
# 2025-10-26 14:00:05 [INFO] Starting daily analysis
# 2025-10-26 14:00:06 [INFO] Fetched mempool.space price: $67,234.56
# 2025-10-26 14:00:08 [INFO] UTXOracle price calculated
# 2025-10-26 14:00:08 [INFO] Price comparison
# 2025-10-26 14:00:08 [INFO] [DRY-RUN] Would save data:
# {
#   "timestamp": "2025-10-26 14:00:08",
#   "utxoracle_price": 67150.20,
#   "mempool_price": 67234.56,
#   "confidence": 0.85,
#   "tx_count": 1423,
#   "diff_amount": 84.36,
#   "diff_percent": 0.126,
#   "is_valid": true
# }
```

#### Step 7: Enable Cron Job (Production)

```bash
# Edit crontab
crontab -e

# Add this line (runs every 10 minutes)
*/10 * * * * cd /media/sam/1TB/UTXOracle && /home/sam/.cargo/bin/uv run python3 scripts/daily_analysis.py >> /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log 2>&1

# Save and exit

# Verify crontab
crontab -l | grep daily_analysis

# Expected output:
# */10 * * * * cd /media/sam/1TB/UTXOracle && ...
```

#### Step 8: Verify Cron Execution (Wait 10 Minutes)

```bash
# Check cron log
tail -f /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log

# Expected output (after next 10-minute mark):
# 2025-10-26 14:10:00 [INFO] Starting daily analysis
# 2025-10-26 14:10:02 [INFO] Daily analysis completed successfully
```

---

### 🔴 Stopping All Services (Graceful Shutdown)

#### Step 1: Disable Cron Job (Prevent Mid-Analysis Interruption)

```bash
# Temporarily disable cron
crontab -e

# Comment out the line with #
# */10 * * * * cd /media/sam/1TB/UTXOracle && ...

# Save and exit
```

#### Step 2: Wait for Running Analysis to Finish

```bash
# Check if analysis script is running
ps aux | grep daily_analysis.py

# If running, wait for completion (max 5 minutes)
# Monitor log:
tail -f /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log
```

#### Step 3: Stop mempool.space Stack

```bash
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack

# Graceful stop (waits for containers to finish)
docker compose stop

# Expected output:
# [+] Stopping 4/4
#  ✔ Container mempool-web     Stopped
#  ✔ Container mempool-api     Stopped
#  ✔ Container mempool-electrs Stopped
#  ✔ Container mempool-db      Stopped

# Verify containers stopped
docker compose ps -a
# All should show "Exited" status
```

#### Step 4: Stop Bitcoin Core (Optional - Only if Needed)

```bash
# Graceful shutdown (flushes caches, closes DB)
bitcoin-cli stop

# Wait for shutdown (can take 5-30 seconds)
# Expected output:
# Bitcoin Core stopping

# Verify stopped
ps aux | grep bitcoind
# Should return no results
```

---

### 🔄 Restarting Individual Components

#### Restart electrs Only

```bash
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack

# Restart container
docker compose restart electrs

# Wait 30 seconds for startup
sleep 30

# Verify healthy
docker compose ps electrs
# Expected: Up X seconds (healthy)

# Check logs
docker compose logs electrs --tail 20
```

#### Restart mempool Backend API Only

```bash
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack

docker compose restart api

# Wait 10 seconds
sleep 10

# Test API
curl http://localhost:8999/api/v1/blocks/tip/height
```

#### Restart MariaDB

```bash
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack

# ⚠️ WARNING: This will briefly interrupt mempool backend
docker compose restart db

# Wait for MariaDB startup (30 seconds)
sleep 30

# Verify healthy
docker compose ps db

# Restart dependent API service
docker compose restart api
```

#### Restart Entire Stack (Without Recreating Containers)

```bash
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack

# Stop all
docker compose stop

# Start all
docker compose start

# Verify all healthy
docker compose ps
```

---

### ✅ Post-Restart Verification Checklist

After any restart, verify these in order:

```bash
# 1. Bitcoin Core RPC responding
bitcoin-cli getblockcount
# ✅ Should return block height

# 2. electrs HTTP API responding
curl http://localhost:3001/blocks/tip/hash
# ✅ Should return block hash

# 3. MariaDB accepting connections
docker compose exec db mysqladmin ping -h localhost
# ✅ Should return "mysqld is alive"

# 4. mempool Backend API responding
curl http://localhost:8999/api/v1/prices
# ✅ Should return {"USD":...}

# 5. mempool Frontend responding
curl -I http://localhost:8080
# ✅ Should return HTTP/1.1 200 OK

# 6. DuckDB writable
ls -lah /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db
# ✅ Should exist and show recent modification time

# 7. Cron job scheduled
crontab -l | grep daily_analysis
# ✅ Should show uncommented cron entry
```

---

## Monitoring

### Key Metrics to Watch

#### 1. API Latency (mempool Backend)

**Why it matters**: Slow API = slow UTXOracle analysis

**How to check:**
```bash
# Test API response time
time curl http://localhost:8999/api/v1/prices

# Expected: <500ms
# Warning: >2s (backend struggling)
# Critical: >5s (backend failing)
```

**Dashboard query (if Prometheus configured):**
```promql
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

#### 2. DuckDB Database Growth

**Why it matters**: Unbounded growth = disk full = analysis failure

**How to check:**
```bash
# Current size
du -sh /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db

# Expected growth rate: ~10KB per analysis (every 10 min)
# Daily growth: ~1.4MB/day (10KB × 144 runs)
# Monthly growth: ~42MB/month
# Annual growth: ~500MB/year

# Warning: >1GB (investigate old data retention)
# Critical: >5GB (cleanup needed)
```

**Check oldest data:**
```sql
-- Connect to DuckDB
duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db

-- Query oldest record
SELECT MIN(timestamp) as oldest_data,
       MAX(timestamp) as newest_data,
       COUNT(*) as total_records
FROM prices;

-- Expected: oldest_data = 7-30 days ago
```

#### 3. Cron Job Execution

**Why it matters**: Missed executions = data gaps

**How to check:**
```bash
# Last 10 executions
tail -20 /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log | grep "completed successfully"

# Expected: 1 entry every 10 minutes
# Count executions in last hour (should be 6)
grep "$(date +%Y-%m-%d\ %H)" /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log | grep "completed successfully" | wc -l

# Expected: 6 (if full hour elapsed)
# Warning: <5 (missed executions)
# Critical: 0 (cron not running)
```

**Check for errors:**
```bash
# Errors in last 24 hours
grep ERROR /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log | tail -20
```

#### 4. electrs Sync Status

**Why it matters**: Out-of-sync electrs = stale mempool data

**How to check:**
```bash
# Check electrs height vs Bitcoin Core height
ELECTRS_HEIGHT=$(curl -s http://localhost:3001/blocks/tip/height)
BITCOIN_HEIGHT=$(bitcoin-cli getblockcount)

echo "electrs: $ELECTRS_HEIGHT"
echo "Bitcoin Core: $BITCOIN_HEIGHT"

# Expected: Difference = 0-2 blocks
# Warning: Difference = 3-10 blocks (electrs lagging)
# Critical: Difference >10 blocks (electrs stuck)
```

#### 5. Docker Container Health

**Why it matters**: Unhealthy containers = degraded service

**How to check:**
```bash
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack

# Check health status
docker compose ps

# All should show "(healthy)"
# Warning: "(health: starting)" for >5 minutes
# Critical: "unhealthy" or "Exited"
```

**Check container logs for errors:**
```bash
# Check all containers for ERROR logs
docker compose logs --tail 100 | grep ERROR

# Expected: No critical errors
# Warning: Occasional network timeouts (retryable)
# Critical: Persistent errors (service failure)
```

#### 6. Disk Space (NVMe)

**Why it matters**: Full disk = system failure

**How to check:**
```bash
# NVMe usage
df -h /media/sam/2TB-NVMe

# Expected usage breakdown:
# electrs DB: 38GB (static after sync)
# MariaDB: 2GB (grows slowly)
# DuckDB: <1GB (grows 42MB/month)
# Logs: <1GB (rotated)
# Total: ~45GB used of 2TB

# Warning: >80% full (1.6TB used)
# Critical: >95% full (1.9TB used)
```

---

### Using Health Check Script

**Currently**: No `scripts/health_check.sh` exists yet.

**TODO (T099)**: Create health check script that verifies all metrics above.

**Expected usage:**
```bash
# Manual health check
bash scripts/health_check.sh

# Expected output:
# ✅ Bitcoin Core RPC: OK (height: 867123)
# ✅ electrs sync: OK (0 blocks behind)
# ✅ mempool Backend API: OK (latency: 127ms)
# ✅ DuckDB: OK (size: 423MB, last write: 3 minutes ago)
# ✅ Cron job: OK (last run: 5 minutes ago)
# ✅ Disk space: OK (42GB / 2TB used, 21%)
#
# Overall Status: HEALTHY
```

**Automated monitoring (add to cron):**
```bash
# Run health check every hour, alert on failure
0 * * * * bash /media/sam/1TB/UTXOracle/scripts/health_check.sh || curl -X POST $ALERT_WEBHOOK_URL -d '{"status":"UNHEALTHY"}'
```

---

### Log Locations

| Component | Log Location | Rotation |
|-----------|--------------|----------|
| Bitcoin Core | `~/.bitcoin/debug.log` | Manual |
| electrs | Docker logs: `docker compose logs electrs` | Auto (Docker) |
| mempool API | Docker logs: `docker compose logs api` | Auto (Docker) |
| mempool Frontend | Docker logs: `docker compose logs web` | Auto (Docker) |
| MariaDB | Docker logs: `docker compose logs db` | Auto (Docker) |
| UTXOracle Cron | `/media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log` | Manual (logrotate) |
| systemd (future) | `journalctl -u utxoracle-*` | Auto (systemd) |

**View all Docker logs:**
```bash
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose logs --tail 100 --follow
```

**View UTXOracle cron logs:**
```bash
tail -f /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log
```

---

### Normal vs Abnormal Behavior

#### Normal Behavior

**electrs logs:**
```
INFO electrs::db: Indexing height=867123 (finished)
INFO electrs::server: Serving Electrum RPC on 127.0.0.1:50001
INFO electrs::server: Serving Esplora HTTP on 127.0.0.1:3001
```

**mempool Backend logs:**
```
Mempool Server is running on port 8999
Bitcoin Core RPC connected: mainnet
Electrs connected successfully
```

**UTXOracle cron logs:**
```
2025-10-26 14:00:00 [INFO] Starting daily analysis
2025-10-26 14:00:02 [INFO] Fetched mempool.space price: $67,234.56
2025-10-26 14:00:04 [INFO] UTXOracle price calculated
2025-10-26 14:00:04 [INFO] Price comparison
2025-10-26 14:00:04 [INFO] Data saved to /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db
2025-10-26 14:00:04 [INFO] Daily analysis completed successfully
```

#### Abnormal Behavior (Requires Investigation)

**electrs stuck:**
```
ERROR electrs::db: RocksDB write failed
INFO electrs::db: Adding 0 blocks (repeated)
```
→ See [Troubleshooting: electrs sync stuck](#issue-1-electrs-sync-stuck)

**mempool Backend errors:**
```
ERROR Cannot connect to electrs at http://192.168.1.111:3001
ERROR Bitcoin Core RPC timeout after 30s
```
→ See [Troubleshooting: API service won't start](#issue-2-api-service-wont-start)

**UTXOracle errors:**
```
ERROR Failed to fetch mempool price: Connection refused
ERROR Low confidence: 0.12 < 0.3
CRITICAL FALLBACK: Data saved to /tmp/utxoracle_backup.duckdb
CRITICAL FATAL: Both primary and backup DB writes failed
```
→ See [Troubleshooting sections](#common-issues--troubleshooting)

---

## Common Issues & Troubleshooting

### Issue 1: electrs Sync Stuck

**Symptoms:**
- electrs logs show "Adding 0 blocks" repeatedly
- Database size not growing
- electrs container healthy but not syncing

**Diagnosis:**
```bash
# Check logs
docker compose logs electrs --tail 50

# Check database growth
watch -n 5 'du -sh /media/sam/2TB-NVMe/prod/apps/mempool-stack/data/electrs'
# If size not changing for >5 minutes → stuck

# Check electrs height vs Bitcoin Core
curl -s http://localhost:3001/blocks/tip/height
bitcoin-cli getblockcount
# If difference >100 blocks → stuck
```

**Root Cause:**
- Database corruption from repeated container restarts during sync
- Partial RocksDB data (Phase 1 complete, Phase 2 empty)

**Solution (Nuclear Option - Requires 3-4 Hour Re-Sync):**
```bash
# 1. Stop stack
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose stop

# 2. Backup current database (optional)
sudo mv data/electrs data/electrs.backup-$(date +%Y%m%d-%H%M%S)

# 3. Create fresh directory
mkdir -p data/electrs

# 4. Start stack
docker compose up -d

# 5. Monitor sync (3-4 hours)
watch -n 10 'echo "Database size:"; du -sh data/electrs; echo; echo "Recent logs:"; docker compose logs electrs --tail 5'

# Expected output during sync:
# Database size:
# 264M  data/electrs
#
# Recent logs:
# INFO electrs::db: Tx indexing is up to height=50000
```

**Prevention:**
- Avoid container restarts during initial sync
- Get configuration right before starting sync
- Use `docker compose restart electrs` instead of `docker compose down && docker compose up`

---

### Issue 2: API Service Won't Start

**Symptoms:**
- mempool Backend container exits immediately
- Docker logs show "Cannot connect to electrs"
- `curl http://localhost:8999` refuses connection

**Diagnosis:**
```bash
# Check container status
docker compose ps api
# If "Exited (1)" → startup failure

# Check logs
docker compose logs api --tail 50
# Look for connection errors
```

**Common Causes & Solutions:**

#### Cause A: electrs Not Reachable

**Error in logs:**
```
ERROR Cannot connect to electrs at http://192.168.1.111:3001
```

**Solution:**
```bash
# 1. Verify electrs is running
docker compose ps electrs
# Should show "Up" and "(healthy)"

# 2. Test electrs API from host
curl http://localhost:3001/blocks/tip/hash
# Should return block hash

# 3. Check backend environment variable
docker compose exec api env | grep ESPLORA
# Should show: ESPLORA_REST_API_URL=http://192.168.1.111:3001

# 4. Verify host IP is correct
ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v 127.0.0.1
# Should match IP in ESPLORA_REST_API_URL

# 5. If IP changed, update docker-compose.yml
# Edit: /media/sam/2TB-NVMe/prod/apps/mempool-stack/docker-compose.yml
# Update: ESPLORA_REST_API_URL with new IP
# Restart: docker compose up -d --force-recreate api
```

#### Cause B: MariaDB Not Ready

**Error in logs:**
```
ERROR Cannot connect to MySQL: Connection refused
```

**Solution:**
```bash
# 1. Check MariaDB health
docker compose ps db
# Should show "(healthy)"

# 2. Test MariaDB connection
docker compose exec db mysqladmin ping -h localhost
# Should return "mysqld is alive"

# 3. Check backend wait-for script
docker compose logs api | grep "wait-for"
# Should show "waiting for db:3306"

# 4. Restart API (it will wait for DB)
docker compose restart api
```

#### Cause C: Bitcoin Core RPC Not Accessible

**Error in logs:**
```
ERROR Bitcoin Core RPC timeout
```

**Solution:**
```bash
# 1. Test Bitcoin Core RPC from host
bitcoin-cli getblockcount
# Should return block height

# 2. Check bitcoin.conf authentication
grep rpcpassword ~/.bitcoin/bitcoin.conf
# Should show password matching docker-compose.yml

# 3. Verify RPC credentials in docker-compose.yml
docker compose exec api env | grep CORE_RPC
# CORE_RPC_HOST=192.168.1.111
# CORE_RPC_PORT=8332
# CORE_RPC_USERNAME=bitcoinrpc
# CORE_RPC_PASSWORD=<should match bitcoin.conf>

# 4. Update credentials if needed
# Edit: docker-compose.yml
# Update: CORE_RPC_PASSWORD
# Restart: docker compose up -d --force-recreate api
```

---

### Issue 3: Cron Job Not Running

**Symptoms:**
- No new entries in cron log
- DuckDB not updated (old timestamps)
- No price analysis happening

**Diagnosis:**
```bash
# 1. Check crontab exists
crontab -l | grep daily_analysis
# Should show uncommented line

# 2. Check cron log for recent activity
tail -20 /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log
# Should show entries every 10 minutes

# 3. Check last cron execution time
stat /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log
# Modify time should be <10 minutes ago

# 4. Test script manually
cd /media/sam/1TB/UTXOracle
uv run python3 scripts/daily_analysis.py --dry-run
# Should complete without errors
```

**Common Causes & Solutions:**

#### Cause A: Crontab Entry Commented Out

**Solution:**
```bash
# Edit crontab
crontab -e

# Ensure line is NOT commented (no # at start)
# CORRECT:
*/10 * * * * cd /media/sam/1TB/UTXOracle && /home/sam/.cargo/bin/uv run python3 scripts/daily_analysis.py >> /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log 2>&1

# WRONG (commented):
# */10 * * * * cd /media/sam/1TB/UTXOracle && ...

# Save and exit
```

#### Cause B: Log Directory Not Writable

**Error (check syslog):**
```bash
grep CRON /var/log/syslog | tail -20
# Shows: "Permission denied" writing to log
```

**Solution:**
```bash
# Create log directory if missing
mkdir -p /media/sam/2TB-NVMe/prod/apps/utxoracle/logs

# Fix permissions
chmod 755 /media/sam/2TB-NVMe/prod/apps/utxoracle/logs
chown sam:sam /media/sam/2TB-NVMe/prod/apps/utxoracle/logs

# Test write
touch /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/test.log
# Should succeed without errors
```

#### Cause C: UV Not in Cron PATH

**Error (in cron log):**
```
/bin/sh: 1: uv: not found
```

**Solution:**
```bash
# Find UV path
which uv
# Output: /home/sam/.cargo/bin/uv

# Edit crontab
crontab -e

# Use absolute path to uv
*/10 * * * * cd /media/sam/1TB/UTXOracle && /home/sam/.cargo/bin/uv run python3 scripts/daily_analysis.py >> /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log 2>&1

# OR set PATH in crontab
PATH=/home/sam/.cargo/bin:/usr/local/bin:/usr/bin:/bin
*/10 * * * * cd /media/sam/1TB/UTXOracle && uv run python3 scripts/daily_analysis.py >> /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log 2>&1
```

#### Cause D: Script Crashing on Execution

**Diagnosis:**
```bash
# Run manually to see error
cd /media/sam/1TB/UTXOracle
uv run python3 scripts/daily_analysis.py --verbose

# Check for errors:
# - Import errors (missing dependencies)
# - Config errors (missing .env)
# - Permission errors (cannot read Bitcoin datadir)
```

**Solution depends on error**:
```bash
# If dependencies missing:
cd /media/sam/1TB/UTXOracle
uv sync

# If config missing:
cp .env.example .env
nano .env  # Edit configuration

# If permission error:
chmod 644 /media/sam/3TB-WDC/Bitcoin/bitcoin.conf
```

---

### Issue 4: DuckDB Write Failure

**Symptoms:**
- Cron log shows "CRITICAL: DuckDB write failed"
- Analysis runs but data not saved
- Fallback to `/tmp/utxoracle_backup.duckdb`

**Diagnosis:**
```bash
# Check error in cron log
grep "DuckDB write failed" /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log | tail -5

# Check disk space
df -h /media/sam/2TB-NVMe
# If >95% full → disk full issue

# Check file permissions
ls -lah /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db
# Should be owned by executing user (sam)

# Check directory permissions
ls -lah /media/sam/2TB-NVMe/prod/apps/utxoracle/data/
# Should be writable (755 or 775)
```

**Common Causes & Solutions:**

#### Cause A: Disk Full

**Solution:**
```bash
# 1. Free up space
# Check what's using space
du -sh /media/sam/2TB-NVMe/* | sort -h

# 2. Clean Docker images (if safe)
docker system prune -a --volumes
# WARNING: This removes unused containers/images

# 3. Clean logs
find /media/sam/2TB-NVMe -name "*.log" -mtime +30 -delete

# 4. Archive old DuckDB data
cd /media/sam/2TB-NVMe/prod/apps/utxoracle/data
duckdb utxoracle_cache.db "DELETE FROM prices WHERE timestamp < DATE_SUB(NOW(), INTERVAL 90 days)"
```

#### Cause B: File Permissions

**Solution:**
```bash
# Fix ownership
sudo chown sam:sam /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db

# Fix directory permissions
sudo chmod 755 /media/sam/2TB-NVMe/prod/apps/utxoracle/data

# Test write
cd /media/sam/1TB/UTXOracle
uv run python3 scripts/daily_analysis.py --dry-run
# Should complete without fallback
```

#### Cause C: Database Corruption

**Error:**
```
duckdb.IOException: IO Error: Cannot open database file
```

**Solution (Restore from Backup):**
```bash
# 1. Check if backup exists
ls -lah /tmp/utxoracle_backup.duckdb

# 2. Verify backup is readable
duckdb /tmp/utxoracle_backup.duckdb "SELECT COUNT(*) FROM prices"

# 3. Replace corrupted database
cd /media/sam/2TB-NVMe/prod/apps/utxoracle/data
mv utxoracle_cache.db utxoracle_cache.db.corrupted-$(date +%Y%m%d)
cp /tmp/utxoracle_backup.duckdb utxoracle_cache.db

# 4. Test
cd /media/sam/1TB/UTXOracle
uv run python3 scripts/daily_analysis.py --dry-run
```

---

### Issue 5: mempool API Unreachable

**Symptoms:**
- UTXOracle cron log shows "Failed to fetch mempool price"
- Connection refused or timeout
- Analysis script retries 3 times then fails

**Diagnosis:**
```bash
# 1. Test API manually
curl http://localhost:8999/api/v1/prices
# Should return: {"USD":67234.56,...}

# 2. Check mempool Backend container
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose ps api
# Should show "Up" and "(healthy)"

# 3. Check logs for errors
docker compose logs api --tail 50
```

**Common Causes & Solutions:**

#### Cause A: Backend Container Down

**Solution:**
```bash
# Restart backend
docker compose restart api

# Wait 30 seconds
sleep 30

# Test API
curl http://localhost:8999/api/v1/prices
```

#### Cause B: Backend Stuck (No Response)

**Solution:**
```bash
# Force recreate container
docker compose up -d --force-recreate api

# Monitor startup
docker compose logs -f api

# Should see:
# Mempool Server is running on port 8999
```

#### Cause C: electrs Connection Lost

**Backend logs show:**
```
ERROR Cannot connect to electrs
```

**Solution:**
```bash
# Check electrs health
docker compose ps electrs
curl http://localhost:3001/blocks/tip/hash

# If electrs down, restart it
docker compose restart electrs

# Then restart backend
docker compose restart api
```

---

### Issue 6: High Memory Usage

**Symptoms:**
- System slow or OOM killer activating
- Docker containers restarting unexpectedly
- `dmesg` shows OOM messages

**Diagnosis:**
```bash
# Check memory usage
free -h

# Check top consumers
docker stats --no-stream

# Expected usage:
# mempool-electrs: ~2-3GB
# mempool-api:     ~500MB
# mempool-db:      ~200MB
# mempool-web:     ~100MB
```

**Common Causes & Solutions:**

#### Cause A: electrs Memory Leak (Rare)

**Solution:**
```bash
# Restart electrs (it will recover sync state)
docker compose restart electrs

# Monitor memory
watch -n 5 'docker stats mempool-electrs --no-stream'
```

#### Cause B: MariaDB Query Cache Too Large

**Solution:**
```bash
# Connect to MariaDB
docker compose exec db mysql -u root -padmin

# Check cache size
SHOW VARIABLES LIKE 'query_cache%';

# Reduce if >256MB
SET GLOBAL query_cache_size = 134217728;  # 128MB

# Exit
exit
```

#### Cause C: Too Many Docker Logs

**Solution:**
```bash
# Truncate large logs
docker compose logs --tail 0 -f > /dev/null &
sleep 1
kill %1

# Configure log rotation in docker-compose.yml
# Add to each service:
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"

# Restart stack
docker compose up -d --force-recreate
```

---

### Issue 7: Disk Space Issues

**Symptoms:**
- "No space left on device" errors
- Docker containers failing to start
- DuckDB writes failing

**Diagnosis:**
```bash
# Check disk usage
df -h /media/sam/2TB-NVMe

# Check what's using space
du -sh /media/sam/2TB-NVMe/prod/apps/* | sort -h

# Expected usage:
# 38G   mempool-stack/data/electrs
# 2G    mempool-stack/data/mysql
# 1G    mempool-stack/data/cache
# 500M  utxoracle/data
# Total: ~45GB
```

**Solutions:**

#### Solution A: Clean Docker System

```bash
# Remove unused images/containers
docker system prune -a --volumes

# WARNING: This removes ALL unused Docker data
# Only run if you know what you're doing
```

#### Solution B: Rotate Logs

```bash
# Find large logs
find /media/sam/2TB-NVMe -name "*.log" -size +100M

# Truncate large logs
truncate -s 0 /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log

# Or compress old logs
gzip /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/*.log
```

#### Solution C: Archive Old DuckDB Data

```bash
# Export data older than 90 days
duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db <<EOF
COPY (SELECT * FROM prices WHERE timestamp < DATE_SUB(NOW(), INTERVAL 90 days))
TO '/media/sam/2TB-NVMe/prod/apps/utxoracle/archives/prices_archive_$(date +%Y%m%d).parquet'
(FORMAT PARQUET);
EOF

# Delete archived data
duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db <<EOF
DELETE FROM prices WHERE timestamp < DATE_SUB(NOW(), INTERVAL 90 days);
VACUUM;
EOF
```

---

## Maintenance Tasks

### Daily: Health Check

**Time Required**: 2 minutes

```bash
# Run health check script (TODO: Create this)
bash /media/sam/1TB/UTXOracle/scripts/health_check.sh

# Manual checks:
# 1. Check cron executed in last 10 minutes
tail -5 /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log

# 2. Check no errors in logs
grep ERROR /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log | grep "$(date +%Y-%m-%d)"

# 3. Verify Docker containers healthy
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack && docker compose ps

# 4. Check disk space
df -h /media/sam/2TB-NVMe | grep -v tmpfs
```

---

### Weekly: Log Review

**Time Required**: 10 minutes

```bash
# 1. Review UTXOracle errors (past 7 days)
grep ERROR /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log | grep -E "$(date -d '7 days ago' +%Y-%m-%d)|$(date +%Y-%m-%d)" | sort | uniq -c

# 2. Review Docker container restarts
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose ps -a | grep -v "Up"

# 3. Check for low confidence scores (< 0.3)
duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
  "SELECT COUNT(*) as low_confidence_count,
          MIN(confidence) as min_confidence
   FROM prices
   WHERE timestamp > DATE_SUB(NOW(), INTERVAL 7 days)
     AND is_valid = false"

# 4. Review disk space trend
du -sh /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db
# Compare to last week (should grow ~10MB/week)

# 5. Check electrs sync status
docker compose logs electrs --tail 50 | grep -E "(Indexing|up to height)"
```

---

### Monthly: Verify Backups

**Time Required**: 15 minutes

```bash
# 1. Test DuckDB backup restore
# Create test backup
cp /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
   /tmp/utxoracle_test_restore.db

# Verify readable
duckdb /tmp/utxoracle_test_restore.db "SELECT COUNT(*) FROM prices"
# Should return total record count

# Query recent data
duckdb /tmp/utxoracle_test_restore.db \
  "SELECT MAX(timestamp) FROM prices"
# Should be within last 10 minutes

# Clean up
rm /tmp/utxoracle_test_restore.db

# 2. Archive old DuckDB data (>90 days)
# (See "Disk Space Issues" section above)

# 3. Verify electrs database health
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose exec electrs ls -lh /data
# Total size should be stable (~38GB)

# 4. Review price divergence trends
duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
  "SELECT
     AVG(diff_percent) as avg_diff,
     MAX(ABS(diff_percent)) as max_diff,
     STDDEV(diff_percent) as stddev_diff
   FROM prices
   WHERE timestamp > DATE_SUB(NOW(), INTERVAL 30 days)
     AND is_valid = true"

# Expected:
# avg_diff: -1% to +1%
# max_diff: <5%
# stddev_diff: <2%

# 5. Update dependencies
cd /media/sam/1TB/UTXOracle
uv sync --upgrade
uv run pytest tests/  # Verify tests pass
```

---

### Quarterly: Performance Review

**Time Required**: 30 minutes

```bash
# 1. Analyze cron execution time trends
grep "completed successfully" /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log | \
  awk '{print $(NF-1)}' | \
  awk -F: '{print $1*3600 + $2*60 + $3}' | \
  awk '{sum+=$1; count++} END {print "Avg execution time:", sum/count "seconds"}'

# Expected: <5 seconds average
# Warning: >10 seconds (investigate slow queries)

# 2. Review DuckDB query performance
duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
  "SELECT COUNT(*) as total_records,
          MIN(timestamp) as oldest,
          MAX(timestamp) as newest,
          (MAX(timestamp) - MIN(timestamp)) / INTERVAL '1 day' as days_of_data
   FROM prices"

# 3. Check mempool API latency trend
# (TODO: Implement Prometheus metrics)

# 4. Review disk usage growth rate
# Compare current vs 3 months ago
du -sh /media/sam/2TB-NVMe/prod/apps/mempool-stack/data/mysql
du -sh /media/sam/2TB-NVMe/prod/apps/utxoracle/data

# 5. Update system documentation
# Review this runbook, update any changed procedures
nano /media/sam/1TB/UTXOracle/docs/OPERATIONS.md
```

---

## Disaster Recovery

### Scenario 1: DuckDB Database Corruption

**Situation**: Database file unreadable, primary write fails

**Recovery Steps:**

```bash
# Step 1: Verify corruption
duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
  "SELECT COUNT(*) FROM prices"
# If error → database corrupted

# Step 2: Check fallback backup
ls -lah /tmp/utxoracle_backup.duckdb
# Should exist if fallback triggered

# Step 3: Verify fallback data
duckdb /tmp/utxoracle_backup.duckdb \
  "SELECT MAX(timestamp), COUNT(*) FROM prices"
# Check data is recent

# Step 4: Restore from fallback
cd /media/sam/2TB-NVMe/prod/apps/utxoracle/data
mv utxoracle_cache.db utxoracle_cache.db.corrupted-$(date +%Y%m%d-%H%M%S)
cp /tmp/utxoracle_backup.duckdb utxoracle_cache.db

# Step 5: Verify restored database
duckdb utxoracle_cache.db "SELECT MAX(timestamp), COUNT(*) FROM prices"

# Step 6: Resume normal operations
cd /media/sam/1TB/UTXOracle
uv run python3 scripts/daily_analysis.py --verbose
# Should complete successfully

# Step 7: Notify admin (if webhook configured)
curl -X POST $ALERT_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"status":"RECOVERED","message":"DuckDB restored from fallback"}'
```

**Data Loss**: Up to 10 minutes (since last cron execution)

---

### Scenario 2: electrs Index Corrupted

**Situation**: electrs database corrupted, service won't start

**Recovery Steps:**

```bash
# Step 1: Verify corruption
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose logs electrs | grep -E "(ERROR|panic)"

# Step 2: Stop stack
docker compose stop

# Step 3: Backup corrupted database (for investigation)
sudo mv data/electrs data/electrs.corrupted-$(date +%Y%m%d-%H%M%S)

# Step 4: Create fresh directory
mkdir -p data/electrs
sudo chown sam:sam data/electrs

# Step 5: Start stack (begins re-sync)
docker compose up -d

# Step 6: Monitor re-sync progress (3-4 hours on NVMe)
watch -n 30 'echo "Database size:"; du -sh data/electrs; echo; docker compose logs electrs --tail 3'

# Step 7: Verify sync completion
curl http://localhost:3001/blocks/tip/height
bitcoin-cli getblockcount
# Heights should match

# Step 8: Resume UTXOracle cron
crontab -e
# Uncomment cron line if disabled
```

**Downtime**: 3-4 hours (electrs re-sync time)

---

### Scenario 3: Full NVMe Disk

**Situation**: NVMe 100% full, all services failing

**Recovery Steps:**

```bash
# Step 1: Identify what's using space
du -sh /media/sam/2TB-NVMe/* | sort -h | tail -10

# Step 2: Emergency cleanup (free ~5GB)
# Option A: Clean Docker
docker system prune -a --volumes --force

# Option B: Compress logs
find /media/sam/2TB-NVMe -name "*.log" -size +100M -exec gzip {} \;

# Option C: Archive old DuckDB data
duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
  "DELETE FROM prices WHERE timestamp < DATE_SUB(NOW(), INTERVAL 30 days); VACUUM;"

# Step 3: Verify space freed
df -h /media/sam/2TB-NVMe
# Should now have >5GB free

# Step 4: Restart services
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose restart

# Step 5: Test DuckDB write
cd /media/sam/1TB/UTXOracle
uv run python3 scripts/daily_analysis.py --verbose

# Step 6: Set up monitoring alert (prevent recurrence)
# Add to cron:
# 0 * * * * df -h /media/sam/2TB-NVMe | awk '$5 ~ /^9[0-9]%/ {print "Disk critical:", $5}' | xargs -r -I {} curl -X POST $ALERT_WEBHOOK_URL -d '{"alert":"{}"}'
```

**Prevention**:
- Set up disk space monitoring (alert at 80%)
- Implement log rotation (max 1GB logs)
- Archive DuckDB data monthly (>90 days)

---

### Scenario 4: Complete System Failure (Server Reboot)

**Situation**: Power loss, kernel panic, hardware failure

**Recovery Steps:**

```bash
# Step 1: Verify Bitcoin Core auto-started
ps aux | grep bitcoind
bitcoin-cli getblockcount
# If not running:
bitcoind -daemon -datadir=/media/sam/3TB-WDC/Bitcoin

# Step 2: Check Docker service
sudo systemctl status docker
# If not running:
sudo systemctl start docker

# Step 3: Start mempool stack
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose up -d

# Step 4: Wait for services to become healthy (2-5 minutes)
watch -n 5 'docker compose ps'

# Step 5: Verify electrs sync status
docker compose logs electrs --tail 50
curl http://localhost:3001/blocks/tip/height

# Step 6: Test mempool API
curl http://localhost:8999/api/v1/prices

# Step 7: Enable UTXOracle cron
crontab -l | grep daily_analysis
# If missing or commented, re-enable

# Step 8: Run manual analysis test
cd /media/sam/1TB/UTXOracle
uv run python3 scripts/daily_analysis.py --verbose

# Step 9: Monitor for 30 minutes
tail -f /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log
```

**Expected Recovery Time**: 5-10 minutes

---

### Scenario 5: Full Stack Redeploy (Nuclear Option)

**Situation**: Need to rebuild everything from scratch

**Recovery Steps:**

```bash
# Step 1: Backup critical data
mkdir -p /tmp/utxoracle-backup-$(date +%Y%m%d)

# Backup DuckDB
cp /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
   /tmp/utxoracle-backup-$(date +%Y%m%d)/

# Backup config
cp /media/sam/1TB/UTXOracle/.env \
   /tmp/utxoracle-backup-$(date +%Y%m%d)/

# Step 2: Stop and remove all containers
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose down -v

# Step 3: Remove all data (DESTRUCTIVE!)
sudo rm -rf data/*

# Step 4: Recreate directory structure
mkdir -p data/{electrs,mysql,cache}

# Step 5: Re-run setup script
bash /media/sam/1TB/UTXOracle/scripts/setup_full_mempool_stack.sh

# Step 6: Start stack (electrs will re-sync 3-4 hours)
docker compose up -d

# Step 7: Monitor electrs sync
watch -n 60 'du -sh data/electrs'

# Step 8: Restore DuckDB after electrs sync complete
cp /tmp/utxoracle-backup-$(date +%Y%m%d)/utxoracle_cache.db \
   /media/sam/2TB-NVMe/prod/apps/utxoracle/data/

# Step 9: Restore config
cp /tmp/utxoracle-backup-$(date +%Y%m%d)/.env \
   /media/sam/1TB/UTXOracle/

# Step 10: Re-enable cron
crontab -e
# Add cron line (see Start/Stop Procedures)

# Step 11: Test full workflow
cd /media/sam/1TB/UTXOracle
uv run python3 scripts/daily_analysis.py --verbose
```

**Total Time**: 4-5 hours (mostly electrs sync)

---

## Configuration Files

### Primary Configurations

#### 1. docker-compose.yml (mempool Stack)

**Location**: `/media/sam/2TB-NVMe/prod/apps/mempool-stack/docker-compose.yml`

**Purpose**: Defines all mempool.space stack containers

**Key Settings**:

```yaml
# electrs settings
services:
  electrs:
    network_mode: host  # CRITICAL: Allows 127.0.0.1 Bitcoin Core access
    command:
      - --http-addr
      - 127.0.0.1:3001  # Esplora HTTP API (port 3001 to avoid Grafana conflict)
      - --electrum-rpc-addr
      - 127.0.0.1:50001  # Electrum RPC (for wallets)

  api:
    environment:
      MEMPOOL_BACKEND: "esplora"  # Use HTTP REST API, not Electrum RPC
      ESPLORA_REST_API_URL: "http://192.168.1.111:3001"  # electrs connection
      CORE_RPC_HOST: "192.168.1.111"  # Bitcoin Core RPC
```

**How to Change**:
```bash
# 1. Edit file
nano /media/sam/2TB-NVMe/prod/apps/mempool-stack/docker-compose.yml

# 2. Validate syntax
docker compose config

# 3. Apply changes (recreates containers)
docker compose up -d --force-recreate

# 4. Verify health
docker compose ps
```

**Safety Notes**:
- Changing `network_mode` requires container recreation
- Changing ports requires checking for conflicts first (`sudo lsof -i :PORT`)
- Never change `volumes` while containers running (data loss risk)

---

#### 2. .env (UTXOracle Configuration)

**Location**: `/media/sam/1TB/UTXOracle/.env`

**Purpose**: Environment variables for UTXOracle analysis script

**Template**:
```bash
# Database
DUCKDB_PATH=/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db
DUCKDB_BACKUP_PATH=/tmp/utxoracle_backup.duckdb

# Bitcoin Core
BITCOIN_DATADIR=/media/sam/3TB-WDC/Bitcoin

# mempool.space API
MEMPOOL_API_URL=http://localhost:8999

# Validation thresholds
UTXORACLE_CONFIDENCE_THRESHOLD=0.3
MIN_PRICE_USD=10000
MAX_PRICE_USD=500000

# Logging
LOG_LEVEL=INFO

# Cron schedule
ANALYSIS_INTERVAL_MINUTES=10

# Alerts (optional)
ALERT_WEBHOOK_URL=https://n8n.example.com/webhook/utxoracle-alerts
```

**How to Change**:
```bash
# 1. Edit file
nano /media/sam/1TB/UTXOracle/.env

# 2. Test changes (dry-run mode)
cd /media/sam/1TB/UTXOracle
uv run python3 scripts/daily_analysis.py --dry-run --verbose

# 3. No restart needed (cron reads .env on each execution)
```

**Safety Notes**:
- Never commit `.env` to git (contains paths/credentials)
- Always test with `--dry-run` before production use
- Backup `.env` before making changes: `cp .env .env.backup`

---

#### 3. bitcoin.conf (Bitcoin Core RPC)

**Location**: `~/.bitcoin/bitcoin.conf` or `/media/sam/3TB-WDC/Bitcoin/bitcoin.conf`

**Purpose**: Bitcoin Core RPC authentication

**Relevant Settings**:
```ini
# RPC server
server=1
rpcuser=bitcoinrpc
rpcpassword=$(openssl rand -hex 32)
rpcallowip=127.0.0.1

# ZMQ (for future real-time features)
zmqpubhashtx=tcp://127.0.0.1:28332
zmqpubrawtx=tcp://127.0.0.1:28332
zmqpubrawblock=tcp://127.0.0.1:28333
```

**How to Change**:
```bash
# 1. Edit bitcoin.conf
nano ~/.bitcoin/bitcoin.conf

# 2. Restart Bitcoin Core (CAUTION: Stops node)
bitcoin-cli stop
# Wait for shutdown (5-30 seconds)
bitcoind -daemon

# 3. Update docker-compose.yml with new credentials
nano /media/sam/2TB-NVMe/prod/apps/mempool-stack/docker-compose.yml
# Update: CORE_RPC_PASSWORD

# 4. Restart mempool stack
docker compose up -d --force-recreate api
```

**Safety Notes**:
- Changing `rpcpassword` breaks existing connections (update all consumers)
- Never expose RPC to public internet (`rpcallowip` should be local only)
- Cookie file auto-generated (in `~/.bitcoin/.cookie`)

---

#### 4. crontab (Scheduled Tasks)

**Location**: User crontab (edit with `crontab -e`)

**Purpose**: Schedule UTXOracle analysis every 10 minutes

**Current Configuration**:
```cron
# UTXOracle price analysis (runs every 10 minutes)
*/10 * * * * cd /media/sam/1TB/UTXOracle && /home/sam/.cargo/bin/uv run python3 scripts/daily_analysis.py >> /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log 2>&1
```

**How to Change**:
```bash
# 1. Edit crontab
crontab -e

# 2. Change schedule (examples):
# Every 5 minutes:
*/5 * * * * ...

# Every 15 minutes:
*/15 * * * * ...

# Hourly at :00:
0 * * * * ...

# Every 6 hours:
0 */6 * * * ...

# 3. Save and exit (cron automatically reloads)

# 4. Verify new schedule
crontab -l
```

**Safety Notes**:
- Always use absolute paths in crontab (cron has minimal `$PATH`)
- Test script manually before adding to cron
- Logs to file, not stdout (cron doesn't show console output)

---

### Configuration Hierarchy

**Priority order** (highest to lowest):

1. **Environment variables** (set in shell)
   ```bash
   export DUCKDB_PATH=/custom/path.db
   uv run python3 scripts/daily_analysis.py
   ```

2. **`.env` file** (in project root)
   ```bash
   # .env
   DUCKDB_PATH=/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db
   ```

3. **Hardcoded defaults** (in `daily_analysis.py`)
   ```python
   config = {
       "DUCKDB_PATH": os.getenv("DUCKDB_PATH", "./utxoracle.duckdb"),  # Default
   }
   ```

**Best Practice**: Use `.env` file for deployment-specific values, let script defaults handle development.

---

## Appendix

### A. Port Reference

| Service | Port | Protocol | Purpose |
|---------|------|----------|---------|
| Bitcoin Core RPC | 8332 | HTTP | RPC API |
| Bitcoin Core ZMQ | 28332 | TCP | Transaction stream |
| Bitcoin Core ZMQ | 28333 | TCP | Block stream |
| electrs Electrum | 50001 | TCP | Electrum wallet RPC |
| electrs Esplora | 3001 | HTTP | REST API (changed from 3000 to avoid Grafana) |
| electrs Monitoring | 4224 | HTTP | Health check |
| MariaDB | 3306 | TCP | MySQL (internal Docker network) |
| mempool Backend | 8999 | HTTP | JSON API |
| mempool Frontend | 8080 | HTTP | Web UI |
| FastAPI (future) | 8000 | HTTP | UTXOracle API |

---

### B. File Sizes Reference

| File/Directory | Expected Size | Growth Rate |
|----------------|---------------|-------------|
| electrs DB | 38GB | Static (after sync) |
| MariaDB | 2GB | ~100MB/month |
| DuckDB | 100-500MB | ~42MB/month |
| Logs (cron) | 10-50MB | ~10MB/month (before rotation) |
| Docker images | 5GB | Static (unless updated) |

---

### C. Command Quick Reference

```bash
# === Bitcoin Core ===
bitcoin-cli getblockcount          # Current block height
bitcoin-cli getmempoolinfo         # Mempool stats
bitcoin-cli stop                   # Graceful shutdown

# === Docker (mempool stack) ===
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose ps                  # Container status
docker compose logs -f electrs     # Follow electrs logs
docker compose restart api         # Restart backend
docker compose stop                # Stop all
docker compose up -d               # Start all

# === electrs ===
curl http://localhost:3001/blocks/tip/height  # Current height
curl http://localhost:3001/blocks/tip/hash    # Current block hash
du -sh data/electrs                           # Database size

# === mempool.space ===
curl http://localhost:8999/api/v1/prices      # Exchange prices
curl http://localhost:8080                    # Frontend (HTML)

# === UTXOracle ===
cd /media/sam/1TB/UTXOracle
uv run python3 scripts/daily_analysis.py --dry-run  # Test run
uv run python3 scripts/daily_analysis.py --init-db  # Initialize DB
tail -f /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/cron.log  # Monitor cron

# === DuckDB ===
duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db
> SELECT * FROM prices ORDER BY timestamp DESC LIMIT 10;
> .quit

# === Cron ===
crontab -l                         # List cron jobs
crontab -e                         # Edit cron jobs
grep CRON /var/log/syslog          # Cron execution log

# === System ===
df -h /media/sam/2TB-NVMe          # Disk space
free -h                            # Memory usage
docker stats --no-stream           # Container resource usage
```

---

### D. Emergency Contact Info

**System Owner**: sam
**Repository**: `/media/sam/1TB/UTXOracle`
**NVMe Mount**: `/media/sam/2TB-NVMe/prod`

**Critical Escalation**:
- If electrs stuck >1 hour → See [Issue 1](#issue-1-electrs-sync-stuck)
- If disk >95% full → See [Scenario 3](#scenario-3-full-nvme-disk)
- If complete failure → See [Scenario 4](#scenario-4-complete-system-failure-server-reboot)

**Alerting** (if configured):
- Webhook URL: Set in `.env` as `ALERT_WEBHOOK_URL`
- Alert triggers: Cron failure, low confidence, DB write failure

---

### E. Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-10-26 | Initial runbook for spec-003 production |

---

**Document Status**: ✅ Production Ready
**Next Review**: 2026-01-26 (Quarterly)

---

**End of Operations Runbook**
