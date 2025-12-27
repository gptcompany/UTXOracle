#!/usr/bin/env python3
"""
Import Historical HTML Data to DuckDB

Parses 672 days of historical UTXOracle HTML files and imports data into DuckDB.
Extracts: date, price from const prices = [...] JavaScript array

Usage:
    python scripts/import_historical_data.py
    python scripts/import_historical_data.py --dry-run  # Preview only
"""

import os
import sys
import re
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict

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

# Will be configured in main()
logger = logging.getLogger(__name__)


def parse_html_file(file_path: Path) -> Optional[Dict]:
    """
    Parse UTXOracle HTML file and extract price data.

    Args:
        file_path: Path to HTML file

    Returns:
        dict with keys: date, price, confidence, tx_count
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

        # Extract FINAL price from prices array (last element after all blocks processed)
        # UTXOracle.py generates: const prices = [p1, p2, ..., pFINAL]
        # The last value is the final consensus price after processing all blocks
        prices_match = re.search(r"const prices = \[([0-9., ]+)\]", content)
        if not prices_match:
            logging.warning(f"No prices array found in {filename}")
            return None

        prices_str = prices_match.group(1)
        prices = [float(p.strip()) for p in prices_str.split(",") if p.strip()]

        if not prices:
            logging.warning(f"Empty prices array in {filename}")
            return None

        # Take LAST price (final consensus)
        price = prices[-1]

        # Validate price is in reasonable range
        if not (10000 <= price <= 500000):
            logging.warning(f"Price ${price:,.2f} out of range in {filename}")
            return None

        # Try to extract confidence (may not exist in all files)
        confidence = 1.0  # Default high confidence for historical data
        conf_match = re.search(r'confidence["\']?\s*:\s*([0-9.]+)', content)
        if conf_match:
            confidence = float(conf_match.group(1))

        return {
            "date": date_str,
            "price": round(price, 2),
            "confidence": confidence,
        }

    except Exception as e:
        logging.error(f"Error parsing {file_path}: {e}")
        return None


def setup_file_logging(log_dir: Path) -> str:
    """
    Setup logging to file + console.

    Args:
        log_dir: Directory to save log files

    Returns:
        Path to log file created
    """
    # Create logs directory if needed
    log_dir.mkdir(exist_ok=True)

    # Log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"import_historical_{timestamp}.log"

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # File handler (detailed format)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(funcName)s: %(message)s"
    )
    file_handler.setFormatter(file_formatter)

    # Console handler (simple format)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console_handler.setFormatter(console_formatter)

    # Add both handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.info(f"Logging to file: {log_file}")
    return str(log_file)


def check_temporal_gaps(data_records: list) -> list[tuple]:
    """
    Check for temporal gaps in the data series.

    Args:
        data_records: List of dicts with 'date' field

    Returns:
        List of (gap_start, gap_end, gap_days) tuples
    """
    if not data_records:
        return []

    # Sort by date
    sorted_records = sorted(data_records, key=lambda r: r["date"])
    dates = [datetime.strptime(r["date"], "%Y-%m-%d").date() for r in sorted_records]

    gaps = []
    for i in range(len(dates) - 1):
        current = dates[i]
        next_date = dates[i + 1]
        expected_next = current + timedelta(days=1)

        if next_date != expected_next:
            gap_days = (next_date - current).days - 1
            if gap_days > 0:
                gaps.append((current, next_date, gap_days))

    return gaps


def import_to_duckdb(data_records: list, db_path: str, dry_run: bool = False):
    """
    Import parsed data into DuckDB price_analysis table.

    Args:
        data_records: List of dicts with parsed data
        db_path: Path to DuckDB file
        dry_run: If True, only preview without inserting
    """
    if dry_run:
        logging.info("[DRY-RUN] Would insert into DuckDB:")
        for record in data_records[:5]:  # Show first 5
            logging.info(f"  {record}")
        logging.info(f"  ... and {len(data_records) - 5} more records")
        return

    try:
        with duckdb.connect(db_path) as conn:
            # Ensure table exists (schema from daily_analysis.py)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS price_analysis (
                    date DATE PRIMARY KEY,
                    exchange_price DECIMAL(12, 2),
                    utxoracle_price DECIMAL(12, 2),
                    price_difference DECIMAL(12, 2),
                    avg_pct_diff DECIMAL(6, 2),
                    confidence DECIMAL(5, 4),
                    tx_count INTEGER,
                    is_valid BOOLEAN DEFAULT TRUE
                )
            """)

            # Check which dates already exist (for duplicate reporting)
            existing_dates = set()
            result = conn.execute("SELECT date FROM price_analysis").fetchall()
            existing_dates = {str(row[0]) for row in result}

            # Insert records
            insert_sql = """
                INSERT OR REPLACE INTO price_analysis (
                    date, utxoracle_price, exchange_price, price_difference,
                    avg_pct_diff, confidence, tx_count, is_valid
                ) VALUES (?, ?, NULL, NULL, NULL, ?, NULL, ?)
            """

            inserted = 0
            updated = 0
            for record in data_records:
                try:
                    # Validate confidence (0-1 range)
                    confidence = max(0.0, min(1.0, record["confidence"]))

                    # Mark as valid if confidence >= 0.3
                    is_valid = confidence >= 0.3

                    # Check if this is an update or insert
                    is_update = record["date"] in existing_dates

                    conn.execute(
                        insert_sql,
                        [
                            record["date"],
                            record["price"],
                            confidence,
                            is_valid,
                        ],
                    )

                    if is_update:
                        updated += 1
                        logging.debug(f"Updated existing record: {record['date']}")
                    else:
                        inserted += 1

                except Exception as e:
                    logging.warning(f"Failed to insert {record['date']}: {e}")
                    continue

            logging.info(
                f"Inserted {inserted} new records, updated {updated} existing records "
                f"({inserted + updated}/{len(data_records)} total processed)"
            )

    except Exception as e:
        logging.error(f"Database error: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Import historical HTML data to DuckDB"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview only, don't insert"
    )
    parser.add_argument("--limit", type=int, help="Limit number of files to process")
    args = parser.parse_args()

    # Setup file logging
    log_file = setup_file_logging(LOG_DIR)

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
        if i % 50 == 0:
            logging.info(f"Processing {i}/{len(html_files)}...")

        record = parse_html_file(file_path)
        if record:
            data_records.append(record)

    logging.info(f"Successfully parsed {len(data_records)}/{len(html_files)} files")

    if not data_records:
        logging.error("No valid data extracted")
        sys.exit(1)

    # Check for temporal gaps
    gaps = check_temporal_gaps(data_records)
    if gaps:
        logging.warning(f"Found {len(gaps)} temporal gaps in data series:")
        for gap_start, gap_end, gap_days in gaps:
            logging.warning(f"  Gap: {gap_start} → {gap_end} ({gap_days} days missing)")
    else:
        logging.info("✅ No temporal gaps detected (continuous data series)")

    # Import to DuckDB
    import_to_duckdb(data_records, DUCKDB_PATH, dry_run=args.dry_run)

    # Summary stats
    if data_records:
        prices = [r["price"] for r in data_records]
        logging.info(f"Price range: ${min(prices):,.2f} - ${max(prices):,.2f}")
        logging.info(
            f"Date range: {data_records[0]['date']} - {data_records[-1]['date']}"
        )

    logging.info(f"✅ Import complete. Log saved to: {log_file}")


if __name__ == "__main__":
    main()
