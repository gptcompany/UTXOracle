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
import itertools
import json
import argparse
import logging

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
from pathlib import Path

# --- Startup guards -----------------------------------------------------------------------
# They run BEFORE the imports below: api.questdb_repository converts QUESTDB_* with int() at
# import time, so a bad value there ended in a traceback that printed the value. Here every
# problem is reported by variable NAME only and the process exits with a dedicated code.
# Exit codes of the script: 0 done (or both rows of the day already present); 1 invalid
# configuration; 2 any failure (exception, incomplete row, failed metrics block, failed
# write); 3 QuestDB destination mismatch or a .env defining it; 4 table without dedup on ts;
# 5 run outside its window; 6 non-numeric value in an integer variable read at import
# (QUESTDB_*) or for the day selection (MIN_CONFIRMATIONS, which must also be >= 1);
# 7 the day to analyse is not complete yet (IncompleteWindowError, nothing written).
FORBIDDEN_ENV_PREFIXES = ("UTXORACLE_EXPECTED_", "QUESTDB_")
NUMERIC_QUESTDB_ENV = (  # int() at import in api/questdb_repository.py (test-checked), + below
    "QUESTDB_ILP_PORT",
    "QUESTDB_PG_PORT",
    "QUESTDB_HTTP_PORT",
    "QUESTDB_POOL_MIN_SIZE",
    "QUESTDB_POOL_MAX_SIZE",
    "QUESTDB_COMMAND_TIMEOUT",
    "QUESTDB_MAX_INACTIVE_LIFETIME",
    "MIN_CONFIRMATIONS",  # read by select_day_blocks (_min_confirmations adds the >= 1 rule)
)
EXIT_BAD_ENV_VALUE = 6


def env_file_path() -> Path:
    """The .env that load_config()/load_secrets() read (the unit's EnvironmentFile= is the
    same file when WorkingDirectory is the repository). UTXORACLE_ENV_FILE overrides the
    path (tests); the unit does not set it."""
    override = os.environ.get("UTXORACLE_ENV_FILE")
    return Path(override) if override else Path(__file__).parent.parent / ".env"


def check_env_file_guard(log=logging) -> None:
    """Exit 3 if the .env defines the QuestDB destination or its expectation.

    The destination belongs to the systemd unit (Environment=); a .env that redefines it
    would override the unit (EnvironmentFile= wins over Environment=) or load_secrets()
    would. The file is read with a real parser (dotenv_values) and only the NAMES of the
    offending keys are logged, never a value. A missing file is not an error. `log` is the
    logging module or a logger; at startup it is a private one, so the root logger is left
    unconfigured for setup_logging().
    """
    from dotenv import dotenv_values

    path = env_file_path()
    if not path.exists():
        log.info(".env not found at %s: nothing to check", path)
        return
    offending = sorted(
        key for key in dotenv_values(path) if key.startswith(FORBIDDEN_ENV_PREFIXES)
    )
    if offending:
        log.error(
            "%s defines keys reserved to the systemd unit: %s (exit 3)",
            path,
            ", ".join(offending),
        )
        sys.exit(3)
    log.info(".env checked: no %s keys", " / ".join(FORBIDDEN_ENV_PREFIXES))


def check_numeric_env(log=logging) -> None:
    """Exit 6 if a QUESTDB_* variable that is converted with int() at import is not an int.

    Only the variable NAMES are logged, never the value.
    """
    bad = []
    for name in NUMERIC_QUESTDB_ENV:
        value = os.environ.get(name)
        if value is None:
            continue
        try:
            int(value)
        except ValueError:
            bad.append(name)
    if bad:
        log.error(
            "non-numeric value in: %s (values are never logged; exit %d)",
            ", ".join(bad),
            EXIT_BAD_ENV_VALUE,
        )
        sys.exit(EXIT_BAD_ENV_VALUE)


def _startup_logger() -> logging.Logger:
    logger = logging.getLogger("daily_analysis.startup")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger


if __name__ == "__main__":
    _startup = _startup_logger()
    check_env_file_guard(_startup)
    check_numeric_env(_startup)


# Add parent directory and scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

# Third-party imports
import requests  # noqa: E402 - after the startup guards

# Use SOPS-encrypted secrets
sys.path.insert(0, "/media/sam/1TB/claude-hooks-shared/scripts")
from secrets_loader import load_secrets  # noqa: E402 - after the startup guards

# Local imports
from UTXOracle_library import UTXOracleCalculator  # noqa: E402 - after the startup guards
from scripts.config import UTXORACLE_DB_PATH  # noqa: E402 - after the startup guards
from scripts.utils.rpc_cookie import RpcClient, clean_env_value, resolve_target  # noqa: E402 - after the startup guards
from api.questdb_repository import QuestDBRepository  # noqa: E402

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

# Advanced On-Chain Analytics (spec-009 + spec-019) - Power Law, Symbolic Dynamics, Fractal Dimension
try:
    from scripts.metrics.monte_carlo_fusion import (  # noqa: F401 - availability probe
        enhanced_fusion,
        sopr_to_vote,
        ENHANCED_WEIGHTS,
    )
    from scripts.metrics.power_law import fit as power_law_fit
    from scripts.metrics.symbolic_dynamics import analyze as symbolic_analyze
    from scripts.metrics.fractal_dimension import analyze as fractal_analyze

    ADVANCED_METRICS_ENABLED = True
    # Log weights being used (spec-019: derivatives reduced, SOPR added)
    _derivatives_pct = (ENHANCED_WEIGHTS["funding"] + ENHANCED_WEIGHTS["oi"]) * 100
    logging.info(
        f"spec-019: Fusion weights active (derivatives={_derivatives_pct:.0f}%, sopr={ENHANCED_WEIGHTS['sopr'] * 100:.0f}%)"
    )
