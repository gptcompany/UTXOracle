# Whale Detection Dashboard - Manual Test Checklist

**Feature**: Real-Time Whale Detection Dashboard (Spec 006)
**Phase**: Phase 5 - User Story 1 Implementation
**Date**: 2025-11-27

## Test Environment Setup

### Prerequisites
- [ ] UTXOracle API server running (`uvicorn api.main:app --host 0.0.0.0 --port 8001`)
- [ ] DuckDB database exists with whale flow data
- [ ] Modern browser installed (Chrome 90+, Firefox 88+, or Safari 14+)

### Access Dashboard
- [ ] Navigate to `http://localhost:8001/whale`
- [ ] Dashboard HTML loads without errors
- [ ] Browser console (F12) shows no JavaScript errors

---

## Initial Load Performance (SC-001)

- [ ] Dashboard loads in **<3 seconds**
- [ ] All CSS styles applied correctly (dark theme visible)
- [ ] Net flow display area visible
- [ ] Transaction feed section visible
- [ ] Chart placeholder visible
- [ ] Footer displays correctly

**Expected**:
- Dark background (#0a0a0a)
- Green terminal aesthetic
- Monaco monospace font
- Smooth loading animation

---

## Connection Status (FR-010)

### Status Indicator
- [ ] Status bar appears at top of page
- [ ] Initial status shows "Connecting..." (yellow dot)
- [ ] Status changes to "Connected" (green dot) within 5 seconds
- [ ] Last update timestamp displays

### Connection Resilience
- [ ] Stop API server → status changes to "Disconnected" (red dot)
- [ ] Restart API server → reconnects automatically
- [ ] Error message displays gracefully if API unavailable

**Expected**:
- Status dot animates (pulse) while connecting
- Clear visual feedback for each state

---

## Net Flow Display (FR-001, T041)

### BTC Value Display
- [ ] Net flow value displays in format: "+XX.XX BTC" or "-XX.XX BTC"
- [ ] Value updates every 5 seconds (poll interval)
- [ ] Sign (+/-) matches direction
- [ ] Decimal precision: 2 places

### USD Value Display (T046)
- [ ] USD equivalent displays below BTC value
- [ ] Format uses number suffixes (K, M, B) appropriately
  - Example: "$2.5M" for $2,500,000
  - Example: "$125K" for $125,000
  - Example: "$1.2B" for $1,200,000,000
- [ ] USD value updates with BTC value

### Visual Feedback
- [ ] Net flow value has appropriate color:
  - Green for positive (accumulation)
  - Red for negative (distribution)
  - Yellow for neutral/zero
- [ ] Value has glow effect (text-shadow)

**Expected**:
- Large, prominent display (4rem font)
- Clear contrast against dark background
- Smooth color transitions

---

## Direction Indicator (FR-003, T042)

### Arrow Symbol
- [ ] Arrow direction matches flow:
  - ↑ (up arrow) for ACCUMULATION/BUY
  - ↓ (down arrow) for DISTRIBUTION/SELL
  - → (right arrow) for NEUTRAL
- [ ] Arrow color matches direction
- [ ] Arrow animates smoothly on direction change

### Direction Label
- [ ] Label displays: "ACCUMULATION", "DISTRIBUTION", or "NEUTRAL"
- [ ] Label color matches arrow color
- [ ] Font size: 2rem, bold

### Description Text
- [ ] Descriptive message displays:
  - "Whales are buying Bitcoin" (accumulation)
  - "Whales are selling Bitcoin" (distribution)
  - "No significant whale activity" (neutral)
- [ ] Message is readable (smaller font, lighter color)

**Expected**:
- Instant visual understanding of whale sentiment
- Clear, professional presentation

---

## API Integration (FR-002, T043-T044)

### Polling Mechanism
- [ ] API called immediately on page load
- [ ] Subsequent polls every 5 seconds
- [ ] Network tab (F12) shows regular `/api/whale/latest` requests
- [ ] No excessive polling when page hidden (tab inactive)

### Data Parsing
- [ ] API response correctly parsed:
  - `whale_net_flow` → BTC value
  - `whale_direction` → Direction indicator
- [ ] Handles null/undefined values gracefully
- [ ] Timestamp updates on each successful poll

### Error Handling (FR-010, T045)
- [ ] Loading state shows spinner during initial fetch
- [ ] Error state shows retry button if API fails
- [ ] Retry button works correctly
- [ ] Error message is descriptive

**Expected**:
- Seamless real-time updates
- No stuttering or lag
- Graceful degradation on errors

---

## Loading & Error States (T045)

### Loading State
- [ ] Spinner displays on initial load
- [ ] Loading message: "Loading whale flow data..."
- [ ] Transitions smoothly to content when data arrives

### Error State
- [ ] Error icon (⚠️) displays
- [ ] Error message explains issue clearly
- [ ] Retry button present and functional
- [ ] Clicking retry initiates new fetch attempt

### Empty/No Data State
- [ ] If no whale data, displays "NEUTRAL" with zero values
- [ ] No broken UI elements
- [ ] All placeholders render correctly

**Expected**:
- Professional error handling
- User never sees broken/undefined values

---

## Number Formatting (T046)

### Test Cases
| Input (BTC) | Expected Display |
|-------------|------------------|
| 0.00 | +0.00 BTC |
| 125.50 | +125.50 BTC |
| -85.25 | -85.25 BTC |
| 0.01 | +0.01 BTC |

| Input (USD) | Expected Display |
|-------------|------------------|
| $0 | $0 |
| $125,000 | $125K |
| $2,500,000 | $2.5M |
| $1,200,000,000 | $1.2B |
| $45,678,901 | $45.7M |

- [ ] All formatting cases work correctly
- [ ] No scientific notation (e.g., 1.25e6)
- [ ] Consistent decimal places

---

## Responsive Design (Future: Phase 10, T088)

*Note: Full mobile testing deferred to Phase 10*

### Desktop Quick Check
- [ ] Layout looks correct at 1920x1080
- [ ] Layout looks correct at 1366x768
- [ ] No horizontal scrolling
- [ ] Text is readable

---

## Browser Compatibility

### Chrome 90+ (Primary)
- [ ] All features work
- [ ] Styling correct
- [ ] Performance good

### Firefox 88+
- [ ] All features work
- [ ] Styling correct
- [ ] Performance good

### Safari 14+ (if available)
- [ ] All features work
- [ ] Styling correct
- [ ] Performance good

---

## Performance Metrics (FR-001, SC-001-002)

### Load Time
- [ ] Time to first paint: < 1 second
- [ ] Time to interactive: < 3 seconds
- [ ] Net flow displays: < 3 seconds (SC-001)

### Runtime Performance
- [ ] CPU usage acceptable (< 10% idle)
- [ ] Memory usage stable (< 100MB after 10 minutes)
- [ ] No memory leaks (check DevTools Memory tab)
- [ ] Updates appear within 5 seconds (SC-002)

### Polling Efficiency
- [ ] No duplicate requests
- [ ] Requests pause when tab hidden
- [ ] Resume on tab focus

---

## Acceptance Criteria (User Story 1)

### Scenario 1: View Net Flow Value
- [ ] ✅ Dashboard loads
- [ ] ✅ Current net flow displays in BTC
- [ ] ✅ USD equivalent displays

### Scenario 2: Observe Direction Changes
- [ ] ✅ Net flow changes → display updates
- [ ] ✅ Direction indicator shows BUY/SELL/NEUTRAL
- [ ] ✅ Visual feedback (colors, arrows) matches direction

### Scenario 3: Handle No Activity
- [ ] ✅ No whale activity → "NEUTRAL" displays
- [ ] ✅ Zero values show clearly
- [ ] ✅ No broken UI

---

## Known Limitations (Phase 5 MVP)

*These features are intentionally deferred to later phases:*

- **Transaction Feed**: Placeholder only (Phase 6)
- **Historical Chart**: Placeholder only (Phase 7)
- **WebSocket**: Using HTTP polling (Phase 6)
- **Urgency Scores**: Not implemented (Phase 8)
- **Alerts**: Not implemented (Phase 9)
- **Mobile Responsive**: Basic only (Phase 10)

---

## Test Result Summary

**Date Tested**: _______________
**Tester**: _______________
**Browser**: _______________

### Overall Results
- [ ] ✅ PASS - All critical tests passed
- [ ] ⚠️ PASS WITH ISSUES - Non-blocking issues found
- [ ] ❌ FAIL - Blocking issues found

### Issues Found

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

### Notes

```
(Add any additional observations here)
```

---

## Sign-Off

- [ ] Phase 5 (User Story 1) complete and tested
- [ ] Ready to proceed to Phase 6 (Real-time transaction feed)
- [ ] No blocking issues

**Approved By**: _______________
**Date**: _______________
