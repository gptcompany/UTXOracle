# Visualization Fix Plan - Dense Point Rendering

**Date**: 2025-10-22
**Root Cause**: Backend has baseline transaction data but doesn't serialize it for WebSocket
**Status**: READY TO IMPLEMENT

---

## Problem Summary

**Current Behavior**:
- Backend calculates baseline from 11,176 transactions (144 blocks)
- Backend stores transactions in memory: `self.blocks = [{"height": ..., "transactions": [(amount, timestamp), ...]}]`
- **BUT**: WebSocket message sends empty `baseline.transactions = []`
- Frontend fallback generates only 50 synthetic points (sparse visualization)

**Target Behavior**:
- Backend sends actual transaction data in WebSocket message
- Frontend renders 5,000-10,000 real transaction points
- Creates dense continuous cloud matching reference images

---

## Data Flow Verification

### Backend Storage (CONFIRMED)

**File**: `/media/sam/1TB/UTXOracle/live/backend/baseline_calculator.py`

```python
# Line 192-194: Transactions stored in memory
def add_block(self, transactions: List[Tuple[float, float]], height: int):
    """Add a block with transactions to the rolling window."""
    self.blocks.append({"height": height, "transactions": transactions})
    # transactions = [(amount_btc, timestamp), ...]

# Line 370-373: Transactions collected for baseline calculation
all_transactions = []
for block in self.blocks:
    all_transactions.extend(block["transactions"])
# Result: all_transactions = [(0.5, 1729580000), (1.2, 1729580001), ...]
```

**Data is present** in `BaselineCalculator.blocks` - just not exposed via API!

### Current API Response (MISSING DATA)

**File**: `/media/sam/1TB/UTXOracle/live/backend/api.py:72-80`

```python
# Current code (INCOMPLETE):
baseline_data = BaselineData(
    price=bl.price,
    price_min=bl.price_min,
    price_max=bl.price_max,
    confidence=bl.confidence,
    timestamp=bl.timestamp,
    block_height=bl.block_height,
    # ❌ MISSING: transactions field
)
```

**Result**: WebSocket sends baseline without transaction data.

### Target API Response (REQUIRED)

```python
# Fixed code:
from live.shared.models import BaselineData, TransactionPoint

# Convert raw transactions to TransactionPoint list
transaction_points = [
    TransactionPoint(timestamp=ts, price=amount_btc * bl.price)
    for amount_btc, ts in bl.transactions[:10000]  # Sample to 10k for performance
]

baseline_data = BaselineData(
    price=bl.price,
    price_min=bl.price_min,
    price_max=bl.price_max,
    confidence=bl.confidence,
    timestamp=bl.timestamp,
    block_height=bl.block_height,
    transactions=transaction_points,  # ✅ ADD THIS
)
```

---

## Implementation Plan

### Step 1: Modify Data Models (ALREADY DONE ✅)

**File**: `/media/sam/1TB/UTXOracle/live/shared/models.py:212-221`

```python
class BaselineData(BaseModel):
    """Baseline price data from on-chain blocks (T106)"""
    price: float = Field(..., gt=0, description="24h baseline price (USD)")
    price_min: float = Field(..., gt=0, description="Lower bound (USD)")
    price_max: float = Field(..., gt=0, description="Upper bound (USD)")
    confidence: float = Field(..., ge=0, le=1, description="Baseline confidence [0-1]")
    timestamp: float = Field(..., gt=0, description="Last updated (Unix timestamp)")
    block_height: Optional[int] = Field(None, description="Latest block height")
    # ✅ ALREADY HAS: TransactionPoint support via MempoolUpdateData.transactions
```

**Note**: The model structure already supports transactions via `MempoolUpdateData.transactions`, but baseline doesn't populate it.

### Step 2: Expose Transactions in BaselineResult

**File**: `/media/sam/1TB/UTXOracle/live/backend/baseline_calculator.py:22-31`

**BEFORE**:
```python
@dataclass
class BaselineResult:
    price: float
    price_min: float
    price_max: float
    confidence: float
    timestamp: float
    block_height: Optional[int] = None
    num_transactions: int = 0
    # ❌ MISSING: actual transaction data
```

**AFTER**:
```python
@dataclass
class BaselineResult:
    price: float
    price_min: float
    price_max: float
    confidence: float
    timestamp: float
    block_height: Optional[int] = None
    num_transactions: int = 0
    transactions: List[Tuple[float, float]] = None  # ✅ ADD: [(amount_btc, timestamp), ...]
```

### Step 3: Populate Transactions in calculate_baseline()

**File**: `/media/sam/1TB/UTXOracle/live/backend/baseline_calculator.py:370-423`

