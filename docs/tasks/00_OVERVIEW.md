# UTXOracle Live - Task Overview

**Project Goal**: Add real-time mempool analysis to UTXOracle with KISS MVP approach

**Timeline**: 10-14 weeks (MVP in 3-4 weeks)

**Tech Stack**:
- **Backend**: Python 3.11+, FastAPI, PyZMQ, UV package manager
- **Frontend**: Vanilla JS + Canvas 2D (MVP) → Three.js (production)
- **Storage**: In-memory (MVP) → Optional Redis/TimescaleDB
- **Deployment**: Single Python process (MVP) → Docker (production)

---

## Architecture Principles (Eskil Steenberg / Vibe Coding)

1. **Constant developer velocity** - Fast iteration regardless of project size
2. **One module, one person** - Each module is independently owned/developed
3. **Everything replaceable** - Black box interfaces allow module swapping
4. **Clean APIs** - Modules communicate only through defined data structures
5. **Write 5 lines today** - Avoid future context switching with upfront clarity

**Rust Migration Path**: Core algorithm (histogram, stencil, convergence) can be rewritten in Rust/Cython later without touching other modules.

---

## Module Breakdown

### Phase 0: Core Refactor (Optional)
**File**: `00_core_refactor.md`
**Owner**: General-purpose agent
**Duration**: 2 weeks
**Goal**: Extract Steps 5-11 from UTXOracle.py into `core/` modules

---

### Phase 1: Bitcoin Interface
**File**: `01_bitcoin_interface.md`
**Owner**: Bitcoin-onchain-expert agent
**Duration**: 1-2 weeks
**Goal**: ZMQ listener for mempool transactions

**Deliverable**:
```python
# live/backend/zmq_listener.py
async def stream_mempool_transactions():
    """Yields raw mempool tx as they arrive"""
    async for tx_bytes in zmq_subscribe():
        yield tx_bytes
```

---

### Phase 2: Transaction Processor
**File**: `02_transaction_processor.md`
**Owner**: General-purpose agent
**Duration**: 2-3 weeks
**Goal**: Parse raw tx, apply filters, extract outputs

**Deliverable**:
```python
# live/backend/tx_processor.py
def process_mempool_tx(raw_tx_bytes) -> Optional[ProcessedTx]:
    """Apply UTXOracle filters, return valid outputs or None"""
    pass
```

---

### Phase 3: Mempool Analyzer
**File**: `03_mempool_analyzer.md`
**Owner**: General-purpose agent
**Duration**: 3-4 weeks
**Goal**: Real-time histogram + price estimation

**Deliverable**:
```python
# live/backend/mempool_analyzer.py
class MempoolAnalyzer:
    def add_transaction(self, tx):
        """Update rolling histogram"""

    def estimate_price(self) -> float:
        """Return current mempool-based price"""
```

---

### Phase 4: Data Streamer
**File**: `04_data_streamer.md`
**Owner**: General-purpose agent
**Duration**: 2 weeks
**Goal**: FastAPI WebSocket server

**Deliverable**:
```python
# live/backend/api.py
@app.websocket("/ws/mempool")
async def websocket_endpoint(websocket: WebSocket):
    """Stream mempool data to frontend"""
```

---

### Phase 5: Visualization Renderer
**File**: `05_visualization_renderer.md`
**Owner**: General-purpose agent
**Duration**: 4-6 weeks (2 weeks MVP, 4 weeks WebGL)
**Goal**: Browser-based real-time chart

**Deliverable**:
```html
<!-- live/frontend/index.html -->
<canvas id="mempool-chart"></canvas>
<script src="mempool-viz.js"></script>
```

---

## Agent Assignment

| Task | Agent Type | Why |
|------|------------|-----|
| 00_core_refactor | general-purpose | Code refactoring, testing |
| 01_bitcoin_interface | bitcoin-onchain-expert | ZMQ expertise, mempool behavior |
| 02_transaction_processor | general-purpose | Binary parsing, filter logic |
| 03_mempool_analyzer | general-purpose | Algorithm implementation |
| 04_data_streamer | general-purpose | WebSocket/FastAPI |
| 05_visualization_renderer | general-purpose | Frontend dev |

---

## Success Criteria

**MVP (Week 4)**:
- ✅ ZMQ listener receiving mempool tx
- ✅ Basic filtering applied
- ✅ Real-time price estimate
- ✅ Canvas 2D scatter plot
- ✅ WebSocket streaming to browser

**Production (Week 14)**:
- ✅ Robust RBF/drop handling
- ✅ Three.js 60fps rendering
- ✅ Historical mempool playback
- ✅ Docker deployment
- ✅ 99% uptime over 7 days

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| ZMQ connection unstable | Reconnection logic + health checks |
| Mempool too noisy | Increase filter strictness |
| Canvas 2D performance lag | Early switch to WebGL |
| Tx drops cause price jumps | Exponential moving average |
| Bitcoin Core version incompatibility | Test on v25, v26, v27 |

---

## Next Steps

1. Review all task files (01-05)
2. Start with `01_bitcoin_interface.md`
3. Create branch: `git checkout -b feature/mempool-live`
4. Launch first agent with task 01
5. Daily standup: Check progress, adjust timeline

---

**Approved**: YES / NO
**Start Date**: ___________
**Target MVP**: ___________ (4 weeks from start)
**Target Production**: ___________ (14 weeks from start)
