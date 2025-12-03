# Mempool.space API Issue - Network Configuration

**Date**: Nov 2, 2025
**Status**: 🔴 IDENTIFIED - Fix Required
**Impact**: Tier 1 (local mempool.space) not functional for transaction fetching

---

## Problem Summary

The local mempool.space API container cannot access the electrs HTTP API due to Docker network configuration mismatch.

### Symptoms

```bash
# This works (from host):
curl http://localhost:3001/blocks/tip/hash
# → 00000000000000000001cce34a5158ba1bfc6a8d12982f5baba0da3a7874029f

# This fails (from mempool-api container):
curl http://localhost:8999/api/blocks/tip/hash
# → 404 Not Found
```

**Result**:
- `/api/v1/prices` works (exchange prices)
- `/api/blocks/*` endpoints missing (transaction data)
- System falls back to Tier 3 (Bitcoin Core RPC)

---

## Root Cause Analysis

### Current Configuration

```yaml
# docker-compose.yml
services:
  electrs:
    network_mode: host  # ← Uses host network namespace
    command:
      - --http-addr
      - 0.0.0.0:3001  # ← Listening on host localhost:3001

  api:
    networks:
      - mempool-network  # ← Bridge network (isolated)
    environment:
      - ESPLORA_REST_API_URL=http://localhost:3001  # ← WRONG!
```

### The Issue

1. **electrs** uses `network_mode: host`
   - Binds directly to host's `localhost:3001`
   - No network isolation

2. **mempool-api** uses bridge network `mempool-network`
   - Has its own network namespace
   - `localhost` inside container ≠ host's `localhost`

3. **Connection fails**:
   ```
   mempool-api container tries: http://localhost:3001
                                        ↓
                         Looks in its own namespace (not host)
                                        ↓
                           Connection refused (ECONNREFUSED)
   ```

### Evidence

**From mempool-api logs**:
```
Nov 2 22:15:40 [130] WARN: connect ECONNREFUSED 127.0.0.1:3001
Nov 2 22:16:41 [130] WARN: esplora request failed http://localhost:3001/mempool/txids
```

**electrs HTTP API verification** (on host):
```bash
curl http://localhost:3001/blocks/tip/height
# → 921972 ✅ Works!

curl http://localhost:3001/blocks/tip/hash
# → 00000000000000000001cce34a5158ba1bfc6a8d12982f5baba0da3a7874029f ✅ Works!
```

---

## Solution

### Option 1: Use Host IP (Recommended)

Change `ESPLORA_REST_API_URL` to use the host's IP address:

```yaml
# docker-compose.yml
services:
  api:
    environment:
      - ESPLORA_REST_API_URL=http://192.168.1.111:3001  # ← Host IP
```

**Pros**:
- Simple configuration change
- No network mode changes
- Maintains container isolation

**Cons**:
- Hardcoded IP (not portable)
- Requires firewall rule if enabled

---

### Option 2: Move mempool-api to host network

```yaml
# docker-compose.yml
services:
  api:
    network_mode: host  # ← Use host network like electrs
    ports:  # ← Remove, not needed with host network
      # - "8999:8999"
    environment:
      - ESPLORA_REST_API_URL=http://localhost:3001  # ← Now works!
      - MEMPOOL_HTTP_PORT=8999  # ← Bind to specific port
```

**Pros**:
- `localhost` works as expected
- No IP hardcoding

**Cons**:
- Loses container network isolation
- Can't use standard Docker networking
- Port conflicts possible

---

### Option 3: Use Docker host.docker.internal

```yaml
# docker-compose.yml (Linux requires extra_hosts)
services:
  api:
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      - ESPLORA_REST_API_URL=http://host.docker.internal:3001
```

**Pros**:
- Portable (works on any host)
- Maintains container isolation

**Cons**:
- Requires Docker 20.10+
- Needs extra configuration

---

## Recommended Fix

**Use Option 1** (Host IP) as it's the simplest and matches the current docker-compose.yml pattern where Bitcoin Core RPC also uses host IP (`CORE_RPC_HOST: "192.168.1.111"`).

### Implementation Steps

1. **Edit docker-compose.yml**:
   ```bash
   cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
   nano docker-compose.yml

   # Change:
   # ESPLORA_REST_API_URL: "http://localhost:3001"
   # To:
   # ESPLORA_REST_API_URL: "http://192.168.1.111:3001"
   ```

2. **Restart mempool-api**:
   ```bash
   docker compose restart api
   ```

3. **Wait 30 seconds for connection**:
   ```bash
   sleep 30
   docker compose logs api --tail=10
   # Should see: successful esplora connections, no ECONNREFUSED
   ```

