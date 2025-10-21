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

- `UTXOracle.py` – The main reference implementation (v9.1)
- `archive/` – Historical versions (v7, v8, v9, start9)
- `live/` – Real-time mempool analysis system (in development)
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

## 🚀 UTXOracle Live - Real-time Mempool Oracle

**New Feature**: Real-time Bitcoin price estimation from mempool analysis (live system in development)

### Quick Start (Live System)

**Prerequisites**:
- Bitcoin Core 25.0+ with ZMQ enabled
- Python 3.11+
- UV package manager

**Installation**:

```bash
# 1. Configure Bitcoin Core ZMQ (add to ~/.bitcoin/bitcoin.conf)
zmqpubrawtx=tcp://127.0.0.1:28332
# Restart bitcoind after configuration change

# 2. Clone repository and checkout live branch
git clone https://github.com/Unbesteveable/UTXOracle.git
cd UTXOracle
git checkout 002-mempool-live-oracle

# 3. Install UV package manager
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env

# 4. Install dependencies
uv sync

# 5. Start backend server
uv run uvicorn live.backend.api:app --reload --host 0.0.0.0 --port 8000

# 6. Open browser to http://localhost:8000
```

**Expected Display**:
- Large price display with confidence score (0.0-1.0)
- Real-time scatter plot of transactions (orange points)
- System stats (received/filtered/active transactions)
- Connection status indicator

**System Requirements**:
- RAM: 8GB minimum (16GB recommended)
- CPU: 4+ cores recommended
- Network: Active Bitcoin Core node with mempool

For detailed setup instructions, see [quickstart.md](specs/002-mempool-live-oracle/quickstart.md)

### Production Deployment (Systemd)

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
```

---

<p align="center">
  <i>Signal from noise.</i>
</p>
