#!/usr/bin/env python3
"""
Import Intraday Prices from HTML to DuckDB

Parses historical HTML files and imports all intraday price points to DuckDB.

Each HTML file contains:
- const heights_smooth = [919111.0064, 919111.0113, ...] (23,000 points)
- const prices = [113567.53, 119521.91, ...] (23,000 points)

This creates a queryable database of ~15.8M price points (685 days × 23k points).

Usage:
    python scripts/import_intraday_prices.py
    python scripts/import_intraday_prices.py --dry-run  # Preview only
    python scripts/import_intraday_prices.py --limit 10  # Test with 10 files
"""

import os
import sys
import re
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import duckdb
from dotenv import load_dotenv
from scripts.config import UTXORACLE_DB_PATH

# Load config
load_dotenv()
DUCKDB_PATH = os.getenv(
    "DUCKDB_PATH", str(UTXORACLE_DB_PATH)
)
HISTORICAL_DIR = Path(__file__).parent.parent / "historical_data" / "html_files"
LOG_DIR = Path(__file__).parent.parent / "logs"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


def parse_html_intraday(file_path: Path) -> Optional[Dict]:
    """
    Parse HTML file and extract intraday price points.

    Args:
        file_path: Path to HTML file

    Returns:
        dict with keys: date, heights (list), prices (list)
        None if parsing fails
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract date from filename: UTXOracle_YYYY-MM-DD.html
        filename = file_path.name
        match = re.search(r"UTXOracle_(\d{4}-\d{2}-\d{2})\.html", filename)
        if not match:
            logging.warning(f"Could not extract date from filename: {filename}")
            return None

        date_str = match.group(1)

        # Extract heights_smooth array
        heights_match = re.search(r"const heights_smooth = \[([\d., ]+)\]", content)
        if not heights_match:
            logging.warning(f"No heights_smooth array found in {filename}")
            return None

        heights_str = heights_match.group(1)
        heights = [float(h.strip()) for h in heights_str.split(",") if h.strip()]

        # Extract prices array
        prices_match = re.search(r"const prices = \[([\d., ]+)\]", content)
        if not prices_match:
            logging.warning(f"No prices array found in {filename}")
            return None

        prices_str = prices_match.group(1)
        prices = [float(p.strip()) for p in prices_str.split(",") if p.strip()]

        # Validate
        if len(heights) != len(prices):
            logging.warning(
                f"Array length mismatch in {filename}: {len(heights)} heights vs {len(prices)} prices"
            )
            return None

        if len(heights) == 0:
            logging.warning(f"Empty arrays in {filename}")
            return None

        return {
            "date": date_str,
            "heights": heights,
            "prices": prices,
        }

    except Exception as e:
        logging.error(f"Error parsing {file_path}: {e}")
        return None


def create_intraday_table(conn: duckdb.DuckDBPyConnection):
    """
    Create intraday_prices table if it doesn't exist.

    Schema:
        date DATE           - Trading date
        block_height INT    - Bitcoin block height (floor of heights_smooth value)
        price DECIMAL       - UTXOracle price at this point
        sequence_idx INT    - Index in intraday array (0-based)

    NOTE: No PRIMARY KEY or indices during initial creation for faster bulk insert.
    These will be added after data import.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS intraday_prices (
            date DATE NOT NULL,
            block_height INTEGER NOT NULL,
            price DECIMAL(12, 2) NOT NULL,
            sequence_idx INTEGER NOT NULL
        )
    """)

    logging.info(
        "✅ Created intraday_prices table (without constraints for fast insert)"
    )


def import_to_duckdb(
    data_records: List[Dict], db_path: str, dry_run: bool = False
) -> int:
    """
    Import intraday price data into DuckDB.

    Args:
        data_records: List of dicts with parsed intraday data
        db_path: Path to DuckDB file
        dry_run: If True, only preview without inserting

    Returns:
        Total number of intraday points inserted
    """
    total_points = sum(len(r["prices"]) for r in data_records)

    if dry_run:
        logging.info("[DRY-RUN] Would insert:")
        for record in data_records[:3]:  # Show first 3
            logging.info(f"  {record['date']}: {len(record['prices'])} intraday points")
        logging.info(f"  ... and {len(data_records) - 3} more dates")
        logging.info(f"  Total: {total_points:,} intraday points")
        return 0

    try:
        with duckdb.connect(db_path) as conn:
            # Create table
            create_intraday_table(conn)

            # Clear existing data (replace strategy)
            dates = [r["date"] for r in data_records]
            if dates:
                placeholders = ", ".join(["?"] * len(dates))
                conn.execute(
                    f"DELETE FROM intraday_prices WHERE date IN ({placeholders})", dates
                )
                logging.info(f"Cleared existing data for {len(dates)} dates")

            # Use COPY FROM CSV for 10-100x faster import
            import csv
            import tempfile

            logging.info("Preparing CSV for fast COPY import...")

            # Create temporary CSV file
            csv_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False, newline=""
            )
            csv_path = csv_file.name

            try:
                writer = csv.writer(csv_file)
                row_count = 0

                for i, record in enumerate(data_records):
                    date_str = record["date"]
                    heights = record["heights"]
                    prices = record["prices"]

                    # Write rows for this date
                    for idx, (height, price) in enumerate(zip(heights, prices)):
                        block_height = int(height)  # Floor to get block number
                        writer.writerow([date_str, block_height, round(price, 2), idx])
                        row_count += 1

                    if (i + 1) % 50 == 0:
                        logging.info(
                            f"  Prepared {i + 1}/{len(data_records)} dates ({row_count:,} points)"
                        )

                csv_file.close()

                logging.info(f"✅ CSV prepared: {row_count:,} rows")
                logging.info("Importing from CSV (fast COPY)...")

                # Fast COPY import
                conn.execute(f"""
                    COPY intraday_prices (date, block_height, price, sequence_idx)
                    FROM '{csv_path}'
                    (DELIMITER ',', HEADER false)
                """)

                # Verify count - simple total count check
                db_count = conn.execute(
                    "SELECT COUNT(*) FROM intraday_prices"
                ).fetchone()[0]

                logging.info(
                    f"Validation: DB has {db_count:,} rows, expected {row_count:,}"
                )

                if db_count < row_count:
                    raise Exception(
                        f"Import validation failed: DB has {db_count} rows, expected at least {row_count}"
                    )

                inserted = row_count
                logging.info(f"✅ Imported {inserted:,} rows (validated)")

            finally:
                # Clean up temporary CSV
                import os

                try:
                    os.unlink(csv_path)
                    logging.info("✅ Cleaned up temporary CSV")
                except:
                    pass

            logging.info(f"✅ Inserted {inserted:,} intraday price points")

            # Add constraints and indices AFTER bulk insert for better performance
            logging.info("Creating indices and constraints...")

            try:
                # Add index for fast block_height lookups
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_intraday_block
                    ON intraday_prices(date, block_height)
                """)
                logging.info("✅ Created block_height index")

                # Add index for date+sequence lookups (acts as de-facto PRIMARY KEY)
                conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_intraday_pk
                    ON intraday_prices(date, sequence_idx)
                """)
                logging.info("✅ Created unique index on (date, sequence_idx)")

            except Exception as e:
                logging.warning(f"Index creation issue (may already exist): {e}")

            return inserted

    except Exception as e:
        logging.error(f"Database error: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Import historical intraday prices to DuckDB"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview only, don't insert"
    )
    parser.add_argument("--limit", type=int, help="Limit number of files to process")
    args = parser.parse_args()

    # Check historical directory exists
    if not HISTORICAL_DIR.exists():
        logging.error(f"Historical directory not found: {HISTORICAL_DIR}")
        sys.exit(1)

    # Get all HTML files
    html_files = sorted(HISTORICAL_DIR.glob("UTXOracle_*.html"))
    if not html_files:
        logging.error(f"No HTML files found in {HISTORICAL_DIR}")
        sys.exit(1)

    logging.info(f"Found {len(html_files)} HTML files")

    # Apply limit if specified
    if args.limit:
        html_files = html_files[: args.limit]
        logging.info(f"Limited to first {args.limit} files")

    # Parse all files
    data_records = []
    for i, file_path in enumerate(html_files):
        if i % 50 == 0 and i > 0:
            logging.info(f"Parsing {i}/{len(html_files)}...")

        record = parse_html_intraday(file_path)
        if record:
            data_records.append(record)

    logging.info(f"Successfully parsed {len(data_records)}/{len(html_files)} files")

    if not data_records:
        logging.error("No valid data extracted")
        sys.exit(1)

    # Calculate stats
    total_points = sum(len(r["prices"]) for r in data_records)
    avg_points_per_day = total_points / len(data_records)

    logging.info(f"\nParsed {total_points:,} intraday price points")
    logging.info(f"Average {avg_points_per_day:.0f} points per day")

    # Import to DuckDB
    inserted = import_to_duckdb(data_records, DUCKDB_PATH, dry_run=args.dry_run)

    if not args.dry_run:
        # Verify
        with duckdb.connect(DUCKDB_PATH, read_only=True) as conn:
            count = conn.execute("SELECT COUNT(*) FROM intraday_prices").fetchone()[0]
            dates = conn.execute(
                "SELECT COUNT(DISTINCT date) FROM intraday_prices"
            ).fetchone()[0]

            logging.info("\n✅ Import complete!")
            logging.info(f"   Total points in DB: {count:,}")
            logging.info(f"   Dates covered: {dates}")
            logging.info(f"   Avg points/day: {count / dates:.0f}")


if __name__ == "__main__":
    main()
