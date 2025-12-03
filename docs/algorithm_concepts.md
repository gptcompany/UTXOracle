# UTXOracle Algorithm Concepts

This document extracts and organizes the conceptual sections from UTXOracle.py to facilitate modular development and understanding of the algorithm.

---

## Introduction

**Purpose**: Explain the dual function of code (for computers and humans) and provide context for new readers.

**Key Concepts**:
- UTXOracle finds Bitcoin price using only local node data
- No third-party dependencies or external price feeds
- Pure Python 3 standard library implementation
- Single-file, top-to-bottom execution for transparency

**User Guidance**:
- Requires Python 3 and Bitcoin Core node with RPC enabled
- Default: finds yesterday's price
- Options: `-d YYYY/MM/DD` for specific date, `-rb` for recent 144 blocks

**Design Philosophy**:
- Intentional inefficiencies for educational clarity
- Avoids advanced libraries to maintain independence
- Linear execution without function abstraction
- Hash-tag comments explain algorithm to non-programmers

---

## Step 1 - Configuration Options

**Lines**: 78-203

**Purpose**: Detect operating system, set Bitcoin data paths, parse command-line arguments, and prepare RPC credentials.

**Key Concepts**:

### Platform Detection
- Automatically determines Bitcoin data directory based on OS:
  - **macOS**: `~/Library/Application Support/Bitcoin`
  - **Windows**: `%APPDATA%\Bitcoin`
  - **Linux**: `~/.bitcoin`

### Command-Line Argument Parsing
- `-h`: Display help message
- `-d YYYY/MM/DD`: Specify UTC date to evaluate
- `-p /path/to/dir`: Specify custom data directory
- `-rb`: Use recent 144 blocks instead of date mode

### Configuration File Discovery
- Searches for `bitcoin.conf` or `bitcoin_rw.conf`
- Parses configuration to extract:
  - RPC user/password
  - RPC host/port
  - Cookie file path
  - Blocks directory location

### Variables Initialized
```python
date_entered = ""
date_mode = True
block_mode = False
block_start_num = 0
block_finish_num = 0
block_nums_needed = []
block_hashes_needed = []
block_times_needed = []
```

---

## Step 2 - Establish RPC Connection

**Lines**: 206-312

**Purpose**: Create a reusable function to communicate with Bitcoin node via RPC and test connectivity.

**Key Concepts**:

### RPC Communication Standard
- Community consensus: RPC is the standard interface for node communication
- Supports both cookie authentication and username/password

### `Ask_Node()` Function
- **Parameters**: `command` (list), `cred_creation` (bool)
- **Authentication**:
  - Attempts rpcuser/rpcpassword from config
  - Falls back to `.cookie` file if credentials not found
- **Error Handling**: Provides troubleshooting steps on connection failure
- **Returns**: JSON-RPC response as bytes (mimics subprocess output)

### Connection Verification
- Tests connection with `getblockcount`
- Retrieves current block height minus 6 (consensus confirmation)
- Gets block header to verify node responsiveness

### Progress Tracking
```
0%.. 20%.. 40%.. 60%.. 80%.. 100%
```

---

## Step 3 - Check Dates

**Lines**: 315-405

**Purpose**: Validate user-requested date and determine time window for price calculation.

**Key Concepts**:

### Why Time Averaging is Required
- Single block often lacks sufficient transaction data
- Some blocks may contain zero transactions
- Daily average provides natural human time scale
- Accounting standard: daily resolution is commonly used

### Date Discovery Process
1. Get most recent block timestamp from node
2. Calculate UTC midnight of latest day
3. Assign previous day as latest possible price date
4. Validate user-entered date against constraints

### Date Validation Rules
- **Maximum date**: Must be before latest UTC midnight (need 6 blocks after)
- **Minimum date**: December 15, 2023 (earliest tested version)
- **Format**: Must be `YYYY/MM/DD`

### Date Mode Variables
```python
datetime_entered       # User-requested date as datetime object
price_day_seconds      # Unix timestamp of target day
price_day_date_utc     # Formatted date string (e.g., "Jan 15, 2025")
price_date_dash        # Dash-separated date (e.g., "2025-01-15")
```

---

## Step 4 - Find Block Hashes

**Lines**: 409-583

**Purpose**: Identify which blocks correspond to the requested date and retrieve their hashes.

**Key Concepts**:

### Why Block Hashes are Required
- Bitcoin nodes store blocks by hash, not by date or height
- Must convert date → block height → block hash

### Block Mode (Recent Blocks)
- Simple: subtract 144 from current block height
- Iterate from start to finish, collecting hashes

