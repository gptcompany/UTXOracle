# Temporary Configuration - Public mempool.space API

**Status**: Spec-003 implementation using public APIs while Bitcoin Core re-syncs
**Date**: 2025-10-27
**Reason**: HDD change requires Bitcoin Core blockchain re-sync (estimated completion: several days)

---

## Current Configuration

### `.env` File Changes

```bash
# Mempool.space Backend
# TEMPORARY: Using public API while Bitcoin Core re-syncs blockchain
# Switch back to http://localhost:8999 when self-hosted stack is operational
MEMPOOL_API_URL=https://mempool.space
MEMPOOL_WS_URL=wss://mempool.space

# Bitcoin Core
# TEMPORARY: Bitcoin Core is re-syncing blockchain after HDD change
# Using mock transactions until node is fully synced
BITCOIN_RPC_URL=http://127.0.0.1:8332
BITCOIN_RPC_USER=your_user
BITCOIN_RPC_PASSWORD=your_password
BITCOIN_DATADIR=/home/sam/.bitcoin
```

### Code Changes

#### `scripts/daily_analysis.py`
- **Line 54**: `load_dotenv(env_path, override=True)` - Prioritizes .env file over environment variables
- **Line 186**: `logging.warning("Using mock Bitcoin RPC - implement actual RPC connection")` - Mock transactions active

#### `api/main.py`
- **Line 31**: `load_dotenv(env_path, override=True)` - Prioritizes .env file over environment variables

---

## What Works Now

✅ **Full functionality** with limitations:
- Exchange prices from public mempool.space API (real-time BTC/USD)
- UTXOracle prices from **mock transactions** (placeholder: $100,000)
- Price comparison and statistics
- DuckDB storage
- FastAPI REST API (all endpoints functional)
- Frontend dashboard (Plotly.js visualization)

⚠️ **Limitations**:
- UTXOracle prices are NOT real (using 3 mock transactions)
- Cannot access self-hosted mempool.space stack (requires Bitcoin Core)

---

## Migration Path: When Bitcoin Core is Synced

### Step 1: Verify Bitcoin Core is Ready

```bash
# Check sync status
bitcoin-cli getblockchaininfo | jq '.blocks, .headers, .verificationprogress'

# Should show:
# - blocks == headers (fully synced)
# - verificationprogress >= 0.9999
```

### Step 2: Deploy Self-Hosted mempool.space Stack

```bash
# Navigate to stack directory
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack

# Start Docker stack (electrs will take 3-4 hours to index on NVMe)
docker-compose up -d

# Monitor electrs sync
docker-compose logs -f electrs
# Wait for: "finished full compaction"

# Verify all services healthy
docker-compose ps
# All should show "Up" and "(healthy)"
```

### Step 3: Update `.env` Configuration

```bash
# Change MEMPOOL_API_URL back to localhost
sed -i 's|MEMPOOL_API_URL=https://mempool.space|MEMPOOL_API_URL=http://localhost:8999|' .env
sed -i 's|MEMPOOL_WS_URL=wss://mempool.space|MEMPOOL_WS_URL=ws://localhost:8999|' .env
```

### Step 4: Implement Real Bitcoin RPC Connection

Edit `scripts/daily_analysis.py`, replace mock implementation:

```python
def fetch_bitcoin_transactions(bitcoin_datadir: str) -> List[dict]:
    """
    Fetch recent transactions from Bitcoin Core RPC.

    Uses cookie authentication from Bitcoin data directory.
    """
    from bitcoin.rpc import RawProxy

    # Connect to Bitcoin Core RPC
    rpc = RawProxy(btc_conf_file=f"{bitcoin_datadir}/bitcoin.conf")

    # Get latest block
    best_block_hash = rpc.getbestblockhash()
    block_data = rpc.getblock(best_block_hash, 2)  # verbosity=2 includes tx details

    # Return transactions from latest block
    return block_data['tx']
```

