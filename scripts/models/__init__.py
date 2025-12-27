"""
Custom Price Models Framework (spec-036)

Provides a unified interface for Bitcoin valuation models:
- PriceModel ABC and ModelPrediction dataclass
- ModelRegistry for model discovery and instantiation
- Built-in models: Power Law, Stock-to-Flow, Thermocap, UTXOracle
- EnsembleModel for combining multiple models
- ModelBacktester for walk-forward backtesting
"""

# Base classes (Phase 3: US1)
from scripts.models.base import ModelPrediction, PriceModel

# Registry (Phase 4: US2)
from scripts.models.registry import ModelRegistry

# Built-in models (Phase 5: US3)
# Import and auto-register on module load
from scripts.models.power_law_adapter import PowerLawAdapter
from scripts.models.stock_to_flow import StockToFlowModel
from scripts.models.thermocap import ThermocapModel
from scripts.models.utxoracle_model import UTXOracleModel

# Ensemble (Phase 6: US4)
from scripts.models.ensemble import EnsembleConfig, EnsembleModel

# Register all built-in models
ModelRegistry.register(PowerLawAdapter)
ModelRegistry.register(StockToFlowModel)
ModelRegistry.register(ThermocapModel)
ModelRegistry.register(UTXOracleModel)

__all__ = [
    # Base classes
    "PriceModel",
    "ModelPrediction",
    # Registry
    "ModelRegistry",
    # Built-in models
    "PowerLawAdapter",
    "StockToFlowModel",
    "ThermocapModel",
    "UTXOracleModel",
    # Ensemble
    "EnsembleModel",
    "EnsembleConfig",
]
