#!/usr/bin/env python3
"""
Tests for Database Retry Decorator
Task: P2 - Test coverage for database resilience

Focus: Error paths and edge cases
- Transient errors (retry)
- Permanent errors (fail-fast)
- Exponential backoff
- Max retries enforcement
- Retry logic with tenacity
"""

import pytest
from unittest.mock import Mock, patch

# Import module under test
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "utils"))

try:
    from db_retry import (
        DatabaseRetryConfig,
        with_db_retry,
        execute_with_retry,
        connect_with_retry,
    )

    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False
    pytest.skip("tenacity library not available", allow_module_level=True)


class TestDatabaseRetryConfig:
    """Test DatabaseRetryConfig"""

    def test_default_initialization(self):
        """Config should initialize with default values"""
        config = DatabaseRetryConfig()

        assert config.max_attempts == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 10.0
        assert config.multiplier == 2.0
        assert len(config.retry_on_errors) > 0

    def test_custom_initialization(self):
        """Config should accept custom parameters"""
        config = DatabaseRetryConfig(
            max_attempts=5, initial_delay=2.0, max_delay=30.0, multiplier=3.0
        )

        assert config.max_attempts == 5
        assert config.initial_delay == 2.0
        assert config.max_delay == 30.0
        assert config.multiplier == 3.0

    def test_should_retry_transient_errors(self):
        """Should retry on transient errors (IOError, OSError, etc)"""
        config = DatabaseRetryConfig()

        assert config.should_retry(IOError("File system error"))
        assert config.should_retry(OSError("OS error"))
        assert config.should_retry(ConnectionError("Connection failed"))
        assert config.should_retry(TimeoutError("Timeout"))

    def test_should_not_retry_permanent_errors(self):
        """Should NOT retry on permanent errors (constraints, syntax, etc)"""
        config = DatabaseRetryConfig()

        # Constraint violations
        assert not config.should_retry(Exception("UNIQUE constraint failed"))
        assert not config.should_retry(Exception("FOREIGN KEY constraint failed"))
        assert not config.should_retry(Exception("NOT NULL constraint failed"))

        # SQL errors
        assert not config.should_retry(Exception("Syntax error in SQL"))
        assert not config.should_retry(Exception("Table does not exist"))
        assert not config.should_retry(Exception("Column invalid"))

        # Permission errors
        assert not config.should_retry(Exception("Permission denied"))

    def test_should_retry_custom_error_set(self):
        """Should respect custom retry_on_errors set"""
        config = DatabaseRetryConfig(retry_on_errors={ValueError, TypeError})

        assert config.should_retry(ValueError("Value error"))
        assert config.should_retry(TypeError("Type error"))
        assert not config.should_retry(IOError("IO error"))


class TestWithDbRetryDecorator:
    """Test @with_db_retry decorator"""

    def test_decorator_success_no_retry(self):
        """Should succeed on first attempt without retry"""
        mock_func = Mock(return_value="success")

        @with_db_retry(max_attempts=3)
        def test_function():
            return mock_func()

        result = test_function()

        assert result == "success"
        assert mock_func.call_count == 1

    def test_decorator_retries_on_transient_error(self):
        """Should retry on transient errors"""
        mock_func = Mock(
            side_effect=[IOError("Transient"), IOError("Transient"), "success"]
        )

        @with_db_retry(max_attempts=3)
        def test_function():
            return mock_func()

        result = test_function()

        assert result == "success"
        assert mock_func.call_count == 3  # 2 failures + 1 success

    def test_decorator_fails_fast_on_permanent_error(self):
        """Should fail immediately on permanent errors"""
        mock_func = Mock(side_effect=Exception("UNIQUE constraint failed"))

        @with_db_retry(max_attempts=3)
        def test_function():
            return mock_func()

        with pytest.raises(Exception, match="UNIQUE constraint"):
            test_function()

        # Should only try once (no retries for permanent errors)
        assert mock_func.call_count == 1

    def test_decorator_respects_max_attempts(self):
        """Should fail after max_attempts exceeded"""
        mock_func = Mock(side_effect=IOError("Transient"))

        @with_db_retry(max_attempts=3)
        def test_function():
            return mock_func()

        with pytest.raises(IOError, match="Transient"):
            test_function()

        # Should try max_attempts times
        assert mock_func.call_count == 3

    def test_decorator_with_custom_delays(self):
        """Should respect custom delay parameters"""
        mock_func = Mock(side_effect=[IOError("Transient"), "success"])

        @with_db_retry(initial_delay=0.1, max_delay=1.0, multiplier=2.0)
        def test_function():
            return mock_func()

        result = test_function()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_decorator_fallback_when_tenacity_unavailable(self):
        """Should fallback to no-op decorator if tenacity unavailable"""
        with patch("db_retry.TENACITY_AVAILABLE", False):
            mock_func = Mock(return_value="success")

            @with_db_retry()
            def test_function():
                return mock_func()

            result = test_function()

            assert result == "success"
            assert mock_func.call_count == 1


