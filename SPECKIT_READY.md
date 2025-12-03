# ✅ SpecKit Files Ready for Spec 003

**Created**: 2025-10-24
**Status**: Ready for `/speckit.implement`

---

## 📦 What Was Created

### SpecKit Specification Files

```
specs/003-mempool-integration-refactor/
├── README.md          ✅ Usage guide and quick start
├── spec.md            ✅ Feature specification (4 user stories)
├── plan.md            ✅ Technical implementation plan (4-layer architecture)
└── tasks.md           ✅ Actionable task list (110 tasks, 6 phases)
```

### Supporting Documentation

```
Repository Root:
├── ULTRA_KISS_PLAN.md                    ✅ Strategic plan (basis for spec 003)
├── MEMPOOL_ELECTRS_ARCHITECTURE.md       ✅ Architecture deep-dive
├── PRODUCTION_DEPLOYMENT.md              ✅ Deployment guide
└── scripts/
    ├── setup_full_mempool_stack.sh       ✅ Automated setup script
    └── verify_mempool_setup.sh           ✅ Health check script
```

---

## 🎯 Summary of Plan

### Problem
- `/live/` directory contains 1,222 lines duplicating mempool.space functionality
- `baseline_calculator.py` duplicates 581 lines from UTXOracle.py
- Total: 3,041 lines with significant duplication

### Solution
- Deploy self-hosted mempool.space + electrs stack on NVMe
- Refactor UTXOracle.py → library with clean API
- Create integration service (cron job) comparing on-chain vs exchange prices
- Store results in DuckDB on NVMe
- Expose via FastAPI + visualize with Plotly.js

### Result
- 77% code reduction (3,041 → 700 lines)
- Enable price comparison (on-chain vs exchange)
- Prepare for Rust migration (clean library interface)
- Production-ready deployment with systemd + cron

---

## 🚀 How to Proceed (Two Options)

### Option A: Automated (SpecKit) - Recommended

In a **new Claude Code session**:

```bash
cd /media/sam/1TB/UTXOracle

# Execute all 110 tasks automatically
/speckit.implement
```

**What SpecKit will do**:
1. Read `specs/003-mempool-integration-refactor/tasks.md`
2. Execute tasks T001-T110 in order (respects dependencies)
3. Run tests for each phase (TDD workflow)
4. Mark completed tasks with `[X]`
5. Handle errors and log progress
6. Report status after each phase

**Estimated time**: 10-12 days (mostly automated, some manual verification needed)

---

### Option B: Manual (Step-by-Step)

Follow `tasks.md` manually, starting with infrastructure:

```bash
# Phase 1: Infrastructure (T001-T012) - START HERE
bash scripts/setup_full_mempool_stack.sh

cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker-compose up -d

# Monitor electrs sync (8-12 hours)
docker-compose logs -f electrs

# While waiting, start Phase 2 (Refactor) in parallel
# ... continue with remaining phases
```

---

## ⏱️ Timeline

### Critical Path (Sequential)

**Phase 1**: Infrastructure Setup
- **Time**: 1-2 days (8-12 hours electrs sync)
- **Tasks**: T001-T012
- **Output**: Self-hosted mempool.space stack on NVMe

**Phase 2**: Algorithm Refactor
- **Time**: 2-3 days
- **Tasks**: T013-T033
- **Output**: `UTXOracle_library.py` with clean API

**Phase 3**: Integration Service
- **Time**: 2 days
- **Tasks**: T034-T054
- **Output**: Cron job + DuckDB storage

**Phase 4**: API & Visualization
- **Time**: 1-2 days
- **Tasks**: T055-T079
- **Output**: FastAPI + Plotly.js dashboard

**Phase 5**: Cleanup & Documentation
- **Time**: 1-2 days
- **Tasks**: T080-T099
- **Output**: 77% code reduction, updated docs

**Phase 6**: Validation
- **Time**: 1 day
- **Tasks**: T100-T110
- **Output**: Production-ready system

**Total**: 10-12 days

---

## 📋 Prerequisites Verified

✅ **Bitcoin Core**: Running and synced (block 920581)
✅ **Docker**: Installed and accessible
✅ **NVMe Storage**: `/media/sam/2TB-NVMe/prod/apps/` exists with correct permissions
✅ **DuckDB**: Installed (v1.4.0)
✅ **SpecKit**: Configured and up-to-date (commit c6eae050)
✅ **Ports Available**: 8000, 8080, 8999, 50001 all free

---

## 🎓 Key Files to Review Before Starting

### Must Read (5 minutes)
1. `specs/003-mempool-integration-refactor/README.md` - Quick start guide
2. `MEMPOOL_ELECTRS_ARCHITECTURE.md` - Architecture overview

### Should Read (15 minutes)
3. `specs/003-mempool-integration-refactor/spec.md` - User stories and acceptance criteria
4. `specs/003-mempool-integration-refactor/plan.md` - Technical approach

### Reference (as needed)
5. `specs/003-mempool-integration-refactor/tasks.md` - Detailed task list
6. `ULTRA_KISS_PLAN.md` - Strategic rationale
7. `PRODUCTION_DEPLOYMENT.md` - Deployment details

---

## 🔍 Verification After Each Phase

### Phase 1 Checkpoint (Infrastructure)
```bash
docker-compose ps  # All containers "Up" and healthy
curl http://localhost:8999/api/v1/prices  # Returns JSON with USD price
curl http://localhost:8080  # Returns mempool.space HTML
docker logs mempool-electrs | grep "finished full compaction"  # Found
```

