#!/usr/bin/env python3
"""
UTXOracle + Mempool.space Integration Script

Hybrid approach: Use mempool backend for infrastructure,
UTXOracle.py for on-chain price calculation.

Usage:
    python3 utxoracle_mempool_integration.py 2025-10-23
    python3 utxoracle_mempool_integration.py --recent-blocks
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Paths
UTXORACLE_PATH = Path(__file__).parent.parent / "UTXOracle.py"


def calculate_price_with_utxoracle(
    date_str: str = None, recent_blocks: bool = False
) -> dict:
    """
    Run UTXOracle.py for the given date or recent blocks.

    Args:
        date_str: Date in format "YYYY-MM-DD" (e.g., "2025-10-23")
        recent_blocks: If True, use last 144 blocks instead of date

    Returns:
        dict with keys: price, date, success, output
    """
    cmd = ["python3", str(UTXORACLE_PATH), "--no-browser"]

    if recent_blocks:
        cmd.append("-rb")
    elif date_str:
        # Convert to UTXOracle format: YYYY/MM/DD
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        utxoracle_date = date_obj.strftime("%Y/%m/%d")
        cmd.extend(["-d", utxoracle_date])
    else:
        raise ValueError("Must specify either date_str or recent_blocks=True")

    print(f"🔄 Running UTXOracle: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            check=True,
        )

        # Parse output: "2025-10-24 price: $123,456"
        price = None
        parsed_date = None

        for line in result.stdout.split("\n"):
            if "price:" in line:
                # Extract date and price
                parts = line.split()
                if len(parts) >= 3:
                    parsed_date = parts[0]
                    price_str = parts[2].replace("$", "").replace(",", "")
                    try:
                        price = float(price_str)
                    except ValueError:
                        continue

        if price is None:
            return {
                "success": False,
                "error": "Could not parse price from UTXOracle output",
                "output": result.stdout,
            }

        return {
            "success": True,
            "price": price,
            "date": parsed_date or date_str,
            "output": result.stdout,
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "UTXOracle timed out after 5 minutes"}
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"UTXOracle failed with exit code {e.returncode}",
            "stderr": e.stderr,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 utxoracle_mempool_integration.py 2025-10-23")
        print("  python3 utxoracle_mempool_integration.py --recent-blocks")
        sys.exit(1)

    # Parse arguments
    if sys.argv[1] == "--recent-blocks" or sys.argv[1] == "-rb":
        result = calculate_price_with_utxoracle(recent_blocks=True)
    else:
        date_str = sys.argv[1]
        result = calculate_price_with_utxoracle(date_str=date_str)

    # Display result
    print()
    print("=" * 60)
    if result["success"]:
        print("✅ UTXOracle On-Chain Price Calculation")
        print(f"   Date: {result['date']}")
        print(f"   Price: ${result['price']:,.2f}")
        print()
        print("📊 This price is calculated purely from on-chain transaction data")
        print("   using statistical clustering (UTXOracle algorithm).")
        print()
        print("💡 Compare with mempool.space exchange price:")
        print("   curl http://localhost:8999/api/v1/prices | jq .USD")
    else:
        print("❌ Failed to calculate price")
        print(f"   Error: {result.get('error', 'Unknown error')}")
        if "stderr" in result:
            print(f"   Details: {result['stderr']}")
    print("=" * 60)

    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
