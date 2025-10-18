# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

UTXOracle is a Bitcoin-native, exchange-free price oracle that calculates the market price of Bitcoin directly from blockchain data. It analyzes on-chain transactions using statistical clustering to derive BTC/USD prices without relying on external exchange APIs.

**Key Principles**:
- Pure Python implementation (no external dependencies beyond standard library)
- Single-file reference implementation for clarity and transparency
- Direct Bitcoin Core RPC connection only
- Privacy-first: no external price feeds

## Running UTXOracle

### Main Script

```bash
# Run for yesterday's price (default)
python3 UTXOracle.py

# Run for specific date
python3 UTXOracle.py -d 2025/10/15

# Use recent 144 blocks
python3 UTXOracle.py -rb

# Specify Bitcoin data directory
python3 UTXOracle.py -p /path/to/bitcoin/data

# View all options
python3 UTXOracle.py -h
```

### Batch Processing

```bash
# Process date range in parallel (12 workers)
python3 scripts/utxoracle_batch.py 2025/10/01 2025/10/10 /home/sam/.bitcoin 12

# Suppress browser opening for batch mode
python3 UTXOracle.py -d 2025/10/17 --no-browser
```

### Requirements

- **Python 3.8+** (standard library only)
- **Bitcoin Core node** (fully synced, RPC enabled)
- **RPC Access**: Either cookie authentication (default) or bitcoin.conf configuration

## Architecture

### Current Implementation (v9.1)

**UTXOracle.py** - Single-file reference implementation using a sequential 12-step algorithm:

1. **Configuration Options** - Parse command-line args, detect OS, set Bitcoin data paths
2. **Establish RPC Connection** - Connect to Bitcoin Core via RPC (cookie or bitcoin.conf auth)
3. **Check Dates** - Validate date input and determine block range
4. **Find Block Hashes** - Retrieve block hashes for analysis window
5. **Initialize Histogram** - Set up data structure for transaction value distribution
6. **Load Histogram from Transaction Data** - Extract and process on-chain transactions
7. **Remove Round Bitcoin Amounts** - Filter out transactions with round BTC amounts (likely non-market activity)
8. **Construct the Price Finding Stencil** - Create statistical clustering framework
9. **Estimate a Rough Price** - Initial price approximation from clustered data
10. **Create Intraday Price Points** - Generate hourly/block-level price estimates
11. **Find the Exact Average Price** - Calculate final volume-weighted median price
12. **Generate a Price Plot HTML Page** - Create interactive visualization with canvas/JavaScript

The code is intentionally verbose and linear (top-to-bottom execution) for educational transparency, not production efficiency.

### Future Architecture Plans

See **MODULAR_ARCHITECTURE.md** and **TECHNICAL_SPEC.md** for planned modular Rust-based architecture:

- **5 independent modules**: Bitcoin Interface, Transaction Processor, Mempool Analyzer, Data Streamer, Visualization Renderer
- **Real-time mempool analysis** with WebGL visualization
- **ZMQ integration** for live transaction streaming
- **Black box principle**: Each module independently replaceable without affecting others

## File Structure

