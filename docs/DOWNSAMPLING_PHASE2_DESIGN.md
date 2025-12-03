# Downsampling Phase 2: Design Strategy

**Date**: Nov 2, 2025
**Status**: 📐 DESIGN PHASE
**Prerequisites**: ✅ Phase 1 Complete (T201-T205)

---

## Executive Summary

Based on Phase 1 findings, this document defines the design strategy for implementing downsampling for UTXOracle 2023-2025 historical series visualization.

**Key Decision**: **Hybrid Approach** (ax_range + temporal aggregation) with **Canvas 2D** rendering.

**Target**: 730 dates × 1,370 points/date = **1.0M points** (Canvas 2D compatible)

---

## T206: Use Case Definition ✅

### Use Case 1: Single-Date Chart (Already Implemented)
**Current Implementation**: UTXOracle.py HTML output
**Data Volume**: ~24k filtered points per date
**Rendering**: Canvas 2D (native implementation)
**Performance**: Excellent (<100ms render)

**Example**: `UTXOracle_2025-10-24.html`
- 23,956 filtered points from ~100k total outputs
- Interactive visualization with hover tooltips
- Price range: $105k-$116k (5% ax_range)

**Status**: ✅ Production-ready, no changes needed

---

### Use Case 2: Multi-Date Historical Series (NEW - Primary Goal)
**Requirement**: Display 2023-2025 price evolution (730 dates)

**Constraints**:
- Canvas 2D performance limit: ~1M points
- Target file size: <5MB JSON
- Render time: <2 seconds
- Maintain visual trend fidelity

**Data Challenge**:
```
Without downsampling: 730 dates × 24k points = 17.5M points ❌
With hybrid downsampling: 730 dates × 1.4k points = 1.02M points ✅
```

**User Interactions**:
- Pan/zoom timeline
- Hover for daily statistics
- Click date → load detailed single-date view
- Export chart as PNG/SVG

**Status**: 📋 To be implemented (Phase 3)

---

### Use Case 3: Real-Time Dashboard (Future)
**Requirement**: Live display of last 30 days with 10-minute updates

**Data Volume**: 30 dates × 1.4k points = 42k points (easily manageable)

**Technical Considerations**:
- Incremental updates (append new data without full re-render)
- WebSocket stream for real-time price updates
- Smooth animations for new data points

**Priority**: MEDIUM (after historical series MVP)

**Status**: 📋 Deferred to Phase 5

---

## T207: Data Size Calculations ✅

### Current State (Single Date)
```
Input:  144 blocks × ~700 outputs/block = ~100k total outputs
Filter: ax_range (5-20% dynamic) = 76% reduction
Output: ~24k filtered points for visualization

File Size: ~500KB HTML (includes embedded JavaScript)
```

### Historical Series Without Downsampling (PROBLEM)
```
Scenario: 730 dates (2023-2025)
Per-date: 24k filtered points (after ax_range)
Total:    730 × 24k = 17.5M points

Canvas 2D limit: ~1M points
Over budget: 17.5× (UNACCEPTABLE)
```

### Historical Series With Hybrid Downsampling (SOLUTION)
```
Step 1: Per-date ax_range filtering
        100k → 24k points/date (76% reduction)

Step 2: Temporal aggregation
        24k → 1.4k points/date (94% reduction)

Total:  730 × 1.4k = 1.02M points ✅

File Size Estimate:
- JSON data: ~3.5MB (1M points × 3.5 bytes/point)
- HTML + JS:  ~200KB
- Total:      ~3.7MB (<5MB target) ✅
```

### Breakdown by Target Points/Date

| Target pts/date | Total Points | Reduction | File Size | Canvas OK? |
|----------------|--------------|-----------|-----------|------------|
| 24,000 (current) | 17.5M | 0% | ~61MB | ❌ |
| 5,000 | 3.65M | 79% | ~13MB | ❌ |
| 2,000 | 1.46M | 92% | ~5.1MB | ⚠️ |
| 1,370 | 1.00M | 94% | ~3.5MB | ✅ |
| 1,000 | 730k | 96% | ~2.6MB | ✅ |
| 685 | 500k | 97% | ~1.8MB | ✅ |

