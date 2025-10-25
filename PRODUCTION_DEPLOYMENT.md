# 🚀 Production Deployment: Directory Structure

**Target**: `/media/sam/2TB-NVMe/prod/apps/`
**Rationale**: Separare CODE (development) da APPS (runtime/production)

---

## 📁 Directory Structure

```
/media/sam/2TB-NVMe/prod/apps/
├── mempool/                           # mempool.space Docker stack
│   ├── docker-compose.yml             # Stack configuration
│   ├── .env                           # Environment variables
│   ├── logs/                          # Application logs
│   └── data/                          # Persistent data (NVMe - fast!)
│       ├── electrs/                   # 38GB RocksDB index
│       │   └── db/                    # electrs database
│       ├── mysql/                     # Backend database
│       │   └── data/                  # MySQL data directory
│       └── bitcoin/                   # Bitcoin Core data (if local)
│           └── blocks/                # Blockchain data
│
└── utxoracle/                         # UTXOracle runtime data
    ├── data/                          # DuckDB storage (NVMe - fast queries!)
    │   ├── utxoracle_cache.db         # Price comparison cache
    │   ├── utxoracle_cache.db.wal     # Write-Ahead Log
    │   └── backups/                   # Daily backups
    │       └── utxoracle_cache_YYYY-MM-DD.db
    ├── logs/                          # Analysis logs
    │   ├── daily_analysis.log
    │   └── api.log
    └── config/                        # Production configs
        ├── cron.d/                    # Cron job definitions
        │   └── utxoracle-analysis.cron
        └── systemd/                   # Systemd service files
            ├── utxoracle-api.service
            └── mempool-stack.service

/media/sam/1TB/UTXOracle/              # Git repository (CODE - development)
├── .git/                              # Version control
├── UTXOracle.py                       # CLI script
├── UTXOracle_library.py               # Core algorithm library
├── scripts/                           # Executable scripts
│   ├── daily_analysis.py              # Cron job script
│   ├── setup_mempool_env.sh
│   └── verify_mempool_setup.sh
├── api/                               # FastAPI backend
│   └── main.py
├── frontend/                          # Plotly visualization
│   └── index.html
├── tests/                             # Test suite
├── live/                              # OLD code (to archive)
└── docs/                              # Documentation
```

---

## 🎯 Design Principles

### Separation of Concerns

**CODE** (Git repo: `/media/sam/1TB/UTXOracle/`):
- Version controlled
- Development environment
- Tests, docs, scripts
- No production data
- Lightweight (no large files)

**APPS** (Production: `/media/sam/2TB-NVMe/prod/apps/`):
- Runtime applications (Docker stacks)
- Production data (databases, logs)
- Heavy I/O on fast NVMe
- Not version controlled
- Backup targets

### Why NVMe for Apps?

| Component | Size | I/O Pattern | NVMe Benefit |
|-----------|------|-------------|--------------|
| electrs RocksDB | 38GB | Random read-heavy | 10× faster queries |
| MySQL | ~2GB | Random read/write | Lower latency |
| DuckDB | ~100MB | Sequential read | 5× faster analytics |
| Logs | ~1GB/month | Sequential write | Better throughput |

---

## 🔧 Setup Instructions

### Step 1: Create Production Structure

```bash
# Create base directory structure
sudo mkdir -p /media/sam/2TB-NVMe/prod/apps/{mempool,utxoracle}/{data,logs,config}

# Set ownership
sudo chown -R sam:sam /media/sam/2TB-NVMe/prod/apps

# Create subdirectories
mkdir -p /media/sam/2TB-NVMe/prod/apps/mempool/data/{electrs,mysql,bitcoin}
mkdir -p /media/sam/2TB-NVMe/prod/apps/utxoracle/data/backups
mkdir -p /media/sam/2TB-NVMe/prod/apps/utxoracle/config/{cron.d,systemd}
```

### Step 2: Setup mempool.space Docker Stack

```bash
# Clone mempool.space repository (if not already)
cd /media/sam/2TB-NVMe/prod/apps/mempool
git clone https://github.com/mempool/mempool.git source

# Copy docker-compose to production directory
cp source/docker/docker-compose.yml .

# Create .env configuration
cat > .env << 'EOF'
# Bitcoin Core RPC
CORE_RPC_HOST=127.0.0.1
CORE_RPC_PORT=8332
CORE_RPC_USERNAME=your_rpc_user
CORE_RPC_PASSWORD=your_rpc_password

# Electrs (use NVMe data directory)
ELECTRUM_HOST=electrs
ELECTRUM_PORT=50002
ELECTRUM_TLS_ENABLED=true

# MySQL (use NVMe data directory)
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=mempool
MYSQL_USER=mempool
MYSQL_PASS=mempool

# Backend API
MEMPOOL_BACKEND_HTTP_HOST=0.0.0.0
MEMPOOL_BACKEND_HTTP_PORT=8999

# Frontend
MEMPOOL_FRONTEND_HTTP_PORT=8080

# CORS
MEMPOOL_BACKEND_HTTP_CORS_ALLOW_ALL=true

# Electrs cache (use more RAM on NVMe)
ELECTRS_DB_CACHE_MB=8192
EOF

# Edit docker-compose.yml to use NVMe data paths
nano docker-compose.yml
# Update volumes:
#   - /media/sam/2TB-NVMe/prod/apps/mempool/data/electrs:/data
#   - /media/sam/2TB-NVMe/prod/apps/mempool/data/mysql:/var/lib/mysql
```

