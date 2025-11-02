#!/usr/bin/env python3
"""
Daily Analysis Script - Compares UTXOracle vs mempool.space prices

Runs every 10 minutes (via cron) to:
1. Fetch mempool.space exchange price
2. Calculate UTXOracle price from Bitcoin Core transactions
3. Compare prices and compute difference
4. Save results to DuckDB

Spec: 003-mempool-integration-refactor
Phase: 3 - Integration Service
Tasks: T038-T047
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from typing import Dict, Optional, List
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Third-party imports
import requests
import duckdb
from dotenv import load_dotenv

# Local imports
from UTXOracle_library import UTXOracleCalculator


# =============================================================================
# Configuration Management (T038)
# =============================================================================


def load_config() -> Dict[str, str]:
    """
    Load configuration from .env file or environment variables.

    Priority: Environment variables > .env file > defaults

    Returns:
        dict: Configuration dictionary
    """
    # Load .env file if exists (override=True to prioritize .env over existing env vars)
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
        logging.info(f"Config loaded from .env file at {env_path} (override=True)")
    else:
        logging.info("Config loaded from environment variables (no .env file found)")

    config = {
        # Required settings (fail fast if missing - T064a)
        "DUCKDB_PATH": os.getenv(
            "DUCKDB_PATH",
            "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db",
        ),
        "BITCOIN_DATADIR": os.getenv(
            "BITCOIN_DATADIR", os.path.expanduser("~/.bitcoin")
        ),
        "MEMPOOL_API_URL": os.getenv("MEMPOOL_API_URL", "http://localhost:8999"),
        # Optional settings with defaults
        "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
        "ANALYSIS_INTERVAL_MINUTES": int(os.getenv("ANALYSIS_INTERVAL_MINUTES", "10")),
        "DUCKDB_BACKUP_PATH": os.getenv(
            "DUCKDB_BACKUP_PATH", "/tmp/utxoracle_backup.duckdb"
        ),
        "ALERT_WEBHOOK_URL": os.getenv("ALERT_WEBHOOK_URL"),  # None if not set
        # Validation thresholds (T042a)
        "UTXORACLE_CONFIDENCE_THRESHOLD": float(
            os.getenv("UTXORACLE_CONFIDENCE_THRESHOLD", "0.3")
        ),
        "MIN_PRICE_USD": float(os.getenv("MIN_PRICE_USD", "10000")),
        "MAX_PRICE_USD": float(os.getenv("MAX_PRICE_USD", "500000")),
    }

    return config


def validate_config(config: Dict[str, str]) -> None:
    """
    Validate required configuration exists (T064a).

    Fails fast with helpful error messages if critical vars missing.

    Args:
        config: Configuration dictionary

    Raises:
        EnvironmentError: If critical configuration missing
    """
    # Check DuckDB path is writable
    duckdb_dir = Path(config["DUCKDB_PATH"]).parent
    if not duckdb_dir.exists():
        raise EnvironmentError(
            f"DUCKDB_PATH directory does not exist: {duckdb_dir}\n"
            f"Create it with: mkdir -p {duckdb_dir}"
        )

    # Check Bitcoin data directory exists
    bitcoin_dir = Path(config["BITCOIN_DATADIR"])
    if not bitcoin_dir.exists():
        raise EnvironmentError(
            f"BITCOIN_DATADIR does not exist: {bitcoin_dir}\n"
            f"Set BITCOIN_DATADIR env var or create .env file."
        )

    # Log config summary (with sensitive values redacted)
    logging.info(
        "Configuration validated",
        extra={
            "duckdb_path": config["DUCKDB_PATH"],
            "bitcoin_datadir": "<redacted>",
            "mempool_api": config["MEMPOOL_API_URL"],
            "confidence_threshold": config["UTXORACLE_CONFIDENCE_THRESHOLD"],
        },
    )


# =============================================================================
# Data Fetching (T039, T040)
# =============================================================================


def fetch_mempool_price(api_url: str = "http://localhost:8999") -> float:
    """
    T039: Fetch current BTC/USD price from mempool.space API.

    Args:
        api_url: Base URL for mempool.space API

    Returns:
        float: USD price

    Raises:
        requests.RequestException: On network/API errors
    """
    url = f"{api_url}/api/v1/prices"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        usd_price = data.get("USD")
        if usd_price is None:
            raise ValueError(f"USD price not found in response: {data}")

        logging.info(f"Fetched mempool.space price: ${usd_price:,.2f}")
        return float(usd_price)

    except requests.RequestException as e:
        logging.error(f"Failed to fetch mempool price: {e}")
        raise


def _fetch_from_bitcoin_core(bitcoin_datadir: str) -> List[dict]:
    """
    Tier 1: Fetch transactions from Bitcoin Core RPC (primary source).

    Args:
        bitcoin_datadir: Path to Bitcoin data directory

    Returns:
        list: Transaction dictionaries with vout/vin data

    Raises:
        ValueError: If cannot connect or fetch transactions
    """
    import subprocess

    # Read RPC credentials from bitcoin.conf
    conf_path = f"{bitcoin_datadir}/bitcoin.conf"
    rpc_user = rpc_pass = None

    try:
        with open(conf_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("rpcuser="):
                    rpc_user = line.split("=", 1)[1]
                elif line.startswith("rpcpassword="):
                    rpc_pass = line.split("=", 1)[1]
    except FileNotFoundError:
        raise ValueError(f"bitcoin.conf not found at {conf_path}")

    if not (rpc_user and rpc_pass):
        raise ValueError("rpcuser/rpcpassword not found in bitcoin.conf")

    rpc_url = "http://127.0.0.1:8332/"
    auth = f"{rpc_user}:{rpc_pass}"

    # Get best block hash
    result = subprocess.run(
        [
            "curl",
            "-s",
            "--user",
            auth,
            "--data-binary",
            '{"jsonrpc":"1.0","method":"getbestblockhash","params":[]}',
            "-H",
            "content-type: text/plain;",
            rpc_url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise ValueError(f"Bitcoin Core RPC failed: {result.stderr}")

    best_hash = json.loads(result.stdout)["result"]
    logging.info(f"[Bitcoin Core] Fetching block {best_hash[:16]}...")

    # Get block with full tx details (verbosity=2)
    result = subprocess.run(
        [
            "curl",
            "-s",
            "--user",
            auth,
            "--data-binary",
            f'{{"jsonrpc":"1.0","method":"getblock","params":["{best_hash}",2]}}',
            "-H",
            "content-type: text/plain;",
            rpc_url,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise ValueError(f"Bitcoin Core getblock failed: {result.stderr}")

    block_data = json.loads(result.stdout)["result"]
    transactions = block_data["tx"]

    if len(transactions) < 1000:
        raise ValueError(f"Block has only {len(transactions)} tx (expected >=1000)")

    logging.info(f"[Bitcoin Core] ✅ Fetched {len(transactions)} transactions")
    return transactions


def _fetch_from_mempool_local() -> List[dict]:
    """
    Tier 2: Fetch from self-hosted mempool.space (secondary source).

    Returns:
        list: Transaction dictionaries

    Raises:
        ValueError: If local mempool unavailable or data incomplete
    """
    local_url = "http://localhost:8999"

    # Get best block hash
    resp = requests.get(f"{local_url}/api/blocks/tip/hash", timeout=10)
    resp.raise_for_status()
    best_hash = resp.text.strip()

    logging.info(f"[Mempool Local] Fetching block {best_hash[:16]}...")

    # Get block info to know tx_count
    resp = requests.get(f"{local_url}/api/block/{best_hash}", timeout=10)
    resp.raise_for_status()
    block_info = resp.json()
    total_tx = block_info["tx_count"]

    # Fetch all transactions (paginated: 25 per page)
    transactions = []
    for start_index in range(0, total_tx, 25):
        resp = requests.get(
            f"{local_url}/api/block/{best_hash}/txs/{start_index}",
            timeout=30,
        )
        resp.raise_for_status()
        transactions.extend(resp.json())

    if len(transactions) < 1000:
        raise ValueError(f"Fetched only {len(transactions)} tx (expected >=1000)")

    logging.info(f"[Mempool Local] ✅ Fetched {len(transactions)} transactions")
    return transactions


def _fetch_from_mempool_public() -> List[dict]:
    """
    Tier 3: Fetch from public mempool.space API (last resort).

    Returns:
        list: Transaction dictionaries

    Raises:
        ValueError: If public API unavailable or rate limited
    """
    public_url = "https://mempool.space"

    # Get best block hash
    resp = requests.get(f"{public_url}/api/blocks/tip/hash", timeout=15)
    resp.raise_for_status()
    best_hash = resp.text.strip()

    logging.info(f"[Mempool Public] Fetching block {best_hash[:16]}...")

    # Get block info
    resp = requests.get(f"{public_url}/api/block/{best_hash}", timeout=15)
    resp.raise_for_status()
    block_info = resp.json()
    total_tx = block_info["tx_count"]

    # Fetch all transactions (paginated, with rate limit handling)
    transactions = []
    for start_index in range(0, total_tx, 25):
        try:
            resp = requests.get(
                f"{public_url}/api/block/{best_hash}/txs/{start_index}",
                timeout=30,
            )
            resp.raise_for_status()
            transactions.extend(resp.json())

            # Be nice to public API: small delay between requests
            if start_index % 100 == 0 and start_index > 0:
                import time

                time.sleep(0.5)

        except requests.exceptions.RequestException as e:
            logging.warning(
                f"[Mempool Public] Request failed at index {start_index}: {e}"
            )
            # Continue with partial data if we have enough
            if len(transactions) >= 1000:
                break
            raise

    if len(transactions) < 1000:
        raise ValueError(f"Fetched only {len(transactions)} tx (expected >=1000)")

    logging.info(f"[Mempool Public] ✅ Fetched {len(transactions)} transactions")
    return transactions


def fetch_bitcoin_transactions(bitcoin_datadir: str) -> List[dict]:
    """
    Fetch Bitcoin transactions with 3-tier fallback cascade.

    Tries sources in order:
    1. Bitcoin Core RPC (fast, complete, local)
    2. mempool.space local (self-hosted, reliable)
    3. mempool.space public API (always available, slow)

    Args:
        bitcoin_datadir: Path to Bitcoin data directory

    Returns:
        list: Transaction dictionaries with vout/vin data

    Raises:
        ValueError: If all sources fail
    """
    # Tier 1: Bitcoin Core RPC (primary)
    try:
        return _fetch_from_bitcoin_core(bitcoin_datadir)
    except Exception as e:
        logging.warning(f"[Tier 1] Bitcoin Core failed: {e}")

    # Tier 2: mempool.space local (secondary)
    try:
        return _fetch_from_mempool_local()
    except Exception as e:
        logging.warning(f"[Tier 2] Mempool local failed: {e}")

    # Tier 3: mempool.space public API (last resort)
    try:
        return _fetch_from_mempool_public()
    except Exception as e:
        logging.error(f"[Tier 3] Mempool public failed: {e}")

    # All sources failed
    raise ValueError(
        "All transaction sources unavailable. "
        "Check Bitcoin Core, local mempool, and network connectivity."
    )


def calculate_utxoracle_price(bitcoin_datadir: str) -> Dict:
    """
    T040: Calculate BTC/USD price using UTXOracle algorithm.

    Args:
        bitcoin_datadir: Path to Bitcoin data directory for RPC

    Returns:
        dict: {
            'price_usd': float or None,
            'confidence': float (0-1),
            'tx_count': int,
            'output_count': int
        }
    """
    try:
        # Fetch transactions from Bitcoin Core
        transactions = fetch_bitcoin_transactions(bitcoin_datadir)

        # Calculate price using library
        calc = UTXOracleCalculator()
        result = calc.calculate_price_for_transactions(transactions)

        # Validate result quality
        price = result.get("price_usd")
        confidence = result.get("confidence", 0)
        tx_count = result.get("tx_count", 0)

        # Sanity checks
        if price is None:
            raise ValueError("UTXOracle returned None price")

        if not (10000 <= price <= 500000):
            raise ValueError(
                f"Price ${price:,.0f} outside valid range [$10k-$500k]. "
                f"Likely calculation error or extreme market conditions."
            )

        if confidence < 0.3:
            raise ValueError(
                f"Confidence {confidence:.2f} too low (<0.3). "
                f"Result not reliable for production use."
            )

        if tx_count < 1000:
            raise ValueError(
                f"Calculated from only {tx_count} tx (<1000). "
                f"Data quality insufficient."
            )

        logging.info(
            "UTXOracle price calculated and validated",
            extra={
                "price_usd": price,
                "confidence": confidence,
                "tx_count": tx_count,
            },
        )

        return result

    except Exception as e:
        logging.error(f"Failed to calculate UTXOracle price: {e}")
        return {
            "price_usd": None,
            "confidence": 0.0,
            "tx_count": 0,
            "output_count": 0,
        }


# =============================================================================
# Price Comparison (T041)
# =============================================================================


def compare_prices(utx_price: Optional[float], mem_price: float) -> Dict:
    """
    T041: Compute difference between UTXOracle and mempool prices.

    Args:
        utx_price: UTXOracle price (can be None)
        mem_price: Mempool.space exchange price

    Returns:
        dict: {
            'diff_amount': float (USD),
            'diff_percent': float (percentage)
        }
    """
    if utx_price is None or utx_price == 0:
        return {
            "diff_amount": None,
            "diff_percent": None,
        }

    diff_amount = mem_price - utx_price
    diff_percent = (diff_amount / utx_price) * 100

    logging.info(
        "Price comparison",
        extra={
            "utx_price": utx_price,
            "mem_price": mem_price,
            "diff_amount": diff_amount,
            "diff_percent": diff_percent,
        },
    )

    return {
        "diff_amount": round(diff_amount, 2),
        "diff_percent": round(diff_percent, 3),
    }


# =============================================================================
# Price Validation (T042a)
# =============================================================================


def validate_price_data(data: Dict, config: Dict) -> bool:
    """
    T042a: Validate price data meets quality thresholds.

    Args:
        data: Price data dictionary
        config: Configuration with validation thresholds

    Returns:
        bool: True if valid, False otherwise
    """
    utx_price = data.get("utxoracle_price")
    confidence = data.get("confidence", 0.0)

    # Check confidence threshold
    min_confidence = config["UTXORACLE_CONFIDENCE_THRESHOLD"]
    if confidence < min_confidence:
        logging.warning(
            f"Low confidence: {confidence:.2f} < {min_confidence}",
            extra={
                "confidence": confidence,
                "threshold": min_confidence,
                "tx_count": data.get("tx_count"),
            },
        )
        return False

    # Check price range
    if utx_price is not None:
        min_price = config["MIN_PRICE_USD"]
        max_price = config["MAX_PRICE_USD"]

        if not (min_price <= utx_price <= max_price):
            logging.warning(
                f"Price out of range: ${utx_price:,.2f} not in [${min_price:,.0f}, ${max_price:,.0f}]",
                extra={
                    "price": utx_price,
                    "min": min_price,
                    "max": max_price,
                },
            )
            return False

    return True


# =============================================================================
# Database Operations (T042, T043)
# =============================================================================


def init_database(db_path: str) -> None:
    """
    T042: Initialize DuckDB schema if not exists.

    Args:
        db_path: Path to DuckDB file
    """
    schema = """
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
    """

    try:
        with duckdb.connect(db_path) as conn:
            conn.execute(schema)
            logging.info(f"Database initialized: {db_path}")
    except Exception as e:
        logging.error(f"Failed to initialize database: {e}")
        raise


def detect_gaps(conn, max_days_back: int = None) -> List[str]:
    """
    Detect missing dates in the entire historical series.

    Args:
        conn: DuckDB connection
        max_days_back: DEPRECATED - now scans entire history. If provided, checks from first_date to today.

    Returns:
        list: Missing dates as strings (YYYY-MM-DD)
    """
    # Find first date in database (start of historical series)
    first_date_result = conn.execute("""
        SELECT MIN(date) FROM price_analysis
    """).fetchone()

    if not first_date_result or not first_date_result[0]:
        logging.info("No data in database yet - no gaps to detect")
        return []

    first_date = first_date_result[0]

    # Generate complete date range from first_date to today
    query = """
        WITH date_range AS (
            SELECT date_seq::DATE as expected_date
            FROM generate_series(
                ?::DATE,
                CURRENT_DATE,
                INTERVAL '1 day'
            ) as t(date_seq)
        )
        SELECT dr.expected_date::VARCHAR
        FROM date_range dr
        LEFT JOIN price_analysis p ON p.date = dr.expected_date
        WHERE p.date IS NULL
        ORDER BY dr.expected_date DESC
    """

    result = conn.execute(query, [first_date]).fetchall()
    gaps = [row[0] for row in result]

    if gaps:
        logging.warning(
            f"Detected {len(gaps)} missing dates in historical series (first: {first_date})"
        )
        logging.warning(f"Gap dates: {gaps[:10]}{'...' if len(gaps) > 10 else ''}")
    else:
        logging.info(
            f"✅ No gaps detected (complete series from {first_date} to today)"
        )

    return gaps


def backfill_gap(date_str: str, config: Dict) -> bool:
    """
    Backfill a single missing date using UTXOracle.py reference implementation.

    Args:
        date_str: Date to backfill (YYYY-MM-DD format)
        config: Configuration dictionary

    Returns:
        bool: True if successful, False otherwise
    """
    import subprocess

    logging.info(f"[Backfill] Processing {date_str}...")

    try:
        # Convert YYYY-MM-DD to YYYY/MM/DD (UTXOracle.py format)
        date_utx_format = date_str.replace("-", "/")

        # Get UTXOracle.py path (parent directory)
        script_dir = Path(__file__).parent
        utxoracle_path = script_dir.parent / "UTXOracle.py"

        if not utxoracle_path.exists():
            logging.error(f"[Backfill] UTXOracle.py not found at {utxoracle_path}")
            return False

        # Run UTXOracle.py for this date (with --no-browser)
        cmd = [
            "python3",
            str(utxoracle_path),
            "-d",
            date_utx_format,
            "--no-browser",
            "-p",
            config["BITCOIN_DATADIR"],
        ]

        logging.info(f"[Backfill] Running: {' '.join(cmd)}")

        # Disable browser opening by removing DISPLAY (Linux) or setting env
        env = os.environ.copy()
        env["DISPLAY"] = ""  # Prevent X11 browser opening on Linux

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            env=env,
        )

        if result.returncode != 0:
            logging.error(f"[Backfill] UTXOracle.py failed: {result.stderr}")
            return False

        logging.info(f"[Backfill] UTXOracle.py completed for {date_str}")

        # Now run import_historical_data.py to import the new HTML to DuckDB
        import_script = script_dir / "import_historical_data.py"

        if not import_script.exists():
            logging.warning(
                "[Backfill] import_historical_data.py not found - HTML generated but not imported to DB"
            )
            return True  # Partial success

        # Run import with --limit 1 to import just this new date
        import_cmd = ["python3", str(import_script), "--limit", "1"]

        logging.info("[Backfill] Importing to DuckDB...")

        import_result = subprocess.run(
            import_cmd, capture_output=True, text=True, timeout=60
        )

        if import_result.returncode != 0:
            logging.error(f"[Backfill] Import failed: {import_result.stderr}")
            return False

        logging.info(f"[Backfill] ✅ Successfully backfilled {date_str}")
        return True

    except subprocess.TimeoutExpired:
        logging.error(f"[Backfill] Timeout while processing {date_str}")
        return False
    except Exception as e:
        logging.error(f"[Backfill] Failed to backfill {date_str}: {e}")
        return False


def save_to_duckdb(data: Dict, db_path: str, backup_path: str) -> None:
    """
    T043: Save price comparison data to DuckDB with fallback.

    Args:
        data: Price data dictionary
        db_path: Primary DuckDB path
        backup_path: Fallback path if primary fails

    Raises:
        Exception: If both primary and fallback fail
    """
    insert_sql = """
    INSERT OR REPLACE INTO price_analysis (
        date, exchange_price, utxoracle_price, price_difference,
        avg_pct_diff, confidence, tx_count, is_valid
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    values = (
        data["timestamp"].date()
        if hasattr(data["timestamp"], "date")
        else data["timestamp"],
        data["mempool_price"],
        data["utxoracle_price"],
        data["diff_amount"],
        data["diff_percent"],
        data["confidence"],
        data["tx_count"],
        data["is_valid"],
    )

    try:
        # Attempt primary write
        with duckdb.connect(db_path) as conn:
            conn.execute(insert_sql, values)
        logging.info(f"Data saved to {db_path}")

    except Exception as primary_error:
        logging.error(f"Primary DB write failed: {primary_error}")

        # Attempt fallback write
        try:
            with duckdb.connect(backup_path) as conn:
                # Ensure table exists in backup
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
                conn.execute(insert_sql, values)

            logging.critical(
                f"FALLBACK: Data saved to {backup_path}",
                extra={"backup_path": backup_path},
            )

            # Send notification about fallback
            send_alert_webhook(
                "ERROR",
                f"DuckDB primary write failed, using fallback: {backup_path}",
                {"error": str(primary_error)},
            )

        except Exception as backup_error:
            logging.critical("FATAL: Both primary and backup DB writes failed")
            logging.critical(f"Primary error: {primary_error}")
            logging.critical(f"Backup error: {backup_error}")
            raise Exception("Database write failed completely") from backup_error


# =============================================================================
# Error Handling & Notifications (T044, T044a)
# =============================================================================


def retry_with_backoff(func, max_retries: int = 3, delay: float = 2.0):
    """
    T044: Retry function with exponential backoff.

    Args:
        func: Function to retry
        max_retries: Maximum number of attempts
        delay: Initial delay in seconds

    Returns:
        Function result

    Raises:
        Exception: If all retries fail
    """
    import time

    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise

            wait_time = delay * (2**attempt)
            logging.warning(
                f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                f"Retrying in {wait_time}s..."
            )
            time.sleep(wait_time)


def send_alert_webhook(level: str, message: str, context: Dict = None) -> None:
    """
    T044a: Send alert to webhook (e.g., n8n workflow).

    Args:
        level: Alert level (ERROR, WARNING, etc.)
        message: Alert message
        context: Additional context dict
    """
    webhook_url = os.getenv("ALERT_WEBHOOK_URL")
    if not webhook_url:
        return  # Webhook not configured

    payload = {
        "level": level,
        "component": "daily_analysis",
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "context": context or {},
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=5)
        response.raise_for_status()
        logging.info(f"Alert sent to webhook: {level}")
    except Exception as e:
        logging.warning(f"Failed to send webhook alert: {e}")


# =============================================================================
# Main Execution (T038, T046)
# =============================================================================


def setup_logging(log_level: str) -> None:
    """
    T045: Setup structured logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    """
    Main execution flow for daily analysis.

    T046: Support CLI flags --init-db, --dry-run, --verbose
    """
    parser = argparse.ArgumentParser(description="UTXOracle Daily Analysis")
    parser.add_argument(
        "--init-db", action="store_true", help="Initialize database only"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Run without saving to DB"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--auto-backfill",
        action="store_true",
        help="Automatically backfill detected gaps (max 10 per run)",
    )
    parser.add_argument(
        "--backfill-limit",
        type=int,
        default=10,
        help="Maximum gaps to backfill per run (default: 10)",
    )
    args = parser.parse_args()

    # Load and validate configuration
    config = load_config()
    setup_logging(config["LOG_LEVEL"] if not args.verbose else "DEBUG")

    try:
        validate_config(config)
    except EnvironmentError as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)

    # Handle --init-db flag
    if args.init_db:
        init_database(config["DUCKDB_PATH"])
        logging.info("Database initialized successfully")
        sys.exit(0)

    # Ensure database exists and has correct schema
    init_database(config["DUCKDB_PATH"])

    # Check for gaps in entire historical series before running analysis
    try:
        with duckdb.connect(config["DUCKDB_PATH"]) as conn:
            gaps = detect_gaps(conn)  # Scans entire history
            if gaps:
                logging.warning(
                    f"⚠️  {len(gaps)} total gaps in historical series. Recent: {gaps[:5]}"
                )

                # Auto-backfill if flag enabled
                if args.auto_backfill:
                    logging.info(
                        f"🔄 Auto-backfill enabled - processing up to {args.backfill_limit} gaps..."
                    )
                    gaps_to_fill = gaps[
                        : args.backfill_limit
                    ]  # Limit to prevent overwhelming system

                    success_count = 0
                    fail_count = 0

                    for gap_date in gaps_to_fill:
                        if backfill_gap(gap_date, config):
                            success_count += 1
                        else:
                            fail_count += 1

                    logging.info(
                        f"✅ Backfill complete: {success_count} successful, {fail_count} failed"
                    )

                    # Re-check gaps after backfill
                    with duckdb.connect(config["DUCKDB_PATH"]) as conn:
                        remaining_gaps = detect_gaps(conn)
                        if remaining_gaps:
                            logging.warning(
                                f"⚠️  {len(remaining_gaps)} gaps remaining after backfill"
                            )
                        else:
                            logging.info(
                                "✅ All gaps filled - historical series now complete!"
                            )
                else:
                    logging.info(
                        "💡 Tip: Run with --auto-backfill to automatically fill gaps"
                    )
    except Exception as e:
        logging.warning(f"Gap detection failed: {e}")

    # Main analysis workflow
    try:
        logging.info("=" * 60)
        logging.info("Starting daily analysis")

        # Step 1: Fetch mempool.space price (T039)
        mempool_price = retry_with_backoff(
            lambda: fetch_mempool_price(config["MEMPOOL_API_URL"])
        )

        # Step 2: Calculate UTXOracle price (T040)
        utx_result = calculate_utxoracle_price(config["BITCOIN_DATADIR"])

        # Step 3: Compare prices (T041)
        comparison = compare_prices(utx_result["price_usd"], mempool_price)

        # Step 4: Validate data quality (T042a)
        data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "utxoracle_price": utx_result["price_usd"],
            "mempool_price": mempool_price,
            "confidence": utx_result["confidence"],
            "tx_count": utx_result["tx_count"],
            "diff_amount": comparison["diff_amount"],
            "diff_percent": comparison["diff_percent"],
            "is_valid": validate_price_data(
                {**utx_result, "utxoracle_price": utx_result["price_usd"]}, config
            ),
        }

        # Step 5: Save to database (T042, T043)
        if not args.dry_run:
            save_to_duckdb(data, config["DUCKDB_PATH"], config["DUCKDB_BACKUP_PATH"])
        else:
            logging.info("[DRY-RUN] Would save data:")
            logging.info(json.dumps(data, indent=2))

        logging.info("Daily analysis completed successfully")

    except Exception as e:
        logging.error(f"Daily analysis failed: {e}", exc_info=True)
        send_alert_webhook("ERROR", f"Daily analysis failed: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
