"""
Pydantic models for UTXOracle library v2.

This module provides type-safe data models for the UTXOracle price calculation API.
Models enable:
- Automatic type validation
- IDE autocomplete
- Self-documenting API
- JSON schema generation

T120: Type safety implementation for v2
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field, field_validator


class BitcoinTransaction(BaseModel):
    """
    Bitcoin transaction from RPC or mempool API.

    This model accepts the standard Bitcoin transaction format from either
    Bitcoin Core RPC or mempool.space API.
    """

    txid: str = Field(description="Transaction ID (hex string)")
    vout: List[dict] = Field(description="Transaction outputs")
    vin: List[dict] = Field(description="Transaction inputs")
    time: Optional[int] = Field(None, description="Transaction timestamp (Unix time)")

    class Config:
        extra = "allow"  # Allow additional RPC fields


class DiagnosticsInfo(BaseModel):
    """Transaction filtering diagnostics."""

    total_txs: int = Field(ge=0, description="Total transactions input")
    filtered_inputs: int = Field(ge=0, description="Filtered (>5 inputs)")
    filtered_outputs: int = Field(ge=0, description="Filtered (≠2 outputs)")
    filtered_coinbase: int = Field(ge=0, description="Coinbase transactions")
    filtered_op_return: int = Field(ge=0, description="OP_RETURN transactions")
    filtered_witness: int = Field(ge=0, description="Excessive witness data")
    filtered_same_day: int = Field(ge=0, description="Same-day spending")
    total_filtered: int = Field(ge=0, description="Total transactions filtered")
    passed_filter: int = Field(ge=0, description="Transactions passed filters")

    @field_validator("passed_filter")
    @classmethod
    def validate_passed_filter(cls, v, info):
        """Verify passed_filter matches total - filtered."""
        if info.data.get("total_txs") is not None:
            expected = info.data["total_txs"] - info.data.get("total_filtered", 0)
            if v != expected:
                raise ValueError(
                    f"passed_filter ({v}) != total_txs - total_filtered ({expected})"
                )
        return v


class PriceResult(BaseModel):
    """UTXOracle price calculation result."""

    price_usd: Optional[float] = Field(
        None,
        description="Estimated BTC/USD price (None if calculation failed)",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score (0-1)")
    tx_count: int = Field(ge=0, description="Transactions processed after filtering")
    output_count: int = Field(ge=0, description="Outputs analyzed in histogram")
    histogram: Dict[int, int] = Field(
        default_factory=dict,
        description="Histogram of transaction outputs (bin_index -> count)",
    )
    diagnostics: Optional[DiagnosticsInfo] = Field(
        None,
        description="Filtering diagnostics (if return_diagnostics=True)",
    )

    @field_validator("price_usd")
    @classmethod
    def validate_price_range(cls, v):
        """Verify price is in reasonable range if not None."""
        if v is not None:
            if v < 10_000:
                raise ValueError(f"Price ${v:,.2f} is suspiciously low (< $10k)")
            if v > 500_000:
                raise ValueError(f"Price ${v:,.2f} is suspiciously high (> $500k)")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "price_usd": 110537.54,
                "confidence": 0.87,
                "tx_count": 2345,
                "output_count": 4690,
                "histogram": {},
                "diagnostics": {
                    "total_txs": 3689,
                    "filtered_inputs": 234,
                    "filtered_outputs": 567,
                    "filtered_coinbase": 1,
                    "filtered_op_return": 45,
                    "filtered_witness": 123,
                    "filtered_same_day": 374,
                    "total_filtered": 1344,
                    "passed_filter": 2345,
                },
            }
        }


class IntradayPriceResult(PriceResult):
    """Price result with intraday evolution data."""

    intraday_prices: List[float] = Field(
        default_factory=list,
        description="Intraday price points (convergence evolution)",
    )
    intraday_timestamps: List[int] = Field(
        default_factory=list,
        description="Unix timestamps for each price point",
    )
    intraday_heights: List[int] = Field(
        default_factory=list,
        description="Block heights for each price point",
    )

    @field_validator("intraday_timestamps")
    @classmethod
    def validate_same_length(cls, v, info):
        """Verify all intraday arrays have same length."""
        if "intraday_prices" in info.data:
            prices_len = len(info.data["intraday_prices"])
            if len(v) != prices_len:
                raise ValueError(
                    f"intraday_timestamps length ({len(v)}) != "
                    f"intraday_prices length ({prices_len})"
                )
        return v

    @field_validator("intraday_heights")
    @classmethod
    def validate_heights_length(cls, v, info):
        """Verify intraday_heights matches other arrays."""
        if "intraday_prices" in info.data:
            prices_len = len(info.data["intraday_prices"])
            if len(v) != prices_len:
                raise ValueError(
                    f"intraday_heights length ({len(v)}) != "
                    f"intraday_prices length ({prices_len})"
                )
        return v
