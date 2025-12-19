"""CheckOnChain.com reference data fetcher.

Fetches current metric values from CheckOnChain for baseline comparison.
Implements respectful rate limiting and caching.

Note: CheckOnChain charts are hosted on charts.checkonchain.com subdomain.
Data is embedded as Plotly.js JSON within HTML pages.
"""

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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

    Charts are hosted on charts.checkonchain.com subdomain.
    Plotly.js data is embedded in HTML pages.
    """

    # CheckOnChain chart pages (HTML with embedded Plotly.js data)
    # Structure: /btconchain/{category}/{metric}/{metric}_light.html
    # Updated 2025-12-19 with verified URLs
    ENDPOINTS = {
        "mvrv": "/btconchain/unrealised/mvrv_all/mvrv_all_light.html",
        "nupl": "/btconchain/unrealised/nupl/nupl_light.html",
        "sopr": "/btconchain/realised/sopr/sopr_light.html",
        "cdd": "/btconchain/lifespan/cdd/cdd_light.html",
        "hash_ribbons": "/btconchain/mining/hashribbons/hashribbons_light.html",
        "cost_basis": "/btconchain/pricing/pricing_yearlycostbasis/pricing_yearlycostbasis_light.html",
        "puell_multiple": "/btconchain/mining/puellmultiple/puellmultiple_light.html",
    }

    # Visual comparison URLs (for screenshot validation)
    VISUAL_URLS = {
        "mvrv": "https://charts.checkonchain.com/btconchain/unrealised/mvrv_all/mvrv_all_light.html",
        "nupl": "https://charts.checkonchain.com/btconchain/unrealised/nupl/nupl_light.html",
        "sopr": "https://charts.checkonchain.com/btconchain/realised/sopr/sopr_light.html",
        "cdd": "https://charts.checkonchain.com/btconchain/lifespan/cdd/cdd_light.html",
        "hash_ribbons": "https://charts.checkonchain.com/btconchain/mining/hashribbons/hashribbons_light.html",
        "cost_basis": "https://charts.checkonchain.com/btconchain/pricing/pricing_yearlycostbasis/pricing_yearlycostbasis_light.html",
    }

    BASE_URL = "https://charts.checkonchain.com"

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

    def _extract_plotly_from_html(self, html_content: str) -> Optional[dict]:
        """Extract Plotly.js data from HTML page.

        CheckOnChain embeds Plotly data in script tags as:
        Plotly.newPlot("uuid", data, layout)
        """
        # Find Plotly.newPlot call - container ID is a UUID
        match = re.search(
            r'Plotly\.newPlot\s*\(\s*["\'][a-f0-9-]+["\']\s*,\s*\[',
            html_content,
        )
        if not match:
            return None

        # Extract the data array using balanced bracket matching
        start_idx = match.end() - 1  # Position of opening '['
        data_str = self._extract_balanced_array(html_content, start_idx)

        if not data_str:
            return None

        try:
            data = json.loads(data_str)
            return {"data": data}
        except json.JSONDecodeError:
            return None

    def _extract_balanced_array(self, text: str, start: int) -> Optional[str]:
        """Extract a balanced JSON array starting at position start."""
        if start >= len(text) or text[start] != "[":
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i in range(start, len(text)):
            char = text[i]

            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        return None

    def _js_to_json(self, js_str: str) -> str:
        """Convert JavaScript object notation to valid JSON."""
        # Remove JavaScript comments
        js_str = re.sub(r"//.*?\n", "\n", js_str)
        js_str = re.sub(r"/\*.*?\*/", "", js_str, flags=re.DOTALL)

        # Handle unquoted keys (property: value -> "property": value)
        js_str = re.sub(r"(\w+)\s*:", r'"\1":', js_str)

        # Handle single quotes -> double quotes
        js_str = js_str.replace("'", '"')

        # Handle trailing commas
        js_str = re.sub(r",\s*([}\]])", r"\1", js_str)

        return js_str

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
            try:
                with open(cache_path) as f:
                    cached = json.load(f)
                timestamp_str = cached.get("timestamp", "")
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str)
                else:
                    timestamp = datetime.now(timezone.utc)
                return CheckOnChainData(
                    metric=metric,
                    value=cached.get("latest_value", 0),
                    timestamp=timestamp,
                    source_url=f"{self.BASE_URL}{self.ENDPOINTS[metric]}",
                    raw_data=cached.get("raw_data"),
                )
            except (json.JSONDecodeError, ValueError):
                # Corrupt cache, fall through to fresh fetch
                pass

        # Fetch from CheckOnChain
        self._rate_limit()
        url = f"{self.BASE_URL}{self.ENDPOINTS[metric]}"

        try:
            response = httpx.get(url, timeout=30, follow_redirects=True)
            response.raise_for_status()

            # Parse HTML to extract Plotly data
            html_content = response.text
            plotly_data = self._extract_plotly_from_html(html_content)

            if not plotly_data:
                print(f"Could not extract Plotly data from {metric} page")
                return None

            data = plotly_data

        except Exception as e:
            print(f"Failed to fetch {metric}: {e}")
            return None

        # Parse Plotly.js data format
        latest_value = self._extract_latest_value(data, metric)

        result = CheckOnChainData(
            metric=metric,
            value=latest_value,
            timestamp=datetime.now(timezone.utc),
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

    def get_visual_url(self, metric: str) -> Optional[str]:
        """Get the visual comparison URL for a metric.

        Use this URL with playwright/chrome-devtools for screenshot comparison.
        """
        return self.VISUAL_URLS.get(metric)

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
            "source": "charts.checkonchain.com",
            "captured_at": data.timestamp.isoformat(),
            "current": {
                f"{metric}_value": data.value,
            },
            "source_url": data.source_url,
            "visual_url": self.get_visual_url(metric),
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
