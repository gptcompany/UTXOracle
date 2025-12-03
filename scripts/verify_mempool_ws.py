#!/usr/bin/env python3
"""
Verify mempool.space WebSocket availability
Task T004: Infrastructure verification
"""

import asyncio
import websockets
import aiohttp
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def verify_http_api():
    """Verify mempool.space HTTP API is accessible"""
    logger.info("Checking mempool.space HTTP API...")

    try:
        async with aiohttp.ClientSession() as session:
            # Check prices endpoint
            async with session.get("http://localhost:8999/api/v1/prices") as response:
                if response.status == 200:
                    data = await response.json()
                    btc_price = data.get("USD", "N/A")
                    logger.info(f"✅ HTTP API accessible - BTC Price: ${btc_price}")
                    return True
                else:
                    logger.error(f"❌ HTTP API returned status {response.status}")
                    return False
    except Exception as e:
        logger.error(f"❌ HTTP API error: {e}")
        return False


async def verify_websocket():
    """Verify mempool.space WebSocket is accessible"""
    logger.info("Checking mempool.space WebSocket...")

    ws_url = "ws://localhost:8999/ws/track-mempool-tx"

    try:
        async with websockets.connect(ws_url, open_timeout=5) as websocket:
            logger.info(f"✅ Connected to {ws_url}")

            # Subscribe to mempool transactions
            subscribe_msg = {"action": "subscribe", "type": "mempool-tx"}
            await websocket.send(json.dumps(subscribe_msg))
            logger.info("✅ Subscription message sent")

            # Wait for first message (with timeout)
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(message)
                logger.info(
                    f"✅ Received message: {list(data.keys())[:5]}..."
                )  # Show first 5 keys
                return True
            except asyncio.TimeoutError:
                logger.warning(
                    "⚠️  No transactions received in 10 seconds (mempool might be quiet)"
                )
                return True  # Connection still works

    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(
            f"❌ WebSocket connection failed with status code: {e.status_code}"
        )
        return False
    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
        return False


async def verify_electrs():
    """Verify electrs HTTP API is accessible"""
    logger.info("Checking electrs HTTP API...")

    try:
        async with aiohttp.ClientSession() as session:
            # Check tip height
            async with session.get(
                "http://localhost:3001/blocks/tip/height"
            ) as response:
                if response.status == 200:
                    height = await response.text()
                    logger.info(
                        f"✅ electrs accessible - Current block height: {height.strip()}"
                    )
                    return True
                else:
                    logger.error(f"❌ electrs returned status {response.status}")
                    return False
    except Exception as e:
        logger.error(f"❌ electrs error: {e}")
        return False


async def run_verification():
    """Run all infrastructure verification checks"""
    logger.info("=" * 60)
    logger.info("Mempool Infrastructure Verification")
    logger.info("=" * 60)

    results = {
        "HTTP API": await verify_http_api(),
        "WebSocket": await verify_websocket(),
        "electrs": await verify_electrs(),
    }

    logger.info("\n" + "=" * 60)
    logger.info("Verification Results:")
    logger.info("=" * 60)

    all_passed = True
    for check, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{check:.<30} {status}")
        if not passed:
            all_passed = False

    if all_passed:
        logger.info("\n✅ All infrastructure checks passed!")
    else:
        logger.error("\n❌ Some infrastructure checks failed")
        logger.error("   Make sure mempool.space Docker stack is running:")
        logger.error("   cd /media/sam/2TB-NVMe/prod/apps/mempool-stack/")
        logger.error("   docker compose up -d")

    return all_passed


if __name__ == "__main__":
    import sys

    success = asyncio.run(run_verification())
    sys.exit(0 if success else 1)