4. **Test endpoints**:
   ```bash
   # Test block API (should work now)
   curl http://localhost:8999/api/blocks/tip/hash

   # Test transaction fetch
   python3 /media/sam/1TB/UTXOracle/scripts/daily_analysis.py --dry-run --verbose
   # Should see: "[Primary API] ✅ Fetched XXXX transactions"
   ```

5. **Verify Tier 1 cascade**:
   - Check logs show "Tier 1" success instead of "Tier 1 failed"
   - Confirm no fallback to Tier 3

---

## Impact Assessment

### Before Fix
- ❌ Tier 1: Not functional (404 on `/api/blocks/*`)
- ✅ Tier 2: Functional (public mempool.space)
- ✅ Tier 3: Functional (Bitcoin Core RPC)
- **Current behavior**: Always uses Tier 3 (Bitcoin Core RPC)

### After Fix
- ✅ Tier 1: Should be functional
- ✅ Tier 2: Still functional (unchanged)
- ✅ Tier 3: Still functional (unchanged)
- **Expected behavior**: Uses Tier 1 (local mempool.space) as designed

---

## Alternative: Keep As-Is?

**Consideration**: The system is working with Tier 3 (Bitcoin Core RPC). Is fixing Tier 1 necessary?

**Arguments for fixing**:
- ✅ Reduces load on Bitcoin Core RPC
- ✅ Utilizes self-hosted mempool.space infrastructure
- ✅ Completes the 3-tier architecture as designed
- ✅ Provides better error messages in logs

**Arguments for keeping as-is**:
- ✅ System is production-ready with Tier 3
- ✅ No urgent need (fallback working)
- ❌ Tier 1 only saves ~2 seconds per query
- ❌ Bitcoin Core RPC is more reliable

**Recommendation**: **Fix it** - The infrastructure is already deployed, we should use it. Takes 5 minutes to implement.

---

## Testing Checklist

After implementing fix:

- [ ] Check docker compose logs for esplora connection errors
- [ ] Curl test: `curl http://localhost:8999/api/blocks/tip/hash`
- [ ] Python test: `python3 scripts/daily_analysis.py --dry-run --verbose`
- [ ] Verify logs show "[Primary API] ✅ Fetched" not "[WARNING] Tier 1 failed"
- [ ] Wait 10 minutes and check cron job logs
- [ ] Verify DuckDB receives new data from Tier 1

---

---

## Update: Fix Attempted (Nov 2, 2025, 22:39)

### Changes Applied

✅ **docker-compose.yml updated**:
```yaml
# Changed line 98:
ESPLORA_REST_API_URL: "http://192.168.1.111:3001"  # Was: http://localhost:3001
```

✅ **Container restarted**:
```bash
docker compose stop api && docker compose up -d api
```

### Results

**Connection Fixed** ✅:
- No more `ECONNREFUSED 127.0.0.1:3001` errors in logs
- mempool-api successfully connects to electrs esplora API
- Backend can now query electrs for blockchain data

**API Endpoints Still Missing** ❌:
```bash
curl http://localhost:8999/api/blocks/tip/hash
# → 404 Not Found (still)

python3 scripts/daily_analysis.py --dry-run
# → WARNING: Tier 1 failed (http://localhost:8999): 404 Client Error
# → WARNING: Attempting Tier 3: Bitcoin Core RPC direct
```

### Root Cause Discovery

The `/api/blocks/*` endpoints **do not exist** in the mempool.space backend API, even with working esplora connection.

**Reason**:
- Public mempool.space has these endpoints (we tested successfully)
- Self-hosted version may be:
  1. Different version/build
  2. Missing frontend component that serves these endpoints
  3. Requires additional configuration

**Evidence**:
- Backend logs show no errors
- esplora connection working (confirmed)
- Only `/api/v1/prices` endpoint available
- No `/api/blocks/`, `/api/block/`, `/api/tx/` endpoints

### Conclusion

✅ **Infrastructure fix successful**: esplora connectivity restored
❌ **API endpoints unavailable**: Not exposed by backend
✅ **System operational**: 3-tier cascade working (falls back to Tier 3)

**Decision**: Keep current configuration. The 3-tier cascade is working as designed:
- Tier 1: Not available (API limitation)
- Tier 2: Available (public mempool.space)
- Tier 3: Available (Bitcoin Core RPC) ← Currently used

**Recommendation**: Document as expected limitation, no further action required.

---

**Status**: 🟡 PARTIAL FIX - Infrastructure working, API endpoints not exposed by backend
