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

# Add parent directory and scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

# Third-party imports
import requests
import duckdb
from dotenv import load_dotenv

# Local imports
from UTXOracle_library import UTXOracleCalculator

# Whale Flow Detector (spec-004) - import after scripts/ is in path
try:
    from whale_flow_detector import WhaleFlowDetector
except ImportError:
    # Whale detection will be disabled if import fails
    WhaleFlowDetector = None

# On-Chain Metrics (spec-007) - Monte Carlo Fusion, Active Addresses, TX Volume
try:
    from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion
    from scripts.metrics.active_addresses import count_active_addresses
    from scripts.metrics.tx_volume import calculate_tx_volume
    from scripts.metrics import save_metrics_to_db

    METRICS_ENABLED = True
except ImportError:
    METRICS_ENABLED = False
    logging.warning("spec-007 metrics not available - run scripts/init_metrics_db.py")

# Advanced On-Chain Analytics (spec-009) - Power Law, Symbolic Dynamics, Fractal Dimension
try:
    from scripts.metrics.monte_carlo_fusion import enhanced_fusion
    from scripts.metrics.power_law import fit as power_law_fit
    from scripts.metrics.symbolic_dynamics import analyze as symbolic_analyze
    from scripts.metrics.fractal_dimension import analyze as fractal_analyze

    ADVANCED_METRICS_ENABLED = True
except ImportError:
    ADVANCED_METRICS_ENABLED = False
    logging.warning("spec-009 advanced metrics not available")

# Wasserstein Distance Calculator (spec-010) - Distribution Shift Detection
try:
    from scripts.metrics.wasserstein import rolling_wasserstein, wasserstein_vote

    WASSERSTEIN_ENABLED = True
except ImportError:
    WASSERSTEIN_ENABLED = False
    logging.warning(
        "spec-010 wasserstein not available - distribution shift detection disabled"
    )

# Derivatives Integration (spec-008) - Funding Rate and Open Interest from LiquidationHeatmap
try:
    from scripts.derivatives import get_liq_connection, close_connection
    from scripts.derivatives.funding_rate_reader import get_latest_funding_signal
    from scripts.derivatives.oi_reader import get_latest_oi_signal

    DERIVATIVES_ENABLED = True
except ImportError:
    DERIVATIVES_ENABLED = False
    logging.warning(
        "spec-008 derivatives not available - LiquidationHeatmap integration disabled"
    )

# Webhook Alert System (spec-011) - Signal, Price, and Whale alerts
try:
    from scripts.alerts import (
        emit_alert_sync,
        create_signal_event,
        create_price_event,
        create_whale_event,
        get_config as get_alert_config,
    )

    ALERTS_ENABLED = True
except ImportError:
    ALERTS_ENABLED = False
    logging.warning("spec-011 alerts not available - webhook alerts disabled")

# SOPR - Spent Output Profit Ratio (spec-016)
try:
    from scripts.metrics.sopr import detect_sopr_signals

    SOPR_ENABLED = True
except ImportError:
    SOPR_ENABLED = False
    logging.warning("spec-016 SOPR not available - STH/LTH analysis disabled")


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
        # Fallback configuration (T127 - Phase 9: Soluzione 3c)
        "MEMPOOL_FALLBACK_ENABLED": os.getenv(
            "MEMPOOL_FALLBACK_ENABLED", "false"
        ).lower()
        == "true",
        "MEMPOOL_FALLBACK_URL": os.getenv(
            "MEMPOOL_FALLBACK_URL", "https://mempool.space"
        ),
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


def _convert_satoshi_to_btc(transactions: List[dict]) -> List[dict]:
    """
    Convert mempool.space API format (satoshi) to UTXOracle_library format (BTC).

    mempool.space API returns vout["value"] in satoshi (e.g., 638687680),
    but UTXOracle_library.py expects BTC (e.g., 6.39).

    Args:
        transactions: List of transactions with satoshi values

    Returns:
        list: Same transactions with BTC values
    """
    for tx in transactions:
        for vout in tx.get("vout", []):
            if "value" in vout:
                # Convert satoshi → BTC (divide by 100,000,000)
                vout["value"] = vout["value"] / 1e8

    return transactions


def _fetch_from_mempool_local(api_url: str) -> List[dict]:
    """
    Tier 1 (Primary): Fetch from self-hosted electrs HTTP API.

    Note: Self-hosted mempool.space backend (port 8999) does NOT expose block transaction endpoints.
    We use electrs HTTP API directly (port 3001) instead.

    Args:
        api_url: Base URL for mempool.space API (e.g., http://localhost:8999)
                 This is used only for exchange prices. Transactions come from electrs at localhost:3001.

    Returns:
        list: Transaction dictionaries with vout values in BTC

    Raises:
        ValueError: If local electrs unavailable or data incomplete
    """
    # Use electrs HTTP API directly (localhost:3001)
    electrs_url = "http://localhost:3001"

    # Get best block hash from electrs
    resp = requests.get(f"{electrs_url}/blocks/tip/hash", timeout=10)
    resp.raise_for_status()
    best_hash = resp.text.strip().strip('"')  # electrs returns quoted string

    logging.info(
        f"[Primary API - electrs] Fetching block {best_hash[:16]}... (from {electrs_url})"
    )

    # Get transaction IDs from block
    resp = requests.get(f"{electrs_url}/block/{best_hash}/txids", timeout=30)
    resp.raise_for_status()
    txids = resp.json()

    if len(txids) < 1000:
        raise ValueError(f"Fetched only {len(txids)} tx (expected >=1000)")

    # Fetch full transaction data for each txid
    transactions = []
    logging.info(f"[Primary API - electrs] Fetching {len(txids)} full transactions...")
    for i, txid in enumerate(txids):
        if i % 500 == 0:
            logging.info(
                f"[Primary API - electrs] Progress: {i}/{len(txids)} transactions..."
            )

        resp = requests.get(f"{electrs_url}/tx/{txid}", timeout=10)
        resp.raise_for_status()
        tx = resp.json()
        transactions.append(tx)

    # CRITICAL: Convert satoshi → BTC for UTXOracle_library compatibility
    transactions = _convert_satoshi_to_btc(transactions)

    logging.info(
        f"[Primary API - electrs] ✅ Fetched {len(transactions)} transactions from {electrs_url}"
    )
    return transactions


