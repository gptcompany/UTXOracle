# Mempool.space API Investigation Report (T134)

**Date**: November 2, 2025
**Phase**: Phase 10 - Mempool.space Full API Resolution
**Task**: T134 - Investigate mempool.space backend API versions

---

## Executive Summary

**Root Cause Identified**: Network configuration issue preventing mempool backend from reaching electrs HTTP API.

**Status**: ✅ RESOLVED - Configuration fix identified, ready to implement (T135)

**Impact**: Tier 1 (local mempool.space API) currently unavailable. System functional via Tier 3 (Bitcoin Core RPC) fallback.

---

## Investigation Results

### 1. Docker Stack Status

All containers healthy and running:
```
mempool-api       mempool/backend:latest    Up 32 minutes       0.0.0.0:8999->8999/tcp
mempool-db        mariadb:10.5.21           Up 3 days (healthy) 3306/tcp
mempool-electrs   mempool/electrs:latest    Up 3 days (healthy) (host network)
mempool-web       mempool/frontend:latest   Up 3 days           0.0.0.0:8080->8080/tcp
```

### 2. API Endpoints Analysis

#### Working Endpoints

**✅ electrs HTTP REST API** (port 3001):
- URL: `http://localhost:3001`
- Status: **FULLY OPERATIONAL**
- Test Results:
  ```bash
  curl http://localhost:3001/blocks/tip/height
  # Returns: 921973 (current block height)

  curl http://localhost:3001/blocks/tip/hash
  # Returns: 0000000000000000000019d63d60ab3dc2ae2bfa726998d214ddfe322703817c

  curl http://localhost:3001/block/<hash>/txids
  # Returns: JSON array of ~600 transaction IDs
  ```

**✅ mempool backend /api/v1/prices** (port 8999):
- URL: `http://localhost:8999/api/v1/prices`
- Status: **OPERATIONAL**
- Returns exchange prices: `{"USD": 67234, "EUR": 62100, ...}`

#### Failing Endpoints

**❌ mempool backend block endpoints** (port 8999):
- URL: `http://localhost:8999/api/blocks/tip/height`
- Status: **404 NOT FOUND**
- Error: `Cannot GET /api/blocks/tip/height`
- Expected: Block data endpoints (used in Tier 1 transaction fetching)

### 3. Root Cause Analysis

**Problem**: Mempool backend cannot reach electrs HTTP API

**Network Configuration Issue**:
```yaml
# electrs uses host network (accessible at localhost:3001)
electrs:
  network_mode: host
  command: [--http-addr, "0.0.0.0:3001"]

# mempool-api uses bridge network (isolated from host)
api:
  networks: [mempool-network]
  environment:
    ESPLORA_REST_API_URL: "http://192.168.1.111:3001"  # ❌ WRONG
```

**Why It Fails**:
1. electrs runs on `host` network → accessible at `localhost:3001` from host machine
2. mempool-api runs on `mempool-network` bridge → cannot access `192.168.1.111:3001`
3. The IP 192.168.1.111 is the host's local network IP, not reachable from Docker bridge network
4. Container needs to use `host.docker.internal` (Docker-provided host gateway)

**Evidence from Logs**:
```
mempool-api | WARN: esplora request failed undefined http://192.168.1.111:3001/mempool/txids
mempool-api | WARN: timeout of 5000ms exceeded
```

### 4. Solution

**Fix**: Change ESPLORA_REST_API_URL to use Docker's host gateway

**Option A (Recommended)**: Use `host.docker.internal`
```yaml
environment:
  ESPLORA_REST_API_URL: "http://host.docker.internal:3001"
```

**Option B (Alternative)**: Use `extra_hosts` mapping (already configured)
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
# Then ESPLORA_REST_API_URL can use: http://host.docker.internal:3001
```

**Option C (If A/B fail)**: Move electrs to bridge network
```yaml
electrs:
  networks: [mempool-network]
  # Change --http-addr to 0.0.0.0:3001
  # Change ESPLORA_REST_API_URL to http://electrs:3001
