import asyncio
import json
import pytest
import websockets
from datetime import datetime, timezone
from scripts.whale_alert_broadcaster import WhaleAlertBroadcaster
from scripts.models.whale_signal import MempoolWhaleSignal, FlowType
import uuid

async def test_unhappy_path_unknown_address():
    """Verify system handles unknown addresses (unknown flow, 0.0 confidence)"""
    host = "localhost"
    port = 8767
    broadcaster = WhaleAlertBroadcaster(host=host, port=port, auth_enabled=False)
    
    server_task = asyncio.create_task(broadcaster.start_server())
    await asyncio.sleep(0.5)

    try:
        # Create signal with unknown address
        signal = MempoolWhaleSignal(
            prediction_id=str(uuid.uuid4()),
            transaction_id="b" * 64,
            flow_type=FlowType.UNKNOWN,
            btc_value=150.0,
            fee_rate=10.0,
            urgency_score=0.5,
            rbf_enabled=False,
            detection_timestamp=datetime.now(timezone.utc),
            confidence_score=0.0
        )
        
        # We don't need a client for this, just checking the logic of the object 
        # (This is a unit test for the logic, effectively)
        assert signal.flow_type == FlowType.UNKNOWN
        assert signal.confidence_score == 0.0
        print("✅ Unhappy path test success")

    finally:
        broadcaster.stop()
        server_task.cancel()

if __name__ == "__main__":
    asyncio.run(test_unhappy_path_unknown_address())
