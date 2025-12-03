#!/usr/bin/env python3
"""
Rigorous convergence test: HTML (reference) vs DuckDB (library).

Since UTXOracle_library.py was extracted from UTXOracle.py, they MUST produce
identical results on the same date. This test verifies that extraction is correct.

Tolerance: <0.01% difference (essentially identical)
"""

import os
import re
from pathlib import Path
import duckdb
from typing import Optional, Tuple


def parse_html_price(html_path: Path) -> Optional[float]:
    """
    Extract price from UTXOracle HTML file.

    Uses EXACT SAME logic as import_historical_data.py (lines 66-81)

    Args:
        html_path: Path to HTML file

    Returns:
        Price in USD, or None if not found
    """
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract final price (from convergence algorithm Step 9)
        # UTXOracle.py displays the final price as "$XXX,XXX" once in the HTML
        # This is more accurate than averaging intraday prices
        price_match = re.search(r"\$([0-9,]{5,8})", content)
        if not price_match:
            return None

        price_str = price_match.group(1).replace(",", "")
        try:
            price = float(price_str)
        except ValueError:
            return None

        # Validate price is in reasonable range
        if not (10000 <= price <= 500000):
            return None

        return price

    except Exception as e:
        print(f"Error parsing HTML {html_path}: {e}")
        return None


def query_duckdb_price(db_path: str, date_str: str) -> Optional[Tuple[float, float]]:
    """
    Query DuckDB for price on specific date.

    Args:
        db_path: Path to DuckDB database
        date_str: Date in format "YYYY-MM-DD"

    Returns:
        (utxoracle_price, confidence) tuple, or None if not found
    """
    try:
        conn = duckdb.connect(db_path, read_only=True)
        result = conn.execute(
            """
            SELECT utxoracle_price, confidence
            FROM price_analysis
            WHERE date = ?
        """,
            [date_str],
        ).fetchone()

        conn.close()

        if result:
            price, confidence = result
            return float(price), float(confidence)
        return None

    except Exception as e:
        print(f"Error querying DuckDB: {e}")
        return None


def html_date_to_db_date(html_filename: str) -> Optional[str]:
    """
    Convert HTML filename to DuckDB date format.

    Args:
        html_filename: e.g., "UTXOracle_2025-10-15.html"

    Returns:
        Date string "YYYY-MM-DD" or None
    """
    # Pattern: UTXOracle_YYYY-MM-DD.html
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", html_filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None


def test_single_date(html_path: Path, db_path: str) -> dict:
    """
    Test a single date: compare HTML (reference) vs DuckDB (library).

    Args:
        html_path: Path to HTML file
        db_path: Path to DuckDB database

    Returns:
        dict with test results
    """
    # Extract date from filename
    date_str = html_date_to_db_date(html_path.name)
    if not date_str:
        return {
            "status": "ERROR",
            "message": f"Could not parse date from filename: {html_path.name}",
        }

    # Parse HTML price
    html_price = parse_html_price(html_path)
    if html_price is None:
        return {
            "status": "ERROR",
            "date": date_str,
            "message": "Could not extract price from HTML",
        }

    # Query DuckDB
    db_result = query_duckdb_price(db_path, date_str)
    if db_result is None:
        return {
            "status": "MISSING",
            "date": date_str,
            "html_price": html_price,
            "message": "Date not found in DuckDB",
        }

    db_price, confidence = db_result

    # Compare
    diff = abs(html_price - db_price)
    diff_pct = (diff / html_price) * 100 if html_price > 0 else 0

    # Verdict
    TOLERANCE = 0.01  # 0.01% = essentially identical
    status = "PASS" if diff_pct < TOLERANCE else "FAIL"

    return {
        "status": status,
        "date": date_str,
        "html_price": html_price,
        "db_price": db_price,
        "confidence": confidence,
        "diff": diff,
        "diff_pct": diff_pct,
    }


def main():
    print("=" * 80)
    print("RIGOROUS CONVERGENCE TEST: HTML (Reference) vs DuckDB (Library)")
    print("=" * 80)

    # Paths
    html_dir = Path("historical_data/html_files")
    db_path = os.getenv(
        "DUCKDB_PATH", "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
    )

    print(f"\nHTML directory: {html_dir}")
    print(f"DuckDB path:    {db_path}")

    if not html_dir.exists():
        print(f"\n❌ ERROR: HTML directory not found: {html_dir}")
        return 1

    if not Path(db_path).exists():
        print(f"\n❌ ERROR: DuckDB not found: {db_path}")
        return 1

    # Get all HTML files
    html_files = sorted(html_dir.glob("UTXOracle_*.html"))
    print(f"\nFound {len(html_files)} HTML files")

    # Test recent files (last 30 days)
    print("\n" + "=" * 80)
    print("Testing Recent Dates (Last 30 files)")
    print("=" * 80)

    recent_files = html_files[-30:] if len(html_files) > 30 else html_files

    results = []
    for html_path in recent_files:
        result = test_single_date(html_path, db_path)
        results.append(result)

    # Summary
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)

    passed = [r for r in results if r["status"] == "PASS"]
    failed = [r for r in results if r["status"] == "FAIL"]
    missing = [r for r in results if r["status"] == "MISSING"]
    errors = [r for r in results if r["status"] == "ERROR"]

    print(f"\nTested: {len(results)} dates")
    print(f"  ✅ PASS:    {len(passed)}")
    print(f"  ❌ FAIL:    {len(failed)}")
    print(f"  ⚠️  MISSING: {len(missing)}")
    print(f"  🚫 ERROR:   {len(errors)}")

    # Show failures
    if failed:
        print("\n" + "=" * 80)
        print("FAILURES (Prices DO NOT match!)")
        print("=" * 80)

        for result in failed:
            print(f"\n{result['date']}:")
            print(f"  HTML (reference): ${result['html_price']:,.2f}")
            print(f"  DuckDB (library): ${result['db_price']:,.2f}")
            print(
                f"  Difference:       ${result['diff']:,.2f} ({result['diff_pct']:.4f}%)"
            )

    # Show a few passes
    if passed:
        print("\n" + "=" * 80)
        print("SAMPLE PASSES (First 5)")
        print("=" * 80)

        for result in passed[:5]:
            print(f"\n{result['date']}:")
            print(f"  HTML:       ${result['html_price']:,.2f}")
            print(f"  DuckDB:     ${result['db_price']:,.2f}")
            print(f"  Difference: ${result['diff']:,.2f} ({result['diff_pct']:.6f}%)")
            print("  ✅ PASS")

    # Verdict
    print("\n" + "=" * 80)
    print("VERDICT")
    print("=" * 80)

    if failed:
        print("\n❌ TEST FAILED")
        print(f"   {len(failed)} dates have prices that DO NOT match!")
        print("   Library extraction is INCORRECT.")
        return 1
    elif len(passed) == 0:
        print("\n⚠️  TEST INCONCLUSIVE")
        print("   No matching dates found in DuckDB.")
        print("   Run daily_analysis.py to populate database.")
        return 2
    else:
        print("\n✅ TEST PASSED!")
        print(f"   All {len(passed)} dates match within 0.01% tolerance.")
        print("   Library extraction is CORRECT.")
        return 0


if __name__ == "__main__":
    exit(main())
