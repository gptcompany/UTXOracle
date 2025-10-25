# Spec 003: mempool.space Integration & Refactor

**Status**: Ready for implementation
**Created**: 2025-10-24
**Approach**: SpecKit workflow

---

## 📋 Files Created

✅ **spec.md** - Feature specification (problem, solution, user stories)
✅ **plan.md** - Technical implementation plan (architecture, tech stack, phases)
✅ **tasks.md** - Actionable task list (110 tasks, 6 phases, ~12 days)

---

## 🚀 How to Use with SpecKit

### Prerequisites

SpecKit is already installed and configured in this repository:
- Location: `.specify/` and `.claude/commands/speckit.*`
- Constitution: `.specify/memory/constitution.md` (v1.0.0) ✅
- Git commit: `c6eae050c76bcc8f86bc48cb388c5d3aa528ebe5`

### Workflow

This spec was created following the SpecKit workflow. You can now use SpecKit commands to continue:

#### Option 1: Implement All Tasks

```bash
/speckit.implement
```

This will execute all 110 tasks in `tasks.md` following the defined phases.

#### Option 2: Review & Customize

Before implementing, you can:

1. **Analyze consistency**:
   ```bash
   /speckit.analyze
   ```

2. **Create custom checklist**:
   ```bash
   /speckit.checklist Based on spec 003, create checklist for Infrastructure phase (T001-T012)
   ```

3. **Ask clarifying questions**:
   ```bash
   /speckit.clarify
   ```

#### Option 3: Manual Implementation

You can also implement tasks manually by following `tasks.md` step-by-step:

```bash
# Phase 1: Infrastructure (T001-T012)
bash scripts/setup_full_mempool_stack.sh
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker-compose up -d

# Phase 2: Refactor (T013-T033)
# Create UTXOracle_library.py...

# Phase 3: Integration (T034-T054)
# Create scripts/daily_analysis.py...

# ... continue with remaining phases
```

---

## 🎯 Quick Start (Recommended)

### Start with Infrastructure (Opzione A)

Since you want to proceed with **Opzione A (Full electrs deployment)**, start here:

```bash
# 1. Review the setup script (already created)
cat scripts/setup_full_mempool_stack.sh

# 2. Run the setup
bash scripts/setup_full_mempool_stack.sh

# 3. Start the stack
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker-compose up -d

# 4. Monitor electrs sync (3-4 hours on NVMe)
docker-compose logs -f electrs

# 5. While waiting, start Phase 2 (Refactor) in parallel
# Sync is much faster on NVMe vs HDD
```

### Continue in New Session with SpecKit

As you mentioned, you want to continue with SpecKit in a new session:

```bash
# In new Claude Code session:

# 1. Navigate to project
cd /media/sam/1TB/UTXOracle

# 2. Check spec 003 status
cat specs/003-mempool-integration-refactor/tasks.md | grep "^\- \[ \]" | wc -l
# Shows number of pending tasks

# 3. Run SpecKit implementation
/speckit.implement

# SpecKit will:
# - Read tasks.md
# - Execute tasks T001-T110 in order
# - Mark completed tasks with [X]
# - Handle errors and log progress
```

---

## 📊 Implementation Phases

### Phase 1: Infrastructure Setup (T001-T012)
**Time**: 4-6 hours (3-4 hours electrs sync on NVMe)
**Output**: Self-hosted mempool.space stack on NVMe

### Phase 2: Algorithm Refactor (T013-T033)
**Time**: 2-3 days
**Output**: `UTXOracle_library.py` with clean API

### Phase 3: Integration Service (T034-T054)
**Time**: 2 days
**Output**: Cron job + DuckDB storage

### Phase 4: API & Visualization (T055-T079)
**Time**: 1-2 days
**Output**: FastAPI + Plotly.js dashboard

### Phase 5: Cleanup & Documentation (T080-T099)
**Time**: 1-2 days
**Output**: 77% code reduction, updated docs

### Phase 6: Validation (T100-T110)
**Time**: 1 day
**Output**: Production-ready system

**Total**: 10-12 days

---

## 📚 Reference Documents

All referenced documents are in the repository root:

- `ULTRA_KISS_PLAN.md` - Strategic plan (basis for this spec)
- `MEMPOOL_ELECTRS_ARCHITECTURE.md` - Architecture details
- `PRODUCTION_DEPLOYMENT.md` - Deployment guide
- `scripts/setup_full_mempool_stack.sh` - Automated setup
- `STRATEGIC_INTEGRATION_PLAN.md` - Original analysis

---

## ⚙️ Configuration Files

### Docker Compose

