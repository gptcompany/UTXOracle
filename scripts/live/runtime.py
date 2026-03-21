from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from UTXOracle_library import UTXOracleCalculator
from scripts.live.models import OracleObservation, utc_now
from scripts.live.source_clients import (
    DEFAULT_SOURCE_TIMEOUT_SECONDS,
    BrkClient,
    ElectrsClient,
    HyperliquidSnapshotClient,
    MempoolApiClient,
)
from scripts.live.storage import LiveSnapshotStore
from scripts.live.worker import LiveWorker

logger = logging.getLogger(__name__)
DEFAULT_LIVE_ORACLE_TX_CONCURRENCY = int(os.getenv("LIVE_ORACLE_TX_CONCURRENCY", "32"))
DEFAULT_LIVE_ORACLE_MIN_TX_COUNT = int(os.getenv("LIVE_ORACLE_MIN_TX_COUNT", "1000"))


class ElectrsBlockOracleResolver:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float = DEFAULT_SOURCE_TIMEOUT_SECONDS,
        tx_fetch_concurrency: int = DEFAULT_LIVE_ORACLE_TX_CONCURRENCY,
        min_tx_count: int = DEFAULT_LIVE_ORACLE_MIN_TX_COUNT,
        calculator: UTXOracleCalculator | None = None,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("ELECTRS_HTTP_URL", "http://127.0.0.1:3002")).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.tx_fetch_concurrency = max(tx_fetch_concurrency, 1)
        self.min_tx_count = max(min_tx_count, 1)
        self._calculator = calculator or UTXOracleCalculator()
        self._transport = transport
        self._client = client
        self._owns_client = client is None
        self._last_height: int | None = None
        self._last_observation: OracleObservation | None = None

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

    async def __call__(self, block_height: int, block_changed: bool) -> OracleObservation:
        if (
            not block_changed
            and self._last_observation is not None
            and self._last_height == block_height
        ):
            return self._last_observation

        transactions = await self.fetch_block_transactions(block_height)
        result = await asyncio.to_thread(
            self._calculator.calculate_price_for_transactions,
            transactions,
        )
        observation = OracleObservation(
            timestamp=utc_now(),
            price=_coerce_float(result.get("price_usd")),
            confidence=_coerce_float(result.get("confidence")),
        )
        if observation.price is not None:
            self._last_height = block_height
            self._last_observation = observation
        return observation

    async def fetch_block_transactions(self, block_height: int) -> list[dict[str, Any]]:
        client = await self._get_client()
        block_hash = await self._fetch_block_hash(client, block_height)
        txids = await self._fetch_block_txids(client, block_hash)
        if len(txids) < self.min_tx_count:
            raise ValueError(
                f"electrs block {block_height} returned only {len(txids)} txids (min {self.min_tx_count})"
            )

        semaphore = asyncio.Semaphore(self.tx_fetch_concurrency)

        async def _fetch_transaction(txid: str) -> dict[str, Any]:
            async with semaphore:
                response = await client.get(
                    f"{self.base_url}/tx/{txid}",
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                payload = response.json()
                return _convert_satoshi_tx_to_btc(payload)

        return await asyncio.gather(*(_fetch_transaction(txid) for txid in txids))

    async def _fetch_block_hash(self, client: httpx.AsyncClient, block_height: int) -> str:
        response = await client.get(
            f"{self.base_url}/block-height/{block_height}",
            headers={"Accept": "text/plain"},
        )
        response.raise_for_status()
        block_hash = response.text.strip().strip('"')
        if not block_hash:
            raise ValueError(f"electrs block-height lookup returned empty hash for {block_height}")
        return block_hash

    async def _fetch_block_txids(
        self,
        client: httpx.AsyncClient,
        block_hash: str,
    ) -> list[str]:
        response = await client.get(
            f"{self.base_url}/block/{block_hash}/txids",
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"electrs block {block_hash} returned no txids")
        return [str(item) for item in payload]


class LiveWorkerRuntime:
    def __init__(self, *, worker: LiveWorker, resources: list[Any]) -> None:
        self.worker = worker
        self._resources = resources

    async def run(self) -> list:
        return await self.worker.run(
            market_interval_seconds=float(os.getenv("LIVE_MARKET_INTERVAL_SECONDS", "5.0")),
            block_poll_interval_seconds=float(os.getenv("LIVE_BLOCK_POLL_INTERVAL_SECONDS", "2.0")),
        )

    async def aclose(self) -> None:
        for resource in self._resources:
            close = getattr(resource, "aclose", None)
            if close is not None:
                await close()


def build_live_runtime() -> LiveWorkerRuntime:
    timeout_seconds = float(os.getenv("LIVE_SOURCE_TIMEOUT_SECONDS", str(DEFAULT_SOURCE_TIMEOUT_SECONDS)))
    retention_hours = int(os.getenv("LIVE_RETENTION_HOURS", "24"))
    live_db_path = os.getenv("LIVE_DUCKDB_PATH", "data/utxoracle_live.duckdb")
    process_lock_path = os.getenv("LIVE_WORKER_LOCK_PATH") or None

    electrs_client = ElectrsClient(timeout_seconds=timeout_seconds)
    mempool_client = MempoolApiClient(timeout_seconds=timeout_seconds)
    brk_client = BrkClient(timeout_seconds=timeout_seconds)
    hyperliquid_client = HyperliquidSnapshotClient(timeout_seconds=timeout_seconds)
    oracle_resolver = ElectrsBlockOracleResolver(
        timeout_seconds=timeout_seconds,
        tx_fetch_concurrency=int(os.getenv("LIVE_ORACLE_TX_CONCURRENCY", str(DEFAULT_LIVE_ORACLE_TX_CONCURRENCY))),
        min_tx_count=int(os.getenv("LIVE_ORACLE_MIN_TX_COUNT", str(DEFAULT_LIVE_ORACLE_MIN_TX_COUNT))),
    )
    snapshot_store = LiveSnapshotStore(live_db_path, retention_hours=retention_hours)
    worker = LiveWorker(
        electrs_client=electrs_client,
        mempool_client=mempool_client,
        brk_client=brk_client,
        hyperliquid_client=hyperliquid_client,
        oracle_resolver=oracle_resolver,
        snapshot_store=snapshot_store,
        process_lock_path=process_lock_path,
    )
    return LiveWorkerRuntime(
        worker=worker,
        resources=[
            electrs_client,
            mempool_client,
            brk_client,
            hyperliquid_client,
            oracle_resolver,
        ],
    )


def _convert_satoshi_tx_to_btc(payload: dict[str, Any]) -> dict[str, Any]:
    converted = dict(payload)
    vouts = []
    for vout in payload.get("vout", []):
        converted_vout = dict(vout)
        if "value" in converted_vout:
            converted_vout["value"] = float(converted_vout["value"]) / 1e8
        vouts.append(converted_vout)
    converted["vout"] = vouts
    return converted


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    runtime = build_live_runtime()
    logger.info("Starting UTXOracle live worker runtime")
    try:
        await runtime.run()
    finally:
        await runtime.aclose()


if __name__ == "__main__":
    asyncio.run(main())