**Recommendation**: Target **1,370 points/date** (1M total, 3.5MB file)

---

## T208-T211: Downsampling Strategies

### Option A: Adaptive Price Range (Existing Algorithm)

**Description**: Reuse UTXOracle.py ax_range filtering for each date

**Algorithm**:
```python
for date in dates:
    # 1. Calculate central_price and deviation
    central_price = find_central_output(outputs)
    dev_pct = calculate_deviation(outputs, central_price)

    # 2. Calculate dynamic ax_range (5-20%)
    ax_range = 0.05 + (dev_pct - 0.17) * 3.333
    ax_range = clamp(ax_range, 0.05, 0.20)

    # 3. Filter prices outside range
    price_up = central_price * (1 + ax_range)
    price_dn = central_price * (1 - ax_range)

    filtered = [p for p in outputs if price_dn < p < price_up]
```

**Reduction**: ~76% (100k → 24k per date)

**Pros**:
- ✅ Already implemented and tested
- ✅ Maintains more data during high volatility
- ✅ Proven algorithm (672 days historical validation)
- ✅ Zero additional code needed

**Cons**:
- ❌ Still 17.5M points for 730 dates (17× over budget)
- ❌ Variable points per date (23k-31k range)
- ❌ Insufficient alone for historical series

**Verdict**: **Use as Step 1** in hybrid approach, but NOT sufficient alone.

---

### Option B: Fixed Sample Rate

**Description**: Uniform downsampling across all dates

**Algorithm**:
```python
def downsample_fixed(prices: List[float], target: int) -> List[float]:
    """
    Sample every Nth point to reach target count.

    Args:
        prices: Input array (e.g., 24k points)
        target: Desired count (e.g., 1.4k points)

    Returns:
        Downsampled array
    """
    n = len(prices)
    step = n / target

    indices = [int(i * step) for i in range(target)]
    return [prices[idx] for idx in indices]
```

**Reduction**: 94% (24k → 1.4k per date)

**Pros**:
- ✅ Simple implementation (10 lines of code)
- ✅ Predictable output size
- ✅ Fast (O(n) time complexity)
- ✅ No configuration needed

