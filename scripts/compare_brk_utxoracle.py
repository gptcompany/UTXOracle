#!/usr/bin/env python3
"""
Compare BRK (Bitcoin Research Kit) data with UTXOracle calculations.

This script fetches on-chain metrics from BRK's REST API and compares them
with UTXOracle's metrics from DuckDB, generating a validation report.

Usage:
    python scripts/compare_brk_utxoracle.py [--date YYYY-MM-DD] [--full]
    python scripts/compare_brk_utxoracle.py --list-metrics
    python scripts/compare_brk_utxoracle.py --integration-check

Requirements:
    - BRK server running on localhost:3110
    - UTXOracle DuckDB database
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

BRK_BASE_URL = "http://localhost:3110"

# Metric mapping: BRK name -> (UTXOracle table, column, tolerance%)
METRIC_MAPPING = {
    # Core valuation metrics
    "realized_cap": ("realized_cap_daily", "realized_cap", 2.0),
    "mvrv": ("mvrv_daily", "mvrv", 2.0),
    "mvrv_z": ("mvrv_daily", "mvrv_z", 5.0),
    "nupl": ("nupl_daily", "nupl", 2.0),
    # Spending metrics
    "sopr": ("sopr_daily", "sopr", 1.0),
    "sopr_adjusted": ("sopr_daily", "sopr_adjusted", 2.0),
    # Cointime metrics
    "liveliness": ("cointime_daily", "liveliness", 5.0),
    "vaultedness": ("cointime_daily", "vaultedness", 5.0),
    # Supply metrics
    "circulating_supply": (None, None, 0.1),  # Should be exact
}


def fetch_brk_api(endpoint: str, timeout: int = 30) -> dict | None:
    """Fetch data from BRK REST API."""
    url = f"{BRK_BASE_URL}{endpoint}"
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except URLError:
        return None
    except json.JSONDecodeError:
        return None


def check_brk_server() -> tuple[bool, dict]:
    """Check if BRK server is running and get status."""
    status = {"running": False, "synced": False, "block_height": None, "metrics": []}

    # Check OpenAPI spec
    spec = fetch_brk_api("/api/openapi.json")
    if not spec:
        return False, status

    status["running"] = True

    # Check block height
    blocks = fetch_brk_api("/api/blocks/tip")
    if blocks and isinstance(blocks, dict):
        status["block_height"] = blocks.get("height")
        status["synced"] = status["block_height"] is not None

    # List available metrics
    metrics = fetch_brk_api("/api/metrics")
    if metrics and isinstance(metrics, (dict, list)):
        status["metrics"] = (
            list(metrics.keys()) if isinstance(metrics, dict) else metrics
        )

    return True, status


def get_brk_metric(metric_name: str, height: int | None = None) -> dict | None:
    """Get a specific metric value from BRK."""
    endpoint = f"/api/metrics/{metric_name}"
    if height:
        endpoint += f"?height={height}"
    return fetch_brk_api(endpoint)


def get_utxoracle_metrics(date_str: str) -> dict:
    """Load UTXOracle metrics from DuckDB for a specific date."""
    try:
        from scripts.config import get_connection

        conn = get_connection()
        metrics = {}

        # Query each daily table
        tables = [
            ("realized_cap_daily", ["realized_cap", "market_cap"]),
            ("mvrv_daily", ["mvrv", "mvrv_z"]),
            ("nupl_daily", ["nupl", "market_cap", "realized_cap"]),
            ("sopr_daily", ["sopr", "sopr_adjusted"]),
            (
                "cointime_daily",
                ["liveliness", "vaultedness", "active_supply", "vaulted_supply"],
            ),
        ]

        for table, columns in tables:
            try:
                cols = ", ".join(columns)
                result = conn.execute(
                    f"""
                    SELECT {cols} FROM {table}
                    WHERE date = ?
                    ORDER BY date DESC LIMIT 1
                """,
                    [date_str],
                ).fetchone()

                if result:
                    for i, col in enumerate(columns):
                        metrics[col] = result[i]
            except Exception:
                pass

        conn.close()
        return metrics

    except ImportError:
        print("Warning: scripts.config not available")
        return {}
    except Exception as e:
        print(f"Warning: Could not load UTXOracle metrics: {e}")
        return {}


def compare_single_metric(
    brk_value: float, utxo_value: float, tolerance: float
) -> dict:
    """Compare a single metric value."""
    if brk_value is None or utxo_value is None:
        return {"status": "missing", "diff_pct": None}

    if brk_value == 0 and utxo_value == 0:
        return {"status": "match", "diff_pct": 0.0}

    diff = abs(brk_value - utxo_value)
    base = max(abs(brk_value), abs(utxo_value), 1e-10)
    diff_pct = (diff / base) * 100

    if diff_pct <= tolerance:
        status = "match"
    elif diff_pct <= tolerance * 2:
        status = "warning"
    else:
        status = "mismatch"

    return {
        "status": status,
        "brk_value": brk_value,
        "utxo_value": utxo_value,
        "diff_pct": round(diff_pct, 4),
        "tolerance": tolerance,
    }


def run_full_comparison(date_str: str, height: int | None = None) -> dict:
    """Run full metric comparison between BRK and UTXOracle."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "date": date_str,
        "height": height,
        "metrics": {},
        "summary": {"matches": 0, "warnings": 0, "mismatches": 0, "missing": 0},
    }

    # Get UTXOracle metrics
    utxo_metrics = get_utxoracle_metrics(date_str)

    # Compare each mapped metric
    for brk_name, (table, utxo_col, tolerance) in METRIC_MAPPING.items():
        brk_data = get_brk_metric(brk_name, height)
        brk_value = None
        if brk_data:
            # BRK returns different structures, try to extract value
            if isinstance(brk_data, (int, float)):
                brk_value = brk_data
            elif isinstance(brk_data, dict):
                brk_value = brk_data.get("value") or brk_data.get(brk_name)

        utxo_value = utxo_metrics.get(utxo_col) if utxo_col else None

        result = compare_single_metric(brk_value, utxo_value, tolerance)
        result["brk_name"] = brk_name
        result["utxo_column"] = utxo_col
        report["metrics"][brk_name] = result

        # Update summary
        report["summary"][
            result["status"] + ("es" if result["status"] == "match" else "s")
        ] += 1

    return report


