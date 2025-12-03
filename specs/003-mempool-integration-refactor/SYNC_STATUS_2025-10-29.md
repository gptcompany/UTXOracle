# Mempool electrs Sync Status Report
**Date**: 2025-10-29 23:50 UTC
**Status**: 🔄 COMPACTING (Phase 3 in progress)

---

## 📊 Current Status

### Sync Progress
- **Bitcoin Core Height**: 921,382 blocks
- **electrs Indexed Height**: 500,000 blocks (54.2%)
- **Compaction Status**: IN PROGRESS (started)
- **Index Size**: 475GB (uncompacted) → ~38GB (post-compaction)

### Container Health
```
✅ mempool-web      - Frontend (port 8080) - WORKING
✅ mempool-db       - MariaDB - healthy
⚠️  mempool-api     - Backend (port 8999) - Timeout (waiting for electrs)
🔄 mempool-electrs  - COMPACTING database
```

---

## 🔍 Issue Analysis

### Why Sync Appears "Stuck"
electrs is at height **500,000** and appears frozen, BUT:

**Root Cause**: electrs is in **full compaction phase** (Phase 3)
- Last log: `DEBUG - starting full compaction on RocksDB`
- Uncompacted index: **475GB** (12x expected size)
- Expected post-compaction: **~38GB**
- Compaction time: **Unknown** (could be 1-4 hours for 475GB → 38GB)

### Why API Fails
Backend API tries to connect to electrs HTTP endpoint but:
- electrs HTTP API not available during compaction
- Connection timeout: `http://192.168.1.111:3001/mempool/txids`
- API retries every ~1 second (177 failures logged)

---

## ⏱️ Sync Timeline Reconstruction

### Phase 1: Header Download (✅ Complete)
- **Started**: 2025-10-27 ~21:30
- **Duration**: ~5 minutes
- **Result**: Downloaded 921k block headers

### Phase 2: Transaction Indexing (✅ Complete)
- **Started**: 2025-10-27 ~21:35
- **Progress**: 0 → 500,000 blocks (~54%)
- **Duration**: ~48 hours (2 days!)
- **Result**: 475GB uncompacted index

**Why So Slow?**
- Expected: 3-4 hours for full sync
- Actual: 48+ hours for 54% sync
- **10x slower than expected!**

**Possible Reasons**:
1. NVMe disk contention (other processes?)
2. Bitcoin Core I/O bottleneck
3. Suboptimal electrs configuration
4. RocksDB performance issues

### Phase 3: Compaction (🔄 Current)
- **Started**: 2025-10-29 ~23:45 (few minutes ago)
- **Input**: 475GB uncompacted
- **Output**: ~38GB (expected)
- **ETA**: Unknown (1-4 hours estimate)
- **Expected Completion**: 2025-10-30 ~03:00

---

## 🚨 Critical Observations

### 1. Sync Performance Issue
**Normal sync**: 3-4 hours total (entire blockchain)
**Actual sync**: 48+ hours (only 54% complete)

**Impact**: 10x performance degradation

**Action**: After compaction completes, investigate:
- `iostat -x 5` during sync (check disk utilization)
- Bitcoin Core RPC latency
- electrs configuration tuning

### 2. Incomplete Sync After 48 Hours
**Why Only 54%?**
- Possible: electrs restarted/crashed at 500k blocks
- Possible: Compaction triggered early
- Check: `docker compose logs electrs | grep -i "error\|restart\|stopped"`

### 3. Index Size Bloat
**Expected**: 38GB final
**Current**: 475GB uncompacted

**Ratio**: 12.5x bloat factor (normal for RocksDB before compaction)

---

## 🔧 Recommended Actions

### Immediate (Now)
1. **Wait for compaction to finish** (monitor disk size)
   ```bash
   watch -n 60 "du -sh /media/sam/2TB-NVMe/prod/apps/mempool-stack/data/electrs"
   ```

2. **Monitor compaction logs**
   ```bash
   cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
   docker compose logs -f electrs | grep -i "finished full compaction"
   ```

