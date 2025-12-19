"""Tests for ComparisonEngine class.

Tests numerical validation orchestration and report generation.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch


from validation.framework.comparison_engine import (
    ComparisonEngine,
    VisualComparisonResult,
)
from validation.framework.validator import ValidationResult


class TestComparisonEngineNumericalValidation:
    """Tests for ComparisonEngine.run_numerical_validation() method."""

    def test_run_numerical_validation_calls_validator(
        self, baselines_dir: Path, mock_api_response: dict
    ):
        """run_numerical_validation() delegates to MetricValidator."""
        engine = ComparisonEngine(
            api_base_url="http://localhost:8000",
            screenshots_dir=baselines_dir.parent / "screenshots",
        )
        engine.validator.baselines_dir = baselines_dir

        with patch.object(engine.validator, "fetch_our_value") as mock_fetch:

            def side_effect(endpoint):
                if "mvrv" in endpoint:
                    return mock_api_response["mvrv"]
                elif "nupl" in endpoint:
                    return mock_api_response["nupl"]
                elif "hash-ribbons" in endpoint:
                    return mock_api_response["hash_ribbons"]
                return {}

            mock_fetch.side_effect = side_effect
            results = engine.run_numerical_validation()

        assert len(results) >= 3
        assert all(isinstance(r, ValidationResult) for r in results)

    def test_run_numerical_validation_stores_results(
        self, baselines_dir: Path, mock_api_response: dict
    ):
        """run_numerical_validation() stores results in engine."""
        engine = ComparisonEngine(api_base_url="http://localhost:8000")
        engine.validator.baselines_dir = baselines_dir

        with patch.object(engine.validator, "fetch_our_value") as mock_fetch:
            mock_fetch.return_value = mock_api_response["mvrv"]
            engine.run_numerical_validation()

        assert len(engine.numerical_results) >= 1


class TestComparisonEnginePrepareVisualComparison:
    """Tests for ComparisonEngine.prepare_visual_comparison() method."""

    def test_prepare_visual_comparison_known_metric(self, tmp_path: Path):
        """prepare_visual_comparison() returns URLs for known metrics."""
        engine = ComparisonEngine(screenshots_dir=tmp_path)

        comparison = engine.prepare_visual_comparison("mvrv")

        assert "ours" in comparison
        assert "reference" in comparison
        assert "description" in comparison
        assert "localhost:8080" in comparison["ours"]
        assert "checkonchain.com" in comparison["reference"]

    def test_prepare_visual_comparison_unknown_metric(self, tmp_path: Path):
        """prepare_visual_comparison() returns empty dict for unknown metric."""
        engine = ComparisonEngine(screenshots_dir=tmp_path)

        comparison = engine.prepare_visual_comparison("unknown_metric")

        assert comparison == {}

    def test_prepare_visual_comparison_all_metrics(self, tmp_path: Path):
        """prepare_visual_comparison() works for all configured metrics."""
        engine = ComparisonEngine(screenshots_dir=tmp_path)

        for metric in ["mvrv", "nupl", "sopr", "hash_ribbons", "cdd", "cost_basis"]:
            comparison = engine.prepare_visual_comparison(metric)
            assert "ours" in comparison, f"Missing 'ours' for {metric}"
            assert "reference" in comparison, f"Missing 'reference' for {metric}"


class TestComparisonEngineSaveReport:
    """Tests for ComparisonEngine.save_report() method."""

    def test_save_report_creates_file(self, tmp_path: Path):
        """save_report() creates markdown report file."""
        engine = ComparisonEngine(screenshots_dir=tmp_path)
        engine.validator.results = [
            ValidationResult(
                metric="mvrv_z",
                timestamp=datetime.utcnow(),
                our_value=1.45,
                reference_value=1.46,
                deviation_pct=0.68,
                tolerance_pct=2.0,
                status="PASS",
            )
        ]

        report_path = engine.save_report(output_dir=tmp_path / "reports")

        assert report_path.exists()
        assert report_path.suffix == ".md"
        assert "_validation.md" in report_path.name

    def test_save_report_includes_numerical_results(self, tmp_path: Path):
        """save_report() includes numerical validation results."""
        engine = ComparisonEngine(screenshots_dir=tmp_path)
        engine.validator.results = [
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

        report_path = engine.save_report(output_dir=tmp_path / "reports")

        content = report_path.read_text()
        assert "| mvrv_z |" in content
        assert "| nupl |" in content
        assert "✅" in content
        assert "⚠️" in content

    def test_save_report_includes_visual_results(self, tmp_path: Path):
        """save_report() includes visual comparison results when available."""
        engine = ComparisonEngine(screenshots_dir=tmp_path)
        engine.validator.results = []
        engine.visual_results = [
            VisualComparisonResult(
                metric="mvrv",
                our_screenshot=tmp_path / "ours" / "mvrv.png",
                reference_screenshot=tmp_path / "reference" / "mvrv.png",
                trend_match=True,
                zone_match=True,
                value_alignment=95.0,
                notes="Charts aligned",
                status="PASS",
            )
        ]

        report_path = engine.save_report(output_dir=tmp_path / "reports")

        content = report_path.read_text()
        assert "## Visual Comparisons" in content
        assert "### mvrv" in content
        assert "Trend Match: ✓" in content
        assert "Value Alignment: 95.0%" in content

    def test_save_report_uses_default_dir(self, tmp_path: Path, monkeypatch):
        """save_report() uses default reports directory when not specified."""
        # Change to tmp_path to avoid writing to real project
        monkeypatch.chdir(tmp_path)
        (tmp_path / "validation" / "reports").mkdir(parents=True)

        engine = ComparisonEngine(screenshots_dir=tmp_path)
        engine.validator.results = [
            ValidationResult(
                metric="test",
                timestamp=datetime.utcnow(),
                our_value=1.0,
                reference_value=1.0,
                deviation_pct=0.0,
                tolerance_pct=5.0,
                status="PASS",
            )
        ]

        report_path = engine.save_report()

        assert "validation/reports" in str(report_path)


class TestComparisonEngineGenerateBaselineTemplate:
    """Tests for ComparisonEngine.generate_baseline_template() method."""

    def test_generate_baseline_template_mvrv(self, tmp_path: Path):
        """generate_baseline_template() returns MVRV template structure."""
        engine = ComparisonEngine(screenshots_dir=tmp_path)

        template = engine.generate_baseline_template("mvrv")

        assert template["metric"] == "mvrv"
        assert "current" in template
        assert "mvrv_z_score" in template["current"]

    def test_generate_baseline_template_unknown(self, tmp_path: Path):
        """generate_baseline_template() returns generic template for unknown metrics."""
        engine = ComparisonEngine(screenshots_dir=tmp_path)

        template = engine.generate_baseline_template("unknown")

        assert template["metric"] == "unknown"
        assert "current" in template


class TestComparisonEngineSaveBaselineTemplates:
    """Tests for ComparisonEngine.save_baseline_templates() method."""

    def test_save_baseline_templates_creates_files(self, tmp_path: Path, monkeypatch):
        """save_baseline_templates() creates template files for all metrics."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "validation" / "baselines").mkdir(parents=True)

        engine = ComparisonEngine(screenshots_dir=tmp_path)
        engine.save_baseline_templates()

        baselines_dir = tmp_path / "validation" / "baselines"
        # Should create files for mvrv, nupl, hash_ribbons, sopr, cdd
        assert (baselines_dir / "mvrv_baseline.json").exists()
        assert (baselines_dir / "nupl_baseline.json").exists()
        assert (baselines_dir / "hash_ribbons_baseline.json").exists()

    def test_save_baseline_templates_does_not_overwrite(
        self, tmp_path: Path, monkeypatch
    ):
        """save_baseline_templates() does not overwrite existing files."""
        monkeypatch.chdir(tmp_path)
        baselines_dir = tmp_path / "validation" / "baselines"
        baselines_dir.mkdir(parents=True)

        # Create existing file with custom content
        existing_file = baselines_dir / "mvrv_baseline.json"
        existing_file.write_text('{"custom": "data"}')

        engine = ComparisonEngine(screenshots_dir=tmp_path)
        engine.save_baseline_templates()

        # Existing file should not be overwritten
        assert existing_file.read_text() == '{"custom": "data"}'


class TestVisualComparisonResult:
    """Tests for VisualComparisonResult dataclass."""

    def test_visual_comparison_result_creation(self, tmp_path: Path):
        """VisualComparisonResult can be created with all fields."""
        result = VisualComparisonResult(
            metric="mvrv",
            our_screenshot=tmp_path / "ours" / "mvrv.png",
            reference_screenshot=tmp_path / "reference" / "mvrv.png",
            trend_match=True,
            zone_match=False,
            value_alignment=85.5,
            notes="Minor zone mismatch",
            status="REVIEW",
        )

        assert result.metric == "mvrv"
        assert result.trend_match is True
        assert result.zone_match is False
        assert result.value_alignment == 85.5
        assert result.status == "REVIEW"
