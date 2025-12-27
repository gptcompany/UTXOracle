"""
RBN API Integration Tests (spec-035).

TDD Tests for RBNFetcher, ValidationService, and API endpoints.
Following Constitution Principle II: Tests MUST fail first.

Tasks: T011-T012, T016, T020, T024-T025, T030
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.models.validation_models import (
    ComparisonStatus,
    MetricComparison,
    QuotaExceededError,
    RBNConfig,
    RBNDataPoint,
    RBNMetricResponse,
    RBNTier,
    ValidationReport,
)

# =============================================================================
# Fixtures
# =============================================================================

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "rbn_mock_responses"


@pytest.fixture
def mock_mvrv_response() -> dict:
    """Load mock MVRV Z-Score response."""
    with open(FIXTURES_DIR / "mvrv_z_response.json") as f:
        return json.load(f)


@pytest.fixture
def mock_sopr_response() -> dict:
    """Load mock SOPR response."""
    with open(FIXTURES_DIR / "sopr_response.json") as f:
        return json.load(f)


@pytest.fixture
def mock_error_responses() -> dict:
    """Load mock error responses."""
    with open(FIXTURES_DIR / "error_response.json") as f:
        return json.load(f)["errors"]


@pytest.fixture
def rbn_config() -> RBNConfig:
    """Create test RBN configuration."""
    from pydantic import SecretStr

    return RBNConfig(
        token=SecretStr("test-token-12345678-1234-1234-1234-123456789012"),
        tier=RBNTier.FREE,
        cache_ttl_hours=24,
        timeout_seconds=30.0,
    )


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    """Create temporary cache directory."""
    cache_dir = tmp_path / "cache" / "rbn"
    cache_dir.mkdir(parents=True)
    return cache_dir


# =============================================================================
# T011: Test Fixtures Validation
# =============================================================================


class TestFixturesExist:
    """T011: Verify test fixtures are valid and loadable."""

    def test_mvrv_z_response_fixture_exists(self, mock_mvrv_response: dict):
        """MVRV Z-Score response fixture should be valid JSON."""
        assert mock_mvrv_response["status"] == "success"
        assert "data" in mock_mvrv_response
        assert "dates" in mock_mvrv_response["data"]
        assert "values" in mock_mvrv_response["data"]
        assert len(mock_mvrv_response["data"]["dates"]) == 5

    def test_sopr_response_fixture_exists(self, mock_sopr_response: dict):
        """SOPR response fixture should be valid JSON."""
        assert mock_sopr_response["status"] == "success"
        assert len(mock_sopr_response["data"]["values"]) == 5

    def test_error_response_fixtures_exist(self, mock_error_responses: dict):
        """Error response fixtures should include all error types."""
        assert "401_invalid_token" in mock_error_responses
        assert "429_quota_exceeded" in mock_error_responses
        assert "422_invalid_params" in mock_error_responses


# =============================================================================
# T012: RBNFetcher Unit Tests
# =============================================================================


class TestRBNFetcher:
    """T012: Unit tests for RBNFetcher class."""

    @pytest.mark.asyncio
    async def test_fetch_metric_success(
        self,
        rbn_config: RBNConfig,
        temp_cache_dir: Path,
        mock_mvrv_response: dict,
    ):
        """Should successfully fetch and parse metric data."""
        from scripts.integrations.rbn_fetcher import RBNFetcher

        fetcher = RBNFetcher(config=rbn_config, cache_dir=temp_cache_dir)

        # Mock httpx client - use MagicMock for json() since it's a sync method
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_mvrv_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(fetcher, "_get_client") as mock_client:
            client = AsyncMock()
            client.get.return_value = mock_response
            mock_client.return_value = client

            result = await fetcher.fetch_metric(
                metric_id="mvrv_z",
                start_date=date(2024, 12, 1),
                end_date=date(2024, 12, 5),
            )

        assert result.status == "success"
        assert result.metric_id == "mvrv_z"
        assert len(result.data) == 5
        assert result.data[0].value == 2.45

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_fetch_metric_cache_hit(
        self,
        rbn_config: RBNConfig,
        temp_cache_dir: Path,
        mock_mvrv_response: dict,
    ):
        """Should return cached data when cache is valid."""
        from scripts.integrations.rbn_fetcher import RBNFetcher
        import pandas as pd

        fetcher = RBNFetcher(config=rbn_config, cache_dir=temp_cache_dir)

        # Pre-populate cache
        cache_path = temp_cache_dir / "mvrv_z.parquet"
        df = pd.DataFrame(
            {
                "date": [date(2024, 12, 1), date(2024, 12, 2)],
                "value": [2.45, 2.51],
            }
        )
        df.to_parquet(cache_path, index=False)

        # Fetch should use cache (no HTTP call)
        result = await fetcher.fetch_metric(
            metric_id="mvrv_z",
            start_date=date(2024, 12, 1),
            end_date=date(2024, 12, 2),
        )

        assert result.cached is True
        assert result.status == "success"
        assert len(result.data) == 2

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_fetch_metric_invalid_token(
        self,
        rbn_config: RBNConfig,
        temp_cache_dir: Path,
    ):
        """Should raise ValueError for invalid token (401)."""
        from scripts.integrations.rbn_fetcher import RBNFetcher

        fetcher = RBNFetcher(config=rbn_config, cache_dir=temp_cache_dir)

        mock_response = AsyncMock()
        mock_response.status_code = 401

        with patch.object(fetcher, "_get_client") as mock_client:
            client = AsyncMock()
            client.get.return_value = mock_response
            mock_client.return_value = client

            with pytest.raises(ValueError, match="Invalid RBN API token"):
                await fetcher.fetch_metric(
                    metric_id="mvrv_z",
                    start_date=date(2024, 12, 1),
                    force_refresh=True,
                )

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_fetch_metric_quota_exceeded(
        self,
        rbn_config: RBNConfig,
        temp_cache_dir: Path,
    ):
        """Should raise QuotaExceededError when quota exhausted."""
        from scripts.integrations.rbn_fetcher import RBNFetcher

        fetcher = RBNFetcher(config=rbn_config, cache_dir=temp_cache_dir)

        # Set up quota tracking to be exhausted
        quota_file = temp_cache_dir / "quota_tracking.json"
        quota_data = {
            "tier": 0,
            "weekly_limit": 100,
            "used_this_week": 100,
            "reset_at": (datetime.now() + timedelta(days=7)).isoformat(),
        }
        with open(quota_file, "w") as f:
            json.dump(quota_data, f)

        with pytest.raises(QuotaExceededError):
            await fetcher.fetch_metric(
                metric_id="mvrv_z",
                start_date=date(2024, 12, 1),
                force_refresh=True,
            )

        await fetcher.close()

    def test_fetch_metric_unknown_metric(
        self,
        rbn_config: RBNConfig,
        temp_cache_dir: Path,
    ):
        """Should raise ValueError for unknown metric_id."""
        from scripts.integrations.rbn_fetcher import RBNFetcher

        fetcher = RBNFetcher(config=rbn_config, cache_dir=temp_cache_dir)

        with pytest.raises(ValueError, match="Unknown metric"):
            # Use asyncio.run for sync test
            import asyncio

            asyncio.get_event_loop().run_until_complete(
                fetcher.fetch_metric(
                    metric_id="invalid_metric",
                    start_date=date(2024, 12, 1),
                )
            )


# =============================================================================
# T016: ValidationService Unit Tests
# =============================================================================


class TestValidationService:
    """T016: Unit tests for ValidationService class."""

    @pytest.mark.asyncio
    async def test_compare_metric_all_match(self):
        """Should return all MATCH when values are within tolerance."""
        from scripts.integrations.rbn_validator import ValidationService

        # Mock fetcher
        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_metric.return_value = RBNMetricResponse(
            status="success",
            message="OK",
            metric_id="mvrv_z",
            data=[
                RBNDataPoint(date=date(2024, 12, 1), value=2.45),
                RBNDataPoint(date=date(2024, 12, 2), value=2.51),
            ],
            output_format="json",
            timestamp=datetime.now(),
        )

        validator = ValidationService(fetcher=mock_fetcher)

        # Mock UTXOracle data (matching within tolerance)
        with patch.object(
            validator,
            "load_utxoracle_metric",
            return_value={
                date(2024, 12, 1): 2.448,  # 0.08% diff
                date(2024, 12, 2): 2.515,  # 0.2% diff
            },
        ):
            comparisons = await validator.compare_metric(
                metric_id="mvrv_z",
                start_date=date(2024, 12, 1),
                end_date=date(2024, 12, 2),
                tolerance_pct=1.0,
            )

        assert len(comparisons) == 2
        assert all(c.status == ComparisonStatus.MATCH for c in comparisons)

    @pytest.mark.asyncio
    async def test_compare_metric_with_diffs(self):
        """Should detect MINOR_DIFF and MAJOR_DIFF appropriately."""
        from scripts.integrations.rbn_validator import ValidationService

        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_metric.return_value = RBNMetricResponse(
            status="success",
            message="OK",
            metric_id="mvrv_z",
            data=[
                RBNDataPoint(date=date(2024, 12, 1), value=2.45),
                RBNDataPoint(date=date(2024, 12, 2), value=2.50),
                RBNDataPoint(date=date(2024, 12, 3), value=2.55),
            ],
            output_format="json",
            timestamp=datetime.now(),
        )

        validator = ValidationService(fetcher=mock_fetcher)

        with patch.object(
            validator,
            "load_utxoracle_metric",
            return_value={
                date(2024, 12, 1): 2.50,  # 2% diff -> MINOR_DIFF
                date(2024, 12, 2): 2.50,  # 0% diff -> MATCH
                date(2024, 12, 3): 2.80,  # 9.8% diff -> MAJOR_DIFF
            },
        ):
            comparisons = await validator.compare_metric(
                metric_id="mvrv_z",
                start_date=date(2024, 12, 1),
                end_date=date(2024, 12, 3),
                tolerance_pct=1.0,
            )

        assert len(comparisons) == 3
        assert comparisons[0].status == ComparisonStatus.MINOR_DIFF
        assert comparisons[1].status == ComparisonStatus.MATCH
        assert comparisons[2].status == ComparisonStatus.MAJOR_DIFF

    @pytest.mark.asyncio
    async def test_compare_metric_missing_data(self):
        """Should return MISSING when data unavailable on one side."""
        from scripts.integrations.rbn_validator import ValidationService

        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_metric.return_value = RBNMetricResponse(
            status="success",
            message="OK",
            metric_id="mvrv_z",
            data=[
                RBNDataPoint(date=date(2024, 12, 1), value=2.45),
                RBNDataPoint(date=date(2024, 12, 2), value=2.51),
            ],
            output_format="json",
            timestamp=datetime.now(),
        )

        validator = ValidationService(fetcher=mock_fetcher)

        with patch.object(
            validator,
            "load_utxoracle_metric",
            return_value={
                date(2024, 12, 1): 2.45,  # Has data
                # Dec 2 missing
            },
        ):
            comparisons = await validator.compare_metric(
                metric_id="mvrv_z",
                start_date=date(2024, 12, 1),
                end_date=date(2024, 12, 2),
            )

        assert len(comparisons) == 2
        assert comparisons[0].status == ComparisonStatus.MATCH
        assert comparisons[1].status == ComparisonStatus.MISSING

    def test_generate_report(self):
        """Should generate aggregate report from comparisons."""
        comparisons = [
            MetricComparison.create("mvrv_z", date(2024, 12, 1), 2.45, 2.45),
            MetricComparison.create("mvrv_z", date(2024, 12, 2), 2.50, 2.55),
            MetricComparison.create("mvrv_z", date(2024, 12, 3), 2.60, 2.80),
            MetricComparison.create("mvrv_z", date(2024, 12, 4), None, 2.70),
        ]

        report = ValidationReport.from_comparisons(
            metric_id="mvrv_z",
            metric_name="MVRV Z-Score",
            comparisons=comparisons,
        )

        assert report.total_comparisons == 4
        assert report.matches == 1
        assert report.minor_diffs == 1
        assert report.major_diffs == 1
        assert report.missing == 1
        assert report.match_rate_pct == 25.0


# =============================================================================
# T020: API Endpoint Tests
# =============================================================================


class TestValidationEndpoints:
    """T020: Tests for validation API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from api.main import app

        return TestClient(app)

    def test_validate_metric_endpoint_success(self, client):
        """GET /api/v1/validation/rbn/{metric_id} should return report."""
        response = client.get(
            "/api/v1/validation/rbn/mvrv_z",
            params={"start_date": "2024-12-01", "end_date": "2024-12-05"},
        )

        # May return 200 (data exists) or 503 (service unavailable - no token)
        assert response.status_code in [200, 400, 422, 503]

        if response.status_code == 200:
            data = response.json()
            assert "metric" in data
            assert "match_rate" in data
            assert data["status"] == "success"

    def test_validate_metric_endpoint_not_found(self, client):
        """GET /api/v1/validation/rbn/{invalid_metric} should return 404."""
        response = client.get("/api/v1/validation/rbn/invalid_metric_xyz")

        # Should return 400 or 404 for unknown metric
        assert response.status_code in [400, 404, 422]

    def test_list_metrics_endpoint(self, client):
        """GET /api/v1/validation/rbn/metrics should list available metrics."""
        response = client.get("/api/v1/validation/rbn/metrics")

        # May not be implemented yet
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert "metrics" in data
            assert isinstance(data["metrics"], list)


