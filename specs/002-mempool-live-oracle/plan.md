# Implementation Plan: UTXOracle Live - Real-time Mempool Price Oracle

**Branch**: `002-mempool-live-oracle` | **Date**: 2025-10-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/media/sam/1TB/UTXOracle/specs/002-mempool-live-oracle/spec.md`

## Summary

Create a real-time Bitcoin price oracle that analyzes mempool transactions to provide live BTC/USD estimates updated every 0.5-5 seconds. The system streams mempool data from Bitcoin Core via ZMQ, applies UTXOracle's proven statistical clustering algorithm (Steps 5-11 from reference implementation), and visualizes the results in a browser using Canvas 2D. Architecture follows black box modular design with 5 independent modules: Bitcoin Interface (ZMQ listener), Transaction Processor (binary parsing), Mempool Analyzer (price estimation), Data Streamer (WebSocket API), and Visualization Renderer (browser display). Technical approach emphasizes KISS/YAGNI principles with minimal dependencies (Python + FastAPI + PyZMQ for backend, vanilla JavaScript for frontend).

## Technical Context

**Language/Version**: Python 3.11+ (proven, no Rust for MVP)
**Primary Dependencies**: FastAPI ≥0.104.1 (WebSocket), uvicorn[standard] ≥0.24.0 (ASGI), PyZMQ ≥25.1.1 (Bitcoin ZMQ)
**Storage**: In-memory only (no database for MVP - 3-hour rolling window)
**Testing**: pytest ≥7.4.0, pytest-asyncio ≥0.21.0, pytest-watch ≥4.2.0 (TDD guard), pytest-cov ≥4.1.0 (coverage)
**Target Platform**: Linux server (development), browser clients (Chrome/Firefox/Safari latest 2 versions)
**Project Type**: Web application (FastAPI backend + vanilla JavaScript frontend)
**Performance Goals**: <100ms ZMQ latency, >1000 tx/sec processing, <500ms price updates, 30 FPS Canvas rendering, 100 concurrent WebSocket clients
**Constraints**: <500MB backend RAM, <50MB browser heap, ±2% price accuracy vs exchanges, 24+ hour uptime, 3 major browsers
**Scale/Scope**: Single-server MVP, 5 modules, 50k active mempool transactions, 300-500 visible visualization points

**Dependency Management**: UV (not pip) - 10-100x faster, deterministic lockfiles (uv.lock), zero-install deployments

**Frontend**: Vanilla JavaScript ES6+ with zero npm dependencies, Canvas 2D API (built into browsers), no build step required

**Infrastructure**: Minimal setup - Bitcoin Core ≥25.0 with ZMQ enabled, no Redis/PostgreSQL/Docker for MVP

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Code Quality & Simplicity - ✅ PASS

- **KISS Principle**: ✅ Python over Rust for MVP, vanilla JS over frameworks, 3 backend dependencies only
- **Boring Technology**: ✅ FastAPI, PyZMQ, Canvas 2D - all proven, stable
- **YAGNI**: ✅ No database, no authentication, no mobile app for MVP - focus on core value
- **Minimal Dependencies**: ✅ 3 runtime + 5 dev dependencies (vs. 50+ in typical web project)
- **Single Purpose Modules**: ✅ 5 black box modules, each with single responsibility
- **Readability**: ✅ Reuses UTXOracle.py transparent algorithm, well-documented contracts
- **No Premature Abstraction**: ✅ Direct implementation first, abstractions only when needed

**Justification**: Architecture directly aligns with UTXOracle.py philosophy - transparency over optimization.

### II. Test-First Discipline (TDD) - ✅ PASS

- **TDD Cycle**: ✅ RED-GREEN-REFACTOR enforced via pytest-watch + tdd-guard agent
- **Coverage**: ✅ Target 80%+ for all production code, >90% for critical modules (price estimation)
- **Integration Tests**: ✅ Required for module contracts, ZMQ integration, WebSocket streaming
- **Tests Before Code**: ✅ pytest-test-generator skill for boilerplate, tests written first per spec
- **Test Organization**: ✅ Follows standard: tests/test_{module}/, tests/integration/, tests/fixtures/

**Tools**: pytest-watch (continuous), pytest-testmon (only affected tests), pytest-cov (coverage reports)

### III. User Experience Consistency - ✅ PASS

- **CLI Standards**: ✅ N/A for MVP (web-only), future CLI will follow UTXOracle.py patterns
- **Visualization Standards**: ✅ Matches UTXOracle.py HTML output (black bg, cyan/orange, Canvas 2D, tooltips)
- **API Standards**: ✅ WebSocket JSON with Pydantic validation, graceful disconnection, descriptive errors
- **Reproducibility**: ✅ All price estimates traceable to mempool transaction data

**Visual Consistency**:
- Follows `historical_data/html_files/UTXOracle_*.html` format
- References: `examples/Screenshot from 2025-10-18 09-26-*.png` (orange mempool panel)
- Canvas size: 1000x660px, black background, orange points for mempool, tooltips on hover

### IV. Performance Standards - ✅ PASS

**Batch Processing**: ✅ N/A for mempool live (applies to UTXOracle.py batch mode)

**Real-time Mempool**:
- ✅ ZMQ latency <100ms (meets baseline)
- ✅ Price updates ≤5 seconds (within spec)
- ✅ WebSocket latency <50ms (meets baseline)
- ✅ Frontend rendering: 30 FPS minimum (Canvas 2D MVP), 60 FPS production (WebGL upgrade)

**Resource Limits**:
- ✅ Memory <500MB backend (histogram optimized)
- ✅ No RPC for mempool live (ZMQ only), RPC connection pooling for future confirmed data panel
- ✅ No disk writes (in-memory only)

**Logging**: ✅ Structured JSON for production, human-readable for development (DEBUG/INFO/WARN/ERROR)

**Baseline Validation**: Historical tests compare mempool estimates vs confirmed block prices (±2% accuracy requirement)

### Development Workflow Compliance - ✅ PASS

- **Black Box Architecture**: ✅ 5 independent modules, single shared data model file (live/shared/models.py)
- **Agent System**: ✅ Tasks 01-05 mapped to specialized agents (bitcoin-onchain-expert, transaction-processor, mempool-analyzer, data-streamer, visualization-renderer)
- **Skills**: ✅ pytest-test-generator, pydantic-model-generator, bitcoin-rpc-connector used as appropriate
- **Pre-Commit Cleanup**: ✅ .github/CLEANUP_CHECKLIST.md enforced

### Overall Assessment: ✅ ALL GATES PASSED

**No constitutional violations.** All principles strictly followed. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```
specs/002-mempool-live-oracle/
├── spec.md              # Feature specification (WHAT & WHY) - COMPLETE
├── plan.md              # This file (HOW & TECH) - IN PROGRESS
├── research.md          # Phase 0 output - TO BE GENERATED
├── data-model.md        # Phase 1 output - TO BE GENERATED
├── quickstart.md        # Phase 1 output - TO BE GENERATED
├── contracts/           # Phase 1 output - TO BE GENERATED
│   ├── websocket-api.json    # WebSocket message schema (JSON Schema)
│   ├── data-models.json      # Shared data models (Pydantic → JSON Schema)
│   └── README.md             # Contract documentation
├── checklists/
│   └── requirements.md  # Spec quality validation - COMPLETE (✅ PASSED)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

