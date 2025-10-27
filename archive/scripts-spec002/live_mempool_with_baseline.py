#!/usr/bin/env python3
"""
Real-Time Mempool Streaming + UTXOracle Baseline

Connects to self-hosted mempool.space WebSocket for real-time data,
updates UTXOracle on-chain baseline price every 10 minutes.

Usage:
    python3 live_mempool_with_baseline.py

Requirements:
    pip install websockets

Configuration:
    - mempool.space backend must be running: docker-compose up -d
    - Bitcoin Core must be synced
    - WebSocket endpoint: ws://localhost:8999/api/v1/ws
"""

import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import websockets
except ImportError:
    print("❌ Error: websockets module not installed")
    print("   Install with: pip install websockets")
    sys.exit(1)

# Configuration
MEMPOOL_WS = "ws://localhost:8999/api/v1/ws"
UTXORACLE_PATH = Path(__file__).parent.parent / "UTXOracle.py"
BASELINE_UPDATE_INTERVAL = 600  # 10 minutes


async def calculate_baseline_price() -> dict:
    """
    Calculate UTXOracle baseline from last 144 blocks.

    Returns:
        dict with keys: price, timestamp, success
    """
    print("🔄 Calculating UTXOracle baseline (144 blocks)...")

    try:
        result = subprocess.run(
            ["python3", str(UTXORACLE_PATH), "-rb", "--no-browser"],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )

        # Parse output
        for line in result.stdout.split("\n"):
            if "price:" in line:
                price_str = line.split("$")[1].replace(",", "")
                price = float(price_str)

                return {
                    "success": True,
                    "price": price,
                    "timestamp": datetime.now().isoformat(),
                    "source": "UTXOracle_on-chain",
                }

        return {"success": False, "error": "Could not parse UTXOracle output"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "UTXOracle timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def stream_mempool():
    """
    Stream real-time mempool data and update baseline periodically.
    """
    baseline = None
    last_baseline_update = 0

    print("=" * 60)
    print("🚀 UTXOracle Live Monitor")
    print("   Mempool stream: Real-time from mempool.space")
    print("   Baseline price: On-chain from UTXOracle (every 10min)")
    print("=" * 60)
    print()

    # Calculate initial baseline
    baseline_result = await calculate_baseline_price()
    if baseline_result["success"]:
        baseline = baseline_result
        print(f"✅ Initial baseline: ${baseline['price']:,.2f}")
        print(f"   Timestamp: {baseline['timestamp']}")
        print()
    else:
        print(
            f"⚠️  Failed to calculate initial baseline: {baseline_result.get('error')}"
        )
        print()

    last_baseline_update = asyncio.get_event_loop().time()

    # Connect to WebSocket
    print(f"🔌 Connecting to {MEMPOOL_WS}...")
    try:
        async with websockets.connect(MEMPOOL_WS) as ws:
            print("✅ Connected to mempool.space WebSocket")
            print()

            # Subscribe to channels
            subscribe_msg = {
                "action": "want",
                "data": ["blocks", "mempool-blocks", "live-2h-chart", "stats"],
            }
            await ws.send(json.dumps(subscribe_msg))
            print("📡 Subscribed to: blocks, mempool-blocks, stats")
            print()
            print("=" * 60)
            print()

            msg_count = 0

            async for message in ws:
                try:
                    data = json.loads(message)
                    action = data.get("action", "unknown")

                    # Process different message types
                    if action == "block":
                        block_data = data.get("data", {})
                        print(
                            f"🔷 New Block: #{block_data.get('height', '?')} "
                            f"({block_data.get('tx_count', '?')} txs)"
                        )

                    elif action == "mempool-blocks":
                        mempool_blocks = data.get("data", [])
                        if mempool_blocks:
                            total_txs = sum(b.get("nTx", 0) for b in mempool_blocks)
                            print(
                                f"📦 Mempool: {len(mempool_blocks)} blocks, "
                                f"{total_txs} transactions"
                            )

                    elif action == "stats":
                        stats = data.get("data", {})
                        mempool_size = stats.get("mempool_size", 0)
                        vsize = stats.get("vsize", 0)
                        print(
                            f"📊 Stats: {mempool_size} txs, {vsize / 1_000_000:.2f} MB"
                        )

                    msg_count += 1

                    # Update baseline every 10 minutes
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_baseline_update >= BASELINE_UPDATE_INTERVAL:
                        print()
                        print("-" * 60)
                        baseline_result = await calculate_baseline_price()

                        if baseline_result["success"]:
                            old_price = baseline["price"] if baseline else 0
                            new_price = baseline_result["price"]
                            change = new_price - old_price if old_price else 0
                            change_pct = (change / old_price * 100) if old_price else 0

                            baseline = baseline_result
                            print(
                                f"✅ Updated baseline: ${new_price:,.2f} "
                                f"({change:+.2f}, {change_pct:+.2f}%)"
                            )
                            print(f"   Timestamp: {baseline['timestamp']}")
                        else:
                            print(
                                f"⚠️  Failed to update baseline: "
                                f"{baseline_result.get('error')}"
                            )

                        print("-" * 60)
                        print()
                        last_baseline_update = current_time

                    # Show summary every 50 messages
                    if msg_count % 50 == 0:
                        print()
                        print(f"💡 Messages received: {msg_count}")
                        if baseline:
                            print(f"   Current baseline: ${baseline['price']:,.2f}")
                            print(f"   Last update: {baseline['timestamp']}")
                        print()

                except json.JSONDecodeError:
                    print("⚠️  Invalid JSON received")
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print(f"⚠️  Error processing message: {e}")

    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocket error: {e}")
        print()
        print("💡 Make sure mempool.space backend is running:")
        print("   cd /media/sam/1TB/mempool/docker && docker-compose up -d")
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        print()
        print("🛑 Stopped by user")
        print()
        if baseline:
            print(f"Final baseline: ${baseline['price']:,.2f}")
            print(f"Last update: {baseline['timestamp']}")
        sys.exit(0)


def main():
    """Main entry point"""
    try:
        asyncio.run(stream_mempool())
    except KeyboardInterrupt:
        print()
        print("🛑 Stopped")


if __name__ == "__main__":
    main()