### Step 3: Start mempool.space Stack

```bash
cd /media/sam/2TB-NVMe/prod/apps/mempool

# Start all services
docker-compose up -d

# Monitor electrs sync (takes 8-12 hours first time)
docker-compose logs -f electrs

# Verify services
docker-compose ps
curl http://localhost:8999/api/blocks/tip/height
```

### Step 4: Setup DuckDB Data Directory

```bash
# Initialize DuckDB schema
cd /media/sam/1TB/UTXOracle

# Point scripts to NVMe data directory
export UTXORACLE_DATA_DIR="/media/sam/2TB-NVMe/prod/apps/utxoracle/data"

# Run initialization
python3 scripts/daily_analysis.py --init-db
# Creates: /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db
```

### Step 5: Configure Cron Job

```bash
# Create cron job file
cat > /media/sam/2TB-NVMe/prod/apps/utxoracle/config/cron.d/utxoracle-analysis.cron << 'EOF'
# UTXOracle Analysis - Every 10 minutes
*/10 * * * * sam cd /media/sam/1TB/UTXOracle && \
  UTXORACLE_DATA_DIR=/media/sam/2TB-NVMe/prod/apps/utxoracle/data \
  python3 scripts/daily_analysis.py \
  >> /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/daily_analysis.log 2>&1
EOF

# Install cron job
sudo ln -sf /media/sam/2TB-NVMe/prod/apps/utxoracle/config/cron.d/utxoracle-analysis.cron \
  /etc/cron.d/utxoracle-analysis

# Verify cron
sudo service cron reload
crontab -l
```

### Step 6: Setup API Service (Systemd)

```bash
# Create systemd service
cat > /media/sam/2TB-NVMe/prod/apps/utxoracle/config/systemd/utxoracle-api.service << 'EOF'
[Unit]
Description=UTXOracle API Server
After=network.target

[Service]
Type=simple
User=sam
WorkingDirectory=/media/sam/1TB/UTXOracle
Environment="UTXORACLE_DATA_DIR=/media/sam/2TB-NVMe/prod/apps/utxoracle/data"
ExecStart=/usr/bin/python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

StandardOutput=append:/media/sam/2TB-NVMe/prod/apps/utxoracle/logs/api.log
StandardError=append:/media/sam/2TB-NVMe/prod/apps/utxoracle/logs/api.log

[Install]
WantedBy=multi-user.target
EOF

# Install service
sudo ln -sf /media/sam/2TB-NVMe/prod/apps/utxoracle/config/systemd/utxoracle-api.service \
  /etc/systemd/system/utxoracle-api.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable utxoracle-api
sudo systemctl start utxoracle-api

# Check status
sudo systemctl status utxoracle-api
```

---

## 🔍 Configuration Updates

### Update scripts/daily_analysis.py

```python
import os
from pathlib import Path

# Use environment variable or default to NVMe
DATA_DIR = os.getenv(
    'UTXORACLE_DATA_DIR',
    '/media/sam/2TB-NVMe/prod/apps/utxoracle/data'
)
DB_FILE = Path(DATA_DIR) / "utxoracle_cache.db"
```

### Update api/main.py

```python
import os
from pathlib import Path

DATA_DIR = os.getenv(
    'UTXORACLE_DATA_DIR',
    '/media/sam/2TB-NVMe/prod/apps/utxoracle/data'
)
DB_FILE = Path(DATA_DIR) / "utxoracle_cache.db"
```

---

## 📊 Data Flow