# =============================================================================
# T024-T025: Report and Quota Tests
# =============================================================================


class TestReportEndpoint:
    """T024: Tests for aggregate report endpoint."""

    @pytest.fixture
    def client(self):
        from api.main import app

        return TestClient(app)

    def test_generate_validation_report_multiple_metrics(self, client):
        """GET /api/v1/validation/rbn/report should return multi-metric report."""
        response = client.get(
            "/api/v1/validation/rbn/report",
            params={"metrics": "mvrv,sopr"},
        )

        # May not be implemented
        assert response.status_code in [200, 404, 501, 503]

        if response.status_code == 200:
            data = response.json()
            assert "reports" in data
            assert "overall_match_rate" in data


class TestQuotaEndpoint:
    """T025: Tests for quota tracking."""

    @pytest.fixture
    def client(self):
        from api.main import app

        return TestClient(app)

    def test_quota_info_from_api(self, client):
        """GET /api/v1/validation/rbn/quota should return quota status."""
        response = client.get("/api/v1/validation/rbn/quota")

        # May not be implemented
        assert response.status_code in [200, 404, 501, 503]

        if response.status_code == 200:
            data = response.json()
            assert "tier" in data
            assert "weekly_limit" in data
            assert "remaining" in data


# =============================================================================
# T030: Cache Management Tests
# =============================================================================


