# Phase 3 Verification Checklist

**Status:** ⏳ Waiting for mempool.space sync completion

**Created:** 2025-10-26 18:52

---

## 🔍 Pre-Verification: Check Sync Status

### 1. Check mempool.space containers

```bash
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose ps
```

**Expected:** All containers showing `Up` and `(healthy)`

### 2. Check electrs sync progress

```bash
docker compose logs electrs | tail -20
```

**Look for:** `finished full compaction` message

### 3. Test mempool API

```bash
# Exchange prices endpoint
curl http://localhost:8999/api/v1/prices | jq .USD

# Current block height
curl http://localhost:8999/api/blocks/tip/height
```

**Expected:** Valid JSON responses with current data

---

## ✅ Phase 3 End-to-End Verification

Once mempool.space sync is complete, run these verification steps:

### Step 1: Manual Script Execution

```bash
# Set environment
export BITCOIN_DATADIR=/home/sam/.bitcoin
export DUCKDB_PATH=/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db

# Dry-run test (doesn't save to DB)
cd /media/sam/1TB/UTXOracle
uv run python3 scripts/daily_analysis.py --dry-run --verbose
```

**Expected Output:**
```
Config loaded from environment variables...
Configuration validated
Fetched mempool.space price: $67,234.50
UTXOracle price calculated
Price comparison
[DRY-RUN] Would save data:
{
  "timestamp": "2025-10-26 18:52:00",
  "utxoracle_price": 67000.0,
  "mempool_price": 67234.5,
  "confidence": 0.85,
  "tx_count": 1234,
  "diff_amount": 234.5,
  "diff_percent": 0.35,
  "is_valid": true
}
Daily analysis completed successfully
```

### Step 2: Real Database Write

```bash
# Run without --dry-run (writes to DB)
uv run python3 scripts/daily_analysis.py --verbose
```

**Expected:** No errors, successful completion

### Step 3: Verify DuckDB Data

```bash
# Query database
uv run duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
  "SELECT timestamp, utxoracle_price, mempool_price, confidence, is_valid
   FROM prices
   ORDER BY timestamp DESC
   LIMIT 5"
```

**Expected:** At least 1 row with recent timestamp

### Step 4: Check Cron Logs

```bash
# View last 50 lines of cron log
tail -50 /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/daily_analysis.log
```

**Expected:** Entries from cron execution (every 10 minutes)

### Step 5: Monitor Real-Time Execution

```bash
# Watch log file for new entries
tail -f /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/daily_analysis.log
```

**Wait 10 minutes** - should see new log entries

### Step 6: Verify Data Accumulation

```bash
# Count rows in database
uv run duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
  "SELECT COUNT(*) as total_entries FROM prices"
```

**Expected:** Count increases every 10 minutes

---

## 🧪 Full Integration Tests

Once basic verification passes, run integration tests:

```bash
cd /media/sam/1TB/UTXOracle

# Run all Phase 3 tests
uv run pytest tests/test_daily_analysis.py -v

# Run all tests (includes Phase 2)
uv run pytest tests/test_utxoracle_library.py tests/test_backward_compatibility.py tests/test_daily_analysis.py -v
```

**Expected:** All tests passing ✅

---

## 📊 Success Criteria

Phase 3 is fully verified when:

- ✅ Mempool.space API responds with current prices
- ✅ Manual script execution succeeds (--dry-run and real)
- ✅ DuckDB contains at least 3 entries (30 minutes of cron execution)
- ✅ Cron logs show successful executions every 10 minutes
- ✅ No errors in logs
- ✅ All 25/25 tests passing (8 library + 8 backward compat + 8 daily analysis + 1 integration)
- ✅ Price validation working (confidence, range checks)
- ✅ Data quality: is_valid=TRUE for valid entries

---

## 🚨 Troubleshooting

### Issue: Mempool API connection refused

```bash
# Check containers
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker compose ps
docker compose logs mempool-api | tail -20

# Restart if needed
docker compose restart mempool-api
```

### Issue: Bitcoin RPC connection failed

```bash
# Check Bitcoin Core is running
bitcoin-cli getblockchaininfo

# Check RPC credentials
cat /home/sam/.bitcoin/bitcoin.conf | grep rpc

# Test RPC connection
bitcoin-cli getbestblockhash
```

### Issue: DuckDB write fails

```bash
# Check permissions
ls -la /media/sam/2TB-NVMe/prod/apps/utxoracle/data/

# Check disk space
df -h /media/sam/2TB-NVMe/

# Check backup fallback worked
ls -la /tmp/utxoracle_backup.duckdb
```

### Issue: Cron not executing

```bash
# Check cron service
sudo service cron status

# Check cron job file syntax
cat /etc/cron.d/utxoracle-analysis

# Check syslog for cron errors
sudo grep CRON /var/log/syslog | tail -20
```

---

## 📝 Next Steps After Verification

Once Phase 3 is fully verified and working:

1. **Document results** - Screenshot of successful cron execution + DuckDB data
2. **Create checkpoint commit** - Mark T054 verification complete
3. **Proceed to Phase 4** - API & Visualization (T055-T079)

Command to resume:
```bash
cd /media/sam/1TB/UTXOracle
# Tell Claude: "Phase 3 verified, proceed with Phase 4"
```

---

## 📈 Current Status

**Tasks Complete:** 58/110 (53%)

**Phases Complete:**
- ✅ Phase 0: Git Hooks (T000)
- ✅ Phase 1: Infrastructure Setup (T001-T012)
- ✅ Phase 2: Algorithm Refactor (T013-T033)
- ✅ Phase 3: Integration Service (T034-T054) - *Pending full verification*

**Next Phase:**
- ⏳ Phase 4: API & Visualization (T055-T079)
- ⏳ Phase 5: Cleanup & Documentation (T080-T099)
- ⏳ Phase 6: Integration Testing (T100-T110)

---

## 🕐 Monitoring Commands (Quick Reference)

```bash
# Check mempool sync progress
docker compose logs electrs -f | grep -i "progress\|compaction"

# Check API health
curl http://localhost:8999/api/v1/prices | jq .USD

# Watch cron logs
tail -f /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/daily_analysis.log

# Query latest prices
uv run duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
  "SELECT * FROM prices ORDER BY timestamp DESC LIMIT 5"

# Check cron execution count
uv run duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
  "SELECT COUNT(*) as executions,
          MIN(timestamp) as first_run,
          MAX(timestamp) as last_run
   FROM prices"
```

---

**When mempool.space sync completes, run through this checklist and report results!**
