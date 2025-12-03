# UTXOracle Live - Implementation Checklist

**Project Start Date**: __________
**Target MVP Date**: __________ (4 weeks from start)
**Target Production**: __________ (14 weeks from start)

---

## Pre-Implementation Setup

- [ ] Review all task files (`docs/tasks/00-05`)
- [ ] Install UV package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- [ ] Verify Bitcoin Core ZMQ is enabled in bitcoin.conf
- [ ] Create `feature/mempool-live` branch
- [ ] Initialize UV workspace (`uv init`)
- [ ] Set up folder structure as per CLAUDE.md

---

## Phase 1: Bitcoin Interface (Task 01)

**Agent**: `bitcoin-onchain-expert`
**Duration**: 1-2 weeks
**Task File**: `docs/tasks/01_bitcoin_interface.md`

### Deliverables
- [ ] `live/backend/zmq_listener.py` - ZMQ listener implementation
- [ ] `live/backend/config.py` - Configuration with env vars
- [ ] `live/backend/models.py` - RawTransaction dataclass
- [ ] `tests/test_zmq_listener.py` - Unit tests (>90% coverage)
- [ ] `tests/integration/test_zmq_real.py` - Integration with real Bitcoin node
- [ ] `docs/bitcoin_zmq_setup.md` - Setup guide

### Acceptance Criteria
- [ ] Connects to Bitcoin Core ZMQ on startup
- [ ] Yields raw transactions in real-time
- [ ] Auto-reconnects on connection failure (<5s)
- [ ] Unit tests pass
- [ ] Integration test runs for 5 minutes without errors

### Agent Launch Command
```bash
# Launch agent with task file
# Pass docs/tasks/01_bitcoin_interface.md as context
# Agent implements module independently
```

---

## Phase 2: Transaction Processor (Task 02)

**Agent**: `general-purpose`
**Duration**: 2-3 weeks
**Task File**: `docs/tasks/02_transaction_processor.md`

### Deliverables
- [ ] `live/backend/tx_processor.py` - Main processor
- [ ] `live/backend/bitcoin_parser.py` - Binary parsing (from UTXOracle.py)
- [ ] `live/backend/mempool_state.py` - State tracker
- [ ] `tests/test_tx_processor.py` - Unit tests (>90% coverage)
- [ ] `tests/benchmark_tx_processor.py` - Performance tests
- [ ] `tests/fixtures/sample_txs.json` - Test fixtures

### Acceptance Criteria
- [ ] Parses legacy + SegWit transactions correctly
- [ ] Applies all UTXOracle filters accurately
- [ ] Handles RBF replacements
- [ ] Processes >1000 tx/sec (benchmark)
- [ ] Unit tests >90% coverage

---

## Phase 3: Mempool Analyzer (Task 03)

**Agent**: `general-purpose`
**Duration**: 3-4 weeks
**Task File**: `docs/tasks/03_mempool_analyzer.md`

### Deliverables
- [ ] `live/backend/mempool_analyzer.py` - Main analyzer
- [ ] `live/backend/histogram.py` - Histogram management
- [ ] `live/backend/stencil.py` - Stencil matcher
- [ ] `live/backend/convergence.py` - Price convergence
- [ ] `tests/test_mempool_analyzer.py` - Unit tests (>85% coverage)
- [ ] Historical validation report (mempool vs confirmed prices)

### Acceptance Criteria
- [ ] Rolling histogram updates in real-time
- [ ] Price estimate within ±2% of confirmed blocks (historical validation)
- [ ] Processes 1000 tx additions/removals per second
- [ ] Memory <200MB for 50k active tx
- [ ] Confidence score functional

---

## Phase 4: Data Streamer (Task 04)

**Agent**: `general-purpose`
**Duration**: 2 weeks
**Task File**: `docs/tasks/04_data_streamer.md`

### Deliverables
- [ ] `live/backend/api.py` - FastAPI app + WebSocket
- [ ] `live/backend/orchestrator.py` - Pipeline coordinator
- [ ] `tests/test_api.py` - Unit tests
- [ ] `tests/load_test_websocket.py` - Load tests (100 clients)
- [ ] Deployment documentation

### Acceptance Criteria
- [ ] WebSocket streams data at 500ms intervals
- [ ] Handles 100 concurrent clients without lag
- [ ] Health check endpoint (`/health`) functional
- [ ] Graceful client disconnection
- [ ] Load tests pass

