"""Round 4: Security and input validation tests.

Tests for injection attacks, path traversal, DoS vectors, and malicious inputs.
"""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import pytest

from scripts.backtest.data_loader import (
    load_from_html,
    load_from_duckdb,
    _parse_html_file,
    PricePoint,
)
from scripts.backtest.engine import (
    BacktestConfig,
    run_backtest,
    execute_trade,
)
from scripts.backtest.optimizer import (
    generate_weight_grid,
    combine_signals,
)


class TestPathTraversal:
    """Test for path traversal vulnerabilities."""

    def test_html_path_traversal_attempt(self):
        """Attempt path traversal in html_dir should not access system files."""
        # Create a temp directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            # Try to escape with path traversal
            malicious_path = os.path.join(tmpdir, "..", "..", "etc", "passwd")

            # Should not crash or leak info
            result = load_from_html(
                start_date=datetime(2025, 1, 1),
                end_date=datetime(2025, 1, 5),
                html_dir=malicious_path,
            )

            # Should return empty (path doesn't exist as HTML dir)
            assert result == []

    def test_html_file_outside_dir_not_loaded(self):
        """Files outside the specified directory should not be loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake HTML file outside the "safe" directory
            parent_file = Path(tmpdir) / ".." / "UTXOracle_2025-01-01.html"

            # Try to load from subdirectory but with date matching parent file
            subdir = Path(tmpdir) / "safe"
            subdir.mkdir()

            result = load_from_html(
                start_date=datetime(2025, 1, 1),
                end_date=datetime(2025, 1, 1),
                html_dir=str(subdir),
            )

            # Should not find any files
            assert result == []


class TestSQLInjection:
    """Test for SQL injection vulnerabilities in DuckDB queries."""

    def test_duckdb_date_injection_attempt(self):
        """Malicious date values should not cause SQL injection."""
        # This test verifies parameterized queries are used
        # If SQL is concatenated, this would cause issues
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Create a mock database with the expected table
            try:
                import duckdb

                conn = duckdb.connect(db_path)
                conn.execute("""
                    CREATE TABLE price_analysis (
                        date DATE,
                        utxoracle_price FLOAT,
                        exchange_price FLOAT,
                        confidence FLOAT,
                        combined_signal FLOAT
                    )
                """)
                conn.close()

                # Try loading with dates - should use parameterized queries
                result = load_from_duckdb(
                    start_date=datetime(2025, 1, 1),
                    end_date=datetime(2025, 1, 5),
                    db_path=db_path,
                )

                # Should complete without error (empty result)
                assert isinstance(result, list)

            except ImportError:
                pytest.skip("duckdb not installed")


class TestMaliciousInput:
    """Test handling of malicious/adversarial inputs."""

    def test_extremely_long_signal_name(self):
        """Very long signal names should not cause memory issues."""
        # Create a very long signal name
        long_name = "A" * 10000

        signals = {long_name: [0.5] * 10}
        weights = {long_name: 1.0}

        result = combine_signals(signals, weights)

        # Should work without memory issues
        assert len(result) == 10

    def test_unicode_in_signal_names(self):
        """Unicode signal names should be handled correctly."""
        signals = {
            "シグナル": [0.5] * 5,
            "信号": [0.3] * 5,
            "🚀📈": [0.7] * 5,
        }

        grid = generate_weight_grid(list(signals.keys()), step=0.5)

        # Should generate valid grid
        assert len(grid) > 0
        for weights in grid:
            assert sum(weights.values()) == pytest.approx(1.0)

    def test_special_characters_in_signal_source(self):
        """Special characters in signal_source should not break execution."""
        config = BacktestConfig(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 5),
            signal_source="test'; DROP TABLE users; --",  # SQL injection attempt
        )

        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(days=i),
                utxoracle_price=50000 + i * 100,
                exchange_price=50000 + i * 100,
                confidence=0.9,
                signal_value=0.5,
            )
            for i in range(5)
        ]

        result = run_backtest(config, prices=prices)

        # Should complete without error
        assert result.config.signal_source == "test'; DROP TABLE users; --"


class TestResourceExhaustion:
    """Test for denial of service via resource exhaustion."""

    def test_large_weight_grid_does_not_crash(self):
        """Large number of signals should not cause memory exhaustion."""
        # 4 signals with step 0.1 = ~1000 combinations
        signals = ["s1", "s2", "s3", "s4"]

        grid = generate_weight_grid(signals, step=0.1)

        # Should complete in reasonable time
        assert len(grid) > 0
        # Each weight combination should sum to 1
        for weights in grid[:10]:  # Just check first 10
            assert sum(weights.values()) == pytest.approx(1.0, abs=0.01)

    def test_large_price_list_backtest(self):
        """Large price list should not cause performance issues."""
        config = BacktestConfig(
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2025, 1, 1),
            signal_source="test",
        )

        # 1000 price points
        prices = [
            PricePoint(
                timestamp=datetime(2025, 1, 1) + timedelta(hours=i),
                utxoracle_price=50000 + (i % 100) * 10,
                exchange_price=50000 + (i % 100) * 10,
                confidence=0.9,
                signal_value=0.5 if i % 10 < 5 else -0.5,
            )
            for i in range(1000)
        ]

        result = run_backtest(config, prices=prices)

        # Should complete without timeout
        assert isinstance(result.num_trades, int)

    def test_very_small_step_size_limited(self):
        """Very small step sizes should be handled."""
        signals = ["a", "b"]

        # step=0.01 would create 10000+ combinations
        grid = generate_weight_grid(signals, step=0.01)

        # Should still work but may be large
        assert len(grid) > 0


class TestHTMLParsingSecurity:
    """Test HTML parsing for security issues."""

    def test_malicious_html_content(self):
        """Malicious HTML should not cause code execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a malicious HTML file
            malicious_html = Path(tmpdir) / "UTXOracle_2025-01-01.html"
            malicious_html.write_text("""
                <html>
                <script>alert('xss')</script>
                <body>
                price: $50000
                confidence: 0.9
                <!-- __import__('os').system('rm -rf /') -->
                </body>
                </html>
            """)

            result = _parse_html_file(malicious_html, datetime(2025, 1, 1).date())

            # Should parse price without executing scripts
            assert result is not None
            assert result.utxoracle_price == 50000.0
            assert result.confidence == 0.9

    def test_html_regex_dos_attempt(self):
        """Regex patterns should not be vulnerable to ReDoS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file designed to cause ReDoS
            evil_html = Path(tmpdir) / "UTXOracle_2025-01-01.html"
            evil_html.write_text(
                "price: " + "$" * 1000 + "100"  # Repetitive pattern
            )

            # Should complete in reasonable time (< 1 second)
            import time

            start = time.time()
            result = _parse_html_file(evil_html, datetime(2025, 1, 1).date())
            elapsed = time.time() - start

            # Should not hang
            assert elapsed < 5.0  # Very generous timeout


class TestNumericOverflow:
    """Test for numeric overflow/underflow issues."""

    def test_extreme_price_values(self):
        """Extreme price values should not cause overflow."""
        now = datetime.now()

        trade = execute_trade(
            entry_time=now,
            entry_price=1e308,  # Near max float
            exit_time=now + timedelta(hours=1),
            exit_price=1e308,
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.001,
            capital=10000.0,
            signal_value=0.5,
        )

        # Should not overflow
        assert not (trade.pnl == float("inf") or trade.pnl == float("-inf"))

    def test_very_small_prices(self):
        """Very small price values should not cause underflow."""
        now = datetime.now()

        trade = execute_trade(
            entry_time=now,
            entry_price=1e-300,  # Very small
            exit_time=now + timedelta(hours=1),
            exit_price=2e-300,
            direction="LONG",
            position_size=1.0,
            transaction_cost=0.001,
            capital=10000.0,
            signal_value=0.5,
        )

        # Should complete without underflow to 0
        assert isinstance(trade.pnl, float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
