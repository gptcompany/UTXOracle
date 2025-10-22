# Visualization Bug Report - Missing Points Issue

**Date**: 2025-10-22
**Status**: CRITICAL BUG IDENTIFIED
**System**: UTXOracle Live - Frontend Visualization

## Executive Summary

The visualization canvas is not rendering any transaction points (neither orange mempool points nor cyan baseline points) due to a data model mismatch between backend and frontend.

## Root Cause Analysis

### Issue Location
File: `/media/sam/1TB/UTXOracle/live/frontend/mempool-viz.js`
Function: `getPointSize()` (lines 352-371)

### Problem
The `TransactionPoint` model (backend) only contains:
- `timestamp: float`
- `price: float`

However, the frontend's `getPointSize()` function expects:
- `timestamp`
- `price`
- **`btc_amount`** ← MISSING FIELD

### Evidence

#### Backend Model
```python
# /media/sam/1TB/UTXOracle/live/shared/models.py
class TransactionPoint(BaseModel):
    """Single transaction point for visualization"""
    timestamp: float = Field(..., gt=0, description="Unix timestamp (seconds)")
    price: float = Field(..., gt=0, description="Estimated price for this transaction (USD)")
```

#### Frontend Code (BUG)
```javascript
// Line 357-361
const values = this.transactions.map(t => t.price * t.btc_amount);  // ← btc_amount is undefined!
// ...
const txValue = tx.price * tx.btc_amount;  // ← Results in NaN
```

### Impact
- **Symptom**: Canvas renders background, axes, and labels correctly, but shows ZERO transaction points
- **WebSocket**: Connected and receiving 500 transactions per update
- **Baseline Data**: Present ($108,392 price received)
- **Render Loop**: Running at ~30 FPS (599 calls in 2 seconds)
- **Point Rendering**: **0 calls to `ctx.arc()`** - points never drawn

### Debug Evidence

Browser console shows:
```json
{
  "type": "mempool_update",
  "transactionsCount": 500,
  "hasBaseline": true,
  "baselinePrice": 108392.69,
  "firstTransaction": {
    "timestamp": 1761142475.1383312,
    "price": 100000
    // ← No btc_amount field
  },
  "renderCalls": 599,  // ← Render loop working
  "arcCalls": 0        // ← NO POINTS DRAWN
}
```

Testing `tx.price * tx.btc_amount`:
```json
{
  "btc_amount": undefined,
  "txValue": NaN,
  "isNaN": true
}
```

## Solution Options

### Option 1: Fix Frontend (Constant Point Size) ✅ RECOMMENDED
**Pros**:
- Simplest fix
- Works with existing backend
- No API changes
- Immediate restoration of functionality

**Cons**:
- Loses variable point sizing feature (T074b)
- All points same size

**Implementation**:
```javascript
getPointSize(tx) {
    // Use constant point radius (TransactionPoint lacks btc_amount field)
    return 3;
}
```

### Option 2: Add btc_amount to TransactionPoint Model
**Pros**:
- Preserves variable point sizing
- More informative visualization

**Cons**:
- Requires backend changes (Module 2, 3, 4)
- Need to track/store BTC amounts through entire pipeline
- More complex fix

**Implementation**:
```python
# models.py
class TransactionPoint(BaseModel):
    timestamp: float
    price: float
    btc_amount: float  # ← Add this field
```

Then update:
- `tx_processor.py`: Pass amounts through
- `mempool_analyzer.py`: Store amounts in history
- `api.py`: Include amounts in WebSocket message

### Option 3: Use Price-Based Sizing
**Pros**:
- Works with existing data
- Provides visual variation
- No backend changes

**Cons**:
- Less meaningful than USD value-based sizing
- High/low price points stand out arbitrarily

**Implementation**:
```javascript
getPointSize(tx) {
    const prices = this.transactions.map(t => t.price);
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const normalized = (tx.price - minPrice) / (maxPrice - minPrice);
    return this.pointMinRadius + Math.sqrt(normalized) * (this.pointMaxRadius - this.pointMinRadius);
}
```

## Recommendation

**Implement Option 1 immediately** to restore visualization functionality, then **consider Option 2** for a future enhancement (requires T074b specification update).

## Screenshots

### Current State (Bug)
![Current State](/media/sam/1TB/UTXOracle/current_viz_state.png)
- Shows: Axes, labels, baseline line (cyan dashed), stats
- Missing: Orange points (mempool), cyan points (baseline)

### Expected State
![Expected](/media/sam/1TB/UTXOracle/examples/mempool_attuale_reference.png)
- Should show: Orange points clustered on right, cyan points on left

## Testing Plan

After fix:
1. Reload page at http://localhost:8000
2. Verify orange points appear on right side (mempool transactions)
3. Verify points animate/scroll with 5-minute window
4. Verify baseline cyan line remains visible
5. Verify tooltips work on hover
6. Check console for errors
7. Monitor for 5+ minutes to confirm stability

## Related Tasks

- T074b: Variable point size (currently broken, will be constant-sized after fix)
- T107: Render baseline points (blocked by this bug)
- T108: Baseline price line (working, visible as cyan dashed line)
- T109: Dual timeline split (blocked by this bug)

## Files to Modify

### Option 1 (Immediate Fix)
- `/media/sam/1TB/UTXOracle/live/frontend/mempool-viz.js` (lines 352-371)

### Option 2 (Future Enhancement)
- `/media/sam/1TB/UTXOracle/live/shared/models.py`
- `/media/sam/1TB/UTXOracle/live/backend/tx_processor.py`
- `/media/sam/1TB/UTXOracle/live/backend/mempool_analyzer.py`
- `/media/sam/1TB/UTXOracle/live/backend/api.py`
- `/media/sam/1TB/UTXOracle/live/frontend/mempool-viz.js`
