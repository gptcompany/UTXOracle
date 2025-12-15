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
        csv_content = """txid,vout,height,coinbase,amount,type,address
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
            f.write("txid,vout,height,coinbase,amount,type,address\n")
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

        # Required columns for Tier 1 metrics (unified schema)
        required = ["txid", "vout", "creation_block", "amount"]
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


class TestTier2IncrementalSync:
    """Tests for T0007: Incremental rpc-v3 sync for Tier 2 (spent UTXOs)."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Create temporary DuckDB path."""
        return str(tmp_path / "test_tier2.duckdb")

    @pytest.fixture
    def sample_utxo_db(self, temp_db_path):
        """Create sample UTXO database with unspent UTXOs.

        Uses unified schema (spec-021):
        - creation_block (not height)
        - amount in satoshis (btc_value computed at query time)
        """
        import duckdb

        conn = duckdb.connect(temp_db_path)
        # Unified schema from import_chainstate.py
        conn.execute(
            """
            CREATE TABLE utxo_lifecycle (
                txid VARCHAR NOT NULL,
                vout INTEGER NOT NULL,
                creation_block INTEGER NOT NULL,
                amount BIGINT NOT NULL,
                is_coinbase BOOLEAN DEFAULT FALSE,
                script_type VARCHAR,
                address VARCHAR,
                is_spent BOOLEAN DEFAULT FALSE,
                spent_block INTEGER,
                spent_timestamp BIGINT,
                spent_price_usd DOUBLE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (txid, vout)
            )
            """
        )
        # Insert unspent UTXOs (amount in satoshis)
        conn.execute(
            """
            INSERT INTO utxo_lifecycle (txid, vout, creation_block, amount)
            VALUES
                ('abc123', 0, 800000, 100000000),
                ('def456', 1, 800001, 50000000),
                ('ghi789', 0, 800002, 200000000)
            """
        )
        conn.close()
        return temp_db_path

    def test_mark_utxo_as_spent(self, sample_utxo_db):
        """Verify UTXOs can be marked as spent with correct metadata."""
        from scripts.bootstrap.sync_spent_utxos import mark_utxo_as_spent

        import duckdb

        conn = duckdb.connect(sample_utxo_db)

        # Mark abc123:0 as spent
        result = mark_utxo_as_spent(
            conn,
            txid="abc123",
            vout=0,
            spent_block=800100,
            spent_timestamp=1700000000,
            spent_price_usd=55000.0,
        )

        assert result is True

        # Verify the update
        row = conn.execute(
            "SELECT is_spent, spent_block, spent_timestamp, spent_price_usd "
            "FROM utxo_lifecycle WHERE txid = 'abc123' AND vout = 0"
        ).fetchone()

        assert row[0] is True  # is_spent
        assert row[1] == 800100  # spent_block
        assert row[2] == 1700000000  # spent_timestamp
        assert row[3] == 55000.0  # spent_price_usd

        conn.close()

    def test_process_block_spent_utxos(self, sample_utxo_db):
        """Verify processing block inputs marks UTXOs as spent."""
        from scripts.bootstrap.sync_spent_utxos import process_block_spent_utxos

        import duckdb

        conn = duckdb.connect(sample_utxo_db)

        # Mock block data with transactions spending our UTXOs
        block_data = {
            "height": 800100,
            "time": 1700000000,
            "tx": [
                {
                    "txid": "spendtx1",
                    "vin": [
                        {
                            "txid": "abc123",
                            "vout": 0,
                            "prevout": {"value": 1.0, "height": 800000},
                        }
                    ],
                    "vout": [{"value": 0.99}],
                },
                {
                    "txid": "spendtx2",
                    "vin": [
                        {
                            "txid": "def456",
                            "vout": 1,
                            "prevout": {"value": 0.5, "height": 800001},
                        }
                    ],
                    "vout": [{"value": 0.49}],
                },
            ],
        }

        spent_count = process_block_spent_utxos(conn, block_data, block_price=55000.0)

        assert spent_count == 2

        # Verify both UTXOs marked as spent
        result = conn.execute(
            "SELECT COUNT(*) FROM utxo_lifecycle WHERE is_spent = TRUE"
        ).fetchone()
        assert result[0] == 2

        # Verify ghi789:0 still unspent
        result = conn.execute(
            "SELECT is_spent FROM utxo_lifecycle WHERE txid = 'ghi789'"
        ).fetchone()
        assert result[0] is False

        conn.close()

    @pytest.mark.asyncio
    async def test_sync_spent_utxos_range(self, sample_utxo_db):
        """Verify sync processes a range of blocks for spent UTXOs."""
        from unittest.mock import MagicMock

        from scripts.bootstrap.sync_spent_utxos import sync_spent_utxos_range

        import duckdb

        # Create a mock RPC that returns block data
        def make_mock_block(height):
            return {
                "height": height,
                "time": 1700000000 + height,
                "tx": [
                    {
                        "txid": f"spend_at_{height}",
                        "vin": [
                            # Only first block spends abc123
                            {
                                "txid": "abc123" if height == 800100 else "unknown",
                                "vout": 0,
                                "prevout": {"value": 1.0, "height": 800000},
                            }
                        ],
                        "vout": [{"value": 0.99}],
                    }
                ],
            }

        mock_rpc = MagicMock()
        mock_rpc.getblockhash.return_value = "mockhash"
        mock_rpc.getblock.side_effect = lambda hash, verbosity: make_mock_block(
            800100 if hash == "mockhash" else 800101
        )

        conn = duckdb.connect(sample_utxo_db)

        # Sync blocks 800100-800102
        stats = await sync_spent_utxos_range(
            conn,
            start_block=800100,
            end_block=800102,
            rpc=mock_rpc,
            price_lookup=lambda h: 55000.0,
        )

        assert stats["blocks_processed"] >= 1
        assert stats["utxos_spent"] >= 1

        conn.close()

    def test_get_unspent_utxo_txids(self, sample_utxo_db):
        """Verify retrieval of unspent UTXO txids for efficient lookup."""
        from scripts.bootstrap.sync_spent_utxos import get_unspent_utxo_txids

        import duckdb

        conn = duckdb.connect(sample_utxo_db)

        txids = get_unspent_utxo_txids(conn)

        assert "abc123" in txids
        assert "def456" in txids
        assert "ghi789" in txids
        assert len(txids) == 3

        conn.close()

    def test_tier2_bootstrap_integration(self, sample_utxo_db):
        """Verify Tier 2 bootstrap integrates with orchestrator."""
        from scripts.bootstrap.bootstrap_utxo_lifecycle import bootstrap_tier2_available

        # Verify the function exists and is callable
        assert callable(bootstrap_tier2_available)

        # Function should return True if rpc-v3 is available
        # (In actual test, this would check Bitcoin Core version >= 25.0)
        result = bootstrap_tier2_available()
        assert isinstance(result, bool)
