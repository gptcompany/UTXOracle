# UTXOracle Live - Visual Reference Examples

**Purpose**: Visual design references for UTXOracle Live implementation

**Sources**:
- UTXOracle.py output (confirmed/historical data visualization)
- utxo.live/oracle production system (mempool live visualization)

**Date**: 2025-10-18 to 2025-10-19

---

## 1. UTXOracle.py Output (Confirmed/Historical Data)

**File**: `UTXOracle_Local_Node_Price.png`

**Purpose**: Reference for **LEFT panel** ("Confirmed On-Chain") in dual-panel design

### Visual Characteristics

**Title & Metadata**:
- **Header**: "UTXOracle Local" (cyan, large)
- **Subtitle**: "Oct 16, 2025 blocks from local node" (white)
- **Price**: "UTXOracle Consensus Price $110,488" (bright green)
- **Footer**: "Consensus Data: this plot is identical and immutable for every bitcoin node" (green)

**Scatter Plot**:
- **Background**: Black (#000000)
- **Points**: Cyan/Teal (#00CED1 or similar)
- **Density**: Very high (thousands of points)
- **Range**: $104,964 - $116,013 (Y-axis)
- **Timespan**: Block heights 919255-919407 (24 hours, Oct 16 2025)
- **X-axis labels**: Block height + UTC time (00:12 - 23:58)
- **Clustering**: Strong horizontal bands at ~$110k-111k

**Color Palette**:
- Background: `#000000` (black)
- Title: `#00FFFF` (cyan)
- Price: `#00FF00` (bright green)
- Points: `#00CED1` (cyan/teal)
- Footer text: `#00FF00` (green)
- Axis labels: White

**Key Insight**: This represents **confirmed blockchain data** (immutable, identical for all nodes). Contrast with mempool data (real-time, orange points below).

---

## 2. Mempool Live Visualization (Real-time Data)

**Files**: Sequential screenshots from utxo.live/oracle

**Purpose**: Reference for **RIGHT panel** ("Mempool") in dual-panel design

### Screenshot Sequence

These screenshots demonstrate the **real-time accumulation** of mempool transaction points over ~30 seconds:

### 1. Screenshot from 2025-10-18 09-26-57.png (t=0s)
- **Mempool Avg**: $113,600
- **Last Block**: 3min ago
- **Transaction count**: ~200-300 visible points
- **Price range**: $108k-119k (wide distribution)
- **Cluster center**: ~$113k (strong clustering around average)

### 2. Screenshot from 2025-10-18 09-27-03.png (t=6s)
- **Mempool Avg**: $113,600 (stable)
- **Last Block**: Still 3min
- **Transaction count**: ~250-350 points (new points added)
- **Animation**: Points appear in real-time on right side
- **Cluster behavior**: Tightening around $113-114k

### 3. Screenshot from 2025-10-18 09-27-11.png (t=14s)
- **Mempool Avg**: $113,600 (stable)
- **Last Block**: Still 3min
- **Transaction count**: ~300-400 points
- **Pattern**: Vertical spread increasing (more price variance)
- **New points**: Appearing at $116-118k (upper range)

### 4. Screenshot from 2025-10-18 09-27-21.png (t=24s)
- **Time progression**: Shows continuous accumulation
- **Rolling window**: Older points on left fade/scroll out
- **Real-time update**: Demonstrates live streaming behavior

### 5-7. Additional frames (10:24-10:27)
- Different time window (1 hour later)
- Shows system running continuously
- Price stability over extended period

---

## Key Visual Elements (Reference for Implementation)

### Layout (Dual Panel)
```
┌─────────────────────────────────┬─────────────────────────────────┐
│ Confirmed On-Chain (3hr)        │ Mempool                         │
│ [Left panel - confirmed data]   │ Avg: $113,600                  │
│                                  │ [Scatter plot - orange dots]   │
│                                  │ Last Block: 3min               │
│                                  │ Current Time: 16:19:46 EST     │
└─────────────────────────────────┴─────────────────────────────────┘
```

### Color Scheme
- **Background**: Black (#000000)
- **Transaction points**: Orange (#FFA500 or similar)
- **Price text**: Orange/Yellow (#FFB000)
- **Labels**: Cyan for "Confirmed On-Chain" (#00FFFF)
- **Labels**: Orange for "Mempool" section

### Typography
- **Main header**: "UTXOracle Live" (large, cyan + orange)
- **Price display**: "Avg: $113,600" (prominent, orange)
- **Metadata**: "Last Block: 3min" (smaller, orange)
- **Timestamp**: "Current Time: HH:MM:SS TZ" (bottom right)

### Scatter Plot Characteristics
- **X-axis**: Time (horizontal scroll, recent on right)
- **Y-axis**: Price ($108k-119k range shown)
- **Point size**: Small dots (2-3px diameter)
- **Point density**: High (300-500 visible points in 3hr window)
- **Animation**: Points appear right-to-left (newest on right edge)
- **Clustering**: Strong vertical clustering around average price

### Performance Indicators
- **Frame capture interval**: 6-14 seconds between screenshots
- **Point accumulation rate**: ~50-100 new points every 6 seconds
- **Price stability**: $113,600 held constant across sequence
- **Smooth animation**: No visible lag or stuttering

---

## Implementation Requirements (Derived from Screenshots)

### Must Have (MVP)
1. **Dual panel layout** - Confirmed vs Mempool side-by-side
2. **Orange scatter plot** - Canvas 2D rendering
3. **Large price display** - "Avg: $XXX,XXX" prominently shown
4. **Last block timer** - "Last Block: Xmin" indicator
5. **Real-time timestamp** - Current time display (with timezone)
6. **Auto-scaling Y-axis** - Adapts to price range (e.g., 108k-119k)
7. **Rolling window** - Points scroll left as new ones appear right
8. **Black background** - Dark theme for long viewing sessions

### Nice to Have (Post-MVP)
- Left panel "Confirmed On-Chain" visualization (can be static for MVP)
- Transition animations between price ranges
- Confidence score indicator (not visible in these screenshots)
- Stats display (total tx, filtered, etc.)

### Performance Targets (From Visual Analysis)
- **Point capacity**: 300-500 points visible simultaneously
- **Update rate**: New points every 0.5-5 seconds
- **Rendering**: Must handle point accumulation without lag
- **Smoothness**: 30 FPS minimum (Canvas 2D sufficient for this density)

---

## Animation Sequence Breakdown

**t=0s to t=24s progression**:
1. Initial state: ~200 points clustered at $113k
2. **Every 6 seconds**: +50-100 new points appear on right edge
3. **Vertical spread**: Price variance increases from $110-115k to $108-118k
4. **Horizontal scroll**: Oldest points (left edge) gradually disappear
5. **Center of mass**: Stays stable at $113k (algorithm working correctly)

This demonstrates the **3-hour rolling window** behavior - older transactions exit left as new ones enter right.

---

## Reference for Agents

**Task 05 (Visualization Renderer)** should use these screenshots as visual reference:

- **Color palette**: Extract exact hex codes if possible
- **Layout proportions**: Dual panel ~50/50 split
- **Point rendering**: Small orange circles, anti-aliased
- **Typography**: Large bold for price, smaller for metadata
- **Animation timing**: Points appear smoothly, not in batches

**Key takeaway**: This is the **proven production design** from utxo.live - implement this exact visual style for UTXOracle Live MVP.

---

## Files
- `Screenshot from 2025-10-18 09-26-57.png` - Initial state (t=0s)
- `Screenshot from 2025-10-18 09-27-03.png` - +6 seconds
- `Screenshot from 2025-10-18 09-27-11.png` - +14 seconds
- `Screenshot from 2025-10-18 09-27-21.png` - +24 seconds
- `Screenshot from 2025-10-18 10-24-54.png` - 1 hour later
- `Screenshot from 2025-10-18 10-25-09.png` - +15 seconds
- `Screenshot from 2025-10-18 10-27-16.png` - +2 minutes

**Total sequence duration**: 24 seconds (active animation) + 1 hour stability test

---

## Dual-Panel Design Comparison

### Side-by-Side Layout (Target for UTXOracle Live)

```
┌───────────────────────────────────┬───────────────────────────────────┐
│ LEFT: Confirmed On-Chain (3hr)    │ RIGHT: Mempool (Live)             │
├───────────────────────────────────┼───────────────────────────────────┤
│ Reference: UTXOracle_Local_...png │ Reference: Screenshot 09-26-*.png │
├───────────────────────────────────┼───────────────────────────────────┤
│ • CYAN/TEAL points               │ • ORANGE points                   │
│ • Thousands of points (dense)     │ • 300-500 points (sparse)         │
│ • Historical/Confirmed data       │ • Real-time/Mempool data          │
│ • Static (updates every 10 min)   │ • Live (updates every 0.5-5s)     │
│ • Block height X-axis             │ • Timestamp X-axis                │
│ • "Consensus Price $XXX,XXX"      │ • "Avg: $XXX,XXX"                 │
│ • Footer: "Consensus Data..."     │ • "Last Block: Xmin"              │
└───────────────────────────────────┴───────────────────────────────────┘
```

### Key Differences

| Aspect | Left Panel (Confirmed) | Right Panel (Mempool) |
|--------|------------------------|----------------------|
| **Data Source** | Confirmed blocks (3hr window) | Mempool transactions (real-time) |
| **Point Color** | Cyan/Teal (#00CED1) | Orange (#FFA500) |
| **Point Density** | Very high (thousands) | Medium (300-500) |
| **Update Rate** | Every ~10 minutes (new block) | Every 0.5-5 seconds |
| **X-Axis** | Block height + UTC time | Rolling timestamp |
| **Y-Axis** | BTC Price ($) | BTC Price ($) |
| **Title** | "UTXOracle Local" | "Mempool" |
| **Price Label** | "Consensus Price $XXX,XXX" (green) | "Avg: $XXX,XXX" (orange) |
| **Footer** | "Consensus Data: identical..." | "Last Block: Xmin" |
| **Immutability** | ✅ Immutable (blockchain) | ❌ Dynamic (mempool changes) |
| **Purpose** | Show confirmed price truth | Show real-time market activity |

### Implementation Priority (MVP)

**Phase 1** (MVP):
- ✅ **RIGHT panel only** (Mempool live visualization)
- ❌ LEFT panel can be static placeholder or empty

**Phase 2** (Production):
- ✅ Both panels functional
- ✅ LEFT panel updates every block (~10 min)
- ✅ Synchronized Y-axis ranges

### Color Palette Summary

**LEFT Panel** (Confirmed):
```css
background: #000000;
points: #00CED1;      /* Cyan/Teal */
title: #00FFFF;       /* Bright Cyan */
price: #00FF00;       /* Bright Green */
footer: #00FF00;      /* Green */
```

**RIGHT Panel** (Mempool):
```css
background: #000000;
points: #FFA500;      /* Orange */
title: #FFA500;       /* Orange */
price: #FFB000;       /* Orange/Yellow */
metadata: #FFA500;    /* Orange */
```

**Total sequence duration**: 24 seconds (active animation) + 1 hour stability test

---

## Files Summary

### Confirmed/Historical Visualization
- `UTXOracle_Local_Node_Price.png` - Oct 16, 2025 output from UTXOracle.py

### Mempool Live Visualization
- `Screenshot from 2025-10-18 09-26-57.png` - t=0s (baseline)
- `Screenshot from 2025-10-18 09-27-03.png` - t=6s
- `Screenshot from 2025-10-18 09-27-11.png` - t=14s
- `Screenshot from 2025-10-18 09-27-21.png` - t=24s
- `Screenshot from 2025-10-18 10-24-54.png` - 1 hour later
- `Screenshot from 2025-10-18 10-25-09.png` - +15s
- `Screenshot from 2025-10-18 10-27-16.png` - +2 min

---

*Visual Reference Guide v1.1*
*Created*: 2025-10-19
*Updated*: Added UTXOracle.py confirmed data reference (dual-panel comparison)
*Purpose*: Complete design reference for UTXOracle Live implementation