### Date Mode (Historical Date)
**Challenge**: Map calendar date to block range

**Solution - Iterative Refinement**:
1. **Initial estimate**: Use ~144 blocks/day assumption
   ```
   blocks_ago_estimate = round(144 * seconds_since_price_day / seconds_in_a_day)
   ```
2. **Refinement loop**: Oscillate around correct block until convergence
3. **Fine-tuning**: Increment/decrement by single blocks to find exact midnight
4. **Forward search**: Find last block of target day

### Helper Functions
- `get_block_time(height)`: Returns (timestamp, hash) for block height
- `get_day_of_month(time_in_seconds)`: Extracts day from Unix timestamp

### Output Lists
```python
block_nums_needed    # List of block heights
block_hashes_needed  # Corresponding block hashes
block_times_needed   # Block timestamps
```

---

## Step 5 - Initialize Histogram

**Lines**: 589-642

**Purpose**: Create data structure to capture distribution of transaction output values.

**Key Concepts**:

### Why Histogram is Needed
- Price doesn't exist at single satoshi amount
- On-chain price emerges from clustering at round fiat amounts
- Need to detect patterns in BTC spending behavior

### Histogram Design Parameters

**Interval Width**:
- Too small → noisy data
- Too large → lost detail
- Optimal: ~0.5% (average daily fiat volatility)
- Implementation: **200 intervals per 10x range**

**Value Range**:
- **Minimum**: 10⁻⁶ BTC (100 sats)
- **Maximum**: 10⁶ BTC (1 million BTC)
- **Rationale**: Most round fiat amounts fall within this range (2020-2025)
- **Future**: May need adjustment as purchasing power changes

### Histogram Structure
```python
output_histogram_bins = [0.0]  # Bin edges (logarithmic scale)

# Generate 200 samples per 10x range from 10^-6 to 10^6 BTC
for exponent in range(-6, 6):
    for b in range(0, 200):
        bin_value = 10 ** (exponent + b/200)
        output_histogram_bins.append(bin_value)

# Initialize bin counts (all zeros)
output_histogram_bin_counts = [0.0] * number_of_bins
```

**Total bins**: 12 decades × 200 bins/decade = 2400 bins

---

## Step 6 - Load Histogram from Transaction Data

**Lines**: 646-887

**Purpose**: Extract transaction outputs from raw block data and populate histogram bins.

**Key Concepts**:

### Why This Step is Time-Consuming
- Processes ~144 blocks × 1MB each = ~144 MB raw binary data
- Reads every transaction in every block
- Manually parses binary Bitcoin block format

### Binary Parsing Functions

**`read_varint(f)`**: Read variable-length integer from byte stream
- Handles 1-byte, 2-byte, 4-byte, 8-byte formats

**`encode_varint(i)`**: Convert integer to variable-length bytes
- Used for reconstructing transaction data

**`compute_txid(raw_tx_bytes)`**: Calculate transaction ID
- SegWit detection (marker=0x00, flag=0x01)
- Strips witness data for txid computation
- Double SHA-256 hash in reverse byte order

### Transaction Filters

**Excluded Transactions**:
1. **More than 5 inputs**: Complex transactions unlikely to reflect simple spending
2. **Not exactly 2 outputs**: Reduces noise from complex payment patterns
3. **Coinbase outputs**: Mining rewards don't reflect market prices
4. **OP_RETURN outputs**: Data storage, not spending
5. **Large witness scripts**: >500 bytes indicates complex contracts
6. **Same-day inputs**: Circular transactions within analysis window

**Rationale**: Years of testing determined these filters maximize signal clarity

### Histogram Population Process
```python
for amount in filtered_output_values:
    amount_log = log10(amount)
    percent_in_range = (amount_log - first_bin_value) / range_bin_values
    bin_number = locate_bin(percent_in_range)
    output_histogram_bin_counts[bin_number] += 1.0
```

### Output Tracking Lists
```python
raw_outputs = []         # BTC amounts
block_heights_dec = []   # Block heights
block_times_dec = []     # Block timestamps
todays_txids = set()     # For same-day detection
```

---

## Step 7 - Remove Round Bitcoin Amounts

**Lines**: 889-968

**Purpose**: Smooth histogram bins containing round BTC amounts and normalize data.

**Key Concepts**:

### The Round BTC Problem
- Users spend both round BTC amounts AND round fiat amounts
- Hard to distinguish: Is 0.01 BTC a round BTC send, or is $1000 the round fiat target?
- **Cannot completely remove** because overlap occurs when BTC price is near round numbers

