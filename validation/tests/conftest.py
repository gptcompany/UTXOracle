"""Test fixtures for validation framework tests.

Provides mock HTTP responses and sample data for testing.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def sample_plotly_html() -> str:
    """Sample HTML with embedded Plotly.js data."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>MVRV Chart</title></head>
    <body>
    <div id="550e8400-e29b-41d4-a716-446655440000"></div>
    <script>
    Plotly.newPlot("550e8400-e29b-41d4-a716-446655440000", [
        {
            "x": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "y": [1.5, 1.6, 1.55],
            "type": "scatter",
            "name": "MVRV Z-Score"
        }
    ], {"title": "MVRV"})
    </script>
    </body>
    </html>
    """


@pytest.fixture
def sample_mvrv_baseline(tmp_path: Path) -> Path:
    """Create sample MVRV baseline file."""
    baseline = {
        "metric": "mvrv",
        "source": "charts.checkonchain.com",
        "captured_at": "2025-12-19T10:00:00+00:00",
        "current": {"mvrv_value": 1.55, "mvrv_z_score": 1.45},
        "source_url": "https://charts.checkonchain.com/btconchain/unrealised/mvrv_all/mvrv_all_light.html",
        "visual_url": "https://charts.checkonchain.com/btconchain/unrealised/mvrv_all/mvrv_all_light.html",
    }
    baseline_path = tmp_path / "baselines" / "mvrv_baseline.json"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    with open(baseline_path, "w") as f:
        json.dump(baseline, f)
    return baseline_path


@pytest.fixture
def sample_nupl_baseline(tmp_path: Path) -> Path:
    """Create sample NUPL baseline file."""
    baseline = {
        "metric": "nupl",
        "source": "charts.checkonchain.com",
        "captured_at": "2025-12-19T10:00:00+00:00",
        "current": {"nupl_value": 0.52, "zone": "belief"},
        "source_url": "https://charts.checkonchain.com/btconchain/unrealised/nupl/nupl_light.html",
        "visual_url": "https://charts.checkonchain.com/btconchain/unrealised/nupl/nupl_light.html",
    }
    baseline_path = tmp_path / "baselines" / "nupl_baseline.json"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    with open(baseline_path, "w") as f:
        json.dump(baseline, f)
    return baseline_path


@pytest.fixture
def sample_hash_ribbons_baseline(tmp_path: Path) -> Path:
    """Create sample Hash Ribbons baseline file."""
    baseline = {
        "metric": "hash_ribbons",
        "source": "charts.checkonchain.com",
        "captured_at": "2025-12-19T10:00:00+00:00",
        "current": {"ma_30d": 750.5, "ma_60d": 720.3, "ribbon_signal": False},
        "source_url": "https://charts.checkonchain.com/btconchain/mining/hashribbons/hashribbons_light.html",
        "visual_url": "https://charts.checkonchain.com/btconchain/mining/hashribbons/hashribbons_light.html",
    }
    baseline_path = tmp_path / "baselines" / "hash_ribbons_baseline.json"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    with open(baseline_path, "w") as f:
        json.dump(baseline, f)
    return baseline_path


@pytest.fixture
def mock_api_response() -> dict[str, Any]:
    """Mock API response data for metrics."""
    return {
        "mvrv": {"mvrv_z_score": 1.45, "mvrv_ratio": 2.1},
        "nupl": {"nupl": 0.52, "zone": "belief"},
        "hash_ribbons": {"hashrate_ma_30d": 750.0, "hashrate_ma_60d": 720.0},
    }


@pytest.fixture
def baselines_dir(
    tmp_path: Path,
    sample_mvrv_baseline: Path,
    sample_nupl_baseline: Path,
    sample_hash_ribbons_baseline: Path,
) -> Path:
    """Get the baselines directory with all sample files."""
    return tmp_path / "baselines"


@pytest.fixture
def mock_httpx_get():
    """Factory for creating mock httpx.get responses."""

    def _create_mock(
        json_data: dict | None = None, text: str | None = None, status_code: int = 200
    ):
        mock = MagicMock()
        mock.status_code = status_code
        mock.raise_for_status = MagicMock()
        if status_code >= 400:
            mock.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
        if json_data:
            mock.json.return_value = json_data
        if text:
            mock.text = text
        return mock

    return _create_mock


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """Create temporary cache directory."""
    cache = tmp_path / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


@pytest.fixture
def sample_cache_file(cache_dir: Path) -> Path:
    """Create sample cache file."""
    cache_data = {
        "metric": "mvrv",
        "latest_value": 1.55,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "raw_data": {
            "data": [
                {
                    "x": ["2024-01-01", "2024-01-02"],
                    "y": [1.5, 1.55],
                    "type": "scatter",
                    "name": "MVRV",
                }
            ]
        },
    }
    cache_path = cache_dir / "mvrv_cache.json"
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)
    return cache_path
