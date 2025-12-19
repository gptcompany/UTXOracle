"""Tests for CheckOnChainFetcher class.

Tests Plotly.js extraction and caching logic.
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch


from validation.framework.checkonchain_fetcher import CheckOnChainFetcher


class TestExtractPlotlyFromHtml:
    """Tests for CheckOnChainFetcher._extract_plotly_from_html() method."""

    def test_extract_plotly_valid_html(self, sample_plotly_html: str, cache_dir: Path):
        """_extract_plotly_from_html() extracts data from valid HTML."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)

        result = fetcher._extract_plotly_from_html(sample_plotly_html)

        assert result is not None
        assert "data" in result
        assert len(result["data"]) == 1
        assert result["data"][0]["name"] == "MVRV Z-Score"
        assert result["data"][0]["y"] == [1.5, 1.6, 1.55]

    def test_extract_plotly_no_plotly_call(self, cache_dir: Path):
        """_extract_plotly_from_html() returns None for HTML without Plotly."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)
        html = "<html><body>No chart here</body></html>"

        result = fetcher._extract_plotly_from_html(html)

        assert result is None

    def test_extract_plotly_malformed_json(self, cache_dir: Path):
        """_extract_plotly_from_html() handles malformed JSON gracefully."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)
        html = """
        <script>
        Plotly.newPlot("550e8400-e29b-41d4-a716-446655440000", [
            {invalid json here}
        ])
        </script>
        """

        result = fetcher._extract_plotly_from_html(html)

        # Should return None on JSON decode error
        assert result is None

    def test_extract_plotly_nested_arrays(self, cache_dir: Path):
        """_extract_plotly_from_html() handles nested arrays."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)
        html = """
        <script>
        Plotly.newPlot("550e8400-e29b-41d4-a716-446655440000", [
            {
                "x": [["2024-01-01"], ["2024-01-02"]],
                "y": [[1.5], [1.6]],
                "type": "scatter"
            }
        ])
        </script>
        """

        result = fetcher._extract_plotly_from_html(html)

        assert result is not None
        assert "data" in result


class TestExtractLatestValue:
    """Tests for CheckOnChainFetcher._extract_latest_value() method."""

    def test_extract_latest_value_simple(self, cache_dir: Path):
        """_extract_latest_value() returns last value from trace."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)
        plotly_data = {"data": [{"x": ["2024-01-01", "2024-01-02"], "y": [1.5, 1.6]}]}

        result = fetcher._extract_latest_value(plotly_data, "mvrv")

        assert result == 1.6

    def test_extract_latest_value_with_nulls(self, cache_dir: Path):
        """_extract_latest_value() skips null values at end."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)
        plotly_data = {
            "data": [
                {"x": ["2024-01-01", "2024-01-02", "2024-01-03"], "y": [1.5, 1.6, None]}
            ]
        }

        result = fetcher._extract_latest_value(plotly_data, "mvrv")

        assert result == 1.6

    def test_extract_latest_value_empty_data(self, cache_dir: Path):
        """_extract_latest_value() returns 0 for empty data."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)

        result = fetcher._extract_latest_value({}, "mvrv")
        assert result == 0.0

        result = fetcher._extract_latest_value({"data": []}, "mvrv")
        assert result == 0.0

        result = fetcher._extract_latest_value({"data": [{"y": []}]}, "mvrv")
        assert result == 0.0

    def test_extract_latest_value_multiple_traces(self, cache_dir: Path):
        """_extract_latest_value() uses first trace with y values."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)
        plotly_data = {
            "data": [
                {"x": ["2024-01-01"], "type": "bar"},  # No y values
                {"x": ["2024-01-01"], "y": [2.5]},  # Has y values
            ]
        }

        result = fetcher._extract_latest_value(plotly_data, "mvrv")

        assert result == 2.5


class TestFetchMetricDataWithCache:
    """Tests for CheckOnChainFetcher.fetch_metric_data() with caching."""

    def test_fetch_uses_valid_cache(self, cache_dir: Path, sample_cache_file: Path):
        """fetch_metric_data() returns cached data when valid."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)

        with patch("httpx.get") as mock_get:
            result = fetcher.fetch_metric_data("mvrv", use_cache=True)

        # Should not make HTTP request
        mock_get.assert_not_called()
        assert result is not None
        assert result.metric == "mvrv"
        assert result.value == 1.55

    def test_fetch_skips_expired_cache(
        self, cache_dir: Path, sample_cache_file: Path, sample_plotly_html: str
    ):
        """fetch_metric_data() fetches fresh data when cache is expired."""
        # Make cache file old
        old_time = time.time() - 7200  # 2 hours ago
        import os

        os.utime(sample_cache_file, (old_time, old_time))

        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)

        mock_response = MagicMock()
        mock_response.text = sample_plotly_html
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response):
            result = fetcher.fetch_metric_data("mvrv", use_cache=True)

        assert result is not None
        # Value from sample_plotly_html
        assert result.value == 1.55

    def test_fetch_bypasses_cache_when_disabled(
        self, cache_dir: Path, sample_cache_file: Path, sample_plotly_html: str
    ):
        """fetch_metric_data() bypasses cache when use_cache=False."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)

        mock_response = MagicMock()
        mock_response.text = sample_plotly_html
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response) as mock_get:
            result = fetcher.fetch_metric_data("mvrv", use_cache=False)

        mock_get.assert_called_once()
        assert result is not None

    def test_fetch_unknown_metric_returns_none(self, cache_dir: Path):
        """fetch_metric_data() returns None for unknown metric."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)

        result = fetcher.fetch_metric_data("unknown_metric")

        assert result is None

    def test_fetch_creates_cache_on_success(
        self, tmp_path: Path, sample_plotly_html: str
    ):
        """fetch_metric_data() creates cache file on successful fetch."""
        cache_dir = tmp_path / "new_cache"
        cache_dir.mkdir()
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)

        mock_response = MagicMock()
        mock_response.text = sample_plotly_html
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response):
            fetcher.fetch_metric_data("mvrv", use_cache=False)

        cache_file = cache_dir / "mvrv_cache.json"
        assert cache_file.exists()

        with open(cache_file) as f:
            cached = json.load(f)
        assert cached["metric"] == "mvrv"
        assert cached["latest_value"] == 1.55


class TestRateLimiting:
    """Tests for rate limiting behavior."""

    def test_rate_limit_enforced(self, cache_dir: Path, sample_plotly_html: str):
        """_rate_limit() enforces minimum delay between requests."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)

        mock_response = MagicMock()
        mock_response.text = sample_plotly_html
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response):
            start = time.time()
            # Make two requests (bypassing cache)
            fetcher.fetch_metric_data("mvrv", use_cache=False)
            fetcher.fetch_metric_data("nupl", use_cache=False)
            elapsed = time.time() - start

        # Should take at least 2 seconds due to rate limit
        assert elapsed >= 2.0


class TestGetVisualUrl:
    """Tests for CheckOnChainFetcher.get_visual_url() method."""

    def test_get_visual_url_known_metric(self, cache_dir: Path):
        """get_visual_url() returns URL for known metrics."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)

        url = fetcher.get_visual_url("mvrv")

        assert url is not None
        assert "charts.checkonchain.com" in url
        assert "mvrv" in url

    def test_get_visual_url_unknown_metric(self, cache_dir: Path):
        """get_visual_url() returns None for unknown metric."""
        fetcher = CheckOnChainFetcher(cache_dir=cache_dir)

        url = fetcher.get_visual_url("unknown_metric")

        assert url is None
