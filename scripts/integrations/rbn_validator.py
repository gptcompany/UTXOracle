"""
RBN Validation Service for ResearchBitcoin.net integration (spec-035).
Tasks T017-T019: Validation service for comparing UTXOracle metrics against RBN.
"""

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from typing import Optional

from api.models.validation_models import (
    RBN_METRICS,
    MetricComparison,
    ValidationEndpointResponse,
    ValidationReport,
)

logger = logging.getLogger(__name__)


class ValidationService:
    """
    Validates UTXOracle metrics against ResearchBitcoin.net data.

    Features:
    - Fetches RBN data via RBNFetcher
    - Loads UTXOracle data from metrics database
    - Compares values with configurable tolerance
    - Generates aggregate reports
    """

    def __init__(self, fetcher: "RBNFetcher"):  # noqa: F821
        """
        Initialize validation service.

        Args:
            fetcher: RBNFetcher instance for API calls
        """
        self.fetcher = fetcher

    def load_utxoracle_metric(
        self,
        metric_id: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, float]:
        """
        Load UTXOracle metric data for date range.

        Args:
            metric_id: Metric identifier
            start_date: Start date
            end_date: End date

        Returns:
            Dictionary mapping dates to values
        """
        from scripts.integrations.metric_loader import MetricLoader

        loader = MetricLoader()

        try:
            series = loader.load_metric(metric_id, start_date, end_date)
            if series.data:
                logger.info(
                    f"Loaded {len(series.data)} points for {metric_id} from {series.source}"
                )
                return series.to_dict()
            logger.warning(f"No data found for {metric_id}")
            return {}
        except ValueError as e:
            logger.warning(f"Metric {metric_id} not supported: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error loading {metric_id}: {e}")
            return {}

    async def compare_metric(
        self,
        metric_id: str,
        start_date: date,
        end_date: Optional[date] = None,
        tolerance_pct: float = 1.0,
    ) -> list[MetricComparison]:
        """
        Compare UTXOracle and RBN values for a metric.

        Args:
            metric_id: Metric identifier
            start_date: Start date for comparison
            end_date: End date (defaults to today)
            tolerance_pct: Match tolerance percentage

        Returns:
            List of MetricComparison for each date
        """
        end_date = end_date or date.today()

        # Fetch RBN data
        rbn_response = await self.fetcher.fetch_metric(
            metric_id=metric_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Load UTXOracle data
        utxo_data = self.load_utxoracle_metric(metric_id, start_date, end_date)

        # Compare for each date in RBN response
        comparisons = []
        for dp in rbn_response.data:
            utxo_val = utxo_data.get(dp.date)
            comparison = MetricComparison.create(
                metric_id=metric_id,
                dt=dp.date,
                utxo_val=utxo_val,
                rbn_val=dp.value,
                tolerance_pct=tolerance_pct,
            )
            comparisons.append(comparison)

        return comparisons

    def generate_report(
        self,
        metric_id: str,
        comparisons: list[MetricComparison],
    ) -> ValidationReport:
        """
        Generate aggregate report from comparisons.

        Args:
            metric_id: Metric identifier
            comparisons: List of comparisons

        Returns:
            ValidationReport with aggregate statistics
        """
        metric_info = RBN_METRICS.get(metric_id)
        metric_name = metric_info.name if metric_info else metric_id

        return ValidationReport.from_comparisons(
            metric_id=metric_id,
            metric_name=metric_name,
            comparisons=comparisons,
        )

    async def validate_metric(
        self,
        metric_id: str,
        start_date: date,
        end_date: Optional[date] = None,
        tolerance_pct: float = 1.0,
    ) -> ValidationReport:
        """
        Validate a metric and return full report.

        Args:
            metric_id: Metric identifier
            start_date: Start date
            end_date: End date (defaults to today)
            tolerance_pct: Match tolerance percentage

        Returns:
            ValidationReport with comparison results
        """
        comparisons = await self.compare_metric(
            metric_id=metric_id,
            start_date=start_date,
            end_date=end_date,
            tolerance_pct=tolerance_pct,
        )

        return self.generate_report(metric_id, comparisons)

    def to_endpoint_response(
        self,
        report: ValidationReport,
        include_details: bool = False,
        comparisons: Optional[list[MetricComparison]] = None,
    ) -> ValidationEndpointResponse:
        """
        Convert report to API response format.

        Args:
            report: ValidationReport
            include_details: Include comparison details
            comparisons: Optional list of comparisons for details

        Returns:
            ValidationEndpointResponse for API
        """
        return ValidationEndpointResponse(
            metric=report.metric_id,
            date_range=(
                report.date_range_start.isoformat(),
                report.date_range_end.isoformat(),
            ),
            comparisons=report.total_comparisons,
            matches=report.matches,
            match_rate=report.match_rate_pct,
            avg_deviation_pct=report.avg_deviation_pct,
            status="success",
            details=comparisons if include_details else None,
        )


# =============================================================================
# CLI Interface (T033)
# =============================================================================


async def run_validation(
    metric_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    tolerance_pct: float = 1.0,
    report_mode: bool = False,
) -> None:
    """Run validation from CLI."""
    from scripts.integrations.rbn_fetcher import RBNFetcher

    # Default to last 30 days
    if not start_date:
        start_date = date.today() - timedelta(days=30)
    if not end_date:
        end_date = date.today()

    fetcher = RBNFetcher()
    validator = ValidationService(fetcher=fetcher)

    try:
        if report_mode:
            # Validate all priority metrics
            metrics = ["mvrv_z", "sopr", "nupl", "realized_cap"]
            print("\n=== RBN Validation Report ===\n")

            for mid in metrics:
                try:
                    report = await validator.validate_metric(
                        metric_id=mid,
                        start_date=start_date,
                        end_date=end_date,
                        tolerance_pct=tolerance_pct,
                    )
                    print(f"{report.metric_name}:")
                    print(f"  Match rate: {report.match_rate_pct:.1f}%")
                    if report.avg_deviation_pct is not None:
                        print(f"  Avg deviation: {report.avg_deviation_pct:.2f}%")
                    else:
                        print("  Avg deviation: N/A")
                    print()
                except Exception as e:
                    print(f"{mid}: ERROR - {e}")
                    print()

        else:
            # Validate single metric
            if not metric_id:
                print("Error: metric_id required (use --report for all)")
                sys.exit(1)

            report = await validator.validate_metric(
                metric_id=metric_id,
                start_date=start_date,
                end_date=end_date,
                tolerance_pct=tolerance_pct,
            )

            print(f"\n=== {report.metric_name} Validation ===")
            print(f"Date range: {start_date} to {end_date}")
            print(f"Total comparisons: {report.total_comparisons}")
            print(f"Matches: {report.matches} ({report.match_rate_pct:.1f}%)")
            print(f"Minor diffs: {report.minor_diffs}")
            print(f"Major diffs: {report.major_diffs}")
            print(f"Missing: {report.missing}")
            if report.avg_deviation_pct:
                print(f"Avg deviation: {report.avg_deviation_pct:.2f}%")
            if report.max_deviation_pct:
                print(f"Max deviation: {report.max_deviation_pct:.2f}%")
            print()

    finally:
        await fetcher.close()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate UTXOracle metrics against ResearchBitcoin.net"
    )
    parser.add_argument(
        "metric_id",
        nargs="?",
        help="Metric to validate (e.g., mvrv_z, sopr)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate full validation report for all metrics",
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1.0,
        help="Match tolerance percentage (default: 1.0)",
    )

    args = parser.parse_args()

    asyncio.run(
        run_validation(
            metric_id=args.metric_id,
            start_date=args.start_date,
            end_date=args.end_date,
            tolerance_pct=args.tolerance,
            report_mode=args.report,
        )
    )


if __name__ == "__main__":
    main()
