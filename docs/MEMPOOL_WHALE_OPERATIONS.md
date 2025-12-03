# Mempool Whale Detection System - Operations Guide

**Version**: 1.0.0
**Last Updated**: 2025-11-19
**Feature**: Real-time Mempool Whale Detection (spec-005)

## Overview

The Mempool Whale Detection System monitors unconfirmed Bitcoin transactions in real-time to detect large whale movements (>100 BTC) and provide predictive signals 10-20 minutes before block confirmation.

### Key Components

1. **Whale Detection Orchestrator** (`whale_detection_orchestrator.py`) - Main coordinator
2. **Mempool Whale Monitor** (`mempool_whale_monitor.py`) - WebSocket client for mempool.space
3. **Whale Flow Detector** (`whale_flow_detector.py`) - Transaction classification logic
4. **Whale Urgency Scorer** (`whale_urgency_scorer.py`) - Fee-based urgency calculation
5. **Whale Alert Broadcaster** (`whale_alert_broadcaster.py`) - WebSocket alert distribution
6. **Correlation Tracker** (`correlation_tracker.py`) - Prediction accuracy tracking
7. **Accuracy Monitor** (`accuracy_monitor.py`) - Alert system for accuracy thresholds

---

## Quick Start

### Prerequisites

- **Bitcoin Core**: Fully synced (mainnet)
- **mempool.space stack**: Running on `localhost:8999` (WebSocket), `localhost:3001` (electrs HTTP)
- **Python**: 3.8+ with `uv` for dependency management
- **Database**: DuckDB (auto-created on first run)

### Start Services

```bash
# 1. Ensure mempool.space stack is running
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack/
docker compose ps  # Verify all services are up

# 2. Start whale detection orchestrator
cd /media/sam/1TB/UTXOracle
python scripts/whale_detection_orchestrator.py

# 3. Start FastAPI dashboard (separate terminal)
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload

# 4. Access dashboard
# http://localhost:8001/static/comparison.html
```

### Stop Services

```bash
# Graceful shutdown (Ctrl+C sends SIGINT)
# Orchestrator handles:
# - WebSocket connection cleanup
# - Database connection closure
# - In-flight transaction processing completion
```

---

## Service Management

### systemd Service (Production)

See `utxoracle-whale-detection.service` in project root:

```bash
# Enable service
sudo systemctl enable /media/sam/1TB/UTXOracle/utxoracle-whale-detection.service

# Start service
sudo systemctl start utxoracle-whale-detection

# Check status
sudo systemctl status utxoracle-whale-detection

# View logs
sudo journalctl -u utxoracle-whale-detection -f

# Restart service
sudo systemctl restart utxoracle-whale-detection

# Stop service
sudo systemctl stop utxoracle-whale-detection
```

---

## Configuration

### Environment Variables

Create `.env` file in project root:

```env
# Database
DB_PATH=data/mempool_predictions.db

# WebSocket Server
BROADCASTER_HOST=0.0.0.0
BROADCASTER_PORT=8765

# Mempool.space
MEMPOOL_WS_URL=ws://localhost:8999/ws/track-mempool-tx

# Whale Detection
WHALE_THRESHOLD_BTC=100.0

# Authentication (JWT)
JWT_SECRET_KEY=your-secret-key-here-change-in-production
JWT_ALGORITHM=HS256

# Monitoring
MEMORY_THRESHOLD_MB=400
MEMORY_MAX_MB=500

# Accuracy Alerts
ACCURACY_WARNING_THRESHOLD=0.75
ACCURACY_CRITICAL_THRESHOLD=0.70
ALERT_COOLDOWN_SECONDS=3600

# Webhook Notifications (optional)
WEBHOOK_URL=https://your-webhook-endpoint.com/alerts
WEBHOOK_ENABLED=false
WEBHOOK_RETRY_MAX_ATTEMPTS=3
WEBHOOK_RETRY_DELAY_SECONDS=5

# Email Alerts (optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_EMAIL_TO=admin@example.com
```

### Command-Line Arguments

