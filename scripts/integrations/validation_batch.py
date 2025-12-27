#!/usr/bin/env python3
"""
Weekly Batch Validation for UTXOracle metrics.

Compares our metrics against RBN reference data and generates reports.
Designed to run weekly to stay within RBN free tier quota (100/week).

Usage:
    # Run validation for all P1 metrics
    python scripts/integrations/validation_batch.py

    # Generate HTML report
    python scripts/integrations/validation_batch.py --html

    # Run specific metrics only
    python scripts/integrations/validation_batch.py --metrics mvrv_z,sopr

    # Send alerts on deviation
    python scripts/integrations/validation_batch.py --alert

Cron example (every Sunday at 2am):
    0 2 * * 0 cd /path/to/UTXOracle && python scripts/integrations/validation_batch.py --html --alert
"""

import argparse
import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Output directories
REPORTS_DIR = Path("reports/validation")
GOLDEN_DATA_DIR = Path("tests/validation/golden_data")

# Metric configurations
P1_METRICS = ["mvrv_z", "sopr", "nupl", "realized_cap"]
P2_METRICS = ["liveliness", "power_law"]

# Thresholds
CORRELATION_THRESHOLD = 0.90  # r > 0.90
MAPE_THRESHOLD = 10.0  # MAPE < 10%
CRITICAL_MAPE_THRESHOLD = 20.0  # MAPE > 20% = critical


@dataclass
class MetricValidationResult:
    """Result of validating a single metric."""

    metric_id: str
    our_data_count: int
    rbn_data_count: int
    overlap_count: int
    correlation: Optional[float]
    mape: Optional[float]
    max_deviation: Optional[float]
    status: str  # "pass", "warn", "fail", "error", "no_data"
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "metric_id": self.metric_id,
            "our_data_count": self.our_data_count,
            "rbn_data_count": self.rbn_data_count,
            "overlap_count": self.overlap_count,
            "correlation": self.correlation,
            "mape": self.mape,
            "max_deviation": self.max_deviation,
            "status": self.status,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ValidationBatchResult:
    """Result of validating multiple metrics."""

    run_id: str
    run_timestamp: datetime
    metrics_validated: int
    passed: int
    warned: int
    failed: int
    errors: int
    no_data: int
    results: list[MetricValidationResult]

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "run_timestamp": self.run_timestamp.isoformat(),
            "summary": {
                "metrics_validated": self.metrics_validated,
                "passed": self.passed,
                "warned": self.warned,
                "failed": self.failed,
                "errors": self.errors,
                "no_data": self.no_data,
            },
            "results": [r.to_dict() for r in self.results],
        }