**Structure Decision**: Web application pattern (backend + frontend)

```
UTXOracle/
├── pyproject.toml            # UV workspace root
├── uv.lock                   # Dependency lockfile (MUST COMMIT)
│
├── live/                     # Mempool live system
│   ├── pyproject.toml        # Live system package definition
│   │
│   ├── backend/              # Python backend modules
│   │   ├── __init__.py
│   │   ├── zmq_listener.py      # Module 1: Bitcoin ZMQ interface
│   │   ├── tx_processor.py      # Module 2: Binary transaction parser
│   │   ├── mempool_analyzer.py  # Module 3: Price estimation engine
│   │   ├── api.py               # Module 4: FastAPI WebSocket server
│   │   ├── orchestrator.py      # Pipeline coordinator (glues modules 1-4)
│   │   │
│   │   ├── histogram.py         # Module 3 internals (UTXOracle Steps 5-7)
│   │   ├── stencil.py           # Module 3 internals (UTXOracle Steps 8-9)
│   │   ├── convergence.py       # Module 3 internals (UTXOracle Step 11)
│   │   ├── bitcoin_parser.py    # Module 2 internals (binary parsing)
│   │   │
│   │   ├── config.py            # Configuration management
│   │   └── models.py            # Backend-specific models
│   │
│   ├── frontend/             # Vanilla JavaScript frontend
│   │   ├── index.html           # Main page (served by FastAPI)
│   │   ├── mempool-viz.js       # Module 5: Canvas 2D renderer (MVP)
│   │   ├── mempool-viz-webgl.js # Module 5: Three.js WebGL (production upgrade)
│   │   └── styles.css           # Styling (black bg, orange theme)
│   │
│   └── shared/               # ONLY shared code between modules
│       ├── __init__.py
│       └── models.py         # RawTransaction, ProcessedTransaction, MempoolState
│
├── tests/                    # Test suite (pytest)
│   ├── __init__.py
│   ├── conftest.py           # Shared pytest fixtures
│   │
│   ├── test_zmq_listener.py        # Module 1 unit tests
│   ├── test_tx_processor.py        # Module 2 unit tests
│   ├── test_mempool_analyzer.py    # Module 3 unit tests
│   ├── test_api.py                 # Module 4 unit tests
│   │
│   ├── integration/          # Cross-module tests
│   │   ├── __init__.py
│   │   ├── test_zmq_live.py        # ZMQ + Bitcoin Core integration (5 min)
│   │   ├── test_pipeline.py        # Modules 1-4 end-to-end
│   │   └── test_websocket.py       # WebSocket client simulation
│   │
│   ├── benchmark/            # Performance tests
│   │   ├── __init__.py
│   │   ├── benchmark_tx_processor.py  # Must achieve >1k tx/sec
│   │   └── load_test_websocket.py     # 100 concurrent clients
│   │
│   └── fixtures/             # Test data
│       ├── __init__.py
│       ├── sample_tx.bin           # Raw transaction bytes
│       ├── sample_mempool.json     # Mock mempool state
│       └── historical_prices.csv   # Validation dataset
│
├── docs/                     # Documentation (existing)
│   ├── tasks/
│   │   ├── 00_OVERVIEW.md          # Project overview
│   │   ├── 01_bitcoin_interface.md # Task for bitcoin-onchain-expert
│   │   ├── 02_transaction_processor.md
│   │   ├── 03_mempool_analyzer.md
│   │   ├── 04_data_streamer.md
│   │   └── 05_visualization_renderer.md
│   └── IMPLEMENTATION_CHECKLIST.md
│
├── examples/                 # Visual reference (existing)
│   ├── UTXOracle_Local_Node_Price.png       # LEFT panel (confirmed, cyan)
│   ├── Screenshot from 2025-10-18 09-26-57.png  # RIGHT panel t=0s (mempool, orange)
│   ├── Screenshot from 2025-10-18 09-27-03.png  # RIGHT panel t=6s
│   ├── Screenshot from 2025-10-18 09-27-11.png  # RIGHT panel t=14s
│   └── README.md                            # Dual-panel comparison table
│
└── historical_data/
    └── html_files/
        └── UTXOracle_2025-10-16.html  # Canvas rendering reference
```

