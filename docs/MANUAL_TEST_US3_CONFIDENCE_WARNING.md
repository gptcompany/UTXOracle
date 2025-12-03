# Manual Test: T083 [US3] - Confidence Awareness

This document describes manual testing procedures for User Story 3: Confidence Awareness with low confidence warnings.

## Overview
User Story 3 adds visual feedback to help users understand when the price estimate is unreliable due to insufficient transaction data.

## Automated Tests
The following tests are automated and should PASS before manual testing:
- `test_confidence_score_ranges` (T075) - Validates confidence calculation logic
- `test_confidence_warning_display` (T076) - Validates HTML/CSS warning element exists

Run: `uv run pytest tests/test_mempool_analyzer.py::test_confidence_score_ranges tests/integration/test_frontend.py::test_confidence_warning_display -v`

## Prerequisites
Before running manual tests, ensure:

1. **Bitcoin Core running** with ZMQ enabled:
   ```bash
   # Check bitcoin.conf has:
   # zmqpubrawtx=tcp://127.0.0.1:28332
   ```

2. **Backend server running**:
   ```bash
   cd /media/sam/1TB/UTXOracle
   uv run uvicorn live.backend.api:app --reload
   ```

3. **Browser open** to frontend:
   ```
   http://localhost:8000
   ```

4. **Browser DevTools Console open** (F12) to monitor WebSocket messages

## Manual Test Cases

### Test Case 1: Initial State (0 transactions)
**Expected Behavior**:
- **Confidence value**: `--` (not available)
- **Confidence label**: `(--)` (gray)
- **Warning**: Hidden (not displayed)

**Steps**:
1. Open frontend in browser
2. Wait for WebSocket connection
3. Observe initial state before any transactions

**Why manual**: Cannot automate "no transactions" state in live environment

---

### Test Case 2: Warming Up Phase (1-99 transactions)
**Expected Behavior**:
- **Confidence value**: `0.00` - `0.29` (low)
- **Confidence label**: `(Low)` in **orange** color
- **Warning**: `⚠ Low confidence - warming up` **VISIBLE** (orange, italic)

**Steps**:
1. Start backend with fresh mempool
2. Wait for initial transactions to arrive (1-99)
3. Monitor confidence value in UI
4. Confirm warning appears when confidence < 0.30
5. Verify warning text is orange and italic

**Validation**:
```javascript
// In browser console:
document.getElementById('confidence').textContent  // Should be "0.XX"
document.getElementById('confidence-label').textContent  // Should be "(Low)"
document.getElementById('confidence-warning').classList.contains('show')  // Should be true
```

**Why manual**: Requires observing real-time transaction accumulation

---

### Test Case 3: Medium Confidence (100-999 transactions)
**Expected Behavior**:
- **Confidence value**: `0.30` - `0.79` (medium)
- **Confidence label**: `(Medium)` in **yellow** color
- **Warning**: Hidden (automatically disappears)

**Steps**:
1. Continue from Test Case 2
2. Wait for 100+ transactions to accumulate
3. Observe confidence increase to 0.30+
4. **Verify warning automatically disappears** when confidence >= 0.50

**Validation**:
```javascript
// In browser console:
document.getElementById('confidence').textContent  // Should be "0.30" - "0.79"
document.getElementById('confidence-label').textContent  // Should be "(Medium)"
document.getElementById('confidence-warning').classList.contains('show')  // Should be false
```

**Critical**: Warning should disappear at exactly `confidence = 0.50` (threshold per spec)

**Why manual**: Cannot automate gradual confidence transition

---

### Test Case 4: High Confidence (1000+ transactions)
**Expected Behavior**:
- **Confidence value**: `0.80` - `1.00` (high)
- **Confidence label**: `(High)` in **green** color
- **Warning**: Hidden (remains hidden)

**Steps**:
1. Continue from Test Case 3
2. Wait for 1000+ transactions to accumulate
3. Observe confidence increase to 0.80+
4. Confirm warning remains hidden

**Validation**:
```javascript
// In browser console:
document.getElementById('confidence').textContent  // Should be "0.80" - "1.00"
document.getElementById('confidence-label').textContent  // Should be "(High)"
document.getElementById('confidence-warning').classList.contains('show')  // Should be false
```

**Why manual**: Requires sustained transaction volume (10-20 minutes)

---

### Test Case 5: WebSocket Reconnect
**Expected Behavior**:
- Warning state should persist across reconnections
- If confidence was low before disconnect, warning should reappear after reconnect
- If confidence was high before disconnect, warning should stay hidden

**Steps**:
1. Wait until confidence is ~0.40 (warning visible)
2. Stop backend: `Ctrl+C` in uvicorn terminal
3. Observe UI shows "Disconnected" status
4. Restart backend: `uv run uvicorn live.backend.api:app --reload`
5. Verify warning reappears when confidence data arrives