class ValidationBatch:
    """Run batch validation of UTXOracle metrics against RBN."""

    def __init__(
        self,
        golden_data_dir: Optional[Path] = None,
        reports_dir: Optional[Path] = None,
    ):
        self.golden_data_dir = golden_data_dir or GOLDEN_DATA_DIR
        self.reports_dir = reports_dir or REPORTS_DIR
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def validate_metric(
        self,
        metric_id: str,
        start_date: date,
        end_date: date,
    ) -> MetricValidationResult:
        """Validate a single metric against golden data."""
        from scripts.integrations.metric_loader import MetricLoader

        loader = MetricLoader(golden_data_dir=self.golden_data_dir)

        try:
            # Load our data
            our_series = loader.load_metric(metric_id, start_date, end_date)
            our_data = our_series.to_dataframe() if our_series.data else pd.DataFrame()

            # Load golden data
            golden_file = self.golden_data_dir / f"{metric_id}.parquet"
            if not golden_file.exists():
                return MetricValidationResult(
                    metric_id=metric_id,
                    our_data_count=len(our_data),
                    rbn_data_count=0,
                    overlap_count=0,
                    correlation=None,
                    mape=None,
                    max_deviation=None,
                    status="no_data",
                    error_message="No golden data available",
                )

            golden = pd.read_parquet(golden_file)
            golden["date"] = pd.to_datetime(golden["date"]).dt.date
            golden = golden.set_index("date")

            # Filter by date range
            mask = (golden.index >= start_date) & (golden.index <= end_date)
            golden = golden[mask]

            if len(our_data) == 0:
                return MetricValidationResult(
                    metric_id=metric_id,
                    our_data_count=0,
                    rbn_data_count=len(golden),
                    overlap_count=0,
                    correlation=None,
                    mape=None,
                    max_deviation=None,
                    status="no_data",
                    error_message="No UTXOracle data available",
                )

            # Merge and compare
            merged = pd.DataFrame(
                {"our": our_data["value"], "rbn": golden["value"]}
            ).dropna()

            overlap_count = len(merged)

            if overlap_count < 3:
                return MetricValidationResult(
                    metric_id=metric_id,
                    our_data_count=len(our_data),
                    rbn_data_count=len(golden),
                    overlap_count=overlap_count,
                    correlation=None,
                    mape=None,
                    max_deviation=None,
                    status="no_data",
                    error_message="Insufficient overlap for comparison",
                )

            # Calculate metrics
            correlation = float(merged["our"].corr(merged["rbn"]))

            # MAPE
            mask = merged["rbn"] != 0
            if mask.any():
                pct_errors = (
                    abs(merged.loc[mask, "our"] - merged.loc[mask, "rbn"])
                    / abs(merged.loc[mask, "rbn"])
                    * 100
                )
                mape = float(pct_errors.mean())
                max_deviation = float(pct_errors.max())
            else:
                mape = None
                max_deviation = None

            # Determine status
            if mape is not None:
                if mape > CRITICAL_MAPE_THRESHOLD:
                    status = "fail"
                elif mape > MAPE_THRESHOLD or (
                    correlation is not None and correlation < CORRELATION_THRESHOLD
                ):
                    status = "warn"
                else:
                    status = "pass"
            else:
                status = "warn"

            return MetricValidationResult(
                metric_id=metric_id,
                our_data_count=len(our_data),
                rbn_data_count=len(golden),
                overlap_count=overlap_count,
                correlation=correlation,
                mape=mape,
                max_deviation=max_deviation,
                status=status,
            )

        except Exception as e:
            logger.error(f"Error validating {metric_id}: {e}")
            return MetricValidationResult(
                metric_id=metric_id,
                our_data_count=0,
                rbn_data_count=0,
                overlap_count=0,
                correlation=None,
                mape=None,
                max_deviation=None,
                status="error",
                error_message=str(e),
            )

    def run_batch(
        self,
        metrics: Optional[list[str]] = None,
        days: int = 30,
    ) -> ValidationBatchResult:
        """Run validation for multiple metrics."""
        if metrics is None:
            metrics = P1_METRICS + P2_METRICS

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        results = []

        for metric_id in metrics:
            logger.info(f"Validating {metric_id}...")
            result = self.validate_metric(metric_id, start_date, end_date)
            results.append(result)

        # Calculate summary
        passed = sum(1 for r in results if r.status == "pass")
        warned = sum(1 for r in results if r.status == "warn")
        failed = sum(1 for r in results if r.status == "fail")
        errors = sum(1 for r in results if r.status == "error")
        no_data = sum(1 for r in results if r.status == "no_data")

        return ValidationBatchResult(
            run_id=run_id,
            run_timestamp=datetime.now(),
            metrics_validated=len(metrics),
            passed=passed,
            warned=warned,
            failed=failed,
            errors=errors,
            no_data=no_data,
            results=results,
        )

    def save_json_report(self, result: ValidationBatchResult) -> Path:
        """Save validation result as JSON."""
        output_path = self.reports_dir / f"validation_{result.run_id}.json"
        with open(output_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info(f"JSON report saved: {output_path}")
        return output_path

    def generate_html_report(self, result: ValidationBatchResult) -> Path:
        """Generate HTML validation report."""
        output_path = self.reports_dir / f"validation_{result.run_id}.html"

        # Status colors
        status_colors = {
            "pass": "#28a745",
            "warn": "#ffc107",
            "fail": "#dc3545",
            "error": "#6c757d",
            "no_data": "#17a2b8",
        }

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>UTXOracle Validation Report - {result.run_id}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f8f9fa; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
        .summary-card {{ padding: 15px 25px; border-radius: 8px; text-align: center; }}
        .summary-card.pass {{ background: #d4edda; color: #155724; }}
        .summary-card.warn {{ background: #fff3cd; color: #856404; }}
        .summary-card.fail {{ background: #f8d7da; color: #721c24; }}
        .summary-card h2 {{ margin: 0; font-size: 36px; }}
        .summary-card p {{ margin: 5px 0 0 0; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #dee2e6; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        .status {{ padding: 4px 12px; border-radius: 4px; color: white; font-weight: 500; }}
        .metric-name {{ font-weight: 600; }}
        .number {{ font-family: 'SF Mono', Monaco, monospace; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; color: #6c757d; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 UTXOracle Validation Report</h1>
        <p>Run ID: <code>{result.run_id}</code> | Timestamp: {result.run_timestamp.strftime("%Y-%m-%d %H:%M:%S")}</p>

        <div class="summary">
            <div class="summary-card pass">
                <h2>{result.passed}</h2>
                <p>Passed</p>
            </div>
            <div class="summary-card warn">
                <h2>{result.warned}</h2>
                <p>Warnings</p>
            </div>
            <div class="summary-card fail">
                <h2>{result.failed}</h2>
                <p>Failed</p>
            </div>
        </div>

        <h2>Metric Details</h2>
        <table>
            <thead>
                <tr>
                    <th>Metric</th>
                    <th>Status</th>
                    <th>Correlation</th>
                    <th>MAPE</th>
                    <th>Max Deviation</th>
                    <th>Data Points</th>
                </tr>
            </thead>
            <tbody>
"""
        for r in result.results:
            color = status_colors.get(r.status, "#6c757d")
            corr = f"{r.correlation:.3f}" if r.correlation is not None else "N/A"
            mape = f"{r.mape:.2f}%" if r.mape is not None else "N/A"
            max_dev = (
                f"{r.max_deviation:.2f}%" if r.max_deviation is not None else "N/A"
            )

            html += f"""
                <tr>
                    <td class="metric-name">{r.metric_id}</td>
                    <td><span class="status" style="background: {color}">{r.status.upper()}</span></td>
                    <td class="number">{corr}</td>
                    <td class="number">{mape}</td>
                    <td class="number">{max_dev}</td>
                    <td class="number">{r.overlap_count}/{r.rbn_data_count}</td>
                </tr>
"""
            if r.error_message:
                html += f"""
                <tr>
                    <td colspan="6" style="color: #dc3545; font-size: 13px;">⚠️ {r.error_message}</td>
                </tr>
"""

        html += f"""
            </tbody>
        </table>

        <div class="footer">
            <p>Thresholds: Correlation > {CORRELATION_THRESHOLD}, MAPE < {MAPE_THRESHOLD}%, Critical MAPE > {CRITICAL_MAPE_THRESHOLD}%</p>
            <p>Generated by UTXOracle Validation System | Reference: ResearchBitcoin.net</p>
        </div>
    </div>
</body>
</html>
"""
        with open(output_path, "w") as f:
            f.write(html)

        logger.info(f"HTML report saved: {output_path}")
        return output_path


async def send_alert(result: ValidationBatchResult, webhook_url: str) -> bool:
    """Send alert via webhook on validation failures."""
    import httpx

    # Only alert on failures
    if result.failed == 0 and result.errors == 0:
        logger.info("No failures to alert")
        return True

    failed_metrics = [r for r in result.results if r.status in ("fail", "error")]

    payload = {
        "text": "🚨 UTXOracle Validation Alert",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 Validation Failures Detected",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Run ID*: {result.run_id}\n*Failed*: {result.failed}\n*Errors*: {result.errors}",
                },
            },
        ],
    }

    for r in failed_metrics[:5]:  # Limit to 5 failures
        payload["blocks"].append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"• *{r.metric_id}*: {r.status.upper()} - MAPE: {r.mape:.2f}% | {r.error_message or ''}",
                },
            }
        )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
            logger.info("Alert sent successfully")
            return True
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
        return False


def main():
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="Run batch metric validation")
    parser.add_argument(
        "--metrics",
        type=str,
        help="Comma-separated list of metrics (default: P1+P2)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to validate (default: 30)",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate HTML report",
    )
    parser.add_argument(
        "--alert",
        action="store_true",
        help="Send webhook alert on failures",
    )
    parser.add_argument(
        "--webhook-url",
        type=str,
        help="Webhook URL for alerts (or use VALIDATION_WEBHOOK_URL env)",
    )

    args = parser.parse_args()

    # Parse metrics
    metrics = None
    if args.metrics:
        metrics = [m.strip() for m in args.metrics.split(",")]

    # Run validation
    validator = ValidationBatch()
    result = validator.run_batch(metrics=metrics, days=args.days)

    # Save JSON report (always)
    validator.save_json_report(result)

    # Generate HTML if requested
    if args.html:
        html_path = validator.generate_html_report(result)
        print(f"HTML report: {html_path}")

    # Send alert if requested
    if args.alert:
        webhook_url = args.webhook_url or os.getenv("VALIDATION_WEBHOOK_URL")
        if webhook_url:
            asyncio.run(send_alert(result, webhook_url))
        else:
            logger.warning("No webhook URL provided for alerts")

    # Print summary
    print("\n" + "=" * 50)
    print("VALIDATION SUMMARY")
    print("=" * 50)
    print(f"Metrics validated: {result.metrics_validated}")
    print(f"✅ Passed: {result.passed}")
    print(f"⚠️  Warnings: {result.warned}")
    print(f"❌ Failed: {result.failed}")
    print(f"🔴 Errors: {result.errors}")
    print(f"📭 No data: {result.no_data}")
    print("=" * 50)

    # Exit with error code if failures
    if result.failed > 0 or result.errors > 0:
        exit(1)


if __name__ == "__main__":
    main()
