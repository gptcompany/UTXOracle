# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**📘 For Skill Implementation**: See `.claude/SKILLS_FRAMEWORK_BLUEPRINT.md`

## Project Overview

UTXOracle is a Bitcoin-native, exchange-free price oracle that calculates the market price of Bitcoin directly from blockchain data. It analyzes on-chain transactions using statistical clustering to derive BTC/USD prices without relying on external exchange APIs.

**Key Principles**:
- Pure Python implementation (no external dependencies beyond standard library)
- Single-file reference implementation for clarity and transparency
- Direct Bitcoin Core RPC connection only
- Privacy-first: no external price feeds

**🎯 Development Philosophy**: KISS (Keep It Simple) + YAGNI (You Ain't Gonna Need It)

## Running UTXOracle

```bash
# Run for yesterday's price (default)
python3 UTXOracle.py

# Run for specific date
python3 UTXOracle.py -d 2025/10/15

# Use recent 144 blocks
python3 UTXOracle.py -rb

# Batch processing (12 parallel workers)
python3 scripts/utxoracle_batch.py 2025/10/01 2025/10/10 /home/sam/.bitcoin 12
```

**Requirements**: Python 3.8+, Bitcoin Core node (fully synced, RPC enabled)

## Architecture

> **📖 Full documentation**: See `docs/ARCHITECTURE.md` for complete spec details (spec-007 to spec-013).

**4-Layer Architecture**:

| Layer | Component | Purpose |
|-------|-----------|---------|
| 1 | `UTXOracle.py` | Reference implementation (IMMUTABLE) |
| 2 | `UTXOracle_library.py` | Reusable algorithm library |
| 3 | mempool.space + electrs | Self-hosted infrastructure (Docker) |
| 4 | `api/main.py` + `frontend/` | FastAPI + Plotly.js dashboard |

**Service Endpoints**:

| Service | URL | Purpose |
|---------|-----|---------|
| Bitcoin Core RPC | `http://localhost:8332` | Blockchain data |
| electrs HTTP API | `http://localhost:3001` | Transaction data (primary) |
| mempool backend | `http://localhost:8999` | Exchange prices |
| mempool frontend | `http://localhost:8080` | Block explorer UI |

**Spec Status**:

| Spec | Module | Status |
|------|--------|--------|
| spec-007 | metrics/ | ✅ Complete |
| spec-008 | derivatives/ | ✅ Complete |
| spec-009 | metrics/ (advanced) | ✅ Complete |
| spec-010 | metrics/wasserstein | ✅ Complete |
| spec-011 | alerts/ | ✅ Complete |
| spec-012 | backtest/ | ✅ Complete |
| spec-013 | clustering/ | ✅ Complete |
| spec-014 | metrics/ (evidence weights) | ✅ Complete |
| spec-015 | backtest/ (validation) | ✅ Complete |
| spec-016 | metrics/sopr | ✅ Complete |
| spec-017 | metrics/utxo_lifecycle | ✅ Complete |
| spec-018 | metrics/cointime | ✅ Complete |

## Repository Organization

```
UTXOracle/
├── UTXOracle.py              # Reference implementation (IMMUTABLE)
├── UTXOracle_library.py      # Reusable library
├── CLAUDE.md                 # THIS FILE
├── api/main.py               # FastAPI backend
├── frontend/                 # Plotly.js dashboard
├── scripts/
│   ├── daily_analysis.py     # Integration service (cron)
│   ├── metrics/              # On-chain metrics (spec-007, 009, 010)
│   ├── derivatives/          # Derivatives data (spec-008)
│   ├── alerts/               # Alert system (spec-011)
│   ├── backtest/             # Backtesting (spec-012)
│   └── clustering/           # Address clustering (spec-013)
├── tests/                    # pytest test suite
├── specs/                    # Feature specifications (SpecKit)
├── docs/
│   ├── ARCHITECTURE.md       # ⚠️ UPDATE THIS for architecture changes
│   ├── DEVELOPMENT_WORKFLOW.md  # TDD, cleanup checklists
│   └── tasks/                # Agent task specs
├── .claude/                  # Claude Code config (agents, skills, hooks)
├── .serena/                  # Serena MCP (code navigation)
├── .specify/                 # SpecKit (task management)
├── archive/                  # Previous versions (v7-v9, spec-002)
└── historical_data/          # 672 days of HTML outputs
```

**File Placement**:
- Backend modules → `api/`
- Frontend code → `frontend/`
- Integration scripts → `scripts/`
- Tests → `tests/test_<module>.py`
- Agent specs → `.claude/agents/`

**Immutable Files** (do not refactor):
- `UTXOracle.py` - Reference implementation
- `historical_data/html_files/` - Historical outputs

## Agent & Skill Architecture

### Subagents (8)

| Agent | Responsibility |
|-------|----------------|
| bitcoin-onchain-expert | ZMQ, Bitcoin Core integration |
| transaction-processor | Binary parsing, UTXOracle filtering |
| mempool-analyzer | Histogram, stencil, price estimation |
| data-streamer | FastAPI WebSocket server |
| visualization-renderer | Canvas 2D + Three.js WebGL |
| tdd-guard | TDD enforcement, coverage validation |
| alpha-debug | Iterative bug hunting (auto-triggered) |
| alpha-evolve | Multi-implementation generator |

### Skills (4)

| Skill | Purpose | Token Savings |
|-------|---------|---------------|
| pytest-test-generator | Test boilerplate | 83% |
| github-workflow | PR/Issue/Commit templates | 79% |
| pydantic-model-generator | Data models | 75% |
| bitcoin-rpc-connector | RPC client setup | 60% |

### Alpha-Debug (Auto-Triggered)

Finds bugs even when tests pass. Triggers automatically after implementation phases.

**Dynamic Rounds** (complexity-based): 2-10 rounds based on lines changed and files modified.

**Stop Conditions**:
1. MAX_ROUNDS reached
2. 2 consecutive clean rounds
3. Confidence >= 95%
4. Tests failing → human intervention

## Development Principles

### KISS & YAGNI

- **Choose boring technology**: Python, not Rust (until needed)
- **One module, one purpose**: Each file does ONE thing well
- **Delete dead code**: If unused for 2 weeks, remove it
- **No generic solutions**: Specific beats flexible

### Code Reuse First

- **NEVER write custom code if >80% can be reused**
- **Self-host over custom build**: Use mempool.space instead of custom ZMQ parser

### Important Reminders

#### ❌ NEVER
- Use `--no-verify` to bypass commit hooks
- Disable tests instead of fixing them
- Commit without testing locally first
- Hardcode secrets/API keys (use `.env`)

#### ✅ ALWAYS
- Run tests before committing (`uv run pytest`)
- Format code (`ruff check . && ruff format .`)
- Use `uv` for dependencies (not `pip`)

## Development Workflow

> **📖 Full documentation**: See `docs/DEVELOPMENT_WORKFLOW.md` for TDD flow, cleanup checklists, and decision frameworks.

**Quick Reference**:

```bash
# TDD cycle
uv run pytest tests/test_module.py::test_new -v  # RED (must fail)
# implement minimal code
uv run pytest tests/test_module.py::test_new -v  # GREEN (must pass)
# refactor if needed
```

**When Stuck**: Maximum 3 attempts per issue, then document and ask for help.

**Before Every Commit**:
1. Run tests: `uv run pytest`
2. Lint/format: `ruff check . && ruff format .`
3. Check for debug code: No `print()` statements
4. Update docs if architecture changed: `docs/ARCHITECTURE.md`

## Documentation Update Rules

**⚠️ CRITICAL**: When implementing new specs or changing architecture:

1. **Update `docs/ARCHITECTURE.md`** (NOT CLAUDE.md) with:
   - New module documentation
   - API endpoints
   - Data models
   - Configuration details

2. **Keep CLAUDE.md small** (~400 lines max):
   - Only essential instructions
   - References to detailed docs
   - Quick reference tables

3. **Update `docs/DEVELOPMENT_WORKFLOW.md`** for:
   - New workflow patterns
   - Additional checklists
   - Process changes

## Bitcoin Node Connection

UTXOracle connects to Bitcoin Core using:
1. **Cookie authentication** (default): Reads `.cookie` file from Bitcoin data directory
2. **bitcoin.conf settings**: If RPC credentials are configured

Default paths: `~/.bitcoin` (Linux), `~/Library/Application Support/Bitcoin` (macOS)

## Historical Data

672 days of historical analysis (Dec 15, 2023 → Oct 17, 2025) in `historical_data/html_files/`.
Processing stats: 99.85% success rate, ~2.25 seconds per date with 12 parallel workers.

## Output

- **Console**: Date and calculated price (e.g., "2025-10-15 price: $111,652")
- **HTML file**: Interactive visualization saved as `UTXOracle_YYYY-MM-DD.html`
- **Auto-opens browser**: Unless `--no-browser` flag is used

## Testing & Verification

```bash
# Verify specific historical date
python3 UTXOracle.py -d 2025/10/15
# Should output: $111,652
```

## License

Blue Oak Model License 1.0.0
