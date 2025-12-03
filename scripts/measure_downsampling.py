#!/usr/bin/env python3
"""
Measure Downsampling: Quantify data reduction in UTXOracle.py HTML generation

This script analyzes HTML files to understand the downsampling mechanism:
- Extracts total intraday outputs (pre-filtering)
- Counts filtered prices for chart (post-filtering)
- Calculates reduction percentage
- Analyzes ax_range values and volatility relationship

Usage:
    python3 scripts/measure_downsampling.py --date 2025-10-24
    python3 scripts/measure_downsampling.py --samples 10
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional


def parse_html_downsampling_data(html_path: Path) -> Optional[Dict]:
    """
    Extract downsampling metrics from UTXOracle HTML file.

    Returns:
        dict with keys:
            - date: Date string
            - total_outputs: Total intraday price outputs (pre-filter)
            - filtered_prices: Number of prices in chart (post-filter)
            - reduction_pct: Percentage of data removed
            - ax_range: Dynamic range used (5-20%)
            - price_range: Min-Max price range
            - central_price: Consensus price
    """
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract date from filename
        match = re.search(r"UTXOracle_(\\d{4}-\\d{2}-\\d{2})\\.html", html_path.name)
        if not match:
            return None
        date_str = match.group(1)

        # Extract consensus price from title
        title_match = re.search(r"UTXOracle Consensus Price \\$([0-9,]+)", content)
        if not title_match:
            return None
        central_price = float(title_match.group(1).replace(",", ""))

        # Extract filtered prices array (chart data)
        prices_match = re.search(r"const prices = \\[([0-9., ]+)\\]", content)
        if not prices_match:
            return None
        prices_str = prices_match.group(1)
        filtered_prices = [float(p.strip()) for p in prices_str.split(",") if p.strip()]
        filtered_count = len(filtered_prices)

        # Calculate price range from filtered data
        if filtered_prices:
            price_min = min(filtered_prices)
            price_max = max(filtered_prices)
            price_range_span = price_max - price_min
        else:
            price_min = price_max = price_range_span = 0

        # Try to find total outputs count
        # This might be in a comment or we estimate from blocks
        heights_match = re.search(r"const heights = \\[([0-9, ]+)\\]", content)
        if heights_match:
            heights_str = heights_match.group(1)
            heights = [int(h.strip()) for h in heights_str.split(",") if h.strip()]
            # Heights array length matches filtered_prices length
            # We need to estimate total outputs differently

            # The total outputs would be ~144 blocks * ~600 outputs/block ≈ 86k
            # But we can calculate from the price range and ax_range
            # ax_range = (price_max - price_min) / (2 * central_price)
            if central_price > 0 and price_range_span > 0:
                ax_range = price_range_span / (2 * central_price)
            else:
                ax_range = 0

            # Estimate total outputs (rough approximation)
            # Typically ~100k outputs for 144 blocks
            block_count = len(set(heights))
            estimated_total = block_count * 700  # Rough average

            reduction_pct = (
                ((estimated_total - filtered_count) / estimated_total) * 100
                if estimated_total > 0
                else 0
            )
        else:
            ax_range = 0
            estimated_total = 0
            reduction_pct = 0

        return {
            "date": date_str,
            "total_outputs": estimated_total,
            "filtered_prices": filtered_count,
            "reduction_pct": reduction_pct,
            "ax_range": ax_range,
            "price_range": price_range_span,
            "price_min": price_min,
            "price_max": price_max,
            "central_price": central_price,
            "block_count": len(set(heights)) if heights_match else 0,
        }

    except Exception as e:
        print(f"Error parsing {html_path}: {e}", file=sys.stderr)
        return None


def analyze_single_date(html_path: Path) -> None:
    """Analyze and print downsampling metrics for a single date."""
    data = parse_html_downsampling_data(html_path)

    if not data:
        print(f"❌ Could not parse {html_path.name}")
        return

    print(f"\\n{'=' * 70}")
    print(f"Date: {data['date']}")
    print(f"{'=' * 70}")
    print(f"Consensus Price: ${data['central_price']:,.2f}")
    print(f"Price Range: ${data['price_min']:,.2f} - ${data['price_max']:,.2f}")
    print(
        f"Range Span: ${data['price_range']:,.2f} ({data['price_range'] / data['central_price'] * 100:.2f}%)"
    )
    print("\\nData Points:")
    print(f"  Estimated Total Outputs: {data['total_outputs']:,}")
    print(f"  Filtered for Chart: {data['filtered_prices']:,}")
    print(f"  Reduction: {data['reduction_pct']:.1f}%")
    print("\\nDynamic Range:")
    print(f"  ax_range: {data['ax_range']:.3f} (±{data['ax_range'] * 100:.1f}%)")
    print(f"  Blocks Processed: {data['block_count']}")


def analyze_multiple_dates(html_files: List[Path]) -> None:
    """Analyze downsampling across multiple dates and show statistics."""
    results = []

    for html_file in html_files:
        data = parse_html_downsampling_data(html_file)
        if data:
            results.append(data)

    if not results:
        print("❌ No valid results")
        return

    # Summary statistics
    print(f"\\n{'=' * 70}")
    print(f"SUMMARY: {len(results)} dates analyzed")
    print(f"{'=' * 70}")

    avg_reduction = sum(r["reduction_pct"] for r in results) / len(results)
    min_reduction = min(r["reduction_pct"] for r in results)
    max_reduction = max(r["reduction_pct"] for r in results)

    avg_filtered = sum(r["filtered_prices"] for r in results) / len(results)
    min_filtered = min(r["filtered_prices"] for r in results)
    max_filtered = max(r["filtered_prices"] for r in results)

    avg_ax_range = sum(r["ax_range"] for r in results) / len(results)
    min_ax_range = min(r["ax_range"] for r in results)
    max_ax_range = max(r["ax_range"] for r in results)

    print("\\nReduction Percentage:")
    print(f"  Average: {avg_reduction:.1f}%")
    print(f"  Range: {min_reduction:.1f}% - {max_reduction:.1f}%")

    print("\\nFiltered Data Points:")
    print(f"  Average: {avg_filtered:,.0f}")
    print(f"  Range: {min_filtered:,} - {max_filtered:,}")

    print("\\nDynamic Range (ax_range):")
    print(f"  Average: {avg_ax_range:.3f} (±{avg_ax_range * 100:.1f}%)")
    print(f"  Range: {min_ax_range:.3f} - {max_ax_range:.3f}")

    # Show extremes
    print(f"\\n{'=' * 70}")
    print("EXTREMES:")
    print(f"{'=' * 70}")

    lowest = min(results, key=lambda r: r["reduction_pct"])
    print(f"\\nLowest Reduction: {lowest['date']}")
    print(f"  Reduction: {lowest['reduction_pct']:.1f}%")
    print(f"  Filtered Points: {lowest['filtered_prices']:,}")
    print(f"  ax_range: {lowest['ax_range']:.3f}")

    highest = max(results, key=lambda r: r["reduction_pct"])
    print(f"\\nHighest Reduction: {highest['date']}")
    print(f"  Reduction: {highest['reduction_pct']:.1f}%")
    print(f"  Filtered Points: {highest['filtered_prices']:,}")
    print(f"  ax_range: {highest['ax_range']:.3f}")

    # Volatility correlation
    print(f"\\n{'=' * 70}")
    print("VOLATILITY CORRELATION:")
    print(f"{'=' * 70}")

    # Sort by ax_range to show volatility relationship
    sorted_by_range = sorted(results, key=lambda r: r["ax_range"])
    print("\\nLow Volatility (smallest ax_range):")
    for r in sorted_by_range[:3]:
        print(
            f"  {r['date']}: ax_range={r['ax_range']:.3f}, "
            f"filtered={r['filtered_prices']:,}, reduction={r['reduction_pct']:.1f}%"
        )

    print("\\nHigh Volatility (largest ax_range):")
    for r in sorted_by_range[-3:]:
        print(
            f"  {r['date']}: ax_range={r['ax_range']:.3f}, "
            f"filtered={r['filtered_prices']:,}, reduction={r['reduction_pct']:.1f}%"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Measure downsampling in UTXOracle HTML files"
    )
    parser.add_argument(
        "--date", type=str, help="Analyze specific date (YYYY-MM-DD)", default=None
    )
    parser.add_argument(
        "--samples",
        type=int,
        help="Analyze N random samples",
        default=None,
    )
    args = parser.parse_args()

    # Find HTML files
    project_root = Path(__file__).parent.parent
    html_dir = project_root / "historical_data" / "html_files"

    if not html_dir.exists():
        print(f"❌ HTML directory not found: {html_dir}", file=sys.stderr)
        sys.exit(1)

    html_files = sorted(html_dir.glob("UTXOracle_*.html"))
    if not html_files:
        print(f"❌ No HTML files found in {html_dir}", file=sys.stderr)
        sys.exit(1)

    # Select files to analyze
    if args.date:
        target_file = html_dir / f"UTXOracle_{args.date}.html"
        if not target_file.exists():
            print(f"❌ HTML file not found: {target_file}", file=sys.stderr)
            sys.exit(1)
        analyze_single_date(target_file)
    elif args.samples:
        import random

        sample_files = random.sample(html_files, min(args.samples, len(html_files)))
        analyze_multiple_dates(sample_files)
    else:
        # Default: analyze 10 random samples
        import random

        sample_files = random.sample(html_files, min(10, len(html_files)))
        analyze_multiple_dates(sample_files)


if __name__ == "__main__":
    main()