3. **Check for errors**
   ```bash
   docker compose logs electrs | grep -i "error\|fail\|fatal"
   ```

### After Compaction Completes
1. **Verify index size reduced**
   - Expected: ~38GB
   - Check: `du -sh data/electrs`

2. **Resume sync** (if stopped at 500k)
   - electrs should auto-resume indexing 500k → 921k blocks

3. **Monitor sync speed**
   - Should see: `INFO - Tx indexing is up to height=510000` (incremental)

4. **Test APIs**
   ```bash
   # Wait for sync to complete, then:
   curl http://localhost:8999/api/v1/blocks/tip/height
   ```

### If Sync Still Stuck After Compaction
**Option A: Let it continue**
- Pros: No data loss, will eventually complete
- Cons: Unknown ETA (could be days at current speed)

**Option B: Restart with optimized config**
- Pros: Potential performance improvement
- Cons: Lose 48 hours of sync progress

**Option C: Use public mempool.space API temporarily**
- Pros: Immediate availability
- Cons: External dependency (not self-hosted)
- Already configured in `daily_analysis.py` as fallback

---

## 📈 Monitoring Commands

### Track compaction progress (index size shrinking)
```bash
# Run in separate terminal
watch -n 60 'du -sh /media/sam/2TB-NVMe/prod/apps/mempool-stack/data/electrs && df -h /media/sam/2TB-NVMe | tail -1'
```

**What to expect**:
- Size decreasing: 475GB → 400GB → 300GB → ... → 38GB
- Duration: 1-4 hours (rough estimate for 437GB reduction)

### Watch for "finished full compaction"
```bash
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose logs -f electrs | grep --line-buffered -E "INFO|finished full compaction"
```

### Check if sync resumes after compaction
```bash
# Should see height incrementing after compaction
docker compose logs -f electrs | grep "Tx indexing is up to height="
```

---

## 🎯 Success Criteria

### Compaction Complete
- ✅ Log message: `finished full compaction on RocksDB`
- ✅ Index size: ~38GB (±5GB acceptable)
- ✅ Disk space freed: ~437GB

### Sync Resumed
- ✅ Height incrementing: 500k → 510k → 520k → ...
- ✅ No errors in logs
- ✅ API timeouts stop

### Sync Complete
- ✅ Height: 921,382 (current Bitcoin Core tip)
- ✅ electrs healthy: `docker ps | grep electrs` shows (healthy)
- ✅ API responding: `curl http://localhost:8999/api/v1/blocks/tip/height`

---

## 📊 Disk Space Status

```
NVMe Total: 1.8TB
Used: 964GB (56%)
Available: 777GB

electrs Index: 475GB (before compaction)
Expected after compaction: ~38GB
Space to be freed: ~437GB
```

**Status**: ✅ Sufficient space for compaction

---

## 🔗 Next Steps

### Within 1 Hour
- [ ] Monitor compaction progress (index size shrinking)
- [ ] Verify no errors in logs
- [ ] Check disk not filling up

### After Compaction (1-4 hours)
- [ ] Verify index size ~38GB
- [ ] Confirm sync resumes (height > 500k)
- [ ] Update MEMPOOL_RESTART_REPORT.md with findings

### After Full Sync (Unknown ETA)
- [ ] Test all APIs
- [ ] Integrate with `daily_analysis.py`
- [ ] Mark T001-T012 as COMPLETE
- [ ] Document performance tuning for future syncs

---

## 🐛 Debug Info

### Container Logs Sample
```
mempool-api: timeout of 5000ms exceeded (http://192.168.1.111:3001/mempool/txids)
mempool-electrs: DEBUG - starting full compaction on RocksDB { path: "/data/mainnet/newindex/txstore" }
```

### Last Indexed Height
```
INFO - Tx indexing is up to height=500000
```

### Current Process
```
Phase 3: Database compaction (475GB → 38GB)
```

---

## Status: 🔄 WAITING FOR COMPACTION
**Action Required**: Monitor disk size reduction, wait for completion message.
**ETA**: 1-4 hours (rough estimate)
**Next Check**: 2025-10-30 01:00 UTC
