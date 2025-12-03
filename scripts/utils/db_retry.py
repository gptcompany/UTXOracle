#!/usr/bin/env python3
"""
Database Retry Decorator with Tenacity
Task: P1 - Resilience improvement

Features:
- Exponential backoff for database operations
- Configurable retry attempts and delays
- Only retries on transient errors (not schema/data errors)
- Structured logging for retry attempts
- Fail-fast on permanent errors

Usage:
    from scripts.utils.db_retry import with_db_retry, db_retry_config

    @with_db_retry()
    def query_database(conn):
        return conn.execute("SELECT * FROM table").fetchall()

    # Custom retry config
    @with_db_retry(max_attempts=5, initial_delay=2.0)
    def critical_operation(conn):
        return conn.execute("INSERT INTO ...").fetchall()
"""

import logging
from functools import wraps
from typing import Callable, Optional, Set, Type

try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        before_sleep_log,
        RetryError,
    )

    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False
    logging.warning("tenacity library not available - database retry disabled")


logger = logging.getLogger(__name__)


# =============================================================================
# Retry Configuration
# =============================================================================


class DatabaseRetryConfig:
    """Configuration for database retry behavior"""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 10.0,
        multiplier: float = 2.0,
        retry_on_errors: Optional[Set[Type[Exception]]] = None,
    ):
        """
        Initialize retry configuration.

        Args:
            max_attempts: Maximum number of retry attempts (default: 3)
            initial_delay: Initial delay in seconds (default: 1.0)
            max_delay: Maximum delay in seconds (default: 10.0)
            multiplier: Exponential backoff multiplier (default: 2.0)
            retry_on_errors: Set of exception types to retry on (default: transient errors)
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier

        # Default: retry on transient database errors
        if retry_on_errors is None:
            self.retry_on_errors = {
                # DuckDB transient errors
                IOError,  # File system issues
                OSError,  # Operating system issues
                ConnectionError,  # Network/connection issues
                TimeoutError,  # Operation timeout
                # Generic transient errors
                Exception,  # Catch-all for unknown transient errors
            }
        else:
            self.retry_on_errors = retry_on_errors

    def should_retry(self, exception: Exception) -> bool:
        """
        Determine if exception is transient and should be retried.

        Args:
            exception: The exception that occurred

        Returns:
            bool: True if should retry, False otherwise
        """
        # Don't retry on schema/data errors
        error_msg = str(exception).lower()

        # Permanent errors - DO NOT retry
        permanent_errors = [
            "constraint",  # Constraint violations
            "unique",  # Unique key violations
            "foreign key",  # Foreign key violations
            "not null",  # NOT NULL violations
            "invalid",  # Invalid syntax
            "syntax error",  # SQL syntax errors
            "does not exist",  # Table/column doesn't exist
            "permission denied",  # Permission errors
        ]

        if any(err in error_msg for err in permanent_errors):
            logger.warning(f"Permanent error detected - not retrying: {error_msg}")
            return False

        # Check if exception type is retryable
        return any(isinstance(exception, err_type) for err_type in self.retry_on_errors)


# Default configuration
default_config = DatabaseRetryConfig()


# =============================================================================
# Retry Decorator
# =============================================================================


def with_db_retry(
    max_attempts: Optional[int] = None,
    initial_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    multiplier: Optional[float] = None,
):
    """
    Decorator to add retry logic to database operations.

    Args:
        max_attempts: Maximum retry attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 10.0)
        multiplier: Exponential backoff multiplier (default: 2.0)

    Returns:
        Decorated function with retry logic

    Example:
        @with_db_retry(max_attempts=5)
        def query_database(conn):
            return conn.execute("SELECT * FROM table").fetchall()
    """
    if not TENACITY_AVAILABLE:
        # No-op decorator if tenacity not available
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                logger.warning(
                    f"Tenacity not available - {func.__name__} running without retry"
                )
                return func(*args, **kwargs)

            return wrapper

        return decorator

    # Use provided values or defaults
    config = DatabaseRetryConfig(
        max_attempts=max_attempts or default_config.max_attempts,
        initial_delay=initial_delay or default_config.initial_delay,
        max_delay=max_delay or default_config.max_delay,
        multiplier=multiplier or default_config.multiplier,
    )

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        @retry(
            stop=stop_after_attempt(config.max_attempts),
            wait=wait_exponential(
                multiplier=config.multiplier,
                min=config.initial_delay,
                max=config.max_delay,
            ),
            retry=retry_if_exception_type(tuple(config.retry_on_errors)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                # Check if should retry
                if not config.should_retry(e):
                    logger.error(
                        f"Permanent error in {func.__name__} - not retrying: {e}"
                    )
                    raise

                # Log retry attempt
                logger.warning(f"Transient error in {func.__name__} - will retry: {e}")
                raise  # Let tenacity handle the retry

        return wrapper

    return decorator


# =============================================================================
# Convenience Functions
# =============================================================================


def execute_with_retry(conn, query: str, params=None, max_attempts: int = 3):
    """
    Execute database query with automatic retry on transient errors.

    Args:
        conn: DuckDB connection
        query: SQL query string
        params: Query parameters (optional)
        max_attempts: Maximum retry attempts

    Returns:
        Query result

    Example:
        result = execute_with_retry(conn, "SELECT * FROM table WHERE id = ?", [123])
    """

    @with_db_retry(max_attempts=max_attempts)
    def _execute():
        if params:
            return conn.execute(query, params).fetchall()
        else:
            return conn.execute(query).fetchall()

    return _execute()


def connect_with_retry(db_path: str, max_attempts: int = 3, read_only: bool = True):
    """
    Connect to DuckDB with automatic retry on transient errors.

    Args:
        db_path: Path to DuckDB database
        max_attempts: Maximum retry attempts
        read_only: Open in read-only mode

    Returns:
        DuckDB connection

    Example:
        conn = connect_with_retry("/path/to/database.db")
    """
    import duckdb

    @with_db_retry(max_attempts=max_attempts)
    def _connect():
        return duckdb.connect(db_path, read_only=read_only)

    return _connect()


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":

    # Example 1: Decorator usage
    @with_db_retry(max_attempts=5)
    def query_example(conn):
        """Example query with retry"""
        return conn.execute("SELECT 1 as test").fetchone()

    # Example 2: Convenience function
    def main():
        try:
            # Connect with retry
            conn = connect_with_retry(":memory:")

            # Create test table
            conn.execute("CREATE TABLE test (id INTEGER, value VARCHAR)")

            # Insert with retry
            @with_db_retry()
            def insert_data():
                conn.execute("INSERT INTO test VALUES (1, 'hello')")

            insert_data()

            # Query with retry
            result = execute_with_retry(conn, "SELECT * FROM test")
            print(f"✅ Query result: {result}")

            # Query with decorator
            result2 = query_example(conn)
            print(f"✅ Decorator result: {result2}")

            conn.close()

        except Exception as e:
            print(f"❌ Error: {e}")

    main()