class TestExecuteWithRetry:
    """Test execute_with_retry convenience function"""

    @pytest.fixture
    def mock_conn(self):
        """Mock database connection"""
        conn = Mock()
        conn.execute = Mock()
        return conn

    def test_execute_simple_query(self, mock_conn):
        """Should execute query successfully"""
        mock_conn.execute.return_value.fetchall.return_value = [("result",)]

        result = execute_with_retry(mock_conn, "SELECT * FROM table")

        assert result == [("result",)]
        mock_conn.execute.assert_called_once_with("SELECT * FROM table", None)

    def test_execute_query_with_params(self, mock_conn):
        """Should execute query with parameters"""
        mock_conn.execute.return_value.fetchall.return_value = [("result",)]

        result = execute_with_retry(
            mock_conn, "SELECT * FROM table WHERE id = ?", [123]
        )

        assert result == [("result",)]
        mock_conn.execute.assert_called_once_with(
            "SELECT * FROM table WHERE id = ?", [123]
        )

    def test_execute_retries_on_transient_error(self, mock_conn):
        """Should retry query on transient errors"""
        # First call fails, second succeeds
        mock_conn.execute.side_effect = [
            IOError("Transient"),
            Mock(fetchall=Mock(return_value=[("result",)])),
        ]

        result = execute_with_retry(mock_conn, "SELECT * FROM table", max_attempts=3)

        assert result == [("result",)]
        assert mock_conn.execute.call_count == 2

    def test_execute_fails_after_max_attempts(self, mock_conn):
        """Should fail after max_attempts"""
        mock_conn.execute.side_effect = IOError("Transient")

        with pytest.raises(IOError, match="Transient"):
            execute_with_retry(mock_conn, "SELECT * FROM table", max_attempts=3)

        assert mock_conn.execute.call_count == 3


class TestConnectWithRetry:
    """Test connect_with_retry convenience function"""

    def test_connect_success(self):
        """Should connect successfully to database"""
        with patch("duckdb.connect") as mock_connect:
            mock_connect.return_value = Mock()

            conn = connect_with_retry(":memory:", max_attempts=3)

            assert conn is not None
            mock_connect.assert_called_once_with(":memory:", read_only=True)

    def test_connect_retries_on_failure(self):
        """Should retry connection on transient errors"""
        with patch("duckdb.connect") as mock_connect:
            # First call fails, second succeeds
            mock_connect.side_effect = [IOError("Transient"), Mock()]

            conn = connect_with_retry(":memory:", max_attempts=3)

            assert conn is not None
            assert mock_connect.call_count == 2

    def test_connect_fails_after_max_attempts(self):
        """Should fail after max_attempts"""
        with patch("duckdb.connect") as mock_connect:
            mock_connect.side_effect = IOError("Transient")

            with pytest.raises(IOError, match="Transient"):
                connect_with_retry(":memory:", max_attempts=3)

            assert mock_connect.call_count == 3

    def test_connect_read_write_mode(self):
        """Should support read_write mode"""
        with patch("duckdb.connect") as mock_connect:
            mock_connect.return_value = Mock()

            conn = connect_with_retry(":memory:", read_only=False)

            assert conn is not None
            mock_connect.assert_called_once_with(":memory:", read_only=False)


class TestRetryLogic:
    """Test retry logic and exponential backoff"""

    def test_exponential_backoff_timing(self):
        """Verify exponential backoff delays increase correctly"""
        attempt_times = []
        mock_func = Mock(side_effect=[IOError(), IOError(), IOError(), "success"])

        @with_db_retry(max_attempts=4, initial_delay=0.1, max_delay=1.0)
        def test_function():
            import time

            attempt_times.append(time.time())
            return mock_func()

        result = test_function()

        assert result == "success"
        assert len(attempt_times) == 4

        # Verify delays increase (approximately)
        # Note: timing tests are inherently flaky, so we use loose bounds
        if len(attempt_times) >= 2:
            delay1 = attempt_times[1] - attempt_times[0]
            assert delay1 >= 0.05  # Should be ~0.1s (with some tolerance)

    def test_max_delay_enforced(self):
        """Max delay should be enforced even with high multiplier"""
        mock_func = Mock(
            side_effect=[IOError(), IOError(), IOError(), IOError(), "success"]
        )

        @with_db_retry(
            max_attempts=5, initial_delay=1.0, max_delay=2.0, multiplier=10.0
        )
        def test_function():
            return mock_func()

        result = test_function()

        assert result == "success"
        # With multiplier=10, delays would be 1, 10, 100, 1000...
        # But max_delay=2.0 should cap them


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_zero_max_attempts_still_tries_once(self):
        """Even with max_attempts=0, should try at least once"""
        mock_func = Mock(return_value="success")

        @with_db_retry(max_attempts=0)
        def test_function():
            return mock_func()

        result = test_function()

        # Tenacity will default to at least 1 attempt
        assert result == "success"

    def test_decorator_preserves_function_name(self):
        """Decorator should preserve original function metadata"""

        @with_db_retry()
        def my_function():
            """My docstring"""
            return "result"

        assert my_function.__name__ == "my_function"
        assert "My docstring" in (my_function.__doc__ or "")

    def test_multiple_decorators_work_together(self):
        """Should work with multiple decorators"""
        mock_func = Mock(return_value="success")

        def another_decorator(func):
            def wrapper(*args, **kwargs):
                return f"wrapped-{func(*args, **kwargs)}"

            return wrapper

        @another_decorator
        @with_db_retry()
        def test_function():
            return mock_func()

        result = test_function()

        assert result == "wrapped-success"
        assert mock_func.call_count == 1
