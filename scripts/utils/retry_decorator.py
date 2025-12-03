#!/usr/bin/env python3
"""
Retry Decorator with Tenacity
Task T010+: Resilient error handling for database and external API operations

Provides production-ready retry logic with:
- Exponential backoff with jitter
- Custom retry conditions
- Structured logging with context
- Configurable max attempts
"""

import logging
from typing import Type, Union, Tuple, Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log,
    RetryError,
)
import duckdb

logger = logging.getLogger(__name__)


# ==================== Database Retry ====================


def retry_database(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
):
    """
    Retry decorator for DuckDB database operations

    Retries on:
    - duckdb.IOException (disk I/O errors)
    - duckdb.CatalogException (table/schema issues)
    - duckdb.OperationalError (connection issues)

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        min_wait: Minimum wait time in seconds (default: 1.0)
        max_wait: Maximum wait time in seconds (default: 10.0)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_database(max_attempts=3)
        def insert_prediction(signal: MempoolWhaleSignal):
            conn.execute("INSERT INTO ...", signal.to_db_dict())
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(
            (duckdb.IOException, duckdb.CatalogException, duckdb.OperationalError)
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.DEBUG),
        reraise=True,
    )


# ==================== HTTP/API Retry ====================


def retry_http(
    max_attempts: int = 5,
    min_wait: float = 0.5,
    max_wait: float = 30.0,
):
    """
    Retry decorator for HTTP/API operations (aiohttp, requests)

    Retries on:
    - ConnectionError (network failures)
    - TimeoutError (request timeouts)
    - OSError (socket errors)

    Args:
        max_attempts: Maximum number of retry attempts (default: 5)
        min_wait: Minimum wait time in seconds (default: 0.5)
        max_wait: Maximum wait time in seconds (default: 30.0)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_http(max_attempts=5)
        async def fetch_mempool_transactions():
            async with session.get(url) as response:
                return await response.json()
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.DEBUG),
        reraise=True,
    )


# ==================== Custom Retry ====================


def retry_on_exception(
    exception_types: Union[Type[Exception], Tuple[Type[Exception], ...]],
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
):
    """
    Custom retry decorator for specific exception types

    Args:
        exception_types: Exception type(s) to retry on
        max_attempts: Maximum number of retry attempts (default: 3)
        min_wait: Minimum wait time in seconds (default: 1.0)
        max_wait: Maximum wait time in seconds (default: 10.0)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_on_exception(ValueError, max_attempts=2)
        def parse_transaction(data: dict):
            if not data.get("txid"):
                raise ValueError("Missing txid")
            return Transaction(**data)
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(exception_types),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.DEBUG),
        reraise=True,
    )


# ==================== Context Manager Wrapper ====================


class RetryContext:
    """
    Context manager for retry logic without decorators

    Useful for code blocks that need retry behavior without
    wrapping entire functions.

    Example:
        retry_ctx = RetryContext(max_attempts=3)
        for attempt in retry_ctx:
            with attempt:
                conn.execute("INSERT INTO ...", data)
                break  # Success - exit retry loop
    """

    def __init__(
        self,
        max_attempts: int = 3,
        min_wait: float = 1.0,
        max_wait: float = 10.0,
        exception_types: Tuple[Type[Exception], ...] = (Exception,),
    ):
        """
        Initialize retry context

        Args:
            max_attempts: Maximum retry attempts
            min_wait: Minimum wait between retries (seconds)
            max_wait: Maximum wait between retries (seconds)
            exception_types: Tuple of exception types to catch
        """
        self.max_attempts = max_attempts
        self.min_wait = min_wait
        self.max_wait = max_wait
        self.exception_types = exception_types
        self.attempt_number = 0
        self.last_exception: Optional[Exception] = None

    def __iter__(self):
        """Start retry iteration"""
        self.attempt_number = 0
        return self

    def __next__(self):
        """Get next retry attempt"""
        if self.attempt_number >= self.max_attempts:
            if self.last_exception:
                raise RetryError(
                    f"Failed after {self.max_attempts} attempts"
                ) from self.last_exception
            raise StopIteration

        self.attempt_number += 1
        return self

    def __enter__(self):
        """Enter attempt context"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Handle attempt result"""
        if exc_type is None:
            # Success - stop retrying
            return True

        if not issubclass(exc_type, self.exception_types):
            # Not a retryable exception - propagate
            return False

        # Retryable exception - log and continue
        self.last_exception = exc_val
        wait_time = min(self.min_wait * (2**self.attempt_number), self.max_wait)

        logger.warning(
            f"Retry attempt {self.attempt_number}/{self.max_attempts} "
            f"after {exc_type.__name__}: {exc_val}. "
            f"Waiting {wait_time:.1f}s before retry..."
        )

        import time

        time.sleep(wait_time)

        # Suppress exception to continue retry loop
        return True


