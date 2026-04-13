import httpx
import logging

logger = logging.getLogger(__name__)

class NTWhaleAdapter:
    """
    Adapter for Nautilus Trader to interact with UTXOracle whale detection.
    Provides execution safety checks based on system health and latency.
    """
    def __init__(self, api_url: str = "http://127.0.0.1:8011", max_jitter_ms: int = 500):
        self.api_url = api_url
        self.max_jitter_ms = max_jitter_ms

    async def can_execute(self) -> bool:
        """
        Check if market conditions allow execution.
        Returns True if the system is ready and latency is within acceptable limits.
        """
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{self.api_url}/api/execution/btc/status", timeout=2.0)
                if resp.status_code != 200:
                    logger.warning(f"Gatekeeper returned status {resp.status_code}")
                    return False
                
                data = resp.json()
                
                # Check system status
                if data.get("status") != "ready":
                    logger.warning(f"Execution suspended: {data.get('reason', 'unknown')}")
                    return False
                
                # Check latency (jitter)
                stats = data.get("stats", {})
                jitter = stats.get("last_jitter_ms", 0)
                if jitter > self.max_jitter_ms:
                    logger.warning(f"Execution suspended: High jitter {jitter:.1f}ms (limit {self.max_jitter_ms}ms)")
                    return False
                    
                return True
            except httpx.RequestError as e:
                logger.error(f"Gatekeeper unreachable: {e}")
                return False
            except Exception as e:
                logger.error(f"Gatekeeper error: {e}")
                return False
