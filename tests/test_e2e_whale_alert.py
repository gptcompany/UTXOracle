import asyncio
import json
import pytest
import websockets
from datetime import datetime, timezone
from scripts.whale_alert_broadcaster import WhaleAlertBroadcaster
from scripts.models.whale_signal import MempoolWhaleSignal, FlowType
import uuid

async def test_whale_alert_broadcast_e2e():
    """Test E2E: Broadcaster sends alert to subscriber"""
    host = "localhost"
    port = 8766  # Different port to avoid conflict
    broadcaster = WhaleAlertBroadcaster(host=host, port=port, auth_enabled=False)
    
    server_task = asyncio.create_task(broadcaster.start_server())
    await asyncio.sleep(0.5)

    try:
        # Subscribe as a client
        async with websockets.connect(f"ws://{host}:{port}") as ws:
            # Receive welcome
            welcome = await ws.recv()
            
            # Send a test signal via broadcaster
            signal = MempoolWhaleSignal(
                prediction_id=str(uuid.uuid4()),
                transaction_id="a" * 64,
                flow_type=FlowType.INFLOW,
                btc_value=150.0,
                fee_rate=10.0,
                urgency_score=0.5,
                rbf_enabled=False,
                detection_timestamp=datetime.now(timezone.utc)
            )
            
            await broadcaster.broadcast_alert(signal)
            
            # Receive broadcasted alert
            message = await ws.recv()
            data = json.loads(message)
            
            assert data["type"] == "whale_alert"
            assert data["data"]["transaction_id"] == signal.transaction_id
            print("✅ E2E Broadcast success")
            
    finally:
        await broadcaster.stop()
        server_task.cancel()

if __name__ == "__main__":
    asyncio.run(test_whale_alert_broadcast_e2e())