```
UTXOracle/
├── pyproject.toml            # UV workspace root
├── uv.lock                   # Dependency lockfile (commit this!)
│
├── UTXOracle.py              # Reference implementation v9.1 (IMMUTABLE)
│
├── .claude/                  # Claude Code configuration
│   ├── agents/               # Specialized subagents (complex reasoning)
│   │   ├── bitcoin-onchain-expert.md      # Task 01 - ZMQ listener
│   │   ├── transaction-processor.md       # Task 02 - Binary parsing
│   │   ├── mempool-analyzer.md            # Task 03 - Price estimation
│   │   ├── data-streamer.md               # Task 04 - WebSocket API
│   │   ├── visualization-renderer.md      # Task 05 - Canvas/WebGL
│   │   └── tdd-guard.md                   # TDD enforcement
│   ├── skills/               # Template-driven automation (token efficiency)
│   │   ├── pytest-test-generator/         # Test boilerplate (83% savings)
│   │   └── github-workflow/               # PR/Issue templates (79% savings)
│   ├── prompts/
│   │   └── utxoracle-system.md            # Orchestration rules
│   └── settings.local.json   # Permissions & hooks
│
├── core/                     # Shared algorithm modules (future)
│   ├── __init__.py
│   ├── histogram.py          # Steps 5-7 (extracted from UTXOracle.py)
│   ├── stencil.py            # Steps 8-9
│   ├── convergence.py        # Step 11
│   └── bitcoin_rpc.py        # Step 2
│
├── live/                     # Mempool live system (implementation target)
│   ├── backend/
│   │   ├── zmq_listener.py   # Bitcoin ZMQ interface (Task 01)
│   │   ├── tx_processor.py   # Transaction parser/filter (Task 02)
│   │   ├── mempool_analyzer.py  # Real-time price estimation (Task 03)
│   │   ├── api.py            # FastAPI WebSocket server (Task 04)
│   │   ├── models.py         # Data models (Pydantic)
│   │   └── config.py         # Configuration
│   ├── frontend/
│   │   ├── index.html        # Main page
│   │   ├── mempool-viz.js    # Canvas 2D renderer (MVP)
│   │   ├── mempool-viz-webgl.js  # Three.js renderer (production)
│   │   └── styles.css        # Styling
│   └── shared/
│       └── models.py         # Shared data structures
│
├── scripts/                  # Utilities
│   ├── utxoracle_batch.py    # Batch processor
│   └── README.md
│
├── docs/                     # Documentation
│   ├── algorithm_concepts.md # Algorithm breakdown by concept
│   ├── tasks/                # Task breakdown for agents
│   │   ├── 00_OVERVIEW.md    # Project overview, agent assignment
│   │   ├── 01_bitcoin_interface.md  # ZMQ listener task
│   │   ├── 02_transaction_processor.md
│   │   ├── 03_mempool_analyzer.md
│   │   ├── 04_data_streamer.md
│   │   └── 05_visualization_renderer.md
│   ├── IMPLEMENTATION_CHECKLIST.md  # Progress tracking
│   ├── api.md                # WebSocket API spec (future)
│   └── deployment.md         # Deployment guide (future)
│
├── tests/
│   ├── test_core/            # Core algorithm tests
│   ├── test_live/            # Mempool system tests
│   ├── integration/          # Integration tests
│   └── fixtures/             # Test data
│
├── historical_data/
│   └── html_files/           # 672 HTML files (Dec 2023 - Oct 2025)
│
├── archive/
│   ├── v9/                   # Previous versions
│   ├── v8/
│   ├── v7/
│   └── start9/
│
├── CLAUDE.md                 # THIS FILE - Claude Code instructions
├── MODULAR_ARCHITECTURE.md   # Black box module design
├── TECHNICAL_SPEC.md         # MVP KISS implementation plan
├── TECHNICAL_SPEC_ADVANCED.md  # Production features (WebGL, Rust, etc.)
├── SKILL_SUMMARY.md          # Agent Skills vs Subagents analysis
├── HISTORICAL_DATA.md        # 672 days of historical analysis
└── README.md
```

## Agent & Skill Architecture

### **Subagents** (6) - Complex Reasoning
Specialized agents for deep domain expertise and multi-step workflows.

| Agent | Task | Responsibility | Token Cost |
|-------|------|---------------|-----------|
| bitcoin-onchain-expert | 01 | ZMQ listener, Bitcoin Core integration | ~8,000 |
| transaction-processor | 02 | Binary parsing, UTXOracle filtering | ~7,500 |
| mempool-analyzer | 03 | Histogram, stencil, price estimation | ~9,000 |
| data-streamer | 04 | FastAPI WebSocket server | ~6,000 |
| visualization-renderer | 05 | Canvas 2D + Three.js WebGL | ~7,000 |
| tdd-guard | - | TDD enforcement, coverage validation | ~5,000 |

**Usage**: Invoke via Claude Code for complex implementation tasks.

### **Skills** (2) - Template-Driven Automation
Lightweight templates for repetitive operations with 70-80% token savings.

| Skill | Purpose | Token Savings |
|-------|---------|---------------|
| pytest-test-generator | Auto-generate test boilerplate | 83% (3,000→500) |
| github-workflow | PR/Issue/Commit templates | 79% (18,900→4,000) |

**Usage**: Automatically triggered by keywords like "generate tests" or "create PR".

### **Modus Operandi**
See `.claude/prompts/utxoracle-system.md` for:
- Task classification rules (01-05)
- TDD workflow enforcement
- Agent spawning patterns
- Checkpoint management
- Error handling protocols

**Combined Token Savings**: ~87,000 tokens per full pipeline (27% reduction)

## Development Principles

### Vibe Coding Architecture (Eskil Steenberg)

