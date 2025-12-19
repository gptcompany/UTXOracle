"""Tests for MetricValidator class.

Tests compare() method and validate_* methods.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch


from validation.framework.validator import MetricValidator, ValidationResult


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_to_dict(self):
        """ValidationResult.to_dict returns correct structure."""
        result = ValidationResult(
            metric="mvrv_z",
            timestamp=datetime(2025, 12, 19, 10, 0, 0),
            our_value=1.45,
            reference_value=1.50,
            deviation_pct=3.33,
            tolerance_pct=2.0,
            status="WARN",
            notes="Slight deviation",
        )
        d = result.to_dict()

        assert d["metric"] == "mvrv_z"
        assert d["our_value"] == 1.45
        assert d["reference_value"] == 1.50
        assert d["deviation_pct"] == 3.33
        assert d["tolerance_pct"] == 2.0
        assert d["status"] == "WARN"
        assert d["notes"] == "Slight deviation"
        assert "timestamp" in d


class TestMetricValidatorCompare:
    """Tests for MetricValidator.compare() method."""

    def test_compare_pass_within_tolerance(self, baselines_dir: Path):
        """compare() returns PASS when deviation is within tolerance."""
        validator = MetricValidator(baselines_dir=baselines_dir)

        result = validator.compare(
            metric="mvrv_z",
            our_value=1.45,
            reference_value=1.46,
            tolerance_pct=2.0,
        )

        assert result.status == "PASS"
        assert result.deviation_pct < 2.0

    def test_compare_warn_between_1x_2x_tolerance(self, baselines_dir: Path):
        """compare() returns WARN when deviation is between 1x-2x tolerance."""
        validator = MetricValidator(baselines_dir=baselines_dir)

        # 3% deviation with 2% tolerance = WARN (between 2% and 4%)
        result = validator.compare(
            metric="mvrv_z",
            our_value=1.03,
            reference_value=1.00,
            tolerance_pct=2.0,
        )

        assert result.status == "WARN"
        assert 2.0 < result.deviation_pct <= 4.0

    def test_compare_fail_exceeds_2x_tolerance(self, baselines_dir: Path):
        """compare() returns FAIL when deviation exceeds 2x tolerance."""
        validator = MetricValidator(baselines_dir=baselines_dir)

        # 10% deviation with 2% tolerance = FAIL (> 4%)
        result = validator.compare(
            metric="mvrv_z",
            our_value=1.10,
            reference_value=1.00,
            tolerance_pct=2.0,
        )

        assert result.status == "FAIL"
        assert result.deviation_pct > 4.0

    def test_compare_uses_default_tolerance(self, baselines_dir: Path):
        """compare() uses default tolerance from TOLERANCES dict."""
        validator = MetricValidator(baselines_dir=baselines_dir)

        result = validator.compare(
            metric="sopr",  # Default tolerance is 1.0%
            our_value=1.005,
            reference_value=1.00,
        )

        assert result.tolerance_pct == 1.0

    def test_compare_handles_zero_reference(self, baselines_dir: Path):
        """compare() handles zero reference value correctly."""
        validator = MetricValidator(baselines_dir=baselines_dir)

        # Both zero = 0% deviation
        result = validator.compare(
            metric="test",
            our_value=0.0,
            reference_value=0.0,
        )
        assert result.deviation_pct == 0.0

        # Non-zero vs zero = 100% deviation
        result = validator.compare(
            metric="test",
            our_value=1.0,
            reference_value=0.0,
        )
        assert result.deviation_pct == 100.0

    def test_compare_appends_to_results(self, baselines_dir: Path):
        """compare() appends result to validator.results list."""
        validator = MetricValidator(baselines_dir=baselines_dir)
        assert len(validator.results) == 0

        validator.compare("test", 1.0, 1.0)
        assert len(validator.results) == 1

        validator.compare("test2", 2.0, 2.0)
        assert len(validator.results) == 2


class TestMetricValidatorValidateMvrv:
    """Tests for MetricValidator.validate_mvrv() method."""

    def test_validate_mvrv_success(self, baselines_dir: Path, mock_api_response: dict):
        """validate_mvrv() successfully compares API with baseline."""
        validator = MetricValidator(
            api_base_url="http://localhost:8000", baselines_dir=baselines_dir
        )

        with patch.object(validator, "fetch_our_value") as mock_fetch:
            mock_fetch.return_value = mock_api_response["mvrv"]
            result = validator.validate_mvrv()

        assert result.metric == "mvrv_z"
        assert result.our_value == 1.45
        # Reference value from sample_mvrv_baseline fixture
        assert result.reference_value == 1.45
        assert result.status == "PASS"

    def test_validate_mvrv_api_error(self, baselines_dir: Path):
        """validate_mvrv() returns ERROR on API failure."""
        validator = MetricValidator(
            api_base_url="http://localhost:8000", baselines_dir=baselines_dir
        )

        with patch.object(validator, "fetch_our_value") as mock_fetch:
            mock_fetch.side_effect = Exception("Connection refused")
            result = validator.validate_mvrv()

        assert result.status == "ERROR"
        assert "Connection refused" in result.notes

    def test_validate_mvrv_missing_baseline(
        self, tmp_path: Path, mock_api_response: dict
    ):
        """validate_mvrv() uses 0 reference when baseline is missing."""
        empty_baselines = tmp_path / "empty_baselines"
        empty_baselines.mkdir()
        validator = MetricValidator(
            api_base_url="http://localhost:8000", baselines_dir=empty_baselines
        )

        with patch.object(validator, "fetch_our_value") as mock_fetch:
            mock_fetch.return_value = mock_api_response["mvrv"]
            result = validator.validate_mvrv()

        assert result.reference_value == 0


class TestMetricValidatorRunAll:
    """Tests for MetricValidator.run_all() method."""

    def test_run_all_returns_all_results(
        self, baselines_dir: Path, mock_api_response: dict
    ):
        """run_all() returns results for all metrics."""
        validator = MetricValidator(
            api_base_url="http://localhost:8000", baselines_dir=baselines_dir
        )

        with patch.object(validator, "fetch_our_value") as mock_fetch:

            def side_effect(endpoint):
                if "mvrv" in endpoint:
                    return mock_api_response["mvrv"]
                elif "nupl" in endpoint:
                    return mock_api_response["nupl"]
                elif "hash-ribbons" in endpoint:
                    return mock_api_response["hash_ribbons"]
                return {}

            mock_fetch.side_effect = side_effect
            results = validator.run_all()

        # Should have mvrv, nupl, and 2 hash_ribbons results
        assert len(results) >= 3

    def test_run_all_clears_previous_results(
        self, baselines_dir: Path, mock_api_response: dict
    ):
        """run_all() clears previous results before running."""
        validator = MetricValidator(
            api_base_url="http://localhost:8000", baselines_dir=baselines_dir
        )
        validator.results = [MagicMock()]  # Pre-populate

        with patch.object(validator, "fetch_our_value") as mock_fetch:
            mock_fetch.return_value = mock_api_response["mvrv"]
            results = validator.run_all()

        # Should not contain the pre-populated mock
        assert all(isinstance(r, ValidationResult) for r in results)


class TestMetricValidatorValidateNupl:
    """Tests for MetricValidator.validate_nupl() method."""

    def test_validate_nupl_success(self, baselines_dir: Path, mock_api_response: dict):
        """validate_nupl() successfully compares API with baseline."""
        validator = MetricValidator(
            api_base_url="http://localhost:8000", baselines_dir=baselines_dir
        )

        with patch.object(validator, "fetch_our_value") as mock_fetch:
            mock_fetch.return_value = mock_api_response["nupl"]
            result = validator.validate_nupl()

        assert result.metric == "nupl"
        assert result.our_value == 0.52
        assert result.status == "PASS"

    def test_validate_nupl_api_error(self, baselines_dir: Path):
        """validate_nupl() returns ERROR on API failure."""
        validator = MetricValidator(
            api_base_url="http://localhost:8000", baselines_dir=baselines_dir
        )

        with patch.object(validator, "fetch_our_value") as mock_fetch:
            mock_fetch.side_effect = Exception("API timeout")
            result = validator.validate_nupl()

        assert result.status == "ERROR"
        assert "API timeout" in result.notes

    def test_validate_nupl_missing_baseline(
        self, tmp_path: Path, mock_api_response: dict
    ):
        """validate_nupl() uses 0 reference when baseline is missing."""
        empty_baselines = tmp_path / "empty_baselines"
        empty_baselines.mkdir()
        validator = MetricValidator(
            api_base_url="http://localhost:8000", baselines_dir=empty_baselines
        )

        with patch.object(validator, "fetch_our_value") as mock_fetch:
            mock_fetch.return_value = mock_api_response["nupl"]
            result = validator.validate_nupl()

        assert result.reference_value == 0


class TestMetricValidatorValidateHashRibbons:
    """Tests for MetricValidator.validate_hash_ribbons() method."""

    def test_validate_hash_ribbons_success(
        self, baselines_dir: Path, mock_api_response: dict
    ):
        """validate_hash_ribbons() successfully compares API with baseline."""
        validator = MetricValidator(
            api_base_url="http://localhost:8000", baselines_dir=baselines_dir
        )

        with patch.object(validator, "fetch_our_value") as mock_fetch:
            mock_fetch.return_value = mock_api_response["hash_ribbons"]
            results = validator.validate_hash_ribbons()

        assert len(results) == 2
        assert results[0].metric == "hash_ribbons_30d"
        assert results[1].metric == "hash_ribbons_60d"

    def test_validate_hash_ribbons_api_error(self, baselines_dir: Path):
        """validate_hash_ribbons() returns ERROR on API failure."""
        validator = MetricValidator(
            api_base_url="http://localhost:8000", baselines_dir=baselines_dir
        )

        with patch.object(validator, "fetch_our_value") as mock_fetch:
            mock_fetch.side_effect = Exception("Network error")
            results = validator.validate_hash_ribbons()

        assert len(results) == 1
        assert results[0].status == "ERROR"
        assert "Network error" in results[0].notes

    def test_validate_hash_ribbons_missing_baseline(
        self, tmp_path: Path, mock_api_response: dict
    ):
        """validate_hash_ribbons() uses 0 reference when baseline is missing."""
        empty_baselines = tmp_path / "empty_baselines"
        empty_baselines.mkdir()
        validator = MetricValidator(
            api_base_url="http://localhost:8000", baselines_dir=empty_baselines
        )

        with patch.object(validator, "fetch_our_value") as mock_fetch:
            mock_fetch.return_value = mock_api_response["hash_ribbons"]
            results = validator.validate_hash_ribbons()

        assert results[0].reference_value == 0
        assert results[1].reference_value == 0


class TestMetricValidatorGenerateReport:
    """Tests for MetricValidator.generate_report() method."""

    def test_generate_report_markdown_format(self, baselines_dir: Path):
        """generate_report() returns valid markdown."""
        validator = MetricValidator(baselines_dir=baselines_dir)
        validator.results = [
            ValidationResult(
                metric="mvrv_z",
                timestamp=datetime.utcnow(),
                our_value=1.45,
                reference_value=1.46,
                deviation_pct=0.68,
                tolerance_pct=2.0,
                status="PASS",
            ),
            ValidationResult(
                metric="nupl",
                timestamp=datetime.utcnow(),
                our_value=0.52,
                reference_value=0.50,
                deviation_pct=4.0,
                tolerance_pct=2.0,
                status="WARN",
            ),
        ]

        report = validator.generate_report()

        assert "# Validation Report" in report
        assert "| Status | Count |" in report
        assert "✅ PASS | 1" in report
        assert "⚠️ WARN | 1" in report
        assert "| mvrv_z |" in report
        assert "| nupl |" in report

    def test_generate_report_empty_results(self, baselines_dir: Path):
        """generate_report() handles empty results."""
        validator = MetricValidator(baselines_dir=baselines_dir)
        validator.results = []

        report = validator.generate_report()

        assert "# Validation Report" in report
        assert "| ✅ PASS | 0 |" in report
