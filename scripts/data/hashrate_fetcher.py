"""Hashrate data fetcher for Hash Ribbons (spec-030).

Fetches hashrate data from mempool.space API with input validation
and TTL caching to minimize API calls.

API Endpoint: https://mempool.space/api/v1/mining/hashrate/1y
"""

import time
from typing import Any

import httpx

# TTL cache configuration
_CACHE_TTL_SECONDS = 300  # 5 minutes
_cache_data: dict[str, Any] = {}
_cache_timestamp: float = 0.0


def validate_hashrate_response(data: dict) -> None:
    """Validate API response structure.

    Args:
        data: Raw API response dict

    Raises:
        ValueError: If response is missing required fields
    """
    if not isinstance(data, dict):
        raise ValueError("Invalid API response: expected dict")

    if "hashrates" not in data:
        raise ValueError("Invalid API response: missing 'hashrates' field")

    if "currentHashrate" not in data:
        raise ValueError("Invalid API response: missing 'currentHashrate' field")

    hashrates = data["hashrates"]
    if not isinstance(hashrates, list):
        raise ValueError("Invalid API response: 'hashrates' must be a list")

    if len(hashrates) == 0:
        raise ValueError("Invalid API response: 'hashrates' is empty")

    # Validate first entry structure
    first = hashrates[0]
    if not isinstance(first, dict):
        raise ValueError("Invalid API response: hashrate entry must be a dict")

    if "timestamp" not in first:
        raise ValueError("Invalid API response: hashrate entry missing 'timestamp'")

    if "avgHashrate" not in first:
        raise ValueError("Invalid API response: hashrate entry missing 'avgHashrate'")


def fetch_hashrate_data(
    base_url: str = "https://mempool.space",
    use_cache: bool = True,
    timeout: float = 30.0,
) -> dict:
    """Fetch hashrate data from mempool.space API.

    Args:
        base_url: Base URL for mempool.space API
        use_cache: Whether to use TTL cache (default True)
        timeout: Request timeout in seconds

    Returns:
        Dict with 'hashrates' list and 'currentHashrate'

    Raises:
        ValueError: If API response is invalid
        httpx.HTTPError: If request fails
    """
    global _cache_data, _cache_timestamp

    # Check cache
    if use_cache and _cache_data:
        age = time.time() - _cache_timestamp
        if age < _CACHE_TTL_SECONDS:
            return _cache_data

    # Fetch from API
    url = f"{base_url}/api/v1/mining/hashrate/1y"
    response = httpx.get(url, timeout=timeout)
    response.raise_for_status()

    data = response.json()

    # Validate response
    validate_hashrate_response(data)

    # Update cache
    if use_cache:
        _cache_data = data
        _cache_timestamp = time.time()

    return data


def clear_cache() -> None:
    """Clear the hashrate cache."""
    global _cache_data, _cache_timestamp
    _cache_data = {}
    _cache_timestamp = 0.0
