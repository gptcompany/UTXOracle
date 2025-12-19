"""CheckOnChain.com reference data fetcher.

Fetches current metric values from CheckOnChain for baseline comparison.
Implements respectful rate limiting and caching.
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

# Rate limiting: max 1 request per 2 seconds
RATE_LIMIT_SECONDS = 2.0
_last_request_time = 0.0


@dataclass
class CheckOnChainData:
    """Data point from CheckOnChain."""

    metric: str
    value: float
    timestamp: datetime
    source_url: str
    raw_data: Optional[dict] = None


class CheckOnChainFetcher:
    """Fetches reference data from CheckOnChain.com.

    Note: This fetcher respects rate limits and caches data locally
    to minimize requests to the public service.
    """

    # Known CheckOnChain chart data endpoints (Plotly.js JSON)
    ENDPOINTS = {
        "mvrv": "/btconchain/mvrv/mvrv_data.json",
        "nupl": "/btconchain/unrealised_pnl/unrealised_pnl_data.json",
        "sopr": "/btconchain/sopr/sopr_data.json",
        "cdd": "/btconchain/cdd/cdd_data.json",
        "hash_ribbons": "/btconchain/mining_hashribbons/mining_hashribbons_data.json",
        "realized_price": "/btconchain/realised_price/realised_price_data.json",
    }

    BASE_URL = "https://checkonchain.com"

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path("validation/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        global _last_request_time
        elapsed = time.time() - _last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)
        _last_request_time = time.time()

    def _get_cache_path(self, metric: str) -> Path:
        """Get cache file path for a metric."""
        return self.cache_dir / f"{metric}_cache.json"

    def _is_cache_valid(self, cache_path: Path, max_age_hours: int = 1) -> bool:
        """Check if cache is still valid."""
        if not cache_path.exists():
            return False
        mtime = cache_path.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600
        return age_hours < max_age_hours

    def fetch_metric_data(
        self, metric: str, use_cache: bool = True
    ) -> Optional[CheckOnChainData]:
        """Fetch metric data from CheckOnChain.

        Args:
            metric: Metric name (mvrv, nupl, sopr, etc.)
            use_cache: Whether to use cached data if available

        Returns:
            CheckOnChainData or None if fetch failed
        """
        if metric not in self.ENDPOINTS:
            print(f"Unknown metric: {metric}")
            return None

        cache_path = self._get_cache_path(metric)

        # Check cache first
        if use_cache and self._is_cache_valid(cache_path):
            with open(cache_path) as f:
                cached = json.load(f)
            return CheckOnChainData(
                metric=metric,
                value=cached.get("latest_value", 0),
                timestamp=datetime.fromisoformat(cached.get("timestamp", "")),
                source_url=f"{self.BASE_URL}{self.ENDPOINTS[metric]}",
                raw_data=cached.get("raw_data"),
            )

        # Fetch from CheckOnChain
        self._rate_limit()
        url = f"{self.BASE_URL}{self.ENDPOINTS[metric]}"

        try:
            response = httpx.get(url, timeout=30, follow_redirects=True)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"Failed to fetch {metric}: {e}")
            return None

        # Parse Plotly.js data format
        latest_value = self._extract_latest_value(data, metric)

        result = CheckOnChainData(
            metric=metric,
            value=latest_value,
            timestamp=datetime.utcnow(),
            source_url=url,
            raw_data=data,
        )

        # Cache the result
        cache_data = {
            "metric": metric,
            "latest_value": latest_value,
            "timestamp": result.timestamp.isoformat(),
            "raw_data": data,
        }
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)

        return result

    def _extract_latest_value(self, plotly_data: dict, metric: str) -> float:
        """Extract the latest value from Plotly.js JSON data.

        Plotly data format typically has:
        - data[]: array of traces
        - data[n].x: dates
        - data[n].y: values
        """
        try:
            traces = plotly_data.get("data", [])
            if not traces:
                return 0.0

            # Find the main trace (usually first one with y values)
            for trace in traces:
                y_values = trace.get("y", [])
                if y_values:
                    # Get last non-null value
                    for val in reversed(y_values):
                        if val is not None:
                            return float(val)

            return 0.0
        except Exception as e:
            print(f"Error extracting value for {metric}: {e}")
            return 0.0

    def update_baseline(self, metric: str) -> Optional[Path]:
        """Fetch current data and update baseline file.

        Args:
            metric: Metric to update

        Returns:
            Path to updated baseline file or None
        """
        data = self.fetch_metric_data(metric, use_cache=False)
        if not data:
            return None

        baseline_dir = Path("validation/baselines")
        baseline_dir.mkdir(parents=True, exist_ok=True)
        baseline_path = baseline_dir / f"{metric}_baseline.json"

        baseline = {
            "metric": metric,
            "source": "checkonchain.com",
            "captured_at": data.timestamp.isoformat(),
            "current": {
                f"{metric}_value": data.value,
            },
            "source_url": data.source_url,
        }

        with open(baseline_path, "w") as f:
            json.dump(baseline, f, indent=2)

        return baseline_path

    def update_all_baselines(self) -> list[Path]:
        """Update baselines for all known metrics."""
        updated = []
        for metric in self.ENDPOINTS:
            print(f"Fetching {metric}...")
            path = self.update_baseline(metric)
            if path:
                updated.append(path)
                print(f"  ✓ Updated {path}")
            else:
                print(f"  ✗ Failed to update {metric}")
        return updated