### Phase 2 Checkpoint (Refactor)
```bash
python3 -c "from UTXOracle_library import UTXOracleCalculator; print('✅')"
python3 UTXOracle.py -rb  # CLI still works (backward compatible)
pytest tests/test_utxoracle_library.py -v  # All tests pass
```

### Phase 3 Checkpoint (Integration)
```bash
python3 scripts/daily_analysis.py --dry-run  # Runs without errors
duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db "SELECT COUNT(*) FROM prices"  # Returns >0
tail -f /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/daily_analysis.log  # New entries every 10 min
```

### Phase 4 Checkpoint (API)
```bash
sudo systemctl status utxoracle-api  # Active (running)
curl http://localhost:8000/api/prices/latest  # Returns JSON
firefox http://localhost:8000/comparison.html  # Shows Plotly chart
```

### Phase 5 Checkpoint (Cleanup)
```bash
find . -name '*.py' -not -path './archive/*' -not -path './tests/*' | xargs wc -l | tail -1
# Total ≤ 800 lines (77% reduction achieved)
pytest tests/ -v --cov  # 80%+ coverage
```

### Phase 6 Checkpoint (Validation)
```bash
sudo reboot  # Reboot server
# After reboot:
docker-compose ps  # All auto-started
sudo systemctl status utxoracle-api  # Auto-started
tail -f /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/daily_analysis.log  # Cron executing
```

---

## 🎯 Success Criteria

After completing all phases, you should have:

- ✅ Self-hosted mempool.space stack on NVMe (38GB electrs, 2GB MySQL)
- ✅ UTXOracle algorithm as importable library (`UTXOracle_library.py`)
- ✅ Cron job running every 10 minutes, updating DuckDB
- ✅ FastAPI serving comparison data on port 8000
- ✅ Plotly.js dashboard visualizing on-chain vs exchange prices
- ✅ 77% code reduction (3,041 → 700 lines)
- ✅ 80%+ test coverage
- ✅ Production deployment with systemd + cron
- ✅ All services survive reboot (auto-start configured)

---

## 🐛 If Something Goes Wrong

### During Infrastructure Setup (Phase 1)

**Problem**: electrs sync stuck

**Solution**:
```bash
docker logs mempool-electrs --tail 100  # Check for errors
df -h /media/sam/2TB-NVMe/  # Verify disk space
docker-compose restart electrs  # Restart if needed
```

**Problem**: RPC connection refused

**Solution**:
```bash
bitcoin-cli getblockcount  # Verify Bitcoin Core running
cat ~/.bitcoin/.cookie  # Verify cookie file exists
# Check docker-compose.yml has correct CORE_RPC_HOST
```

---

### During Refactor (Phase 2)

**Problem**: Tests fail after refactor

**Solution**:
```bash
# Compare output before/after
python3 UTXOracle.py -rb > before.txt  # Run original
python3 UTXOracle.py -rb > after.txt   # Run with library
diff before.txt after.txt  # Should be identical
```

---

### During Integration (Phase 3)

**Problem**: Cron not executing

**Solution**:
```bash
sudo tail -f /var/log/syslog | grep CRON  # Monitor cron
python3 scripts/daily_analysis.py --verbose  # Test manually
sudo service cron restart  # Restart cron daemon
```

---

### During API (Phase 4)

**Problem**: API returns 500 error

**Solution**:
```bash
sudo journalctl -u utxoracle-api -f  # View logs
# Check UTXORACLE_DATA_DIR environment variable
# Verify DuckDB file exists and is readable
```

---

## 📞 Next Actions

### Right Now (Before New Session)

1. ✅ **Review this file** (you're reading it!)
2. ✅ **Read** `specs/003-mempool-integration-refactor/README.md`
3. ⏭️ **Decide**: Automated (SpecKit) or Manual approach

### In New Claude Code Session

**Option A (Automated)**:
```bash
cd /media/sam/1TB/UTXOracle
/speckit.implement
```

**Option B (Manual)**:
```bash
cd /media/sam/1TB/UTXOracle
bash scripts/setup_full_mempool_stack.sh
# Follow tasks.md step by step
```

---

## 📚 Reference Links

- **SpecKit**: https://github.com/github/spec-kit
- **mempool.space**: https://github.com/mempool/mempool
- **electrs**: https://github.com/romanz/electrs
- **DuckDB**: https://duckdb.org/
- **FastAPI**: https://fastapi.tiangolo.com/
- **Plotly.js**: https://plotly.com/javascript/

---

## ✨ Summary

**What was done in this session**:
1. ✅ Analyzed current system state
2. ✅ Corrected architecture understanding (electrs is separate!)
3. ✅ Created unified docker-compose for full stack
4. ✅ Created SpecKit files (spec.md, plan.md, tasks.md)
5. ✅ Documented deployment strategy
6. ✅ Verified all prerequisites

**What to do next**:
1. Open new Claude Code session
2. Run `/speckit.implement` (automated) OR follow tasks.md (manual)
3. Monitor progress through 6 phases
4. Verify checkpoints after each phase
5. Celebrate 77% code reduction! 🎉

---

**Status**: Ready to deploy! 🚀

**Recommended command in new session**:
```bash
/speckit.implement
```

**Estimated completion**: 10-12 days (mostly automated)