---

## Phase 5: Visualization Renderer (Task 05)

**Agent**: `general-purpose`
**Duration**: MVP 2 weeks | Production 4-6 weeks
**Task File**: `docs/tasks/05_visualization_renderer.md`

### MVP Deliverables (Canvas 2D)
- [ ] `live/frontend/index.html` - Main page
- [ ] `live/frontend/mempool-viz.js` - Canvas 2D renderer
- [ ] `live/frontend/styles.css` - Styling
- [ ] Browser compatibility tests (Chrome, Firefox, Safari)

### Production Deliverables (Three.js WebGL)
- [ ] `live/frontend/mempool-viz-webgl.js` - Three.js renderer
- [ ] Performance benchmark (10k-100k points @ 60fps)
- [ ] Fallback logic (WebGL unavailable → Canvas)

### MVP Acceptance Criteria
- [ ] Real-time scatter plot updates
- [ ] 30fps with <2000 points
- [ ] Tooltip shows price/time on hover
- [ ] Zero build dependencies

### Production Acceptance Criteria
- [ ] 60fps with 50k points
- [ ] Point fade-out over time
- [ ] GPU acceleration verified

---

## Integration & Testing

- [ ] End-to-end integration test (ZMQ → Visualization)
- [ ] 24-hour stress test (continuous operation)
- [ ] Memory leak detection (valgrind/heaptrack)
- [ ] Performance profiling (py-spy)
- [ ] Cross-browser testing (Chrome, Firefox, Safari, Edge)

---

## Documentation

- [ ] API documentation (`docs/api.md`)
- [ ] Deployment guide (`docs/deployment.md`)
- [ ] User guide for running live system
- [ ] Troubleshooting FAQ
- [ ] Update README.md with live system instructions

---

## Deployment

### Development
- [ ] `uv run uvicorn live.backend.api:app --reload`
- [ ] Verify WebSocket connection
- [ ] Test with local Bitcoin node

### Production
- [ ] Docker image creation
- [ ] Environment variables documented
- [ ] Reverse proxy setup (Nginx/Caddy)
- [ ] SSL/TLS for WebSocket (wss://)
- [ ] Monitoring (Prometheus/Grafana)
- [ ] Log aggregation (Loki/ELK)

---

## Optional: Rust/Cython Migration (Advanced)

**See**: `TECHNICAL_SPEC_ADVANCED.md`

- [ ] Benchmark Python baseline performance
- [ ] Rewrite `histogram.py` in Rust/Cython
- [ ] Rewrite `stencil.py` in Rust/Cython
- [ ] Rewrite `convergence.py` in Rust/Cython
- [ ] Create Python bindings (PyO3/maturin)
- [ ] Verify 10x+ speedup
- [ ] Integration test (Rust modules + Python pipeline)

---

## Success Metrics

| Metric | Target | Status |
|--------|--------|--------|
| MVP Completion | 4 weeks | [ ] |
| Production Completion | 14 weeks | [ ] |
| Price Accuracy | ±2% vs confirmed | [ ] |
| Throughput | >1k tx/sec | [ ] |
| WebSocket Latency | <100ms | [ ] |
| Uptime (7 days) | >99% | [ ] |
| Memory Usage | <300MB | [ ] |
| Frontend FPS | >30fps (MVP) / >60fps (prod) | [ ] |

---

## Risk Register

| Risk | Probability | Impact | Mitigation | Status |
|------|-------------|--------|------------|--------|
| Bitcoin Core ZMQ instability | Medium | High | Reconnection logic, health checks | [ ] |
| Mempool too noisy | High | Medium | Stricter filters, confidence threshold | [ ] |
| Canvas 2D lag | Medium | Low | Early Three.js switch | [ ] |
| Tx drop price jumps | Medium | Medium | Exponential moving average | [ ] |
| Agent code quality | Low | High | Code review, test coverage | [ ] |

---

## Notes

- Each task is independent (black box principle)
- Agents implement modules without dependencies on others
- Test each module before integration
- Use UV lockfile (`uv.lock`) for reproducible builds
- Commit after each phase completion

---

**Last Updated**: __________
**Status**: __________ (Planning / In Progress / Completed)
