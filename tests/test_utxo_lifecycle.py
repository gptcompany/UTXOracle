"""Tests for UTXO Lifecycle Engine.

Spec: spec-017
TDD approach: RED phase tests first, then GREEN implementation.
"""

from __future__ import annotations

import pytest
from datetime import datetime
from pathlib import Path

import duckdb

# Import modules under test
from scripts.metrics.utxo_lifecycle import (
    init_schema,
    init_indexes,
    save_utxo,
    load_utxo,
    mark_utxo_spent,
    get_supply_by_cohort,
    get_sth_lth_supply,
    process_block_outputs,
    process_block_inputs,
    process_block_utxos,
    prune_old_utxos,
    get_sync_state,
    update_sync_state,
    BLOCKS_PER_DAY,
)
from scripts.models.metrics_models import (
    UTXOLifecycle,
    AgeCohortsConfig,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """Create a temporary DuckDB database for testing."""
    db_path = tmp_path / "test_utxo.duckdb"
    conn = duckdb.connect(str(db_path))
    init_schema(conn)
    init_indexes(conn)
    return conn


@pytest.fixture
def sample_utxo() -> UTXOLifecycle:
    """Create a sample UTXO for testing."""
    return UTXOLifecycle(
        outpoint="abc123:0",
        txid="abc123",
        vout_index=0,
        creation_block=850000,
        creation_timestamp=datetime(2024, 1, 15, 12, 0, 0),
        creation_price_usd=50000.0,
        btc_value=1.5,
        realized_value_usd=75000.0,
        is_coinbase=False,
        price_source="utxoracle",
    )


@pytest.fixture
def sample_block_data() -> dict:
    """Create sample block data for testing."""
    return {
        "height": 850000,
        "time": 1705320000,  # 2024-01-15 12:00:00 UTC
        "tx": [
            {
                "txid": "coinbase_tx_001",
                "vout": [{"n": 0, "value": 6.25}],  # Coinbase
            },
            {
                "txid": "regular_tx_001",
                "vin": [{"txid": "prev_tx_001", "vout": 0}],
                "vout": [
                    {"n": 0, "value": 1.0},
                    {"n": 1, "value": 0.5},
                ],
            },
            {
                "txid": "regular_tx_002",
                "vin": [{"txid": "prev_tx_002", "vout": 1}],
                "vout": [
                    {"n": 0, "value": 2.0},
                    {"n": 1, "value": 0.0},  # OP_RETURN, should be skipped
                ],
            },
        ],
    }


@pytest.fixture
def age_config() -> AgeCohortsConfig:
    """Create age cohort configuration for testing."""
    return AgeCohortsConfig()


# =============================================================================
# Phase 2: Storage Operation Tests (T015a-T015c)
# =============================================================================


class TestStorageOperations:
    """Test storage operations for UTXO lifecycle."""

    def test_utxo_save_and_load(
        self, temp_db: duckdb.DuckDBPyConnection, sample_utxo: UTXOLifecycle
    ):
        """T015a: Test saving and loading a UTXO record."""
        # Save UTXO
        save_utxo(temp_db, sample_utxo)

        # Load UTXO
        loaded = load_utxo(temp_db, sample_utxo.outpoint)

        assert loaded is not None
        assert loaded.outpoint == sample_utxo.outpoint
        assert loaded.txid == sample_utxo.txid
        assert loaded.vout_index == sample_utxo.vout_index
        assert loaded.creation_block == sample_utxo.creation_block
        assert loaded.btc_value == sample_utxo.btc_value
        assert loaded.realized_value_usd == sample_utxo.realized_value_usd
        assert loaded.is_spent is False

    def test_utxo_index_lookup_performance(self, temp_db: duckdb.DuckDBPyConnection):
        """T015b: Test that indexes improve lookup performance."""
        # Create 1000 UTXOs
        for i in range(1000):
            utxo = UTXOLifecycle(
                outpoint=f"tx{i}:0",
                txid=f"tx{i}",
                vout_index=0,
                creation_block=850000 + i,
                creation_timestamp=datetime.now(),
                creation_price_usd=50000.0,
                btc_value=0.1,
                realized_value_usd=5000.0,
            )
            save_utxo(temp_db, utxo)

        # Query by creation_block (should use index)
        import time

        start = time.perf_counter()
        result = temp_db.execute(
            "SELECT COUNT(*) FROM utxo_lifecycle WHERE creation_block > 850500"
        ).fetchone()
        elapsed = time.perf_counter() - start

        assert result[0] == 499  # UTXOs from blocks 850501-850999
        assert elapsed < 1.0  # Should be fast with index

    def test_utxo_pruning_removes_old_spent(self, temp_db: duckdb.DuckDBPyConnection):
        """T015c: Test that pruning removes old spent UTXOs."""
        # Create and mark some UTXOs as spent at different blocks
        for i in range(10):
            utxo = UTXOLifecycle(
                outpoint=f"prune_tx{i}:0",
                txid=f"prune_tx{i}",
                vout_index=0,
                creation_block=800000 + i * 1000,
                creation_timestamp=datetime.now(),
                creation_price_usd=50000.0,
                btc_value=1.0,
                realized_value_usd=50000.0,
                is_spent=True,
                spent_block=810000 + i * 1000,
            )
            save_utxo(temp_db, utxo)

        # Count before prune
        before = temp_db.execute("SELECT COUNT(*) FROM utxo_lifecycle").fetchone()[0]
        assert before == 10

        # Prune UTXOs spent before block 815000
        current_block = 850000
        retention_blocks = 35000  # Keep only last 35000 blocks
        pruned = prune_old_utxos(temp_db, retention_blocks, current_block)

        # UTXOs spent at 810000, 811000, 812000, 813000, 814000 should be pruned
        # Cutoff is 850000 - 35000 = 815000
        assert pruned == 5

        after = temp_db.execute("SELECT COUNT(*) FROM utxo_lifecycle").fetchone()[0]
        assert after == 5


# =============================================================================
# Phase 3: User Story 1 - UTXO Creation Tracking Tests (T016-T018)
# =============================================================================


class TestUTXOCreationTracking:
    """Test UTXO creation tracking functionality."""

    def test_utxo_creation_tracking(
        self, temp_db: duckdb.DuckDBPyConnection, sample_utxo: UTXOLifecycle
    ):
        """T016: Test that UTXO creation is properly tracked."""
        save_utxo(temp_db, sample_utxo)
        loaded = load_utxo(temp_db, sample_utxo.outpoint)

        assert loaded is not None
        assert loaded.creation_block == 850000
        assert loaded.creation_price_usd == 50000.0
        assert loaded.btc_value == 1.5
        assert loaded.is_spent is False

    def test_utxo_realized_value_calculation(self, sample_utxo: UTXOLifecycle):
        """T017: Test realized value calculation."""
        # realized_value = btc_value × creation_price
        expected_realized = 1.5 * 50000.0  # 75000
        assert sample_utxo.realized_value_usd == expected_realized

    def test_process_block_outputs(
        self, temp_db: duckdb.DuckDBPyConnection, sample_block_data: dict
    ):
        """T018: Test processing block outputs creates UTXOs correctly."""
        block_price = 50000.0
        created = process_block_outputs(temp_db, sample_block_data, block_price)

        # Should create 4 UTXOs (1 coinbase + 2 from tx1 + 1 from tx2, skipping 0-value)
        assert len(created) == 4

        # Verify coinbase UTXO
        coinbase_utxo = next(u for u in created if u.is_coinbase)
        assert coinbase_utxo.btc_value == 6.25
        assert coinbase_utxo.is_coinbase is True

        # Verify regular UTXO
        regular_utxo = next(
            u for u in created if u.txid == "regular_tx_001" and u.vout_index == 0
        )
        assert regular_utxo.btc_value == 1.0
        assert regular_utxo.realized_value_usd == 50000.0
        assert regular_utxo.is_coinbase is False


# =============================================================================
# Phase 3: Edge Case Tests (T018a-T018d)
# =============================================================================


class TestEdgeCases:
    """Test edge cases for UTXO lifecycle."""

    def test_unknown_creation_price_fallback(self, temp_db: duckdb.DuckDBPyConnection):
        """T018a: Test fallback when creation price is from mempool.space."""
        utxo = UTXOLifecycle(
            outpoint="fallback_tx:0",
            txid="fallback_tx",
            vout_index=0,
            creation_block=800000,
            creation_timestamp=datetime(2023, 1, 1, 0, 0, 0),
            creation_price_usd=45000.0,
            btc_value=1.0,
            realized_value_usd=45000.0,
            price_source="mempool",  # Fallback source
        )
        save_utxo(temp_db, utxo)
        loaded = load_utxo(temp_db, utxo.outpoint)

        assert loaded is not None
        assert loaded.price_source == "mempool"

    def test_coinbase_utxo_handling(self, temp_db: duckdb.DuckDBPyConnection):
        """T018b: Test coinbase UTXO is marked correctly."""
        utxo = UTXOLifecycle(
            outpoint="coinbase_tx:0",
            txid="coinbase_tx",
            vout_index=0,
            creation_block=850000,
            creation_timestamp=datetime.now(),
            creation_price_usd=50000.0,
            btc_value=6.25,  # Block subsidy
            realized_value_usd=312500.0,
            is_coinbase=True,
        )
        save_utxo(temp_db, utxo)
        loaded = load_utxo(temp_db, utxo.outpoint)

        assert loaded is not None
        assert loaded.is_coinbase is True
        assert loaded.btc_value == 6.25

    def test_reorg_invalidation(self, temp_db: duckdb.DuckDBPyConnection):
        """T018c: Test reorg handling - UTXOs should be removable."""
        # Create a UTXO that will be invalidated by reorg
        utxo = UTXOLifecycle(
            outpoint="reorg_tx:0",
            txid="reorg_tx",
            vout_index=0,
            creation_block=850100,
            creation_timestamp=datetime.now(),
            creation_price_usd=50000.0,
            btc_value=1.0,
            realized_value_usd=50000.0,
        )
        save_utxo(temp_db, utxo)

        # Simulate reorg by deleting the UTXO
        temp_db.execute("DELETE FROM utxo_lifecycle WHERE creation_block >= 850100")

        # Verify UTXO is gone
        loaded = load_utxo(temp_db, utxo.outpoint)
        assert loaded is None

    def test_storage_limit_exceeded_triggers_prune(
        self, temp_db: duckdb.DuckDBPyConnection
    ):
        """T018d: Test that storage management works with retention period."""
        # Create old spent UTXOs that should be pruned
        for i in range(100):
            utxo = UTXOLifecycle(
                outpoint=f"old_spent_{i}:0",
                txid=f"old_spent_{i}",
                vout_index=0,
                creation_block=700000,
                creation_timestamp=datetime.now(),
                creation_price_usd=30000.0,
                btc_value=0.1,
                realized_value_usd=3000.0,
                is_spent=True,
                spent_block=700100,
            )
            save_utxo(temp_db, utxo)

        # 6-month retention in blocks
        retention_blocks = 180 * BLOCKS_PER_DAY
        current_block = 850000

        pruned = prune_old_utxos(temp_db, retention_blocks, current_block)
        assert pruned == 100  # All old UTXOs should be pruned


# =============================================================================
# Phase 4: User Story 2 - UTXO Spending Tracking Tests (T024-T026)
# =============================================================================


class TestUTXOSpendingTracking:
    """Test UTXO spending tracking functionality."""

    def test_utxo_spending_tracking(
        self,
        temp_db: duckdb.DuckDBPyConnection,
        sample_utxo: UTXOLifecycle,
        age_config: AgeCohortsConfig,
    ):
        """T024: Test that UTXO spending is properly tracked."""
        save_utxo(temp_db, sample_utxo)

        # Mark as spent
        spent_block = 860000
        spent_time = datetime(2024, 3, 15, 12, 0, 0)
        spent_price = 100000.0

        sopr = mark_utxo_spent(
            temp_db,
            sample_utxo.outpoint,
            spent_block,
            spent_time,
            spent_price,
            "spending_tx_001",
            age_config,
        )

        loaded = load_utxo(temp_db, sample_utxo.outpoint)
        assert loaded is not None
        assert loaded.is_spent is True
        assert loaded.spent_block == spent_block
        assert loaded.spending_txid == "spending_tx_001"

    def test_sopr_calculation_on_spend(
        self,
        temp_db: duckdb.DuckDBPyConnection,
        sample_utxo: UTXOLifecycle,
        age_config: AgeCohortsConfig,
    ):
        """T025: Test SOPR calculation when UTXO is spent."""
        save_utxo(temp_db, sample_utxo)

        # SOPR = spent_price / creation_price = 100000 / 50000 = 2.0
        sopr = mark_utxo_spent(
            temp_db,
            sample_utxo.outpoint,
            860000,
            datetime.now(),
            100000.0,
            "spending_tx",
            age_config,
        )

        assert sopr == pytest.approx(2.0)

    def test_process_block_inputs(
        self,
        temp_db: duckdb.DuckDBPyConnection,
        sample_block_data: dict,
        age_config: AgeCohortsConfig,
    ):
        """T026: Test processing block inputs marks UTXOs as spent."""
        # First, create the UTXOs that will be spent
        prev_utxo_1 = UTXOLifecycle(
            outpoint="prev_tx_001:0",
            txid="prev_tx_001",
            vout_index=0,
            creation_block=840000,
            creation_timestamp=datetime(2024, 1, 1, 0, 0, 0),
            creation_price_usd=40000.0,
            btc_value=1.5,
            realized_value_usd=60000.0,
        )
        prev_utxo_2 = UTXOLifecycle(
            outpoint="prev_tx_002:1",
            txid="prev_tx_002",
            vout_index=1,
            creation_block=845000,
            creation_timestamp=datetime(2024, 1, 10, 0, 0, 0),
            creation_price_usd=42000.0,
            btc_value=2.5,
            realized_value_usd=105000.0,
        )
        save_utxo(temp_db, prev_utxo_1)
        save_utxo(temp_db, prev_utxo_2)

        # Process inputs
        block_price = 50000.0
        spent = process_block_inputs(
            temp_db, sample_block_data, block_price, age_config
        )

        # Should have spent 2 UTXOs
        assert len(spent) == 2

        # Verify they are marked as spent
        loaded_1 = load_utxo(temp_db, prev_utxo_1.outpoint)
        loaded_2 = load_utxo(temp_db, prev_utxo_2.outpoint)

        assert loaded_1 is not None and loaded_1.is_spent is True
        assert loaded_2 is not None and loaded_2.is_spent is True


# =============================================================================
# Phase 5: User Story 3 - Age Cohort Analysis Tests (T032-T034)
# =============================================================================


class TestAgeCohortAnalysis:
    """Test age cohort classification functionality."""

    def test_age_cohort_classification(self, age_config: AgeCohortsConfig):
        """T032: Test age cohort classification."""
        # Test various ages
        assert age_config.classify(0) == ("STH", "<1d")
        assert age_config.classify(3) == ("STH", "1d-1w")
        assert age_config.classify(15) == ("STH", "1w-1m")
        assert age_config.classify(60) == ("STH", "1m-3m")
        assert age_config.classify(120) == ("STH", "3m-6m")
        assert age_config.classify(200) == ("LTH", "6m-1y")
        assert age_config.classify(400) == ("LTH", "1y-2y")
        assert age_config.classify(800) == ("LTH", "2y-3y")
        assert age_config.classify(1200) == ("LTH", "3y-5y")
        assert age_config.classify(2000) == ("LTH", ">5y")

    def test_sth_lth_split(self, temp_db: duckdb.DuckDBPyConnection):
        """T033: Test STH/LTH supply split at 155-day threshold."""
        current_block = 850000

        # Create STH UTXO (< 155 days old)
        sth_utxo = UTXOLifecycle(
            outpoint="sth_utxo:0",
            txid="sth_utxo",
            vout_index=0,
            creation_block=current_block - (100 * BLOCKS_PER_DAY),  # 100 days old
            creation_timestamp=datetime.now(),
            creation_price_usd=50000.0,
            btc_value=1.0,
            realized_value_usd=50000.0,
        )

        # Create LTH UTXO (>= 155 days old)
        lth_utxo = UTXOLifecycle(
            outpoint="lth_utxo:0",
            txid="lth_utxo",
            vout_index=0,
            creation_block=current_block - (200 * BLOCKS_PER_DAY),  # 200 days old
            creation_timestamp=datetime.now(),
            creation_price_usd=45000.0,
            btc_value=2.0,
            realized_value_usd=90000.0,
        )

        save_utxo(temp_db, sth_utxo)
        save_utxo(temp_db, lth_utxo)

        sth_supply, lth_supply = get_sth_lth_supply(temp_db, current_block)

        assert sth_supply == pytest.approx(1.0)
        assert lth_supply == pytest.approx(2.0)

    def test_supply_by_cohort(
        self, temp_db: duckdb.DuckDBPyConnection, age_config: AgeCohortsConfig
    ):
        """T034: Test supply distribution by cohort."""
        current_block = 850000

        # Create UTXOs in different cohorts
        utxos = [
            (0, 1.0),  # <1d
            (10, 2.0),  # 1w-1m
            (60, 1.5),  # 1m-3m
            (400, 3.0),  # 1y-2y
        ]

        for days, btc in utxos:
            creation_block = current_block - (days * BLOCKS_PER_DAY)
            utxo = UTXOLifecycle(
                outpoint=f"cohort_{days}:0",
                txid=f"cohort_{days}",
                vout_index=0,
                creation_block=creation_block,
                creation_timestamp=datetime.now(),
                creation_price_usd=50000.0,
                btc_value=btc,
                realized_value_usd=btc * 50000.0,
            )
            save_utxo(temp_db, utxo)

        supply = get_supply_by_cohort(temp_db, current_block, age_config)

        assert supply["<1d"] == pytest.approx(1.0)
        assert supply["1w-1m"] == pytest.approx(2.0)
        assert supply["1m-3m"] == pytest.approx(1.5)
        assert supply["1y-2y"] == pytest.approx(3.0)


# =============================================================================
# Phase 7: User Story 5 - HODL Waves Tests (T048-T049)
# =============================================================================


class TestHODLWaves:
    """Test HODL Waves functionality."""

    def test_hodl_waves_calculation(
        self, temp_db: duckdb.DuckDBPyConnection, age_config: AgeCohortsConfig
    ):
        """T048: Test HODL Waves calculation."""
        from scripts.metrics.hodl_waves import calculate_hodl_waves

        current_block = 850000

        # Create UTXOs with known distribution
        utxos = [
            (10, 25.0),  # 1w-1m: 25%
            (60, 25.0),  # 1m-3m: 25%
            (400, 50.0),  # 1y-2y: 50%
        ]

        for days, btc in utxos:
            creation_block = current_block - (days * BLOCKS_PER_DAY)
            utxo = UTXOLifecycle(
                outpoint=f"hodl_{days}:0",
                txid=f"hodl_{days}",
                vout_index=0,
                creation_block=creation_block,
                creation_timestamp=datetime.now(),
                creation_price_usd=50000.0,
                btc_value=btc,
                realized_value_usd=btc * 50000.0,
            )
            save_utxo(temp_db, utxo)

        waves = calculate_hodl_waves(temp_db, current_block, age_config)

        assert waves["1w-1m"] == pytest.approx(25.0)
        assert waves["1m-3m"] == pytest.approx(25.0)
        assert waves["1y-2y"] == pytest.approx(50.0)

    def test_hodl_waves_sum_to_100(
        self, temp_db: duckdb.DuckDBPyConnection, age_config: AgeCohortsConfig
    ):
        """T049: Test that HODL Waves percentages sum to 100%."""
        from scripts.metrics.hodl_waves import calculate_hodl_waves, validate_hodl_waves

        current_block = 850000

        # Create some UTXOs
        for i in range(5):
            days = i * 100
            utxo = UTXOLifecycle(
                outpoint=f"sum_test_{i}:0",
                txid=f"sum_test_{i}",
                vout_index=0,
                creation_block=current_block - (days * BLOCKS_PER_DAY),
                creation_timestamp=datetime.now(),
                creation_price_usd=50000.0,
                btc_value=10.0,
                realized_value_usd=500000.0,
            )
            save_utxo(temp_db, utxo)

        waves = calculate_hodl_waves(temp_db, current_block, age_config)

        assert validate_hodl_waves(waves)
        assert sum(waves.values()) == pytest.approx(100.0, rel=0.01)


# =============================================================================
# Phase 8: User Story 6 - Sync & API Tests (T053-T054)
# =============================================================================


class TestSyncAndAPI:
    """Test sync state tracking functionality."""

    def test_sync_state_tracking(self, temp_db: duckdb.DuckDBPyConnection):
        """T053: Test sync state is tracked correctly."""
        block_height = 850000
        timestamp = datetime(2024, 1, 15, 12, 0, 0)

        # Initially no sync state
        state = get_sync_state(temp_db)
        assert state is None

        # Update sync state
        update_sync_state(
            temp_db, block_height, timestamp, utxos_created=100, utxos_spent=50
        )

        # Verify state
        state = get_sync_state(temp_db)
        assert state is not None
        assert state.last_processed_block == block_height
        assert state.total_utxos_created == 100
        assert state.total_utxos_spent == 50

    def test_incremental_sync(self, temp_db: duckdb.DuckDBPyConnection):
        """T054: Test incremental sync accumulates correctly."""
        # First batch
        update_sync_state(
            temp_db,
            block_height=850000,
            timestamp=datetime(2024, 1, 15, 12, 0, 0),
            utxos_created=100,
            utxos_spent=50,
        )

        # Second batch
        update_sync_state(
            temp_db,
            block_height=850100,
            timestamp=datetime(2024, 1, 16, 12, 0, 0),
            utxos_created=200,
            utxos_spent=75,
        )

        state = get_sync_state(temp_db)
        assert state is not None
        assert state.last_processed_block == 850100
        assert state.total_utxos_created == 300  # 100 + 200
        assert state.total_utxos_spent == 125  # 50 + 75


# =============================================================================
# Phase 9: NFR Validation Tests (T065a-T065b)
# =============================================================================


class TestNFRValidation:
    """Test non-functional requirements."""

    @pytest.mark.slow
    def test_block_processing_under_5_seconds(self, temp_db: duckdb.DuckDBPyConnection):
        """T065a: Test block processing completes in <5 seconds (NFR-001)."""
        import time

        # Create a block with many transactions
        block_data = {
            "height": 850000,
            "time": 1705320000,
            "tx": [],
        }

        # Add 100 transactions with 10 outputs each = 1000 UTXOs
        for i in range(100):
            tx = {
                "txid": f"perf_tx_{i:04d}",
                "vin": [{"txid": f"prev_perf_{i:04d}", "vout": 0}] if i > 0 else [],
                "vout": [{"n": j, "value": 0.1} for j in range(10)],
            }
            block_data["tx"].append(tx)

        start = time.perf_counter()
        created, spent = process_block_utxos(temp_db, block_data, 50000.0)
        elapsed = time.perf_counter() - start

        assert len(created) == 1000
        assert elapsed < 5.0, f"Block processing took {elapsed:.2f}s, exceeds 5s limit"

    @pytest.mark.slow
    def test_100k_utxos_per_block(self, temp_db: duckdb.DuckDBPyConnection):
        """T065b: Test handling 100,000+ UTXOs per block (NFR-004)."""
        # Create a large block
        block_data = {
            "height": 850000,
            "time": 1705320000,
            "tx": [],
        }

        # 1000 transactions × 100 outputs = 100,000 UTXOs
        for i in range(1000):
            tx = {
                "txid": f"stress_tx_{i:04d}",
                "vin": [],
                "vout": [{"n": j, "value": 0.001} for j in range(100)],
            }
            block_data["tx"].append(tx)

        # Process should complete without error
        created, spent = process_block_utxos(temp_db, block_data, 50000.0)

        assert len(created) == 100000
        # Verify some were stored
        count = temp_db.execute("SELECT COUNT(*) FROM utxo_lifecycle").fetchone()[0]
        assert count == 100000
