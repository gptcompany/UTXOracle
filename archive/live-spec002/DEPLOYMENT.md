# UTXOracle Live - Production Deployment Guide

## Prerequisites

1. **Bitcoin Core** with ZMQ enabled (see main README)
2. **UV package manager** installed
3. **Systemd** (Linux only)

## Installation Steps

### 1. Create System User

```bash
sudo useradd --system --create-home --shell /bin/bash utxoracle
sudo usermod -aG bitcoin utxoracle  # If Bitcoin runs as 'bitcoin' user
```

### 2. Install Application

```bash
# Clone/copy repository to /opt
sudo git clone https://github.com/username/UTXOracle.git /opt/UTXOracle
sudo chown -R utxoracle:utxoracle /opt/UTXOracle

# Switch user
sudo -u utxoracle -i
cd /opt/UTXOracle

# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Create logs directory
mkdir -p /opt/UTXOracle/logs
```

### 3. Configure Environment

Create `/opt/UTXOracle/.env`:

```bash
# Environment
UTXORACLE_ENV=production
LOG_LEVEL=INFO

# Bitcoin ZMQ endpoints
BITCOIN_ZMQ_TX=tcp://127.0.0.1:28332
BITCOIN_ZMQ_BLOCK=tcp://127.0.0.1:28333

# Server settings
UTXORACLE_HOST=0.0.0.0
UTXORACLE_PORT=8000

# Log directory
LOG_DIR=/opt/UTXOracle/logs
```

### 4. Install Systemd Service

```bash
# Copy service file
sudo cp /opt/UTXOracle/live/utxoracle-live.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable utxoracle-live

# Start service
sudo systemctl start utxoracle-live

# Check status
sudo systemctl status utxoracle-live
```

### 5. Verify Installation

```bash
# Check service logs
sudo journalctl -u utxoracle-live -f

# Test WebSocket connection
wscat -c ws://localhost:8000/ws/mempool

# Check health endpoint
curl http://localhost:8000/health
```

## Service Management

```bash
# Start service
sudo systemctl start utxoracle-live

# Stop service
sudo systemctl stop utxoracle-live

# Restart service
sudo systemctl restart utxoracle-live

# View logs (real-time)
sudo journalctl -u utxoracle-live -f

# View logs (last 100 lines)
sudo journalctl -u utxoracle-live -n 100

# Check service status
sudo systemctl status utxoracle-live
```

## Nginx Reverse Proxy (Optional)

For SSL/TLS and domain name:

```nginx
# /etc/nginx/sites-available/utxoracle-live
server {
    listen 443 ssl http2;
    server_name utxoracle.example.com;

    ssl_certificate /etc/letsencrypt/live/utxoracle.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/utxoracle.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/utxoracle-live /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Troubleshooting

### Service won't start

```bash
# Check detailed logs
sudo journalctl -u utxoracle-live -e

# Common issues:
# 1. Bitcoin Core not running → sudo systemctl start bitcoind
# 2. ZMQ not configured → check bitcoin.conf
# 3. Port 8000 in use → change UTXORACLE_PORT in .env
# 4. Permissions → check /opt/UTXOracle ownership
```

### Memory issues

```bash
# Check memory usage
sudo systemctl status utxoracle-live

# Increase memory limit in service file:
# MemoryMax=1G  # (default is 512M)
sudo systemctl daemon-reload
sudo systemctl restart utxoracle-live
```

### ZMQ connection failed

```bash
# Verify Bitcoin Core ZMQ is enabled
bitcoin-cli getzmqnotifications

# Should show:
# {
#   "type": "pubrawtx",
#   "address": "tcp://127.0.0.1:28332"
# }

# If empty, add to bitcoin.conf:
# zmqpubrawtx=tcp://127.0.0.1:28332
# Then restart: sudo systemctl restart bitcoind
```

## Monitoring

### Prometheus Metrics (Future)

Add to service file environment:

```
Environment="PROMETHEUS_ENABLED=true"
Environment="PROMETHEUS_PORT=9090"
```

### Log Rotation

Systemd journal handles log rotation automatically. To configure:

```bash
# Edit /etc/systemd/journald.conf
SystemMaxUse=1G
RuntimeMaxUse=100M

# Restart journald
sudo systemctl restart systemd-journald
```

## Security Recommendations

1. **Firewall**: Only expose necessary ports
   ```bash
   sudo ufw allow 8000/tcp  # WebSocket (or use nginx proxy)
   sudo ufw enable
   ```

2. **User Isolation**: Service runs as dedicated `utxoracle` user

3. **File Permissions**: Restrict access to /opt/UTXOracle

4. **SSL/TLS**: Use nginx reverse proxy with Let's Encrypt

5. **Rate Limiting**: Configure nginx to prevent abuse

## Backup & Recovery

### Backup (minimal - stateless application)

```bash
# Backup configuration only
tar -czf utxoracle-backup.tar.gz \
    /opt/UTXOracle/.env \
    /opt/UTXOracle/uv.lock \
    /etc/systemd/system/utxoracle-live.service
```

### Recovery

```bash
# Restore from backup
tar -xzf utxoracle-backup.tar.gz -C /

# Reinstall dependencies
cd /opt/UTXOracle
uv sync

# Restart service
sudo systemctl restart utxoracle-live
```

## Updates

```bash
# Stop service
sudo systemctl stop utxoracle-live

# Update code
cd /opt/UTXOracle
git pull origin main

# Update dependencies
uv sync

# Restart service
sudo systemctl start utxoracle-live

# Verify
sudo systemctl status utxoracle-live
```

## Performance Tuning

### Increase Worker Count (Not recommended for MVP)

MVP uses single worker due to in-memory state. For production with persistent storage:

```bash
# Edit service file
ExecStart=... --workers 4  # Multi-worker requires Redis/PostgreSQL

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart utxoracle-live
```

### Optimize for High Traffic

```bash
# Increase file descriptor limits
# Edit /etc/security/limits.conf
utxoracle soft nofile 65536
utxoracle hard nofile 65536

# Restart service
sudo systemctl restart utxoracle-live
```

---

**Status**: Production deployment ready
**Updated**: 2025-10-21
**Version**: 1.0.0
