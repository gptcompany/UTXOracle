"""
Configuration module for Whale Detection Dashboard.
Task T006: Create logging configuration with rotation.
"""

import os
import sys
import logging
import logging.handlers
from pathlib import Path
from typing import Optional

# Use SOPS-encrypted secrets when available, otherwise fall back to dotenv/plain env
try:
    sys.path.insert(0, "/media/sam/1TB/claude-hooks-shared/scripts")
    from secrets_loader import load_secrets

    _secrets_mode = "sops"
except ImportError:
    try:
        from dotenv import load_dotenv as load_secrets

        _secrets_mode = "dotenv"
    except ImportError:
        def load_secrets(_path: str | None = None):
            return False

        _secrets_mode = "env"

# Load environment variables (from .env.enc when SOPS is available, otherwise .env or current env)
_project_root = Path(__file__).resolve().parent.parent
_env_enc_path = _project_root / ".env.enc"
_env_path = _project_root / ".env"
_preloaded_jwt_secret = os.getenv("JWT_SECRET")
if _secrets_mode == "sops" and _env_enc_path.exists():
    load_secrets(str(_env_enc_path))
elif _env_path.exists():
    load_secrets(str(_env_path))
else:
    load_secrets(None)
if _preloaded_jwt_secret and (
    not os.getenv("JWT_SECRET") or str(os.getenv("JWT_SECRET")).startswith("ENC[")
):
    os.environ["JWT_SECRET"] = _preloaded_jwt_secret

# Environment configuration
def get_clean_env(key: str, default: str = "") -> str:
    val = os.getenv(key, default)
    if val is not None and str(val).startswith("ENC["):
        return default
    return val


def get_clean_env_list(key: str) -> list[str]:
    raw = get_clean_env(key)
    return [item.strip() for item in raw.split(",") if item.strip()]

# SECURITY: JWT_SECRET must be set in environment - no insecure defaults
_jwt_secret = get_clean_env("JWT_SECRET")
if not _jwt_secret:
    raise ValueError(
        "SECURITY ERROR: JWT_SECRET environment variable is required. "
        "Generate with: openssl rand -base64 64"
    )
JWT_SECRET = _jwt_secret


def get_cors_middleware_kwargs(origins: list[str]) -> dict[str, object]:
    normalized = [origin for origin in origins if origin]
    if normalized and "*" not in normalized:
        return {
            "allow_origins": normalized,
            "allow_credentials": True,
        }
    return {
        "allow_origins": ["*"],
        "allow_credentials": False,
    }


