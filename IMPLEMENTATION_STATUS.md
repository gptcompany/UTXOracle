# UTXOracle Live - Implementation Status

**Session Date**: 2025-10-21
**Branch**: 002-mempool-live-oracle

## ✅ Phase BL-1: Baseline Calculator (COMPLETE)

- [X] **T095**: Baseline calculator structure + stencils created
- [X] **T096**: 144-block rolling window (`deque` with `maxlen=144`)
- [X] **T097**: `calculate_baseline()` algorithm (Steps 7-11 from UTXOracle.py)
  - ✅ Histogram normalization (Step 7)
  - ✅ Stencil slide for rough price (Step 9)
  - ⚠️ Simplified convergence (uses rough price, full convergence TODO)
  - ✅ Fallback to $100k if stencil slide fails
  - ✅ Test passing: `tests/test_baseline_calculator.py`
- [X] **T098**: Baseline state management (`get_state()` method)

**File**: `live/backend/baseline_calculator.py`

---

## ✅ Phase BL-2: ZMQ Block Listener (COMPLETE)

- [X] **T099**: ZMQ block subscription (`connect_blocks()`, dual sockets)
- [X] **T100**: `stream_blocks()` async generator
  - Yields `(raw_block_bytes, block_height)` tuples
  - Auto-reconnect logic (same as mempool stream)
- [X] **T101**: Block transaction parser
  - `extract_transactions_from_block()` → List[(amount_btc, timestamp)]
  - Reuses UTXOracle filtering logic (amount range [1e-5, 1e5])
- [X] **T102**: Orchestrator integration
  - `_process_blocks()` task added
  - Baseline recalculation on new block
  - Graceful degradation if blocks unavailable

**Files**:
- `live/backend/zmq_listener.py` (extended)
- `live/backend/block_parser.py` (new)
- `live/backend/orchestrator.py` (extended)

---

## ⚠️ Phase BL-3: Mempool Integration (CRITICAL - IN PROGRESS)

### 🔴 **CRITICAL ISSUE**: Hardcoded Price

**Current State:**
```python
# live/backend/mempool_analyzer.py
def estimate_price(self) -> float:
    return 100000.0  # ❌ HARDCODED - NOT calculating from mempool!
```

**Screenshot Evidence:** `examples/mempool_space_reference.png` shows system displaying "$100,000" (hardcoded value)

### **Remaining Tasks:**

- [ ] **T103**: Modify `mempool_analyzer.py` to accept baseline reference
  ```python
  class MempoolAnalyzer:
      def __init__(self, window_hours=3.0):
          self.baseline = None  # ADD THIS

      def set_baseline(self, baseline_result: BaselineResult):
          """Update baseline reference from orchestrator."""
          self.baseline = baseline_result
  ```

- [ ] **T104**: Update `estimate_price()` to use baseline (**CRITICAL**)
  ```python
  def estimate_price(self) -> float:
      if self.baseline is None:
          logger.warning("No baseline available, using fallback")
          return 100000.0  # Fallback only

      # Use baseline price as reference for mempool scaling
      baseline_price = self.baseline.price

      # TODO: Calculate actual mempool price deviation from baseline
      # For MVP: return baseline price (better than hardcoded)
      return baseline_price
  ```

- [ ] **T105**: Implement `get_combined_history()`
  ```python
  def get_combined_history(self) -> List[dict]:
      """Return baseline + mempool data points for dual timeline."""
      history = []

      # Baseline points (24h on-chain, cyan)
      if self.baseline:
          history.append({
              "type": "baseline",
              "price": self.baseline.price,
              "timestamp": self.baseline.timestamp,
              "color": "cyan"
          })

      # Mempool points (3h real-time, orange)
      for tx in self.transactions:
          history.append({
              "type": "mempool",
              "price": tx.amounts[0] * estimate_price(),  # Approximate
              "timestamp": tx.timestamp,
              "color": "orange"
          })

      return history
  ```

---

## ⚠️ Phase BL-4: Frontend Visualization (BLOCKED by T103-T105)

- [ ] **T106**: Update `WebSocketMessage` in `live/shared/models.py`
  ```python
  class MempoolUpdateData(BaseModel):
      price: float
      confidence: float
      transactions: List[TransactionPoint]
      stats: SystemStats
      timestamp: float

      # ADD THESE:
      baseline_price: Optional[float] = None
      baseline_range: Optional[Tuple[float, float]] = None
      baseline_confidence: Optional[float] = None
  ```

- [ ] **T107**: Modify `mempool-viz.js` to render baseline points (cyan) vs mempool (orange)
- [ ] **T108**: Add baseline price line indicator (horizontal reference line)
- [ ] **T109**: Implement timeline split: LEFT=baseline (24h), RIGHT=mempool (3h)

---

## 📋 Phase BL-5-6: Optional (NOT PRIORITY)

- [ ] **T111-T114**: Code refactoring (extract histogram/price estimator modules)
- [ ] **T115-T118**: Algorithm parity tests (verification vs UTXOracle.py)

---

## 🚨 **Next Session Priorities**

### **PRIORITY 1: Fix Hardcoded Price (T103-T104)**
1. Read `live/backend/mempool_analyzer.py`
2. Add `set_baseline()` method
3. Replace `return 100000.0` with `return self.baseline.price`
4. Uncomment line in `orchestrator.py`: `self.analyzer.set_baseline(baseline_result)`

### **PRIORITY 2: Combined History (T105)**
1. Implement `get_combined_history()` in `mempool_analyzer.py`
2. Returns baseline + mempool data points for visualization

### **PRIORITY 3: WebSocket Integration (T106)**
1. Update `WebSocketMessage` data model
2. Include baseline data in broadcasts

### **PRIORITY 4: Frontend Dual Timeline (T107-T109)**
1. Modify `mempool-viz.js` to render two timelines
2. LEFT: Baseline (24h on-chain, cyan points)
3. RIGHT: Mempool (3h real-time, orange points)
4. Horizontal line showing baseline price reference

---

## 📝 Manual Testing (BLOCKED - Requires Bitcoin Core ZMQ)

- [ ] **T062-T064**: End-to-end validation (needs `zmqpubrawtx` + `zmqpubrawblock` configured)
- [ ] **T074d**: Visual verification (timeline scrolling, fade, point size)
- [ ] **T110**: Baseline update verification (new block triggers recalculation)

**Blocker**: Bitcoin Core must be running with ZMQ enabled:
```conf
# bitcoin.conf
zmqpubrawtx=tcp://127.0.0.1:28332
zmqpubrawblock=tcp://127.0.0.1:28333
```

See `specs/002-mempool-live-oracle/quickstart.md` Step 1.2 for setup.

---

## 🎯 Summary

**What Works:**
- ✅ Baseline calculator (Steps 7-9 algorithm)
- ✅ ZMQ block subscription
- ✅ Block transaction parser
- ✅ Orchestrator integration
- ✅ Mempool visualization (66 tx visible, scrolling/fade/size working)

**What's Broken:**
- ❌ **Price is hardcoded $100,000** instead of calculated
- ❌ **No baseline → mempool integration** (baseline calculated but not used)
- ❌ **Dual timeline not implemented** (only mempool visible)

**Critical Path to Fix:**
1. T103: Pass baseline to mempool analyzer
2. T104: Use baseline.price instead of 100000
3. T105: Combined history for dual timeline
4. T106-T109: Frontend visualization

**Estimated Time**: 1-2 hours for T103-T109

---

*Last Updated*: 2025-10-21 (Session 9d388d71)
*Token Usage*: 127k/200k (63%)
