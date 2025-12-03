# Bugfix Report: WebSocket Payload Crash (2025-10-23)

## Issue
After implementing UTXOracle Step 10 to generate dense intraday price points, the browser crashed with:
```
RangeError: Maximum call stack size exceeded
```

## Root Cause
Backend generated 186,232 intraday points from 320,686 transactions across 144 blocks. All points were sent via WebSocket, exceeding browser JSON parsing limits.

## Solution
Added sampling in `baseline_calculator.py` to limit intraday_points to 10,000 max before sending via WebSocket:

```python
# BUGFIX 2025-10-23: Sample intraday_points to 10k for WebSocket performance
sampled_intraday_points = intraday_points
if len(intraday_points) > 10000:
    import random
    sampled_intraday_points = random.sample(intraday_points, 10000)
    logger.info(
        f"Sampled {len(sampled_intraday_points)} intraday points for WebSocket (from {len(intraday_points)})"
    )
```

## Files Modified
- `live/backend/baseline_calculator.py` (lines 551-560)

## Validation
✅ Browser loads without crashes
✅ Dense baseline cloud renders correctly (10k points)
✅ Mempool updates stream smoothly
✅ WebSocket stable with confidence 0.33 (148 active transactions)

## Visual Proof
- Before: Browser crashed on connection
- After: Working visualization with 40/60 panel split
  - Left: Cyan baseline cloud (10k sampled from 186k points)
  - Right: Orange mempool transactions

## Performance Impact
- Reduced WebSocket payload: 186k → 10k points (94.6% reduction)
- Visual quality: No degradation (10k points sufficient for dense cloud)
- Render time: <5ms per frame