except ImportError:
    ADVANCED_METRICS_ENABLED = False
    logging.warning("spec-009 advanced metrics not available")

# Wasserstein Distance Calculator (spec-010) - Distribution Shift Detection
try:
    from scripts.metrics.wasserstein import rolling_wasserstein

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
    from scripts.alerts import (  # noqa: F401 - availability probe
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

# UTXO Lifecycle Engine (spec-017) - Realized Cap, MVRV, NUPL, HODL Waves
try:
    from scripts.metrics.utxo_lifecycle import (  # noqa: F401 - availability probe
        init_schema as init_utxo_schema,
        init_indexes as init_utxo_indexes,
        get_sync_state as get_utxo_sync_state,
        get_sth_lth_supply,
    )
    from scripts.metrics.realized_metrics import (  # noqa: F401 - availability probe
        calculate_realized_cap,
        calculate_market_cap,
        calculate_mvrv,
        calculate_nupl,
        get_total_unspent_supply,
        create_snapshot,
    )
    from scripts.metrics.hodl_waves import calculate_hodl_waves  # noqa: F401 - availability probe
    from scripts.models.metrics_models import AgeCohortsConfig  # noqa: F401 - availability probe

    UTXO_LIFECYCLE_ENABLED = (
        os.getenv("UTXO_LIFECYCLE_ENABLED", "true").lower() == "true"
    )
except ImportError as e:
    UTXO_LIFECYCLE_ENABLED = False
    logging.warning(f"spec-017 UTXO lifecycle not available: {e}")


# =============================================================================
# Configuration Management (T038)
# =============================================================================


def _get_env_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None or val.startswith("ENC["):
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _get_env_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None or val.startswith("ENC["):
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _get_env_str(key: str, default: str) -> str:
    val = os.getenv(key)
    if val is None or val.startswith("ENC["):
        return default
    return val


def load_config() -> Dict[str, str]:
    """
    Load configuration from .env file or environment variables.

    Priority: Environment variables > .env file > defaults

    Returns:
        dict: Configuration dictionary
    """
    # Load .env file if exists (override=True to prioritize .env over existing env vars)
    env_path = env_file_path()
    if env_path.exists():
        load_secrets()
        logging.info(f"Config loaded from .env file at {env_path} (override=True)")
    else:
        logging.info("Config loaded from environment variables (no .env file found)")

    config = {
        # Required settings (fail fast if missing - T064a)
        "DUCKDB_PATH": _get_env_str("DUCKDB_PATH", str(UTXORACLE_DB_PATH)),
        # None: scripts.utils.rpc_cookie.resolve_target picks the datadir.
        "BITCOIN_DATADIR": clean_env_value(os.getenv("BITCOIN_DATADIR")),
        "MEMPOOL_API_URL": _get_env_str("MEMPOOL_API_URL", "http://localhost:8999"),
        # Optional settings with defaults
        "LOG_LEVEL": _get_env_str("LOG_LEVEL", "INFO"),
        "ANALYSIS_INTERVAL_MINUTES": _get_env_int("ANALYSIS_INTERVAL_MINUTES", 10),
        "DUCKDB_BACKUP_PATH": _get_env_str(
            "DUCKDB_BACKUP_PATH", "/tmp/utxoracle_backup.duckdb"
        ),
        "ALERT_WEBHOOK_URL": _get_env_str("ALERT_WEBHOOK_URL", ""),  # Empty if not set
        # Validation thresholds (T042a)
        "UTXORACLE_CONFIDENCE_THRESHOLD": _get_env_float(
            "UTXORACLE_CONFIDENCE_THRESHOLD", 0.3
        ),
        "MIN_PRICE_USD": _get_env_float("MIN_PRICE_USD", 10000.0),
        "MAX_PRICE_USD": _get_env_float("MAX_PRICE_USD", 500000.0),
        "MAX_PRICE_DIVERGENCE_PERCENT": _get_env_float(
            "MAX_PRICE_DIVERGENCE_PERCENT", 5.0
        ),
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
    bitcoin_dir = resolve_target(config["BITCOIN_DATADIR"]).datadir
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


def fetch_mempool_price_at(
    timestamp: int, api_url: str = "http://localhost:8999"
) -> float:
    """Reference BTC/USD price at `timestamp` (unix seconds) from mempool.space.

    Reuses the bootstrap fetcher of /api/v1/historical-price. The endpoint answers with the
    price nearest to the timestamp, not the average of a day: diff_* in price_analysis
    compares two estimates of the same day, with this one taken at the end of the window.

    Raises:
        ValueError: if the API has no price for the timestamp.
    """
    import asyncio

    from scripts.bootstrap.build_price_table import fetch_historical_price

    price = asyncio.run(fetch_historical_price(timestamp, mempool_url=api_url))
    if price is None:
        raise ValueError(f"no historical price at {timestamp} from {api_url}")
    logging.info(f"Fetched mempool.space price at {timestamp}: ${price:,.2f}")
    return price


def rpc_client(config: Optional[Dict] = None, timeout: float = 60) -> RpcClient:
    """The daily job's Bitcoin Core client, built only here.

    Cookie auth (re-read on HTTP 401); rpcuser/rpcpassword only as fallback. Without
    a config it loads the job configuration as ``main`` does. Connection settings
    come from scripts.utils.rpc_cookie.resolve_target.
    """
    config = load_config() if config is None else config
    return RpcClient(
        config.get("BITCOIN_DATADIR"), timeout=timeout, request_id="utxoracle-daily"
    )


def _fetch_from_bitcoin_core(bitcoin_datadir: str | None) -> List[dict]:
    """
    Tier 1: Fetch transactions from Bitcoin Core RPC (primary source).

    Args:
        bitcoin_datadir: Path to Bitcoin data directory

    Returns:
        list: Transaction dictionaries with vout/vin data

    Raises:
        ValueError: If cannot connect or fetch transactions
    """
    rpc = rpc_client({"BITCOIN_DATADIR": bitcoin_datadir}, timeout=120)
    best_hash = rpc.call("getbestblockhash")
    logging.info(f"[Bitcoin Core] Fetching block {best_hash[:16]}...")

    # Get block with full tx details (verbosity=2)
    block_data = rpc.call("getblock", [best_hash, 2])
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
    We use electrs HTTP API directly (port 3002) instead.

    Args:
        api_url: Base URL for mempool.space API (e.g., http://localhost:8999)
                 This is used only for exchange prices. Transactions come from electrs at localhost:3002.

    Returns:
        list: Transaction dictionaries with vout values in BTC

    Raises:
        ValueError: If local electrs unavailable or data incomplete
    """
    # Use electrs HTTP API directly (localhost:3002)
    electrs_url = "http://localhost:3002"

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


def fetch_bitcoin_transactions(config: Dict[str, any]) -> tuple[List[dict], int]:
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
        tuple: (list of transaction dicts, tier used as int)

    Raises:
        requests.exceptions.RequestException: If primary fails and fallback disabled
        ValueError: If both primary and fallback fail
    """
    primary_url = config["MEMPOOL_API_URL"]
    fallback_enabled = config.get("MEMPOOL_FALLBACK_ENABLED", False)
    fallback_url = config.get("MEMPOOL_FALLBACK_URL", "https://mempool.space")

    # Tier 1: Primary API (self-hosted mempool.space)
    try:
        return _fetch_from_mempool_local(primary_url), 1
    except requests.exceptions.RequestException as e:
        logging.warning(f"Tier 1 failed ({primary_url}): {e}")

        # Tier 2: Fallback (only if enabled)
        if fallback_enabled:
            logging.warning(f"Attempting Tier 2: Fallback API ({fallback_url})")
            try:
                return _fetch_from_mempool_public(fallback_url), 2
            except requests.exceptions.RequestException as e_fallback:
                logging.warning(f"Tier 2 failed ({fallback_url}): {e_fallback}")
        else:
            logging.info("Tier 2 (fallback) disabled for privacy")

        # Tier 3: Bitcoin Core RPC (ultimate fallback - always enabled)
        logging.warning("Attempting Tier 3: Bitcoin Core RPC direct")
        try:
            bitcoin_datadir = config.get("BITCOIN_DATADIR")
            return _fetch_from_bitcoin_core(bitcoin_datadir), 3
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


def calculate_utxoracle_price(config: Dict, day: Optional[datetime] = None) -> Dict:
    """
    T040: Calculate BTC/USD price using UTXOracle algorithm.

    Updated for Phase 9: Uses mempool.space API instead of Bitcoin Core RPC.

    Args:
        config: Configuration dict with MEMPOOL_API_URL and fallback settings
        day: analysed UTC day at 00:00Z. With it the transactions are those of the blocks
            mined in [day, day + 1 day) (Bitcoin Core RPC, tier 3); without it, the latest
            block through the three fetch tiers.

    Returns:
        dict: {
            'price_usd': float or None,
            'confidence': float (0-1),
            'tx_count': int,
            'output_count': int,
            'fetch_tier': int
        }
    """
    try:
        if day is None:
            # Fetch transactions from mempool.space API (Phase 9: Soluzione 3c)
            transactions, tier = fetch_bitcoin_transactions(config)
        else:
            # A stream, consumed once by the library. Its first transaction is looked at
            # (not consumed) so that the metrics' format guard can tell the source format.
            stream = iter(
                fetch_historical_transactions(day.strftime("%Y-%m-%d"), config)
            )
            format_sample = next(stream, None)
            transactions = (
                itertools.chain([format_sample], stream)
                if format_sample is not None
                else iter(())
            )
            tier = FETCH_TIER_RPC_HISTORICAL

        # Calculate price using library
        calc = UTXOracleCalculator()
        result = calc.calculate_price_for_transactions(transactions)

        # Add tier to result
        result["fetch_tier"] = tier
        # The spec-007 metrics (active addresses, tx volume) are computed from these.
        # A day is a stream already consumed: its metrics need the same pass (F-432), so no
        # list is handed on; the format sample lets the guard report what the source lacks.
        result["transactions"] = transactions if day is None else []
        if day is not None:
            result["format_sample"] = format_sample

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

    except IncompleteWindowError:
        raise  # the window of the day is open: main() ends with exit 7, nothing is written
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

    # Check price divergence (T103)
    diff_percent = data.get("diff_percent")
    max_divergence = config["MAX_PRICE_DIVERGENCE_PERCENT"]
    if diff_percent is not None and abs(diff_percent) > max_divergence:
        logging.warning(
            f"Large price divergence detected: {diff_percent:.2f}% > {max_divergence}%",
            extra={
                "diff_percent": diff_percent,
                "max_divergence": max_divergence,
                "utx_price": utx_price,
                "mem_price": data.get("mempool_price"),
            },
        )
        # We don't return False here because the data is technically "valid"
        # but the warning fulfills T103 "logged prominently".

    return True


# =============================================================================
# Database Operations (T042, T043)
# =============================================================================


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


# Tier recorded in price_analysis.fetch_tier for blocks of a past day read through Bitcoin Core
# RPC (tiers 1-3 are the live fetchers of the latest block).
FETCH_TIER_RPC_HISTORICAL = 4
# Plausibility only: a day has ~144 blocks on average. More than this is an error, not a cap.
MAX_BLOCKS_PER_DAY = 400
# Exit code of main() when the window of the requested day is not complete yet.
EXIT_INCOMPLETE_WINDOW = 7
# The last block of the day needs this many confirmations (env MIN_CONFIRMATIONS overrides).
DEFAULT_MIN_CONFIRMATIONS = 6


class IncompleteWindowError(Exception):
    """The chain tip is not past the end of the requested day (mediantime < D+1 00:00Z)."""


class BadEnvValueError(ValueError):
    """An environment variable has an invalid value; the message names the variable only."""


class StaleBlockError(RuntimeError):
    """A block selected for the day is no longer in the best chain (confirmations == -1)."""


class ImplausibleDayError(Exception):
    """The blocks found for the day are zero or more than MAX_BLOCKS_PER_DAY."""


def _median_time(rpc, height: int) -> int:
    """BIP113 median-time-past of the block at `height`: non-decreasing with the height."""
    return rpc.call("getblockheader", [rpc.call("getblockhash", [height])])[
        "mediantime"
    ]


def _first_height_with_mediantime_at_least(rpc, tip: int, timestamp: int) -> int:
    """Exact binary search on [0, tip + 1): the lowest height whose mediantime >= timestamp."""
    low, high = 0, tip + 1
    while low < high:
        mid = (low + high) // 2
        if _median_time(rpc, mid) >= timestamp:
            high = mid
        else:
            low = mid + 1
    return low


def _min_confirmations() -> int:
    """MIN_CONFIRMATIONS from the environment: an integer >= 1, default 6.

    Anything else (not an integer, 0, negative) raises BadEnvValueError (main: exit 6) naming
    only the variable, never the value.
    """
    raw = os.environ.get("MIN_CONFIRMATIONS")
    if not raw:
        return DEFAULT_MIN_CONFIRMATIONS
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        raise BadEnvValueError(
            "MIN_CONFIRMATIONS must be an integer >= 1 (value not logged)"
        ) from None
    return value


def select_day_blocks(rpc, date_str: str) -> tuple[int, list[str]]:
    """(first height, block hashes) of the UTC day `date_str`, fixed once, by mediantime.

    Convention: day D = the blocks whose MEDIAN-TIME-PAST is in [D 00:00:00Z, D+1 00:00:00Z),
    which lags the header `time` by about an hour; the gap from the reference price is
    measured by F-438 over several days. The mediantime never decreases with the height
    (BIP113), so the boundaries come from an exact binary search over [0, tip], with no
    estimate of the height and no margin.

    Raises:
        ValueError: invalid date. BadEnvValueError: MIN_CONFIRMATIONS is not an integer >= 1.
        IncompleteWindowError: the tip's mediantime is before D+1 00:00Z (day still open),
            or the last block of D has fewer than MIN_CONFIRMATIONS confirmations.
        ImplausibleDayError: zero blocks, or more than MAX_BLOCKS_PER_DAY.
        Any RPC error is propagated unchanged: nothing is swallowed.
    """
    try:
        start = int(
            datetime.strptime(date_str, "%Y-%m-%d")
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
    except ValueError as e:
        raise ValueError(f"Invalid date format '{date_str}' (expected YYYY-MM-DD): {e}")
    end = start + 86400
    min_confirmations = _min_confirmations()

    tip = rpc.call("getblockcount", [])
    tip_mediantime = _median_time(rpc, tip)
    if tip_mediantime < end:
        raise IncompleteWindowError(
            f"{date_str} is not complete: tip {tip} has mediantime {tip_mediantime} < {end}"
        )

    first = _first_height_with_mediantime_at_least(rpc, tip, start)
    stop = _first_height_with_mediantime_at_least(rpc, tip, end)
    count = stop - first
    if count < 1 or count > MAX_BLOCKS_PER_DAY:
        raise ImplausibleDayError(
            f"{count} blocks with mediantime in {date_str} (expected 1..{MAX_BLOCKS_PER_DAY})"
        )
    hashes = [rpc.call("getblockhash", [height]) for height in range(first, stop)]
    confirmations = rpc.call("getblockheader", [hashes[-1]])["confirmations"]
    if confirmations < 0:  # first: a block that left the best chain is not "too recent"
        raise StaleBlockError(
            f"last block {hashes[-1]} of {date_str} has confirmations {confirmations}: "
            "it left the best chain after the selection"
        )
    if confirmations < min_confirmations:
        raise IncompleteWindowError(
            f"last block of {date_str} has {confirmations} confirmations "
            f"(< {min_confirmations}): too close to the tip to be final"
        )
    logging.info(f"[Historical] {date_str}: {count} blocks, heights {first}-{stop - 1}")
    return first, hashes


def _stream_transactions(rpc, hashes: list[str]):
    """Yield the transactions of the blocks `hashes`, one block in memory at a time.

    Blocks are read BY HASH, the ones fixed at selection: a block that left the best chain
    meanwhile (confirmations == -1) is an explicit error, never silently replaced by the
    block now at that height.
    """
    total = 0
    for index, block_hash in enumerate(hashes):
        if index % 50 == 0:
            logging.info(f"[Historical] Fetching block {index + 1}/{len(hashes)}...")
        block = rpc.call("getblock", [block_hash, 2])
        if block.get("confirmations", 0) < 0:
            raise StaleBlockError(
                f"block {block_hash} has confirmations {block['confirmations']}: "
                "it left the best chain while the day was being read"
            )
        total += len(block["tx"])
        yield from block["tx"]
    logging.info(
        f"[Historical] Streamed {total} transactions from {len(hashes)} blocks"
    )


def fetch_historical_transactions(date_str: str, config: Dict):
    """
    Transactions of the blocks that belong to the UTC day `date_str`, as a stream.

    The selection (select_day_blocks, mediantime, exact) runs at call time, so its errors
    are raised here, not during iteration; the returned generator then fetches one block at
    a time by hash (getblock verbosity 2, values in BTC) and keeps none of them: the day is
    never held in memory. Callers that need the transactions twice (price library AND
    metrics) must compute both in the same pass.

    Raises: what select_day_blocks raises; StaleBlockError during iteration.
    """
    rpc = rpc_client(config)
    _, hashes = select_day_blocks(rpc, date_str)
    return _stream_transactions(rpc, hashes)


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
        transactions = fetch_historical_transactions(date_str, config)  # a stream

        # Calculate UTXOracle price using library (NO subprocess!)
        calc = UTXOracleCalculator()
        result = calc.calculate_price_for_transactions(transactions)

        price = result.get("price_usd")
        confidence = result.get("confidence", 0)
        tx_count = result.get("tx_count", 0)

        if not tx_count:
            logging.error(f"[Backfill] No transactions found for {date_str}")
            return False
        if price is None:
            logging.error(f"[Backfill] UTXOracle returned None price for {date_str}")
            return False

        logging.info(
            f"[Backfill] UTXOracle price: ${price:,.2f} "
            f"(confidence={confidence:.2f}, tx_count={tx_count})"
        )

        # Prepare data for database
        data = {
            "timestamp": target_date.isoformat(),
            "mempool_price": mempool_price
            or price,  # Fallback to UTXOracle if no exchange price
            "utxoracle_price": price,
            "diff_amount": (mempool_price - price) if mempool_price else 0,
            "diff_percent": (
                ((mempool_price - price) / mempool_price * 100) if mempool_price else 0
            ),
            "confidence": confidence,
            "tx_count": tx_count,
            "fetch_tier": FETCH_TIER_RPC_HISTORICAL,
            "is_valid": confidence >= 0.3 and tx_count >= 1000,
            "whale_net_flow": 0.0,  # No whale data for historical backfill
            "whale_direction": "NEUTRAL",
            "action": "HOLD",
            "combined_signal": 0.0,
        }

        # Save to database
        save_to_questdb(data)

        logging.info(f"[Backfill] ✅ Successfully backfilled {date_str}")
        return True

    except IncompleteWindowError:
        raise  # the day is not over: not a backfill failure, the caller must know (exit 7)
    except Exception as e:
        logging.error(f"[Backfill] Failed to backfill {date_str}: {e}")
        return False


def save_to_questdb(data: Dict) -> None:
    """
    Save price comparison data to QuestDB.

    The row key is data["timestamp"]: for the daily run it is the analysed day, the UTC day
    before the run, at 00:00Z (see analysis_day_for); a write with the same key replaces the
    row (DEDUP UPSERT KEYS(ts)).

    Args:
        data: Price data dictionary

    Raises:
        RuntimeError: if the ILP write or its flush failed (_send_row answers False).
    """
    try:
        repo = QuestDBRepository()
        sent = repo._send_row(
            "price_analysis",
            symbols={},
            columns={
                "exchange_price": data["mempool_price"],
                "utxoracle_price": data["utxoracle_price"],
                "price_difference": data["diff_amount"],
                "avg_pct_diff": data["diff_percent"],
                "confidence": data["confidence"],
                "tx_count": data["tx_count"],
                "fetch_tier": data.get("fetch_tier"),
                "is_valid": data["is_valid"],
                # Absent for backfill_gap (F-441): the column is simply not written.
                "window_end_ts": data.get("window_end_ts"),
                "created_at": datetime.now(),
            },
            at=datetime.fromisoformat(data["timestamp"]),
            flush=True,
        )
        if sent is not True:
            raise RuntimeError(
                "QuestDB refused the price_analysis row (see ILP error above)"
            )
        logging.info("Data saved to QuestDB")
    except Exception as e:
        logging.error(f"Failed to save data to QuestDB: {e}")
        # In a real application, you'd want more robust error handling,
        # maybe a retry mechanism or a dead-letter queue.
        send_alert_webhook(
            "ERROR",
            "Failed to save data to QuestDB",
            {"error": str(e)},
        )
        raise


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


def check_questdb_destination() -> None:
    """Fail before any write when the QuestDB in use is not the one the unit expects (F-419).

    The effective target is what the repository module holds, which is what every writer
    uses; it is read here, after load_config()/load_secrets() (override=True), so an
    override from .env cannot silently move the writes. The expectation comes from
    UTXORACLE_EXPECTED_QUESTDB_{ILP,PG}_{HOST,PORT}, declared in the systemd unit. Without
    any of them (manual run, tests) the target is only logged.
    """
    import api.questdb_repository as questdb

    effective = {
        "ILP_HOST": str(questdb.QUESTDB_ILP_HOST),
        "ILP_PORT": str(questdb.QUESTDB_ILP_PORT),
        "PG_HOST": str(questdb.QUESTDB_PG_HOST),
        "PG_PORT": str(questdb.QUESTDB_PG_PORT),
    }
    logging.info(
        "QuestDB destination: ILP %s:%s, PG %s:%s",
        effective["ILP_HOST"],
        effective["ILP_PORT"],
        effective["PG_HOST"],
        effective["PG_PORT"],
    )
    expected = {
        key: os.environ[f"UTXORACLE_EXPECTED_QUESTDB_{key}"]
        for key in effective
        if os.environ.get(f"UTXORACLE_EXPECTED_QUESTDB_{key}")
    }
    if not expected:
        logging.info("QuestDB destination: no expected destination set, not checked")
        return
    wrong = {k: (effective[k], v) for k, v in expected.items() if effective[k] != v}
    if wrong:
        detail = ", ".join(
            f"{k} is {got} (expected {want})" for k, (got, want) in wrong.items()
        )
        logging.error("QuestDB destination mismatch: %s", detail)
        sys.exit(3)


def check_daily_tables_dedup() -> None:
    """Refuse to write into a table that does not deduplicate on ts (exit code 4).

    The daily row is keyed by the UTC day; without DEDUP UPSERT KEYS(ts) a rerun would add a
    duplicate row. Checked once per run, before the first write, from tables().
    """
    import asyncio

    import api.questdb_repository as questdb

    missing = asyncio.run(questdb.tables_without_dedup(("price_analysis", "metrics")))
    if missing:
        logging.error(
            "QuestDB tables without dedup on ts: %s; refusing to write "
            "(enable DEDUP UPSERT KEYS(ts) on a WAL table first)",
            ", ".join(missing),
        )
        sys.exit(4)


def utc_now() -> datetime:
    """The clock of the run (a function, so tests can inject a time)."""
    return datetime.now(timezone.utc)


def analysis_day_for(now: datetime) -> datetime:
    """Row key of both tables: the analysed day, the UTC day before `now`, at 00:00Z.

    The timer runs at 03:00Z and UTXOracle produces the price of "yesterday": the price is
    computed from the recent transactions at run time, i.e. mostly the day D-1. Any run on
    the same UTC date gets the same key, so the first successful run of the day wins and a
    rerun replaces nothing unless --overwrite is given (DEDUP UPSERT KEYS(ts) is the net).
    """
    return (now.astimezone(timezone.utc) - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


SCHEDULE_ENV = "UTXORACLE_DAILY_SCHEDULE_UTC"
EXIT_OUTSIDE_WINDOW = 5


def missing_metric_fields(transactions: list) -> list[str]:
    """Names of the fields the metrics need that NO transaction carries (empty = usable).

    Permanent guard, in one place, before any metrics block. The metrics read the
    mempool.space/electrs shape: vin[].prevout.scriptpubkey_address (active addresses),
    vout[].scriptpubkey_address (active addresses) and vout[].value (tx volume).
    getblock verbosity 2 from Bitcoin Core has vout[].scriptPubKey.address and no prevout,
    so with it the address metrics would silently be 0: reported here instead, and the run
    ends with exit 2 and no write (until the metrics learn that shape, F-432).
    """
    senders = receivers = values = False
    for tx in transactions:
        for vin in tx.get("vin", []):
            senders = senders or bool(
                (vin.get("prevout") or {}).get("scriptpubkey_address")
            )
        for vout in tx.get("vout", []):
            receivers = receivers or bool(vout.get("scriptpubkey_address"))
            values = values or vout.get("value") is not None
    present = {
        "vin[].prevout.scriptpubkey_address": senders,
        "vout[].scriptpubkey_address": receivers,
        "vout[].value": values,
    }
    return [name for name, ok in present.items() if not ok]


def check_run_window(now: datetime) -> None:
    """Exit 5, writing nothing, when the run started outside its window.

    The scheduled time ("HH:MM", UTC) comes from the systemd unit through
    UTXORACLE_DAILY_SCHEDULE_UTC, the single place it is written (a test keeps it equal to the
    timer's OnCalendar). The window of the run on UTC day D is [scheduled time on D,
    23:59:59Z on D]. A Persistent=true catch-up that fires after midnight is outside it:
    its key (the day before the run) would label the wrong day. Without the variable
    (manual use, tests) the window is not checked and that is logged; an unparsable value
    is an error (exit 2 through the usual path).
    """
    schedule = os.environ.get(SCHEDULE_ENV)
    if not schedule:
        logging.info("%s not set: run window not checked", SCHEDULE_ENV)
        return
    try:
        scheduled = datetime.strptime(schedule, "%H:%M")
    except ValueError as exc:
        raise ValueError(f"{SCHEDULE_ENV}={schedule!r} is not HH:MM") from exc
    now = now.astimezone(timezone.utc)
    start = now.replace(
        hour=scheduled.hour, minute=scheduled.minute, second=0, microsecond=0
    )
    if now < start:
        logging.error(
            "run fuori finestra: started at %s, the window of %s is [%s, 23:59:59Z]; "
            "writing nothing (exit %d)",
            now.isoformat(timespec="seconds"),
            now.date(),
            start.strftime("%H:%M:%SZ"),
            EXIT_OUTSIDE_WINDOW,
        )
        sys.exit(EXIT_OUTSIDE_WINDOW)


def preflight(args) -> tuple[datetime, set[str], bool]:
    """Destination, dedup and already-written-day checks, before any computation or write.

    Returns (analysis_day, tables to skip, nothing_to_do). Runs inside main()'s try so every
    non-zero exit is logged the same way. Exit codes of the script: 0 done or both rows of
    the day already present; 1 invalid configuration; 2 any failure (exception, incomplete
    row, failed metrics block, failed write); 3 QuestDB destination mismatch or the .env defining the destination; 4 a table
    without dedup on ts; 5 run outside its window (check_run_window); 6 invalid integer
    variable (startup guard or MIN_CONFIRMATIONS); 7 day not complete yet
    (IncompleteWindowError). The full list is at the top of the module.

    The skip needs BOTH rows of the day: with only one present the run was incomplete and
    both are rewritten, as with --overwrite, after a WARNING.
    """
    check_env_file_guard()
    check_questdb_destination()
    now = utc_now()
    analysis_day = analysis_day_for(now)
    skip_tables: set[str] = set()
    if args.dry_run:
        return analysis_day, skip_tables, False
    check_run_window(now)

    import asyncio

    import api.questdb_repository as questdb

    check_daily_tables_dedup()
    existing = asyncio.run(
        questdb.tables_with_day_row(("price_analysis", "metrics"), analysis_day)
    )
    if existing and args.overwrite:
        logging.warning(
            "--overwrite: replacing the %s row of %s already written (DEDUP upsert)",
            ", ".join(existing),
            analysis_day.date(),
        )
    elif len(existing) == 2:
        logging.info(
            "Both rows of %s already written: the first successful run wins, nothing to "
            "do (--overwrite replaces them)",
            analysis_day.date(),
        )
        return analysis_day, skip_tables, True
    elif existing:
        logging.warning(
            "only one row of %s exists (%s): the previous run was incomplete, rewriting "
            "BOTH rows as with --overwrite",
            analysis_day.date(),
            existing[0],
        )
    return analysis_day, skip_tables, False


def main():
    """
    Main execution flow for daily analysis.

    T046: Support CLI flags --init-db, --dry-run, --verbose

    Exit codes (full list at the top of the module): 0 done or both rows of the day already
    present; 1 invalid configuration; 2 any failure (no row is written); 3 destination
    mismatch or a .env defining it; 4 table without dedup on ts; 5 run outside its window;
    6 invalid integer variable (BadEnvValueError, name only); 7 the day to analyse is not
    complete yet (IncompleteWindowError, nothing written).
    """
    parser = argparse.ArgumentParser(description="UTXOracle Daily Analysis")

    parser.add_argument(
        "--dry-run", action="store_true", help="Run without saving to DB"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the rows of today (UTC) already written; default: first run wins",
    )

    args = parser.parse_args()

    # Load and validate configuration
    config = load_config()
    setup_logging(config["LOG_LEVEL"] if not args.verbose else "DEBUG")
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    try:
        validate_config(config)
    except EnvironmentError as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)

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

        analysis_day, skip_tables, nothing_to_do = preflight(args)
        if nothing_to_do:
            return

        # Step 1: Fetch mempool.space price (T039)
        window_end = analysis_day + timedelta(days=1)
        mempool_price = retry_with_backoff(
            lambda: fetch_mempool_price_at(
                int(window_end.timestamp()), config["MEMPOOL_API_URL"]
            )
        )

        # Step 2: Calculate UTXOracle price (T040 - Phase 9: uses mempool.space API)
        utx_result = calculate_utxoracle_price(config, analysis_day)

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
        current_time = datetime.now()

        metrics_failed: list[str] = []

        def run_metrics_block(name: str, block) -> None:
            """A failing block is recorded, never skipped: no half-filled metrics row."""
            try:
                block()
            except Exception as e:
                metrics_failed.append(name)
                logging.error(f"Metrics block {name} failed: {e}", exc_info=True)

        if METRICS_ENABLED:
            transactions = utx_result.get("transactions") or []

            def monte_carlo_block() -> None:
                nonlocal mc_result, action, combined_signal
                whale_vote = _calculate_whale_vote(
                    net_flow_btc=whale_signal.net_flow_btc,
                    direction=whale_signal.direction,
                )
                utxo_vote = _calculate_utxo_vote(confidence=utx_result["confidence"])

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

            def active_addresses_block() -> None:
                nonlocal active_addr_result
                if not transactions:
                    raise ValueError("no transactions available")
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

            def tx_volume_block() -> None:
                nonlocal tx_vol_result
                if not transactions or not utx_result["price_usd"]:
                    raise ValueError("no transactions or no price available")
                tx_vol_result = calculate_tx_volume(
                    transactions=transactions,
                    utxoracle_price=utx_result["price_usd"],
                    confidence=utx_result["confidence"],
                    timestamp=current_time,
                    # The fetchers already turned satoshi into BTC (_convert_satoshi_to_btc):
                    # the conversion happens once, there. Dividing again here gave 1e-8 of it.
                    value_unit="btc",
                )
                logging.info(
                    f"💰 TX Volume: {tx_vol_result.tx_volume_btc:.2f} BTC "
                    f"(${tx_vol_result.tx_volume_usd:,.0f} USD), "
                    f"{tx_vol_result.tx_count} transactions"
                )

            def input_format_block() -> None:
                sample = utx_result.get("format_sample")
                missing = missing_metric_fields(
                    [sample] if sample is not None else transactions
                )
                if missing:
                    raise ValueError(
                        f"transactions lack the fields {', '.join(missing)}"
                    )

            run_metrics_block("input_format", input_format_block)

            # Monte Carlo needs a whale signal: without one it does not apply.
            if whale_signal:
                run_metrics_block("monte_carlo", monte_carlo_block)
            run_metrics_block("active_addresses", active_addresses_block)
            run_metrics_block("tx_volume", tx_volume_block)

        # Step 2.8: Spec-009 Advanced On-Chain Analytics
        power_law_result = None
        symbolic_result = None
        fractal_result = None
        enhanced_fusion_result = None
        wasserstein_result = None
        wasserstein_attempted = False

        if ADVANCED_METRICS_ENABLED:
            try:
                # Extract UTXO values from transactions for distribution analysis
                utxo_values = []
                for tx in utx_result.get("transactions", []):
                    for vout in tx.get("vout", []):
                        value = vout.get("value", 0)
                        if value > 0:
                            utxo_values.append(value)

                # Spec-010: Wasserstein Distribution Shift Detection. Persisted in metrics, so a
                # failure is a metrics-block failure (no write, exit 2), not a warning.
                wasserstein_attempted = True
                w_vote = None

                def wasserstein_block() -> None:
                    nonlocal wasserstein_result, w_vote
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

                if WASSERSTEIN_ENABLED and len(utxo_values) >= 288:  # 2 windows of 144
                    run_metrics_block("wasserstein", wasserstein_block)

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

                    # Spec-016/019: SOPR signal calculation
                    sopr_vote = None
                    sopr_conf = None
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
                            # B6 fix: Check for meaningful signal (not just truthy dict)
                            # Empty window returns dict with sopr_vote=0.0, which should be treated as no signal
                            if sopr_signals and sopr_signals.get("sopr_vote") != 0.0:
                                sopr_vote = sopr_signals["sopr_vote"]
                                # spec-019: Add confidence from signal strength
                                sopr_conf = sopr_signals.get("confidence", 0.8)
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
                                        f"→ vote={sopr_vote:+.2f}, conf={sopr_conf:.2f}"
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
                        sopr_conf=sopr_conf,  # spec-019 SOPR confidence
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
                if WASSERSTEIN_ENABLED and not wasserstein_attempted:
                    # The failure came before the Wasserstein block could run: its columns
                    # would be NULL for a reason nobody sees.
                    metrics_failed.append("wasserstein")
                    logging.error(f"Metrics block wasserstein failed: {e}")

        # Step 3: Compare prices (T041)
        comparison = compare_prices(utx_result["price_usd"], mempool_price)

        # Step 4: Validate data quality (T042a)
        data = {
            # The row key is the analysed UTC day at 00:00Z (not the run time): with DEDUP
            # UPSERT KEYS(ts) a rerun on the same day replaces the row instead of adding one.
            "timestamp": analysis_day.isoformat(),
            # End of the analysed window [analysis_day, window_end): D 00:00Z.
            "window_end_ts": window_end,
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

        # Step 4b: only complete rows are written (F-419): a missing value or a failed metrics
        # block ends the run with an error and writes nothing, never a row with NULL columns.
        price_columns = (
            "mempool_price",
            "utxoracle_price",
            "diff_amount",
            "diff_percent",
            "confidence",
            "tx_count",
            "is_valid",
        )
        missing_values = [k for k in price_columns if data.get(k) is None]
        if missing_values:
            logging.error(
                "price_analysis row incomplete, missing: %s", ", ".join(missing_values)
            )
            raise RuntimeError(
                f"price_analysis row incomplete: {', '.join(missing_values)}"
            )
        if not METRICS_ENABLED and not args.dry_run:
            raise RuntimeError("spec-007 metrics modules are not available")
        if metrics_failed:
            raise RuntimeError(f"metrics blocks failed: {', '.join(metrics_failed)}")

        # Step 5: Save to database
        if not args.dry_run:
            if "price_analysis" not in skip_tables:
                save_to_questdb(data)
            # F-419: the metrics were computed and then dropped; persist them with the price row.
            if "metrics" not in skip_tables:
                saved = save_metrics_to_db(
                    timestamp=analysis_day,
                    monte_carlo=mc_result.to_dict() if mc_result else None,
                    active_addresses=active_addr_result.to_dict()
                    if active_addr_result
                    else None,
                    tx_volume=tx_vol_result.to_dict() if tx_vol_result else None,
                    wasserstein=wasserstein_result.to_dict()
                    if wasserstein_result and wasserstein_result.is_valid
                    else None,
                )
                if not saved:
                    raise RuntimeError("Failed to save metrics to QuestDB")
        else:
            logging.info("[DRY-RUN] Would save data:")
            logging.info(json.dumps(data, indent=2, default=str))

        logging.info("Daily analysis completed successfully")

    except Exception as e:
        logging.error(f"Daily analysis failed: {e}", exc_info=True)
        send_alert_webhook("ERROR", f"Daily analysis failed: {e}")
        sys.exit(
            EXIT_INCOMPLETE_WINDOW
            if isinstance(e, IncompleteWindowError)
            else EXIT_BAD_ENV_VALUE
            if isinstance(e, BadEnvValueError)
            else 2
        )


if __name__ == "__main__":
    main()