**Rationale**:
- Clean separation of backend (Python) and frontend (JavaScript)
- `live/` namespace avoids conflicts with reference `UTXOracle.py`
- `shared/models.py` is ONLY file shared between modules (black box principle)
- Tests mirror source structure for easy navigation
- Follows UV workspace conventions (pyproject.toml at multiple levels)

## Complexity Tracking

*No violations - this section is not applicable.*

## Phase 0: Research & Technology Validation

### Research Tasks

The technical plan provided comprehensive implementation details. All technology choices are proven and well-documented:

1. **UV Dependency Management** - Already validated (10-100x faster than pip, deterministic lockfiles)
2. **FastAPI WebSocket Streaming** - Standard async framework, well-documented
3. **PyZMQ Bitcoin Integration** - Existing examples in Bitcoin ecosystem
4. **Canvas 2D Performance** - Browser standard, 30 FPS achievable with <2k points
5. **UTXOracle Algorithm Adaptation** - Reference implementation exists (UTXOracle.py)

### Research Output

**Decision**: Use technologies exactly as specified in SPECKIT_TECH_PLAN.md

**Rationale**:
- All dependencies are mature, stable, widely-used
- Python 3.11+ provides async/await for ZMQ + WebSocket
- UV solves pip performance/determinism issues
- FastAPI is de-facto standard for Python async APIs
- Canvas 2D is universal browser standard (zero compatibility issues)
- UTXOracle.py proves algorithm works in Python