```
┌────────────────────────────────────────────────────┐
│  DEVELOPMENT (/media/sam/1TB/UTXOracle/)           │
│  - Git repository (version controlled)             │
│  - Scripts: daily_analysis.py, api/main.py         │
│  - Tests, docs, configuration                      │
└────────────────────┬───────────────────────────────┘
                     │
                     │ Reads code, executes
                     ▼
┌────────────────────────────────────────────────────┐
│  PRODUCTION (/media/sam/2TB-NVMe/prod/apps/)       │
├────────────────────────────────────────────────────┤
│  mempool/ (Docker)                                 │
│  ├─ localhost:8999/api (REST)                      │
│  └─ electrs: 38GB RocksDB (NVMe - fast!)           │
│                     │                               │
│                     │ HTTP API calls                │
│                     ▼                               │
│  Cron Job: daily_analysis.py (every 10 min)        │
│  ├─ Fetch: mempool API → transactions              │
│  ├─ Calculate: UTXOracle algorithm → price         │
│  └─ Save: DuckDB (NVMe - fast writes!)             │
│                     │                               │
│                     │ Read queries                  │
│                     ▼                               │
│  API: utxoracle-api.service (systemd)              │
│  └─ localhost:8000/api (FastAPI)                   │
│                     │                               │
│                     │ JSON response                 │
│                     ▼                               │
│  Frontend: Plotly.js visualization                 │
└────────────────────────────────────────────────────┘
```

---

## 💾 Backup Strategy

### Automated Daily Backups

```bash
# Create backup script
cat > /media/sam/2TB-NVMe/prod/apps/utxoracle/config/backup.sh << 'EOF'
#!/bin/bash
# Daily DuckDB backup

DATA_DIR="/media/sam/2TB-NVMe/prod/apps/utxoracle/data"
BACKUP_DIR="$DATA_DIR/backups"
DATE=$(date +%Y-%m-%d)

# Backup DuckDB
cp "$DATA_DIR/utxoracle_cache.db" "$BACKUP_DIR/utxoracle_cache_$DATE.db"

# Keep only last 30 days
find "$BACKUP_DIR" -name "utxoracle_cache_*.db" -mtime +30 -delete

echo "Backup completed: $DATE"
EOF

chmod +x /media/sam/2TB-NVMe/prod/apps/utxoracle/config/backup.sh

# Add to cron (3 AM daily)
echo "0 3 * * * sam /media/sam/2TB-NVMe/prod/apps/utxoracle/config/backup.sh" | \
  sudo tee -a /etc/cron.d/utxoracle-analysis
```

### Manual Backup Commands

```bash
# Backup DuckDB
cp /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
   /media/sam/2TB-NVMe/prod/apps/utxoracle/data/backups/utxoracle_cache_$(date +%Y%m%d_%H%M).db

# Backup electrs (WARNING: 38GB!)
tar -czf electrs_backup_$(date +%Y%m%d).tar.gz \
  -C /media/sam/2TB-NVMe/prod/apps/mempool/data/electrs .

# Backup MySQL
docker exec mempool-mysql mysqldump -umempool -pmempool mempool | \
  gzip > mysql_backup_$(date +%Y%m%d).sql.gz
```

---

## 🎯 Benefits of This Structure

| Aspect | Benefit |
|--------|---------|
| **Performance** | NVMe: 10× faster than HDD for database I/O |
| **Organization** | Clear separation: code vs data vs logs |
| **Backup** | Easy to backup `/prod/apps/` directory only |
| **Development** | Git repo stays clean (no large data files) |
| **Scaling** | Can move `/prod/apps/` to different server |
| **Monitoring** | All logs in one place (`/prod/apps/*/logs/`) |
| **Security** | Prod data separated from development |

---

## 📋 Verification Checklist

```bash
# 1. Directory structure
ls -la /media/sam/2TB-NVMe/prod/apps/
ls -la /media/sam/2TB-NVMe/prod/apps/mempool/data/
ls -la /media/sam/2TB-NVMe/prod/apps/utxoracle/data/

# 2. mempool.space running
docker-compose -f /media/sam/2TB-NVMe/prod/apps/mempool/docker-compose.yml ps
curl http://localhost:8999/api/blocks/tip/height

# 3. DuckDB accessible
ls -lh /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db

# 4. Cron job active
sudo cat /etc/cron.d/utxoracle-analysis
tail -f /media/sam/2TB-NVMe/prod/apps/utxoracle/logs/daily_analysis.log

# 5. API service running
sudo systemctl status utxoracle-api
curl http://localhost:8000/api/prices/latest

# 6. Disk usage
df -h /media/sam/2TB-NVMe/prod/apps/
du -sh /media/sam/2TB-NVMe/prod/apps/*
```

---

## 🔄 Migration from Old Setup

Se hai già mempool.space in `/media/sam/1TB/mempool/`:

```bash
# Stop old stack
cd /media/sam/1TB/mempool/docker
docker-compose down

# Move data to NVMe (CAREFUL - 38GB transfer!)
sudo rsync -avh --progress \
  /media/sam/1TB/mempool/docker/data/ \
  /media/sam/2TB-NVMe/prod/apps/mempool/data/

# Start new stack on NVMe
cd /media/sam/2TB-NVMe/prod/apps/mempool
docker-compose up -d

# Archive old installation
mv /media/sam/1TB/mempool /media/sam/1TB/mempool.backup
```

---

**Ready to setup?** Vuoi che creo gli script automatici per setup completo?