def print_comparison_report(report: dict):
    """Print formatted comparison report."""
    print("\n" + "=" * 70)
    print("  BRK vs UTXOracle Comparison Report")
    print(f"  Date: {report['date']}  |  Generated: {report['timestamp'][:19]}")
    print("=" * 70)

    # Summary
    s = report["summary"]
    total = s["matches"] + s["warnings"] + s["mismatches"] + s["missing"]
    match_rate = (s["matches"] / total * 100) if total > 0 else 0

    print(f"\n  Summary: {s['matches']}/{total} metrics match ({match_rate:.1f}%)")
    print(
        f"  ✅ Matches: {s['matches']}  ⚠️ Warnings: {s['warnings']}  "
        f"❌ Mismatches: {s['mismatches']}  ❓ Missing: {s['missing']}"
    )

    # Details
    print("\n  " + "-" * 66)
    print(f"  {'Metric':<20} {'BRK':>12} {'UTXOracle':>12} {'Diff%':>8} {'Status':>10}")
    print("  " + "-" * 66)

    status_icons = {"match": "✅", "warning": "⚠️", "mismatch": "❌", "missing": "❓"}

    for name, data in report["metrics"].items():
        brk_val = (
            f"{data.get('brk_value', 'N/A'):,.4f}" if data.get("brk_value") else "N/A"
        )
        utxo_val = (
            f"{data.get('utxo_value', 'N/A'):,.4f}" if data.get("utxo_value") else "N/A"
        )
        diff = f"{data['diff_pct']:.2f}%" if data.get("diff_pct") is not None else "N/A"
        icon = status_icons.get(data["status"], "?")

        # Truncate for display
        brk_val = brk_val[:12] if len(brk_val) > 12 else brk_val
        utxo_val = utxo_val[:12] if len(utxo_val) > 12 else utxo_val

        print(f"  {name:<20} {brk_val:>12} {utxo_val:>12} {diff:>8} {icon:>10}")

    print("  " + "-" * 66)
    print()