```bash
# Whale Detection Orchestrator
python scripts/whale_detection_orchestrator.py \
  --db-path data/custom.db \
  --ws-host 0.0.0.0 \
  --ws-port 8765 \
  --mempool-url ws://localhost:8999/ws/track-mempool-tx \
  --whale-threshold 100.0

# Accuracy Monitor (runs separately if needed)
python scripts/accuracy_monitor.py \
  --db-path data/mempool_predictions.db \
  --warning-threshold 0.75 \
  --critical-threshold 0.70 \
  --check-interval 300  # seconds

# Correlation Tracker (runs separately if needed)
python scripts/correlation_tracker.py \
  --db-path data/mempool_predictions.db \
  --check-interval 600 \
  --retention-days 90
```

---

## Monitoring

### Health Checks

```bash
# API health endpoint
curl http://localhost:8001/health | jq

# Expected response:
# {
#   "status": "healthy",  # or "degraded", "unhealthy"
#   "database": "connected",
#   "uptime_seconds": 12345,
#   "started_at": "2025-11-19T10:00:00Z",
#   "gaps_detected": 0,
#   "missing_dates": []
# }
```

### WebSocket Connection Test

```python
import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as ws:
        # Authenticate
        await ws.send(json.dumps({
            "type": "auth",
            "token": "your-jwt-token-here"
        }))

        # Receive welcome message
        welcome = await ws.recv()
        print(f"Welcome: {welcome}")

        # Receive alerts
        while True:
            message = await ws.recv()
            data = json.loads(message)
            print(f"Alert: {data}")

asyncio.run(test_websocket())
```

### Key Metrics

Monitor these metrics for system health:

1. **Detection Latency**: <1 second from mempool.space to alert broadcast
2. **Memory Usage**: <500MB (alert at 400MB)
3. **WebSocket Connections**: Track authenticated vs unauthenticated clients
4. **Prediction Accuracy**: >80% over 7-day window
5. **False Positive Rate**: <20%
6. **Alert Volume**: ~50-100 whale transactions per day

### Database Queries

```sql
-- Check recent predictions
SELECT * FROM mempool_predictions
ORDER BY prediction_timestamp DESC
LIMIT 10;

-- Check confirmation outcomes
SELECT * FROM prediction_outcomes
WHERE outcome_status IN ('confirmed', 'dropped')
ORDER BY confirmation_timestamp DESC
LIMIT 10;

-- Calculate accuracy over last 7 days
SELECT
  COUNT(*) as total,
  SUM(CASE WHEN prediction_accuracy THEN 1 ELSE 0 END) as accurate,
  SUM(CASE WHEN prediction_accuracy THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as accuracy_pct
FROM prediction_outcomes
WHERE confirmation_timestamp > current_date - INTERVAL 7 DAY;

-- Check memory pressure events
SELECT * FROM system_metrics
WHERE metric_name = 'memory_usage_mb'
ORDER BY timestamp DESC
LIMIT 20;
```

---

## Troubleshooting

### Issue: WebSocket Connection Fails (403 Forbidden)

**Symptoms**: Dashboard shows "DISCONNECTED" badge, browser console shows 403 error

**Causes**:
1. JWT token not sent or invalid
2. Whale detection orchestrator not running
3. Port mismatch (frontend expects 8765, server runs on different port)

**Solutions**:
```bash
# 1. Check if orchestrator is running
ps aux | grep whale_detection_orchestrator

# 2. Check WebSocket server port
lsof -i :8765

# 3. Generate valid JWT token
uv run python api/auth_middleware.py test-client --permissions read write --hours 24

# 4. Verify token in browser localStorage
# Open DevTools > Application > Local Storage > jwt_token

# 5. Restart orchestrator if needed
python scripts/whale_detection_orchestrator.py
```

---

### Issue: Database Errors (Table Not Found)

**Symptoms**: API returns 500 errors, health check shows database errors

**Causes**:
1. Database not initialized
2. Schema migration needed
3. Wrong table names in queries

**Solutions**:
```bash
# 1. Check database file exists
ls -lh data/mempool_predictions.db

# 2. Initialize database manually
python scripts/whale_detection_orchestrator.py --init-db-only

# 3. Verify schema
sqlite3 data/mempool_predictions.db ".schema"

# 4. Drop and recreate (CAUTION: data loss)
rm data/mempool_predictions.db
python scripts/whale_detection_orchestrator.py
```

