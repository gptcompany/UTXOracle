"""
Whale Flow Detector - MVP Implementation

Synchronous, simple implementation following KISS principles.
Detects whale accumulation/distribution signals from Bitcoin blocks.

References:
- examples/whale-flow-references/*.py (reference implementations)
- specs/004-whale-flow-detection/contracts/whale_flow_detector_interface.py (interface)
"""

import csv
import logging
import asyncio
import aiohttp
from typing import Tuple, List, Dict, Set
from pathlib import Path

# Add contracts to path for import
import sys

contracts_path = (
    Path(__file__).parent.parent / "specs" / "004-whale-flow-detection" / "contracts"
)
if str(contracts_path) not in sys.path:
    sys.path.insert(0, str(contracts_path))

from whale_flow_detector_interface import WhaleFlowSignal


# Configuration
ELECTRS_API_URL = "http://localhost:3001"
WHALE_ACCUMULATION_THRESHOLD_BTC = -100  # Net outflow > 100 BTC
WHALE_DISTRIBUTION_THRESHOLD_BTC = 100  # Net inflow > 100 BTC

logger = logging.getLogger(__name__)


class WhaleFlowDetector:
    """
    Async whale flow detector using electrs HTTP API with aiohttp + batching.

    Performance:
    - Batched async processing (100 tx/batch, 50 concurrent per batch)
    - ~84 seconds for 3190 tx block (vs ~180 seconds sequential)
    - Rust-aligned: async/await pattern maps directly to Tokio
    """

    def __init__(self, exchange_addresses_path: str):
        """
        Initialize whale flow detector with exchange addresses.

        Args:
            exchange_addresses_path: Path to CSV file (exchange_name,address,type)

        Raises:
            FileNotFoundError: If CSV doesn't exist
            ValueError: If CSV format is invalid
        """
        self._exchange_addresses_path = Path(exchange_addresses_path)
        self._exchange_addresses = self._load_exchange_addresses()

        logger.info(
            f"WhaleFlowDetector initialized with {len(self._exchange_addresses)} "
            f"exchange addresses"
        )

    def _load_exchange_addresses(self) -> Set[str]:
        """
        Load exchange addresses from CSV into a set for O(1) lookup.

        Returns:
            Set of Bitcoin addresses belonging to exchanges

        Raises:
            FileNotFoundError: If CSV doesn't exist
            ValueError: If CSV format is invalid
        """
        if not self._exchange_addresses_path.exists():
            raise FileNotFoundError(
                f"Exchange addresses CSV not found: {self._exchange_addresses_path}"
            )

        addresses = set()

        try:
            with open(self._exchange_addresses_path, "r") as f:
                reader = csv.DictReader(f)

                # Validate headers
                expected_headers = {"exchange_name", "address", "type"}
                if not expected_headers.issubset(set(reader.fieldnames or [])):
                    raise ValueError(f"CSV must contain headers: {expected_headers}")

                # Load addresses
                for row in reader:
                    address = row["address"].strip()
                    if address:
                        addresses.add(address)

        except Exception as e:
            raise ValueError(f"Failed to parse CSV: {e}")

        if len(addresses) == 0:
            raise ValueError("CSV contains no valid addresses")

        return addresses

    def _parse_addresses(self, tx: Dict) -> Tuple[List[str], List[str]]:
        """
        Extract input and output addresses from a transaction.

        Args:
            tx: Transaction dict from electrs API

        Returns:
            Tuple of (input_addresses, output_addresses)
        """
        input_addrs = []
        output_addrs = []

        # Parse inputs (from prevout)
        for vin in tx.get("vin", []):
            # Skip coinbase transactions (mining rewards)
            if "coinbase" in vin:
                continue

            prevout = vin.get("prevout")
            if prevout is None:
                continue  # Skip if no prevout

            addr = prevout.get("scriptpubkey_address")
            if addr:
                input_addrs.append(addr)

        # Parse outputs
        for vout in tx.get("vout", []):
            addr = vout.get("scriptpubkey_address")
            if addr:
                output_addrs.append(addr)

        return input_addrs, output_addrs

    def _classify_transaction(
        self, input_addrs: List[str], output_addrs: List[str]
    ) -> Tuple[str, int]:
        """
        Classify transaction flow type based on exchange address involvement.

        Args:
            input_addrs: List of input addresses
            output_addrs: List of output addresses

        Returns:
            Tuple of (flow_type, direction_multiplier)
            - flow_type: "inflow" | "outflow" | "internal" | "unrelated"
            - direction_multiplier: 1 (bearish), -1 (bullish), 0 (neutral)
        """
        input_is_exchange = any(
            addr in self._exchange_addresses for addr in input_addrs
        )
        output_is_exchange = any(
            addr in self._exchange_addresses for addr in output_addrs
        )

        if not input_is_exchange and output_is_exchange:
            # Personal → Exchange (deposit to sell)
            return "inflow", 1

        if input_is_exchange and not output_is_exchange:
            # Exchange → Personal (withdrawal to hold)
            return "outflow", -1

        if input_is_exchange and output_is_exchange:
            # Exchange → Exchange (internal hot/cold wallet movement)
            return "internal", 0

        # Personal → Personal (unrelated to exchanges)
        return "unrelated", 0

    def _calculate_net_flow(
        self, transactions: List[Dict]
    ) -> Tuple[float, float, float]:
        """
        Calculate net BTC flow for a set of transactions.

        Args:
            transactions: List of transaction dicts from electrs API

        Returns:
            Tuple of (inflow_btc, outflow_btc, internal_btc)
        """
        inflow_btc = 0.0
        outflow_btc = 0.0
        internal_btc = 0.0

        for tx in transactions:
            input_addrs, output_addrs = self._parse_addresses(tx)
            flow_type, _ = self._classify_transaction(input_addrs, output_addrs)

            # Calculate BTC value for this transaction
            for vout in tx.get("vout", []):
                addr = vout.get("scriptpubkey_address")
                value_satoshis = vout.get("value", 0)
                value_btc = value_satoshis / 1e8

                # Only count flows to/from exchange addresses
                if addr in self._exchange_addresses:
                    if flow_type == "inflow":
                        inflow_btc += value_btc
                    elif flow_type == "outflow":
                        # For outflow, count from inputs
                        pass  # Will be calculated below
                    elif flow_type == "internal":
                        internal_btc += value_btc

            # For outflow, sum exchange inputs
            if flow_type == "outflow":
                for vin in tx.get("vin", []):
                    if "prevout" in vin:
                        addr = vin["prevout"].get("scriptpubkey_address")
                        value_satoshis = vin["prevout"].get("value", 0)
                        value_btc = value_satoshis / 1e8

                        if addr in self._exchange_addresses:
                            outflow_btc += value_btc

        return inflow_btc, outflow_btc, internal_btc

    def _determine_direction(self, net_flow_btc: float) -> str:
        """
        Determine whale direction based on net flow.

        Args:
            net_flow_btc: Net BTC flow (inflow - outflow)

        Returns:
            "ACCUMULATION" | "DISTRIBUTION" | "NEUTRAL"
        """
        if net_flow_btc < WHALE_ACCUMULATION_THRESHOLD_BTC:
            return "ACCUMULATION"  # Large outflow = whales withdrawing (bullish)
        elif net_flow_btc > WHALE_DISTRIBUTION_THRESHOLD_BTC:
            return "DISTRIBUTION"  # Large inflow = whales depositing (bearish)
        else:
            return "NEUTRAL"

    async def _fetch_transactions_from_electrs(
        self,
        session: "aiohttp.ClientSession",
        block_hash: str,
        batch_size: int = 100,
        concurrent_per_batch: int = 50,
    ) -> List[Dict]:
        """
        Fetch all transactions for a block from electrs HTTP API (ASYNC with batching).

        Args:
            session: aiohttp ClientSession (must be created by caller)
            block_hash: Bitcoin block hash
            batch_size: Number of transactions per batch (default: 100)
            concurrent_per_batch: Max concurrent requests per batch (default: 50)

        Returns:
            List of transaction dicts

        Raises:
            ConnectionError: If electrs API is unavailable

        Performance:
            - 3190 tx block: ~84 seconds (vs ~180 seconds sequential)
            - Batching prevents event loop overload from too many simultaneous tasks
        """
        try:
            # Get transaction IDs for block
            url = f"{ELECTRS_API_URL}/block/{block_hash}/txids"
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                txids = await response.json()

            logger.info(
                f"Fetching {len(txids)} transactions in batches of {batch_size}..."
            )

            all_transactions = []

            # Process in batches to avoid overwhelming asyncio.gather()
            for i in range(0, len(txids), batch_size):
                batch = txids[i : i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(txids) - 1) // batch_size + 1

                logger.debug(f"  Batch {batch_num}/{total_batches}: {len(batch)} txids")

                # Fetch batch with semaphore limiting concurrency
                semaphore = asyncio.Semaphore(concurrent_per_batch)

                async def fetch_one(txid: str):
                    async with semaphore:
                        try:
                            tx_url = f"{ELECTRS_API_URL}/tx/{txid}"
                            async with session.get(
                                tx_url, timeout=aiohttp.ClientTimeout(total=10)
                            ) as resp:
                                resp.raise_for_status()
                                return await resp.json()
                        except Exception as e:
                            logger.warning(f"Failed to fetch tx {txid}: {e}")
                            return None

                tasks = [fetch_one(txid) for txid in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Filter successful results
                transactions = [
                    tx
                    for tx in results
                    if tx is not None and not isinstance(tx, Exception)
                ]
                all_transactions.extend(transactions)

                logger.debug(
                    f"    Batch complete: {len(transactions)}/{len(batch)} successful"
                )

            logger.info(
                f"Successfully fetched {len(all_transactions)}/{len(txids)} transactions"
            )
            return all_transactions

        except aiohttp.ClientError as e:
            raise ConnectionError(f"Failed to fetch transactions from electrs: {e}")

    def _analyze_transactions(
        self, transactions: List[Dict], block_height: int, timestamp: int
    ) -> WhaleFlowSignal:
        """
        Analyze a list of transactions and generate whale flow signal.

        Args:
            transactions: List of transaction dicts
            block_height: Bitcoin block height
            timestamp: Block timestamp (Unix epoch)

        Returns:
            WhaleFlowSignal with flow metrics
        """
        # Calculate flows
        inflow_btc, outflow_btc, internal_btc = self._calculate_net_flow(transactions)
        net_flow_btc = inflow_btc - outflow_btc

        # Determine direction
        direction = self._determine_direction(net_flow_btc)

        # Calculate confidence (simple heuristic for MVP)
        tx_count_relevant = sum(
            1
            for tx in transactions
            if any(
                addr in self._exchange_addresses
                for addr in (
                    self._parse_addresses(tx)[0] + self._parse_addresses(tx)[1]
                )
            )
        )

        confidence = min(
            1.0, tx_count_relevant / 100.0
        )  # Simple: more tx = higher confidence

        return WhaleFlowSignal(
            net_flow_btc=net_flow_btc,
            direction=direction,
            confidence=confidence,
            inflow_btc=inflow_btc,
            outflow_btc=outflow_btc,
            internal_btc=internal_btc,
            tx_count_total=len(transactions),
            tx_count_relevant=tx_count_relevant,
            block_height=block_height,
            timestamp=timestamp,
        )

    async def analyze_block(self, block_height: int) -> WhaleFlowSignal:
        """
        Analyze whale flow for a specific Bitcoin block (ASYNC).

        Args:
            block_height: Bitcoin block number

        Returns:
            WhaleFlowSignal

        Raises:
            ConnectionError: If electrs unavailable
            ValueError: If block_height invalid
            RuntimeError: If analysis fails
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Get block hash from height
                url = f"{ELECTRS_API_URL}/block-height/{block_height}"
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    response.raise_for_status()
                    block_hash = (await response.text()).strip()

                # Get block details for timestamp
                block_url = f"{ELECTRS_API_URL}/block/{block_hash}"
                async with session.get(
                    block_url, timeout=aiohttp.ClientTimeout(total=10)
                ) as block_response:
                    block_response.raise_for_status()
                    block_data = await block_response.json()
                    timestamp = block_data.get("timestamp", 0)

                # Fetch transactions (uses same session, async with batching)
                transactions = await self._fetch_transactions_from_electrs(
                    session, block_hash
                )

            # Analyze transactions (synchronous analysis)
            return self._analyze_transactions(transactions, block_height, timestamp)

        except aiohttp.ClientError as e:
            raise ConnectionError(f"Failed to analyze block {block_height}: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error analyzing block {block_height}: {e}")

    async def analyze_latest_block(self) -> WhaleFlowSignal:
        """
        Analyze the latest confirmed Bitcoin block (ASYNC).

        Returns:
            WhaleFlowSignal for latest block

        Raises:
            ConnectionError: If unable to fetch latest block
            RuntimeError: If analysis fails
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Get latest block height
                url = f"{ELECTRS_API_URL}/blocks/tip/height"
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    response.raise_for_status()
                    latest_height = int((await response.text()).strip())

            # Analyze using the async analyze_block method
            return await self.analyze_block(latest_height)

        except aiohttp.ClientError as e:
            raise ConnectionError(f"Failed to fetch latest block: {e}")

    def get_exchange_address_count(self) -> int:
        """
        Get count of loaded exchange addresses.

        Returns:
            Number of exchange addresses in lookup set
        """
        return len(self._exchange_addresses)


# CLI for standalone testing
if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Whale Flow Detector")
    parser.add_argument(
        "--block",
        type=int,
        help="Analyze specific block height",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="/media/sam/1TB/UTXOracle/data/exchange_addresses.csv",
        help="Path to exchange addresses CSV",
    )

    args = parser.parse_args()

    detector = WhaleFlowDetector(args.csv)

    # Run async method with asyncio.run()
    if args.block:
        signal = asyncio.run(detector.analyze_block(args.block))
    else:
        signal = asyncio.run(detector.analyze_latest_block())

    print(f"\n🐋 Whale Flow Signal - Block {signal.block_height}")
    print(f"Direction: {signal.direction}")
    print(f"Net Flow: {signal.net_flow_btc:+.2f} BTC")
    print(f"  Inflow:  {signal.inflow_btc:.2f} BTC (to exchanges)")
    print(f"  Outflow: {signal.outflow_btc:.2f} BTC (from exchanges)")
    print(f"  Internal: {signal.internal_btc:.2f} BTC (exchange-to-exchange)")
    print(f"Confidence: {signal.confidence:.2%}")
    print(
        f"Transactions: {signal.tx_count_relevant}/{signal.tx_count_total} relevant\n"
    )