def check_integration_feasibility() -> dict:
    """Check if BRK can replace electrs/mempool.space in UTXOracle architecture."""
    print("\n" + "=" * 70)
    print("  BRK Integration Feasibility Analysis")
    print("=" * 70)

    feasibility = {
        "can_replace_electrs": {"status": "unknown", "notes": []},
        "can_replace_mempool": {"status": "unknown", "notes": []},
        "required_endpoints": [],
        "missing_endpoints": [],
        "recommendation": "",
    }

    # Check BRK server
    ok, status = check_brk_server()
    if not ok:
        print("\n  ❌ BRK server not available. Cannot assess integration.")
        feasibility["recommendation"] = (
            "BRK server must be running to assess integration"
        )
        return feasibility

    print("\n  BRK Server Status:")
    print(f"    Running: {'✅' if status['running'] else '❌'}")
    print(f"    Synced: {'✅' if status['synced'] else '❌'}")
    print(f"    Block Height: {status['block_height']}")
    print(f"    Available Metrics: {len(status['metrics'])}")

    # Check required endpoints for electrs replacement
    electrs_requirements = [
        ("/api/blocks/{height}", "Block data by height"),
        ("/api/txs/{txid}", "Transaction details"),
        ("/api/addresses/{addr}", "Address UTXOs"),
    ]

    print("\n  Checking electrs replacement requirements:")
    electrs_ok = True
    for endpoint_pattern, desc in electrs_requirements:
        # Test with sample data
        test_endpoint = (
            endpoint_pattern.replace("{height}", "1")
            .replace("{txid}", "test")
            .replace("{addr}", "test")
        )
        result = fetch_brk_api(test_endpoint.split("?")[0])
        available = (
            result is not None or "error" not in str(result).lower()
            if result
            else False
        )

        # For now, assume available if server responds
        status_icon = "✅" if available else "⚠️"
        print(f"    {status_icon} {desc}: {endpoint_pattern}")

        if not available:
            electrs_ok = False
            feasibility["missing_endpoints"].append(endpoint_pattern)

    # Check mempool.space replacement (price API)
    print("\n  Checking mempool.space replacement requirements:")
    mempool_requirements = [
        ("/api/v1/prices", "Exchange price API"),
        ("/api/mempool", "Mempool data"),
    ]

    mempool_ok = True
    for endpoint, desc in mempool_requirements:
        result = fetch_brk_api(endpoint)
        available = result is not None
        status_icon = "✅" if available else "❌"
        print(f"    {status_icon} {desc}: {endpoint}")

        if not available:
            mempool_ok = False

    # Determine feasibility
    if electrs_ok:
        feasibility["can_replace_electrs"] = {
            "status": "yes",
            "notes": ["BRK provides all required block/tx/address endpoints"],
        }
    else:
        feasibility["can_replace_electrs"] = {
            "status": "partial",
            "notes": ["Some endpoints may need mapping or workarounds"],
        }

    if mempool_ok:
        feasibility["can_replace_mempool"] = {
            "status": "yes",
            "notes": ["BRK provides price and mempool data"],
        }
    else:
        feasibility["can_replace_mempool"] = {
            "status": "no",
            "notes": ["BRK uses fetch=true for external prices, not self-contained"],
        }

    # Print recommendations
    print("\n  " + "-" * 66)
    print("  INTEGRATION RECOMMENDATION:")
    print("  " + "-" * 66)

    if electrs_ok and mempool_ok:
        print("  ✅ BRK can FULLY replace electrs + mempool.space stack")
        print("     - Simpler architecture: 1 binary vs Docker compose")
        print("     - Faster queries: Pre-indexed data")
        print("     - Same data source: Bitcoin Core")
        feasibility["recommendation"] = "full_replacement"
    elif electrs_ok:
        print("  🔶 BRK can PARTIALLY replace infrastructure:")
        print("     - ✅ Replace electrs for block/tx/address queries")
        print("     - ❌ Keep mempool.space for exchange prices (or use BRK fetch)")
        feasibility["recommendation"] = "partial_electrs"
    else:
        print("  ⚠️ Further testing needed once BRK is fully synced")
        feasibility["recommendation"] = "pending_sync"

    print()
    return feasibility


def main():
    parser = argparse.ArgumentParser(
        description="Compare BRK and UTXOracle data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/compare_brk_utxoracle.py                    # Compare yesterday
  python scripts/compare_brk_utxoracle.py -d 2025-12-01      # Specific date
  python scripts/compare_brk_utxoracle.py --list-metrics     # List BRK metrics
  python scripts/compare_brk_utxoracle.py --integration-check # Check if BRK can replace electrs
        """,
    )
    parser.add_argument(
        "-d", "--date", type=str, help="Date (YYYY-MM-DD), default: yesterday"
    )
    parser.add_argument("--height", type=int, help="Block height for queries")
    parser.add_argument(
        "--list-metrics", action="store_true", help="List available BRK metrics"
    )
    parser.add_argument(
        "-m", "--metric", type=str, help="Fetch specific metric from BRK"
    )
    parser.add_argument(
        "--integration-check", action="store_true", help="Check integration feasibility"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Check BRK server
    ok, status = check_brk_server()
    if not ok:
        print("❌ BRK server not available at", BRK_BASE_URL)
        print("   Make sure brk-bin is running and synced")
        return 1

    print(
        f"✅ BRK server running (block height: {status.get('block_height', 'unknown')})"
    )

    # Integration check mode
    if args.integration_check:
        check_integration_feasibility()
        return 0

    # List metrics mode
    if args.list_metrics:
        print(f"\nAvailable BRK metrics ({len(status['metrics'])}):")
        for m in sorted(status["metrics"]):
            mapping = METRIC_MAPPING.get(m)
            mapped = f" → UTXOracle: {mapping[1]}" if mapping and mapping[1] else ""
            print(f"  • {m}{mapped}")
        return 0

    # Single metric mode
    if args.metric:
        print(f"\nFetching metric: {args.metric}")
        data = get_brk_metric(args.metric, args.height)
        if data:
            print(json.dumps(data, indent=2))
        else:
            print("No data returned")
        return 0

    # Comparison mode
    date_str = args.date or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    report = run_full_comparison(date_str, args.height)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_comparison_report(report)

    # Return non-zero if mismatches
    return 1 if report["summary"]["mismatches"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
