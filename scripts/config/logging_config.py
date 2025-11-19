#!/usr/bin/env python3
"""
Logging configuration for mempool whale detection system
Task T005: Structured logging with JSON output for production
"""

import logging
import logging.handlers
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging in production"""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


class HumanReadableFormatter(logging.Formatter):
    """Human-readable formatter for development"""

    # Color codes for terminal output
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",  # Reset
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors"""
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]

        # Format: [TIMESTAMP] LEVEL - module.function:line - message
        formatted = (
            f"{color}[{self.formatTime(record, '%Y-%m-%d %H:%M:%S')}] "
            f"{record.levelname:<8}{reset} - "
            f"{record.module}.{record.funcName}:{record.lineno} - "
            f"{record.getMessage()}"
        )

        # Add exception if present
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted


def setup_logging(
    name: str = "mempool_whale",
    level: str = "INFO",
    mode: str = "development",
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Setup logging configuration for the application

    Args:
        name: Logger name
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        mode: "development" for human-readable, "production" for JSON
        log_dir: Directory for log files
        max_bytes: Maximum size of log file before rotation
        backup_count: Number of backup log files to keep

    Returns:
        Configured logger instance
    """

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console handler (always present)
    console_handler = logging.StreamHandler(sys.stdout)

    if mode == "production":
        # JSON format for production
        console_handler.setFormatter(JSONFormatter())
    else:
        # Human-readable format for development
        console_handler.setFormatter(HumanReadableFormatter())

    logger.addHandler(console_handler)

    # File handler (rotating)
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_path / f"{name}.log", maxBytes=max_bytes, backupCount=backup_count
    )

    if mode == "production":
        file_handler.setFormatter(JSONFormatter())
    else:
        # Use standard format for file in development
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s"
            )
        )

    logger.addHandler(file_handler)

    # Log initial message
    logger.info(f"Logging initialized: mode={mode}, level={level}, log_dir={log_dir}")

    return logger


def get_logger(name: str = None, level: str = None, mode: str = None) -> logging.Logger:
    """
    Get or create a logger with configuration

    Args:
        name: Logger name (default: mempool_whale)
        level: Override logging level
        mode: Override mode (development/production)

    Returns:
        Logger instance
    """
    import os

    # Get configuration from environment or use defaults
    name = name or os.environ.get("LOG_NAME", "mempool_whale")
    level = level or os.environ.get("LOG_LEVEL", "INFO")
    mode = mode or os.environ.get("LOG_MODE", "development")

    # Check if logger already exists and is configured
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    # Setup new logger
    return setup_logging(name=name, level=level, mode=mode)


class LogContext:
    """Context manager for adding extra fields to log messages"""

    def __init__(self, logger: logging.Logger, **kwargs):
        self.logger = logger
        self.extra_fields = kwargs
        self.old_factory = logging.getLogRecordFactory()

    def __enter__(self):
        """Add extra fields to log record factory"""

        def record_factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            record.extra_fields = self.extra_fields
            return record

        logging.setLogRecordFactory(record_factory)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore original log record factory"""
        logging.setLogRecordFactory(self.old_factory)


# Example usage and testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test logging configuration")
    parser.add_argument(
        "--mode",
        choices=["development", "production"],
        default="development",
        help="Logging mode",
    )
    parser.add_argument(
        "--level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level",
    )

    args = parser.parse_args()

    # Setup logger
    logger = setup_logging(level=args.level, mode=args.mode)

    # Test different log levels
    logger.debug("This is a DEBUG message")
    logger.info("This is an INFO message")
    logger.warning("This is a WARNING message")
    logger.error("This is an ERROR message")

    # Test with extra context
    with LogContext(logger, transaction_id="test_tx_123", client_id="test_client"):
        logger.info("Message with extra context fields")

    # Test exception logging
    try:
        raise ValueError("Test exception")
    except ValueError:
        logger.exception("Exception occurred during processing")

    logger.info("Logging test completed")
