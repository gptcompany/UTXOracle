"""Visual validation using screenshot comparison.

Captures screenshots of our charts and CheckOnChain reference charts,
then compares them for trend and zone alignment.

Note: This module is designed to work with Playwright MCP for screenshot capture.
When run directly, it uses subprocess to invoke MCP tools.
When used with Claude Code, the MCP tools are called directly.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from validation.framework.config import (
    URL_MAPPING,
    get_our_url,
    get_reference_url,
)


@dataclass
class VisualComparisonResult:
    """Result of visual chart comparison."""

    metric: str
    our_screenshot: Path
    reference_screenshot: Path
    trend_match: bool
    zone_match: bool
    value_alignment: float  # 0-100%
    notes: str
    status: str  # PASS, FAIL, REVIEW


class VisualValidator:
    """Visual validation through screenshot comparison.

    This class orchestrates visual validation by:
    1. Capturing screenshots of our charts
    2. Capturing screenshots of CheckOnChain reference charts
    3. Comparing the screenshots for trend/zone alignment

    Note: Screenshot capture requires Playwright MCP to be configured.
    The actual MCP calls are made through the compare_metric() method
    which returns instructions for the AI agent to execute.
    """

    def __init__(
        self,
        screenshots_dir: Optional[Path] = None,
    ):
        self.screenshots_dir = screenshots_dir or Path("validation/screenshots")
        self.ours_dir = self.screenshots_dir / "ours"
        self.reference_dir = self.screenshots_dir / "reference"

        # Ensure directories exist
        self.ours_dir.mkdir(parents=True, exist_ok=True)
        self.reference_dir.mkdir(parents=True, exist_ok=True)

        self.results: list[VisualComparisonResult] = []

    def get_screenshot_path(self, metric: str, is_ours: bool = True) -> Path:
        """Get the path where a screenshot should be saved.

        Args:
            metric: Metric name (mvrv, nupl, etc.)
            is_ours: True for our chart, False for reference

        Returns:
            Path to screenshot file
        """
        directory = self.ours_dir if is_ours else self.reference_dir
        return directory / f"{metric}.png"

    def capture_our_screenshot(self, metric: str) -> dict:
        """Get instructions for capturing our chart screenshot.

        This method returns a dict with URL and path for the AI agent
        to use with Playwright MCP tools.

        Args:
            metric: Metric to capture (mvrv, nupl, etc.)

        Returns:
            Dict with 'url' and 'path' for MCP screenshot capture
        """
        url = get_our_url(metric)
        if not url:
            return {"error": f"Unknown metric: {metric}"}

        screenshot_path = self.get_screenshot_path(metric, is_ours=True)
        return {
            "action": "capture_screenshot",
            "url": url,
            "path": str(screenshot_path),
            "description": f"Capture our {metric.upper()} chart",
            "mcp_sequence": [
                f"mcp__playwright__browser_navigate(url='{url}')",
                f"mcp__playwright__browser_take_screenshot(path='{screenshot_path}')",
            ],
        }

    def capture_reference_screenshot(self, metric: str) -> dict:
        """Get instructions for capturing CheckOnChain reference screenshot.

        Args:
            metric: Metric to capture (mvrv, nupl, etc.)

        Returns:
            Dict with 'url' and 'path' for MCP screenshot capture
        """
        url = get_reference_url(metric)
        if not url:
            return {"error": f"Unknown metric or no reference: {metric}"}

        screenshot_path = self.get_screenshot_path(metric, is_ours=False)
        return {
            "action": "capture_screenshot",
            "url": url,
            "path": str(screenshot_path),
            "description": f"Capture CheckOnChain {metric.upper()} reference chart",
            "mcp_sequence": [
                f"mcp__playwright__browser_navigate(url='{url}')",
                f"mcp__playwright__browser_take_screenshot(path='{screenshot_path}')",
            ],
        }

    def compare_screenshots(
        self,
        metric: str,
        trend_match: bool = True,
        zone_match: bool = True,
        value_alignment: float = 90.0,
        notes: str = "",
    ) -> VisualComparisonResult:
        """Record comparison result for a metric.

        This method is called after manual or AI-assisted comparison
        of the two screenshots.

        Args:
            metric: Metric compared
            trend_match: Whether trends align visually
            zone_match: Whether colored zones match
            value_alignment: Estimated alignment percentage (0-100)
            notes: Observer notes about the comparison

        Returns:
            VisualComparisonResult with status determined by inputs
        """
        our_path = self.get_screenshot_path(metric, is_ours=True)
        ref_path = self.get_screenshot_path(metric, is_ours=False)

        # Determine status based on criteria
        if trend_match and zone_match and value_alignment >= 90:
            status = "PASS"
        elif trend_match and value_alignment >= 70:
            status = "REVIEW"
        else:
            status = "FAIL"

        result = VisualComparisonResult(
            metric=metric,
            our_screenshot=our_path,
            reference_screenshot=ref_path,
            trend_match=trend_match,
            zone_match=zone_match,
            value_alignment=value_alignment,
            notes=notes,
            status=status,
        )

        self.results.append(result)
        return result

    def compare_metric(self, metric: str) -> dict:
        """Get full comparison workflow for a metric.

        Returns instructions for the AI agent to:
        1. Navigate to our chart and take screenshot
        2. Navigate to reference chart and take screenshot
        3. Compare the two screenshots visually

        Args:
            metric: Metric to compare

        Returns:
            Dict with workflow steps for AI agent execution
        """
        if metric not in URL_MAPPING:
            return {"error": f"Unknown metric: {metric}"}

        our_capture = self.capture_our_screenshot(metric)
        ref_capture = self.capture_reference_screenshot(metric)

        return {
            "metric": metric,
            "workflow": [
                {
                    "step": 1,
                    "action": "capture_our_chart",
                    "details": our_capture,
                },
                {
                    "step": 2,
                    "action": "capture_reference_chart",
                    "details": ref_capture,
                },
                {
                    "step": 3,
                    "action": "compare_visually",
                    "instructions": [
                        f"Compare the two screenshots for {metric.upper()}:",
                        f"  - Our chart: {our_capture.get('path')}",
                        f"  - Reference: {ref_capture.get('path')}",
                        "Evaluate:",
                        "  1. Do the trends align? (upward/downward movements match)",
                        "  2. Do colored zones match? (if applicable)",
                        "  3. What's the estimated visual alignment? (0-100%)",
                        "Then call compare_screenshots() with your findings.",
                    ],
                },
            ],
            "completion": {
                "method": "compare_screenshots",
                "signature": f"compare_screenshots('{metric}', trend_match=True/False, zone_match=True/False, value_alignment=0-100, notes='...')",
            },
        }

    def get_all_metrics(self) -> list[str]:
        """Get list of all metrics available for visual validation."""
        return list(URL_MAPPING.keys())

    def compare_all_metrics(self) -> dict:
        """Get comparison workflow for all available metrics.

        Returns:
            Dict with workflows for each metric
        """
        workflows = {}
        for metric in self.get_all_metrics():
            workflows[metric] = self.compare_metric(metric)
        return workflows

    def generate_visual_report(self) -> str:
        """Generate markdown report of visual comparison results.

        Returns:
            Markdown formatted report string
        """
        if not self.results:
            return "# Visual Validation Report\n\nNo visual comparisons recorded.\n"

        passed = sum(1 for r in self.results if r.status == "PASS")
        review = sum(1 for r in self.results if r.status == "REVIEW")
        failed = sum(1 for r in self.results if r.status == "FAIL")

        report = f"""# Visual Validation Report

**Generated**: {datetime.utcnow().isoformat()}

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | {passed} |
| 👁️ REVIEW | {review} |
| ❌ FAIL | {failed} |

## Details

"""
        for r in self.results:
            status_icon = {"PASS": "✅", "REVIEW": "👁️", "FAIL": "❌"}.get(r.status, "?")
            report += f"""### {r.metric.upper()} {status_icon}

- **Trend Match**: {"✓" if r.trend_match else "✗"}
- **Zone Match**: {"✓" if r.zone_match else "✗"}
- **Value Alignment**: {r.value_alignment:.1f}%
- **Our Screenshot**: `{r.our_screenshot}`
- **Reference**: `{r.reference_screenshot}`
- **Notes**: {r.notes or "None"}

"""
        return report