Install python-bitcoinrpc:
```bash
uv pip install python-bitcoinrpc
```

### Step 5: Test Full System

```bash
# Test Bitcoin RPC connection
python3 -c "from bitcoin.rpc import RawProxy; rpc = RawProxy(); print(rpc.getblockcount())"

# Test mempool.space stack
curl http://localhost:8999/api/v1/prices | jq .USD

# Run daily analysis manually
python3 scripts/daily_analysis.py --verbose

# Verify DuckDB has real data
duckdb /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db \
  "SELECT * FROM prices ORDER BY timestamp DESC LIMIT 1"
```

### Step 6: Restart Services

```bash
# Restart API server (if running as systemd service)
sudo systemctl restart utxoracle-api

# Or restart manually if running in background
pkill -f "uvicorn api.main:app"
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 &
```

### Step 7: Verify Real Data Flow

```bash
# Check API returns real UTXOracle prices (not $100,000 mock)
curl http://localhost:8000/api/prices/latest | jq '.utxoracle_price, .confidence'

# Open dashboard to see real comparison
firefox http://localhost:8000/static/comparison.html
```

---

## Testing Checklist

- [ ] Bitcoin Core fully synced (`verificationprogress >= 0.9999`)
- [ ] mempool-stack Docker containers all healthy
- [ ] electrs index completed (~38GB on NVMe)
- [ ] mempool.space frontend accessible at `http://localhost:8080`
- [ ] mempool.space API returns prices: `curl http://localhost:8999/api/v1/prices`
- [ ] Bitcoin RPC connection works in Python
- [ ] `.env` updated to use `http://localhost:8999`
- [ ] `scripts/daily_analysis.py` uses real RPC (not mock)
- [ ] Daily analysis script runs without errors
- [ ] DuckDB shows real UTXOracle prices (not $100,000)
- [ ] API endpoints return real data
- [ ] Frontend dashboard shows real comparison

---

## Rollback Instructions

If issues occur, revert to public API:

```bash
# Restore public API configuration
sed -i 's|MEMPOOL_API_URL=http://localhost:8999|MEMPOOL_API_URL=https://mempool.space|' .env

# Restore mock transactions (comment out real RPC code)
# Edit scripts/daily_analysis.py - restore mock implementation

# Restart services
sudo systemctl restart utxoracle-api
```

---

## Current System Status

| Component | Status | Configuration |
|-----------|--------|---------------|
| Bitcoin Core | ⚠️ Re-syncing | Blockchain download in progress |
| mempool-stack | ⚠️ Not started | Waiting for Bitcoin Core sync |
| Public mempool.space API | ✅ Active | `https://mempool.space` |
| Mock Transactions | ✅ Active | 3 hardcoded transactions |
| DuckDB | ✅ Operational | 1 entry with mock data |
| FastAPI Server | ✅ Running | All endpoints functional |
| Frontend Dashboard | ✅ Accessible | `http://localhost:8000/static/comparison.html` |
| Pytest Suite | ✅ Passing | 14/14 tests |

---

## Timeline Estimate

**Current Date**: 2025-10-27
**Bitcoin Core Sync Started**: ~today
**Estimated Completion**: 3-7 days (depends on network speed)
**electrs Index**: +3-4 hours after Bitcoin Core sync
**Total Time to Production**: ~4-8 days

---

## Support

If issues arise during migration:

1. Check logs: `/tmp/utxoracle_api.log`
2. Check Bitcoin Core: `tail -f ~/.bitcoin/debug.log`
3. Check Docker: `docker-compose logs -f`
4. Verify connectivity: `curl http://localhost:8999/api/v1/prices`
5. Test RPC: `bitcoin-cli getblockchaininfo`

---

**Last Updated**: 2025-10-27 by Claude Code
**Spec**: 003-mempool-integration-refactor
**Phase**: 4 (API & Visualization) - Completed with temporary config
