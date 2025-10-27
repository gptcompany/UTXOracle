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


def fetch_bitcoin_transactions(bitcoin_datadir: str) -> List[dict]:
    """
    Fetch recent transactions from Bitcoin Core RPC.

    Uses cookie authentication from Bitcoin data directory.

    Args:
        bitcoin_datadir: Path to Bitcoin data directory

    Returns:
        list: Transaction dictionaries with vout/vin data
    """
    # This is a simplified stub - in production would use bitcoin-rpc library
    # For now, return mock data that matches the library's expected format

    # TODO: Implement actual Bitcoin Core RPC connection
    # from bitcoin.rpc import RawProxy
    # rpc = RawProxy(btc_conf_file=f"{bitcoin_datadir}/bitcoin.conf")
    # blocks = rpc.getbestblockhash()
    # block_data = rpc.getblock(blocks, 2)  # verbosity=2 includes tx details
    # return block_data['tx']

    logging.warning("Using mock Bitcoin RPC - implement actual RPC connection")

    # Return mock transactions for testing
    return [
        {"vout": [{"value": 0.001}], "vin": [{}]},
        {"vout": [{"value": 0.0009}], "vin": [{}]},
        {"vout": [{"value": 0.0011}], "vin": [{}]},
    ]


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

        logging.info(
            "UTXOracle price calculated",
            extra={
                "price_usd": result.get("price_usd"),
                "confidence": result.get("confidence"),
                "tx_count": result.get("tx_count"),
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
    CREATE TABLE IF NOT EXISTS prices (
        timestamp TIMESTAMP PRIMARY KEY,
        utxoracle_price DECIMAL(12, 2),
        mempool_price DECIMAL(12, 2),
        confidence DECIMAL(5, 4),
        tx_count INTEGER,
        diff_amount DECIMAL(12, 2),
        diff_percent DECIMAL(6, 2),
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
    INSERT INTO prices (
        timestamp, utxoracle_price, mempool_price, confidence,
        tx_count, diff_amount, diff_percent, is_valid
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    values = (
        data["timestamp"],
        data["utxoracle_price"],
        data["mempool_price"],
        data["confidence"],
        data["tx_count"],
        data["diff_amount"],
        data["diff_percent"],
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
                CREATE TABLE IF NOT EXISTS prices (
                    timestamp TIMESTAMP PRIMARY KEY,
                    utxoracle_price DECIMAL(12, 2),
                    mempool_price DECIMAL(12, 2),
                    confidence DECIMAL(5, 4),
                    tx_count INTEGER,
                    diff_amount DECIMAL(12, 2),
                    diff_percent DECIMAL(6, 2),
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
