"""Tests for config module.

Tests URL mapping helpers and tolerance lookups.
"""

from validation.framework.config import (
    AVAILABLE_METRICS,
    TOLERANCES,
    URL_MAPPING,
    get_api_endpoint,
    get_our_url,
    get_reference_url,
    get_tolerance,
)


class TestURLHelpers:
    """Tests for URL lookup helper functions."""

    def test_get_our_url_known_metric(self):
        """get_our_url() returns frontend URL for known metric."""
        url = get_our_url("mvrv")
        assert url is not None
        assert "localhost:8080" in url
        assert "mvrv" in url

    def test_get_our_url_unknown_metric(self):
        """get_our_url() returns None for unknown metric."""
        url = get_our_url("nonexistent_metric")
        assert url is None

    def test_get_reference_url_known_metric(self):
        """get_reference_url() returns CheckOnChain URL for known metric."""
        url = get_reference_url("nupl")
        assert url is not None
        assert "checkonchain.com" in url

    def test_get_reference_url_unknown_metric(self):
        """get_reference_url() returns None for unknown metric."""
        url = get_reference_url("nonexistent_metric")
        assert url is None

    def test_get_api_endpoint_known_metric(self):
        """get_api_endpoint() returns API path for known metric."""
        endpoint = get_api_endpoint("sopr")
        assert endpoint is not None
        assert endpoint.startswith("/api/")

    def test_get_api_endpoint_unknown_metric(self):
        """get_api_endpoint() returns None for unknown metric."""
        endpoint = get_api_endpoint("nonexistent_metric")
        assert endpoint is None


class TestToleranceHelpers:
    """Tests for tolerance lookup functions."""

    def test_get_tolerance_known_metric(self):
        """get_tolerance() returns configured tolerance for known metric."""
        tolerance = get_tolerance("mvrv_z")
        assert tolerance == 2.0

    def test_get_tolerance_unknown_metric(self):
        """get_tolerance() returns default 5.0 for unknown metric."""
        tolerance = get_tolerance("nonexistent_metric")
        assert tolerance == 5.0

    def test_get_tolerance_all_metrics(self):
        """get_tolerance() returns valid tolerance for all configured metrics."""
        for metric in TOLERANCES:
            tolerance = get_tolerance(metric)
            assert tolerance >= 0.0


class TestURLMappingConsistency:
    """Tests for URL mapping consistency."""

    def test_available_metrics_matches_url_mapping(self):
        """AVAILABLE_METRICS matches URL_MAPPING keys."""
        assert set(AVAILABLE_METRICS) == set(URL_MAPPING.keys())

    def test_all_url_mappings_have_required_keys(self):
        """All URL mappings have ours, reference, and api keys."""
        for metric, mapping in URL_MAPPING.items():
            assert "ours" in mapping, f"Missing 'ours' for {metric}"
            assert "reference" in mapping, f"Missing 'reference' for {metric}"
            assert "api" in mapping, f"Missing 'api' for {metric}"