def _fetch_from_mempool_public(api_url: str) -> List[dict]:
    """
    Tier 2 (Fallback): Fetch from public mempool.space API.

    Args:
        api_url: Base URL for fallback API (e.g., https://mempool.space)

    Returns:
        list: Transaction dictionaries

    Raises:
        ValueError: If public API unavailable or rate limited
    """
    # Get best block hash
    resp = requests.get(f"{api_url}/api/blocks/tip/hash", timeout=15)
    resp.raise_for_status()
    best_hash = resp.text.strip()

    logging.info(f"[Fallback API] Fetching block {best_hash[:16]}... (from {api_url})")

    # Get block info
    resp = requests.get(f"{api_url}/api/block/{best_hash}", timeout=15)
    resp.raise_for_status()
    block_info = resp.json()
    total_tx = block_info["tx_count"]

    # Fetch all transactions (paginated, with rate limit handling)
    transactions = []
    for start_index in range(0, total_tx, 25):
        try:
            resp = requests.get(
                f"{api_url}/api/block/{best_hash}/txs/{start_index}",
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
                f"[Fallback API] Request failed at index {start_index}: {e}"
            )
            # Continue with partial data if we have enough
            if len(transactions) >= 1000:
                break
            raise

    if len(transactions) < 1000:
        raise ValueError(f"Fetched only {len(transactions)} tx (expected >=1000)")

    # CRITICAL: Convert satoshi → BTC for UTXOracle_library compatibility
    transactions = _convert_satoshi_to_btc(transactions)

    logging.info(
        f"[Fallback API] ✅ Fetched {len(transactions)} transactions from {api_url}"
    )
    return transactions


def fetch_bitcoin_transactions(config: Dict[str, any]) -> List[dict]:
    """
    Fetch Bitcoin transactions with configurable fallback (T124-T125).

    Phase 9: Soluzione 3c - Hybrid with configurable fallback.

    Architecture:
    - Primary: Self-hosted mempool.space API (config["MEMPOOL_API_URL"])
    - Fallback: Public API (config["MEMPOOL_FALLBACK_URL"]) - opt-in only
    - Privacy-first: Fallback disabled by default

    Args:
        config: Configuration dict with MEMPOOL_API_URL, MEMPOOL_FALLBACK_*

    Returns:
        list: Transaction dictionaries with vout/vin data

    Raises:
        requests.exceptions.RequestException: If primary fails and fallback disabled
        ValueError: If both primary and fallback fail
    """
    primary_url = config["MEMPOOL_API_URL"]
    fallback_enabled = config.get("MEMPOOL_FALLBACK_ENABLED", False)
    fallback_url = config.get("MEMPOOL_FALLBACK_URL", "https://mempool.space")

    # Tier 1: Primary API (self-hosted mempool.space)
    try:
        return _fetch_from_mempool_local(primary_url)
    except requests.exceptions.RequestException as e:
        logging.warning(f"Tier 1 failed ({primary_url}): {e}")

        # Tier 2: Fallback (only if enabled)
        if fallback_enabled:
            logging.warning(f"Attempting Tier 2: Fallback API ({fallback_url})")
            try:
                return _fetch_from_mempool_public(fallback_url)
            except requests.exceptions.RequestException as e_fallback:
                logging.warning(f"Tier 2 failed ({fallback_url}): {e_fallback}")
        else:
            logging.info("Tier 2 (fallback) disabled for privacy")

        # Tier 3: Bitcoin Core RPC (ultimate fallback - always enabled)
        logging.warning("Attempting Tier 3: Bitcoin Core RPC direct")
        try:
            bitcoin_datadir = config.get(
                "BITCOIN_DATADIR", os.path.expanduser("~/.bitcoin")
            )
            return _fetch_from_bitcoin_core(bitcoin_datadir)
        except Exception as e_rpc:
            logging.error(f"Tier 3 failed (Bitcoin Core RPC): {e_rpc}")
            raise ValueError(
                f"All 3 tiers failed:\n"
                f"  Tier 1 (mempool local): {primary_url}\n"
                f"  Tier 2 (mempool public): {fallback_url if fallback_enabled else 'disabled'}\n"
                f"  Tier 3 (Bitcoin Core RPC): {bitcoin_datadir}\n"
                "Check network connectivity, mempool-stack, and Bitcoin Core status."
            )
    except Exception as e:
        # Non-network errors (ValueError, etc.) - no fallback
        logging.error(f"Primary API failed with non-network error: {e}")
        raise


