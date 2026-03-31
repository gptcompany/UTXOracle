from __future__ import annotations

import httpx

from scripts.live.models import LiveSnapshot


class LiveSnapshotPollingClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 5.0,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
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

    async def fetch_snapshot(self) -> LiveSnapshot:
        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/api/v1/live/snapshot",
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        return LiveSnapshot.model_validate(response.json())

    async def fetch_history(self, *, minutes: int) -> list[LiveSnapshot]:
        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/api/v1/live/history",
            params={"minutes": minutes},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        return [LiveSnapshot.model_validate(item) for item in response.json()]

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None
