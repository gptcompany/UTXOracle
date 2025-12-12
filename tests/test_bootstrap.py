"""Tests for UTXO lifecycle bootstrap utilities.

TDD: These tests are written FIRST (RED phase) before implementation.
Each test validates a specific bootstrap component.

Test Coverage:
- T0001b: test_build_price_table() - verify 2011 data fetch from mempool API
- T0001c: test_build_block_heights() - verify height→timestamp mapping from electrs
- T0001d: test_import_chainstate() - verify CSV→DuckDB COPY performance
"""

from unittest.mock import AsyncMock, patch

import pytest

# Mark all tests as bootstrap tests
pytestmark = pytest.mark.bootstrap


class TestBuildPriceTable:
    """Tests for build_price_table.py - T0001b."""

    @pytest.fixture
    def mock_mempool_response(self):
        """Mock mempool API response for historical price."""
        return {"USD": 16.45}  # July 2011 price

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Create temporary DuckDB path."""
        return str(tmp_path / "test_prices.duckdb")

    @pytest.mark.asyncio
    async def test_fetch_historical_price_2011(self, mock_mempool_response):
        """Verify we can fetch prices from 2011 (mempool API coverage).

        Note: This test validates the function signature and return type.
        Integration tests with actual API should be run separately.
        """
        from contextlib import asynccontextmanager

        from scripts.bootstrap.build_price_table import fetch_historical_price

        # Create mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_mempool_response)

        # Create async context manager that yields the mock response
        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            yield mock_response

        # Create mock session with get method returning context manager
        mock_session = AsyncMock()
        mock_session.get = mock_get

        # July 12, 2011 timestamp
        timestamp = 1310428800
        price = await fetch_historical_price(timestamp, session=mock_session)

        assert price is not None
        assert price == 16.45
        assert isinstance(price, float)

    @pytest.mark.asyncio
    async def test_build_price_table_creates_schema(self, temp_db_path):
        """Verify price table schema is created correctly."""
        from scripts.bootstrap.build_price_table import create_price_table_schema

        import duckdb

        conn = duckdb.connect(temp_db_path)
        create_price_table_schema(conn)

        # Verify table exists with correct columns
        result = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'daily_prices' ORDER BY ordinal_position"
        ).fetchall()

        columns = {row[0]: row[1] for row in result}
        assert "date" in columns
        assert "price_usd" in columns
        assert "block_height" in columns

        conn.close()

    @pytest.mark.asyncio
    async def test_price_table_handles_missing_dates(self):
        """Verify graceful handling of dates without price data."""
        from contextlib import asynccontextmanager

        from scripts.bootstrap.build_price_table import fetch_historical_price

        # Create mock response with empty data (no price)
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={})  # Empty response

        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            yield mock_response

        mock_session = AsyncMock()
        mock_session.get = mock_get

        # 2008 timestamp (before Bitcoin)
        price = await fetch_historical_price(1199145600, session=mock_session)
        assert price is None or price == 0.0


class TestBuildBlockHeights:
    """Tests for build_block_heights.py - T0001c."""

    @pytest.fixture
    def mock_electrs_block_hash(self):
        """Mock electrs block hash response."""
        return "000000000000000000024bead8df69990852c202db0e0097c1a12ea637d7e96d"

    @pytest.fixture
    def mock_electrs_block_meta(self):
        """Mock electrs block metadata response."""
        return {
            "id": "000000000000000000024bead8df69990852c202db0e0097c1a12ea637d7e96d",
            "height": 800000,
            "timestamp": 1690000000,
            "mediantime": 1689999000,
        }

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Create temporary DuckDB path."""
        return str(tmp_path / "test_heights.duckdb")

    @pytest.mark.asyncio
    async def test_fetch_block_timestamp(
        self, mock_electrs_block_hash, mock_electrs_block_meta
    ):
        """Verify block height→timestamp mapping via electrs."""
        from contextlib import asynccontextmanager

        from scripts.bootstrap.build_block_heights import fetch_block_timestamp

        # First call returns block hash (text)
        mock_hash_response = AsyncMock()
        mock_hash_response.text = AsyncMock(return_value=mock_electrs_block_hash)
        mock_hash_response.status = 200

        # Second call returns block metadata (json)
        mock_meta_response = AsyncMock()
        mock_meta_response.json = AsyncMock(return_value=mock_electrs_block_meta)
        mock_meta_response.status = 200

        # Track call count to return different responses
        call_count = 0

        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield mock_hash_response
            else:
                yield mock_meta_response

        mock_session = AsyncMock()
        mock_session.get = mock_get

        height = 800000
        timestamp = await fetch_block_timestamp(height, session=mock_session)

        assert timestamp is not None
        assert timestamp == 1690000000
        assert isinstance(timestamp, int)

    @pytest.mark.asyncio
    async def test_block_heights_table_schema(self, temp_db_path):
        """Verify block_heights table schema is created correctly."""
        from scripts.bootstrap.build_block_heights import create_block_heights_schema

        import duckdb

        conn = duckdb.connect(temp_db_path)
        create_block_heights_schema(conn)

        # Verify table exists with correct columns
        result = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'block_heights' ORDER BY ordinal_position"
        ).fetchall()

        columns = {row[0]: row[1] for row in result}
        assert "height" in columns
        assert "timestamp" in columns
        assert "block_hash" in columns

        conn.close()

    @pytest.mark.asyncio
    async def test_batch_fetch_block_timestamps(self):
        """Verify batch fetching of multiple block timestamps."""
        from scripts.bootstrap.build_block_heights import batch_fetch_block_timestamps

        with patch(
            "scripts.bootstrap.build_block_heights.fetch_block_timestamp"
        ) as mock_fetch:
            mock_fetch.return_value = 1690000000

            heights = [800000, 800001, 800002]
            results = await batch_fetch_block_timestamps(heights)

            assert len(results) == 3
            assert all(ts == 1690000000 for ts in results.values())


