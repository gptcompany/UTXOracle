# Baseline + Live Mempool Architecture Design

**Problem**: Mempool live visualization needs price baseline but UTXOracle.py:
1. Generates HTML (not reusable)
2. Static calculation (stale after new block)
3. Can't be called directly without code duplication

**Solution**: Extract core algorithm → shared module + continuous update

---

## Current State Analysis

### UTXOracle.py Structure (v9.1)
```
Step 1-4:  Configuration, RPC, Date handling, Block hashes
Step 5-6:  Histogram initialization, Transaction loading
Step 7:    Remove round BTC amounts ← REUSABLE
Step 8:    Build price finding stencil ← REUSABLE
Step 9:    Estimate rough price ← REUSABLE
Step 10:   Create intraday price points ← REUSABLE
Step 11:   Find exact average price ← REUSABLE
Step 12:   Generate HTML plot ← NOT NEEDED
```

**Reusable Core**: Steps 7-11 (~400 lines)
- Pure algorithm (no I/O, no UI)
- Input: transactions list
- Output: price estimate + confidence

---

## Proposed Architecture

### Option A: Shared Price Calculator Module ⭐ RECOMMENDED

**Principle**: Black box modularity - extract algorithm once, use twice

```
live/backend/price_calculator.py  ← NEW MODULE
├── build_histogram()           # Step 5-6 logic
├── remove_round_amounts()      # Step 7
├── build_stencil()             # Step 8
├── estimate_rough_price()      # Step 9
└── calculate_price()           # Main entry point

UTXOracle.py                    ← IMMUTABLE
├── Uses: price_calculator module for Steps 7-11
├── Adds: Steps 1-4 (config), Step 12 (HTML)
└── Remains: Reference implementation

live/backend/mempool_analyzer.py  ← MODIFIED
├── Uses: price_calculator module
├── Adds: Real-time streaming, windowing
└── Updates: On every new block
```

**Pros**:
- Zero code duplication
- UTXOracle.py remains immutable (reference)
- Mempool live gets same algorithm
- Single source of truth for pricing logic

**Cons**:
- Refactoring needed (extract from UTXOracle.py)
- Need to verify extracted code matches exactly

---

### Option B: Hybrid - Reference Keeps Original, Live Uses Copy

**Principle**: UTXOracle.py stays pure, mempool has independent implementation

```
UTXOracle.py                    ← IMMUTABLE, UNCHANGED
└── All Steps 1-12 inline

live/backend/mempool_analyzer.py  ← ENHANCED
├── Duplicate Steps 7-11 logic internally
├── Comment: "Algorithm from UTXOracle.py v9.1"
└── Independent maintenance
```

**Pros**:
- UTXOracle.py completely untouched
- No risk breaking reference implementation
- Easier initial development

**Cons**:
- Code duplication (400 lines)
- Algorithm divergence risk
- Must manually sync fixes/improvements

---

## Continuous Update Strategy

### Problem: Baseline Staleness
```
Block N confirmed → baseline calculated
    ↓ 10 minutes pass
Block N+1 confirmed → baseline STALE
    ↓ mempool visualization
Wrong Y-axis range (uses old N baseline)
```

### Solution: Block-Triggered Recalculation

```python
# live/backend/zmq_listener.py - MODIFIED
async def stream_blocks():  # NEW: listen to zmqpubrawblock
    """Stream confirmed blocks from Bitcoin Core"""
    zmq_socket_blocks = context.socket(zmq.SUB)
    zmq_socket_blocks.connect("tcp://127.0.0.1:28333")  # rawblock endpoint
    zmq_socket_blocks.subscribe(b"rawblock")

    while True:
        topic, body, seq = await zmq_socket_blocks.recv_multipart()
        yield body  # Raw block bytes

# live/backend/orchestrator.py - MODIFIED
async def _update_baseline_on_block(self):
    """Recalculate baseline when new block arrives"""
    async for raw_block in self.zmq_listener.stream_blocks():
        # Parse block to get transactions
        block_txs = parse_block_transactions(raw_block)

        # Update baseline calculator with confirmed transactions
        self.baseline_calculator.add_confirmed_block(block_txs)

        # Recalculate 24h baseline
        new_baseline = self.baseline_calculator.calculate_baseline()

        # Update mempool analyzer with new baseline
        self.analyzer.update_baseline(new_baseline)

        logger.info(f"Baseline updated: {new_baseline.price}")
```

**Flow**:
1. Block confirmed (ZMQ `rawblock` message)
2. Parse block → extract transactions
3. Add to rolling 24h window (144 blocks)
4. Recalculate baseline price
5. Update mempool analyzer Y-axis range
6. Mempool points rendered with correct scaling

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Bitcoin Core                                                 │
├─────────────────────────────────────────────────────────────┤
│ zmqpubrawblock (28333) → Confirmed blocks                   │
│ zmqpubrawtx (28332)    → Mempool transactions               │
└───────────┬─────────────────────────────┬───────────────────┘
            │                             │
            ▼                             ▼
