from __future__ import annotations

import httpx
import logging

logger = logging.getLogger(__name__)


class NTWhaleAdapter:
    """
    Adapter for Nautilus Trader to interact with UTXOracle whale detection.
    Provides execution safety checks based on the execution status contract.
    """

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8011",
        max_jitter_ms: int = 500,
        timeout_seconds: float = 2.0,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_url = api_url
        self.max_jitter_ms = max_jitter_ms
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._transport = transport
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_execution_status(self) -> dict | None:
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.api_url}/api/execution/btc/status")
            if resp.status_code != 200:
                logger.warning("Gatekeeper returned status %s", resp.status_code)
                return None
            return resp.json()
        except httpx.RequestError as exc:
            logger.error("Gatekeeper unreachable: %s", exc)
            return None
        except Exception as exc:
            logger.error("Gatekeeper error: %s", exc)
            return None

    async def can_execute(self) -> bool:
        """
        Check if market conditions allow execution.
        Returns True only when the execution contract explicitly allows trading.
        """
        data = await self.fetch_execution_status()
        if not data:
            return False

        stats = data.get("stats", {})
        jitter = stats.get("last_jitter_ms")
        if jitter is not None and float(jitter) > self.max_jitter_ms:
            logger.warning(
                "Execution suspended: High jitter %.1fms (limit %sms)",
                float(jitter),
                self.max_jitter_ms,
            )
            return False

        execution_mode = str(data.get("execution_mode", "")).lower()
        compatibility_status = str(data.get("compatibility_status", "")).upper()
        status_reason = data.get("status_reason", "unknown")

        if execution_mode == "trade_enabled" or compatibility_status == "STATUS_OK":
            return True

        logger.warning(
            "Execution suspended: mode=%s compatibility=%s reason=%s",
            execution_mode or "unknown",
            compatibility_status or "unknown",
            status_reason,
        )
        return False