**Alternatives Considered**:
- ❌ Rust backend: Premature optimization (YAGNI violation)
- ❌ React/Vue frontend: Build complexity + dependencies (KISS violation)
- ❌ HTTP polling: Higher latency than WebSocket
- ❌ Server-Sent Events: Less flexible than WebSocket bidirectional
- ❌ PostgreSQL: Overkill for 3-hour rolling window (in-memory sufficient)

**No further research needed.** Proceed to Phase 1.

## Phase 1: Data Models & API Contracts

### Data Model Design

**File**: `live/shared/models.py` (ONLY shared file)

**Entities** (from feature spec):

1. **RawTransaction** - Bitcoin ZMQ output
   - Fields: raw_bytes (bytes), timestamp (float), topic (Literal['rawtx'])
   - Source: Module 1 (ZMQ listener)
   - Consumer: Module 2 (transaction processor)

2. **ProcessedTransaction** - Filtered transaction with extracted data
   - Fields: txid (str), amounts (List[float]), timestamp (float), fee_rate (Optional[float]), input_count (int), output_count (int)
   - Source: Module 2 (transaction processor)
   - Consumer: Module 3 (mempool analyzer)

3. **MempoolState** - Current analysis state
   - Fields: price (float), confidence (float), active_tx_count (int), total_received (int), total_filtered (int), uptime_seconds (float)
   - Source: Module 3 (mempool analyzer)
   - Consumer: Module 4 (data streamer)

4. **WebSocketMessage** - Client-facing stream
   - Fields: price (float), confidence (float), transactions (List[dict]), stats (dict), timestamp (float)
   - Source: Module 4 (data streamer)
   - Consumer: Module 5 (visualization renderer)

**Validation Rules** (from feature spec):
- Price: Must be positive float
- Confidence: Must be in [0.0, 1.0] range
- Timestamps: Unix epoch seconds (float)
- Transaction amounts: Filtered to [1e-5, 1e5] BTC range
- Transaction filters: ≤5 inputs, exactly 2 outputs (UTXOracle algorithm)

### API Contract Design

**WebSocket Endpoint**: `ws://localhost:8000/ws/mempool`

**Message Flow**: Server → Client (one-way stream for MVP)

**Message Format** (JSON):
```json
{
  "type": "mempool_update",
  "data": {
    "price": 113600.50,
    "confidence": 0.87,
    "transactions": [
      {
        "timestamp": 1678901234.1,
        "price": 113500.0
      },
      {
        "timestamp": 1678901234.2,
        "price": 113700.0
      }
    ],
    "stats": {
      "total_received": 12543,
      "total_filtered": 8234,
      "active_in_window": 4309,
      "uptime_seconds": 3600.5
    },
    "timestamp": 1678901234.567
  }
}
```

**Connection Lifecycle**:
1. Client connects: `ws://localhost:8000/ws/mempool`
2. Server accepts connection
3. Server broadcasts updates every 500ms
4. Client disconnects gracefully or server detects timeout
5. Server cleans up connection

**Error Handling**:
- Connection errors: Client retries with exponential backoff
- Parse errors: Server logs, client receives error message
- Timeout: Server closes connection after 60s inactivity

### Module Contracts (Black Box Interfaces)

**Module 1 → Module 2**:
```python
# zmq_listener.py → tx_processor.py
async def stream_mempool_transactions() -> AsyncGenerator[RawTransaction, None]:
    """Yields raw mempool transactions from Bitcoin Core ZMQ"""
    pass
```