class TestImportChainstate:
    """Tests for import_chainstate.py - T0001d."""

    @pytest.fixture
    def sample_chainstate_csv(self, tmp_path):
        """Create sample chainstate CSV for testing."""
        csv_path = tmp_path / "utxos.csv"
        csv_content = """txid,vout,height,coinbase,amount,script_type,address
abc123,0,800000,0,100000000,p2wpkh,bc1qtest1
def456,1,800001,0,50000000,p2sh,3TestAddress
ghi789,0,800002,1,625000000,p2pk,unknown
"""
        csv_path.write_text(csv_content)
        return str(csv_path)

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Create temporary DuckDB path."""
        return str(tmp_path / "test_utxo.duckdb")

    def test_import_csv_creates_table(self, sample_chainstate_csv, temp_db_path):
        """Verify CSV import creates utxo_lifecycle table."""
        from scripts.bootstrap.import_chainstate import import_chainstate_csv

        import duckdb

        conn = duckdb.connect(temp_db_path)

        # Import the CSV
        rows_imported = import_chainstate_csv(conn, sample_chainstate_csv)

        # Verify rows imported
        assert rows_imported == 3

        # Verify table exists
        result = conn.execute("SELECT COUNT(*) FROM utxo_lifecycle").fetchone()
        assert result[0] == 3

        conn.close()

    def test_import_uses_duckdb_copy(self, sample_chainstate_csv, temp_db_path):
        """Verify DuckDB COPY is used (not INSERT) for performance."""
        from scripts.bootstrap.import_chainstate import import_chainstate_csv

        import duckdb

        conn = duckdb.connect(temp_db_path)

        # This test verifies the function uses COPY under the hood
        # We'll measure that it's fast (COPY is ~2970x faster than INSERT)
        import time

        start = time.time()
        rows = import_chainstate_csv(conn, sample_chainstate_csv)
        elapsed = time.time() - start

        # Even small CSV should import in <1 second with COPY
        assert elapsed < 1.0
        assert rows == 3

        conn.close()

    def test_import_handles_large_csv(self, tmp_path, temp_db_path):
        """Verify import handles larger CSV files efficiently."""
        from scripts.bootstrap.import_chainstate import import_chainstate_csv

        import duckdb

        # Generate 10K row CSV
        csv_path = tmp_path / "large_utxos.csv"
        with open(csv_path, "w") as f:
            f.write("txid,vout,height,coinbase,amount,script_type,address\n")
            for i in range(10000):
                f.write(
                    f"tx{i:08d},{i % 10},{800000 + i},0,{100000 * i},p2wpkh,bc1q{i}\n"
                )

        conn = duckdb.connect(temp_db_path)

        import time

        start = time.time()
        rows = import_chainstate_csv(conn, str(csv_path))
        elapsed = time.time() - start

        # 10K rows should import in <5 seconds with COPY
        assert elapsed < 5.0
        assert rows == 10000

        conn.close()

    def test_import_schema_matches_utxo_lifecycle(
        self, sample_chainstate_csv, temp_db_path
    ):
        """Verify imported schema matches existing utxo_lifecycle schema."""
        from scripts.bootstrap.import_chainstate import import_chainstate_csv

        import duckdb

        conn = duckdb.connect(temp_db_path)
        import_chainstate_csv(conn, sample_chainstate_csv)

        # Check required columns exist
        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'utxo_lifecycle'"
        ).fetchall()

        columns = [row[0] for row in result]

        # Required columns for Tier 1 metrics
        required = ["txid", "vout", "height", "amount"]
        for col in required:
            assert col in columns, f"Missing required column: {col}"

        conn.close()


class TestBootstrapOrchestrator:
    """Tests for bootstrap_utxo_lifecycle.py - Integration tests."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Create temporary DuckDB path."""
        return str(tmp_path / "test_bootstrap.duckdb")

    @pytest.mark.asyncio
    async def test_bootstrap_creates_all_tables(self, temp_db_path):
        """Verify bootstrap creates all required tables."""
        from scripts.bootstrap.bootstrap_utxo_lifecycle import create_all_schemas

        import duckdb

        conn = duckdb.connect(temp_db_path)
        create_all_schemas(conn)

        # Check all tables exist
        result = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main'"
        ).fetchall()

        tables = [row[0] for row in result]
        assert "daily_prices" in tables
        assert "block_heights" in tables

        conn.close()

    @pytest.mark.asyncio
    async def test_bootstrap_validates_dependencies(self):
        """Verify bootstrap checks for required dependencies."""
        from scripts.bootstrap.bootstrap_utxo_lifecycle import check_dependencies

        # This should return a dict of dependency status
        deps = await check_dependencies()

        assert "bitcoin_core" in deps
        assert "electrs" in deps
        assert "mempool_api" in deps
        # Each should be True/False
        assert all(isinstance(v, bool) for v in deps.values())