# QuestDB Configuration
QUESTDB_ILP_HOST = get_clean_env("QUESTDB_ILP_HOST", "localhost")
QUESTDB_ILP_PORT = int(get_clean_env("QUESTDB_ILP_PORT", "9009"))
QUESTDB_PG_HOST = get_clean_env("QUESTDB_PG_HOST", "localhost")
QUESTDB_PG_PORT = int(get_clean_env("QUESTDB_PG_PORT", "8812"))
QUESTDB_HTTP_HOST = get_clean_env("QUESTDB_HTTP_HOST", "localhost")
QUESTDB_HTTP_PORT = int(get_clean_env("QUESTDB_HTTP_PORT", "9000"))
QUESTDB_PG_USER = get_clean_env("QUESTDB_PG_USER", "admin")
QUESTDB_PG_PASSWORD = get_clean_env("QUESTDB_PG_PASSWORD", "quest")
QUESTDB_PG_DATABASE = get_clean_env("QUESTDB_PG_DATABASE", "main")
QUESTDB_POOL_MIN_SIZE = int(get_clean_env("QUESTDB_POOL_MIN_SIZE", "5"))
QUESTDB_POOL_MAX_SIZE = int(get_clean_env("QUESTDB_POOL_MAX_SIZE", "20"))
MEMPOOL_API_URL = get_clean_env("MEMPOOL_API_URL", "http://127.0.0.1:8999")
WHALE_MIN_BTC = float(get_clean_env("WHALE_MIN_BTC", "100"))
WHALE_WS_PORT = int(get_clean_env("WHALE_WS_PORT", "8001"))
FASTAPI_HOST = get_clean_env("FASTAPI_HOST", "0.0.0.0")
FASTAPI_PORT = int(get_clean_env("FASTAPI_PORT", "8001"))
DUCKDB_PATH = get_clean_env("DUCKDB_PATH", "data/utxoracle.duckdb")
UTXO_DB_PATH = get_clean_env("UTXO_DB_PATH", DUCKDB_PATH)
ELECTRS_HTTP_URL = get_clean_env("ELECTRS_HTTP_URL", "http://127.0.0.1:3002")
MEMPOOL_API_V1_URL = get_clean_env("MEMPOOL_API_V1_URL", f"{MEMPOOL_API_URL.rstrip('/')}/api/v1")
BRK_BASE_URL = get_clean_env("BRK_BASE_URL", "http://127.0.0.1:7070")
HYPERLIQUID_NODE_API_URL = get_clean_env("HYPERLIQUID_NODE_API_URL", "http://127.0.0.1:3001/info")
HYPERLIQUID_NODE_INFO_REQUEST_TYPE = get_clean_env("HYPERLIQUID_NODE_INFO_REQUEST_TYPE", "")
HYPERLIQUID_NODE_SNAPSHOT_PATH = get_clean_env("HYPERLIQUID_NODE_SNAPSHOT_PATH", "")
HYPERLIQUID_METRICS_URL = get_clean_env("HYPERLIQUID_METRICS_URL", "http://127.0.0.1:9101/metrics")
HYPERLIQUID_DATA_ROOT = get_clean_env("HYPERLIQUID_DATA_ROOT", "/media/sam/4TB-NVMe/hyperliquid/filtered")
HYPERLIQUID_FILTERED_STREAM = get_clean_env("HYPERLIQUID_FILTERED_STREAM", "hip3_oracle_updates_by_block")
HYPERLIQUID_MAX_AGE_SECONDS = float(get_clean_env("HYPERLIQUID_MAX_AGE_SECONDS", "900"))
WASSERSTEIN_SHIFT_THRESHOLD = float(get_clean_env("WASSERSTEIN_SHIFT_THRESHOLD", "0.10"))
LIVE_ENABLED = get_clean_env("LIVE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
LIVE_API_PORT = int(get_clean_env("LIVE_API_PORT", "8011"))
LIVE_SOURCE_TIMEOUT_SECONDS = float(get_clean_env("LIVE_SOURCE_TIMEOUT_SECONDS", "5.0"))
LIVE_MARKET_INTERVAL_SECONDS = float(get_clean_env("LIVE_MARKET_INTERVAL_SECONDS", "5.0"))
LIVE_BLOCK_POLL_INTERVAL_SECONDS = float(get_clean_env("LIVE_BLOCK_POLL_INTERVAL_SECONDS", "2.0"))
LIVE_RETENTION_HOURS = int(get_clean_env("LIVE_RETENTION_HOURS", "24"))
LIVE_WORKER_LOCK_PATH = get_clean_env(
    "LIVE_WORKER_LOCK_PATH", "/tmp/utxoracle_live.worker.lock"
)
LIVE_ORACLE_TX_CONCURRENCY = int(get_clean_env("LIVE_ORACLE_TX_CONCURRENCY", "32"))
LIVE_ORACLE_MIN_TX_COUNT = int(get_clean_env("LIVE_ORACLE_MIN_TX_COUNT", "1000"))
API_CORS_ALLOWED_ORIGINS = get_clean_env_list("API_CORS_ALLOWED_ORIGINS")
LIVE_API_CORS_ALLOWED_ORIGINS = (
    get_clean_env_list("LIVE_API_CORS_ALLOWED_ORIGINS") or API_CORS_ALLOWED_ORIGINS
)

# WebSocket configuration
WS_HEARTBEAT_INTERVAL = 30  # seconds
WS_HEARTBEAT_TIMEOUT = 90  # 3 missed heartbeats
WS_MESSAGE_BATCH_WINDOW = 0.1  # 100ms batching window
WS_MAX_BATCH_SIZE = 10  # maximum messages per batch

# Rate limiting configuration
RATE_LIMIT_HTTP_PER_MINUTE = 100
RATE_LIMIT_WS_PER_SECOND = 20
RATE_LIMIT_BURST_CAPACITY = 10
RATE_LIMIT_CONNECTION_ATTEMPTS = 5  # per minute per IP

# JWT configuration
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 1
JWT_REFRESH_MINUTES = 55  # Refresh 5 minutes before expiry

# Data retention configuration
UI_RETENTION_HOURS = 24  # Transaction feed in UI
API_RETENTION_DAYS = 7  # Historical data via API
AGGREGATION_INTERVALS = ["1m", "5m", "1h", "24h"]

# Alert thresholds
ALERT_CRITICAL_BTC = 1000
ALERT_HIGH_BTC = 500
ALERT_MEDIUM_BTC = 250
ALERT_LOW_BTC = 100

# Logging configuration
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "whale_dashboard.log"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB per file
LOG_BACKUP_COUNT = 5  # Keep 5 old log files
LOG_LEVEL = get_clean_env("LOG_LEVEL", "INFO")


# Create logger function
def setup_logging(name: str, log_file: Optional[Path] = None) -> logging.Logger:
    """
    Set up logging with rotation for a specific module.

    Args:
        name: Logger name (usually __name__)
        log_file: Optional specific log file for this logger

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL.upper()))

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler with rotation
    file_path = log_file or LOG_FILE
    file_handler = logging.handlers.RotatingFileHandler(
        filename=file_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger


# Create default logger for this module
logger = setup_logging(__name__)
logger.info("Whale Dashboard configuration loaded")
logger.info(f"QuestDB PG URL: postgresql://{QUESTDB_PG_USER}:***@{QUESTDB_PG_HOST}:{QUESTDB_PG_PORT}/{QUESTDB_PG_DATABASE}")
logger.info(f"Mempool API: {MEMPOOL_API_URL}")
logger.info(f"WebSocket port: {WHALE_WS_PORT}")
logger.info(f"Whale threshold: {WHALE_MIN_BTC} BTC")