**Module 2 → Module 3**:
```python
# tx_processor.py → mempool_analyzer.py
def process_mempool_transaction(raw_tx: RawTransaction) -> Optional[ProcessedTransaction]:
    """Parses and filters transaction. Returns None if filtered out."""
    pass
```

**Module 3 → Module 4**:
```python
# mempool_analyzer.py → api.py
class MempoolAnalyzer:
    def add_transaction(self, tx: ProcessedTransaction) -> None:
        """Update rolling histogram"""
        pass

    def estimate_price(self) -> Tuple[float, float]:
        """Returns (price, confidence_score)"""
        pass

    def get_stats(self) -> dict:
        """Returns operational statistics"""
        pass
```

**Module 4 → Module 5**:
```javascript
// WebSocket → mempool-viz.js
class MempoolVisualizer {
    constructor(canvasId, websocketUrl) {}

    connect() {
        // Establish WebSocket connection
    }

    updateData(message) {
        // Process incoming WebSocket message
        // Update internal state
    }

    render() {
        // Draw to Canvas 2D at 30fps
    }
}
```

### Quickstart Guide

**Prerequisites**:
1. Bitcoin Core ≥25.0 running with ZMQ enabled
2. Python 3.11+ installed
3. UV package manager installed

**bitcoin.conf Configuration**:
```conf
zmqpubhashtx=tcp://127.0.0.1:28332
zmqpubrawblock=tcp://127.0.0.1:28333
zmqpubrawtx=tcp://127.0.0.1:28332
rpcallowip=127.0.0.1
```

**Installation**:
```bash
# Clone repository
git clone https://github.com/username/UTXOracle.git
cd UTXOracle

# Checkout feature branch
git checkout 002-mempool-live-oracle

# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Initialize UV workspace and install dependencies
uv sync

# Verify installation
uv run python -c "import fastapi, zmq; print('Dependencies OK')"
```

**Run Development Server**:
```bash
# Terminal 1: Start backend
uv run uvicorn live.backend.api:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Open browser
open http://localhost:8000

# Terminal 3 (optional): Watch tests
uv run ptw -- --testmon --cov=live/backend
```

**Verify System**:
1. Open http://localhost:8000 in browser
2. Check DevTools console for WebSocket connection
3. Verify price updates every 0.5-5 seconds
4. Hover over scatter plot points for tooltips
5. Check confidence score indicator

**Troubleshooting**:
- **"ZMQ connection failed"**: Check Bitcoin Core is running and ZMQ enabled in bitcoin.conf
- **"No transactions"**: Bitcoin mempool might be empty (low network activity)
- **"Low confidence"**: Normal when starting up (<100 transactions processed)
- **Canvas not rendering**: Check browser console for JavaScript errors

## Phase 2: Task Breakdown (Future)

**Note**: Task breakdown is generated by `/speckit.tasks` command (NOT part of `/speckit.plan`).

Tasks will be organized as:
- **Task 01**: Bitcoin Interface (zmq_listener.py) - Agent: bitcoin-onchain-expert
- **Task 02**: Transaction Processor (tx_processor.py) - Agent: transaction-processor
- **Task 03**: Mempool Analyzer (mempool_analyzer.py) - Agent: mempool-analyzer
- **Task 04**: Data Streamer (api.py, orchestrator.py) - Agent: data-streamer
- **Task 05**: Visualization Renderer (mempool-viz.js) - Agent: visualization-renderer

Each task will include:
- Detailed implementation steps
- Test requirements (RED-GREEN-REFACTOR)
- Acceptance criteria
- Dependencies on other tasks
- Estimated effort (story points)

**Dependency graph**:
```
Task 01 (ZMQ) ──┐
                ├──> Task 03 (Analyzer) ──> Task 04 (API) ──> Task 05 (Viz)
Task 02 (Parse) ┘
```

Task 01 and Task 02 can be developed in parallel. Task 03 depends on both. Task 04 depends on Task 03. Task 05 depends on Task 04.

## Agent Context Update

