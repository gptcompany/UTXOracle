"""Comparison engine for numerical and visual validation.

Handles both API value comparison and screenshot-based visual validation.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from validation.framework.validator import MetricValidator, ValidationResult
from validation.framework.visual_validator import (
    VisualComparisonResult,
)


class ComparisonEngine:
    """Engine for comprehensive metric comparison."""

    def __init__(
        self,
        api_base_url: str = "http://localhost:8000",
        screenshots_dir: Optional[Path] = None,
    ):
        self.validator = MetricValidator(api_base_url)
        self.screenshots_dir = screenshots_dir or Path("validation/screenshots")
        self.numerical_results: list[ValidationResult] = []
        self.visual_results: list[VisualComparisonResult] = []

    def run_numerical_validation(self) -> list[ValidationResult]:
        """Run numerical validation for all metrics."""
        self.numerical_results = self.validator.run_all()
        return self.numerical_results

    def prepare_visual_comparison(self, metric: str) -> dict:
        """Prepare for visual comparison by defining what to capture.

        Returns dict with URLs to capture for both our app and reference.
        Uses centralized URL mapping from config.
        """
        from validation.framework.config import URL_MAPPING

        descriptions = {
            "mvrv": "MVRV-Z Score chart comparison",
            "nupl": "NUPL chart comparison",
            "sopr": "SOPR chart comparison",
            "hash_ribbons": "Hash Ribbons chart comparison",
            "cdd": "Coin Days Destroyed chart comparison",
            "binary_cdd": "Binary CDD heatmap comparison",
            "cost_basis": "Cost Basis / Realized Price comparison",
        }

        if metric not in URL_MAPPING:
            return {}

        mapping = URL_MAPPING[metric]
        return {
            "ours": mapping["ours"],
            "reference": mapping["reference"],
            "description": descriptions.get(metric, f"{metric} chart comparison"),
        }

    def save_report(self, output_dir: Optional[Path] = None) -> Path:
        """Save validation report to file."""
        output_dir = output_dir or Path("validation/reports")
        output_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        report_path = output_dir / f"{date_str}_validation.md"

        report = self.validator.generate_report()

        # Add visual comparison section if available
        if self.visual_results:
            report += "\n## Visual Comparisons\n\n"
            for vr in self.visual_results:
                status_icon = {"PASS": "✅", "FAIL": "❌", "REVIEW": "👁️"}.get(
                    vr.status, "?"
                )
                report += f"### {vr.metric} {status_icon}\n\n"
                report += f"- Trend Match: {'✓' if vr.trend_match else '✗'}\n"
                report += f"- Zone Match: {'✓' if vr.zone_match else '✗'}\n"
                report += f"- Value Alignment: {vr.value_alignment:.1f}%\n"
                report += f"- Notes: {vr.notes}\n\n"

        with open(report_path, "w") as f:
            f.write(report)

        return report_path

    def generate_baseline_template(self, metric: str) -> dict:
        """Generate a baseline template for manual population."""
        templates = {
            "mvrv": {
                "metric": "mvrv",
                "source": "checkonchain.com",
                "captured_at": datetime.utcnow().isoformat(),
                "current": {
                    "mvrv_z_score": 0.0,
                    "mvrv_ratio": 0.0,
                },
                "historical_samples": [
                    {"date": "2024-01-01", "mvrv_z_score": 0.0},
                ],
            },
            "nupl": {
                "metric": "nupl",
                "source": "checkonchain.com",
                "captured_at": datetime.utcnow().isoformat(),
                "current": {
                    "nupl": 0.0,
                    "zone": "unknown",
                },
                "historical_samples": [
                    {"date": "2024-01-01", "nupl": 0.0},
                ],
            },
            "hash_ribbons": {
                "metric": "hash_ribbons",
                "source": "checkonchain.com",
                "captured_at": datetime.utcnow().isoformat(),
                "current": {
                    "ma_30d": 0.0,
                    "ma_60d": 0.0,
                    "ribbon_signal": False,
                },
            },
        }
        return templates.get(metric, {"metric": metric, "current": {}})

    def save_baseline_templates(self) -> None:
        """Save all baseline templates for manual population."""
        baselines_dir = Path("validation/baselines")
        baselines_dir.mkdir(parents=True, exist_ok=True)

        for metric in ["mvrv", "nupl", "hash_ribbons", "sopr", "cdd"]:
            template = self.generate_baseline_template(metric)
            baseline_path = baselines_dir / f"{metric}_baseline.json"
            if not baseline_path.exists():
                with open(baseline_path, "w") as f:
                    json.dump(template, f, indent=2)
                print(f"Created template: {baseline_path}")
