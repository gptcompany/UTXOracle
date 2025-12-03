# Dashboard Gap Analysis - 2025-10-30

## Executive Summary

**Status**: Dashboard implementation **incomplete** and **not aligned with original spec-002 requirements**.

**Critical Issues**:
1. JavaScript crash blocks all data loading
2. Visualization downgraded from Canvas (spec-002) to Plotly (spec-003)
3. No real data - only 1 mock test record
4. Integration service never executed

---

## 🐛 Bug Report

### Bug #1: JavaScript TypeError (CRITICAL)

**File**: `frontend/comparison.html:365`
**Error**: `TypeError: Cannot read properties of undefined (reading 'add')`

**Root Cause**:
```javascript
async function loadData(days) {
    // ...
    event.target.classList.add('active');  // ❌ event undefined!
}

// Called without event context:
window.addEventListener('DOMContentLoaded', () => {
    loadData(7);  // No event parameter!
});
```

**Fix Required**:
```javascript
async function loadData(days, eventTarget = null) {
    if (eventTarget) {
        document.querySelectorAll('.timeframe-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        eventTarget.classList.add('active');
    }
    // ... rest of function
}

// Update calls:
window.addEventListener('DOMContentLoaded', () => {
    loadData(7);  // No event needed for initial load
});

// Button onclick:
<button onclick="loadData(7, this)">7 Days</button>
```

**Impact**: Dashboard completely non-functional (stuck on "Loading...")

---

### Bug #2: Missing Real Data

**DuckDB**: Only 1 test record (Oct 27)
**Integration Service**: Never executed (no cron, no manual runs)
**Bitcoin RPC**: Mock implementation (lines 186-193 in `daily_analysis.py`)

**Current Data**:
```json
{
  "timestamp": "2025-10-27T17:44:11",
  "utxoracle_price": 100000,    // MOCK
  "mempool_price": 115654,
  "confidence": 1,
  "tx_count": 3                  // MOCK
}
```

**Impact**: Cannot test timeframe selector (7/30/90 days) with only 1 data point

---

### Bug #3: API Count Mismatch

**Claimed**: "14/14 tests passing"
**Reality**:
- 5 total endpoints (latest, historical, comparison, health, root)
- 14 test CASES (not endpoints)
- No WebSocket (spec-002 requirement)
- No real-time streaming (spec-002 requirement)

---

## 📊 Spec-002 vs Spec-003 Comparison

### Visualization Requirements

| Feature | Spec-002 (Original) | Spec-003 (Refactor) | Implemented |
|---------|---------------------|---------------------|-------------|
| **Rendering** | Canvas 2D | Plotly.js | ✅ Plotly |
| **Data Type** | Individual outputs | Aggregated price | ✅ Aggregated |
| **Point Count** | 300-500 visible | 2 lines (time series) | ✅ 2 lines |
| **Update Rate** | 0.5-5 seconds | 10 minutes (cron) | ⚠️ Never runs |
| **Animation** | Real-time accumulation | Static reloads | ✅ Static |
| **Window** | 3-hour rolling | 7/30/90 days | ✅ Days |
| **Dual Panel** | Confirmed + Mempool | Single chart | ❌ Single |
| **Points** | Orange "quadratini" | Green/Red lines | ✅ Lines |

### Architecture

| Component | Spec-002 | Spec-003 | Implemented |
|-----------|----------|----------|-------------|
| **ZMQ Listener** | Custom (229 lines) | mempool.space | ✅ Docker |
| **TX Parser** | Custom (369 lines) | mempool.space | ✅ Docker |
| **Algorithm** | Duplicated (581 lines) | Library (536 lines) | ✅ Library |
| **Storage** | In-memory | DuckDB | ✅ DuckDB |
| **API** | WebSocket | REST | ✅ REST |
| **Frontend** | Canvas | Plotly | ✅ Plotly |

---

## ❓ Key Questions for User

### Question 1: Visualization Type

**Spec-002 shows**: Canvas rendering with individual transaction outputs (300-500 orange "quadratini")
**Spec-003 implements**: Plotly dual time series (2 aggregate lines)

**Which do you want?**
- Option A: Keep Plotly (simpler, aggregate view)
- Option B: Implement Canvas (detailed, per-output view)
- Option C: Hybrid (Plotly for history + Canvas for live)

