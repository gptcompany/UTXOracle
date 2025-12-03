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
import time
from typing import Tuple, List, Dict, Set, Optional
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


async def _retry_with_backoff(
    func, *args, max_retries: int = 3, base_delay: float = 1.0, **kwargs
):
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        *args: Positional arguments for func
        max_retries: Maximum retry attempts (default: 3)
        base_delay: Base delay in seconds (default: 1.0)
        **kwargs: Keyword arguments for func

    Returns:
        Result from func

    Raises:
        Last exception if all retries fail
    """
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
                logger.error(
                    f"All {max_retries} retry attempts failed. Last error: {e}"
                )

    raise last_exception


class WhaleFlowDetector:
    """
    Async whale flow detector using electrs HTTP API with aiohttp + batching.

    Performance:
    - Batched async processing (100 tx/batch, 50 concurrent per batch)
    - ~84 seconds for 3190 tx block (vs ~180 seconds sequential)
    - Rust-aligned: async/await pattern maps directly to Tokio
    """

    def __init__(
        self,
        exchange_addresses_path: str,
        bitcoin_rpc_url: Optional[str] = None,
        bitcoin_rpc_user: Optional[str] = None,
        bitcoin_rpc_password: Optional[str] = None,
    ):
        """
        Initialize whale flow detector with exchange addresses.

        T085: Added Bitcoin Core RPC fallback support (Tier 3 cascade).

        Args:
            exchange_addresses_path: Path to CSV file (exchange_name,address,type)
            bitcoin_rpc_url: Optional Bitcoin Core RPC URL (default: http://localhost:8332)
            bitcoin_rpc_user: Optional RPC username (if not using cookie auth)
            bitcoin_rpc_password: Optional RPC password (if not using cookie auth)

        Raises:
            FileNotFoundError: If CSV doesn't exist
            ValueError: If CSV format is invalid
        """
        self._exchange_addresses_path = Path(exchange_addresses_path)
        self._exchange_addresses = self._load_exchange_addresses()

        # T085: Bitcoin Core RPC fallback configuration
        self._bitcoin_rpc_url = bitcoin_rpc_url or "http://localhost:8332"
        self._bitcoin_rpc_user = bitcoin_rpc_user
        self._bitcoin_rpc_password = bitcoin_rpc_password
        self._bitcoin_rpc_enabled = bitcoin_rpc_url is not None or (
            bitcoin_rpc_user and bitcoin_rpc_password
        )

        logger.info(
            f"WhaleFlowDetector initialized with {len(self._exchange_addresses)} "
            f"exchange addresses"
        )
        if self._bitcoin_rpc_enabled:
            logger.info(f"Bitcoin Core RPC fallback enabled: {self._bitcoin_rpc_url}")
        else:
            logger.info("Bitcoin Core RPC fallback disabled (electrs only)")

    def _load_exchange_addresses(self) -> Set[str]:
        """
        Load exchange addresses from CSV into a set for O(1) lookup.

        T083: Enhanced error handling for malformed CSV
        T084: Validation for minimum address count (warns if <100)

        Returns:
            Set of Bitcoin addresses belonging to exchanges

        Raises:
            FileNotFoundError: If CSV doesn't exist
            ValueError: If CSV format is invalid or empty
        """
        if not self._exchange_addresses_path.exists():
            raise FileNotFoundError(
                f"Exchange addresses CSV not found: {self._exchange_addresses_path}\n"
                f"Please download from: https://gist.github.com/f13end/bf88acb162bed0b3dcf5e35f1fdb3c17"
            )

        addresses = set()
        row_count = 0
        invalid_rows = []

        try:
            with open(self._exchange_addresses_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                # Validate headers (T083: Better error messages)
                expected_headers = {"exchange_name", "address", "type"}
                actual_headers = set(reader.fieldnames or [])

                if not expected_headers.issubset(actual_headers):
                    missing = expected_headers - actual_headers
                    raise ValueError(
                        f"CSV missing required headers: {missing}\n"
                        f"Expected: {expected_headers}\n"
                        f"Found: {actual_headers}"
                    )

                # Load addresses with validation (T083: Track invalid rows)
                for line_num, row in enumerate(
                    reader, start=2
                ):  # Start at 2 (header is line 1)
                    row_count += 1

                    try:
                        address = row["address"].strip()
                        exchange = row.get("exchange_name", "unknown").strip()

                        if not address:
                            invalid_rows.append((line_num, "empty address"))
                            continue

                        # Basic Bitcoin address validation (length check)
                        if not (25 <= len(address) <= 62):
                            invalid_rows.append(
                                (line_num, f"invalid address length: {len(address)}")
                            )
                            logger.debug(
                                f"Skipping invalid address on line {line_num}: {address}"
                            )
                            continue

                        addresses.add(address)
                        logger.debug(
                            f"Loaded address from {exchange}: {address[:8]}...{address[-8:]}"
                        )

                    except KeyError as e:
                        invalid_rows.append((line_num, f"missing column: {e}"))

        except csv.Error as e:
            raise ValueError(
                f"Malformed CSV file at {self._exchange_addresses_path}: {e}\n"
                f"Please check file format (should be: exchange_name,address,type)"
            )
        except UnicodeDecodeError as e:
            raise ValueError(f"CSV encoding error: {e}\nFile must be UTF-8 encoded")
        except Exception as e:
            raise ValueError(f"Failed to parse CSV: {e.__class__.__name__}: {e}")

        # Report invalid rows (T083)
        if invalid_rows:
            logger.warning(
                f"Skipped {len(invalid_rows)} invalid rows out of {row_count} total"
            )
            if logger.isEnabledFor(logging.DEBUG):
                for line_num, reason in invalid_rows[:10]:  # Show first 10
                    logger.debug(f"  Line {line_num}: {reason}")

        # Validation checks
        if len(addresses) == 0:
            raise ValueError(
                f"CSV contains no valid addresses (processed {row_count} rows, "
                f"found {len(invalid_rows)} invalid)"
            )

        # T084: Warn if address count is below recommended threshold
        MIN_RECOMMENDED_ADDRESSES = 100
        if len(addresses) < MIN_RECOMMENDED_ADDRESSES:
            logger.warning(
                f"⚠️  Only {len(addresses)} exchange addresses loaded "
                f"(recommended: {MIN_RECOMMENDED_ADDRESSES}+)\n"
                f"   Lower coverage may reduce detection accuracy.\n"
                f"   Consider updating exchange_addresses.csv from:\n"
                f"   https://gist.github.com/f13end/bf88acb162bed0b3dcf5e35f1fdb3c17"
            )
        else:
            logger.info(
                f"✓ Loaded {len(addresses)} exchange addresses "
                f"({len(invalid_rows)} invalid rows skipped)"
            )

        return addresses

    def _parse_addresses(self, tx: Dict) -> Tuple[List[str], List[str]]:
        """
        Extract input and output addresses from a transaction.

        T077: Enhanced with DEBUG-level logging for transaction details.

        Args:
            tx: Transaction dict from electrs API

        Returns:
            Tuple of (input_addresses, output_addresses)
        """
        input_addrs = []
        output_addrs = []
        txid = tx.get("txid", "unknown")[:16]  # First 16 chars for logging

        # Parse inputs (from prevout)
        for idx, vin in enumerate(tx.get("vin", [])):
            # Skip coinbase transactions (mining rewards)
            if "coinbase" in vin:
                logger.debug(f"  TX {txid}: vin[{idx}] is coinbase (skip)")
                continue

            prevout = vin.get("prevout")
            if prevout is None:
                logger.debug(f"  TX {txid}: vin[{idx}] has no prevout (skip)")
                continue

            addr = prevout.get("scriptpubkey_address")
            if addr:
                input_addrs.append(addr)
                logger.debug(
                    f"  TX {txid}: vin[{idx}] → {addr[:8]}...{addr[-8:]} "
                    f"({prevout.get('value', 0) / 1e8:.8f} BTC)"
                )

        # Parse outputs
        for idx, vout in enumerate(tx.get("vout", [])):
            addr = vout.get("scriptpubkey_address")
            value_btc = vout.get("value", 0) / 1e8

            if addr:
                output_addrs.append(addr)
                logger.debug(
                    f"  TX {txid}: vout[{idx}] → {addr[:8]}...{addr[-8:]} "
                    f"({value_btc:.8f} BTC)"
                )

        logger.debug(
            f"TX {txid}: Parsed {len(input_addrs)} inputs, {len(output_addrs)} outputs"
        )

        return input_addrs, output_addrs

    def _classify_transaction(
        self, input_addrs: List[str], output_addrs: List[str]
    ) -> Tuple[str, int]:
        """
        Classify transaction flow type based on exchange address involvement.

        T077: Enhanced with DEBUG-level logging for classification logic.

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

        # Count exchange addresses for logging
        input_exchange_count = sum(
            1 for addr in input_addrs if addr in self._exchange_addresses
        )
        output_exchange_count = sum(
            1 for addr in output_addrs if addr in self._exchange_addresses
        )

        logger.debug(
            f"    Classification: {input_exchange_count}/{len(input_addrs)} inputs from exchange, "
            f"{output_exchange_count}/{len(output_addrs)} outputs to exchange"
        )

        if not input_is_exchange and output_is_exchange:
            # Personal → Exchange (deposit to sell)
            logger.debug("    → INFLOW (personal → exchange, bearish)")
            return "inflow", 1

        if input_is_exchange and not output_is_exchange:
            # Exchange → Personal (withdrawal to hold)
            logger.debug("    → OUTFLOW (exchange → personal, bullish)")
            return "outflow", -1

        if input_is_exchange and output_is_exchange:
            # Exchange → Exchange (internal hot/cold wallet movement)
            logger.debug("    → INTERNAL (exchange → exchange, neutral)")
            return "internal", 0

        # Personal → Personal (unrelated to exchanges)
        logger.debug("    → UNRELATED (personal → personal, neutral)")
        return "unrelated", 0

    def _calculate_net_flow(
        self, transactions: List[Dict]
    ) -> Tuple[float, float, float, Dict[str, Tuple[List[str], List[str]]]]:
        """
        Calculate net BTC flow for a set of transactions.

        PERFORMANCE OPTIMIZED: Also returns parsed addresses to avoid re-parsing.

        Args:
            transactions: List of transaction dicts from electrs API

        Returns:
            Tuple of (inflow_btc, outflow_btc, internal_btc, address_cache)
            where address_cache = {txid: (input_addrs, output_addrs)}
        """
        inflow_btc = 0.0
        outflow_btc = 0.0
        internal_btc = 0.0
        address_cache = {}  # Cache parsed addresses to avoid re-parsing

        for tx in transactions:
            txid = tx.get("txid", "")
            input_addrs, output_addrs = self._parse_addresses(tx)
            address_cache[txid] = (input_addrs, output_addrs)  # Cache for later use

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

        return inflow_btc, outflow_btc, internal_btc, address_cache

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

        T078: Enhanced with retry logic (3 retries, exponential backoff: 1s/2s/4s)

        Args:
            session: aiohttp ClientSession (must be created by caller)
            block_hash: Bitcoin block hash
            batch_size: Number of transactions per batch (default: 100)
            concurrent_per_batch: Max concurrent requests per batch (default: 50)

        Returns:
            List of transaction dicts

        Raises:
            ConnectionError: If electrs API is unavailable after all retries

        Performance:
            - 3190 tx block: ~84 seconds (vs ~180 seconds sequential)
            - Batching prevents event loop overload from too many simultaneous tasks
        """

        async def fetch_txids():
            """Helper to fetch transaction IDs with timeout."""
            url = f"{ELECTRS_API_URL}/block/{block_hash}/txids"
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                return await response.json()

        try:
            # T078: Retry transaction ID fetch with exponential backoff
            txids = await _retry_with_backoff(
                fetch_txids, max_retries=3, base_delay=1.0
            )

            logger.info(
                f"Fetching {len(txids)} transactions in batches of {batch_size}..."
            )

            all_transactions = []

            # Create semaphore ONCE for all batches (PERFORMANCE OPTIMIZATION)
            semaphore = asyncio.Semaphore(concurrent_per_batch)

            # Process in batches to avoid overwhelming asyncio.gather()
            for i in range(0, len(txids), batch_size):
                batch = txids[i : i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(txids) - 1) // batch_size + 1

                logger.debug(f"  Batch {batch_num}/{total_batches}: {len(batch)} txids")

                # Fetch batch with semaphore limiting concurrency (reused from above)
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

    async def _fetch_transactions_from_bitcoin_rpc(
        self, session: "aiohttp.ClientSession", block_hash: str
    ) -> List[Dict]:
        """
        T085: Fallback method to fetch transactions via Bitcoin Core RPC (Tier 3).

        This is a fallback when electrs fails. Uses Bitcoin Core RPC to fetch
        block data and transaction details.

        Args:
            session: aiohttp ClientSession
            block_hash: Bitcoin block hash

        Returns:
            List of transaction dicts (converted to electrs-compatible format)

        Raises:
            ConnectionError: If Bitcoin Core RPC is unavailable or disabled
        """
        if not self._bitcoin_rpc_enabled:
            raise ConnectionError(
                "Bitcoin Core RPC fallback is disabled. "
                "Enable by providing bitcoin_rpc_url in constructor."
            )

        logger.warning(
            f"⚠️  Falling back to Bitcoin Core RPC (electrs failed) for block {block_hash[:16]}..."
        )

        try:
            # Prepare RPC authentication
            auth = None
            if self._bitcoin_rpc_user and self._bitcoin_rpc_password:
                auth = aiohttp.BasicAuth(
                    self._bitcoin_rpc_user, self._bitcoin_rpc_password
                )

            # RPC call to get block with full transaction details
            rpc_payload = {
                "jsonrpc": "1.0",
                "id": "whale_detector",
                "method": "getblock",
                "params": [block_hash, 2],  # Verbosity 2 = full tx details
            }

            async with session.post(
                self._bitcoin_rpc_url,
                json=rpc_payload,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=30),  # RPC can be slower
            ) as response:
                response.raise_for_status()
                rpc_result = await response.json()

            if "error" in rpc_result and rpc_result["error"] is not None:
                raise ConnectionError(
                    f"Bitcoin RPC error: {rpc_result['error'].get('message', 'unknown')}"
                )

            block_data = rpc_result.get("result", {})
            raw_txs = block_data.get("tx", [])

            # Convert Bitcoin Core RPC format to electrs-compatible format
            transactions = []
            for raw_tx in raw_txs:
                # Convert to electrs format (simplified, only fields we need)
                tx = {
                    "txid": raw_tx.get("txid", ""),
                    "vin": [],
                    "vout": [],
                }

                # Convert inputs (vin)
                for vin in raw_tx.get("vin", []):
                    if "coinbase" in vin:
                        tx["vin"].append({"coinbase": vin["coinbase"]})
                    else:
                        # For RPC, we need to fetch prevout details separately
                        # Simplified: just mark as unknown (limitation of RPC fallback)
                        tx["vin"].append(
                            {
                                "txid": vin.get("txid", ""),
                                "vout": vin.get("vout", 0),
                                "prevout": {
                                    "scriptpubkey_address": None,  # Unknown without extra RPC call
                                    "value": 0,
                                },
                            }
                        )

                # Convert outputs (vout)
                for vout in raw_tx.get("vout", []):
                    script_pub_key = vout.get("scriptPubKey", {})
                    addresses = script_pub_key.get("addresses", [])
                    address = addresses[0] if addresses else None

                    # RPC uses "address" field in newer versions
                    if not address and "address" in script_pub_key:
                        address = script_pub_key["address"]

                    tx["vout"].append(
                        {
                            "scriptpubkey_address": address,
                            "value": int(vout.get("value", 0) * 1e8),  # BTC to satoshis
                        }
                    )

                transactions.append(tx)

            logger.warning(
                f"✓ Bitcoin Core RPC fallback successful: {len(transactions)} transactions fetched"
            )
            return transactions

        except aiohttp.ClientError as e:
            raise ConnectionError(f"Bitcoin Core RPC failed: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error in Bitcoin RPC fallback: {e}")

    def _analyze_transactions(
        self, transactions: List[Dict], block_height: int, timestamp: int
    ) -> WhaleFlowSignal:
        """
        Analyze a list of transactions and generate whale flow signal.

        PERFORMANCE OPTIMIZED: Uses cached address parsing from _calculate_net_flow.

        Args:
            transactions: List of transaction dicts
            block_height: Bitcoin block height
            timestamp: Block timestamp (Unix epoch)

        Returns:
            WhaleFlowSignal with flow metrics
        """
        # Calculate flows (returns address cache to avoid re-parsing)
        inflow_btc, outflow_btc, internal_btc, address_cache = self._calculate_net_flow(
            transactions
        )
        net_flow_btc = inflow_btc - outflow_btc

        # Determine direction
        direction = self._determine_direction(net_flow_btc)

        # Calculate confidence using CACHED addresses (no re-parsing!)
        tx_count_relevant = sum(
            1
            for tx in transactions
            if (txid := tx.get("txid", "")) in address_cache
            and any(
                addr in self._exchange_addresses
                for addr in (address_cache[txid][0] + address_cache[txid][1])
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

    async def _analyze_block_with_session(
        self, session: "aiohttp.ClientSession", block_height: int
    ) -> WhaleFlowSignal:
        """
        Analyze whale flow for a specific Bitcoin block using an existing session (ASYNC).

        T078: Enhanced with retry logic for block hash and metadata fetches.
        T080: Enhanced with performance metrics tracking.

        PERFORMANCE OPTIMIZED: Reuses aiohttp session instead of creating new one.

        Args:
            session: Existing aiohttp ClientSession (for connection pooling)
            block_height: Bitcoin block number

        Returns:
            WhaleFlowSignal

        Raises:
            ConnectionError: If electrs unavailable after retries
            ValueError: If block_height invalid
            RuntimeError: If analysis fails
        """
        start_time = time.time()  # T080: Performance tracking

        async def fetch_block_hash():
            """Helper to fetch block hash with timeout (for retry)."""
            url = f"{ELECTRS_API_URL}/block-height/{block_height}"
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                return (await response.text()).strip()

        async def fetch_block_metadata(block_hash: str):
            """Helper to fetch block metadata (for retry)."""
            block_url = f"{ELECTRS_API_URL}/block/{block_hash}"
            async with session.get(
                block_url, timeout=aiohttp.ClientTimeout(total=10)
            ) as block_response:
                block_response.raise_for_status()
                return await block_response.json()

        try:
            # T078: Get block hash with retry
            block_hash = await _retry_with_backoff(
                fetch_block_hash, max_retries=3, base_delay=1.0
            )
            logger.info(f"Block {block_height}: hash = {block_hash[:16]}...")

            # T078: Get block details with retry
            block_data = await _retry_with_backoff(
                fetch_block_metadata, block_hash, max_retries=3, base_delay=1.0
            )
            timestamp = block_data.get("timestamp", 0)

            # T085: Fetch transactions with fallback cascade (electrs → Bitcoin RPC)
            tx_fetch_start = time.time()  # T080: Track tx fetch time
            transactions = []
            electrs_failed = False

            try:
                # Try electrs first (Tier 1 - primary)
                transactions = await self._fetch_transactions_from_electrs(
                    session, block_hash
                )
            except ConnectionError as e:
                electrs_failed = True
                logger.warning(f"Electrs failed for block {block_height}: {e}")

                # T085: Fallback to Bitcoin Core RPC (Tier 3)
                if self._bitcoin_rpc_enabled:
                    logger.info("Attempting Bitcoin Core RPC fallback...")
                    try:
                        transactions = await _retry_with_backoff(
                            self._fetch_transactions_from_bitcoin_rpc,
                            session,
                            block_hash,
                            max_retries=3,
                            base_delay=1.0,
                        )
                    except Exception as rpc_error:
                        raise ConnectionError(
                            f"Both electrs and Bitcoin RPC failed: {rpc_error}"
                        )
                else:
                    raise ConnectionError(
                        f"Electrs failed and Bitcoin RPC fallback is disabled: {e}"
                    )

            tx_fetch_duration = time.time() - tx_fetch_start

            # Analyze transactions (synchronous analysis)
            analysis_start = time.time()
            signal = self._analyze_transactions(transactions, block_height, timestamp)
            analysis_duration = time.time() - analysis_start

            # T080: Log performance metrics
            total_duration = time.time() - start_time
            logger.info(
                f"Block {block_height} analysis complete: "
                f"{len(transactions)} tx in {total_duration:.2f}s "
                f"(fetch: {tx_fetch_duration:.2f}s, analysis: {analysis_duration:.2f}s)"
            )

            return signal

        except aiohttp.ClientError as e:
            raise ConnectionError(f"Failed to analyze block {block_height}: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error analyzing block {block_height}: {e}")

    async def analyze_block(self, block_height: int) -> WhaleFlowSignal:
        """
        Analyze whale flow for a specific Bitcoin block (ASYNC).

        NOTE: For batch analysis, use _analyze_block_with_session() with a shared
        session for better performance (avoids recreating HTTP connections).

        Args:
            block_height: Bitcoin block number

        Returns:
            WhaleFlowSignal

        Raises:
            ConnectionError: If electrs unavailable
            ValueError: If block_height invalid
            RuntimeError: If analysis fails
        """
        # Create temporary session and delegate to optimized method
        async with aiohttp.ClientSession() as session:
            return await self._analyze_block_with_session(session, block_height)

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

    def shutdown(self):
        """
        T086: Graceful shutdown handler (no-op for stateless detector).

        WhaleFlowDetector is stateless - all data is loaded at init and
        aiohttp sessions are created per-analysis. No persistent state
        to save or connections to close.

        Future: If persistent connections or caching is added, cleanup here.
        """
        logger.info("WhaleFlowDetector shutdown (no cleanup needed - stateless)")


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
