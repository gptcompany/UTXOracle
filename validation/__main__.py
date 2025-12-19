"""CLI entry point for validation framework.

Usage:
    python -m validation                  # Run full validation suite
    python -m validation --numerical      # Numerical validation only
    python -m validation --visual         # Visual validation only
    python -m validation --metric mvrv    # Single metric validation
    python -m validation --update-baselines  # Refresh baseline files
"""

import argparse
import sys
from pathlib import Path

from validation.framework.checkonchain_fetcher import CheckOnChainFetcher
from validation.framework.comparison_engine import ComparisonEngine
from validation.framework.config import AVAILABLE_METRICS
from validation.framework.visual_validator import VisualValidator


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="validation",
        description="Validate UTXOracle metrics against CheckOnChain.com reference",
        epilog="Examples:\n"
        "  python -m validation                  # Full suite\n"
        "  python -m validation --metric mvrv    # Single metric\n"
        "  python -m validation --update-baselines  # Refresh baselines",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--numerical",
        action="store_true",
        help="Run numerical validation only (API value comparison)",
    )

    parser.add_argument(
        "--visual",
        action="store_true",
        help="Run visual validation only (screenshot comparison)",
    )

    parser.add_argument(
        "--metric",
        type=str,
        choices=AVAILABLE_METRICS,
        help=f"Validate single metric. Choices: {', '.join(AVAILABLE_METRICS)}",
    )

    parser.add_argument(
        "--update-baselines",
        action="store_true",
        help="Refresh baseline files from CheckOnChain",
    )

    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8000",
        help="UTXOracle API base URL (default: http://localhost:8000)",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="validation/reports",
        help="Directory for validation reports (default: validation/reports)",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    return parser.parse_args()


def update_baselines(quiet: bool = False) -> int:
    """Update baseline files from CheckOnChain.

    Returns:
        Exit code (0 = success, 1 = partial failure)
    """
    if not quiet:
        print("Updating baselines from CheckOnChain...")

    fetcher = CheckOnChainFetcher()
    updated = fetcher.update_all_baselines()

    if not quiet:
        print(f"\nUpdated {len(updated)} baseline files")

    return 0 if len(updated) == len(fetcher.ENDPOINTS) else 1


def run_numerical_validation(
    api_url: str,
    output_dir: Path,
    metric: str | None = None,
    quiet: bool = False,
) -> int:
    """Run numerical validation.

    Returns:
        Exit code (0 = all pass, 1 = failures)
    """
    if not quiet:
        print(f"Running numerical validation against {api_url}...")

    engine = ComparisonEngine(api_base_url=api_url)
    results = engine.run_numerical_validation()

    # Filter results if specific metric requested
    if metric:
        filtered = [r for r in results if r.metric.startswith(metric)]
        if not filtered and not quiet:
            print(f"Warning: No validation results for metric '{metric}'")
            print("  Available validated metrics: mvrv, nupl, hash_ribbons")
            print("  (Other metrics in config are pending validator implementation)")
        # Update engine's stored results to only include filtered
        engine.numerical_results = filtered
        engine.validator.results = filtered
        results = filtered

    # Print results
    if not quiet:
        print("\n" + engine.validator.generate_report())

    # Save report
    report_path = engine.save_report(output_dir=output_dir)
    if not quiet:
        print(f"\nReport saved: {report_path}")

    # Return exit code based on results
    failures = sum(1 for r in results if r.status in ("FAIL", "ERROR"))
    return 1 if failures > 0 else 0


def run_visual_validation(
    metric: str | None = None,
    quiet: bool = False,
) -> int:
    """Run visual validation.

    This generates workflow instructions for screenshot comparison.
    Actual screenshot capture requires Playwright MCP.

    Returns:
        Exit code (0 = instructions generated)
    """
    if not quiet:
        print("Visual Validation Workflow")
        print("=" * 40)

    validator = VisualValidator()

    if metric:
        metrics = [metric]
    else:
        metrics = validator.get_all_metrics()

    for m in metrics:
        workflow = validator.compare_metric(m)

        if "error" in workflow:
            print(f"\n{m}: {workflow['error']}")
            continue

        if not quiet:
            print(f"\n## {m.upper()}")
            for step in workflow.get("workflow", []):
                print(f"\nStep {step['step']}: {step['action']}")
                if "details" in step:
                    details = step["details"]
                    if "url" in details:
                        print(f"  URL: {details['url']}")
                    if "path" in details:
                        print(f"  Save to: {details['path']}")
                if "instructions" in step:
                    for instruction in step["instructions"]:
                        print(f"  {instruction}")

    if not quiet:
        print("\n" + "=" * 40)
        print("Use Playwright MCP to capture screenshots, then compare visually.")

    return 0


def run_full_validation(
    api_url: str,
    output_dir: Path,
    metric: str | None = None,
    quiet: bool = False,
) -> int:
    """Run both numerical and visual validation.

    Returns:
        Exit code (0 = success, 1 = numerical failures)
    """
    # Numerical validation
    exit_code = run_numerical_validation(api_url, output_dir, metric, quiet)

    if not quiet:
        print("\n" + "=" * 40 + "\n")

    # Visual validation (instructions only)
    run_visual_validation(metric, quiet)

    return exit_code


def main() -> int:
    """Main entry point."""
    args = parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Handle --update-baselines
    if args.update_baselines:
        return update_baselines(args.quiet)

    # Handle validation modes
    if args.numerical and not args.visual:
        return run_numerical_validation(
            args.api_url, output_dir, args.metric, args.quiet
        )
    elif args.visual and not args.numerical:
        return run_visual_validation(args.metric, args.quiet)
    else:
        # Full validation (default)
        return run_full_validation(args.api_url, output_dir, args.metric, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