### Question 2: Real-time vs Historical

**Spec-002**: Real-time streaming (0.5-5 second updates)
**Spec-003**: Historical comparison (10-minute cron)

**Which is priority?**
- Option A: Fix historical dashboard first (Plotly + DuckDB)
- Option B: Implement real-time first (WebSocket + Canvas)
- Option C: Both (longer timeline)

### Question 3: Data Granularity

**"Quadratini" rendering** implies:
- Individual outputs visible
- Clustering/filtering (top N)
- 90 days @ 144 blocks/day @ ~3000 tx/block @ ~2.5 outputs/tx = **97M outputs**

**Plotly dual time series** implies:
- Aggregated price (1 point per calculation)
- 90 days @ 144 blocks/day = **12,960 points** (manageable)

**Which granularity do you need?**

---

## 🎯 Recommended Actions

### Immediate (< 1 hour)

1. **Fix JavaScript bug** (event.target undefined)
   - Edit `frontend/comparison.html:365`
   - Add optional parameter to `loadData()`
   - Test dashboard loads without crash

2. **Generate test data** (7 days)
   ```bash
   # Manually run daily_analysis 7 times with mock data
   for i in {1..7}; do
     # Modify timestamp to simulate historical data
     python scripts/daily_analysis.py --dry-run
   done
   ```

3. **Verify Plotly renders** with multiple data points
   - Test 7/30/90 day selector
   - Verify time series displays correctly

### Short-term (< 1 day)

4. **Clarify visualization requirements**
   - User decision: Canvas (spec-002) vs Plotly (spec-003)
   - Update tasks.md accordingly
   - Document decision in spec.md

5. **Implement real Bitcoin RPC** (if continuing spec-003)
   - Replace mock in `daily_analysis.py:164-193`
   - Use bitcoin-python-async or similar
   - Test with real Bitcoin Core node

6. **Set up cron job** (if continuing spec-003)
   ```bash
   */10 * * * * cd /media/sam/1TB/UTXOracle && uv run python scripts/daily_analysis.py
   ```

### Long-term (1+ days)

7. **If choosing Canvas (spec-002)**:
   - Implement WebSocket server (Task 04)
   - Implement Canvas 2D rendering (Task 05)
   - Real-time transaction streaming
   - Rolling 3-hour window

8. **If choosing Plotly (spec-003)**:
   - Keep current implementation
   - Fix bugs
   - Populate historical data
   - Deploy systemd service

---

## 📈 Current Implementation Score

| Category | Score | Notes |
|----------|-------|-------|
| **API Backend** | 8/10 | Works, but no WebSocket |
| **Database** | 9/10 | Schema correct, needs data |
| **Frontend** | 3/10 | Broken JS, no real data |
| **Integration** | 1/10 | Never executed |
| **Visualization** | 4/10 | Simple dual series, not Canvas |
| **Documentation** | 7/10 | Good, but specs conflicting |
| **Testing** | 8/10 | 14/14 API tests pass |
| **Deployment** | 2/10 | No systemd, no cron |

**Overall**: **42/80 (52%)** - Incomplete implementation

---

## 🚧 Blockers

1. **electrs sync** (99.8% complete, 1-2 hours)
   - Blocks: Real Bitcoin RPC connection
   - Blocks: Self-hosted mempool.space API
   - Blocks: Integration service execution

2. **Spec ambiguity** (Canvas vs Plotly)
   - Blocks: Frontend implementation clarity
   - Blocks: Task prioritization
   - Blocks: Resource estimation

3. **No real data** (only 1 mock record)
   - Blocks: Dashboard testing
   - Blocks: Timeframe selector verification
   - Blocks: Scalability testing

---

## 📝 Conclusion

**Dashboard is NOT production-ready**:
- ❌ JavaScript crash (critical)
- ❌ Only 1 mock data point
- ❌ Integration service never run
- ⚠️ Visualization mismatch (spec-002 vs spec-003)
- ⚠️ No systemd/cron deployment

**Estimated completion**: 1-3 days depending on user decision (Canvas vs Plotly)

**Next step**: User must clarify visualization requirements before proceeding.
