from __future__ import annotations

from pathlib import Path

import sqlite3
import httpx
import pytest

from scripts.live.runtime import (
    ElectrsBlockOracleResolver,
    build_live_runtime,
)


class DummyCalculator:
    def __init__(self, price: float = 84211.52, confidence: float = 0.82):
        self.price = price
        self.confidence = confidence
        self.calls: list[list[dict]] = []

    def calculate_price_for_transactions(self, transactions: list[dict]) -> dict:
        self.calls.append(transactions)
        return {
            "price_usd": self.price,
            "confidence": self.confidence,
        }


@pytest.mark.asyncio
async def test_electrs_block_oracle_resolver_fetches_and_caches_current_block():
    calculator = DummyCalculator()
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path == "/block-height/941453":
            return httpx.Response(200, text='"0000abc"')
        if request.url.path == "/block/0000abc/txids":
            return httpx.Response(200, json=["tx1", "tx2"])
        if request.url.path == "/tx/tx1":
            return httpx.Response(200, json={"txid": "tx1", "vout": [{"value": 100000000}]})
        if request.url.path == "/tx/tx2":
            return httpx.Response(200, json={"txid": "tx2", "vout": [{"value": 50000000}]})
        raise AssertionError(f"unexpected path: {request.url.path}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        resolver = ElectrsBlockOracleResolver(
            base_url="http://electrs.local",
            client=client,
            calculator=calculator,
            tx_fetch_concurrency=1,
            min_tx_count=1,
        )
        first = await resolver(941453, True)
        second = await resolver(941453, False)

    assert first.price == pytest.approx(84211.52)
    assert first.confidence == pytest.approx(0.82)
    assert second.price == first.price
    assert len(calculator.calls) == 1
    assert calculator.calls[0][0]["vout"][0]["value"] == pytest.approx(1.0)
    assert calculator.calls[0][1]["vout"][0]["value"] == pytest.approx(0.5)
    assert seen_paths.count("/block-height/941453") == 1
    assert seen_paths.count("/block/0000abc/txids") == 1


@pytest.mark.asyncio
async def test_build_live_runtime_uses_env_driven_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("LIVE_DB_PATH", str(tmp_path / "live.sqlite3"))
    monkeypatch.setenv("LIVE_WORKER_LOCK_PATH", str(tmp_path / "worker.lock"))
    monkeypatch.setenv("ELECTRS_HTTP_URL", "http://electrs.local")
    monkeypatch.setenv("MEMPOOL_API_V1_URL", "http://mempool.local/api/v1")
    monkeypatch.setenv("BRK_BASE_URL", "http://brk.local")
    monkeypatch.setenv("HYPERLIQUID_NODE_API_URL", "http://hl.local/info")
    monkeypatch.setenv("HYPERLIQUID_DATA_ROOT", str(tmp_path / "hl"))
    monkeypatch.setenv("HYPERLIQUID_NODE_INFO_REQUEST_TYPE", "l2Book")

    runtime = build_live_runtime()
    try:
        assert runtime.worker.snapshot_store.db_path == Path(tmp_path / "live.sqlite3")
        assert runtime.worker.process_lock_path == Path(tmp_path / "worker.lock")
        assert runtime.worker.electrs_client.base_url == "http://electrs.local"
        assert runtime.worker.mempool_client.base_url == "http://mempool.local/api/v1"
        assert runtime.worker.brk_client.base_url == "http://brk.local"
        assert runtime.worker.hyperliquid_client.base_url == "http://hl.local/info"
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
async def test_runtime_run_initializes_schema_before_worker_run(monkeypatch, tmp_path):
    monkeypatch.setenv("LIVE_DB_PATH", str(tmp_path / "live.sqlite3"))
    monkeypatch.setenv("LIVE_WORKER_LOCK_PATH", str(tmp_path / "worker.lock"))
    monkeypatch.setenv("ELECTRS_HTTP_URL", "http://electrs.local")
    monkeypatch.setenv("MEMPOOL_API_V1_URL", "http://mempool.local/api/v1")
    monkeypatch.setenv("BRK_BASE_URL", "http://brk.local")
    monkeypatch.setenv("HYPERLIQUID_NODE_API_URL", "http://hl.local/info")
    monkeypatch.setenv("HYPERLIQUID_DATA_ROOT", str(tmp_path / "hl"))

    runtime = build_live_runtime()

    async def fake_run(*, market_interval_seconds: float, block_poll_interval_seconds: float):
        assert market_interval_seconds == 5.0
        assert block_poll_interval_seconds == 2.0
        conn = sqlite3.connect(str(runtime.worker.snapshot_store.db_path))
        try:
            assert conn.execute("SELECT COUNT(*) FROM live_snapshots").fetchone() == (0,)
        finally:
            conn.close()
        return []

    monkeypatch.setattr(runtime.worker, "run", fake_run)

    try:
        assert await runtime.run() == []
    finally:
        await runtime.aclose()
