from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class BundleStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    EMPTY = "empty"
    MISCONFIGURED = "misconfigured"


class BundleMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    schema_version: str = Field(..., description="Schema version identifier, e.g., 'v1'")
    bundle_id: str = Field(..., description="Unique identifier for the bundle type, e.g., 'btc_macro.v1'")
    sequence_id: int = Field(..., description="Monotonic sequence identifier for history and replay")
    produced_at: datetime = Field(..., description="Timestamp when the bundle was produced")
    bundle_status: BundleStatus = Field(..., description="Overall health status of the bundle")
    degraded_reasons: List[str] = Field(default_factory=list, description="List of reasons if bundle is degraded")


class BTCMacroMetricsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    realized_price_usd: Optional[float] = Field(default=None, description="Realized price from BRK")
    liveliness: Optional[float] = Field(default=None, description="Liveliness from BRK")
    reserve_risk: Optional[float] = Field(default=None, description="Reserve risk from BRK")
    nupl: Optional[float] = Field(default=None, description="Net Unrealized Profit/Loss from BRK")
    sopr: Optional[float] = Field(default=None, description="Spent Output Profit Ratio from BRK")


class BTCMacroBundleV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    metadata: BundleMetadata
    metrics: BTCMacroMetricsV1
    source_health: dict = Field(..., description="Details on the upstream source health, e.g., BRK")