Agent-specific context files will be updated to include:
- UV workspace structure
- FastAPI WebSocket patterns
- PyZMQ Bitcoin integration examples
- Canvas 2D rendering snippets
- Pydantic model definitions
- pytest-asyncio test patterns

**Update script**: `.specify/scripts/bash/update-agent-context.sh claude`

This will detect Claude Code agent and update `.claude/prompts/utxoracle-system.md` with technology-specific guidance between preservation markers.

## Constitution Re-Check (Post-Design)

### I. Code Quality & Simplicity - ✅ STILL PASSING

- **KISS**: Architecture remains simple (5 modules, clear data flow)
- **YAGNI**: No scope creep in design phase
- **Minimal Dependencies**: Still 3 runtime + 5 dev (unchanged)
- **Single Purpose**: Each module contract confirms single responsibility

### II. Test-First Discipline - ✅ STILL PASSING

- **TDD Workflow**: Tests defined before implementation in task breakdown
- **Coverage**: Unit + integration + benchmark tests planned
- **Test Organization**: Structure follows standards

### III. User Experience Consistency - ✅ STILL PASSING

- **Visual Consistency**: Design references UTXOracle.py HTML output
- **API Standards**: WebSocket JSON with Pydantic validation
- **Reproducibility**: All data traceable to mempool transactions

### IV. Performance Standards - ✅ STILL PASSING

- **Performance Targets**: All metrics defined and achievable
- **Resource Limits**: Memory/CPU targets within constitution baselines
- **Logging**: Structured logging planned

**Final Assessment**: ✅ **NO VIOLATIONS INTRODUCED DURING DESIGN**

## Implementation Roadmap

### Phase 0: Setup (Week 0) - ✅ COMPLETE
- [x] UV installation and workspace initialization
- [x] Bitcoin Core ZMQ configuration
- [x] Feature branch created (002-mempool-live-oracle)
- [x] Specification written and validated

### Phase 1: Design (Week 1) - ✅ IN PROGRESS
- [x] Data models designed
- [x] API contracts defined
- [x] Module interfaces specified
- [ ] research.md generated (this plan serves as research output)
- [ ] data-model.md generated
- [ ] contracts/ directory created with JSON schemas
- [ ] quickstart.md generated
- [ ] Agent context updated

### Phase 2: Task Breakdown (Week 2)
- [ ] Run `/speckit.tasks` command
- [ ] Generate tasks.md with dependency-ordered implementation steps
- [ ] Review and approve task breakdown

### Phase 3-7: Implementation (Weeks 3-14)
- [ ] Task 01: Bitcoin Interface (Weeks 3-4)
- [ ] Task 02: Transaction Processor (Weeks 5-7)
- [ ] Task 03: Mempool Analyzer (Weeks 8-10)
- [ ] Task 04: Data Streamer (Weeks 11-12)
- [ ] Task 05: Visualization Renderer (Weeks 13-14)

### Phase 8: Integration & Testing (Weeks 15-16)
- [ ] End-to-end integration tests
- [ ] Performance benchmarking
- [ ] Browser compatibility testing
- [ ] Historical validation (mempool vs confirmed blocks)

### Phase 9: Documentation & Deployment (Week 17)
- [ ] User documentation
- [ ] Deployment guide
- [ ] Production configuration
- [ ] MVP launch

### Phase 10: Production Enhancements (Weeks 18+, Optional)
- [ ] WebGL upgrade for 50k+ points
- [ ] 100 concurrent client load testing
- [ ] Historical mempool replay
- [ ] Monitoring/logging infrastructure

## Next Steps

1. **Complete Phase 1 artifacts**:
   - Generate `research.md` (formalize technology validation)
   - Generate `data-model.md` (Pydantic class definitions)
   - Generate `contracts/` directory with JSON Schema files
   - Generate `quickstart.md` (detailed setup guide)
   - Run agent context update script

2. **Execute `/speckit.tasks`** to generate dependency-ordered task breakdown

3. **Begin TDD implementation** starting with Task 01 (Bitcoin Interface)

---

*Implementation Plan v1.0 - UTXOracle Live*
*Created*: 2025-10-19
*Status*: Phase 1 Design Complete - Ready for artifact generation
