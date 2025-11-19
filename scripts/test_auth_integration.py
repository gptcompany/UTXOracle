#!/usr/bin/env python3
"""
Test script for WebSocket authentication integration
Verifies that T018a and T018b tasks are working correctly
"""

import asyncio
import websockets
import json
import sys
from pathlib import Path

# Add auth module to path
sys.path.append(str(Path(__file__).parent))
from auth.websocket_auth import WebSocketAuthenticator


async def test_authenticated_connection():
    """Test connecting with valid authentication"""
    print("=" * 60)
    print("TEST 1: Authenticated Connection")
    print("-" * 60)

    # Create authenticator and generate token
    auth = WebSocketAuthenticator()
    token = auth.generate_token("test_client", {"read", "write"})
    print("✅ Generated token for test_client")

    try:
        # Connect to broadcaster
        async with websockets.connect("ws://localhost:8765") as websocket:
            print("✅ Connected to whale alert broadcaster")

            # Send authentication
            auth_msg = {"type": "auth", "token": token}
            await websocket.send(json.dumps(auth_msg))
            print("✅ Sent authentication message")

            # Wait for auth response
            response = await websocket.recv()
            data = json.loads(response)

            if data.get("type") == "auth_success":
                print("✅ Authentication successful!")
                print(f"   Client ID: {data.get('client_id')}")
                print(f"   Permissions: {data.get('permissions')}")

                # Wait for welcome message
                welcome = await websocket.recv()
                welcome_data = json.loads(welcome)
                if welcome_data.get("type") == "welcome":
                    print("✅ Received welcome message")

                # Test ping/pong
                await websocket.send(json.dumps({"type": "ping"}))
                pong = await websocket.recv()
                pong_data = json.loads(pong)
                if pong_data.get("type") == "pong":
                    print("✅ Ping/pong working")

                # Test stats request
                await websocket.send(json.dumps({"type": "stats"}))
                stats = await websocket.recv()
                stats_data = json.loads(stats)
                if stats_data.get("type") == "stats":
                    print(f"✅ Stats received: {stats_data.get('data')}")

                print("✅ TEST 1 PASSED: Authenticated connection successful")
            else:
                print(f"❌ Authentication failed: {data}")

    except Exception as e:
        print(f"❌ Connection error: {e}")
        print("   Is the whale_alert_broadcaster.py running?")
        print("   Start it with: python3 scripts/whale_alert_broadcaster.py --no-auth")


async def test_unauthenticated_rejection():
    """Test that unauthenticated connections are rejected when auth is enabled"""
    print("\n" + "=" * 60)
    print("TEST 2: Unauthenticated Connection (Should Fail)")
    print("-" * 60)

    try:
        # Try to connect without auth
        async with websockets.connect("ws://localhost:8765") as websocket:
            print("✅ Connected to whale alert broadcaster")

            # Send non-auth message first (should fail)
            await websocket.send(json.dumps({"type": "ping"}))
            print("❌ Sent message without auth (should have been rejected)")

            # Wait for error
            response = await websocket.recv()
            data = json.loads(response)

            if data.get("type") == "error":
                print(f"✅ Correctly rejected: {data.get('message')}")
                print("✅ TEST 2 PASSED: Unauthenticated connections properly rejected")
            else:
                print(f"❌ Should have been rejected but got: {data}")

    except websockets.ConnectionClosedError as e:
        print(f"✅ Connection closed as expected: {e}")
        print("✅ TEST 2 PASSED: Unauthenticated connections properly rejected")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


async def test_invalid_token():
    """Test that invalid tokens are rejected"""
    print("\n" + "=" * 60)
    print("TEST 3: Invalid Token")
    print("-" * 60)

    try:
        # Connect with invalid token
        async with websockets.connect("ws://localhost:8765") as websocket:
            print("✅ Connected to whale alert broadcaster")

            # Send invalid token
            auth_msg = {"type": "auth", "token": "invalid_token_12345"}
            await websocket.send(json.dumps(auth_msg))
            print("✅ Sent invalid authentication token")

            # Wait for error response
            response = await websocket.recv()
            data = json.loads(response)

            if data.get("type") == "error":
                print(f"✅ Invalid token rejected: {data.get('message')}")
                print("✅ TEST 3 PASSED: Invalid tokens properly rejected")
            else:
                print(f"❌ Should have been rejected but got: {data}")

    except websockets.ConnectionClosedError as e:
        print(f"✅ Connection closed as expected: {e}")
        print("✅ TEST 3 PASSED: Invalid tokens properly rejected")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


async def test_development_mode():
    """Test connecting in development mode (no auth)"""
    print("\n" + "=" * 60)
    print("TEST 4: Development Mode (No Auth)")
    print("-" * 60)

    print(
        "ℹ️  For this test, restart the server with: python3 scripts/whale_alert_broadcaster.py --no-auth"
    )
    print("   Then run this test again.")
    print("   Skipping for now...")


async def run_all_tests():
    """Run all authentication tests"""
    print("\n" + "🔐 WebSocket Authentication Integration Tests")
    print("=" * 60)

    # Note about server
    print("⚠️  Make sure the whale alert broadcaster is running:")
    print("   With auth:    python3 scripts/whale_alert_broadcaster.py")
    print("   Without auth: python3 scripts/whale_alert_broadcaster.py --no-auth")
    print()

    await asyncio.sleep(2)

    # Run tests
    await test_authenticated_connection()
    await test_unauthenticated_rejection()
    await test_invalid_token()
    await test_development_mode()

    print("\n" + "=" * 60)
    print("🎉 All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