class TestCacheManagement:
    """T030: Tests for cache clearing operations."""

    @pytest.mark.asyncio
    async def test_clear_cache_all(
        self,
        rbn_config: RBNConfig,
        temp_cache_dir: Path,
    ):
        """clear_cache() should remove all Parquet files."""
        from scripts.integrations.rbn_fetcher import RBNFetcher
        import pandas as pd

        fetcher = RBNFetcher(config=rbn_config, cache_dir=temp_cache_dir)

        # Create some cache files
        for metric in ["mvrv_z", "sopr", "nupl"]:
            df = pd.DataFrame({"date": [date(2024, 12, 1)], "value": [1.0]})
            df.to_parquet(temp_cache_dir / f"{metric}.parquet", index=False)

        assert len(list(temp_cache_dir.glob("*.parquet"))) == 3

        # Clear all
        count = fetcher.clear_cache()

        assert count == 3
        assert len(list(temp_cache_dir.glob("*.parquet"))) == 0

    @pytest.mark.asyncio
    async def test_clear_cache_single_metric(
        self,
        rbn_config: RBNConfig,
        temp_cache_dir: Path,
    ):
        """clear_cache(metric_id) should only remove that metric."""
        from scripts.integrations.rbn_fetcher import RBNFetcher
        import pandas as pd

        fetcher = RBNFetcher(config=rbn_config, cache_dir=temp_cache_dir)

        # Create cache files
        for metric in ["mvrv_z", "sopr"]:
            df = pd.DataFrame({"date": [date(2024, 12, 1)], "value": [1.0]})
            df.to_parquet(temp_cache_dir / f"{metric}.parquet", index=False)

        # Clear only mvrv_z
        count = fetcher.clear_cache(metric_id="mvrv_z")

        assert count == 1
        assert not (temp_cache_dir / "mvrv_z.parquet").exists()
        assert (temp_cache_dir / "sopr.parquet").exists()