**BEFORE**:
```python
def calculate_baseline(self) -> Optional[BaselineResult]:
    # ... (existing code) ...

    # Line 370-373: Collect all transactions
    all_transactions = []
    for block in self.blocks:
        all_transactions.extend(block["transactions"])

    # ... (price calculation logic) ...

    # Line 417-424: Return result WITHOUT transactions
    return BaselineResult(
        price=final_price,
        price_min=price_min,
        price_max=price_max,
        confidence=confidence,
        timestamp=time.time(),
        block_height=self.blocks[-1]["height"],
        num_transactions=len(all_transactions),
        # ❌ MISSING: transactions=all_transactions
    )
```

**AFTER**:
```python
def calculate_baseline(self) -> Optional[BaselineResult]:
    # ... (existing code) ...

    # Collect all transactions
    all_transactions = []
    for block in self.blocks:
        all_transactions.extend(block["transactions"])

    # ... (price calculation logic) ...

    # ✅ SAMPLE to 10,000 transactions for performance
    sampled_transactions = all_transactions
    if len(all_transactions) > 10000:
        import random
        sampled_transactions = random.sample(all_transactions, 10000)

    return BaselineResult(
        price=final_price,
        price_min=price_min,
        price_max=price_max,
        confidence=confidence,
        timestamp=time.time(),
        block_height=self.blocks[-1]["height"],
        num_transactions=len(all_transactions),
        transactions=sampled_transactions,  # ✅ ADD THIS
    )
```

### Step 4: Serialize Transactions in API Response

**File**: `/media/sam/1TB/UTXOracle/live/backend/api.py:72-91`

**BEFORE**:
```python
from live.shared.models import BaselineData

baseline_data = BaselineData(
    price=bl.price,
    price_min=bl.price_min,
    price_max=bl.price_max,
    confidence=bl.confidence,
    timestamp=bl.timestamp,
    block_height=bl.block_height,
)
```

**AFTER**:
```python
from live.shared.models import BaselineData, TransactionPoint

# Convert baseline transactions to TransactionPoint format
baseline_transactions = []
if hasattr(bl, 'transactions') and bl.transactions:
    for amount_btc, timestamp in bl.transactions:
        baseline_transactions.append(
            TransactionPoint(
                timestamp=timestamp,
                price=bl.price  # Use baseline price (all points at same price horizontally)
            )
        )

baseline_data = BaselineData(
    price=bl.price,
    price_min=bl.price_min,
    price_max=bl.price_max,
    confidence=bl.confidence,
    timestamp=bl.timestamp,
    block_height=bl.block_height,
)
```

**Wait, problem**: `BaselineData` doesn't have a `transactions` field. We need to pass it via `MempoolUpdateData.transactions` instead.

### Step 4 (CORRECTED): Add Baseline Transactions to MempoolUpdateData

**File**: `/media/sam/1TB/UTXOracle/live/backend/api.py:72-105`

**Check current structure**:
```python
# Line 72-80: baseline_data created
# Line 88-96: MempoolUpdateData created
update_data = MempoolUpdateData(
    price=state.price,
    confidence=state.confidence,
    transactions=[],  # ❌ EMPTY - should include baseline transactions
    stats=stats,
    timestamp=time.time(),
    baseline=baseline_data,
)
```

**FIX**:
```python
# Convert baseline transactions to TransactionPoint format
baseline_transactions = []
if combined["baseline"] is not None:
    bl = combined["baseline"]
    if hasattr(bl, 'transactions') and bl.transactions:
        for amount_btc, timestamp in bl.transactions:
            baseline_transactions.append(
                TransactionPoint(
                    timestamp=timestamp,
                    price=bl.price  # All baseline points at consensus price
                )
            )

# Create baseline_data (without transactions field)
baseline_data = BaselineData(
    price=bl.price,
    price_min=bl.price_min,
    price_max=bl.price_max,
    confidence=bl.confidence,
    timestamp=bl.timestamp,
    block_height=bl.block_height,
)

# Create update_data WITH baseline transactions
update_data = MempoolUpdateData(
    price=state.price,
    confidence=state.confidence,
    transactions=baseline_transactions,  # ✅ ADD baseline transactions here
    stats=stats,
    timestamp=time.time(),
    baseline=baseline_data,
)
```

---

## Frontend Changes (MINIMAL)

**File**: `/media/sam/1TB/UTXOracle/live/frontend/mempool-viz.js:275-320`

**Current code (with synthetic fallback)**:
```javascript
updateBaseline(update) {
    if (!update.baseline) return;

    // ❌ FALLBACK: Generate synthetic points if transactions missing
    if (!update.transactions || update.transactions.length === 0) {
        const syntheticPoints = [];
        for (let i = 0; i < 50; i++) {
            syntheticPoints.push({
                timestamp: Date.now() / 1000 - Math.random() * 10800,
                price: update.baseline.price * (0.95 + Math.random() * 0.10)
            });
        }
        this.baselinePoints = syntheticPoints;
    } else {
        this.baselinePoints = update.transactions;
    }
}
```