┌───────────────────────┐    ┌────────────────────────────────┐
│ BaselineCalculator    │    │ MempoolAnalyzer                │
├───────────────────────┤    ├────────────────────────────────┤
│ • 144 blocks (24h)    │    │ • Real-time tx stream          │
│ • Histogram building  │    │ • 3h window                    │
│ • Stencil sliding     │    │ • Uses baseline for Y-axis     │
│ • Price calculation   │───►│ • Adds mempool points          │
└───────────────────────┘    └──────────────┬─────────────────┘
                                            │
                                            ▼
                                ┌───────────────────────────┐
                                │ DataStreamer (WebSocket)  │
                                ├───────────────────────────┤
                                │ • Baseline price          │
                                │ • Mempool transactions    │
                                │ • Combined visualization  │
                                └───────────┬───────────────┘
                                            │
                                            ▼
                                ┌───────────────────────────┐
                                │ Frontend (Canvas 2D)      │
                                ├───────────────────────────┤
                                │ LEFT:  Baseline (cyan)    │
                                │ RIGHT: Mempool (orange)   │
                                │ Y-axis: Baseline range    │
                                └───────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Extract Core Algorithm ✅ DO FIRST
1. Create `live/backend/price_calculator.py`
2. Extract Steps 7-11 from UTXOracle.py
3. Write unit tests for extracted module
4. Verify: matches UTXOracle.py output exactly

### Phase 2: Baseline Calculator
1. Create `live/backend/baseline_calculator.py`
2. Use `price_calculator` module
3. Maintain rolling 144-block window
4. Expose: `calculate_baseline()` → price + range

### Phase 3: ZMQ Block Listener
1. Add `rawblock` subscription to `zmq_listener.py`
2. Parse block transactions
3. Trigger baseline recalculation

### Phase 4: Mempool Analyzer Integration
1. Modify `mempool_analyzer.py` to accept baseline
2. Use baseline price range for Y-axis
3. Render mempool points relative to baseline

### Phase 5: Frontend Visualization
1. Display baseline price line (horizontal)
2. Show baseline confidence band
3. Render mempool points on same scale
4. Timeline: baseline (left) → mempool (right)

---

## Open Questions ❓

1. **Histogram compatibility**: Do mempool tx fit same bins as on-chain?
   - Mempool: no confirmation time
   - On-chain: has block timestamp
   - Solution: Use price bins only, ignore time bins?

2. **Baseline window**: 24h (144 blocks) vs 3h mempool?
   - Baseline: slower-moving, stable reference
   - Mempool: fast-moving, volatile
   - Need different Y-axis ranges?

3. **UTXOracle.py modification**: Extract vs copy?
   - Option A: Modify UTXOracle.py to import shared module
   - Option B: Keep UTXOracle.py unchanged, copy algorithm
   - Recommendation: **Option A** (single source of truth)

4. **Performance**: Recalculate 144 blocks every 10 min?
   - Current: ~2.25s for 1 day (batch mode)
   - Real-time: needs <10s recalculation
   - Optimization: Incremental update (rolling window)?

---

## Decision: OPTION B + Verification Tests ✅ APPROVED

**Chosen**: Independent implementation with mandatory parity testing
**Date**: 2025-10-21
**Rationale**: User identified verification tests eliminate divergence risk

**Why Option B + Verification is SUPERIOR**:
1. ✅ UTXOracle.py 100% immutable (sacred reference)
2. ✅ Mempool live optimized for production
3. ✅ Verification tests guarantee algorithmic equivalence
4. ✅ CI/CD blocks merge if algorithms diverge
5. ✅ Simpler implementation (no refactoring)
6. ✅ Separation of concerns: reference vs production

**Implementation**:
```python
# tests/test_algorithm_parity.py
def test_price_calculation_matches_reference():
    """BLOCKS CI/CD if fails - prevents divergence"""
    ref_price = utxoracle_reference(test_data)
    live_price = mempool_analyzer.estimate_price(test_data)
    assert ref_price == pytest.approx(live_price, rel=1e-6)
```

**Next Steps** (Updated to Option B):
1. ✅ Design approved
2. Phase 1: Build verification framework (T075-T078)
3. Phase 2: Copy algorithm with parity tests (T079-T082)
4. Phases 3-6: Baseline + integration (T083-T099)

---

**Author**: Claude Code (ultrathink session)
**Date**: 2025-10-21
**Status**: DRAFT - Needs user approval
