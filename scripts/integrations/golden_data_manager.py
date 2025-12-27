#!/usr/bin/env python3
"""
Golden Data Manager for RBN validation.

Downloads reference data from ResearchBitcoin.net API and stores as Parquet files.
Used for offline validation tests without consuming API quota.

Usage:
    # Download all P1 metrics for last 90 days
    python scripts/integrations/golden_data_manager.py --download

    # Update specific metric
    python scripts/integrations/golden_data_manager.py --metric mvrv_z

    # List available golden data
    python scripts/integrations/golden_data_manager.py --list

    # Generate synthetic golden data (for testing without API)
    python scripts/integrations/golden_data_manager.py --generate-synthetic
"""

import argparse
import asyncio
import json
import logging
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Golden data directory
GOLDEN_DATA_DIR = Path("tests/validation/golden_data")

# P1 Priority metrics for validation
P1_METRICS = ["mvrv_z", "sopr", "nupl", "realized_cap"]

# P2 Priority metrics
P2_METRICS = ["liveliness", "power_law", "thermocap", "stocktoflow_nominal"]

# Metadata file
METADATA_FILE = GOLDEN_DATA_DIR / "metadata.json"


def ensure_dir():
    """Ensure golden data directory exists."""
    GOLDEN_DATA_DIR.mkdir(parents=True, exist_ok=True)


async def download_metric(
    metric_id: str,
    start_date: date,
    end_date: date,
    force: bool = False,
) -> bool:
    """
    Download metric from RBN API and save as Parquet.

    Args:
        metric_id: Metric identifier
        start_date: Start date
        end_date: End date
        force: Overwrite existing data

    Returns:
        True if successful
    """
    from scripts.integrations.rbn_fetcher import RBNFetcher

    output_path = GOLDEN_DATA_DIR / f"{metric_id}.parquet"

    if output_path.exists() and not force:
        logger.info(f"Golden data exists for {metric_id}, use --force to overwrite")
        return True

    fetcher = RBNFetcher()
    try:
        response = await fetcher.fetch_metric(
            metric_id=metric_id,
            start_date=start_date,
            end_date=end_date,
            force_refresh=True,
        )

        if not response.data:
            logger.warning(f"No data returned for {metric_id}")
            return False

        # Convert to DataFrame
        df = pd.DataFrame(
            [{"date": dp.date, "value": dp.value} for dp in response.data]
        )

        # Save as Parquet
        df.to_parquet(output_path, index=False)
        logger.info(f"Saved {len(df)} records to {output_path}")

        # Update metadata
        update_metadata(metric_id, start_date, end_date, len(df))

        return True

    except Exception as e:
        logger.error(f"Failed to download {metric_id}: {e}")
        return False
    finally:
        await fetcher.close()


def generate_synthetic_golden_data(days: int = 365) -> None:
    """
    Generate synthetic golden data for testing without API access.

    Creates realistic-looking metric values based on historical patterns.
    NOT for production validation - only for testing infrastructure.
    """
    ensure_dir()
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    dates = pd.date_range(start=start_date, end=end_date, freq="D")

    np.random.seed(42)  # Reproducible

    # MVRV Z-Score: typically between -1 and 3, with mean around 1
    mvrv_z = pd.DataFrame(
        {
            "date": dates,
            "value": np.clip(
                1.0 + np.cumsum(np.random.normal(0, 0.05, len(dates))), -1, 4
            ),
        }
    )
    mvrv_z.to_parquet(GOLDEN_DATA_DIR / "mvrv_z.parquet", index=False)
    logger.info(f"Generated synthetic mvrv_z: {len(mvrv_z)} records")

    # SOPR: typically between 0.95 and 1.05, centered around 1
    sopr = pd.DataFrame(
        {
            "date": dates,
            "value": np.clip(1.0 + np.random.normal(0, 0.02, len(dates)), 0.9, 1.2),
        }
    )
    sopr.to_parquet(GOLDEN_DATA_DIR / "sopr.parquet", index=False)
    logger.info(f"Generated synthetic sopr: {len(sopr)} records")

    # NUPL: typically between -0.5 and 0.75
    nupl = pd.DataFrame(
        {
            "date": dates,
            "value": np.clip(
                0.3 + np.cumsum(np.random.normal(0, 0.01, len(dates))), -0.5, 0.75
            ),
        }
    )
    nupl.to_parquet(GOLDEN_DATA_DIR / "nupl.parquet", index=False)
    logger.info(f"Generated synthetic nupl: {len(nupl)} records")

    # Realized Cap: around $400-600B, growing slowly
    base_cap = 500_000_000_000  # $500B
    realized_cap = pd.DataFrame(
        {
            "date": dates,
            "value": base_cap
            + np.cumsum(np.random.normal(100_000_000, 500_000_000, len(dates))),
        }
    )
    realized_cap.to_parquet(GOLDEN_DATA_DIR / "realized_cap.parquet", index=False)
    logger.info(f"Generated synthetic realized_cap: {len(realized_cap)} records")

    # Liveliness: between 0.5 and 0.7
    liveliness = pd.DataFrame(
        {
            "date": dates,
            "value": np.clip(
                0.6 + np.cumsum(np.random.normal(0, 0.002, len(dates))), 0.5, 0.7
            ),
        }
    )
    liveliness.to_parquet(GOLDEN_DATA_DIR / "liveliness.parquet", index=False)
    logger.info(f"Generated synthetic liveliness: {len(liveliness)} records")

    # Power Law price: approximately follows ln(price) = a + b*ln(days)
    days_since_genesis = np.arange(5000, 5000 + len(dates))
    power_law = pd.DataFrame(
        {
            "date": dates,
            "value": np.exp(
                -17.0
                + 5.8 * np.log(days_since_genesis)
                + np.random.normal(0, 0.1, len(dates))
            ),
        }
    )
    power_law.to_parquet(GOLDEN_DATA_DIR / "power_law.parquet", index=False)
    logger.info(f"Generated synthetic power_law: {len(power_law)} records")

    # Update metadata
    metadata = {
        "generated_at": date.today().isoformat(),
        "type": "synthetic",
        "warning": "NOT for production validation - synthetic data only",
        "metrics": {
            m: {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "records": days + 1,
            }
            for m in [
                "mvrv_z",
                "sopr",
                "nupl",
                "realized_cap",
                "liveliness",
                "power_law",
            ]
        },
    }
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Synthetic golden data generated in {GOLDEN_DATA_DIR}")