def calculate_utxoracle_price(config: Dict) -> Dict:
    """
    T040: Calculate BTC/USD price using UTXOracle algorithm.

    Updated for Phase 9: Uses mempool.space API instead of Bitcoin Core RPC.

    Args:
        config: Configuration dict with MEMPOOL_API_URL and fallback settings

    Returns:
        dict: {
            'price_usd': float or None,
            'confidence': float (0-1),
            'tx_count': int,
            'output_count': int
        }
    """
    try:
        # Fetch transactions from mempool.space API (Phase 9: Soluzione 3c)
        transactions = fetch_bitcoin_transactions(config)

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


def fetch_historical_transactions(date_str: str, config: Dict) -> List[dict]:
    """
    Fetch Bitcoin transactions for a specific historical date.

    This function finds all blocks mined on the target date (00:00-23:59 UTC)
    and fetches all transactions from those blocks.

    Architecture:
    - Tier 1: Bitcoin Core RPC (primary - has full historical blockchain)
    - Tier 2: electrs (fallback - if available and faster)
    - Tier 3: Fail (no mempool.space for old historical data)

    Args:
        date_str: Target date (YYYY-MM-DD format)
        config: Configuration dict with BITCOIN_DATADIR

    Returns:
        list: Transaction dictionaries with vout/vin data

    Raises:
        ValueError: If date is invalid or no blocks found
        subprocess.CalledProcessError: If Bitcoin Core RPC fails
    """
    import subprocess
    from datetime import datetime, timezone

    # Parse target date
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except ValueError as e:
        raise ValueError(f"Invalid date format '{date_str}' (expected YYYY-MM-DD): {e}")

    # Calculate Unix timestamp range for target date
    start_timestamp = int(target_date.timestamp())  # 00:00:00 UTC
    end_timestamp = start_timestamp + 86400  # +24 hours

    logging.info(
        f"[Historical] Fetching transactions for {date_str} "
        f"(timestamps: {start_timestamp}-{end_timestamp})"
    )

    # Get Bitcoin Core RPC credentials
    bitcoin_datadir = config.get("BITCOIN_DATADIR", os.path.expanduser("~/.bitcoin"))
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

    def rpc_call(method: str, params: list) -> any:
        """Helper to make Bitcoin Core RPC calls."""
        result = subprocess.run(
            [
                "curl",
                "-s",
                "--user",
                auth,
                "--data-binary",
                json.dumps({"jsonrpc": "1.0", "method": method, "params": params}),
                "-H",
                "content-type: text/plain;",
                rpc_url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            raise ValueError(f"RPC call '{method}' failed: {result.stderr}")

        response = json.loads(result.stdout)
        if response.get("error"):
            raise ValueError(f"RPC error for '{method}': {response['error']}")

        return response["result"]

    # Step 1: Get current block height to estimate target height
    current_height = rpc_call("getblockcount", [])
    logging.info(f"[Historical] Current block height: {current_height}")

    # Step 2: Estimate target block height (144 blocks per day)
    # Calculate days between target date and now
    now = datetime.now(timezone.utc)
    days_ago = (now - target_date).days
    estimated_height = current_height - (days_ago * 144)

    logging.info(
        f"[Historical] Estimated height for {date_str}: ~{estimated_height} "
        f"({days_ago} days ago)"
    )

    # Step 3: Binary search to find first block of target date
    def get_block_timestamp(height: int) -> int:
        """Get block timestamp for given height."""
        block_hash = rpc_call("getblockhash", [height])
        block_header = rpc_call("getblockheader", [block_hash])
        return block_header["time"]

    # Binary search for first block >= start_timestamp
    search_range = 300  # Search ±300 blocks (~2 days) around estimate
    left = max(0, estimated_height - search_range)
    right = min(current_height, estimated_height + search_range)

    first_block_height = None
    while left <= right:
        mid = (left + right) // 2
        mid_timestamp = get_block_timestamp(mid)

        if mid_timestamp < start_timestamp:
            left = mid + 1
        elif mid_timestamp >= end_timestamp:
            right = mid - 1
        else:
            # Found a block within target date
            # Search backward to find first block of the day
            first_block_height = mid
            right = mid - 1

    if first_block_height is None:
        raise ValueError(
            f"No blocks found for {date_str} "
            f"(searched heights {estimated_height - search_range} to {estimated_height + search_range})"
        )

    # Step 4: Find last block of target date
    last_block_height = first_block_height
    for h in range(
        first_block_height + 1, first_block_height + 200
    ):  # Max 200 blocks per day
        try:
            ts = get_block_timestamp(h)
            if ts < end_timestamp:
                last_block_height = h
            else:
                break
        except Exception:
            break  # Reached current tip or error

    block_count = last_block_height - first_block_height + 1
    logging.info(
        f"[Historical] Found {block_count} blocks for {date_str} "
        f"(heights {first_block_height}-{last_block_height})"
    )

    # Step 5: Fetch all transactions from blocks in range
    all_transactions = []
    for height in range(first_block_height, last_block_height + 1):
        if (height - first_block_height) % 50 == 0:
            logging.info(
                f"[Historical] Fetching block {height - first_block_height + 1}/{block_count}..."
            )

        block_hash = rpc_call("getblockhash", [height])
        block_data = rpc_call(
            "getblock", [block_hash, 2]
        )  # verbosity=2 for full tx data
        transactions = block_data["tx"]
        all_transactions.extend(transactions)

    logging.info(
        f"[Historical] ✅ Fetched {len(all_transactions)} transactions from {block_count} blocks"
    )

    if len(all_transactions) < 1000:
        logging.warning(
            f"[Historical] Only {len(all_transactions)} transactions found "
            f"(expected >=1000 for normal day)"
        )

    return all_transactions


def backfill_gap(date_str: str, config: Dict) -> bool:
    """
    Backfill a single missing date using UTXOracle library directly (NO subprocess).

    NEW IMPLEMENTATION: Uses UTXOracleCalculator directly instead of calling UTXOracle.py subprocess.
    This eliminates database deadlock issues and is much faster.

    Args:
        date_str: Date to backfill (YYYY-MM-DD format)
        config: Configuration dictionary

    Returns:
        bool: True if successful, False otherwise
    """
    logging.info(f"[Backfill] Processing {date_str}...")

    try:
        # Parse date
        target_date = datetime.strptime(date_str, "%Y-%m-%d")

        # Fetch exchange price for this date (mempool.space API)
        try:
            mempool_price = fetch_mempool_price(
                config.get("MEMPOOL_API_URL", "http://localhost:8999")
            )
            logging.info(f"[Backfill] Exchange price: ${mempool_price:,.2f}")
        except Exception as e:
            logging.warning(f"[Backfill] Could not fetch exchange price: {e}")
            mempool_price = None  # Continue without exchange price

        # Fetch Bitcoin transactions for this date (HISTORICAL!)
        logging.info(f"[Backfill] Fetching historical transactions for {date_str}...")
        transactions = fetch_historical_transactions(date_str, config)

        if not transactions:
            logging.error(f"[Backfill] No transactions found for {date_str}")
            return False

        # Calculate UTXOracle price using library (NO subprocess!)
        calc = UTXOracleCalculator()
        result = calc.calculate_price_for_transactions(transactions)

        price = result.get("price_usd")
        confidence = result.get("confidence", 0)
        tx_count = result.get("tx_count", 0)

        if price is None:
            logging.error(f"[Backfill] UTXOracle returned None price for {date_str}")
            return False

        logging.info(
            f"[Backfill] UTXOracle price: ${price:,.2f} "
            f"(confidence={confidence:.2f}, tx_count={tx_count})"
        )

        # Prepare data for database
        data = {
            "timestamp": target_date,
            "mempool_price": mempool_price
            or price,  # Fallback to UTXOracle if no exchange price
            "utxoracle_price": price,
            "diff_amount": (mempool_price - price) if mempool_price else 0,
            "diff_percent": (
                ((mempool_price - price) / mempool_price * 100) if mempool_price else 0
            ),
            "confidence": confidence,
            "tx_count": tx_count,
            "is_valid": confidence >= 0.3 and tx_count >= 1000,
            "whale_net_flow": 0.0,  # No whale data for historical backfill
            "whale_direction": "NEUTRAL",
            "action": "HOLD",
            "combined_signal": 0.0,
        }

        # Save to database
        save_to_duckdb(
            data,
            config["DUCKDB_PATH"],
            config.get("DUCKDB_BACKUP_PATH", "/tmp/utxoracle_backup.duckdb"),
        )

        logging.info(f"[Backfill] ✅ Successfully backfilled {date_str}")
        return True

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
        avg_pct_diff, confidence, tx_count, is_valid,
        whale_net_flow, whale_direction, action, combined_signal
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        data.get("whale_net_flow"),
        data.get("whale_direction"),
        data.get("action"),
        data.get("combined_signal"),
    )

    try:
        # Attempt primary write
        with duckdb.connect(db_path) as conn:
            # Check existing data to prevent overwriting better quality data
            date_to_check = values[0]
            existing = conn.execute(
                "SELECT confidence, is_valid FROM price_analysis WHERE date = ?",
                [date_to_check],
            ).fetchone()

            # Only insert if: (1) no existing data OR (2) new data has better/equal confidence
            if existing:
                existing_confidence = existing[0]
                existing_is_valid = existing[1]
                new_confidence = values[5]  # confidence is 6th value (index 5)
                new_is_valid = values[7]  # is_valid is 8th value (index 7)

                # Skip if existing data is valid and new data is invalid
                if existing_is_valid and not new_is_valid:
                    logging.warning(
                        f"Skipping update for {date_to_check}: "
                        f"Existing valid data (confidence={existing_confidence:.2f}) "
                        f"not replaced with invalid data (confidence={new_confidence:.2f})"
                    )
                    return

                # Skip if existing has better confidence
                if existing_confidence > new_confidence:
                    logging.info(
                        f"Skipping update for {date_to_check}: "
                        f"Existing confidence {existing_confidence:.2f} > "
                        f"new confidence {new_confidence:.2f}"
                    )
                    return

            # Proceed with insert/update
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
                    is_valid BOOLEAN DEFAULT TRUE,
                    whale_net_flow REAL,
                    whale_direction TEXT,
                    action TEXT,
                    combined_signal REAL
                )
                """)

                # Apply same "keep best" logic to backup
                date_to_check = values[0]
                existing = conn.execute(
                    "SELECT confidence, is_valid FROM price_analysis WHERE date = ?",
                    [date_to_check],
                ).fetchone()

                if existing:
                    existing_confidence = existing[0]
                    existing_is_valid = existing[1]
                    new_confidence = values[5]
                    new_is_valid = values[7]

                    if existing_is_valid and not new_is_valid:
                        logging.warning(
                            f"[BACKUP] Skipping update for {date_to_check}: "
                            f"Existing valid data not replaced with invalid data"
                        )
                        return

                    if existing_confidence > new_confidence:
                        logging.info(
                            f"[BACKUP] Skipping update for {date_to_check}: "
                            f"Existing confidence {existing_confidence:.2f} > new {new_confidence:.2f}"
                        )
                        return

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


# ===== Signal Fusion Logic (spec-004, Phase 4: T050-T053) =====


def _calculate_whale_vote(net_flow_btc: float, direction: str) -> float:
    """
    T050: Calculate whale vote from net flow signal.

    Args:
        net_flow_btc: Net BTC flow (inflow - outflow)
        direction: Whale direction ("ACCUMULATION" | "DISTRIBUTION" | "NEUTRAL")

    Returns:
        Vote value:
        - 1.0: Bullish (ACCUMULATION = whales withdrawing from exchanges)
        - -1.0: Bearish (DISTRIBUTION = whales depositing to exchanges)
        - 0.0: Neutral (no strong signal)
    """
    if direction == "ACCUMULATION":
        return 1.0  # Bullish: whales withdrawing (likely to hold)
    elif direction == "DISTRIBUTION":
        return -1.0  # Bearish: whales depositing (likely to sell)
    else:
        return 0.0  # Neutral: no clear signal


def _calculate_utxo_vote(confidence: float) -> float:
    """
    T051: Calculate UTXOracle vote from confidence score.

    Args:
        confidence: UTXOracle confidence score (0.0 to 1.0)

    Returns:
        Vote value:
        - 1.0: High confidence (≥0.3) → trust the price calculation
        - 0.0: Low confidence (<0.3) → don't trust price, stay neutral
    """
    if confidence >= 0.3:
        return 1.0  # High confidence: trust UTXOracle price
    else:
        return 0.0  # Low confidence: don't trust price, neutral vote


def _fuse_signals(whale_vote: float, utxo_vote: float) -> float:
    """
    T052: Fuse whale and UTXOracle signals with weighted combination.

    Args:
        whale_vote: Whale vote (-1.0 to 1.0)
        utxo_vote: UTXOracle vote (0.0 or 1.0)

    Returns:
        Combined signal (-1.0 to 1.0):
        - Whale weight: 70% (leading indicator, on-chain behavior)
        - UTXOracle weight: 30% (confidence in price calculation)

    Formula:
        combined_signal = 0.7 * whale_vote + 0.3 * utxo_vote

    Examples:
        - Whale bullish (1.0) + UTXOracle confident (1.0) = 1.0 (strong BUY)
        - Whale bearish (-1.0) + UTXOracle uncertain (0.0) = -0.7 (SELL)
        - Whale neutral (0.0) + UTXOracle confident (1.0) = 0.3 (HOLD)
    """
    return 0.7 * whale_vote + 0.3 * utxo_vote


def _determine_action(combined_signal: float) -> str:
    """
    T053: Determine trading action from combined signal.

    Args:
        combined_signal: Fused signal (-1.0 to 1.0)

    Returns:
        Action string:
        - "BUY": Signal > 0.5 (strong bullish)
        - "SELL": Signal < -0.5 (strong bearish)
        - "HOLD": Signal between -0.5 and 0.5 (neutral or weak signal)

    Thresholds:
        - BUY threshold: 0.5 (requires strong bullish signal)
        - SELL threshold: -0.5 (requires strong bearish signal)
        - HOLD: Default for uncertain signals
    """
    if combined_signal > 0.5:
        return "BUY"
    elif combined_signal < -0.5:
        return "SELL"
    else:
        return "HOLD"


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
        # Detect gaps (close connection after detection)
        gaps = None
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

                # Connection is now CLOSED - safe to run backfill (uses library directly, no subprocess)
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

    # Initialize Whale Flow Detector (T042 - spec-004)
    whale_detector = None
    try:
        exchange_csv_path = Path(
            config.get(
                "EXCHANGE_ADDRESSES_CSV",
                "/media/sam/1TB/UTXOracle/data/exchange_addresses.csv",
            )
        )
        if exchange_csv_path.exists():
            whale_detector = WhaleFlowDetector(str(exchange_csv_path))
            logging.info(
                f"Whale detector initialized with {whale_detector.get_exchange_address_count()} exchange addresses"
            )
        else:
            logging.warning(
                f"Exchange addresses CSV not found at {exchange_csv_path}, whale detection disabled"
            )
    except Exception as e:
        logging.warning(
            f"Failed to initialize whale detector: {e}. Continuing without whale detection."
        )

    # Main analysis workflow
    try:
        logging.info("=" * 60)
        logging.info("Starting daily analysis")

        # Step 1: Fetch mempool.space price (T039)
        mempool_price = retry_with_backoff(
            lambda: fetch_mempool_price(config["MEMPOOL_API_URL"])
        )

        # Step 2: Calculate UTXOracle price (T040 - Phase 9: uses mempool.space API)
        utx_result = calculate_utxoracle_price(config)

        # Step 2.5: Analyze whale flow (T043 - spec-004)
        whale_signal = None
        if whale_detector:
            try:
                import asyncio

                # Run async whale detection (optimized with aiohttp)
                whale_signal = asyncio.run(whale_detector.analyze_latest_block())
                logging.info(
                    f"🐋 Whale Signal: {whale_signal.direction} "
                    f"(net flow: {whale_signal.net_flow_btc:+.2f} BTC, "
                    f"confidence: {whale_signal.confidence:.2%})"
                )
            except Exception as e:
                logging.warning(
                    f"Whale detection failed: {e}. Continuing without whale data."
                )

        # Step 2.6: Signal Fusion (T054-T057 - spec-004 Phase 4)
        action = None
        combined_signal = None

        # T056: Graceful degradation - if no whale signal, use UTXOracle only
        if whale_signal:
            # Calculate votes from each signal
            whale_vote = _calculate_whale_vote(
                net_flow_btc=whale_signal.net_flow_btc, direction=whale_signal.direction
            )
            utxo_vote = _calculate_utxo_vote(confidence=utx_result["confidence"])

            # Fuse signals (70% whale + 30% utxo)
            combined_signal = _fuse_signals(whale_vote, utxo_vote)

            # Determine action
            action = _determine_action(combined_signal)

            # T057: Log signal fusion details
            logging.info(
                f"📊 Signal Fusion: "
                f"whale_vote={whale_vote:+.1f}, "
                f"utxo_vote={utxo_vote:+.1f}, "
                f"combined={combined_signal:+.2f} → "
                f"Action: {action}"
            )
        else:
            # T056: No whale signal - UTXOracle only mode
            logging.info(
                "📊 Signal Fusion: No whale data, using UTXOracle-only mode (action=HOLD)"
            )
            action = "HOLD"  # Conservative: HOLD when missing whale data
            combined_signal = 0.0  # Neutral signal

        # Step 2.7: Spec-007 On-Chain Metrics (Monte Carlo Fusion, Active Addresses, TX Volume)
        mc_result = None
        active_addr_result = None
        tx_vol_result = None

        if METRICS_ENABLED:
            try:
                # Get transactions for metrics calculation
                transactions = utx_result.get("transactions", [])
                current_time = datetime.now()

                # Monte Carlo Signal Fusion (replaces linear fusion when whale data available)
                if whale_signal:
                    whale_vote = _calculate_whale_vote(
                        net_flow_btc=whale_signal.net_flow_btc,
                        direction=whale_signal.direction,
                    )
                    utxo_vote = _calculate_utxo_vote(
                        confidence=utx_result["confidence"]
                    )

                    mc_result = monte_carlo_fusion(
                        whale_vote=whale_vote,
                        whale_confidence=whale_signal.confidence,
                        utxo_vote=utxo_vote,
                        utxo_confidence=utx_result["confidence"],
                        n_samples=1000,
                    )

                    # Override action with Monte Carlo result
                    action = mc_result.action
                    combined_signal = mc_result.signal_mean

                    logging.info(
                        f"📈 Monte Carlo Fusion: "
                        f"signal={mc_result.signal_mean:+.3f} "
                        f"(95% CI: [{mc_result.ci_lower:+.3f}, {mc_result.ci_upper:+.3f}]), "
                        f"action={mc_result.action} "
                        f"(conf: {mc_result.action_confidence:.1%}), "
                        f"distribution: {mc_result.distribution_type}"
                    )

                # Active Addresses
                if transactions:
                    active_addr_result = count_active_addresses(
                        transactions=transactions,
                        block_height=utx_result.get("block_height", 0),
                        timestamp=current_time,
                    )
                    logging.info(
                        f"👥 Active Addresses: {active_addr_result.active_addresses_block} "
                        f"(senders: {active_addr_result.unique_senders}, "
                        f"receivers: {active_addr_result.unique_receivers})"
                    )

                # TX Volume USD
                if transactions and utx_result["price_usd"]:
                    tx_vol_result = calculate_tx_volume(
                        transactions=transactions,
                        utxoracle_price=utx_result["price_usd"],
                        confidence=utx_result["confidence"],
                        timestamp=current_time,
                    )
                    logging.info(
                        f"💰 TX Volume: {tx_vol_result.tx_volume_btc:.2f} BTC "
                        f"(${tx_vol_result.tx_volume_usd:,.0f} USD), "
                        f"{tx_vol_result.tx_count} transactions"
                    )

            except Exception as e:
                logging.warning(f"Spec-007 metrics calculation failed: {e}")

        # Step 2.8: Spec-009 Advanced On-Chain Analytics
        power_law_result = None
        symbolic_result = None
        fractal_result = None
        enhanced_fusion_result = None

        if ADVANCED_METRICS_ENABLED:
            try:
                # Extract UTXO values from transactions for distribution analysis
                utxo_values = []
                for tx in utx_result.get("transactions", []):
                    for vout in tx.get("vout", []):
                        value = vout.get("value", 0)
                        if value > 0:
                            utxo_values.append(value)

                if len(utxo_values) >= 100:
                    # US1: Power Law Regime Detection
                    power_law_result = power_law_fit(utxo_values)
                    logging.info(
                        f"📊 Power Law: τ={power_law_result.tau:.3f} "
                        f"(regime: {power_law_result.regime}, "
                        f"vote: {power_law_result.power_law_vote:+.3f})"
                    )

                    # US3: Fractal Dimension Analysis
                    fractal_result = fractal_analyze(utxo_values)
                    logging.info(
                        f"📐 Fractal Dimension: D={fractal_result.dimension:.3f} "
                        f"(structure: {fractal_result.structure}, "
                        f"vote: {fractal_result.fractal_vote:+.3f})"
                    )

                # US2: Symbolic Dynamics (requires time series - use tx volumes)
                tx_volumes = []
                for tx in utx_result.get("transactions", []):
                    total_out = sum(vout.get("value", 0) for vout in tx.get("vout", []))
                    if total_out > 0:
                        tx_volumes.append(total_out)

                if len(tx_volumes) >= 240:  # Minimum for order=5 symbolic analysis
                    symbolic_result = symbolic_analyze(tx_volumes, order=5)
                    logging.info(
                        f"🔣 Symbolic Dynamics: H={symbolic_result.permutation_entropy:.3f} "
                        f"(pattern: {symbolic_result.pattern_type}, "
                        f"vote: {symbolic_result.symbolic_vote:+.3f})"
                    )

                # Spec-010: Wasserstein Distribution Shift Detection
                wasserstein_result = None
                w_vote = None
                if WASSERSTEIN_ENABLED and len(utxo_values) >= 288:  # 2 windows of 144
                    try:
                        wasserstein_result = rolling_wasserstein(
                            values=utxo_values,  # B1 fix: series → values
                            window_size=144,  # 24h of blocks (144 blocks/day)
                            step_size=6,  # 1h steps (6 blocks/hour)
                        )
                        if wasserstein_result.is_valid:
                            w_vote = (
                                wasserstein_result.wasserstein_vote
                            )  # B2 fix: use precomputed vote
                            logging.info(
                                f"📊 Wasserstein: W={wasserstein_result.mean_distance:.4f} "
                                f"(regime: {wasserstein_result.regime_status}, "
                                f"vote: {w_vote:+.3f})"
                            )
                    except Exception as e:
                        logging.warning(f"Wasserstein calculation failed: {e}")

                # US4: Enhanced 8-Component Fusion (spec-009 + spec-010) + Derivatives (spec-008)
                if whale_signal and mc_result:
                    whale_vote = _calculate_whale_vote(
                        net_flow_btc=whale_signal.net_flow_btc,
                        direction=whale_signal.direction,
                    )
                    utxo_vote = _calculate_utxo_vote(
                        confidence=utx_result["confidence"]
                    )

                    # T033: Fetch derivatives signals from LiquidationHeatmap (spec-008)
                    funding_vote = None
                    oi_vote = None
                    if DERIVATIVES_ENABLED:
                        liq_conn = None
                        try:
                            liq_conn = get_liq_connection()
                            if liq_conn:
                                # Get funding rate signal
                                funding_signal = get_latest_funding_signal(
                                    conn=liq_conn
                                )
                                if funding_signal:
                                    funding_vote = funding_signal.funding_vote
                                    logging.info(
                                        f"📊 Funding Rate: {funding_signal.funding_rate * 100:.4f}% "
                                        f"→ vote={funding_vote:+.2f} "
                                        f"({'EXTREME' if funding_signal.is_extreme else 'normal'})"
                                    )

                                # Get OI signal (use whale direction for context)
                                oi_signal = get_latest_oi_signal(
                                    conn=liq_conn,
                                    whale_direction=whale_signal.direction,
                                )
                                if oi_signal:
                                    oi_vote = oi_signal.oi_vote
                                    logging.info(
                                        f"📈 Open Interest: {oi_signal.oi_value / 1e9:.2f}B USD "
                                        f"(1h: {oi_signal.oi_change_1h * 100:+.2f}%) "
                                        f"→ vote={oi_vote:+.2f} ({oi_signal.context})"
                                    )
                        except Exception as e:
                            logging.warning(f"Failed to fetch derivatives: {e}")
                        finally:
                            if liq_conn:
                                close_connection(liq_conn)

                    # Spec-016: SOPR signal calculation
                    sopr_vote = None
                    if SOPR_ENABLED:
                        try:
                            # Note: Full SOPR requires historical price data for creation blocks
                            # This is a simplified version using current block data only
                            # In production, would need historical BlockSOPR windows
                            sopr_signals = detect_sopr_signals(
                                window=[],  # Would need historical block SOPR windows
                                capitulation_days=3,
                                distribution_threshold=3.0,
                            )
                            if sopr_signals:
                                sopr_vote = sopr_signals["sopr_vote"]
                                # Determine signal type from flags
                                if sopr_signals["sth_capitulation"]:
                                    signal_type = "STH_CAPITULATION"
                                elif sopr_signals["lth_distribution"]:
                                    signal_type = "LTH_DISTRIBUTION"
                                elif sopr_signals["sth_breakeven_cross"]:
                                    signal_type = "BREAKEVEN_CROSS"
                                else:
                                    signal_type = "NEUTRAL"
                                if sopr_vote != 0.0:
                                    logging.info(
                                        f"📊 SOPR: {signal_type} signal "
                                        f"→ vote={sopr_vote:+.2f}"
                                    )
                        except Exception as e:
                            logging.warning(f"SOPR calculation failed: {e}")

                    enhanced_fusion_result = enhanced_fusion(
                        whale_vote=whale_vote,
                        whale_conf=whale_signal.confidence,
                        utxo_vote=utxo_vote,
                        utxo_conf=utx_result["confidence"],
                        power_law_vote=power_law_result.power_law_vote
                        if power_law_result and power_law_result.is_valid
                        else None,
                        symbolic_vote=symbolic_result.symbolic_vote
                        if symbolic_result and symbolic_result.is_valid
                        else None,
                        fractal_vote=fractal_result.fractal_vote
                        if fractal_result and fractal_result.is_valid
                        else None,
                        wasserstein_vote=w_vote,  # spec-010 distribution shift
                        funding_vote=funding_vote,  # spec-008 derivatives
                        oi_vote=oi_vote,  # spec-008 derivatives
                        sopr_vote=sopr_vote,  # spec-016 SOPR (STH/LTH)
                        n_samples=1000,
                    )

                    logging.info(
                        f"🔮 Enhanced Fusion ({enhanced_fusion_result.components_available} components): "
                        f"signal={enhanced_fusion_result.signal_mean:+.3f} "
                        f"(95% CI: [{enhanced_fusion_result.ci_lower:+.3f}, {enhanced_fusion_result.ci_upper:+.3f}]), "
                        f"action={enhanced_fusion_result.action} "
                        f"(conf: {enhanced_fusion_result.action_confidence:.1%})"
                    )

                    # Override action with enhanced fusion result if available
                    action = enhanced_fusion_result.action
                    combined_signal = enhanced_fusion_result.signal_mean

            except Exception as e:
                logging.warning(f"Spec-009 advanced metrics calculation failed: {e}")

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
            # Whale flow data (T044 - spec-004 Phase 3)
            "whale_net_flow": whale_signal.net_flow_btc if whale_signal else None,
            "whale_direction": whale_signal.direction if whale_signal else None,
            # Signal fusion data (T055 - spec-004 Phase 4)
            "action": action,
            "combined_signal": combined_signal,
        }

        # Step 5: Save to database (T042, T043)
        if not args.dry_run:
            save_to_duckdb(data, config["DUCKDB_PATH"], config["DUCKDB_BACKUP_PATH"])

            # Step 5.5: Save spec-007 + spec-010 metrics to metrics table
            if METRICS_ENABLED:
                try:
                    mc_dict = mc_result.to_dict() if mc_result else None
                    aa_dict = (
                        active_addr_result.to_dict() if active_addr_result else None
                    )
                    tv_dict = tx_vol_result.to_dict() if tx_vol_result else None

                    # Wasserstein data (spec-010)
                    ws_dict = None
                    if wasserstein_result and wasserstein_result.is_valid:
                        ws_dict = {
                            "mean_distance": wasserstein_result.mean_distance,
                            "mean_normalized_distance": wasserstein_result.mean_normalized_distance,
                            "dominant_shift_direction": wasserstein_result.dominant_shift_direction,
                            "regime_status": wasserstein_result.regime_status,
                            "wasserstein_vote": w_vote,
                            "is_valid": wasserstein_result.is_valid,
                        }

                    if save_metrics_to_db(
                        timestamp=current_time,
                        monte_carlo=mc_dict,
                        active_addresses=aa_dict,
                        tx_volume=tv_dict,
                        wasserstein=ws_dict,
                        db_path=config["DUCKDB_PATH"],
                    ):
                        logging.info("✅ Spec-007/010 metrics saved to metrics table")
                    else:
                        logging.warning("⚠️ Failed to save spec-007/010 metrics")
                except Exception as e:
                    logging.warning(f"Spec-007/010 metrics save failed: {e}")

            # Step 5.6: Emit webhook alerts (spec-011)
            if ALERTS_ENABLED:
                try:
                    alert_config = get_alert_config()

                    # Signal alert (if action is BUY/SELL with sufficient confidence)
                    if alert_config.signal_enabled and action in ("BUY", "SELL"):
                        confidence = (
                            enhanced_fusion_result.action_confidence
                            if enhanced_fusion_result
                            else 0.5
                        )
                        if confidence >= alert_config.signal_min_confidence:
                            signal_event = create_signal_event(
                                action=action,
                                confidence=confidence,
                                signal_mean=combined_signal,
                                top_contributors=[
                                    {
                                        "name": "whale",
                                        "value": whale_vote if whale_vote else 0,
                                    },
                                    {
                                        "name": "utxo",
                                        "value": utxo_vote if utxo_vote else 0,
                                    },
                                ],
                            )
                            if signal_event:
                                emit_alert_sync(signal_event)
                                logging.info(
                                    f"📢 Signal alert emitted: {action} (conf: {confidence:.1%})"
                                )

                    # Price divergence alert
                    if alert_config.price_enabled:
                        divergence = abs(comparison["diff_percent"])
                        if divergence >= alert_config.price_min_divergence:
                            price_event = create_price_event(
                                utxoracle_price=utx_result["price_usd"],
                                exchange_price=mempool_price,
                                divergence_pct=comparison["diff_percent"],
                            )
                            emit_alert_sync(price_event)
                            logging.info(
                                f"📢 Price divergence alert emitted: {divergence:.2f}%"
                            )

                    # Whale alert (if whale signal available)
                    if (
                        alert_config.whale_enabled
                        and whale_signal
                        and whale_signal.net_flow_btc
                    ):
                        net_flow = abs(whale_signal.net_flow_btc)
                        if net_flow >= alert_config.whale_min_btc:
                            whale_event = create_whale_event(
                                amount_btc=net_flow,
                                direction="INFLOW"
                                if whale_signal.net_flow_btc > 0
                                else "OUTFLOW",
                                signal_vote=whale_vote if whale_vote else 0,
                            )
                            emit_alert_sync(whale_event)
                            logging.info(
                                f"📢 Whale alert emitted: {net_flow:.2f} BTC {whale_signal.direction}"
                            )

                except Exception as e:
                    logging.warning(f"Spec-011 alert emission failed: {e}")
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
