# UTXOracle Operational Runbook

**Version**: Spec-003
**Last Updated**: 2025-10-27

---

## System Overview

**Components**:
1. mempool.space Docker stack (infrastructure)
2. FastAPI backend (`utxoracle-api.service`)
3. Daily analysis cron job (`scripts/daily_analysis.py`)
4. QuestDB database (time-series price history and analytics)
5. Frontend dashboard (Plotly.js)

**Ports**:
- 8001: FastAPI API (baseline)
- 8011: FastAPI Live API (docker)
- 9000: QuestDB Web Console
- 9009: QuestDB ILP Ingestion
- 8812: QuestDB PostgreSQL Wire Protocol (asyncpg)
- 8080: mempool.space frontend
- 8999: mempool.space backend

---

## Daily Operations

### Health Check

```bash
# General status of all components
./scripts/health_check.sh

# Persistence verification (reboot readiness)
./scripts/verify_reboot_readiness.sh
```

Expected output: All components showing ✅

### Reboot Procedure

When maintenance requires a system reboot:

1. **Verify Readiness**: Run `./scripts/verify_reboot_readiness.sh`
2. **Graceful Shutdown**: 
   ```bash
   # Services will be stopped by systemd during reboot, but manual stop is safer for DBs
   sudo systemctl stop utxoracle-api
   docker stop questdb-global
   ```
3. **Reboot**: `sudo reboot`
4. **Post-Reboot Verification**:
   ```bash
   # Wait 2 minutes for containers to initialize
   ./scripts/health_check.sh
   ```


```bash
# API server
journalctl -u utxoracle-api -f

# Daily analysis (cron)
tail -f /media/sam/1TB/UTXOracle/logs/daily_analysis.log

# QuestDB (docker)
docker logs -f questdb-global
```

### Manual Data Update

```bash
# Run analysis manually (now saves to QuestDB via ILP)
python3 scripts/daily_analysis.py --verbose

# Run whale monitor manually
python3 scripts/mempool_whale_monitor.py

# Sync address clusters from DuckDB to QuestDB (spec-051)
python3 scripts/bootstrap/sync_clusters_to_questdb.py --batch-size 100000
```

---

## Start/Stop Procedures

### Start All Services

```bash
# 1. QuestDB (if not running)
docker start questdb-global

# 2. Docker stack (Infrastructure)
docker-compose -f docker-compose.live.yml up -d

# 3. Baseline API server
sudo systemctl start utxoracle-api

# 4. Verify
./scripts/health_check.sh
```

### Stop All Services

```bash
# 1. API server
sudo systemctl stop utxoracle-api

# 2. Docker stack
docker-compose -f docker-compose.live.yml down

# 3. QuestDB
docker stop questdb-global
```

### Restart API Server

```bash
sudo systemctl restart utxoracle-api
sudo systemctl status utxoracle-api
```

---

## Common Issues

### Issue: API not responding

**Symptoms**: `curl http://localhost:8001/health` fails

**Solution**:
```bash
# Check status
sudo systemctl status utxoracle-api

# View logs
journalctl -u utxoracle-api -n 50

# Restart
sudo systemctl restart utxoracle-api
```

### Issue: QuestDB Ingestion Lag

**Symptoms**: New data doesn't appear in dashboard for >10 seconds

**Solution**:
```bash
# 1. Check if ILP Sender is flushing (look for errors in worker logs)
# 2. Verify QuestDB logs for ingestion errors
docker logs questdb-global | grep -i error

# 3. Check QuestDB table row counts
# Visit http://localhost:9000 and run:
# SELECT count(*) FROM mempool_predictions;
```

### Issue: Database Connection Errors

**Symptoms**: Logs show `asyncpg.ConnectionError`

**Solution**:
```bash
# Check if QuestDB is listening on port 8812
sudo netstat -tulpn | grep 8812

# Restart QuestDB container
docker restart questdb-global
```

### Issue: Docker containers not starting

**Symptoms**: `docker-compose ps` shows containers exited

**Solution**:
```bash
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack

# Check logs
docker-compose logs

# Most common: Bitcoin Core not accessible
# Verify: bitcoin-cli getblockchaininfo
```

---

## Backup & Recovery

### QuestDB Backup

QuestDB supports hot backups. For the MVP, we use the simple file-system snapshot or export.

```bash
# Snapshot the data directory (ensure container is paused or use QuestDB backup API)
docker exec questdb-global questdb-backup.sh
```

### Restore from Snapshot

```bash
# Stop QuestDB
docker stop questdb-global

# Restore data directory
cp -r /media/sam/1TB/questdb-data-backup/* /media/sam/1TB/questdb-data/

# Start QuestDB
docker start questdb-global
```

---

## Monitoring

### Key Metrics

| Metric | Command | Healthy Range |
|--------|---------|---------------|
| API response time | `curl -w "%{time_total}\n" http://localhost:8001/health` | <0.1s |
| QuestDB memory | `docker stats questdb-global --no-stream` | <4GB |
| QuestDB storage | `du -sh /media/sam/1TB/questdb-data/` | <100GB |
| ILP row rate | Check QuestDB metrics endpoint | >0 rows/sec |

### Alerts to Configure

1. API downtime (systemctl status fails)
2. Database write failures (check daily_analysis.log)
3. Disk space >80% full
4. Price divergence >5% (logged in daily_analysis)

---

## Deployment Checklist

### New Server Setup

- [ ] Bitcoin Core installed and synced
- [ ] Docker and docker-compose installed
- [ ] Python 3.10+ and UV installed
- [ ] QuestDB container deployed (`docker run ... questdb/questdb`)
- [ ] Repository cloned
- [ ] Dependencies installed (`uv add questdb asyncpg`)
- [ ] `.env` file configured
- [ ] QuestDB tables initialized (automatic on repository startup)
- [ ] Systemd service installed
- [ ] Health check passes

### Post-Deployment Verification

```bash
# 1. Health check
./scripts/health_check.sh

# 2. API endpoints
curl http://localhost:8001/health | jq
curl http://localhost:8001/api/prices/latest | jq

# 3. Frontend
xdg-open http://localhost:8001/static/comparison.html

# 4. Wait 10 minutes, verify new data in QuestDB
# Check via Web Console at http://localhost:9000
```

---

## Escalation

### Level 1: Check Logs

All issues should start with log review:
- API: `journalctl -u utxoracle-api -n 100`
- Analysis: `/media/sam/2TB-NVMe/prod/apps/utxoracle/logs/daily_analysis.log`
- Docker: `docker-compose logs`

### Level 2: Restart Services

If logs show transient errors, restart:
```bash
sudo systemctl restart utxoracle-api
docker-compose restart
```

### Level 3: Check External Dependencies

- Bitcoin Core: `bitcoin-cli getblockchaininfo`
- Network: `ping 8.8.8.8`
- Disk space: `df -h`

### Level 4: Consult Documentation

- `CLAUDE.md` - Development guidelines
- `specs/003-mempool-integration-refactor/IMPLEMENTATION_STATUS.md` - Implementation details
- `specs/003-mempool-integration-refactor/TEMPORARY_CONFIG.md` - Temporary config
- `MIGRATION_GUIDE.md` - Migration from spec-002

---

**Emergency Contact**: See GitHub issues or community channels
**Documentation**: `/media/sam/1TB/UTXOracle/`