**Cons**:
- ❌ Loses detail uniformly (doesn't preserve volatility spikes)
- ❌ May miss important price movements
- ❌ Fixed rate may not suit all dates equally

**Verdict**: **Good for MVP** but not optimal quality.

---

### Option C: Temporal Aggregation

**Description**: Group consecutive points into time buckets, keep min/max/avg

**Algorithm**:
```python
def downsample_temporal(
    prices: List[float],
    timestamps: List[int],
    bucket_count: int
) -> Dict[str, List]:
    """
    Aggregate points into time buckets (candlestick-style).

    Args:
        prices: Input prices (24k points)
        timestamps: Unix timestamps
        bucket_count: Number of buckets (e.g., 500)

    Returns:
        {
            "prices_min": [...],
            "prices_max": [...],
            "prices_avg": [...],
            "timestamps": [bucket_centers]
        }
    """
    # Calculate bucket size in seconds
    time_span = timestamps[-1] - timestamps[0]
    bucket_size = time_span / bucket_count

    buckets = defaultdict(list)

    # Assign each price to a bucket
    for price, ts in zip(prices, timestamps):
        bucket_idx = int((ts - timestamps[0]) / bucket_size)
        buckets[bucket_idx].append(price)

    # Aggregate each bucket
    result = {
        "prices_min": [],
        "prices_max": [],
        "prices_avg": [],
        "timestamps": []
    }

    for bucket_idx in sorted(buckets.keys()):
        bucket_prices = buckets[bucket_idx]

        result["prices_min"].append(min(bucket_prices))
        result["prices_max"].append(max(bucket_prices))
        result["prices_avg"].append(sum(bucket_prices) / len(bucket_prices))

        # Bucket center timestamp
        center_ts = timestamps[0] + (bucket_idx + 0.5) * bucket_size
        result["timestamps"].append(int(center_ts))

    return result
```

**Reduction**: Configurable (24k → 500-2000 points depending on buckets)

**Pros**:
- ✅ Preserves price extremes (min/max in each bucket)
- ✅ Maintains trend via average
- ✅ Good for visualizing volatility (candlestick-style)
- ✅ Smooth, predictable output

**Cons**:
- ❌ More complex implementation (~50 lines)
- ❌ Requires timestamp data
- ❌ 3× data per point (min, max, avg) → larger payload

**Verdict**: **Best quality**, worth complexity.

---

### Option D: Hybrid Approach (RECOMMENDED)

**Description**: Combine ax_range filtering + temporal aggregation

**Algorithm**:
```python
def downsample_hybrid(
    all_outputs: List[float],
    timestamps: List[int],
    target_per_date: int = 1370
) -> Dict[str, List]:
    """
    Two-step downsampling:
    1. Apply ax_range filter (price-based, 76% reduction)
    2. Apply temporal aggregation (time-based, 94% reduction)

    Args:
        all_outputs: All intraday outputs (~100k)
        timestamps: Unix timestamps
        target_per_date: Final point count per date

    Returns:
        Downsampled data ready for visualization
    """
    # Step 1: Price range filtering (existing algorithm)
    filtered_prices, filtered_timestamps = apply_ax_range_filter(
        all_outputs, timestamps
    )
    # Result: ~24k points

    # Step 2: Temporal aggregation
    bucket_count = target_per_date // 3  # 3 values per bucket (min/max/avg)
    downsampled = downsample_temporal(
        filtered_prices,
        filtered_timestamps,
        bucket_count
    )
    # Result: ~1.4k points (3 × 457 buckets)

    return downsampled
```

**Reduction**: 98.6% total (100k → 1.4k per date)
- Step 1: 76% (100k → 24k)
- Step 2: 94% (24k → 1.4k)

**Pros**:
- ✅ Best of both worlds: quality + performance
- ✅ Preserves volatility spikes (ax_range adapts)
- ✅ Smooth visualization (temporal aggregation)
- ✅ Configurable target size
- ✅ Reuses proven algorithm (ax_range)

**Cons**:
- ❌ Higher complexity (~100 lines total)
- ❌ Slower than fixed sampling (still <100ms per date)
- ❌ Requires both price and timestamp data

**Verdict**: **RECOMMENDED** - Best balance for production use.

---

## T212: API Design ✅

### Proposed Library API

#### Option 1: Standalone Method (RECOMMENDED)

```python
class UTXOracleCalculator:
    """Existing calculator class"""

    def downsample_for_visualization(
        self,
        prices: List[float],
        timestamps: List[int],
        heights: List[int],
        target_points: int = 1370,
        method: str = "hybrid"
    ) -> Dict[str, Any]:
        """
        Downsample intraday price data for efficient visualization.

        This method is designed for historical series visualization where
        rendering millions of points would exceed Canvas 2D performance limits.

        Args:
            prices: Intraday price evolution (post ax_range filtering)
            timestamps: Unix timestamps for each price
            heights: Block heights for each price
            target_points: Desired output size (default: 1370)
            method: Downsampling strategy:
                - "hybrid" (default): ax_range + temporal aggregation
                - "temporal": Temporal aggregation only
                - "fixed": Fixed sample rate
                - "none": No downsampling (return input)

        Returns:
            {
                "prices_min": List[float],     # Min price per bucket
                "prices_max": List[float],     # Max price per bucket
                "prices_avg": List[float],     # Avg price per bucket
                "timestamps": List[int],       # Bucket center timestamps
                "heights": List[int],          # Representative block heights
                "reduction_pct": float,        # Percentage reduced
                "method_used": str,            # Method applied
                "original_count": int,         # Input size
                "downsampled_count": int       # Output size
            }

        Example:
            >>> calc = UTXOracleCalculator()
            >>> result = calc.calculate_price_for_transactions(
            ...     transactions, return_intraday=True
            ... )
            >>>
            >>> downsampled = calc.downsample_for_visualization(
            ...     prices=result["intraday_prices"],
            ...     timestamps=result["intraday_timestamps"],
            ...     heights=result["intraday_heights"],
            ...     target_points=1000,
            ...     method="hybrid"
            ... )
            >>>
            >>> print(f"Reduced: {downsampled['reduction_pct']:.1f}%")
            Reduced: 95.8%
        """
        pass  # Implementation in Phase 3
```

**Pros**:
- ✅ Clear separation of concerns
- ✅ Reusable across different use cases
- ✅ Easy to test independently
- ✅ Opt-in (doesn't affect existing code)

**Cons**:
- ❌ Requires two method calls
- ❌ User must handle intermediate data

---

#### Option 2: Integrated Flag

```python
class UTXOracleCalculator:
    """Existing calculator class"""

    def calculate_price_for_transactions(
        self,
        transactions: List[dict],
        return_intraday: bool = False,
        downsample: bool = False,        # NEW
        downsample_target: int = 1370,   # NEW
        downsample_method: str = "hybrid" # NEW
    ) -> Dict[str, Any]:
        """
        Calculate UTXOracle price with optional downsampling.

        Args:
            transactions: Bitcoin transactions
            return_intraday: Include intraday evolution
            downsample: Apply downsampling (requires return_intraday=True)
            downsample_target: Target points for downsampling
            downsample_method: Downsampling strategy

        Returns:
            Standard result dict with optional "downsampled" key
        """
        # Existing implementation
        result = self._calculate_price(transactions)

        if return_intraday:
            result["intraday_prices"] = [...]
            result["intraday_timestamps"] = [...]

            if downsample:
                # Apply downsampling
                result["downsampled"] = self.downsample_for_visualization(
                    result["intraday_prices"],
                    result["intraday_timestamps"],
                    result["intraday_heights"],
                    target_points=downsample_target,
                    method=downsample_method
                )

        return result
```

**Pros**:
- ✅ Single method call (convenience)
- ✅ Consistent API pattern

**Cons**:
- ❌ Couples calculation with visualization concerns
- ❌ Many parameters (complexity)
- ❌ Less flexible for future use cases

**Verdict**: **Option 1** (standalone method) is cleaner architecture.

---

### FastAPI Endpoint Design

```python
# api/main.py

@app.get("/api/prices/historical-series")
async def get_historical_series(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    max_points_per_date: int = Query(1370, ge=100, le=5000),
    downsample_method: str = Query("hybrid", regex="^(hybrid|temporal|fixed|none)$")
) -> Dict[str, Any]:
    """
    Get historical price series with automatic downsampling.

    Returns:
        {
            "dates": ["2023-01-01", ...],
            "data_by_date": {
                "2023-01-01": {
                    "prices_min": [...],
                    "prices_max": [...],
                    "prices_avg": [...],
                    "timestamps": [...],
                    "consensus_price": 16500.25
                },
                ...
            },
            "metadata": {
                "total_dates": 730,
                "total_points": 1000300,
                "avg_points_per_date": 1370,
                "downsample_method": "hybrid",
                "file_size_bytes": 3670000
            }
        }

    Example:
        GET /api/prices/historical-series?start_date=2023-01-01&end_date=2025-10-31
    """
    # 1. Query DuckDB for date range
    dates = query_dates_between(start_date, end_date)

    # 2. For each date, fetch intraday data and downsample
    calc = UTXOracleCalculator()
    result = {}

    for date in dates:
        transactions = fetch_transactions_for_date(date)

        # Calculate price with intraday data
        price_result = calc.calculate_price_for_transactions(
            transactions, return_intraday=True
        )

        # Downsample for visualization
        downsampled = calc.downsample_for_visualization(
            prices=price_result["intraday_prices"],
            timestamps=price_result["intraday_timestamps"],
            heights=price_result["intraday_heights"],
            target_points=max_points_per_date,
            method=downsample_method
        )

        result[date] = {
            **downsampled,
            "consensus_price": price_result["price_usd"]
        }

    # 3. Calculate metadata
    total_points = sum(len(d["prices_avg"]) for d in result.values())

    return {
        "dates": list(result.keys()),
        "data_by_date": result,
        "metadata": {
            "total_dates": len(dates),
            "total_points": total_points,
            "avg_points_per_date": total_points // len(dates),
            "downsample_method": downsample_method,
            "file_size_estimate_bytes": estimate_json_size(result)
        }
    }
```

---

## Implementation Strategy

### Phase 3: Proof of Concept (Next Phase)

**T213**: Implement `downsample_for_visualization()` method
- Start with Option B (Fixed Sample Rate) as MVP
- 50 lines of code, minimal complexity
- Validate on 5 random dates

**T214**: Test on full 2023-2025 series
- Generate 730-date series
- Measure performance, file size, quality

**T215**: Implement Option D (Hybrid) if MVP insufficient
- Add temporal aggregation layer
- Benchmark against fixed sampling

**T216**: Define "good enough" thresholds
- Correlation > 0.99 with original?
- Max spike detection rate?

### Phase 4: Integration (After POC)

**T217**: FastAPI endpoint implementation
**T218**: Caching strategy (Redis or DuckDB materialized view)
**T219**: Frontend Canvas 2D rendering
**T220**: Progressive loading (optional)

---

## Decision Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Rendering Tech** | Canvas 2D | KISS, zero deps, already implemented |
| **Downsampling Strategy** | Hybrid (ax_range + temporal) | Best quality/performance balance |
| **Target Points/Date** | 1,370 | 1M total (Canvas limit), 3.5MB file |
| **API Pattern** | Standalone method | Clean separation, reusable |
| **MVP Strategy** | Fixed sampling first | Fast implementation, validates pipeline |
| **Production Strategy** | Hybrid approach | Upgrade after MVP validation |

---

## Next Steps

**Ready for Phase 3** (T213-T216):
1. Implement `downsample_for_visualization()` method
2. Start with Option B (Fixed Sample Rate) for quick MVP
3. Test on 5 dates → measure reduction, quality, performance
4. Generate full 730-date series → validate Canvas 2D rendering
5. Upgrade to Option D (Hybrid) if quality insufficient

**Estimated Time**: 3-4 hours implementation + testing

---

## References

- Phase 1 Findings: `docs/DOWNSAMPLING_ANALYSIS_FINDINGS.md`
- TODO Plan: `docs/DOWNSAMPLING_ANALYSIS_TODO.md`
- UTXOracle Reference: `UTXOracle.py` lines 1344-1411
- Library Code: `UTXOracle_library.py`

---

**Tasks Complete**:
- ✅ **T206**: Use cases defined (single-date, historical series, real-time)
- ✅ **T207**: Data sizes calculated (17.5M → 1.0M points target)
- ✅ **T208**: Adaptive price range strategy analyzed
- ✅ **T209**: Fixed sample rate strategy designed
- ✅ **T210**: Temporal aggregation strategy designed
- ✅ **T211**: Hybrid approach strategy designed (RECOMMENDED)
- ✅ **T212**: API design complete (standalone method + FastAPI endpoint)

**Phase 2 Status**: ✅ COMPLETE

**Next**: Phase 3 Implementation (T213-T216)
