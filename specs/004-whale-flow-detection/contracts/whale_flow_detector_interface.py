"""
Whale Flow Detector - Data Contracts and Interface

This module defines the data structures and interface for whale flow detection.
Following black-box architecture principles, any implementation must conform to
this interface.
"""

from dataclasses import dataclass
from typing import Dict
from abc import ABC, abstractmethod


@dataclass
class WhaleFlowSignal:
    """
    Represents a whale accumulation/distribution signal from a Bitcoin block.

    Attributes:
        net_flow_btc: Net BTC flow to/from exchanges.
                      Positive = inflow (bearish), Negative = outflow (bullish)
        direction: Classification of whale behavior
                   "ACCUMULATION" (net outflow > 100 BTC)
                   "DISTRIBUTION" (net inflow > 100 BTC)
                   "NEUTRAL" (neither threshold met)
        confidence: Signal quality score (0.0 to 1.0)
                    Based on: tx count, address coverage, flow magnitude
        inflow_btc: Total BTC flowing into exchanges (personal → exchange)
        outflow_btc: Total BTC flowing out of exchanges (exchange → personal)
        internal_btc: Total BTC in exchange-to-exchange transfers (ignored in net flow)
        tx_count_total: Total transactions analyzed in block
        tx_count_relevant: Transactions involving exchange addresses
        block_height: Bitcoin block height analyzed
        timestamp: Block timestamp (Unix epoch)
    """

    net_flow_btc: float
    direction: str  # "ACCUMULATION" | "DISTRIBUTION" | "NEUTRAL"
    confidence: float  # 0.0 to 1.0
    inflow_btc: float
    outflow_btc: float
    internal_btc: float
    tx_count_total: int
    tx_count_relevant: int
    block_height: int
    timestamp: int

    def __post_init__(self):
        """Validate signal data after initialization."""
        # Validate direction
        valid_directions = ["ACCUMULATION", "DISTRIBUTION", "NEUTRAL"]
        if self.direction not in valid_directions:
            raise ValueError(
                f"Invalid direction: {self.direction}. "
                f"Must be one of {valid_directions}"
            )

        # Validate confidence range
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got: {self.confidence}"
            )

        # Validate net flow calculation
        expected_net_flow = self.inflow_btc - self.outflow_btc
        if (
            abs(self.net_flow_btc - expected_net_flow) > 0.001
        ):  # Allow for float precision
            raise ValueError(
                f"net_flow_btc ({self.net_flow_btc}) doesn't match "
                f"inflow - outflow ({expected_net_flow})"
            )


class WhaleFlowDetectorInterface(ABC):
    """
    Abstract interface for whale flow detection implementations.

    Any concrete implementation (Python sequential, Python async, Rust, etc.)
    must implement this interface to ensure compatibility with the UTXOracle
    integration service (daily_analysis.py).
    """

    @abstractmethod
    def __init__(self, exchange_addresses_path: str):
        """
        Initialize the whale flow detector.

        Args:
            exchange_addresses_path: Path to CSV file with exchange addresses
                                     Format: exchange_name,address,type

        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If CSV format is invalid
        """
        pass

    @abstractmethod
    def analyze_block(self, block_height: int) -> WhaleFlowSignal:
        """
        Analyze whale flow for a specific Bitcoin block.

        Args:
            block_height: Bitcoin block number to analyze

        Returns:
            WhaleFlowSignal containing net flow, direction, and confidence

        Raises:
            ConnectionError: If electrs or Bitcoin Core RPC unavailable
            ValueError: If block_height is invalid
            RuntimeError: If analysis fails for other reasons

        Performance Target:
            - Process 2,500 tx block in <5 seconds (sequential)
            - Memory usage <100MB
        """
        pass

    @abstractmethod
    def analyze_latest_block(self) -> WhaleFlowSignal:
        """
        Convenience method to analyze the latest confirmed block.

        Returns:
            WhaleFlowSignal for the most recent block

        Raises:
            ConnectionError: If unable to fetch latest block height
            RuntimeError: If analysis fails
        """
        pass

    @abstractmethod
    def get_exchange_address_count(self) -> int:
        """
        Get the number of exchange addresses loaded.

        Returns:
            Count of unique exchange addresses in the lookup set

        Note:
            Used for validation and logging. Should return >100 for production.
        """
        pass


# Type aliases for clarity
TransactionFlow = Dict[str, any]  # Parsed transaction with flow classification
ExchangeAddressSet = set  # Set of exchange Bitcoin addresses for O(1) lookup
