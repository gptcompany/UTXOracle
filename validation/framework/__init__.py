"""UTXOracle Validation Framework.

Professional validation of metric implementations against CheckOnChain.com reference.
"""

from validation.framework.validator import MetricValidator
from validation.framework.comparison_engine import ComparisonEngine

__all__ = ["MetricValidator", "ComparisonEngine"]
