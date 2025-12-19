"""Configuration for validation framework.

Centralized URL mappings and tolerance settings for metric validation.
"""

from pathlib import Path

# Base URLs
API_BASE_URL = "http://localhost:8000"
FRONTEND_BASE_URL = "http://localhost:8080"
CHECKONCHAIN_BASE_URL = "https://charts.checkonchain.com"

# URL mapping for validation targets
# Structure: metric -> {ours: frontend URL, reference: CheckOnChain URL, api: API endpoint}
URL_MAPPING = {
    "mvrv": {
        "ours": f"{FRONTEND_BASE_URL}/metrics/mvrv.html",
        "reference": f"{CHECKONCHAIN_BASE_URL}/btconchain/unrealised/mvrv_all/mvrv_all_light.html",
        "api": "/api/metrics/mvrv",
    },
    "nupl": {
        "ours": f"{FRONTEND_BASE_URL}/metrics/nupl.html",
        "reference": f"{CHECKONCHAIN_BASE_URL}/btconchain/unrealised/nupl/nupl_light.html",
        "api": "/api/metrics/nupl",
    },
    "sopr": {
        "ours": f"{FRONTEND_BASE_URL}/metrics/sopr.html",
        "reference": f"{CHECKONCHAIN_BASE_URL}/btconchain/realised/sopr/sopr_light.html",
        "api": "/api/metrics/pl-ratio",
    },
    "cost_basis": {
        "ours": f"{FRONTEND_BASE_URL}/metrics/cost_basis.html",
        "reference": f"{CHECKONCHAIN_BASE_URL}/btconchain/pricing/pricing_yearlycostbasis/pricing_yearlycostbasis_light.html",
        "api": "/api/metrics/cost-basis",
    },
    "hash_ribbons": {
        "ours": f"{FRONTEND_BASE_URL}/metrics/hash_ribbons.html",
        "reference": f"{CHECKONCHAIN_BASE_URL}/btconchain/mining/hashribbons/hashribbons_light.html",
        "api": "/api/metrics/hash-ribbons",
    },
    "binary_cdd": {
        "ours": f"{FRONTEND_BASE_URL}/metrics/binary_cdd.html",
        "reference": f"{CHECKONCHAIN_BASE_URL}/btconchain/lifespan/cdd_all/cdd_all_light.html",
        "api": "/api/metrics/binary-cdd",
    },
    "cdd": {
        "ours": f"{FRONTEND_BASE_URL}/metrics/binary_cdd.html",
        "reference": f"{CHECKONCHAIN_BASE_URL}/btconchain/lifespan/cdd_all/cdd_all_light.html",
        "api": "/api/metrics/cdd",
    },
}

# Tolerance thresholds (percentage)
TOLERANCES = {
    "mvrv_z": 2.0,  # ±2%
    "nupl": 2.0,  # ±2%
    "sopr": 1.0,  # ±1%
    "sth_sopr": 2.0,  # ±2%
    "lth_sopr": 2.0,  # ±2%
    "cdd": 5.0,  # ±5%
    "binary_cdd": 0.0,  # Exact match (0 or 1)
    "cost_basis": 2.0,  # ±2%
    "hash_ribbons_30d": 3.0,  # ±3%
    "hash_ribbons_60d": 3.0,  # ±3%
}

# Directory paths
VALIDATION_ROOT = Path("validation")
BASELINES_DIR = VALIDATION_ROOT / "baselines"
CACHE_DIR = VALIDATION_ROOT / "cache"
REPORTS_DIR = VALIDATION_ROOT / "reports"
SCREENSHOTS_DIR = VALIDATION_ROOT / "screenshots"
SCREENSHOTS_OURS_DIR = SCREENSHOTS_DIR / "ours"
SCREENSHOTS_REFERENCE_DIR = SCREENSHOTS_DIR / "reference"

# Metrics available for validation
AVAILABLE_METRICS = list(URL_MAPPING.keys())


def get_our_url(metric: str) -> str | None:
    """Get frontend URL for a metric."""
    mapping = URL_MAPPING.get(metric)
    return mapping["ours"] if mapping else None


def get_reference_url(metric: str) -> str | None:
    """Get CheckOnChain reference URL for a metric."""
    mapping = URL_MAPPING.get(metric)
    return mapping["reference"] if mapping else None


def get_api_endpoint(metric: str) -> str | None:
    """Get API endpoint for a metric."""
    mapping = URL_MAPPING.get(metric)
    return mapping["api"] if mapping else None


def get_tolerance(metric: str) -> float:
    """Get tolerance percentage for a metric."""
    return TOLERANCES.get(metric, 5.0)
