"""Async Electrs HTTP API Client.

High-performance async client for electrs REST API with:
- Connection pooling (TCPConnector with configurable limits)
- Semaphore-based rate limiting for concurrent requests
- Batch fetching for blocks and transactions
- Exponential backoff retry logic
- Proper async context management

Performance target: 12x speedup vs sequential (180s → 15s per block)

Usage:
    async with ElectrsAsyncClient() as client:
        # Single block
        block = await client.get_block_async(920000)

        # Batch blocks (parallel)
        blocks = await client.get_blocks_batch_async([920000, 920001, 920002])
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_ELECTRS_URL = "http://localhost:3001"
DEFAULT_MAX_CONNECTIONS = 50  # Reduced from 100 to prevent electrs contention
DEFAULT_CONCURRENT_PER_BATCH = 30  # Reduced from 50: optimal for local electrs
DEFAULT_BATCH_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 3


@dataclass
class ElectrsConfig:
    """Configuration for ElectrsAsyncClient."""

    base_url: str = DEFAULT_ELECTRS_URL
    max_connections: int = DEFAULT_MAX_CONNECTIONS
    concurrent_per_batch: int = DEFAULT_CONCURRENT_PER_BATCH
    batch_size: int = DEFAULT_BATCH_SIZE
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES

    @classmethod
    def from_env(cls) -> "ElectrsConfig":
        """Create config from environment variables."""
        return cls(
            base_url=os.getenv("ELECTRS_HTTP_URL", DEFAULT_ELECTRS_URL),
            max_connections=int(
                os.getenv("ELECTRS_MAX_CONNECTIONS", DEFAULT_MAX_CONNECTIONS)
            ),
            concurrent_per_batch=int(
                os.getenv("ELECTRS_CONCURRENT_PER_BATCH", DEFAULT_CONCURRENT_PER_BATCH)
            ),
            batch_size=int(os.getenv("ELECTRS_BATCH_SIZE", DEFAULT_BATCH_SIZE)),
            timeout_seconds=int(
                os.getenv("ELECTRS_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
            ),
            max_retries=int(os.getenv("ELECTRS_MAX_RETRIES", DEFAULT_MAX_RETRIES)),
        )


class ElectrsAsyncClient:
    """High-performance async client for electrs HTTP API.

    Features:
    - Connection pooling: Reuses TCP connections (TCPConnector)
    - Rate limiting: Semaphore prevents overwhelming electrs
    - Batch processing: Fetches transactions in parallel batches
    - Retry logic: Exponential backoff on failures

    Example:
        async with ElectrsAsyncClient() as client:
            block = await client.get_block_async(920000)
            print(f"Block has {len(block['tx'])} transactions")
    """

    def __init__(self, config: ElectrsConfig | None = None):
        """Initialize client with optional config.

        Args:
            config: ElectrsConfig instance. If None, loads from environment.
        """
        self.config = config or ElectrsConfig.from_env()
        self._session: aiohttp.ClientSession | None = None
        self._semaphore: asyncio.Semaphore | None = None

    async def __aenter__(self) -> "ElectrsAsyncClient":
        """Create aiohttp session with connection pooling."""
        connector = aiohttp.TCPConnector(
            limit=self.config.max_connections,
            limit_per_host=self.config.max_connections,
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        self._semaphore = asyncio.Semaphore(self.config.concurrent_per_batch)
        logger.debug(
            f"ElectrsAsyncClient initialized: {self.config.base_url}, "
            f"max_connections={self.config.max_connections}, "
            f"concurrent={self.config.concurrent_per_batch}"
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None
        self._semaphore = None

    async def _retry_with_backoff(
        self,
        func,
        *args,
        max_retries: int | None = None,
        base_delay: float = 1.0,
        **kwargs,
    ) -> Any:
        """Retry an async function with exponential backoff.

        Args:
            func: Async function to retry
            *args: Positional arguments for func
            max_retries: Max retry attempts (default: from config)
            base_delay: Base delay in seconds
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            Last exception if all retries fail
        """
        max_retries = max_retries or self.config.max_retries
        last_exception = None

        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)  # 1s, 2s, 4s
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All {max_retries} retry attempts failed: {e}")

        raise last_exception  # type: ignore

    async def _get_json(self, url: str) -> Any:
        """Fetch JSON from URL with semaphore rate limiting.

        Args:
            url: Full URL to fetch

        Returns:
            Parsed JSON response

        Raises:
            aiohttp.ClientError: On network errors
        """
        if not self._session:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        if not self._semaphore:
            raise RuntimeError("Semaphore not initialized.")

        async with self._semaphore:
            async with self._session.get(url) as response:
                response.raise_for_status()
                return await response.json()

    async def _get_text(self, url: str) -> str:
        """Fetch text from URL with semaphore rate limiting.

        Args:
            url: Full URL to fetch

        Returns:
            Text response
        """
        if not self._session:
            raise RuntimeError("Client not initialized. Use 'async with' context.")
        if not self._semaphore:
            raise RuntimeError("Semaphore not initialized.")

        async with self._semaphore:
            async with self._session.get(url) as response:
                response.raise_for_status()
                return await response.text()

    async def get_block_hash(self, height: int) -> str:
        """Get block hash for a given height.

        Args:
            height: Block height

        Returns:
            Block hash string
        """
        url = f"{self.config.base_url}/block-height/{height}"
        return await self._retry_with_backoff(self._get_text, url)

    async def get_block_meta(self, block_hash: str) -> dict:
        """Get block metadata (timestamp, height, etc.).

        Args:
            block_hash: Block hash

        Returns:
            Block metadata dict
        """
        url = f"{self.config.base_url}/block/{block_hash}"
        return await self._retry_with_backoff(self._get_json, url)

    async def get_txids(self, block_hash: str) -> list[str]:
        """Get all transaction IDs in a block.

        Args:
            block_hash: Block hash

        Returns:
            List of transaction IDs
        """
        url = f"{self.config.base_url}/block/{block_hash}/txids"
        return await self._retry_with_backoff(self._get_json, url)

    async def get_tx(self, txid: str) -> dict | None:
        """Get a single transaction by ID.

        Args:
            txid: Transaction ID

        Returns:
            Transaction dict or None if failed
        """
        try:
            url = f"{self.config.base_url}/tx/{txid}"
            return await self._get_json(url)
        except Exception as e:
            logger.warning(f"Failed to fetch tx {txid[:16]}...: {e}")
            return None

    async def _fetch_txs_batch(self, txids: list[str]) -> list[dict]:
        """Fetch a batch of transactions in parallel.

        Uses asyncio.gather with semaphore limiting concurrency.

        Args:
            txids: List of transaction IDs

        Returns:
            List of transaction dicts (None entries filtered out)
        """
        tasks = [self.get_tx(txid) for txid in txids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter successful results
        return [
            tx for tx in results if tx is not None and not isinstance(tx, Exception)
        ]

    async def get_block_txs_paginated(self, block_hash: str) -> list[dict]:
        """Fetch all transactions using paginated endpoint (25 per page).

        This is much faster than fetching individual transactions:
        - 4000 txs = 160 requests vs 4000 requests

        Args:
            block_hash: Block hash

        Returns:
            List of transaction dicts
        """
        all_txs: list[dict] = []
        start_index = 0
        page_size = 25  # electrs returns 25 txs per page

        while True:
            url = f"{self.config.base_url}/block/{block_hash}/txs/{start_index}"
            try:
                txs = await self._retry_with_backoff(self._get_json, url)
                if not txs:
                    break
                all_txs.extend(txs)
                if len(txs) < page_size:
                    break
                start_index += page_size
            except Exception as e:
                logger.warning(f"Failed to fetch txs at offset {start_index}: {e}")
                break

        return all_txs

    async def get_block_async(self, height: int) -> dict:
        """Fetch complete block data with all transactions.

        This is the main entry point for fetching block data.
        Returns data in format compatible with sync_utxo_lifecycle.py.

        Uses paginated endpoint for efficiency (25 txs per request vs 1).

        Args:
            height: Block height

        Returns:
            Block dict with format:
            {
                "height": int,
                "time": int (unix timestamp),
                "tx": [
                    {
                        "txid": str,
                        "vout": [{"value": float (BTC), "n": int, ...}],
                        "vin": [{"prevout": {...}, ...}]
                    },
                    ...
                ]
            }
        """
        logger.debug(f"Fetching block {height}...")

        # Step 1: Get block hash
        block_hash = await self.get_block_hash(height)
        block_hash = block_hash.strip()

        # Step 2: Get block metadata (timestamp)
        block_meta = await self.get_block_meta(block_hash)
        block_time = block_meta.get("timestamp", 0)

        # Step 3: Fetch all transactions using paginated endpoint (25 per page)
        # This is much faster than fetching individual txs
        all_txs = await self.get_block_txs_paginated(block_hash)

        logger.info(f"Block {height}: fetched {len(all_txs)} transactions")

        # Step 5: Convert to sync_utxo_lifecycle format
        # electrs returns value in satoshi, we convert to BTC
        converted_txs = []
        for tx in all_txs:
            converted_tx = {
                "txid": tx["txid"],
                "vout": [],
                "vin": [],
            }

            # Convert vout: satoshi -> BTC, add index
            for i, vout in enumerate(tx.get("vout", [])):
                converted_vout = {
                    "value": vout.get("value", 0) / 100_000_000,  # satoshi -> BTC
                    "n": i,
                }
                # Preserve scriptpubkey_address if present
                if "scriptpubkey_address" in vout:
                    converted_vout["scriptpubkey_address"] = vout[
                        "scriptpubkey_address"
                    ]
                converted_tx["vout"].append(converted_vout)

            # Copy vin as-is (prevout already included by electrs)
            for vin in tx.get("vin", []):
                converted_vin = dict(vin)
                # Convert prevout value if present
                if "prevout" in converted_vin and converted_vin["prevout"]:
                    prevout = converted_vin["prevout"]
                    if "value" in prevout:
                        prevout["value"] = prevout["value"] / 100_000_000
                converted_tx["vin"].append(converted_vin)

            converted_txs.append(converted_tx)

        return {
            "height": height,
            "time": block_time,
            "hash": block_hash,
            "tx": converted_txs,
        }

    async def get_blocks_batch_async(
        self,
        heights: list[int],
        max_concurrent_blocks: int = 3,  # Reduced from 5: optimal for local electrs
    ) -> list[dict]:
        """Fetch multiple blocks in parallel.

        Uses a separate semaphore for block-level concurrency to prevent
        overwhelming electrs when each block spawns many TX requests.

        NOTE: Benchmarking showed workers=10 is 2x slower than workers=5 due to
        electrs contention. The default of 3 concurrent blocks is optimal.

        Args:
            heights: List of block heights to fetch
            max_concurrent_blocks: Max blocks to fetch simultaneously (default: 3)

        Returns:
            List of block dicts (same format as get_block_async)
        """
        logger.info(
            f"Fetching {len(heights)} blocks (max {max_concurrent_blocks} concurrent)..."
        )

        block_semaphore = asyncio.Semaphore(max_concurrent_blocks)

        async def fetch_with_limit(height: int) -> dict | None:
            async with block_semaphore:
                try:
                    return await self.get_block_async(height)
                except Exception as e:
                    logger.error(f"Failed to fetch block {height}: {e}")
                    return None

        tasks = [fetch_with_limit(h) for h in heights]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter successful results and preserve order
        blocks = []
        for i, result in enumerate(results):
            if result is not None and not isinstance(result, Exception):
                blocks.append(result)
            else:
                logger.warning(f"Block {heights[i]} failed or returned None")

        logger.info(f"Successfully fetched {len(blocks)}/{len(heights)} blocks")
        return blocks


async def get_current_block_height(config: ElectrsConfig | None = None) -> int:
    """Get current blockchain tip height from electrs.

    Convenience function for getting tip without full client context.

    Args:
        config: Optional ElectrsConfig

    Returns:
        Current block height
    """
    config = config or ElectrsConfig.from_env()

    async with aiohttp.ClientSession() as session:
        url = f"{config.base_url}/blocks/tip/height"
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            response.raise_for_status()
            text = await response.text()
            return int(text.strip())


# Convenience function for one-off block fetches
async def fetch_block(height: int, config: ElectrsConfig | None = None) -> dict:
    """Fetch a single block (convenience wrapper).

    Creates a temporary client context for one-off fetches.
    For multiple blocks, use ElectrsAsyncClient directly.

    Args:
        height: Block height
        config: Optional ElectrsConfig

    Returns:
        Block dict
    """
    async with ElectrsAsyncClient(config) as client:
        return await client.get_block_async(height)


# Convenience function for batch block fetches
async def fetch_blocks(
    heights: list[int],
    config: ElectrsConfig | None = None,
    max_concurrent_blocks: int = 5,
) -> list[dict]:
    """Fetch multiple blocks (convenience wrapper).

    Args:
        heights: List of block heights
        config: Optional ElectrsConfig
        max_concurrent_blocks: Max parallel block fetches

    Returns:
        List of block dicts
    """
    async with ElectrsAsyncClient(config) as client:
        return await client.get_blocks_batch_async(heights, max_concurrent_blocks)
