import asyncio
from scripts.mempool_whale_monitor import MempoolWhaleMonitor
# Mock injection
async def inject():
    m = MempoolWhaleMonitor()
    # Mock tx
    tx = {"txid": "a"*64, "btc_value": 150.0, "fee_rate": 20.0, "rbf_enabled": False, "urgency_score": 0.5}
    await m._handle_transaction(str(tx))
    print("✅ Injection success")