### Smoothing Strategy
Instead of removing, **average neighboring bins**:
```python
for round_btc_bin in round_btc_bins:
    amount_above = output_histogram_bin_counts[round_btc_bin + 1]
    amount_below = output_histogram_bin_counts[round_btc_bin - 1]
    output_histogram_bin_counts[round_btc_bin] = 0.5 * (amount_above + amount_below)
```

### Round BTC Amounts Smoothed
```
1k, 10k, 20k, 30k, 50k sats
100k, 200k, 300k, 500k sats
0.01, 0.02, 0.03, 0.04 BTC
0.1, 0.2, 0.3, 0.5 BTC
1 BTC
```

### Normalization Process
1. **Sum all bins** (excluding extreme ranges)
2. **Divide each bin by sum** → converts counts to percentages
3. **Cap extremes**: Any bin >0.008 is capped at 0.008
4. **Remove noise**: Zero out bins <10k sats and >10 BTC

**Why percentages?**
- More stable across days with varying transaction volume
- Makes histogram comparable across different time periods

---

## Step 8 - Construct the Price Finding Stencil

**Lines**: 971-1047

**Purpose**: Create pattern-matching templates based on known fiat spending behavior.

**Key Concepts**:

### Spending Proportionality Principle
- Users spend $100 **far more often** than $10,000
- Predictable proportions depend on amount size
- Historical testing reveals typical histogram shapes for each round fiat amount

### Two-Stencil Approach

**1. Smooth Stencil** (Gaussian curve)
- **Purpose**: Find center of gravity within ~20% range
- **Formula**: Bell curve centered at bin 411, std dev 201
  ```python
  smooth_stencil[x] = 0.00150 * e^(-(x-411)²/(2*201²)) + 0.0000005*x
  ```
- **Effect**: Captures overall spending distribution shift

**2. Spike Stencil** (Round USD amounts)
- **Purpose**: Refine alignment to specific fiat values (0.5% precision)
- **Hard-coded weights** for popular USD amounts:
  - $100 → weight 0.006174 (highest)
  - $50 → 0.005613
  - $10 → 0.003468
  - $1000 → 0.003688
  - etc.

**Data Source**: Historical testing measured average bin counts for each round fiat amount

### Why This Works
- Bitcoin's purchasing power rises over time
- Histogram center shifts toward smaller BTC amounts
- Stencil alignment reveals current BTC/USD price

---

## Step 9 - Estimate a Rough Price

**Lines**: 1049-1157

**Purpose**: Slide stencils across histogram to find best-fit position, yielding rough price estimate.

**Key Concepts**:

### Sliding Window Scoring

**Method**: Multiply stencil heights by histogram values at each position, sum result
```python
for slide in range(min_slide, max_slide):
    shifted_curve = output_histogram_bin_counts[left_p001+slide : right_p001+slide]

    slide_score = sum(shifted_curve[n] * spike_stencil[n] for n in range(len(spike_stencil)))

    if slide_score > best_slide_score:
        best_slide_score = slide_score
        best_slide = slide
```

### Price Range Boundaries
- **Center reference**: 0.001 BTC = $100 (i.e., BTC price = $100k)
- **Min slide**: -141 → implies $500k BTC price
- **Max slide**: +201 → implies $5k BTC price
- **Future updates needed** as Bitcoin purchasing power changes

### Stencil Weighting
- **Smooth weight**: 0.65
- **Spike weight**: 1.0
- **Rationale**: Historical testing optimized this ratio

### Refinement with Neighboring Bins
1. Score the best slide position
2. Score immediate neighbors (up and down)
3. **Weighted average** of best position and best neighbor:
   ```python
   w1 = (best_slide_score - avg_score) / total_weight
   w2 = (neighbor_score - avg_score) / total_weight
   rough_price_estimate = w1 * btc_in_usd_best + w2 * btc_in_usd_2nd
   ```

**Accuracy**: ~0.5% of true price

---

## Step 10 - Create Intraday Price Points

**Lines**: 1160-1257

**Purpose**: Assign rough fiat prices to individual Bitcoin outputs to enable refinement.

**Key Concepts**:

### Why Rough Estimate Isn't Final
- Rough price captures daily average within ~0.5%
- But we need **exact average** for precision
- Strategy: Use rough price to filter outputs, then find center of mass

### Price Window Construction
- **Window width**: ±25% around rough estimate
  - Accounts for errors in rough estimate
  - Handles volatile fiat price days
