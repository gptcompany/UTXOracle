"""
Configuration Management and Logging Infrastructure

Settings for:
- Bitcoin Core ZMQ connection
- WebSocket server
- Algorithm parameters
- Logging (structured JSON for production, human-readable for dev)
"""

import logging
import logging.config
import os
import sys
from pathlib import Path
from typing import Literal


# =============================================================================
# Environment Detection
# =============================================================================


def get_environment() -> Literal["development", "production", "test"]:
    """Detect current environment from ENV variable"""
    env = os.getenv("UTXORACLE_ENV", "development").lower()
    if env in ("production", "prod"):
        return "production"
    elif env in ("test", "testing"):
        return "test"
    else:
        return "development"


ENVIRONMENT = get_environment()


# =============================================================================
# Bitcoin Core Configuration
# =============================================================================


class BitcoinConfig:
    """Bitcoin Core ZMQ and RPC settings"""

    # ZMQ endpoints
    ZMQ_TX_ENDPOINT: str = os.getenv("BITCOIN_ZMQ_TX", "tcp://127.0.0.1:28332")
    ZMQ_BLOCK_ENDPOINT: str = os.getenv("BITCOIN_ZMQ_BLOCK", "tcp://127.0.0.1:28333")

    # Connection settings
    ZMQ_TIMEOUT_MS: int = 5000  # 5 seconds
    ZMQ_RECONNECT_INTERVAL_SEC: int = 5

    # Data directory (for cookie auth)
    BITCOIN_DATA_DIR: Path = Path(
        os.getenv("BITCOIN_DATA_DIR", "~/.bitcoin")
    ).expanduser()


# =============================================================================
# WebSocket Server Configuration
# =============================================================================


class ServerConfig:
    """FastAPI WebSocket server settings"""

    HOST: str = os.getenv("UTXORACLE_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("UTXORACLE_PORT", "8000"))

    # Update throttling
    MIN_UPDATE_INTERVAL_SEC: float = 0.5  # Send updates every 500ms minimum

    # CORS settings
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]


# =============================================================================
# Algorithm Parameters
# =============================================================================


class AlgorithmConfig:
    """UTXOracle algorithm parameters"""

    # Transaction filters (from UTXOracle.py Step 6)
    MAX_INPUTS: int = 5
    REQUIRED_OUTPUTS: int = 2
    MIN_AMOUNT_BTC: float = 1e-5
    MAX_AMOUNT_BTC: float = 1e5

    # Histogram settings (Step 5)
    HISTOGRAM_BINS: int = 10000
    HISTOGRAM_PRICE_MIN: float = 0.0
    HISTOGRAM_PRICE_MAX: float = 200000.0  # USD

    # Rolling window (3-hour expiration)
    ROLLING_WINDOW_HOURS: float = 3.0
    ROLLING_WINDOW_SECONDS: float = 3.0 * 3600

    # Transaction history for visualization
    MAX_TRANSACTION_HISTORY: int = 500  # Keep last 500 for scatter plot


# =============================================================================
# Logging Configuration
# =============================================================================


class LogConfig:
    """Logging infrastructure settings"""

    # Log level
    LEVEL: str = os.getenv(
        "LOG_LEVEL", "INFO" if ENVIRONMENT == "production" else "DEBUG"
    )

    # Log directory
    LOG_DIR: Path = Path(os.getenv("LOG_DIR", "./logs"))
    LOG_DIR.mkdir(exist_ok=True)

    # Log format
    FORMAT_PRODUCTION = "json"  # Structured JSON logs
    FORMAT_DEVELOPMENT = "human"  # Human-readable colored logs
    FORMAT: str = (
        FORMAT_PRODUCTION if ENVIRONMENT == "production" else FORMAT_DEVELOPMENT
    )


def setup_logging():
    """
    Configure logging based on environment.

    - Development: Human-readable format with colors
    - Production: Structured JSON format for log aggregation
    - Test: Minimal output
    """

    if ENVIRONMENT == "test":
        # Minimal logging for tests
        logging.basicConfig(level=logging.WARNING, format="%(message)s")
        return

    # Logging configuration dictionary
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "development": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "production": {
                "format": '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s", "module": "%(module)s", "function": "%(funcName)s"}',
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": LogConfig.FORMAT_DEVELOPMENT
                if ENVIRONMENT == "development"
                else "production",
                "stream": sys.stdout,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "production",
                "filename": LogConfig.LOG_DIR / "utxoracle.log",
                "maxBytes": 10 * 1024 * 1024,  # 10 MB
                "backupCount": 5,
            },
        },
        "loggers": {
            "uvicorn": {
                "level": LogConfig.LEVEL,
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "live": {
                "level": LogConfig.LEVEL,
                "handlers": ["console", "file"],
                "propagate": False,
            },
        },
        "root": {"level": LogConfig.LEVEL, "handlers": ["console", "file"]},
    }

    logging.config.dictConfig(config)

    # Log startup message
    logger = logging.getLogger("live.config")
    logger.info(f"UTXOracle Live starting in {ENVIRONMENT} mode")
    logger.info(f"Log level: {LogConfig.LEVEL}")
    logger.info(f"Bitcoin ZMQ: {BitcoinConfig.ZMQ_TX_ENDPOINT}")
    logger.info(f"WebSocket server: {ServerConfig.HOST}:{ServerConfig.PORT}")


# =============================================================================
# Exports
# =============================================================================


__all__ = [
    "Config",
    "get_config",
    "BitcoinConfig",
    "ServerConfig",
    "AlgorithmConfig",
    "LogConfig",
    "ENVIRONMENT",
    "setup_logging",
]

# =============================================================================
# Configuration Container (T051 requirement)
# =============================================================================


class Config:
    """Unified configuration container for UTXOracle Live."""

    def __init__(self):
        # Bitcoin settings
        self.zmq_endpoint = BitcoinConfig.ZMQ_TX_ENDPOINT
        self.zmq_block_endpoint = BitcoinConfig.ZMQ_BLOCK_ENDPOINT
        self.zmq_timeout_ms = BitcoinConfig.ZMQ_TIMEOUT_MS
        self.zmq_reconnect_interval = BitcoinConfig.ZMQ_RECONNECT_INTERVAL_SEC
        self.bitcoin_data_dir = BitcoinConfig.BITCOIN_DATA_DIR

        # Server settings
        self.host = ServerConfig.HOST
        self.port = ServerConfig.PORT
        self.min_broadcast_interval = ServerConfig.MIN_UPDATE_INTERVAL_SEC
        self.cors_origins = ServerConfig.CORS_ORIGINS

        # Algorithm settings
        self.max_inputs = AlgorithmConfig.MAX_INPUTS
        self.required_outputs = AlgorithmConfig.REQUIRED_OUTPUTS
        self.min_amount_btc = AlgorithmConfig.MIN_AMOUNT_BTC
        self.max_amount_btc = AlgorithmConfig.MAX_AMOUNT_BTC
        self.histogram_bins = AlgorithmConfig.HISTOGRAM_BINS
        self.histogram_price_min = AlgorithmConfig.HISTOGRAM_PRICE_MIN
        self.histogram_price_max = AlgorithmConfig.HISTOGRAM_PRICE_MAX
        self.window_hours = AlgorithmConfig.ROLLING_WINDOW_HOURS
        self.window_seconds = AlgorithmConfig.ROLLING_WINDOW_SECONDS
        self.max_transaction_history = AlgorithmConfig.MAX_TRANSACTION_HISTORY


_config = None


def get_config():
    """Get the global configuration instance (singleton)."""
    global _config
    if _config is None:
        _config = Config()
    return _config
