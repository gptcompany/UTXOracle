# Quickstart Guide - UTXOracle Live

**Feature**: Real-time Mempool Price Oracle
**Branch**: 002-mempool-live-oracle
**Date**: 2025-10-19

## Overview

This guide provides step-by-step instructions to set up and run UTXOracle Live on your local development machine. Expected setup time: **15-30 minutes**.

## Prerequisites

### Required Software

1. **Bitcoin Core ≥ 25.0**
   - Full node with blockchain synced (or at least recent blocks)
   - ZMQ enabled for mempool transaction streaming
   - Disk space: ~600GB for full blockchain (or pruned mode)

2. **Python 3.11+**
   - Check version: `python3 --version`
   - Required for backend server

3. **UV Package Manager**
   - 10-100x faster than pip
   - Install: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### System Requirements

- **OS**: Linux (Ubuntu 22.04+), macOS (13+), or Windows WSL2
- **RAM**: 8GB minimum (16GB recommended for Bitcoin Core + backend)
- **CPU**: 4+ cores recommended
- **Network**: Broadband connection for WebSocket streaming

---

## Step 1: Bitcoin Core Setup

### 1.1 Install Bitcoin Core

**Ubuntu/Debian**:
```bash
# Add Bitcoin PPA
sudo add-apt-repository ppa:bitcoin/bitcoin
sudo apt update
sudo apt install bitcoind bitcoin-qt

# Verify installation
bitcoind --version  # Should show v25.0 or higher
```

**macOS** (Homebrew):
```bash
brew install bitcoin
bitcoind --version
```

**From Source** (all platforms):
```bash
# Download from bitcoin.org
wget https://bitcoincore.org/bin/bitcoin-core-25.0/bitcoin-25.0-x86_64-linux-gnu.tar.gz
tar -xzf bitcoin-25.0-x86_64-linux-gnu.tar.gz
sudo install -m 0755 -o root -g root -t /usr/local/bin bitcoin-25.0/bin/*
```

### 1.2 Configure bitcoin.conf

Create or edit `~/.bitcoin/bitcoin.conf`:

```conf
# Network Settings
testnet=0  # Use mainnet (set testnet=1 for testing)
server=1
daemon=1

# ZMQ Configuration (REQUIRED for UTXOracle Live)
zmqpubhashtx=tcp://127.0.0.1:28332
zmqpubrawblock=tcp://127.0.0.1:28333
zmqpubrawtx=tcp://127.0.0.1:28332

# RPC Configuration
rpcuser=utxoracle
rpcpassword=CHANGE_THIS_PASSWORD
rpcallowip=127.0.0.1

# Performance (optional)
maxmempool=300  # MB
dbcache=2000    # MB (adjust based on available RAM)
```

**Security Note**: Replace `CHANGE_THIS_PASSWORD` with a strong random password.

### 1.3 Start Bitcoin Core

```bash
# Start daemon
bitcoind -daemon

# Check status
bitcoin-cli getblockchaininfo

# Wait for sync (this can take hours/days for first sync)
# Current block should match latest on blockchain explorers

# Check mempool
bitcoin-cli getmempoolinfo
# Should show: "size": 10000+ (active mempool)
```

**Troubleshooting**:
- **"Verifying blocks"**: Initial sync in progress, wait for completion
- **"Not enough memory"**: Reduce `dbcache` in bitcoin.conf
- **ZMQ not working**: Verify `zmqpubrawtx` setting and restart bitcoind

---

## Step 2: UTXOracle Repository Setup

### 2.1 Clone Repository

```bash
# Clone (or fork) repository
git clone https://github.com/username/UTXOracle.git
cd UTXOracle

# Verify you're in correct directory
ls UTXOracle.py  # Should exist (reference implementation)
```

### 2.2 Checkout Feature Branch

```bash
# Switch to mempool live feature branch
git checkout 002-mempool-live-oracle

# Verify branch
git branch --show-current
# Output: 002-mempool-live-oracle

# Check file structure (may not exist yet if not implemented)
ls live/  # Should show backend/, frontend/, shared/ directories
```

---

## Step 3: UV Dependency Management

### 3.1 Install UV

```bash
# Install UV package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Reload shell
source $HOME/.cargo/env  # or restart terminal

# Verify installation
uv --version
# Output: uv 0.1.x or higher
```

### 3.2 Initialize UV Workspace

```bash
# From UTXOracle root directory
cd /path/to/UTXOracle

# Sync dependencies from lockfile (if exists)
uv sync

# Or initialize from scratch (if lockfile missing)
uv init

# Add runtime dependencies
uv add fastapi uvicorn pyzmq

# Add dev dependencies
uv add --dev pytest pytest-asyncio pytest-watch pytest-testmon pytest-cov ruff

# Generate lockfile (COMMIT THIS!)
uv lock
```