**After fix**:
```javascript
updateBaseline(update) {
    if (!update.baseline) return;

    // ✅ Use real transactions from backend
    if (update.transactions && update.transactions.length > 0) {
        this.baselinePoints = update.transactions;
        console.log(`[Baseline] Loaded ${update.transactions.length} transaction points`);
    } else {
        // Fallback only if backend truly has no data
        console.warn('[Baseline] No transactions in update, using synthetic fallback');
        const syntheticPoints = [];
        for (let i = 0; i < 50; i++) {
            syntheticPoints.push({
                timestamp: Date.now() / 1000 - Math.random() * 10800,
                price: update.baseline.price * (0.95 + Math.random() * 0.10)
            });
        }
        this.baselinePoints = syntheticPoints;
    }
}
```

**Note**: Frontend code already supports rendering thousands of points—just needs the data!

---

## Performance Considerations

### WebSocket Payload Size

**Current payload** (no transactions):
```json
{"type": "mempool_update", "data": {"baseline": {...}}}
```
**Size**: ~300 bytes

**With 10,000 transactions**:
```json
{
  "type": "mempool_update",
  "data": {
    "transactions": [
      {"timestamp": 1729580000.5, "price": 110000},
      ... (9,999 more)
    ],
    "baseline": {...}
  }
}
```
**Size**: ~350KB uncompressed, ~50KB gzip compressed

**Verdict**: Acceptable for local deployment (localhost), may need compression for remote access.

### Rendering Performance

**Current**: 50 synthetic points → 60 FPS (no performance issue)
**Target**: 10,000 real points → expect 30-60 FPS (Canvas 2D can handle this)

**Optimization if needed**:
- Use `requestAnimationFrame` batching (already implemented)
- Sample points when zoomed out (LOD - Level of Detail)
- Implement dirty region tracking (only redraw changed areas)

---

## Testing Checklist

### Backend Tests
- [ ] Verify `BaselineResult.transactions` populated with data
- [ ] Check transaction count matches `num_transactions`
- [ ] Confirm sampling to 10,000 works when >10k transactions exist
- [ ] Validate transaction timestamps are in correct range

### API Tests
- [ ] Inspect WebSocket message with DevTools
- [ ] Confirm `data.transactions[]` array is non-empty
- [ ] Verify transaction format: `{timestamp: float, price: float}`
- [ ] Check payload size (~350KB for 10k transactions)

### Frontend Tests
- [ ] Reload http://localhost:8000
- [ ] Check console: "Loaded X transaction points" message
- [ ] Count visible points: Should see ~10,000 cyan points
- [ ] Visual comparison: Should match dense cloud in reference images
- [ ] Performance check: Measure FPS (should be >30 FPS)

---

## Expected Visual Outcome

### Before Fix
- ~150 sparse cyan points (synthetic fallback)
- Large gaps between points
- ~30% horizontal coverage
- Scattered, non-continuous appearance

### After Fix
- ~10,000 dense cyan points (real data)
- Points overlap creating visual bands
- 100% horizontal coverage (full 3-hour timeline)
- Continuous cloud matching reference images

---

## Files to Modify

1. **`/media/sam/1TB/UTXOracle/live/backend/baseline_calculator.py`**
   - Line 22-31: Add `transactions` field to `BaselineResult`
   - Line 417-424: Populate `transactions` in return value
   - Add sampling logic to limit to 10,000 points

2. **`/media/sam/1TB/UTXOracle/live/backend/api.py`**
   - Line 72-105: Convert baseline transactions to `TransactionPoint[]`
   - Pass baseline transactions via `MempoolUpdateData.transactions`

3. **`/media/sam/1TB/UTXOracle/live/frontend/mempool-viz.js`** (OPTIONAL)
   - Line 275-320: Add logging to confirm transaction count
   - Remove synthetic fallback after confirming backend fix works

---

## Implementation Order

1. **Backend first** (baseline_calculator.py + api.py)
2. **Test WebSocket** (DevTools network tab)
3. **Frontend verification** (visual inspection)
4. **Performance tuning** (if FPS drops below 30)

**Estimated time**: 30 minutes implementation + 15 minutes testing

---

## Next Steps

**Ready to implement?**
1. Modify `baseline_calculator.py` (Step 2 + Step 3)
2. Modify `api.py` (Step 4)
3. Restart backend server
4. Reload frontend
5. Verify dense point rendering

**Expected result**: Transformation from sparse ~150 points to dense ~10,000 points, matching the continuous cloud in reference images.