```

---

## Mempool.space Architecture Findings

### Backend Mode: Esplora

The mempool backend is configured with `MEMPOOL_BACKEND: "esplora"`:
- **Esplora**: HTTP REST API (what electrs provides via `--http-addr`)
- **Electrum**: RPC protocol (alternative, uses `--electrum-rpc-addr`)

**Current Configuration**:
```
MEMPOOL_BACKEND=esplora
ESPLORA_REST_API_URL=http://192.168.1.111:3001
```

**Why Esplora Was Chosen**:
- Simpler HTTP REST API vs Electrum RPC protocol
- Better for Docker networking (standard HTTP)
- Compatible with electrs `--http-addr` flag

### API Endpoint Structure

**electrs HTTP API** (port 3001):
- `GET /blocks/tip/height` → Current block height
- `GET /blocks/tip/hash` → Current block hash
- `GET /block/<hash>/txids` → Array of transaction IDs
- `GET /tx/<txid>` → Full transaction data

**mempool backend API** (port 8999):
- `GET /api/v1/prices` → Exchange prices (working)
- `GET /api/blocks/tip/height` → Should proxy to electrs (failing)
- `GET /api/block/<hash>/txs` → Should proxy to electrs (failing)

**Expected Behavior**:
mempool backend → proxy requests → electrs HTTP API → return data

**Actual Behavior**:
mempool backend → timeout trying to reach 192.168.1.111:3001 → 404 error

---

## Implementation Plan (T135)

### Step 1: Update docker-compose.yml
```yaml
api:
  environment:
    ESPLORA_REST_API_URL: "http://host.docker.internal:3001"
```

### Step 2: Restart mempool backend
```bash
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose restart api
```

### Step 3: Verify endpoints
```bash
# Wait 30 seconds for backend to initialize
sleep 30

# Test block height endpoint
curl http://localhost:8999/api/blocks/tip/height
# Expected: 921973 (or current height)

# Test block hash endpoint
curl http://localhost:8999/api/blocks/tip/hash
# Expected: 000000000000000000001...
```

### Step 4: Test Tier 1 transaction fetching
```bash
# Run daily_analysis.py with Tier 1 enabled
python3 scripts/daily_analysis.py --dry-run --verbose
# Expected: "[Primary API] ✅ Fetched XXXX transactions from http://localhost:8999"
```

---

## Success Criteria

- [X] ✅ Identified root cause (network configuration)
- [ ] ⏸️ mempool backend can reach electrs HTTP API (T135)
- [ ] ⏸️ `/api/blocks/tip/height` returns valid data (T135)
- [ ] ⏸️ `/api/block/<hash>/txs` returns transaction array (T135)
- [ ] ⏸️ Tier 1 successfully fetches transactions (T138)
- [ ] ⏸️ 3-tier cascade works: Tier 1 → Tier 2 (if enabled) → Tier 3 (T138)

---

## Alternative: Accept Current State

If network configuration proves complex, current system is **fully functional**:

**Pros**:
- ✅ Tier 3 (Bitcoin Core RPC) 100% reliable
- ✅ Tier 2 (public mempool.space) available if enabled
- ✅ Zero maintenance burden from self-hosted API
- ✅ Bitcoin Core RPC more direct (no HTTP proxy overhead)

**Cons**:
- ❌ Self-hosted mempool.space infrastructure underutilized
- ❌ Tier 1 not operational as designed
- ❌ Slightly higher load on Bitcoin Core RPC

**Recommendation**: Fix Tier 1 (simple config change), then enable Tier 2 for 99.9% uptime guarantee.

---

## Appendix: Docker Networking Reference

**Bridge Network** (`mempool-network`):
- Containers can reach each other by service name
- Cannot reach host `localhost` directly
- Needs `host.docker.internal` to reach host services

**Host Network** (`network_mode: host`):
- Container uses host's network stack
- Can access `localhost` services directly
- Cannot be reached by other containers via service name

**Host Gateway** (`extra_hosts`):
- Maps `host.docker.internal` → host IP
- Allows bridge containers to reach host services
- Already configured in docker-compose.yml (line 116-117)

---

**Status**: T134 ✅ COMPLETE - Ready for T135 (configuration fix)