---

### Issue: High Memory Usage (>400MB)

**Symptoms**: Memory usage warning, slow performance

**Causes**:
1. TransactionCache growing too large
2. Memory leak in WebSocket connections
3. Large mempool (>300MB blockchain mempool)

**Solutions**:
```bash
# 1. Check memory usage
ps aux | grep whale_detection_orchestrator | awk '{print $6/1024 "MB"}'

# 2. Restart service
sudo systemctl restart utxoracle-whale-detection

# 3. Adjust cache size in config
# Edit scripts/config/mempool_config.py:
# cache_max_size: int = 1000  # Reduce from 5000

# 4. Enable memory pressure handling (T051)
# Set MEMORY_THRESHOLD_MB=350 in .env
```

---

### Issue: Low Prediction Accuracy (<80%)

**Symptoms**: Accuracy monitor sends alerts, dashboard shows low correlation

**Causes**:
1. RBF transactions causing false predictions
2. Mempool congestion (fee market volatility)
3. Exchange address list outdated
4. Urgency scoring miscalibrated

**Solutions**:
```bash
# 1. Check recent prediction outcomes
python -c "
import duckdb
conn = duckdb.connect('data/mempool_predictions.db')
result = conn.execute('''
  SELECT outcome_status, COUNT(*) as count
  FROM prediction_outcomes
  WHERE confirmation_timestamp > current_date - INTERVAL 7 DAY
  GROUP BY outcome_status
''').fetchall()
print(result)
"

# 2. Analyze false positives
# Look for patterns in dropped/replaced transactions

# 3. Update exchange address list
# Edit scripts/whale_flow_detector.py:
# EXCHANGE_ADDRESSES list

# 4. Adjust urgency threshold
# Edit scripts/whale_urgency_scorer.py:
# HIGH_URGENCY_THRESHOLD constant
```

---

### Issue: mempool.space WebSocket Disconnects

**Symptoms**: Orchestrator logs show reconnection attempts, gaps in detections

**Causes**:
1. mempool.space stack restarted
2. Network issues
3. High mempool load

**Solutions**:
```bash
# 1. Check mempool.space stack status
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack/
docker compose ps

# 2. Check mempool.space WebSocket endpoint
curl -s http://localhost:8999/api/v1/ws | jq

# 3. Test WebSocket connection
wscat -c ws://localhost:8999/ws/track-mempool-tx

# 4. Restart mempool.space stack if needed
docker compose restart

# 5. Whale detection has auto-reconnect (exponential backoff)
# Monitor logs for successful reconnection
tail -f /var/log/utxoracle-whale-detection.log
```

---

## Performance Tuning

### Optimize Detection Latency

```python
# scripts/mempool_whale_monitor.py

# Reduce processing time:
# 1. Skip non-whale transactions early
# 2. Use async processing for classification
# 3. Batch database writes

# Example optimization:
async def process_transaction(self, tx_data):
    # Quick filter: Check value first
    if tx_data['value_btc'] < self.whale_threshold:
        return None  # Skip immediately

    # Then classify flow type
    flow_type = await self.detector.classify_async(tx_data)

    # Generate signal only if whale
    if flow_type != 'unknown':
        signal = MempoolWhaleSignal(...)
        await self.broadcast_alert(signal)
```

### Optimize Memory Usage

```python
# scripts/utils/transaction_cache.py

# Reduce cache size
self.cache = deque(maxlen=1000)  # Down from 5000

# Implement LRU eviction for confirmed transactions
if len(self.pending) > 500:
    oldest = min(self.pending.items(), key=lambda x: x[1].timestamp)
    del self.pending[oldest[0]]
```

### Optimize Database Writes

```python
# scripts/whale_detection_orchestrator.py

# Batch inserts instead of individual writes
async def batch_persist(self, signals):
    if len(signals) < 10:
        return  # Wait for more

    conn = get_db_connection()
    conn.executemany(
        "INSERT INTO mempool_predictions (...) VALUES (...)",
        [signal.to_tuple() for signal in signals]
    )
    conn.commit()
```

---

## Backup & Recovery

### Database Backup