Location: `/media/sam/2TB-NVMe/prod/apps/mempool-stack/docker-compose.yml` (created by setup script)

Services:
- `electrs` - Rust indexer (port 50001)
- `db` - MariaDB (port 3306)
- `api` - mempool backend (port 8999)
- `web` - mempool frontend (port 8080)

### Environment Variables

Setup script creates `.env` file with:
- Bitcoin Core RPC credentials
- electrs configuration
- Database settings
- API ports

### Systemd Services

Created during Phase 3 and 4:
- `/etc/systemd/system/utxoracle-api.service` - FastAPI backend
- `/etc/cron.d/utxoracle-analysis` - Daily analysis cron

---

## 🔍 Verification Commands

After each phase, verify success:

### Phase 1 (Infrastructure)
```bash
docker-compose ps  # All healthy
curl http://localhost:8999/api/v1/prices  # Returns prices
curl http://localhost:8080  # Returns HTML
```

### Phase 2 (Refactor)
```bash
python3 -c "from UTXOracle_library import UTXOracleCalculator; print('✅')"
pytest tests/test_utxoracle_library.py -v  # All pass
```

### Phase 3 (Integration)
```bash
python3 scripts/daily_analysis.py --dry-run  # Runs without errors
duckdb data/utxoracle_cache.db "SELECT COUNT(*) FROM prices"  # Returns >0
```

### Phase 4 (API)
```bash
curl http://localhost:8000/api/prices/latest  # Returns JSON
firefox http://localhost:8000/comparison.html  # Shows chart
```

### Phase 5 (Cleanup)
```bash
find . -name '*.py' -not -path './archive/*' -not -path './tests/*' | xargs wc -l | tail -1
# Total should be ≤800 lines (77% reduction from 3,041)
```

---

## 🐛 Troubleshooting

### electrs Sync Stuck

```bash
docker logs mempool-electrs --tail 100
# Look for errors

# Check disk space
df -h /media/sam/2TB-NVMe/

# Restart if needed
docker-compose restart electrs
```

### API Not Responding

```bash
sudo systemctl status utxoracle-api
# Check if service is running

sudo journalctl -u utxoracle-api -f
# View logs

# Restart if needed
sudo systemctl restart utxoracle-api
```

### Cron Not Executing

```bash
sudo tail -f /var/log/syslog | grep CRON
# Monitor cron execution

# Verify cron file installed
ls -la /etc/cron.d/utxoracle-analysis

# Test manually
python3 scripts/daily_analysis.py --verbose
```

---

## 📈 Success Metrics

After completing all phases, verify:

- ✅ Code reduction: `find . -name '*.py' | xargs wc -l` ≤ 800 lines
- ✅ Test coverage: `pytest --cov` ≥ 80%
- ✅ API latency: `time curl localhost:8000/api/prices/latest` < 50ms
- ✅ DuckDB query: `time duckdb "SELECT * FROM prices"` < 50ms
- ✅ System uptime: All services survive reboot

---

## 🔗 Dependencies

### System Requirements

- Ubuntu 22.04+ (or similar Linux)
- Docker 20.10+
- docker-compose 1.29+
- Python 3.8+
- Bitcoin Core (synced, RPC enabled)
- 50GB free on NVMe
- 8GB RAM minimum

### Python Dependencies

Will be installed during implementation:
- `fastapi`
- `uvicorn[standard]`
- `duckdb>=1.4.0`
- `requests`
- `pytest` (dev)
- `pytest-cov` (dev)

---

## 🎓 Learning Resources

- **SpecKit**: https://github.com/github/spec-kit
- **mempool.space**: https://github.com/mempool/mempool/tree/master/docker
- **electrs**: https://github.com/romanz/electrs
- **DuckDB**: https://duckdb.org/docs/
- **FastAPI**: https://fastapi.tiangolo.com/
- **Plotly.js**: https://plotly.com/javascript/

---

## 📞 Next Steps

1. **Read this README** ✅ You're here!
2. **Review the three main files**:
   - `spec.md` - Understand the problem and solution
   - `plan.md` - Review architecture and approach
   - `tasks.md` - See detailed implementation steps
3. **Start implementation**:
   - Option A: Use `/speckit.implement` (automated)
   - Option B: Follow `tasks.md` manually (more control)
4. **Monitor progress** in new Claude Code session
5. **Verify each phase** before moving to next

---

**Status**: Files ready ✅
**Action**: Choose implementation approach (A or B) and begin!

**For Opzione A (your preference)**:
```bash
# Start now:
bash scripts/setup_full_mempool_stack.sh

# Then in new session:
/speckit.implement
```
