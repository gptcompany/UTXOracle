<p align="center">
  <img src="https://utxo.live/oracle/oracle_yesterday.png" alt="UTXOracle Chart" width="100%">
</p>

# UTXOracle

**UTXOracle** is a Bitcoin-native, exchange-free price oracle that calculates the market price of Bitcoin directly from the blockchain.

Unlike traditional oracles that rely on exchange APIs, UTXOracle identifies the most statistically probable BTC/USD exchange rate by analyzing recent transactions on-chain — no external price feeds required.

> ⚡ Pure Python. No dependencies. No assumptions. Just Bitcoin data.

---

## 🔍 How It Works

UTXOracle analyzes confirmed Bitcoin transactions and uses statistical clustering to isolate a "canonical" price point:
- Filters out coinbase, self-spends, and spam transactions.
- Focuses on economically meaningful outputs (within a dynamic BTC range).
- Calculates a volume-weighted median from clustered prices across a recent window of blocks.

The result is a Bitcoin price **derived from actual usage**, not speculative trading.

---

## 🧠 Why It Matters

- 🛑 **Exchange Independence**: Trust the chain, not custodians.
- 🔎 **Transparency**: Every price is reproducible from public block data.
- 🎯 **On-Chain Signal**: Derived from organic BTC/USD activity.
- 🐍 **Minimalism**: The core logic fits in a single, readable Python file.

---

## 📦 Getting Started

Clone the repo and run the reference script:

```bash
git clone https://github.com/Unbesteveable/UTXOracle.git
cd UTXOracle
python3 UTXOracle.py
```

This will connect to your local `bitcoind` node and print the current UTXOracle price.

**Requirements:**
- A running Bitcoin Core node (RPC enabled)
- Python 3.8+

---

## 🌐 Live Example

Check the live visual version of UTXOracle here:  
📺 **https://utxo.live**

- Includes historical charts and real-time YouTube stream
- Based entirely on the same logic as the reference script

---

## 🛠 Structure

- `UTXOracle.py` – The main reference implementation (v9.1) - IMMUTABLE
- `UTXOracle_library.py` – Reusable library extracted from reference implementation
- `api/` – FastAPI backend for price comparison dashboard
- `frontend/` – Plotly.js visualization dashboard
- `scripts/` – Integration service and batch processing utilities
- `archive/` – Historical versions (v7, v8, v9, spec-002)
- `docs/` – Algorithm documentation and task specifications

---

## 📚 Documentation

- **[CHANGELOG_SPEC.md](CHANGELOG_SPEC.md)** – Detailed version evolution (v7→v8→v9→v9.1) with trigger-response-philosophy analysis
- **[CLAUDE.md](CLAUDE.md)** – Claude Code development instructions
- **[MODULAR_ARCHITECTURE.md](MODULAR_ARCHITECTURE.md)** – Black box module design philosophy
- **[TECHNICAL_SPEC.md](TECHNICAL_SPEC.md)** – MVP implementation plan for live system

---

## ⚖️ License

UTXOracle is licensed under the [Blue Oak Model License 1.0.0](./LICENSE), a permissive open-source license designed to be simple, fair, and developer-friendly.

You are free to use, modify, and distribute this software with very few restrictions.

---

## 🙏 Credits

Created by [@Unbesteveable](https://github.com/Unbesteveable)  
Inspired by the idea that **Bitcoin's price should come from Bitcoin itself.**

---

## 🚀 Price Comparison Dashboard - UTXOracle vs Exchange Prices

**New Feature** (spec-003): Self-hosted infrastructure with real-time price comparison

### Architecture Overview

**4-Layer Hybrid Architecture**:

1. **Reference Implementation** (`UTXOracle.py`) - IMMUTABLE, educational transparency
2. **Reusable Library** (`UTXOracle_library.py`) - Extracted core algorithm for reuse
3. **Self-Hosted Infrastructure** - mempool.space + electrs Docker stack (replaces custom ZMQ parsing)
4. **Integration & Visualization** - FastAPI backend + Plotly.js frontend

**Benefits**:
- ✅ Zero custom ZMQ/transaction parsing code (1,122 lines eliminated)
- ✅ Battle-tested mempool.space infrastructure
- ✅ Focus on core algorithm, not infrastructure
- ✅ Real-time price comparison every 10 minutes
- ✅ Historical data visualization (7/30/90 days)

### Quick Start (Price Comparison Dashboard)

**Prerequisites**:
- Bitcoin Core 25.0+ (fully synced, RPC enabled)
- Docker & Docker Compose
- Python 3.10+ (3.11+ recommended)
- UV package manager ([install guide](https://docs.astral.sh/uv/))
- 50GB free disk space (NVMe recommended for electrs index)

> **📝 Note**: During Bitcoin Core re-sync, the system can run with **public mempool.space API** temporarily. See `specs/003-mempool-integration-refactor/TEMPORARY_CONFIG.md` for details.

**Installation**:

```bash
# 1. Clone repository
git clone https://github.com/Unbesteveable/UTXOracle.git
cd UTXOracle
git checkout 003-mempool-integration-refactor

# 2. Install UV package manager
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env

# 3. Install dependencies
uv sync

# 4. Deploy mempool.space infrastructure (3-4 hour electrs sync on NVMe)
bash scripts/setup_full_mempool_stack.sh

# 5. Monitor electrs sync (wait for "finished full compaction")
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker-compose logs -f electrs

# 6. Start FastAPI backend (after electrs sync completes)
sudo systemctl start utxoracle-api

# 7. Open price comparison dashboard
xdg-open http://localhost:8000/static/comparison.html
```

**Expected Display**:
- Time series chart: UTXOracle price (green) vs Exchange price (red)
- Stats cards: Average difference, Max difference, Correlation
- Timeframe selector: 7/30/90 days
- Black background + orange theme (UTXOracle branding)

**System Requirements**:
- RAM: 16GB minimum (32GB recommended for electrs)
- CPU: 4+ cores recommended
- Disk: 50GB free (NVMe recommended for fast electrs sync)
- Network: Active Bitcoin Core node

For detailed setup instructions, see [specs/003-mempool-integration-refactor/spec.md](specs/003-mempool-integration-refactor/spec.md)

### Production Deployment

**Systemd Services**:
- `utxoracle-api.service` - FastAPI backend (auto-starts on boot)
- Cron job: `scripts/daily_analysis.py` (runs every 10 minutes)

**Docker Stack** (mempool.space + electrs):
```bash
cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
docker-compose up -d  # Auto-starts on boot
```

**Health Checks**:
```bash
# API status
curl http://localhost:8000/health | jq

# Latest price comparison
curl http://localhost:8000/api/prices/latest | jq

# Historical data (7 days)
curl http://localhost:8000/api/prices/historical?days=7 | jq
```

### Migration from spec-002

If upgrading from the old spec-002 implementation (custom ZMQ/transaction parsing):

1. Backup old `/live/` directory (archived in `archive/live-spec002/`)
2. Follow installation steps above
3. Review [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for detailed migration path

**Code Reduction** (spec-002 → spec-003):
- **3,102 → 1,598 core lines** (48.5% reduction)
- Eliminated 1,122 lines of custom ZMQ/transaction parsing
- Replaced by battle-tested mempool.space Docker stack
- 50% maintenance reduction (no binary parsing complexity)
- See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for complete details

**Implementation Status**: ✅ **Phase 0-4 Complete** (72% of spec-003)
- Full documentation: `specs/003-mempool-integration-refactor/IMPLEMENTATION_STATUS.md`

---

<p align="center">
  <i>Signal from noise.</i>
</p>