```bash
# Manual backup
cp data/mempool_predictions.db data/backups/predictions_$(date +%Y%m%d_%H%M%S).db

# Automated daily backup (cron)
0 2 * * * cp /media/sam/1TB/UTXOracle/data/mempool_predictions.db /media/sam/1TB/UTXOracle/data/backups/predictions_$(date +\%Y\%m\%d).db
```

### Database Recovery

```bash
# Restore from backup
cp data/backups/predictions_20251119.db data/mempool_predictions.db

# Verify integrity
sqlite3 data/mempool_predictions.db "PRAGMA integrity_check;"

# Rebuild indexes if needed
sqlite3 data/mempool_predictions.db "REINDEX;"
```

### Disaster Recovery Plan

1. **Stop services**:
   ```bash
   sudo systemctl stop utxoracle-whale-detection
   sudo systemctl stop utxoracle-api
   ```

2. **Restore database** from most recent backup

3. **Verify configuration** files (.env, systemd service)

4. **Test connectivity**:
   - mempool.space WebSocket
   - Bitcoin Core RPC
   - electrs HTTP API

5. **Start services**:
   ```bash
   sudo systemctl start utxoracle-whale-detection
   sudo systemctl start utxoracle-api
   ```

6. **Verify health**: Check `/health` endpoint and dashboard

---

## Security

### JWT Authentication

```bash
# Generate secure secret key (production)
openssl rand -hex 32

# Add to .env
JWT_SECRET_KEY=<generated-key>

# Generate client tokens with expiry
uv run python api/auth_middleware.py prod-client \
  --permissions read write \
  --hours 168  # 7 days
```

### Webhook Security

```bash
# Enable HMAC-SHA256 signature verification
# In .env:
WEBHOOK_SECRET=your-webhook-secret-key

# Webhook receiver should verify signature:
import hmac
import hashlib

def verify_webhook(payload, signature, secret):
    expected = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Network Security

```bash
# Restrict WebSocket server to localhost (development)
BROADCASTER_HOST=127.0.0.1

# Or use reverse proxy with TLS (production)
# nginx configuration:
upstream whale_ws {
    server 127.0.0.1:8765;
}

server {
    listen 443 ssl;
    server_name whale.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /ws {
        proxy_pass http://whale_ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }
}
```

---

## Maintenance

### Regular Tasks

**Daily**:
- Check health endpoint status
- Verify accuracy metrics (>80%)
- Monitor memory usage (<500MB)
- Review error logs

**Weekly**:
- Database backup
- Review prediction outcomes
- Check false positive rate
- Update exchange address list if needed

**Monthly**:
- Clean old predictions (>90 days)
- Review and optimize database indexes
- Update dependencies (uv)
- Test disaster recovery procedure

### Log Rotation

```bash
# /etc/logrotate.d/utxoracle-whale

/var/log/utxoracle-whale-detection.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 sam sam
    sharedscripts
    postrotate
        systemctl reload utxoracle-whale-detection > /dev/null 2>&1 || true
    endscript
}
```

### Database Maintenance

```sql
-- Clean old predictions (>90 days)
DELETE FROM mempool_predictions
WHERE prediction_timestamp < current_date - INTERVAL 90 DAY;

DELETE FROM prediction_outcomes
WHERE confirmation_timestamp < current_date - INTERVAL 90 DAY;

-- Vacuum database to reclaim space
VACUUM;

-- Analyze for query optimization
ANALYZE;
```

---

## Support & Contact

**Documentation**: See `/docs/` directory for additional guides
**Issues**: https://github.com/yourusername/UTXOracle/issues
**Slack/Discord**: #utxoracle-support channel

---

## Changelog

### v1.0.0 (2025-11-19)
- Initial production release
- Real-time whale detection (>100 BTC)
- Dashboard integration with WebSocket updates
- JWT authentication for WebSocket connections
- Prediction accuracy tracking and alerts
- Memory pressure handling
- systemd service configuration

### Future Enhancements
- Redis pub/sub for NautilusTrader integration (T093-T096)
- Advanced filtering UI (flow type, urgency, value) (T037)
- Correlation metrics dashboard display (T043)
- Webhook notification system (T056-T060)
- Performance metrics collection (T053)
- Rate limiting on API endpoints (T052)