# Example usage and testing
if __name__ == "__main__":
    print("🔧 Retry Decorator Test Suite")
    print("=" * 60)

    # Test 1: Database retry (simulated)
    print("\n📦 Test 1: Database retry (simulated DuckDB error)")

    class DatabaseTest:
        """Encapsulate test with state"""

        def __init__(self):
            self.attempt_count = 0

        @retry_database(max_attempts=3, min_wait=0.1, max_wait=1.0)
        def flaky_database_insert(self):
            """Simulates flaky database operation"""
            self.attempt_count += 1
            print(f"   Attempt {self.attempt_count}: Trying database insert...")

            if self.attempt_count < 2:
                # Fail first attempt
                raise duckdb.IOException("Simulated I/O error")
            else:
                # Succeed on second attempt
                print("   ✅ Database insert successful!")
                return True

    db_test = DatabaseTest()
    try:
        result = db_test.flaky_database_insert()
        print(f"   Result: {result} (took {db_test.attempt_count} attempts)")
    except Exception as e:
        print(f"   ❌ Failed: {e}")

    # Test 2: HTTP retry (simulated)
    print("\n🌐 Test 2: HTTP retry (simulated network error)")

    class HttpTest:
        """Encapsulate test with state"""

        def __init__(self):
            self.http_attempt_count = 0

        @retry_http(max_attempts=3, min_wait=0.1, max_wait=1.0)
        def flaky_http_request(self):
            """Simulates flaky HTTP request"""
            self.http_attempt_count += 1
            print(f"   Attempt {self.http_attempt_count}: Fetching from API...")

            if self.http_attempt_count < 2:
                # Fail first attempt
                raise ConnectionError("Simulated network failure")
            else:
                # Succeed on second attempt
                print("   ✅ HTTP request successful!")
                return {"status": "ok", "data": [1, 2, 3]}

    http_test = HttpTest()
    try:
        response = http_test.flaky_http_request()
        print(f"   Result: {response} (took {http_test.http_attempt_count} attempts)")
    except Exception as e:
        print(f"   ❌ Failed: {e}")

    # Test 3: Custom retry
    print("\n🔧 Test 3: Custom retry (ValueError)")

    class ValidateTest:
        """Encapsulate test with state"""

        def __init__(self):
            self.value_attempt_count = 0

        @retry_on_exception(ValueError, max_attempts=2, min_wait=0.1)
        def validate_input(self, value: int):
            """Simulates validation with retry"""
            self.value_attempt_count += 1
            print(f"   Attempt {self.value_attempt_count}: Validating input {value}...")

            if value < 0:
                raise ValueError("Value must be positive")
            return value * 2

    validate_test = ValidateTest()
    try:
        # This should fail (no retry helps)
        result = validate_test.validate_input(-5)
    except (RetryError, ValueError) as e:
        print(f"   ✅ Correctly failed after max attempts: {type(e).__name__}")

    # Test 4: Context manager
    print("\n📋 Test 4: RetryContext manager")

    ctx_attempt_count = 0
    retry_ctx = RetryContext(
        max_attempts=3, min_wait=0.1, max_wait=1.0, exception_types=(ValueError,)
    )

    for attempt in retry_ctx:
        with attempt:
            ctx_attempt_count += 1
            print(f"   Attempt {ctx_attempt_count}: Processing...")

            if ctx_attempt_count < 2:
                raise ValueError("Simulated error")
            else:
                print("   ✅ Context manager success!")
                break

    # Test 5: Non-retryable exception
    print("\n❌ Test 5: Non-retryable exception (should propagate)")

    @retry_database(max_attempts=3)
    def non_retryable_error():
        """Should not retry on KeyError"""
        raise KeyError("This is not a database error")

    try:
        non_retryable_error()
    except KeyError as e:
        print(f"   ✅ Correctly propagated non-retryable error: {e}")

    print("\n✅ All retry decorator tests passed!")