- **Does NOT mean UTXOracle limited to 25% daily swings**
  - Rough estimate already captures most volatility
  - Remaining error is much smaller

### Round USD Amounts Targeted
```python
usds = [5, 10, 15, 20, 25, 30, 40, 50, 100, 150, 200, 300, 500, 1000]
```

### Output Filtering Process
For each output amount `n`:
1. Loop through each USD target
2. Calculate BTC range: `usd / rough_price ± 25%`
3. Check if output falls within range
4. **Remove micro round satoshi amounts** (0.0001% tolerance around round sats)
5. If valid, compute implied price: `price = usd / n`

### Micro Round Satoshi Removal
Excludes perfectly round amounts at small scales:
- 50-100 sats (increments of 10)
- 100-1000 sats (increments of 10)
- 1k-10k sats (increments of 100)
- 10k-100k sats (increments of 1k)
- 100k-1M sats (increments of 10k)

**Result**: `output_prices[]` list of implied prices from filtered outputs

---

## Step 11 - Find the Exact Average Price

**Lines**: 1260-1375

**Purpose**: Iteratively converge to precise central price using geometric median approach.

**Key Concepts**:

### Central Output Algorithm

**`find_central_output(prices, price_min, price_max)`**:
1. Filter prices within bounds
2. Sort prices ascending
3. **Prefix sum optimization** for efficient distance calculation
4. For each price, compute total distance to all other prices:
   ```python
   dist[i] = sum(|price[i] - price[j]| for all j)
   ```
5. Return price with **minimum total distance** (geometric median)
6. Calculate **Median Absolute Deviation (MAD)** for spread measurement

### Iterative Convergence Process
1. Start with ±5% window around rough estimate
2. Find central price within window
3. Re-center window on new central price
4. Repeat until convergence

**Convergence criteria**:
- Central price already in set → **stable convergence**
- Central price oscillates → **stable oscillation pattern**

**Final price**: First stable value (converged or oscillation center)

### Axis Range Calculation
- Expand window to ±10% for deviation measurement
- Map deviation percentage to y-axis range:
  ```python
  ax_range = 0.05 + (dev_pct - 0.17) * ((0.15 - 0.05) / (0.20 - 0.17))
  ```
- **Clamp**: 5% minimum, 20% maximum
- Used for visualization bounds

**Output**: `central_price` (exact average), `price_dn`, `price_up` (plot bounds)

---

## Step 12 - Generate a Price Plot HTML Page

**Lines**: 1377-1801

**Purpose**: Create interactive HTML visualization with canvas-based price chart.

**Key Concepts**:

### Canvas Layout Geometry
```python
width = 1000           # Canvas width (px)
height = 660           # Canvas height (px)
margin_left = 120      # Y-axis labels
margin_right = 90      # Price annotations
margin_top = 100       # Title area
margin_bottom = 120    # X-axis labels
```

### Data Preparation

**X-axis (Block Heights)**:
- Linearly interpolate between first and last block
- Display as "Block Height + UTC Time" labels
- 5 evenly spaced tick marks

**Y-axis (Prices)**:
- Filter `output_prices` within plot bounds (`price_dn` to `price_up`)
- Corresponding `output_blocks` and `output_times`
- Sort by timestamps for visual continuity

### JavaScript Canvas Rendering

**Coordinate Scaling**:
```javascript
function scaleX(blockHeight) {
    return marginLeft + (blockHeight - xmin) / (xmax - xmin) * plotWidth;
}

function scaleY(price) {
    return marginTop + (1 - (price - ymin) / (ymax - ymin)) * plotHeight;
}
```

**Plot Elements**:
1. **Background**: Black
2. **Title**: "UTXOracle" (cyan) + "Local" (lime green)
3. **Subtitle**: Date + consensus price
4. **Axes**: White borders on all four sides
5. **Y-axis ticks**: 5 evenly spaced price labels
6. **X-axis ticks**: 5 block heights with UTC times
7. **Data points**: Cyan dots (0.75px squares)
8. **Average line**: Cyan annotation at central price
9. **Bottom note**: "Consensus Data: this plot is identical and immutable for every bitcoin node"

### Interactive Features

**Mouseover Tooltip**:
- Shows price, block height, and UTC time at cursor position
- Follows mouse across plot area
- Disappears outside plot bounds

**Download Button**:
- "Save PNG" button overlaid on canvas
- Converts canvas to data URL for download

### File Output
- **Filename format**:
  - Date mode: `UTXOracle_YYYY-MM-DD.html`
  - Block mode: `UTXOracle_start-finish.html`