This project follows "black box" architecture principles for maintainability and AI-assisted development:

1. **Constant developer velocity** - Fast iteration regardless of project size
2. **One module, one person** - Each module can be owned/developed independently
3. **Everything replaceable** - If you don't understand a module, rewrite it without breaking others
4. **Black box interfaces** - Modules communicate only through clean, defined APIs
5. **Write 5 lines today** - Avoid future context switching by writing upfront, not editing later

**Why this matters**: When AI generates complex code, we can easily replace that specific module without touching the rest of the system. Each module is a manageable, bite-sized chunk.

**Reference**: [Eskil Steenberg - Architecting LARGE Software Projects](https://www.youtube.com/watch?v=sSpULGNHyoI)

### Code Philosophy

1. **Transparency over efficiency**: Code is structured for human understanding, not computational optimization
2. **Zero dependencies**: Only Python 3 standard library (reference impl) or minimal deps (live system)
3. **Reproducibility**: Every price calculation is verifiable from public blockchain data
4. **Single file clarity**: UTXOracle.py intentionally avoids function abstraction to keep logic flow visible

### Working with UTXOracle.py

- **Do NOT refactor into functions/classes** unless creating a separate implementation
- **Do NOT add external dependencies** to the reference implementation
- The verbose, repetitive style is intentional for educational purposes
- Code comments with hash tags explain algorithm to non-programmers

### Mempool Live System Development

**Current Status**: Task planning phase (see `docs/tasks/`)

**Tech Stack (KISS MVP)**:
- **Dependency management**: UV (not pip) - 10-100x faster, deterministic lockfiles
- **Backend**: FastAPI + PyZMQ (minimal dependencies)
- **Frontend MVP**: Vanilla JS + Canvas 2D (zero dependencies, no build step)
- **Frontend Production**: Three.js WebGL (only when >5k points cause Canvas lag)
- **Core algorithm**: Pure Python (reuse UTXOracle.py logic exactly)

**Agent Assignment**:
- `bitcoin-onchain-expert`: Task 01 (ZMQ interface)
- `general-purpose`: Tasks 02-05 (processing, analysis, streaming, visualization)

**Development Workflow**:
1. Read task file in `docs/tasks/XX_module_name.md`
2. Launch appropriate agent with task file as context
3. Agent implements module as black box with defined interface
4. Test module independently
5. Integrate with pipeline

**Rust Migration Path** (future):
- Core algorithm (histogram, stencil, convergence) can be rewritten in Rust or Cython
- Replaces Python modules without touching ZMQ/WebSocket/frontend
- Black box interface ensures seamless swap

## Bitcoin Node Connection

UTXOracle connects to Bitcoin Core using:

1. **Cookie authentication** (default): Reads `.cookie` file from Bitcoin data directory
2. **bitcoin.conf settings**: If RPC credentials are configured

Default Bitcoin data paths:
- **Linux**: `~/.bitcoin`
- **macOS**: `~/Library/Application Support/Bitcoin`
- **Windows**: `%APPDATA%\Bitcoin`

Required bitcoin.conf settings for future ZMQ features:
```conf
zmqpubhashtx=tcp://127.0.0.1:28332
zmqpubrawblock=tcp://127.0.0.1:28333
zmqpubrawtx=tcp://127.0.0.1:28332
rpcuser=<user>
rpcpassword=<password>
rpcallowip=127.0.0.1
```

## Historical Data

The repository includes 672 days of historical analysis (Dec 15, 2023 → Oct 17, 2025) as HTML files in `historical_data/html_files/`. Each file contains:

- Daily BTC/USD price calculation
- Statistical confidence score
- Transaction histogram analysis
- Intraday price evolution
- Interactive visualizations
- Blockchain metadata

Processing stats: 99.85% success rate, ~2.25 seconds per date with 12 parallel workers.

## Output

UTXOracle generates:
- **Console output**: Date and calculated price (e.g., "2025-10-15 price: $111,652")
- **HTML file**: Interactive visualization saved as `UTXOracle_YYYY-MM-DD.html`
- **Auto-opens browser**: Unless `--no-browser` flag is used

## Testing & Verification

All results are reproducible:
```bash
# Verify specific historical date
python3 UTXOracle.py -d 2025/10/15

# Should output: $111,652
```

Compare against historical_data files to verify algorithm consistency.

## License

Blue Oak Model License 1.0.0 - permissive open-source license designed for simplicity and developer freedom.