**Validation**:
- Warning state matches confidence value after reconnect
- No visual glitches during reconnection

**Why manual**: Requires backend restart simulation

---

### Test Case 6: Edge Case - Exactly 0.50 Confidence
**Expected Behavior**:
- **At confidence = 0.49**: Warning **VISIBLE**
- **At confidence = 0.50**: Warning **HIDDEN** (threshold)

**Steps**:
1. Monitor confidence value until it reaches ~0.50
2. Observe exact moment warning disappears
3. Confirm threshold is exactly 0.50 (not 0.49 or 0.51)

**Validation**:
```javascript
// In browser console, check threshold logic:
// confidence < 0.50 → warning visible
// confidence >= 0.50 → warning hidden
```

**Why manual**: Requires precise observation of threshold behavior

---

## Visual Reference

### Warning Visible (confidence < 0.50)
```
┌─────────────────────────────────────────────────────┐
│ UTXOracle Live - Mempool Price Oracle               │
├─────────────────────────────────────────────────────┤
│ Avg: $113,456        ● Connected                    │
│ Confidence: 0.42 (Low)                              │
│ ⚠ Low confidence - warming up                       │  ← VISIBLE
└─────────────────────────────────────────────────────┘
```

### Warning Hidden (confidence >= 0.50)
```
┌─────────────────────────────────────────────────────┐
│ UTXOracle Live - Mempool Price Oracle               │
├─────────────────────────────────────────────────────┤
│ Avg: $113,456        ● Connected                    │
│ Confidence: 0.85 (High)                             │
│                                                      │  ← HIDDEN
└─────────────────────────────────────────────────────┘
```

---

## Color Coding Reference

| Confidence Range | Label | Color | Warning Visible? |
|------------------|-------|-------|------------------|
| 0.00 - 0.29 | (Low) | 🟠 Orange | ✅ Yes |
| 0.30 - 0.49 | (Medium) | 🟡 Yellow | ✅ Yes |
| 0.50 - 0.79 | (Medium) | 🟡 Yellow | ❌ No |
| 0.80 - 1.00 | (High) | 🟢 Green | ❌ No |

**Note**: Warning threshold is `0.50`, while color transition from Low→Medium is `0.30`

---

## Implementation Files Changed

- `/media/sam/1TB/UTXOracle/live/frontend/index.html` - Added warning element (line 23)
- `/media/sam/1TB/UTXOracle/live/frontend/styles.css` - Added warning styles (lines 123-134)
- `/media/sam/1TB/UTXOracle/live/frontend/mempool-viz.js` - Added warning logic (lines 138, 160-162, 180-187)
- `/media/sam/1TB/UTXOracle/live/shared/models.py` - Confidence calculation (lines 184-204)

---

## Success Criteria

All test cases must demonstrate:
1. ✅ Warning appears when confidence < 0.50
2. ✅ Warning disappears when confidence >= 0.50
3. ✅ Warning text is correct: "⚠ Low confidence - warming up"
4. ✅ Warning color is orange (#FF8C00) and italic
5. ✅ Transition is smooth (no visual glitches)
6. ✅ State persists across WebSocket reconnections

---

## Troubleshooting

### Warning Never Appears
**Possible causes**:
- CSS class `.show` not being added to element
- Element `#confidence-warning` not found in HTML
- JavaScript error in console (check DevTools)

**Fix**:
```javascript
// In browser console, manually test:
document.getElementById('confidence-warning').classList.add('show');  // Should make warning visible
```

### Warning Never Disappears
**Possible causes**:
- Confidence never reaches 0.50 (check transaction volume)
- JavaScript error in `updateConfidence()` method

**Fix**:
```javascript
// In browser console, manually hide:
document.getElementById('confidence-warning').classList.remove('show');
```

### Wrong Threshold (appears/disappears at wrong confidence value)
**Possible causes**:
- Threshold logic error in `mempool-viz.js` line 182

**Fix**: Verify code has `if (confidence < 0.5)` not `< 0.3` or other value

---

## Notes for Developers

- **Why 0.50 threshold?**: Spec defines Low=0.0-0.3, Medium=0.3-0.8. We chose 0.50 as midpoint to warn only when estimate is truly unreliable.
- **Why not hide at 0.30?**: Even at 0.30-0.49, estimate may have ~20% error. Warning helps users understand limitations.
- **Future improvement**: Could add sliding scale warning text (e.g., "Very low", "Low", "Marginal" based on sub-ranges).

---

**Document Version**: 1.0  
**Last Updated**: 2025-10-20  
**Related Tasks**: T075, T076, T077, T078, T079, T080, T081, T082, T083  
**User Story**: US3 - Confidence Awareness  