- **Auto-open**: Uses `webbrowser.open()` to launch in default browser

### Embedded Content
- YouTube iframe embedding live stream below chart
- Promotes real-time mempool version of UTXOracle

---

## Algorithm Summary Flow

```
1. Configuration → Parse args, detect OS, read bitcoin.conf
2. RPC Connection → Authenticate with node, test connectivity
3. Date Validation → Verify requested date, convert to Unix timestamp
4. Block Discovery → Map date to block range, retrieve hashes
5. Histogram Init → Create logarithmic bins for BTC amounts
6. Transaction Load → Parse raw blocks, filter outputs, fill histogram
7. Round BTC Removal → Smooth round BTC bins, normalize to percentages
8. Stencil Construction → Build smooth + spike pattern templates
9. Rough Price → Slide stencils, find best fit (±0.5% accuracy)
10. Intraday Points → Assign rough fiat prices to outputs, filter round sats
11. Exact Price → Iterative geometric median convergence
12. HTML Visualization → Render canvas chart, interactive tooltips, save PNG
```

---

## Key Design Decisions

### Why Single File?
- **Transparency**: No hidden functions, entire logic visible
- **Independence**: No external dependencies beyond Python stdlib
- **Educational**: Hash-tag comments explain each step inline

### Why No Abstraction?
- **Readability**: Users can follow logic top-to-bottom
- **Avoids scrolling**: No need to jump between function definitions
- **Intentional repetition**: Clarity prioritized over DRY principle

### Why Histogram Approach?
- **Clustering detection**: Reveals patterns in spending behavior
- **Statistical robustness**: Averages over many transactions
- **Round amount filtering**: Separates BTC-round from fiat-round spending

### Why Two-Stencil System?
- **Coarse + fine alignment**: Smooth stencil finds region, spike refines
- **Handles volatility**: Wide search range, narrow precision
- **Historical validation**: Weights optimized from years of testing

### Why Iterative Convergence?
- **Geometric median**: Minimizes total distance (robust to outliers)
- **Handles oscillation**: Detects stable patterns even without point convergence
- **Self-correcting**: Each iteration refines based on updated distribution

---

## Future Modular Architecture Considerations

### Potential Module Boundaries

**1. Configuration Module**
- Input: Command-line args, OS detection
- Output: RPC credentials, date/block range

**2. RPC Interface Module**
- Input: RPC credentials, commands
- Output: Raw JSON responses from node

**3. Block Discovery Module**
- Input: Date or block range, RPC interface
- Output: List of (block_hash, block_height, timestamp)

**4. Transaction Processor Module**
- Input: Block hashes, RPC interface
- Output: Filtered (amount, height, time) tuples

**5. Histogram Analyzer Module**
- Input: Transaction outputs
- Output: Normalized histogram bins

**6. Price Estimator Module**
- Input: Histogram bins, stencil templates
- Output: Rough price estimate

**7. Convergence Module**
- Input: Rough price, output list
- Output: Exact central price, plot bounds

**8. Visualization Renderer Module**
- Input: Price data, block metadata
- Output: HTML file with canvas chart

### Black Box Interface Example
```python
# Module input/output contract
class HistogramAnalyzer:
    def __init__(self, bin_config):
        self.bins = create_bins(bin_config)

    def process(self, transactions):
        # Input: List[{amount, height, time}]
        # Output: {bins: List[float], counts: List[float]}
        return normalized_histogram
```

Each module independently testable and replaceable without breaking others.

---

## Testing Considerations

### Reproducibility
- **Same blockchain data → Same price**
- **Any node with same blocks → Same result**
- Historical validation: 672 days from Dec 2023 to Oct 2025

### Edge Cases to Handle
1. **Low transaction days**: Insufficient data
2. **High volatility days**: Wide price swings
3. **Round number overlap**: BTC price near $10k, $100k milestones
4. **Same-day circular transactions**: Inflates histogram incorrectly

### Historical Accuracy Metrics
- **Success rate**: 99.85% over 672 days
- **Processing time**: ~2.25 seconds per date (12 parallel workers)
- **Confidence indicator**: Deviation percentage (dev_pct)

---

## References

- **Algorithm version**: 9.1
- **Tested date range**: December 15, 2023 → October 17, 2025
- **Price range tested**: ~$5k to ~$500k (may need updates beyond this range)
- **Bin configuration**: 10⁻⁶ to 10⁶ BTC, 200 bins per decade
- **Filter thresholds**: Optimized through historical testing

---

*This document is a conceptual extraction from UTXOracle.py v9.1. For implementation details, refer to the source code.*