### 3.3 Verify Installation

```bash
# Test imports
uv run python -c "import fastapi, zmq; print('✅ Dependencies OK')"

# Check versions
uv run python -c "import fastapi; print(f'FastAPI: {fastapi.__version__}')"
uv run python -c "import zmq; print(f'PyZMQ: {zmq.zmq_version()}')"
```

---

## Step 4: Run Backend Server

### 4.1 Start FastAPI Server

```bash
# Terminal 1: Backend server
cd /path/to/UTXOracle

# Run with hot-reload (development mode)
uv run uvicorn live.backend.api:app --reload --host 0.0.0.0 --port 8000

# Expected output:
# INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
# INFO:     Started reloader process [12345] using StatReload
# INFO:     Started server process [12346]
# INFO:     Waiting for application startup.
# INFO:     Application startup complete.
```

**Troubleshooting**:
- **"Module not found: live.backend.api"**: Backend not implemented yet, see [Step 6](#step-6-development-workflow)
- **"Address already in use"**: Port 8000 occupied, use `--port 8001` or kill process
- **ZMQ connection failed**: Check Bitcoin Core is running and ZMQ enabled

### 4.2 Verify API Health

```bash
# Terminal 2: Test endpoints

# Health check
curl http://localhost:8000/health
# Expected: {"status": "ok", "uptime": 10.5}

# WebSocket connection (wscat tool)
npm install -g wscat  # One-time install
wscat -c ws://localhost:8000/ws/mempool
# Should receive JSON messages every 500ms
```

---

## Step 5: Open Frontend

### 5.1 Access Web Interface

```bash
# Open in default browser
open http://localhost:8000
# macOS: open, Linux: xdg-open, Windows: start

# Or manually navigate to:
# http://localhost:8000
```

### 5.2 Verify Visualization

**Expected Display**:
1. **Price**: Large text showing "Avg: $113,600" (orange/yellow)
2. **Confidence**: Score 0.0-1.0 with color indicator
3. **Scatter Plot**: Orange points appearing right-to-left
4. **Stats**: "Received: X | Filtered: Y | Active: Z | Uptime: Xh Ym"
5. **Connection Status**: Green "Connected" indicator

**Interactive Features**:
- Hover over points: Tooltip shows price + timestamp
- Auto-scaling Y-axis: Adjusts to price range
- Real-time updates: Points appear every 0.5-5 seconds

**Browser Compatibility**:
- ✅ Chrome 120+ (recommended)
- ✅ Firefox 121+
- ✅ Safari 17+
- ❌ Internet Explorer (not supported)

---

## Step 6: Development Workflow

### 6.1 TDD with pytest-watch

```bash
# Terminal 3: Continuous testing
cd /path/to/UTXOracle

# Watch mode: auto-run tests on file changes
uv run ptw -- --testmon --cov=live/backend

# Runs only affected tests (pytest-testmon)
# Shows coverage report (pytest-cov)
```

**Workflow**:
1. **RED**: Write failing test first
```python
# tests/test_zmq_listener.py
def test_zmq_connection():
    listener = ZMQListener()
    assert listener.connect() == True  # FAILS
```

2. **GREEN**: Implement minimal code to pass
```python
# live/backend/zmq_listener.py
class ZMQListener:
    def connect(self):
        return True  # Passes test
```

3. **REFACTOR**: Improve code, tests still pass

### 6.2 Code Quality Tools

```bash
# Linting
uv run ruff check live/

# Auto-fix issues
uv run ruff check live/ --fix

# Format code
uv run ruff format live/

# Type checking (optional)
uv run mypy live/backend --strict
```

### 6.3 Git Workflow

```bash
# Create feature branch for Task 01
git checkout -b feature/task-01-zmq-listener

# Make changes, run tests
# (edit files...)

# Stage and commit
git add live/backend/zmq_listener.py tests/test_zmq_listener.py
git commit -m "Implement ZMQ listener with auto-reconnect

- Listen to Bitcoin Core zmqpubrawtx feed
- Yield RawTransaction dataclass
- Auto-reconnect on connection drop (<5s)
- Tests: 95% coverage

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"

# Push to remote
git push origin feature/task-01-zmq-listener
```

---

## Step 7: Testing & Validation

### 7.1 Unit Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific module tests
uv run pytest tests/test_zmq_listener.py -v

# Run with coverage report
uv run pytest tests/ --cov=live/backend --cov-report=html
open htmlcov/index.html  # View coverage report
```

### 7.2 Integration Tests

```bash
# Long-running tests (requires Bitcoin Core)
uv run pytest tests/integration/ --slow -v

# Example: ZMQ live integration (5 min)
uv run pytest tests/integration/test_zmq_live.py -v
```

### 7.3 Benchmark Tests

```bash
# Performance validation
uv run pytest tests/benchmark/ -v

# Must achieve targets:
# - Tx processing: >1000 tx/sec
# - Price update: <500ms latency
```

---

## Step 8: Production Deployment (Future)

### 8.1 Production Server

```bash
# Production mode (no hot-reload)
uv run uvicorn live.backend.api:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info \
    --access-log

# Note: Single worker only (in-memory state)
```

### 8.2 Systemd Service (Linux)

Create `/etc/systemd/system/utxoracle-live.service`:

```ini
[Unit]
Description=UTXOracle Live - Real-time Mempool Price Oracle
After=network.target bitcoind.service

[Service]
Type=simple
User=utxoracle
WorkingDirectory=/opt/UTXOracle
ExecStart=/home/utxoracle/.cargo/bin/uv run uvicorn live.backend.api:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable utxoracle-live
sudo systemctl start utxoracle-live
sudo systemctl status utxoracle-live
```

### 8.3 Nginx Reverse Proxy (Optional)

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
    }
}
```

---

## Troubleshooting

### Common Issues

**1. "ZMQ connection failed"**
```bash
# Check Bitcoin Core is running
bitcoin-cli getblockchaininfo

# Verify ZMQ settings
grep zmq ~/.bitcoin/bitcoin.conf

# Test ZMQ manually
python3 -c "import zmq; ctx = zmq.Context(); sock = ctx.socket(zmq.SUB); sock.connect('tcp://127.0.0.1:28332'); print('✅ ZMQ OK')"
```

**2. "No transactions appearing"**
```bash
# Check mempool activity
bitcoin-cli getmempoolinfo
# If "size": 0, mempool is empty (low network activity)

# Use testnet for more activity
# Edit bitcoin.conf: testnet=1
# Restart bitcoind
```

**3. "Low confidence score"**
- **Cause**: <100 transactions processed
- **Solution**: Wait 1-2 minutes for warm-up period
- **Normal**: Confidence increases as more transactions accumulate

**4. "Canvas not rendering"**
```bash
# Check browser console (F12)
# Look for JavaScript errors

# Verify WebSocket connection
# Should see: "WebSocket connection established"

# Check network tab
# Should see: ws://localhost:8000/ws/mempool (status: 101 Switching Protocols)
```

**5. "Port 8000 already in use"**
```bash
# Find process using port
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill process or use different port
uv run uvicorn live.backend.api:app --port 8001
```

---

## Next Steps

### For Users

1. **Monitor live prices**: Leave dashboard open, observe real-time updates
2. **Compare accuracy**: Check price vs exchange rates (should be ±2%)
3. **Test reliability**: Leave running 24+ hours, verify no crashes

### For Developers

1. **Read implementation plan**: [plan.md](./plan.md)
2. **Review task breakdown**: [tasks.md](./tasks.md) (after `/speckit.tasks`)
3. **Start implementing**: Begin with Task 01 (Bitcoin Interface)
4. **Follow TDD**: RED → GREEN → REFACTOR for all modules

### For Contributors

1. **Fork repository**: Create your own fork on GitHub
2. **Create feature branch**: `git checkout -b feature/your-feature`
3. **Implement with tests**: Follow TDD workflow
4. **Submit PR**: Use template from `.claude/skills/github-workflow/`

---

## Resources

### Documentation

- **Feature Spec**: [spec.md](./spec.md) - User requirements
- **Implementation Plan**: [plan.md](./plan.md) - Technical architecture
- **Data Models**: [data-model.md](./data-model.md) - Pydantic classes
- **API Contracts**: [contracts/README.md](./contracts/README.md) - JSON schemas

### External Links

- **UV Documentation**: https://astral.sh/uv
- **FastAPI**: https://fastapi.tiangolo.com
- **Bitcoin ZMQ**: https://github.com/bitcoin/bitcoin/blob/master/doc/zmq.md
- **Canvas API**: https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API

### Support

- **Issues**: https://github.com/username/UTXOracle/issues
- **Discussions**: https://github.com/username/UTXOracle/discussions
- **Discord**: (if available)

---

*Quickstart Guide v1.0*
*Created*: 2025-10-19
*Status*: Complete - Ready for use