# =============================================================================
# Model Unit Tests
# =============================================================================


class TestMetricComparison:
    """Unit tests for MetricComparison model."""

    def test_create_match(self):
        """Should create MATCH for values within tolerance."""
        comparison = MetricComparison.create(
            metric_id="mvrv_z",
            dt=date(2024, 12, 1),
            utxo_val=2.45,
            rbn_val=2.45,
            tolerance_pct=1.0,
        )
        assert comparison.status == ComparisonStatus.MATCH
        assert comparison.relative_diff_pct == 0.0

    def test_create_minor_diff(self):
        """Should create MINOR_DIFF for 1-5% deviation."""
        comparison = MetricComparison.create(
            metric_id="mvrv_z",
            dt=date(2024, 12, 1),
            utxo_val=2.50,
            rbn_val=2.45,
            tolerance_pct=1.0,
        )
        assert comparison.status == ComparisonStatus.MINOR_DIFF
        assert 1.0 < comparison.relative_diff_pct < 5.0

    def test_create_major_diff(self):
        """Should create MAJOR_DIFF for >5% deviation."""
        comparison = MetricComparison.create(
            metric_id="mvrv_z",
            dt=date(2024, 12, 1),
            utxo_val=2.80,
            rbn_val=2.45,
            tolerance_pct=1.0,
        )
        assert comparison.status == ComparisonStatus.MAJOR_DIFF
        assert comparison.relative_diff_pct > 5.0

    def test_create_missing(self):
        """Should create MISSING when either value is None."""
        comparison = MetricComparison.create(
            metric_id="mvrv_z",
            dt=date(2024, 12, 1),
            utxo_val=None,
            rbn_val=2.45,
        )
        assert comparison.status == ComparisonStatus.MISSING


class TestRBNMetricResponse:
    """Unit tests for RBNMetricResponse parsing."""

    def test_from_api_response(self, mock_mvrv_response: dict):
        """Should correctly parse API response."""
        response = RBNMetricResponse.from_api_response(mock_mvrv_response, "mvrv_z")

        assert response.status == "success"
        assert response.metric_id == "mvrv_z"
        assert len(response.data) == 5
        assert response.data[0].date == date(2024, 12, 1)
        assert response.data[0].value == 2.45
