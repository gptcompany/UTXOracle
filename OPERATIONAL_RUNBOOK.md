# UTXOracle Operational Runbook

**Version**: Spec-003
**Last Updated**: 2025-10-27

---

## System Overview

**Components**:
1. mempool.space Docker stack (infrastructure)
2. FastAPI backend (`utxoracle-api.service`)
3. Daily analysis cron job (`scripts/daily_analysis.py`)
4. DuckDB database (price history)
5. Frontend dashboard (Plotly.js)

**Ports**:
- 8000: FastAPI API
- 8080: mempool.space frontend (when deployed)
- 8999: mempool.space backend (when deployed)

---

## Daily Operations

### Health Check

```bash
./scripts/health_check.sh
```

Expected output: All components showing ✅

### Check Logs

```bash
# API server
journalctl -u utxoracle-api -f

# Daily analysis (cron)
tail -f /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/daily_analysis.log

# Docker stack (if running)
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker-compose logs -f
```

### Manual Data Update

```bash
# Run analysis manually
python3 scripts/daily_analysis.py --verbose

# Dry run (no database write)
python3 scripts/daily_analysis.py --dry-run
```

---

## Start/Stop Procedures

### Start All Services

```bash
# 1. Docker stack (if Bitcoin Core synced)
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker-compose up -d

# 2. API server
sudo systemctl start utxoracle-api

# 3. Verify
./scripts/health_check.sh
```

### Stop All Services

```bash
# 1. API server
sudo systemctl stop utxoracle-api

# 2. Docker stack
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker-compose down
```

### Restart API Server

```bash
sudo systemctl restart utxoracle-api
sudo systemctl status utxoracle-api
```

---

## Common Issues

### Issue: API not responding

**Symptoms**: `curl http://localhost:8000/health` fails

**Solution**:
```bash
# Check status
sudo systemctl status utxoracle-api

# View logs
journalctl -u utxoracle-api -n 50

# Restart
sudo systemctl restart utxoracle-api
```

### Issue: No new data in database

**Symptoms**: DuckDB shows no recent entries

**Solution**:
```bash
# Check cron logs
grep "daily_analysis" /var/log/syslog

# Run manually to see errors
python3 scripts/daily_analysis.py --verbose

# Check if cron job installed
ls -la /etc/cron.d/utxoracle-analysis
```

### Issue: Frontend shows "No data"

**Symptoms**: Dashboard loads but chart is empty

**Solution**:
```bash
# 1. Check database has data
duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db "SELECT COUNT(*) FROM prices"

# 2. Test API endpoint
curl http://localhost:8000/api/prices/historical?days=7 | jq

# 3. Check browser console for errors (F12)
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

### Manual Backup

```bash
./scripts/backup_duckdb.sh
```

### Restore from Backup

```bash
# List backups
ls -lh /media/sam/2TB-NVMe/prod/apps/utxoracle/data/backups/

# Restore (replace with your backup date)
cp /media/sam/2TB-NVMe/prod/apps/utxoracle/data/backups/utxoracle_cache_2025-10-27.db \
   /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db

# Restart API
sudo systemctl restart utxoracle-api
```

### Setup Automated Backups

```bash
# Add to crontab
sudo crontab -e

# Add this line (daily at 3 AM):
0 3 * * * /media/sam/1TB/UTXOracle/scripts/backup_duckdb.sh >> /var/log/utxoracle-backup.log 2>&1
```

---

## Monitoring

### Key Metrics

| Metric | Command | Healthy Range |
|--------|---------|---------------|
| API response time | `curl -w "%{time_total}\n" http://localhost:8000/health` | <0.1s |
| Database size | `du -h /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db` | <100MB |
| Disk usage | `df -h /media/sam/2TB-NVMe/` | <80% full |
| Memory usage | `free -h` | >2GB available |

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
- [ ] Repository cloned
- [ ] Dependencies installed (`uv pip install -e ".[dev]"`)
- [ ] `.env` file configured
- [ ] DuckDB initialized (`python3 scripts/daily_analysis.py --init-db`)
- [ ] mempool-stack deployed (if Bitcoin Core ready)
- [ ] Systemd service installed
- [ ] Cron job installed
- [ ] Health check passes

### Post-Deployment Verification

```bash
# 1. Health check
./scripts/health_check.sh

# 2. API endpoints
curl http://localhost:8000/health | jq
curl http://localhost:8000/api/prices/latest | jq

# 3. Frontend
xdg-open http://localhost:8000/static/comparison.html

# 4. Wait 10 minutes, verify new data
duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
  "SELECT * FROM prices ORDER BY timestamp DESC LIMIT 1"
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