def update_metadata(metric_id: str, start_date: date, end_date: date, records: int):
    """Update metadata file with download info."""
    if METADATA_FILE.exists():
        with open(METADATA_FILE) as f:
            metadata = json.load(f)
    else:
        metadata = {"type": "downloaded", "metrics": {}}

    metadata["metrics"][metric_id] = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "records": records,
        "downloaded_at": date.today().isoformat(),
    }

    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)


def list_golden_data() -> None:
    """List available golden data files."""
    ensure_dir()

    parquet_files = list(GOLDEN_DATA_DIR.glob("*.parquet"))

    if not parquet_files:
        print("No golden data files found.")
        print("Run with --generate-synthetic to create test data")
        print("Run with --download to download from RBN API")
        return

    print(f"\nGolden Data Directory: {GOLDEN_DATA_DIR}")
    print("-" * 60)

    for f in sorted(parquet_files):
        df = pd.read_parquet(f)
        metric_id = f.stem
        date_range = f"{df['date'].min()} to {df['date'].max()}"
        print(f"  {metric_id:20s} | {len(df):5d} records | {date_range}")

    print("-" * 60)

    # Show metadata if exists
    if METADATA_FILE.exists():
        with open(METADATA_FILE) as f:
            metadata = json.load(f)
        print(f"Type: {metadata.get('type', 'unknown')}")
        if metadata.get("type") == "synthetic":
            print("⚠️  WARNING: Synthetic data - NOT for production validation")


async def download_all(
    metrics: list[str],
    days: int = 90,
    force: bool = False,
) -> dict[str, bool]:
    """
    Download all specified metrics.

    Args:
        metrics: List of metric IDs
        days: Number of days of history
        force: Overwrite existing

    Returns:
        Dict of metric_id -> success
    """
    ensure_dir()
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    results = {}
    for metric_id in metrics:
        print(f"Downloading {metric_id}...")
        results[metric_id] = await download_metric(
            metric_id, start_date, end_date, force
        )

    return results


def main():
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Manage golden reference data for RBN validation"
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download all P1 metrics from RBN API",
    )
    parser.add_argument(
        "--metric",
        type=str,
        help="Download specific metric",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Number of days of history (default: 90)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing data",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available golden data",
    )
    parser.add_argument(
        "--generate-synthetic",
        action="store_true",
        help="Generate synthetic test data (no API needed)",
    )
    parser.add_argument(
        "--include-p2",
        action="store_true",
        help="Include P2 metrics when downloading",
    )

    args = parser.parse_args()

    if args.list:
        list_golden_data()
        return

    if args.generate_synthetic:
        generate_synthetic_golden_data(args.days)
        print("\n✅ Synthetic golden data generated successfully")
        list_golden_data()
        return

    if args.download or args.metric:
        if args.metric:
            metrics = [args.metric]
        else:
            metrics = P1_METRICS.copy()
            if args.include_p2:
                metrics.extend(P2_METRICS)

        results = asyncio.run(download_all(metrics, args.days, args.force))

        print("\n" + "=" * 40)
        print("Download Results:")
        for metric_id, success in results.items():
            status = "✅" if success else "❌"
            print(f"  {status} {metric_id}")

        return

    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
